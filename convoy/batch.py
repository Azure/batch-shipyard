# Copyright (c) Microsoft Corporation
#
# All rights reserved.
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

# compat imports
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)
from builtins import (  # noqa
    bytes, dict, int, list, object, range, str, ascii, chr, hex, input,
    next, oct, open, pow, round, super, filter, map, zip)
# stdlib imports
import codecs
import collections
import concurrent.futures
import datetime
import fnmatch
import getpass
import json
import logging
import multiprocessing
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import ssl
import sys
import time
import uuid
# non-stdlib imports
import azure.batch.models as batchmodels
import azure.mgmt.batch.models as mgmtbatchmodels
import dateutil.tz
# local imports
from . import autoscale
from . import crypto
from . import data
from . import keyvault
from . import settings
from . import storage
from . import util
from .version import __version__

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_MAX_EXECUTOR_WORKERS = min((multiprocessing.cpu_count() * 4, 32))
_MAX_REBOOT_RETRIES = 5
_SSH_TUNNEL_SCRIPT = 'ssh_docker_tunnel_shipyard.sh'
_TASKMAP_PICKLE_FILE = 'taskmap.pickle'
_AUTOSCRATCH_TASK_ID = 'batch-shipyard-autoscratch'
_RUN_ELEVATED = batchmodels.UserIdentity(
    auto_user=batchmodels.AutoUserSpecification(
        scope=batchmodels.AutoUserScope.pool,
        elevation_level=batchmodels.ElevationLevel.admin,
    )
)
_RUN_UNELEVATED = batchmodels.UserIdentity(
    auto_user=batchmodels.AutoUserSpecification(
        scope=batchmodels.AutoUserScope.pool,
        elevation_level=batchmodels.ElevationLevel.non_admin,
    )
)
NodeStateCountCollection = collections.namedtuple(
    'NodeStateCountCollection', [
        'creating',
        'idle',
        'leaving_pool',
        'offline',
        'preempted',
        'rebooting',
        'reimaging',
        'running',
        'start_task_failed',
        'starting',
        'unknown',
        'unusable',
        'waiting_for_start_task',
    ]
)
_ENV_EXCLUDE_LINUX = frozenset((
    '_', 'HOME', 'HOSTNAME', 'PATH', 'PWD', 'SHLVL', 'USER',
))


def _max_workers(iterable):
    # type: (list) -> int
    """Get max number of workers for executor given an iterable
    :param list iterable: an iterable
    :rtype: int
    :return: number of workers for executor
    """
    return min((len(iterable), _MAX_EXECUTOR_WORKERS))


def get_batch_account(
        batch_mgmt_client, config, account_name=None, resource_group=None,
        raw_override=False, get_keys=False):
    # type: (azure.mgmt.batch.BatchManagementClient, dict, str, str, bool) ->
    #        Tuple[azure.mgmt.batch.models.BatchAccount,
    #              azure.mgmt.batch.models.BatchAccountKeys]
    """Get Batch account properties from ARM
    :param azure.mgmt.batch.BatchManagementClient batch_mgmt_client:
        batch management client
    :param dict config: configuration dict
    :param str account_name: account name
    :param str resource_group: resource group of Batch account
    :param bool raw_override: override raw setting
    :rtype: Tuple[azure.mgmt.batch.models.BatchAccount,
        azure.mgmt.batch.models.BatchAccountKeys]
    :return: tuple of batch account, account keys
    """
    if batch_mgmt_client is None:
        raise RuntimeError(
            'Batch management client is invalid, please specify management '
            'aad credentials and valid subscription_id')
    if (util.is_none_or_empty(account_name) or
            util.is_none_or_empty(resource_group)):
        bc = settings.credentials_batch(config)
        if util.is_none_or_empty(account_name):
            account_name = bc.account
        if util.is_none_or_empty(resource_group):
            resource_group = bc.resource_group
        if util.is_none_or_empty(bc.resource_group):
            raise ValueError(
                ('Please specify the resource_group in credentials '
                 'associated with the Batch account {}'.format(bc.account)))
    if not raw_override and settings.raw(config):
        util.print_raw_output(
            batch_mgmt_client.batch_account.get,
            resource_group_name=resource_group,
            account_name=account_name)
        return
    keys = None
    if get_keys:
        keys = batch_mgmt_client.batch_account.get_keys(
            resource_group_name=resource_group,
            account_name=account_name)
    return batch_mgmt_client.batch_account.get(
        resource_group_name=resource_group,
        account_name=account_name,
    ), keys


def _generate_batch_account_log_entry(ba):
    # type: (batchmgmtmodels.BatchAccount) -> list
    """Generate a Batch account log entry
    :param azure.mgmt.batch.models.BatchAccount ba: batch account
    :rtype: list
    :return: log entries for batch account
    """
    log = ['* name: {}'.format(ba.name)]
    # parse out sub id and resource group
    tmp = ba.id.split('/')
    log.append('  * subscription id: {}'.format(tmp[2]))
    log.append('  * resource group: {}'.format(tmp[4]))
    log.append('  * location: {}'.format(ba.location))
    log.append('  * account url: https://{}'.format(ba.account_endpoint))
    log.append('  * pool allocation mode: {}'.format(
        ba.pool_allocation_mode.value))
    if (ba.pool_allocation_mode ==
            mgmtbatchmodels.PoolAllocationMode.user_subscription):
        log.append('  * keyvault reference: {}'.format(
            ba.key_vault_reference.url))
    log.append('  * core quotas:')
    if (ba.pool_allocation_mode ==
            mgmtbatchmodels.PoolAllocationMode.user_subscription):
        log.append('    * dedicated: (see subscription regional core quotas)')
    else:
        log.append('    * dedicated: {}'.format(ba.dedicated_core_quota))
    log.append('    * low priority: {}'.format(ba.low_priority_core_quota))
    log.append('  * pool quota: {}'.format(ba.pool_quota))
    log.append('  * active job and job schedule quota: {}'.format(
        ba.active_job_and_job_schedule_quota))
    return log


def log_batch_account_info(
        batch_mgmt_client, config, account_name=None, resource_group=None):
    # type: (azure.mgmt.batch.BatchManagementClient, dict, str, str) -> None
    """Log Batch account properties from ARM
    :param azure.mgmt.batch.BatchManagementClient batch_mgmt_client:
        batch management client
    :param dict config: configuration dict
    :param str account_name: account name
    :param str resource_group: resource group of Batch account
    """
    ba, _ = get_batch_account(
        batch_mgmt_client, config, account_name=account_name,
        resource_group=resource_group)
    if settings.raw(config):
        return
    log = ['batch account information']
    log.extend(_generate_batch_account_log_entry(ba))
    logger.info(os.linesep.join(log))


def log_batch_account_list(batch_mgmt_client, config, resource_group=None):
    # type: (azure.mgmt.batch.BatchManagementClient, dict, str) -> None
    """Log Batch account properties from ARM
    :param azure.mgmt.batch.BatchManagementClient batch_mgmt_client:
        batch management client
    :param dict config: configuration dict
    :param str resource_group: resource group of Batch account
    """
    if batch_mgmt_client is None:
        raise RuntimeError(
            'Batch management client is invalid, please specify management '
            'aad credentials and valid subscription_id')
    if resource_group is None:
        accounts = batch_mgmt_client.batch_account.list()
    else:
        accounts = batch_mgmt_client.batch_account.list_by_resource_group(
            resource_group)
    mgmt_aad = settings.credentials_management(config)
    log = ['all batch accounts in subscription {}'.format(
        mgmt_aad.subscription_id)]
    for ba in accounts:
        log.extend(_generate_batch_account_log_entry(ba))
    if len(log) == 1:
        logger.error('no batch accounts found in subscription {}'.format(
            mgmt_aad.subscription_id))
    else:
        logger.info(os.linesep.join(log))


def log_batch_account_service_quota(batch_mgmt_client, config, location):
    # type: (azure.mgmt.batch.BatchManagementClient, dict, str) -> None
    """Log Batch account service quota
    :param azure.mgmt.batch.BatchManagementClient batch_mgmt_client:
        batch management client
    :param dict config: configuration dict
    :param str location: location
    """
    if batch_mgmt_client is None:
        raise RuntimeError(
            'Batch management client is invalid, please specify management '
            'aad credentials and valid subscription_id')
    mgmt_aad = settings.credentials_management(config)
    if settings.raw(config):
        util.print_raw_output(
            batch_mgmt_client.location.get_quotas, location)
        return
    blc = batch_mgmt_client.location.get_quotas(location)
    log = ['batch service quota']
    log.append('* subscription id: {}'.format(mgmt_aad.subscription_id))
    log.append('  * location: {}'.format(location))
    log.append('  * account quota: {}'.format(blc.account_quota))
    logger.info(os.linesep.join(log))


def list_supported_images(
        batch_client, config, show_unrelated=False, show_unverified=False):
    # type: (batch.BatchServiceClient, dict, bool, bool) -> None
    """List all supported images for the account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.BatchServiceClient`
    :param dict config: configuration dict
    :param bool show_unrelated: show unrelated
    :param bool show_unverified: show unverified images
    """
    if show_unverified:
        args = []
    else:
        args = [batchmodels.AccountListSupportedImagesOptions(
            filter='verificationType eq \'verified\'')]
    if settings.raw(config):
        util.print_raw_paged_output(
            batch_client.account.list_supported_images, *args)
        return
    images = batch_client.account.list_supported_images(*args)
    image_map = {}
    for image in images:
        os_type = image.os_type.value
        if os_type not in image_map:
            image_map[os_type] = {}
        if (not show_unrelated and
                image.image_reference.publisher.lower() not in
                settings.get_valid_publishers()):
            continue
        if image.image_reference.publisher not in image_map[os_type]:
            image_map[os_type][image.image_reference.publisher] = {}
        if (image.image_reference.offer not in
                image_map[os_type][image.image_reference.publisher]):
            image_map[os_type][image.image_reference.publisher][
                image.image_reference.offer] = []
        image_map[os_type][image.image_reference.publisher][
            image.image_reference.offer].append({
                'sku': image.image_reference.sku,
                'na_sku': image.node_agent_sku_id,
                'verification': image.verification_type,
                'capabilities': image.capabilities,
                'support_eol': image.batch_support_end_of_life,
            })
    log = ['supported images (include unrelated={}, '
           'include unverified={})'.format(show_unrelated, show_unverified)]
    for os_type in image_map:
        log.append('* os type: {}'.format(os_type))
        for publisher in image_map[os_type]:
            log.append('  * publisher: {}'.format(publisher))
            for offer in image_map[os_type][publisher]:
                log.append('    * offer: {}'.format(offer))
                for image in image_map[os_type][publisher][offer]:
                    log.append('      * sku: {}'.format(image['sku']))
                    if util.is_not_empty(image['capabilities']):
                        log.append('        * capabilities: {}'.format(
                            ','.join(image['capabilities'])))
                    log.append('        * verification: {}'.format(
                        image['verification']))
                    if image['support_eol'] is not None:
                        log.append('        * batch support eol: {}'.format(
                            image['support_eol'].strftime("%Y-%m-%d")))
                    log.append('        * node agent sku id: {}'.format(
                        image['na_sku']))
    logger.info(os.linesep.join(log))


def get_node_agent_for_image(batch_client, config, publisher, offer, sku):
    # type: (batch.BatchServiceClient, dict, str, str, str) -> tuple
    """Get node agent for image
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.BatchServiceClient`
    :param dict config: configuration dict
    :param str publisher: publisher
    :param str offer: offer
    :param str sku: sku
    :rtype: tuple
    :return: image ref and node agent sku id
    """
    images = batch_client.account.list_supported_images()
    for image in images:
        if (image.image_reference.publisher.lower() == publisher.lower() and
                image.image_reference.offer.lower() == offer.lower() and
                image.image_reference.sku.lower() == sku.lower()):
            return image.image_reference, image.node_agent_sku_id
    return None, None


def add_certificate_to_account(
        batch_client, config, file, pem_no_certs, pem_public_key,
        pfx_password):
    # type: (batch.BatchServiceClient, dict, str, bool, bool, str) -> None
    """Adds a certificate to a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str file: file to add
    :param bool pem_no_certs: don't export certs from pem
    :param bool pem_public_key: only add public key from pem
    :param str pfx_password: pfx password
    """
    # retrieve encryption cert from config if file isn't specified
    if util.is_none_or_empty(file):
        pfx = crypto.get_encryption_pfx_settings(config)
        add_pfx_cert_to_account(
            batch_client, config, pfx, pfx_password=None, rm_pfxfile=False)
        return
    fpath = pathlib.Path(file)
    if not fpath.exists():
        raise ValueError('certificate file {} does not exist'.format(fpath))
    fext = fpath.suffix.lower()
    if fext == '.cer':
        add_cer_cert_to_account(batch_client, config, file, rm_cerfile=False)
    elif fext == '.pem':
        if pem_public_key:
            # export public portion as cer
            cer = crypto.convert_pem_to_cer(file, pem_no_certs)
            if util.is_none_or_empty(cer):
                raise RuntimeError(
                    'could not convert pem {} to cer'.format(file))
            add_cer_cert_to_account(batch_client, config, cer, rm_cerfile=True)
        else:
            # export pem as pfx
            pfx, pfx_password = crypto.convert_pem_to_pfx(
                file, pem_no_certs, pfx_password)
            if util.is_none_or_empty(pfx):
                raise RuntimeError(
                    'could not convert pem {} to pfx'.format(file))
            add_pfx_cert_to_account(
                batch_client, config, pfx, pfx_password=pfx_password,
                rm_pfxfile=True)
    elif fext == '.pfx':
        add_pfx_cert_to_account(
            batch_client, config, file, pfx_password=pfx_password,
            rm_pfxfile=False)
    else:
        raise ValueError(
            'unknown certificate format {} for file {}'.format(fext, fpath))


def add_cer_cert_to_account(batch_client, config, cer, rm_cerfile=False):
    # type: (batch.BatchServiceClient, dict, str, bool) -> None
    """Adds a cer certificate to a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str cer: cer file to add
    :param bool rm_cerfile: remove CER file from local disk
    """
    # get thumbprint for cer
    thumbprint = crypto.get_sha1_thumbprint_cer(cer)
    # first check if this cert exists
    bc = settings.credentials_batch(config)
    certs = batch_client.certificate.list()
    for cert in certs:
        if cert.thumbprint.lower() == thumbprint:
            logger.error(
                'cert with thumbprint {} already exists for account {}'.format(
                    thumbprint, bc.account))
            # remove cerfile
            if rm_cerfile:
                os.unlink(cer)
            return
    # add cert to account
    data = util.base64_encode_string(open(cer, 'rb').read())
    batch_client.certificate.add(
        certificate=batchmodels.CertificateAddParameter(
            thumbprint=thumbprint,
            thumbprint_algorithm='sha1',
            data=data,
            certificate_format=batchmodels.CertificateFormat.cer)
    )
    logger.info('added cer cert with thumbprint {} to account {}'.format(
        thumbprint, bc.account))
    # remove cerfile
    if rm_cerfile:
        os.unlink(cer)


def add_pfx_cert_to_account(
        batch_client, config, pfx, pfx_password=None, rm_pfxfile=False):
    # type: (batch.BatchServiceClient, dict, str, bool) -> None
    """Adds a pfx certificate to a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str sha1_cert_tp: sha1 thumbprint of pfx
    :param str pfx_password: pfx password
    :param bool rm_pfxfile: remove PFX file from local disk
    """
    if not isinstance(pfx, crypto.PfxSettings):
        pfx = crypto.PfxSettings(
            filename=pfx,
            passphrase=pfx_password,
            sha1=crypto.get_sha1_thumbprint_pfx(pfx, pfx_password),
        )
    # first check if this cert exists
    bc = settings.credentials_batch(config)
    certs = batch_client.certificate.list()
    for cert in certs:
        if cert.thumbprint.lower() == pfx.sha1:
            logger.error(
                'cert with thumbprint {} already exists for account {}'.format(
                    pfx.sha1, bc.account))
            # remove pfxfile
            if rm_pfxfile:
                os.unlink(pfx.filename)
            return
    # set pfx password
    passphrase = pfx.passphrase or getpass.getpass('Enter password for PFX: ')
    # add cert to account
    data = util.base64_encode_string(open(pfx.filename, 'rb').read())
    batch_client.certificate.add(
        certificate=batchmodels.CertificateAddParameter(
            thumbprint=pfx.sha1,
            thumbprint_algorithm='sha1',
            data=data,
            certificate_format=batchmodels.CertificateFormat.pfx,
            password=passphrase)
    )
    logger.info('added pfx cert with thumbprint {} to account {}'.format(
        pfx.sha1, bc.account))
    # remove pfxfile
    if rm_pfxfile:
        os.unlink(pfx.filename)


def list_certificates_in_account(batch_client, config):
    # type: (batch.BatchServiceClient, dict) -> None
    """List all certificates in a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    if settings.raw(config):
        util.print_raw_paged_output(batch_client.certificate.list)
        return
    i = 0
    log = ['list of certificates']
    certs = batch_client.certificate.list()
    for cert in certs:
        log.extend([
            '* thumbprint: {}'.format(cert.thumbprint),
            '  * thumbprint algorithm: {}'.format(cert.thumbprint_algorithm),
            '  * state: {} @ {}'.format(
                cert.state.value, cert.state_transition_time),
            '  * previous state: {} @ {}'.format(
                cert.previous_state.value
                if cert.previous_state is not None else 'n/a',
                cert.previous_state_transition_time),
        ])
        if cert.delete_certificate_error is not None:
            log.append('  * delete error: {}: {}'.format(
                cert.delete_certificate_error.code,
                cert.delete_certificate_error.message))
            for de in cert.delete_certificate_error.values:
                log.append('    * {}: {}'.format(de.name, de.value))
        else:
            log.append('  * no delete errors')
        i += 1
    if i == 0:
        logger.error('no certificates found')
    else:
        logger.info(os.linesep.join(log))


def del_certificate_from_account(batch_client, config, sha1):
    # type: (batch.BatchServiceClient, dict, List[str]) -> None
    """Delete a certificate from a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list sha1: list of sha1 thumbprints to delete
    """
    if util.is_none_or_empty(sha1):
        pfx = crypto.get_encryption_pfx_settings(config)
        sha1 = [pfx.sha1]
    bc = settings.credentials_batch(config)
    certs_to_del = []
    for tp in sha1:
        if not util.confirm_action(
                config, 'delete certificate {} from account {}'.format(
                    tp, bc.account)):
            continue
        certs_to_del.append(tp)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_max_workers(certs_to_del)) as executor:
        for tp in certs_to_del:
            executor.submit(batch_client.certificate.delete, 'sha1', tp)
    logger.info('certificates {} deleted from account {}'.format(
        certs_to_del, bc.account))


def _reboot_node(batch_client, pool_id, node_id, wait):
    # type: (batch.BatchServiceClient, str, str, bool) -> None
    """Reboot a node in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str pool_id: pool id of node
    :param str node_id: node id to delete
    :param bool wait: wait for node to enter rebooting state
    """
    if util.is_none_or_empty(node_id):
        raise ValueError('node id must be specified for reboot')
    logger.info('Rebooting node {} in pool {}'.format(node_id, pool_id))
    batch_client.compute_node.reboot(
        pool_id=pool_id,
        node_id=node_id,
    )
    if wait:
        logger.debug('waiting for node {} to enter rebooting state'.format(
            node_id))
        while True:
            node = batch_client.compute_node.get(pool_id, node_id)
            if node.state == batchmodels.ComputeNodeState.rebooting:
                break
            else:
                time.sleep(1)


def _retrieve_outputs_from_failed_nodes(batch_client, config, nodeid=None):
    # type: (batch.BatchServiceClient, dict) -> None
    """Retrieve stdout/stderr from failed nodes
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    is_windows = settings.is_windows_pool(config)
    pool_id = settings.pool_id(config)
    if nodeid is None:
        nodes = batch_client.compute_node.list(pool_id)
    else:
        nodes = [batch_client.compute_node.get(pool_id, nodeid)]
    if is_windows:
        sep = '\\'
    else:
        sep = '/'
    stdfilter = sep.join(('startup', 'std*.txt'))
    cascadelog = sep.join(('startup', 'wd', 'cascade*.log'))
    # for any node in state start task failed, retrieve the stdout and stderr
    for node in nodes:
        if node.state == batchmodels.ComputeNodeState.start_task_failed:
            settings.set_auto_confirm(config, True)
            get_all_files_via_node(
                batch_client, config,
                filespec='{},{}'.format(node.id, stdfilter))
            try:
                get_all_files_via_node(
                    batch_client, config,
                    filespec='{},{}'.format(node.id, cascadelog))
            except batchmodels.BatchErrorException:
                pass


def _block_for_nodes_ready(
        batch_client, blob_client, config, stopping_states, end_states,
        pool_id):
    # type: (batch.BatchServiceClient, azure.storage.blob.BlockBlobClient,
    #        dict, List[batchmodels.ComputeNodeState],
    #        List[batchmodels.ComputeNodeState],
    #        str) -> List[batchmodels.ComputeNode]
    """Wait for pool to enter steady state and all nodes to enter stopping
    states
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param list stopping_states: list of node states to stop polling
    :param list end_states: list of acceptable end states
    :param str pool_id: pool id
    :rtype: list
    :return: list of nodes
    """
    logger.debug(
        'waiting for all nodes in pool {} to reach one of: {!r}'.format(
            pool_id, stopping_states))
    pool_settings = settings.pool_settings(config)
    reboot_map = {}
    failed_node_list_count = 0
    unusable_delete = False
    last = time.time()
    while True:
        # refresh pool to ensure that there is no dedicated resize error
        pool = batch_client.pool.get(pool_id)
        total_nodes = (
            pool.target_dedicated_nodes + pool.target_low_priority_nodes
        )
        if util.is_not_empty(pool.resize_errors):
            fatal_resize_error = False
            errors = []
            for err in pool.resize_errors:
                errors.append('{}: {}'.format(err.code, err.message))
                if (err.code == 'AccountCoreQuotaReached' or
                        (err.code == 'AccountLowPriorityCoreQuotaReached' and
                         pool.target_dedicated_nodes == 0) or
                        (err.code == 'AllocationTimedout' and
                         pool.target_dedicated_nodes > 0) or
                        (err.code == 'AllocationTimedout' and
                         pool.allocation_state ==
                         batchmodels.AllocationState.steady)):
                    fatal_resize_error = True
            if fatal_resize_error:
                pool_stats(batch_client, config, pool_id=pool_id)
                raise RuntimeError(
                    'Fatal resize errors encountered for pool {}: {}'.format(
                        pool.id, os.linesep.join(errors)))
            else:
                logger.error(
                    'Resize errors encountered for pool {}: {}'.format(
                        pool.id, os.linesep.join(errors)))
        # check pool allocation state
        try:
            nodes = list(batch_client.compute_node.list(pool.id))
            failed_node_list_count = 0
        except ssl.SSLError:
            # SSL error happens sometimes on paging... this is probably
            # a bug in the underlying msrest/msrestazure library that
            # is reusing the SSL connection improperly
            nodes = []
            failed_node_list_count += 1
        # check if any nodes are in start task failed state
        if (any(node.state == batchmodels.ComputeNodeState.start_task_failed
                for node in nodes)):
            # list nodes to dump exact error
            logger.debug('listing nodes in start task failed state')
            list_nodes(
                batch_client, config, pool_id=pool_id, nodes=nodes,
                start_task_failed=True)
            # attempt reboot if enabled for potentially transient errors
            if pool_settings.reboot_on_start_task_failed:
                for node in nodes:
                    if (node.state !=
                            batchmodels.ComputeNodeState.start_task_failed):
                        continue
                    if node.id not in reboot_map:
                        reboot_map[node.id] = 0
                        logger.error(
                            ('Detected start task failure, attempting to '
                             'retrieve files for error diagnosis from '
                             'node {}').format(node.id))
                        _retrieve_outputs_from_failed_nodes(
                            batch_client, config, nodeid=node.id)
                    if reboot_map[node.id] > _MAX_REBOOT_RETRIES:
                        pool_stats(batch_client, config, pool_id=pool_id)
                        raise RuntimeError(
                            ('Ran out of reboot retries for recovery. '
                             'Please inspect both the node status above and '
                             'files found within the {}/{}/startup directory '
                             '(in the current working directory) if '
                             'available. If this error appears '
                             'non-transient, please submit an issue on '
                             'GitHub, if not you can delete these nodes with '
                             '"pool nodes del --all-start-task-failed" first '
                             'prior to the resize operation.').format(
                                 pool.id, node.id))
                    _reboot_node(batch_client, pool.id, node.id, True)
                    reboot_map[node.id] += 1
                # refresh node list to reflect rebooting states
                try:
                    nodes = list(batch_client.compute_node.list(pool.id))
                    failed_node_list_count = 0
                except ssl.SSLError:
                    nodes = []
                    failed_node_list_count += 1
            else:
                # fast path check for start task failures in non-reboot mode
                logger.error(
                    'Detected start task failure, attempting to retrieve '
                    'files for error diagnosis from nodes')
                _retrieve_outputs_from_failed_nodes(batch_client, config)
                raise RuntimeError(
                    ('Please inspect both the node status above and '
                     'files found within the {}/<nodes>/startup directory '
                     '(in the current working directory) if available. If '
                     'this error appears non-transient, please submit an '
                     'issue on GitHub, if not you can delete these nodes '
                     'with "pool nodes del --all-start-task-failed" first '
                     'prior to the resize operation.').format(pool.id))
        # check if any nodes are in unusable state
        elif (any(node.state == batchmodels.ComputeNodeState.unusable
                  for node in nodes)):
            # list nodes to dump exact error
            logger.debug('listing nodes in unusable state')
            list_nodes(
                batch_client, config, pool_id=pool_id, nodes=nodes,
                unusable=True)
            # upload diagnostics logs if specified
            if pool_settings.upload_diagnostics_logs_on_unusable:
                for node in nodes:
                    if node.state == batchmodels.ComputeNodeState.unusable:
                        egress_service_logs(
                            batch_client, blob_client, config,
                            node_id=node.id, generate_sas=True,
                            wait=pool_settings.attempt_recovery_on_unusable)
            # attempt recovery if specified
            if pool_settings.attempt_recovery_on_unusable:
                logger.warning(
                    'Unusable nodes detected, deleting unusable nodes')
                del_nodes(
                    batch_client, config, False, False, True, None,
                    suppress_confirm=True)
                unusable_delete = True
            else:
                raise RuntimeError(
                    ('Unusable nodes detected in pool {}. You can delete '
                     'unusable nodes with "pool nodes del --all-unusable" '
                     'first prior to the resize operation.').format(
                         pool.id))
        # check for full allocation
        if (len(nodes) == total_nodes and
                all(node.state in stopping_states for node in nodes)):
            if any(node.state not in end_states for node in nodes):
                pool_stats(batch_client, config, pool_id=pool_id)
                raise RuntimeError(
                    ('Node(s) of pool {} not in {} state. Please inspect the '
                     'state of nodes in the pool above. If this appears to '
                     'be a transient error, please retry pool creation or '
                     'the resize operation. If any unusable nodes exist, you '
                     'can delete them with "pool nodes del --all-unusable" '
                     'first prior to the resize operation.').format(
                         pool.id, end_states))
            else:
                return nodes
        # issue resize if unusable deletion has occurred
        if (unusable_delete and len(nodes) < total_nodes and
                pool.allocation_state != batchmodels.AllocationState.resizing):
            resize_pool(batch_client, blob_client, config, wait=False)
            unusable_delete = False
        now = time.time()
        if (now - last) > 20:
            last = now
            logger.debug(
                ('waiting for {} dedicated nodes and {} low priority '
                 'nodes of size {} to reach desired state in pool {} '
                 '[resize_timeout={} allocation_state={} '
                 'allocation_state_transition_time={}]').format(
                     pool.target_dedicated_nodes,
                     pool.target_low_priority_nodes,
                     pool.vm_size,
                     pool.id,
                     pool.resize_timeout,
                     pool.allocation_state.value,
                     pool.allocation_state_transition_time))
            if len(nodes) <= 3:
                for node in nodes:
                    logger.debug('{}: {}'.format(node.id, node.state.value))
            else:
                logger.debug(_node_state_counts(nodes))
            if failed_node_list_count > 0:
                logger.error(
                    'could not get a valid node list for pool: {}'.format(
                        pool.id))
        if len(nodes) < 10:
            time.sleep(3)
        elif len(nodes) < 50:
            time.sleep(6)
        elif len(nodes) < 100:
            time.sleep(12)
        else:
            time.sleep(24)


def _node_state_counts(nodes):
    # type: (List[batchmodels.ComputeNode]) -> NodeStateCountCollection
    """Collate counts of various nodes
    :param list nodes: list of nodes
    :rtype: NodeStateCountCollection
    :return: node state count collection
    """
    node_states = [node.state for node in nodes]
    return NodeStateCountCollection(
        creating=node_states.count(batchmodels.ComputeNodeState.creating),
        idle=node_states.count(batchmodels.ComputeNodeState.idle),
        leaving_pool=node_states.count(
            batchmodels.ComputeNodeState.leaving_pool),
        offline=node_states.count(batchmodels.ComputeNodeState.offline),
        preempted=node_states.count(batchmodels.ComputeNodeState.preempted),
        rebooting=node_states.count(batchmodels.ComputeNodeState.rebooting),
        reimaging=node_states.count(batchmodels.ComputeNodeState.reimaging),
        running=node_states.count(batchmodels.ComputeNodeState.running),
        start_task_failed=node_states.count(
            batchmodels.ComputeNodeState.start_task_failed),
        starting=node_states.count(batchmodels.ComputeNodeState.starting),
        unknown=node_states.count(batchmodels.ComputeNodeState.unknown),
        unusable=node_states.count(batchmodels.ComputeNodeState.unusable),
        waiting_for_start_task=node_states.count(
            batchmodels.ComputeNodeState.waiting_for_start_task),
    )


def wait_for_pool_ready(
        batch_client, blob_client, config, pool_id, addl_end_states=None):
    # type: (batch.BatchServiceClient, azure.storage.blob.BlockBlobCLient,
    #        dict, str, List[batchmodels.ComputeNode]) ->
    #        List[batchmodels.ComputeNode]
    """Wait for pool to enter steady state and all nodes in end states
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param str pool_id: pool id
    :param list addl_end_states: additional end states
    :rtype: list
    :return: list of nodes
    """
    base_stopping_states = [
        batchmodels.ComputeNodeState.start_task_failed,
        batchmodels.ComputeNodeState.unusable,
        batchmodels.ComputeNodeState.preempted,
        batchmodels.ComputeNodeState.idle,
    ]
    base_end_states = [
        batchmodels.ComputeNodeState.preempted,
        batchmodels.ComputeNodeState.idle,
    ]
    if addl_end_states is not None and len(addl_end_states) > 0:
        base_stopping_states.extend(addl_end_states)
        base_end_states.extend(addl_end_states)
    stopping_states = frozenset(base_stopping_states)
    end_states = frozenset(base_end_states)
    nodes = _block_for_nodes_ready(
        batch_client, blob_client, config, stopping_states, end_states,
        pool_id)
    pool_stats(batch_client, config, pool_id=pool_id)
    return nodes


def check_pool_nodes_runnable(batch_client, config):
    # type: (batch.BatchServiceClient, dict) -> bool
    """Check that all pool nodes in idle/running state
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :rtype: bool
    :return: all pool nodes are runnable
    """
    pool_id = settings.pool_id(config)
    node_state = frozenset(
        (batchmodels.ComputeNodeState.idle,
         batchmodels.ComputeNodeState.running)
    )
    pool = batch_client.pool.get(pool_id)
    nodes = list(batch_client.compute_node.list(pool_id))
    if (len(nodes) >=
            (pool.target_dedicated_nodes + pool.target_low_priority_nodes) and
            all(node.state in node_state for node in nodes)):
        return True
    return False


def create_pool(batch_client, blob_client, config, pool):
    # type: (batch.BatchServiceClient, azure.storage.blob.BlockBlobService,
    #        dict, batchmodels.PoolAddParameter) ->
    #        List[batchmodels.ComputeNode]
    """Create pool if not exists
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param batchmodels.PoolAddParameter pool: pool addparameter object
    :rtype: list
    :return: list of nodes
    """
    # create pool if not exists
    try:
        logger.info('Attempting to create pool: {}'.format(pool.id))
        if settings.verbose(config):
            logger.debug('node prep commandline: {}'.format(
                pool.start_task.command_line))
        batch_client.pool.add(pool)
        logger.info('Created pool: {}'.format(pool.id))
    except batchmodels.BatchErrorException as e:
        if e.error.code != 'PoolExists':
            if len(e.error.values) == 0:
                raise
            else:
                logger.error('{}: {}'.format(
                    e.error.code, e.error.message.value))
                for detail in e.error.values:
                    logger.error('{}: {}'.format(detail.key, detail.value))
                sys.exit(1)
        else:
            logger.error('Pool {!r} already exists'.format(pool.id))
    # wait for pool idle
    return wait_for_pool_ready(batch_client, blob_client, config, pool.id)


def _add_admin_user_to_compute_node(
        batch_client, pool, node, username, ssh_public_key_data, rdp_password,
        expiry=None):
    # type: (batch.BatchServiceClient, dict, str, batchmodels.ComputeNode,
    #        str, str, datetime.datetime) -> None
    """Adds an administrative user to the Batch Compute Node with a default
    expiry time of 7 days if not specified.
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param settings.PoolSpecification pool: pool settings
    :param node: The compute node.
    :type node: `azure.batch.batch_service_client.models.ComputeNode`
    :param str username: user name
    :param str ssh_public_key_data: ssh rsa public key data
    :param str rdp_password: rdp password
    :param datetime.datetime expiry: expiry
    """
    if expiry is None:
        expiry = datetime.datetime.utcnow() + datetime.timedelta(
            pool.ssh.expiry_days)
    logger.info('adding user {} to node {} in pool {}, expiry={}'.format(
        username, node.id, pool.id, expiry))
    try:
        batch_client.compute_node.add_user(
            pool.id,
            node.id,
            batchmodels.ComputeNodeUser(
                name=username,
                is_admin=True,
                expiry_time=expiry,
                password=rdp_password,
                ssh_public_key=ssh_public_key_data,
            )
        )
    except batchmodels.BatchErrorException as ex:
        if 'The specified node user already exists' in ex.message.value:
            logger.warning('user {} already exists on node {}'.format(
                username, node.id))
        else:
            # log as error instead of raising the exception in case
            # of low-priority removal
            logger.error(ex.message.value)


def add_rdp_user(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict,
    #        List[batchmodels.ComputeNode]) -> None
    """Add an RDP user to all nodes of a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    """
    pool = settings.pool_settings(config)
    is_windows = settings.is_windows_pool(config)
    if not is_windows:
        logger.debug('skipping rdp config for linux pool {}'.format(pool.id))
        return
    if util.is_none_or_empty(pool.rdp.username):
        logger.info('not creating rdp user on pool {}'.format(pool.id))
        return
    password = pool.rdp.password
    if util.is_none_or_empty(password):
        password = crypto.generate_rdp_password().decode('ascii')
        logger.info(
            ('randomly generated password for RDP user {} on pool {} '
             'is {}').format(
                 pool.rdp.username, pool.id, password))
    # get node list if not provided
    if nodes is None:
        nodes = batch_client.compute_node.list(pool.id)
    expiry = datetime.datetime.utcnow() + datetime.timedelta(
        pool.rdp.expiry_days)
    nodes = list(nodes)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_max_workers(nodes)) as executor:
        for node in nodes:
            executor.submit(
                _add_admin_user_to_compute_node,
                batch_client, pool, node, pool.rdp.username, None, password,
                expiry=expiry)


def add_ssh_user(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict,
    #        List[batchmodels.ComputeNode]) -> None
    """Add an SSH user to all nodes of a pool and optionally generate a
    SSH tunneling script
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    """
    pool = settings.pool_settings(config)
    is_windows = settings.is_windows_pool(config)
    if is_windows:
        logger.debug('skipping ssh config for windows pool {}'.format(pool.id))
        return
    if util.is_none_or_empty(pool.ssh.username):
        logger.info('not creating ssh user on pool {}'.format(pool.id))
        return
    # read public key data from settings if available
    if util.is_not_empty(pool.ssh.ssh_public_key_data):
        ssh_pub_key_data = pool.ssh.ssh_public_key_data
        ssh_priv_key = pool.ssh.ssh_private_key
    else:
        # generate ssh key pair if not specified
        if pool.ssh.ssh_public_key is None:
            ssh_priv_key, ssh_pub_key = crypto.generate_ssh_keypair(
                pool.ssh.generated_file_export_path)
        else:
            ssh_pub_key = pool.ssh.ssh_public_key
            ssh_priv_key = pool.ssh.ssh_private_key
        # read public key data
        with ssh_pub_key.open('rb') as fd:
            ssh_pub_key_data = fd.read().decode('utf8')
    # get node list if not provided
    if nodes is None:
        nodes = batch_client.compute_node.list(pool.id)
    expiry = datetime.datetime.utcnow() + datetime.timedelta(
        pool.ssh.expiry_days)
    nodes = list(nodes)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_max_workers(nodes)) as executor:
        for node in nodes:
            executor.submit(
                _add_admin_user_to_compute_node,
                batch_client, pool, node, pool.ssh.username, ssh_pub_key_data,
                None, expiry=expiry)
    # generate tunnel script if requested
    generate_ssh_tunnel_script(batch_client, config, ssh_priv_key, nodes=nodes)


def generate_ssh_tunnel_script(
        batch_client, config, ssh_priv_key, nodes=None, rls=None):
    # type: (batch.BatchServiceClient, dict, str,
    #        List[batchmodels.ComputeNode]) -> None
    """Generate SSH tunneling script
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str ssh_priv_key: path to ssh private key
    :param list nodes: list of nodes
    """
    pool = settings.pool_settings(config)
    if not pool.ssh.generate_docker_tunnel_script:
        return
    if util.on_windows():
        logger.error('cannot generate tunnel script on Windows')
        return
    if settings.is_windows_pool(None, vm_config=pool.vm_configuration):
        logger.debug(
            'cannot generate tunnel script for windows pool {}'.format(
                pool.id))
        return
    if rls is None:
        if nodes is None or len(list(nodes)) != pool.vm_count:
            nodes = batch_client.compute_node.list(pool.id)
        rls = get_remote_login_settings(
            batch_client, config, nodes=nodes, suppress_output=True)
    if ssh_priv_key is None:
        ssh_priv_key = pathlib.Path(
            pool.ssh.generated_file_export_path,
            crypto.get_ssh_key_prefix())
    if not ssh_priv_key.exists():
        logger.warning(
            ('cannot generate tunnel script with non-existant RSA '
             'private key: {}').format(ssh_priv_key))
        return
    if not crypto.check_ssh_private_key_filemode(ssh_priv_key):
        logger.warning(
            'SSH private key filemode is too permissive: {}'.format(
                ssh_priv_key))
    ssh_args = [
        'ssh', '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile={}'.format(os.devnull),
        '-i', str(ssh_priv_key), '-p', '$port', '-N',
        '-L', '2375:localhost:2375', '-L', '3476:localhost:3476',
        '{}@$ip'.format(pool.ssh.username)
    ]
    tunnelscript = pathlib.Path(
        pool.ssh.generated_file_export_path, _SSH_TUNNEL_SCRIPT)
    with tunnelscript.open('w') as fd:
        fd.write('#!/usr/bin/env bash\n')
        fd.write('set -e\n')
        # populate node arrays
        fd.write('declare -A nodes\n')
        fd.write('declare -A ips\n')
        fd.write('declare -A ports\n')
        i = 0
        for node_id in rls:
            fd.write('nodes[{}]={}\n'.format(i, node_id))
            fd.write('ips[{}]={}\n'.format(
                i, rls[node_id].remote_login_ip_address))
            fd.write('ports[{}]={}\n'.format(
                i, rls[node_id].remote_login_port))
            i += 1
        fd.write(
            'if [ -z $1 ]; then echo must specify node cardinal; exit 1; '
            'fi\n')
        fd.write('node=${nodes[$1]}\n')
        fd.write('ip=${ips[$1]}\n')
        fd.write('port=${ports[$1]}\n')
        fd.write(
            'echo tunneling to docker daemon on $node at '
            '$ip:$port\n')
        fd.write(' '.join(ssh_args))
        fd.write(' >{} 2>&1 &\n'.format(os.devnull))
        fd.write('pid=$!\n')
        fd.write('echo ssh tunnel pid is $pid\n')
        fd.write(
            'echo execute docker commands with DOCKER_HOST=: or with '
            'option: -H :\n')
    os.chmod(str(tunnelscript), 0o755)
    logger.info('ssh tunnel script generated: {}'.format(tunnelscript))


def _del_remote_user(batch_client, pool_id, node_id, username):
    # type: (batch.BatchServiceClient, str, str, str) -> None
    """Delete a remote user on a node
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str pool_id: pool id
    :param str node_id: node id
    :param str username: user name
    """
    try:
        batch_client.compute_node.delete_user(
            pool_id, node_id, username)
        logger.debug('deleted remote user {} from node {}'.format(
            username, node_id))
    except batchmodels.BatchErrorException as ex:
        if 'The node user does not exist' not in ex.message.value:
            raise


def del_rdp_user(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict,
    #        List[batchmodels.ComputeNode]) -> None
    """Delete an RDP user on all nodes of a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    """
    pool = settings.pool_settings(config)
    is_windows = settings.is_windows_pool(config)
    if not is_windows:
        logger.debug('skipping rdp user delete for linux pool {}'.format(
            pool.id))
        return
    if util.is_none_or_empty(pool.rdp.username):
        logger.error('not deleting unspecified rdp user on pool {}'.format(
            pool.id))
        return
    if not util.confirm_action(
            config, 'delete user {} from pool {}'.format(
                pool.rdp.username, pool.id)):
        return
    # get node list if not provided
    if nodes is None:
        nodes = batch_client.compute_node.list(pool.id)
    nodes = list(nodes)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_max_workers(nodes)) as executor:
        for node in nodes:
            executor.submit(
                _del_remote_user, batch_client, pool.id, node.id,
                pool.rdp.username)


def del_ssh_user(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict,
    #        List[batchmodels.ComputeNode]) -> None
    """Delete an SSH user on all nodes of a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    """
    pool = settings.pool_settings(config)
    is_windows = settings.is_windows_pool(config)
    if is_windows:
        logger.debug('skipping ssh user delete for windows pool {}'.format(
            pool.id))
        return
    if util.is_none_or_empty(pool.ssh.username):
        logger.error('not deleting unspecified ssh user on pool {}'.format(
            pool.id))
        return
    if not util.confirm_action(
            config, 'delete user {} from pool {}'.format(
                pool.ssh.username, pool.id)):
        return
    # get node list if not provided
    if nodes is None:
        nodes = batch_client.compute_node.list(pool.id)
    nodes = list(nodes)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_max_workers(nodes)) as executor:
        for node in nodes:
            executor.submit(
                _del_remote_user, batch_client, pool.id, node.id,
                pool.ssh.username)


def list_pools(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient,
    #        config) -> None
    """List pools
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    if settings.raw(config):
        util.print_raw_paged_output(batch_client.pool.list)
        return
    i = 0
    log = ['list of pools']
    pools = batch_client.pool.list()
    for pool in pools:
        if util.is_not_empty(pool.resize_errors):
            errors = ['  * resize errors:']
            for err in pool.resize_errors:
                errors.append('    * {}: {}'.format(err.code, err.message))
                if util.is_not_empty(err.values):
                    for de in err.values:
                        de.append('      * {}: {}'.format(de.name, de.value))
        else:
            errors = ['  * no resize errors']
        entry = [
            '* pool id: {}'.format(pool.id),
            '  * vm size: {}'.format(pool.vm_size),
            '  * creation time: {}'.format(pool.creation_time),
            '  * state: {} @ {}'.format(
                pool.state.value, pool.state_transition_time),
            '  * allocation state: {} @ {}'.format(
                pool.allocation_state.value,
                pool.allocation_state_transition_time),
        ]
        entry.extend(errors)
        if util.is_not_empty(pool.metadata):
            entry.append('  * metadata:')
            for md in pool.metadata:
                entry.append('    * {}: {}'.format(md.name, md.value))
        entry.extend([
            '  * vm count:',
            '    * dedicated:',
            '      * current: {}'.format(pool.current_dedicated_nodes),
            '      * target: {}'.format(pool.target_dedicated_nodes),
            '    * low priority:',
            '      * current: {}'.format(pool.current_low_priority_nodes),
            '      * target: {}'.format(pool.target_low_priority_nodes),
            '  * max tasks per node: {}'.format(pool.max_tasks_per_node),
            '  * enable inter node communication: {}'.format(
                pool.enable_inter_node_communication),
            '  * autoscale enabled: {}'.format(pool.enable_auto_scale),
            '  * autoscale evaluation interval: {}'.format(
                pool.auto_scale_evaluation_interval),
            '  * scheduling policy: {}'.format(
                pool.task_scheduling_policy.node_fill_type.value),
            '  * virtual network: {}'.format(
                pool.network_configuration.subnet_id
                if pool.network_configuration is not None else 'n/a'),
            '  * node agent: {}'.format(
                pool.virtual_machine_configuration.node_agent_sku_id),
        ])
        log.extend(entry)
        i += 1
    if i == 0:
        logger.error('no pools found')
    else:
        logger.info(os.linesep.join(log))


def _check_metadata_mismatch(mdtype, metadata, req_ge=None):
    # type: (str, List[batchmodels.MetadataItem], str) -> None
    """Check for metadata mismatch
    :param str mdtype: metadata type (e.g., pool, job)
    :param list metadata: list of metadata items
    :param str req_ge: required greater than or equal to
    """
    if util.is_none_or_empty(metadata):
        if req_ge is not None:
            raise RuntimeError(
                ('{} version metadata not present but version {} is '
                 'required').format(mdtype, req_ge))
        else:
            logger.warning('{} version metadata not present'.format(mdtype))
    else:
        for md in metadata:
            if md.name == settings.get_metadata_version_name():
                if md.value != __version__:
                    logger.warning(
                        '{} version metadata mismatch: {}={} cli={}'.format(
                            mdtype, mdtype, md.value, __version__))
                if req_ge is not None:
                    # split version into tuple
                    mdt = md.value.split('.')
                    mdt = tuple((int(mdt[0]), int(mdt[1]), mdt[2]))
                    rv = req_ge.split('.')
                    rv = tuple((int(rv[0]), int(rv[1]), rv[2]))
                    if mdt < rv:
                        raise RuntimeError(
                            ('{} version of {} does not meet the version '
                             'requirement of at least {}').format(
                                 mdtype, md.value, req_ge))
                break


def resize_pool(batch_client, blob_client, config, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient,
    #        azure.storage.blob.BlockBlobClient, dict, bool) -> list
    """Resize a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param bool wait: wait for operation to complete
    :rtype: list or None
    :return: list of nodes if wait or None
    """
    pool = settings.pool_settings(config)
    _pool = batch_client.pool.get(pool.id)
    # check pool metadata version
    _check_metadata_mismatch('pool', _pool.metadata)
    logger.info(
        ('Resizing pool {} to {} compute nodes [current_dedicated_nodes={} '
         'current_low_priority_nodes={}]').format(
             pool.id, pool.vm_count, _pool.current_dedicated_nodes,
             _pool.current_low_priority_nodes))
    total_vm_count = (
        _pool.current_dedicated_nodes + _pool.current_low_priority_nodes
    )
    batch_client.pool.resize(
        pool_id=pool.id,
        pool_resize_parameter=batchmodels.PoolResizeParameter(
            target_dedicated_nodes=pool.vm_count.dedicated,
            target_low_priority_nodes=pool.vm_count.low_priority,
            resize_timeout=pool.resize_timeout,
        )
    )
    if wait:
        # wait until at least one node has entered leaving_pool state first
        # if this pool is being resized down
        diff_vm_count = (
            pool.vm_count.dedicated + pool.vm_count.low_priority -
            total_vm_count
        )
        if diff_vm_count < 0:
            logger.debug(
                'waiting for resize to start on pool: {}'.format(pool.id))
            while True:
                nodes = list(batch_client.compute_node.list(pool.id))
                if (len(nodes) != total_vm_count or any(
                        node.state == batchmodels.ComputeNodeState.leaving_pool
                        for node in nodes)):
                    break
                else:
                    time.sleep(1)
        return wait_for_pool_ready(
            batch_client, blob_client, config, pool.id,
            addl_end_states=[batchmodels.ComputeNodeState.running])


def pool_exists(batch_client, pool_id):
    # type: (azure.batch.batch_service_client.BatchServiceClient, str) -> bool
    """Check if pool exists
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str pool_id: pool id
    :rtype: bool
    :return: if pool exists
    """
    return batch_client.pool.exists(pool_id)


def del_pool(batch_client, config, pool_id=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str) -> bool
    """Delete a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str pool_id: pool id
    :rtype: bool
    :return: if pool was deleted
    """
    if util.is_none_or_empty(pool_id):
        pool_id = settings.pool_id(config)
    if not util.confirm_action(
            config, 'delete {} pool'.format(pool_id)):
        return False
    logger.info('Deleting pool: {}'.format(pool_id))
    batch_client.pool.delete(pool_id)
    return True


def pool_stats(batch_client, config, pool_id=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str) -> None
    """Get pool stats
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str pool_id: pool id
    """
    if util.is_none_or_empty(pool_id):
        pool_id = settings.pool_id(config)
    try:
        pool = batch_client.pool.get(
            pool_id=pool_id,
            pool_get_options=batchmodels.PoolGetOptions(expand='stats'),
        )
    except batchmodels.BatchErrorException as ex:
        if 'The specified pool does not exist' in ex.message.value:
            logger.error('pool {} does not exist'.format(pool_id))
            return
    if pool.stats is not None and pool.stats.usage_stats is not None:
        usage_stats = '{}    * Total core hours: {} (last updated: {})'.format(
            os.linesep,
            pool.stats.usage_stats.dedicated_core_time,
            pool.stats.usage_stats.last_update_time,
        )
    else:
        usage_stats = ''
    nodes = list(batch_client.compute_node.list(pool_id))
    nsc = []
    runnable_nodes = 0
    for key, value in _node_state_counts(nodes)._asdict().items():
        if key == 'running' or key == 'idle':
            runnable_nodes += value
        nsc.append('  * {}: {}'.format(key, value))
    node_up_times = []
    node_alloc_times = []
    node_start_times = []
    tasks_run = []
    tasks_running = []
    now = datetime.datetime.now(dateutil.tz.tzutc())
    for node in nodes:
        if node.last_boot_time is not None:
            node_up_times.append((now - node.last_boot_time).total_seconds())
        if (node.start_task_info is not None and
                node.start_task_info.end_time is not None):
            node_alloc_times.append(
                (node.start_task_info.end_time -
                 node.allocation_time).total_seconds()
            )
            node_start_times.append(
                (node.start_task_info.end_time -
                 node.last_boot_time).total_seconds()
            )
        if node.total_tasks_run is not None:
            tasks_run.append(node.total_tasks_run)
        if node.running_tasks_count is not None:
            tasks_running.append(node.running_tasks_count)
    total_running_tasks = sum(tasks_running)
    runnable_task_slots = runnable_nodes * pool.max_tasks_per_node
    total_task_slots = (
        pool.current_dedicated_nodes + pool.current_low_priority_nodes
    ) * pool.max_tasks_per_node
    busy_task_slots_fraction = (
        0 if runnable_task_slots == 0 else
        total_running_tasks / runnable_task_slots
    )
    version = 'N/A'
    if util.is_not_empty(pool.metadata):
        for md in pool.metadata:
            if md.name == settings.get_metadata_version_name():
                version = md.value
                break
    log = [
        '* Batch Shipyard version: {}'.format(version),
        '* Total nodes: {}'.format(
            pool.current_dedicated_nodes + pool.current_low_priority_nodes
        ),
        '  * VM size: {}'.format(pool.vm_size),
        '  * Dedicated nodes: {0} ({1:.1f}% of target){2}'.format(
            pool.current_dedicated_nodes,
            100 * (
                1 if pool.target_dedicated_nodes == 0 else
                pool.current_dedicated_nodes / pool.target_dedicated_nodes),
            usage_stats,
        ),
        '  * Low Priority nodes: {0} ({1:.1f}% of target)'.format(
            pool.current_low_priority_nodes,
            100 * (
                1 if pool.target_low_priority_nodes == 0 else
                pool.current_low_priority_nodes /
                pool.target_low_priority_nodes)
        ),
        '* Node states:',
        os.linesep.join(nsc),
    ]
    if len(node_up_times) > 0:
        log.extend([
            '* Node uptime:',
            '  * Mean: {}'.format(
                datetime.timedelta(
                    seconds=(sum(node_up_times) / len(node_up_times)))
            ),
            '  * Min: {}'.format(
                datetime.timedelta(seconds=min(node_up_times))
            ),
            '  * Max: {}'.format(
                datetime.timedelta(seconds=max(node_up_times))
            ),
        ])
    if len(node_alloc_times) > 0:
        log.extend([
            '* Time taken for node creation to ready:',
            '  * Mean: {}'.format(
                datetime.timedelta(
                    seconds=(sum(node_alloc_times) / len(node_alloc_times)))
            ),
            '  * Min: {}'.format(
                datetime.timedelta(seconds=min(node_alloc_times))
            ),
            '  * Max: {}'.format(
                datetime.timedelta(seconds=max(node_alloc_times))
            ),
        ])
    if len(node_start_times) > 0:
        log.extend([
            '* Time taken for last boot startup (includes prep):',
            '  * Mean: {}'.format(
                datetime.timedelta(
                    seconds=(sum(node_start_times) / len(node_start_times)))
            ),
            '  * Min: {}'.format(
                datetime.timedelta(seconds=min(node_start_times))
            ),
            '  * Max: {}'.format(
                datetime.timedelta(seconds=max(node_start_times))
            ),
        ])
    if len(tasks_running) > 0:
        log.extend([
            '* Running tasks:',
            '  * Sum: {}'.format(total_running_tasks),
            '  * Mean: {}'.format(total_running_tasks / len(tasks_running)),
            '  * Min: {}'.format(min(tasks_running)),
            '  * Max: {}'.format(max(tasks_running)),
        ])
    if len(tasks_run) > 0:
        log.extend([
            '* Total tasks run:',
            '  * Sum: {}'.format(sum(tasks_run)),
            '  * Mean: {}'.format(sum(tasks_run) / len(tasks_run)),
            '  * Min: {}'.format(min(tasks_run)),
            '  * Max: {}'.format(max(tasks_run)),
        ])
    log.extend([
        '* Task scheduling slots:',
        '  * Busy: {0} ({1:.2f}% of runnable)'.format(
            total_running_tasks, 100 * busy_task_slots_fraction
        ),
        '  * Available: {0} ({1:.2f}% of runnable)'.format(
            runnable_task_slots - total_running_tasks,
            100 * (1 - busy_task_slots_fraction)
        ),
        '  * Runnable: {0} ({1:.2f}% of total)'.format(
            runnable_task_slots,
            100 * (
                (runnable_task_slots / total_task_slots)
                if total_task_slots > 0 else 0
            ),
        ),
        '  * Total: {}'.format(total_task_slots),
    ])
    logger.info('statistics summary for pool {}{}{}'.format(
        pool_id, os.linesep, os.linesep.join(log)))


def pool_autoscale_disable(batch_client, config):
    # type: (batch.BatchServiceClient, dict) -> None
    """Enable autoscale formula
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool_id = settings.pool_id(config)
    batch_client.pool.disable_auto_scale(pool_id=pool_id)
    logger.info('autoscale disabled for pool {}'.format(pool_id))


def pool_autoscale_enable(batch_client, config):
    # type: (batch.BatchServiceClient, dict) -> None
    """Enable autoscale formula
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool = settings.pool_settings(config)
    _pool = batch_client.pool.get(pool.id)
    # check pool metadata
    _check_metadata_mismatch('pool', _pool.metadata, req_ge='2.9.0')
    asformula = None
    asei = None
    if not _pool.enable_auto_scale:
        # check if an autoscale formula exists in config
        if not settings.is_pool_autoscale_enabled(config, pas=pool.autoscale):
            if not util.confirm_action(
                    config,
                    ('enable dummy formula for pool {} as no autoscale '
                     'formula exists').format(pool.id)):
                logger.error('not enabling autoscale for pool {}'.format(
                    pool.id))
                return
            # set dummy formula
            asformula = (
                '$TargetDedicatedNodes = {}; '
                '$TargetLowPriorityNodes = {};'
            ).format(
                _pool.target_dedicated_nodes, _pool.target_low_priority_nodes)
    if asformula is None:
        asformula = autoscale.get_formula(pool)
        asei = pool.autoscale.evaluation_interval
    # enable autoscale
    batch_client.pool.enable_auto_scale(
        pool_id=pool.id,
        auto_scale_formula=asformula,
        auto_scale_evaluation_interval=asei,
    )
    logger.info('autoscale enabled/updated for pool {}'.format(pool.id))


def _output_autoscale_result(result):
    # type: (batchmodels.AutoScaleRun) -> None
    """Output autoscale evalute or last exec results
    :param batchmodels.AutoScaleRun result: result
    """
    if result is None:
        logger.error(
            'autoscale result is invalid, ensure autoscale is enabled')
        return
    if result.error is not None:
        logger.error('autoscale evaluate error: code={} message={}'.format(
            result.error.code, result.error.message))
    else:
        logger.info('autoscale result: {}'.format(result.results))
        logger.info('last autoscale evaluation: {}'.format(result.timestamp))


def pool_autoscale_evaluate(batch_client, config):
    # type: (batch.BatchServiceClient, dict) -> None
    """Evaluate autoscale formula
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool = settings.pool_settings(config)
    if not settings.is_pool_autoscale_enabled(config, pas=pool.autoscale):
        logger.error(
            ('cannot evaluate autoscale for pool {}, not enabled or '
             'no formula').format(pool.id))
        return
    if settings.raw(config):
        raw = util.print_raw_output(
            batch_client.pool.evaluate_auto_scale, pool.id, return_json=True,
            auto_scale_formula=autoscale.get_formula(pool))
        util.print_raw_json(raw)
        return
    result = batch_client.pool.evaluate_auto_scale(
        pool_id=pool.id,
        auto_scale_formula=autoscale.get_formula(pool),
    )
    _output_autoscale_result(result)


def pool_autoscale_lastexec(batch_client, config):
    # type: (batch.BatchServiceClient, dict) -> None
    """Get last execution of the autoscale formula
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool_id = settings.pool_id(config)
    if settings.raw(config):
        raw = util.print_raw_output(
            batch_client.pool.get, pool_id, return_json=True)
        if 'autoScaleRun' in raw:
            util.print_raw_json(raw['autoScaleRun'])
        return
    pool = batch_client.pool.get(pool_id)
    if not pool.enable_auto_scale:
        logger.error(
            ('last execution information not available for autoscale '
             'disabled pool {}').format(pool_id))
        return
    _output_autoscale_result(pool.auto_scale_run)


def reboot_nodes(batch_client, config, all_start_task_failed, node_ids):
    # type: (batch.BatchServiceClient, dict, bool, list) -> None
    """Reboot nodes in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool all_start_task_failed: reboot all start task failed nodes
    :param list node_ids: list of node ids to reboot
    """
    pool_id = settings.pool_id(config)
    nodes_to_reboot = []
    if all_start_task_failed:
        nodes = list(
            batch_client.compute_node.list(
                pool_id=pool_id,
                compute_node_list_options=batchmodels.ComputeNodeListOptions(
                    filter='state eq \'starttaskfailed\'',
                ),
            ))
        for node in nodes:
            if not util.confirm_action(
                    config, 'reboot node {} from {} pool'.format(
                        node.id, pool_id)):
                continue
            nodes_to_reboot.append(node.id)
    else:
        if util.is_none_or_empty(node_ids):
            raise ValueError('node ids to reboot is empty or invalid')
        for node_id in node_ids:
            if not util.confirm_action(
                    config, 'reboot node {} from {} pool'.format(
                        node_id, pool_id)):
                continue
            nodes_to_reboot.append(node_id)
    if util.is_none_or_empty(nodes_to_reboot):
        return
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_max_workers(nodes_to_reboot)) as executor:
        for node_id in nodes_to_reboot:
            executor.submit(
                _reboot_node, batch_client, pool_id, node_id, False)


def del_nodes(
        batch_client, config, all_start_task_failed, all_starting,
        all_unusable, node_ids, suppress_confirm=False):
    # type: (batch.BatchServiceClient, dict, bool, bool, bool, list,
    #        bool) -> None
    """Delete nodes from a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool all_start_task_failed: delete all start task failed nodes
    :param bool all_starting: delete all starting nodes
    :param bool all_unusable: delete all unusable nodes
    :param list node_ids: list of node ids to delete
    :param bool suppress_confirm: suppress confirm ask
    """
    if util.is_none_or_empty(node_ids):
        node_ids = []
    pool_id = settings.pool_id(config)
    if all_start_task_failed or all_starting or all_unusable:
        filters = []
        if all_start_task_failed:
            filters.append('(state eq \'starttaskfailed\')')
        elif all_starting:
            filters.append('(state eq \'starting\')')
        elif all_unusable:
            filters.append('(state eq \'unusable\')')
        nodes = list(
            batch_client.compute_node.list(
                pool_id=pool_id,
                compute_node_list_options=batchmodels.ComputeNodeListOptions(
                    filter=' or '.join(filters),
                ),
            ))
        for node in nodes:
            if suppress_confirm or util.confirm_action(
                    config, 'delete node {} from {} pool'.format(
                        node.id, pool_id)):
                node_ids.append(node.id)
    else:
        if util.is_none_or_empty(node_ids):
            raise ValueError('node ids to delete is empty or invalid')
        if not suppress_confirm and not util.confirm_action(
                config, 'delete {} nodes from {} pool'.format(
                    len(node_ids), pool_id)):
            return
    if util.is_none_or_empty(node_ids):
        logger.warning('no nodes to delete from pool: {}'.format(pool_id))
        return
    logger.info('Deleting nodes {} from pool {}'.format(node_ids, pool_id))
    batch_client.pool.remove_nodes(
        pool_id=pool_id,
        node_remove_parameter=batchmodels.NodeRemoveParameter(
            node_list=node_ids,
        )
    )


def check_pool_for_job_migration(
        batch_client, config, jobid=None, jobscheduleid=None, poolid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str, str) -> None
    """Check pool for job or job schedule migration eligibility
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to migrate
    :param str jobscheduleid: job schedule id to migrate
    :param str poolid: pool id to update to
    """
    if poolid is None:
        poolid = settings.pool_id(config)
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid or jobscheduleid}]
    for _job in jobs:
        recurrence = (
            True if jobscheduleid is not None else
            settings.job_recurrence(_job)
        )
        if recurrence is not None:
            text = 'job schedule'
        else:
            text = 'job'
        job_id = settings.job_id(_job)
        if recurrence is not None:
            job = batch_client.job_schedule.get(job_schedule_id=job_id)
            if (job.state == batchmodels.JobScheduleState.completed or
                    job.state == batchmodels.JobScheduleState.deleting or
                    job.state == batchmodels.JobScheduleState.terminating):
                raise RuntimeError(
                    'cannot migrate {} {} in state {}'.format(
                        text, job_id, job.state))
            poolinfo = job.job_specification.pool_info
        else:
            job = batch_client.job.get(job_id=job_id)
            if (job.state == batchmodels.JobState.completed or
                    job.state == batchmodels.JobState.deleting or
                    job.state == batchmodels.JobState.terminating):
                raise RuntimeError(
                    'cannot migrate {} {} in state {}'.format(
                        text, job_id, job.state))
            poolinfo = job.pool_info
        if poolinfo.auto_pool_specification is not None:
            raise RuntimeError(
                'cannot migrate {} {} with an autopool specification'.format(
                    text, job_id))
        if poolinfo.pool_id == poolid:
            raise RuntimeError(
                'cannot migrate {} {} to the same pool {}'.format(
                    text, job_id, poolid))


def update_job_with_pool(
        batch_client, config, jobid=None, jobscheduleid=None, poolid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str, str) -> None
    """Update job with different pool id
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to update
    :param str jobscheduleid: job schedule id to update
    :param str poolid: pool id to update to
    """
    if poolid is None:
        poolid = settings.pool_id(config)
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid or jobscheduleid}]
    for _job in jobs:
        recurrence = (
            True if jobscheduleid is not None else
            settings.job_recurrence(_job)
        )
        if recurrence is not None:
            text = 'job schedule'
        else:
            text = 'job'
        job_id = settings.job_id(_job)
        if recurrence is not None:
            # get existing job spec and patch over pool info
            js = batch_client.job_schedule.get(
                job_schedule_id=job_id).job_specification
            js.pool_info = batchmodels.PoolInformation(pool_id=poolid)
            # fix constraints
            if (js.constraints is not None and
                    js.constraints.max_wall_clock_time.days > 9e5):
                js.constraints.max_wall_clock_time = None
            js.job_manager_task.constraints = None
            js.job_preparation_task.constraints = None
            if js.job_release_task is not None:
                js.job_release_task.max_wall_clock_time = None
                js.job_release_task.retention_time = None
            batch_client.job_schedule.patch(
                job_schedule_id=job_id,
                job_schedule_patch_parameter=batchmodels.
                JobSchedulePatchParameter(
                    job_specification=js,
                )
            )
        else:
            batch_client.job.patch(
                job_id=job_id,
                job_patch_parameter=batchmodels.JobPatchParameter(
                    pool_info=batchmodels.PoolInformation(
                        pool_id=poolid)
                )
            )
        logger.info('updated {} {} to target pool {}'.format(
            text, job_id, poolid))


def job_stats(batch_client, config, jobid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str) -> None
    """Job stats
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to query
    """
    if jobid is not None:
        try:
            job = batch_client.job.get(
                job_id=jobid,
                job_get_options=batchmodels.JobGetOptions(expand='stats'),
            )
        except batchmodels.BatchErrorException as ex:
            if 'The specified job does not exist' in ex.message.value:
                raise RuntimeError('job {} does not exist'.format(jobid))
        jobs = [job]
    else:
        jobs = list(batch_client.job.list(
            job_list_options=batchmodels.JobListOptions(expand='stats')))
    job_count = 0
    job_times = []
    task_times = []
    task_wall_times = []
    task_counts = batchmodels.TaskCounts(
        active=0, running=0, completed=0, succeeded=0, failed=0)
    total_tasks = 0
    for job in jobs:
        job_count += 1
        # get task counts
        tc = batch_client.job.get_task_counts(job_id=job.id)
        task_counts.active += tc.active
        task_counts.running += tc.running
        task_counts.completed += tc.completed
        task_counts.succeeded += tc.succeeded
        task_counts.failed += tc.failed
        total_tasks += tc.active + tc.running + tc.completed
        if job.execution_info.end_time is not None:
            job_times.append(
                (job.execution_info.end_time -
                 job.execution_info.start_time).total_seconds())
        # get task-level execution info
        tasks = batch_client.task.list(
            job_id=job.id,
            task_list_options=batchmodels.TaskListOptions(
                filter='(state eq \'running\') or (state eq \'completed\')',
                select='id,state,stats,executionInfo',
            ))
        for task in tasks:
            if task.stats is not None:
                task_wall_times.append(
                    task.stats.wall_clock_time.total_seconds())
            if (task.execution_info is not None and
                    task.execution_info.end_time is not None):
                task_times.append(
                    (task.execution_info.end_time -
                     task.execution_info.start_time).total_seconds())
    log = [
        '* Total jobs: {}'.format(job_count),
        '* Total tasks: {}'.format(total_tasks),
        '  * Active: {0} ({1:.2f}% of total)'.format(
            task_counts.active,
            100 * task_counts.active / total_tasks if total_tasks > 0 else 0
        ),
        '  * Running: {0} ({1:.2f}% of total)'.format(
            task_counts.running,
            100 * task_counts.running / total_tasks if total_tasks > 0 else 0
        ),
        '  * Completed: {0} ({1:.2f}% of total)'.format(
            task_counts.completed,
            100 * task_counts.completed / total_tasks if total_tasks > 0 else 0
        ),
        '    * Succeeded: {0} ({1:.2f}% of completed)'.format(
            task_counts.succeeded,
            100 * task_counts.succeeded / task_counts.completed
            if task_counts.completed > 0 else 0
        ),
        '    * Failed: {0} ({1:.2f}% of completed)'.format(
            task_counts.failed,
            100 * task_counts.failed / task_counts.completed
            if task_counts.completed > 0 else 0
        ),
    ]
    if len(job_times) > 0:
        log.extend([
            '* Job creation to completion time:',
            '  * Mean: {}'.format(
                datetime.timedelta(seconds=(sum(job_times) / len(job_times)))
            ),
            '  * Min: {}'.format(
                datetime.timedelta(seconds=min(job_times))
            ),
            '  * Max: {}'.format(
                datetime.timedelta(seconds=max(job_times))
            ),
        ])
    if len(task_times) > 0:
        log.extend([
            '* Task end-to-end time (completed):',
            '  * Mean: {}'.format(
                datetime.timedelta(seconds=(sum(task_times) / len(task_times)))
            ),
            '  * Min: {}'.format(
                datetime.timedelta(seconds=min(task_times))
            ),
            '  * Max: {}'.format(
                datetime.timedelta(seconds=max(task_times))
            ),
        ])
    if len(task_wall_times) > 0:
        log.extend([
            '* Task command walltime (running and completed):',
            '  * Mean: {}'.format(
                datetime.timedelta(
                    seconds=(sum(task_wall_times) / len(task_wall_times)))
            ),
            '  * Min: {}'.format(
                datetime.timedelta(seconds=min(task_wall_times))
            ),
            '  * Max: {}'.format(
                datetime.timedelta(seconds=max(task_wall_times))
            ),
        ])
    logger.info('statistics summary for {}{}{}'.format(
        'job {}'.format(jobid) if jobid is not None else 'all jobs',
        os.linesep, os.linesep.join(log)))


def disable_jobs(
        batch_client, config, disable_tasks_action, jobid=None,
        jobscheduleid=None, disabling_state_ok=False, term_tasks=False,
        suppress_confirm=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str, bool, bool) -> None
    """Disable jobs or job schedules
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str disable_tasks_action: disable tasks action
    :param str jobid: job id to disable
    :param str jobscheduleid: job schedule id to disable
    :param bool disabling_state_ok: disabling state is ok to proceed
    :param bool term_tasks: terminate tasks after disable
    :param bool suppress_confirm: suppress confirmation
    """
    if jobid is None and jobscheduleid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid or jobscheduleid}]
    for job in jobs:
        recurrence = (
            True if jobscheduleid is not None else settings.job_recurrence(job)
        )
        if recurrence is not None:
            text = 'job schedule'
        else:
            text = 'job'
        job_id = settings.job_id(job)
        if not suppress_confirm and not util.confirm_action(
                config, 'disable {} {}'.format(text, job_id)):
            continue
        logger.info('disabling {}: {}'.format(text, job_id))
        try:
            if recurrence is not None:
                batch_client.job_schedule.disable(job_schedule_id=job_id)
            else:
                batch_client.job.disable(
                    job_id=job_id,
                    disable_tasks=batchmodels.DisableJobOption(
                        disable_tasks_action),
                )
        except batchmodels.BatchErrorException as ex:
            if 'completed state.' in ex.message.value:
                logger.error('{} is already completed'.format(job_id))
            elif 'does not exist' in ex.message.value:
                logger.error('{} {} does not exist'.format(text, job_id))
            else:
                raise
        else:
            # wait for job to enter disabled/completed/deleting state
            while True:
                if recurrence is not None:
                    _js = batch_client.job_schedule.get(
                        job_schedule_id=job_id,
                        job_schedule_get_options=batchmodels.
                        JobScheduleGetOptions(select='id,state')
                    )
                    if (_js.state == batchmodels.JobScheduleState.disabled or
                            _js.state ==
                            batchmodels.JobScheduleState.completed or
                            _js.state ==
                            batchmodels.JobScheduleState.deleting):
                        break
                else:
                    _job = batch_client.job.get(
                        job_id=job_id,
                        job_get_options=batchmodels.JobGetOptions(
                            select='id,state')
                    )
                    if ((disabling_state_ok and
                         _job.state == batchmodels.JobState.disabling) or
                            _job.state == batchmodels.JobState.disabled or
                            _job.state == batchmodels.JobState.completed or
                            _job.state == batchmodels.JobState.deleting):
                        break
                time.sleep(1)
            logger.info('{} {} disabled'.format(text, job_id))
            if term_tasks:
                terminate_tasks(
                    batch_client, config, jobid=job_id, wait=True)


def enable_jobs(batch_client, config, jobid=None, jobscheduleid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str) -> None
    """Enable jobs or job schedules
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to enable
    :param str jobscheduleid: job schedule id to enable
    """
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid or jobscheduleid}]
    for job in jobs:
        recurrence = (
            True if jobscheduleid is not None else settings.job_recurrence(job)
        )
        if recurrence is not None:
            text = 'job schedule'
        else:
            text = 'job'
        job_id = settings.job_id(job)
        try:
            if recurrence is not None:
                batch_client.job_schedule.enable(job_schedule_id=job_id)
            else:
                batch_client.job.enable(job_id=job_id)
        except batchmodels.BatchErrorException as ex:
            if 'completed state.' in ex.message.value:
                pass
        else:
            logger.info('{} {} enabled'.format(text, job_id))


def _wait_for_task_deletion(batch_client, job_id, task):
    # type: (azure.batch.batch_service_client.BatchServiceClient,
    #        str, str) -> None
    """Wait for task deletion
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job id of task to terminate
    :param str task: task id to delete
    """
    try:
        logger.debug(
            'waiting for task {} in job {} to delete'.format(task, job_id))
        while True:
            batch_client.task.get(
                job_id, task,
                task_get_options=batchmodels.TaskGetOptions(select='id')
            )
            time.sleep(1)
    except batchmodels.BatchErrorException as ex:
        if 'The specified task does not exist' in ex.message.value:
            logger.info('task {} in job {} does not exist'.format(
                task, job_id))
        else:
            raise


def del_tasks(batch_client, config, jobid=None, taskid=None, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str, bool) -> None
    """Delete tasks
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id of task to terminate
    :param str taskid: task id to terminate
    :param bool wait: wait for task to terminate
    """
    # first terminate tasks if non-native, force wait for completion
    if not settings.is_native_docker_pool(config):
        terminate_tasks(
            batch_client, config, jobid=jobid, taskid=taskid, wait=True)
    # proceed with deletion
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid}]
    nocheck = {}
    for job in jobs:
        job_id = settings.job_id(job)
        nocheck[job_id] = set()
        if taskid is None:
            tasks = [
                x.id for x in batch_client.task.list(
                    job_id,
                    task_list_options=batchmodels.TaskListOptions(select='id')
                )
            ]
        else:
            tasks = [taskid]
        tasks_to_delete = []
        for task in tasks:
            if not util.confirm_action(
                    config, 'delete {} task in job {}'.format(
                        task, job_id)):
                nocheck[job_id].add(task)
                continue
            tasks_to_delete.append(task)
        if len(tasks_to_delete) == 0:
            continue
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=_max_workers(tasks_to_delete)) as executor:
            for task in tasks_to_delete:
                logger.info('Deleting task: {}'.format(task))
                executor.submit(batch_client.task.delete, job_id, task)
    if wait:
        for job in jobs:
            job_id = settings.job_id(job)
            if taskid is None:
                tasks = [
                    x.id for x in batch_client.task.list(
                        job_id,
                        task_list_options=batchmodels.TaskListOptions(
                            select='id')
                    )
                ]
            else:
                tasks = [taskid]
            if len(tasks) == 0:
                continue
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=_max_workers(tasks)) as executor:
                for task in tasks:
                    try:
                        if task in nocheck[job_id]:
                            continue
                    except KeyError:
                        pass
                executor.submit(
                    _wait_for_task_deletion, batch_client, job_id, task)


def clean_mi_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Clean up multi-instance jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    is_windows = settings.is_windows_pool(config)
    for job in settings.job_specifications(config):
        job_id = settings.job_id(job)
        if not util.confirm_action(
                config, 'cleanup {} job'.format(job_id)):
            continue
        cleanup_job_id = 'shipyardcleanup-' + job_id
        cleanup_job = batchmodels.JobAddParameter(
            id=cleanup_job_id,
            pool_info=batchmodels.PoolInformation(
                pool_id=settings.pool_id(config)),
        )
        try:
            batch_client.job.add(cleanup_job)
            logger.info('Added cleanup job: {}'.format(cleanup_job.id))
        except batchmodels.BatchErrorException as ex:
            if 'The specified job already exists' not in ex.message.value:
                raise
        # get all cleanup tasks
        cleanup_tasks = [
            x.id for x in batch_client.task.list(
                cleanup_job_id,
                task_list_options=batchmodels.TaskListOptions(select='id')
            )
        ]
        # list all tasks in job
        tasks = batch_client.task.list(job_id)
        for task in tasks:
            if (task.id in cleanup_tasks or
                    task.multi_instance_settings is None):
                continue
            # check if task is complete
            if task.state == batchmodels.TaskState.completed:
                name = task.multi_instance_settings.coordination_command_line.\
                    split('--name')[-1].split()[0]
                # create cleanup task
                batchtask = batchmodels.TaskAddParameter(
                    id=task.id,
                    multi_instance_settings=batchmodels.MultiInstanceSettings(
                        number_of_instances=task.
                        multi_instance_settings.number_of_instances,
                        coordination_command_line=util.
                        wrap_commands_in_shell([
                            'docker stop {}'.format(name),
                            'docker rm -v {}'.format(name),
                            'exit 0',
                        ], windows=is_windows, wait=False),
                    ),
                    command_line='/bin/sh -c "exit 0"',
                    user_identity=_RUN_ELEVATED,
                )
                batch_client.task.add(job_id=cleanup_job_id, task=batchtask)
                logger.debug(
                    ('Waiting for docker multi-instance clean up task {} '
                     'for job {} to complete').format(batchtask.id, job_id))
                # wait for cleanup task to complete before adding another
                while True:
                    batchtask = batch_client.task.get(
                        cleanup_job_id, batchtask.id,
                        task_get_options=batchmodels.TaskGetOptions(
                            select='id,state')
                    )
                    if batchtask.state == batchmodels.TaskState.completed:
                        break
                    time.sleep(1)
                logger.info(
                    ('Docker multi-instance clean up task {} for job {} '
                     'completed').format(batchtask.id, job_id))


def del_clean_mi_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Delete clean up multi-instance jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    for job in settings.job_specifications(config):
        job_id = settings.job_id(job)
        cleanup_job_id = 'shipyardcleanup-' + job_id
        logger.info('deleting job: {}'.format(cleanup_job_id))
        try:
            batch_client.job.delete(cleanup_job_id)
        except batchmodels.BatchErrorException:
            pass


def delete_or_terminate_jobs(
        batch_client, config, delete, jobid=None, jobscheduleid=None,
        termtasks=False, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool, str, str, bool, bool) -> None
    """Delete or terminate jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool delete: delete instead of terminate
    :param str jobid: job id to terminate
    :param str jobscheduleid: job schedule id to terminate
    :param bool termtasks: terminate tasks manually prior
    :param bool wait: wait for job to terminate
    """
    if delete:
        action = 'delete'
        action_present = 'deleting'
        action_past = 'deleted'
    else:
        action = 'terminate'
        action_present = 'terminating'
        action_past = 'terminated'
    if jobid is None and jobscheduleid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid or jobscheduleid}]
    if termtasks:
        terminate_tasks(batch_client, config, jobid=jobid, wait=True)
    nocheck = set()
    for job in jobs:
        recurrence = (
            True if jobscheduleid is not None else settings.job_recurrence(job)
        )
        if recurrence is not None:
            text = 'job schedule'
        else:
            text = 'job'
        job_id = settings.job_id(job)
        if not util.confirm_action(
                config, '{} {} {}'.format(action, text, job_id)):
            nocheck.add(job_id)
            continue
        logger.info('{} {}: {}'.format(action_present, text, job_id))
        try:
            if recurrence is not None:
                if delete:
                    batch_client.job_schedule.delete(job_id)
                else:
                    batch_client.job_schedule.terminate(job_id)
            else:
                if delete:
                    batch_client.job.delete(job_id)
                else:
                    batch_client.job.terminate(job_id)
        except batchmodels.BatchErrorException as ex:
            if delete and 'does not exist' in ex.message.value:
                logger.error('{} {} does not exist'.format(job_id, text))
                nocheck.add(job_id)
                continue
            elif 'completed state.' in ex.message.value:
                logger.debug('{} {} already completed'.format(text, job_id))
            else:
                raise
    if wait:
        for job in jobs:
            recurrence = (
                True if jobscheduleid is not None else
                settings.job_recurrence(job)
            )
            if recurrence is not None:
                text = 'job schedule'
            else:
                text = 'job'
            job_id = settings.job_id(job)
            if job_id in nocheck:
                continue
            try:
                logger.debug('waiting for {} {} to {}'.format(
                    text, job_id, action))
                while True:
                    if recurrence is not None:
                        _js = batch_client.job_schedule.get(job_id)
                        if _js.state == batchmodels.JobScheduleState.completed:
                            break
                    else:
                        _job = batch_client.job.get(job_id)
                        if _job.state == batchmodels.JobState.completed:
                            break
                    time.sleep(1)
                logger.info('{} {} {}'.format(text, job_id, action_past))
            except batchmodels.BatchErrorException as ex:
                if 'does not exist' in ex.message.value:
                    if delete:
                        logger.info('{} {} does not exist'.format(
                            text, job_id))
                else:
                    raise


def delete_or_terminate_all_jobs(
        batch_client, config, delete, termtasks=False, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool, bool, bool) -> None
    """Delete or terminate all jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool delete: delete instead of terminate
    :param bool termtasks: terminate tasks prior
    :param bool wait: wait for jobs to terminate
    """
    if delete:
        action = 'delete'
        action_present = 'deleting'
    else:
        action = 'terminate'
        action_present = 'terminating'
    check = set()
    logger.debug('Getting list of all jobs')
    jobs = batch_client.job.list()
    for job in jobs:
        if not util.confirm_action(
                config, '{} {} job'.format(action, job.id)):
            continue
        if termtasks:
            terminate_tasks(batch_client, config, jobid=job.id, wait=True)
        logger.info('{} job: {}'.format(action_present, job.id))
        try:
            if delete:
                batch_client.job.delete(job.id)
            else:
                batch_client.job.terminate(job.id)
        except batchmodels.BatchErrorException as ex:
            if delete and 'does not exist' in ex.message.value:
                logger.error('{} job does not exist'.format(job.id))
                continue
            elif 'already in a completed state' in ex.message.value:
                logger.debug('job {} already completed'.format(job.id))
            else:
                raise
        else:
            check.add(job.id)
    if wait:
        for job_id in check:
            try:
                logger.debug('waiting for job {} to {}'.format(job_id, action))
                while True:
                    _job = batch_client.job.get(job_id)
                    if _job.state == batchmodels.JobState.completed:
                        break
                    time.sleep(1)
            except batchmodels.BatchErrorException as ex:
                if 'The specified job does not exist' not in ex.message.value:
                    raise


def delete_or_terminate_all_job_schedules(
        batch_client, config, delete, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool, bool) -> None
    """Delete or terminate all job schedules
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool delete: delete instead of terminate
    :param bool wait: wait for jobs to terminate
    """
    if delete:
        action = 'delete'
        action_present = 'deleting'
    else:
        action = 'terminate'
        action_present = 'terminating'
    check = set()
    logger.debug('Getting list of all job schedules')
    jobschedules = batch_client.job_schedule.list()
    for js in jobschedules:
        if not util.confirm_action(
                config, '{} job schedule {}'.format(action, js.id)):
            continue
        logger.info('{} job schedule: {}'.format(action_present, js.id))
        try:
            if delete:
                batch_client.job_schedule.delete(js.id)
            else:
                batch_client.job_schedule.terminate(js.id)
        except batchmodels.BatchErrorException as ex:
            if delete and 'does not exist' in ex.message.value:
                logger.error('{} job schedule does not exist'.format(js.id))
                continue
            elif 'already in completed state' in ex.message.value:
                logger.debug('job schedule {} already completed'.format(
                    js.id))
            else:
                raise
        else:
            check.add(js.id)
    if wait:
        for js_id in check:
            try:
                logger.debug('waiting for job schedule {} to {}'.format(
                    js_id, action))
                while True:
                    _js = batch_client.job_schedule.get(js_id)
                    if _js.state == batchmodels.JobScheduleState.completed:
                        break
                    time.sleep(1)
            except batchmodels.BatchErrorException as ex:
                if ('The specified job schedule does not exist'
                        not in ex.message.value):
                    raise


def _send_docker_kill_signal(
        batch_client, config, username, ssh_private_key, pool_id, node_id,
        job_id, task_id, task_is_mi):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict, str,
    #        pathlib.Path, str, str, str, str, bool) -> None
    """Send docker kill signal via SSH
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str username: SSH username
    :param pathlib.Path ssh_private_key: SSH private key
    :param str pool_id: pool_id of node
    :param str node_id: node_id of node
    :param str job_id: job id of task id to kill
    :param str task_id: task id to kill
    :param bool task_is_mi: task is multi-instance
    """
    if util.is_none_or_empty(username):
        raise ValueError(
            'cannot terminate container task via SSH without an SSH username')
    if not ssh_private_key.exists():
        raise RuntimeError(
            ('cannot terminate container task via SSH with a '
             'non-existent SSH private key: {}').format(ssh_private_key))
    targets = [(pool_id, node_id)]
    task_name = None
    # if this task is multi-instance, get all subtasks
    if task_is_mi:
        subtasks = batch_client.task.list_subtasks(job_id, task_id)
        for subtask in subtasks.value:
            targets.append(
                (subtask.node_info.pool_id, subtask.node_info.node_id))
        # fetch container name
        try:
            jobs = settings.job_specifications(config)
            for job in jobs:
                if job_id == settings.job_id(job):
                    for task in settings.job_tasks(config, job):
                        task_name = settings.task_name(task)
                        break
                    break
        except KeyError:
            pass
    # TODO get task names for non-mi tasks?
    if task_name is None:
        task_name = '{}-{}'.format(job_id, task_id)
    # for each task node target, issue docker kill
    for target in targets:
        rls = batch_client.compute_node.get_remote_login_settings(
            target[0], target[1])
        command = [
            'sudo',
            ('/bin/bash -c "docker kill {tn}; docker ps -qa -f name={tn} | '
             'xargs --no-run-if-empty docker rm -v"').format(tn=task_name),
        ]
        rc = crypto.connect_or_exec_ssh_command(
            rls.remote_login_ip_address, rls.remote_login_port,
            ssh_private_key, username, sync=True, tty=True, command=command)
        if rc != 0:
            logger.error('docker kill failed with return code: {}'.format(rc))


def _terminate_task(
        batch_client, config, ssh_username, ssh_private_key, native, force,
        job_id, task, nocheck):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str, bool, bool, str, str, dict) -> None
    """Terminate a task, do not call directly
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str ssh_username: ssh username
    :param str ssh_private_key: ssh private key
    :param bool native: native mode
    :param bool force: force task docker kill signal regardless of state
    :param str jobid: job id of task to terminate
    :param str task: task id to terminate
    :param dict nocheck: nocheck dict
    """
    _task = batch_client.task.get(job_id, task)
    # if completed, skip
    if (_task.state == batchmodels.TaskState.completed and
            (not force or native)):
        logger.debug(
            'Skipping termination of completed task {} on '
            'job {}'.format(task, job_id))
        nocheck[job_id].add(task)
        return
    logger.info('Terminating task: {}'.format(task))
    # always terminate
    if _task.state != batchmodels.TaskState.completed:
        batch_client.task.terminate(job_id, task)
    # directly send docker kill signal if a running docker task
    if not native and (_task.state == batchmodels.TaskState.running or force):
        is_docker_task = False
        if 'shipyard_docker_exec_task_runner' in _task.command_line:
            is_docker_task = True
        else:
            for env_var in _task.environment_settings:
                if env_var.name == 'SHIPYARD_RUNTIME':
                    if env_var.value == 'docker':
                        is_docker_task = True
                    break
        if is_docker_task:
            if (_task.multi_instance_settings is not None and
                    _task.multi_instance_settings.number_of_instances > 1):
                task_is_mi = True
            else:
                task_is_mi = False
            _send_docker_kill_signal(
                batch_client, config, ssh_username,
                ssh_private_key, _task.node_info.pool_id,
                _task.node_info.node_id, job_id, task, task_is_mi)


def _wait_for_task_completion(batch_client, job_id, task):
    # type: (azure.batch.batch_service_client.BatchServiceClient,
    #        str, str) -> None
    """Wait for task completion
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job id of task to terminate
    :param str task: task id to terminate
    """
    try:
        logger.debug(
            'waiting for task {} in job {} to terminate'.format(task, job_id))
        while True:
            _task = batch_client.task.get(
                job_id, task,
                task_get_options=batchmodels.TaskGetOptions(select='state')
            )
            if _task.state == batchmodels.TaskState.completed:
                break
            time.sleep(1)
    except batchmodels.BatchErrorException as ex:
        if 'The specified task does not exist' not in ex.message.value:
            raise


def terminate_tasks(
        batch_client, config, jobid=None, taskid=None, wait=False,
        force=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str, bool, bool) -> None
    """Terminate tasks
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id of task to terminate
    :param str taskid: task id to terminate
    :param bool wait: wait for task to terminate
    :param bool force: force task docker kill signal regardless of state
    """
    native = settings.is_native_docker_pool(config)
    # get ssh login settings for non-native pools
    if not native:
        pool = settings.pool_settings(config)
        ssh_username = pool.ssh.username
        ssh_private_key = pool.ssh.ssh_private_key
        if ssh_private_key is None:
            ssh_private_key = pathlib.Path(
                pool.ssh.generated_file_export_path,
                crypto.get_ssh_key_prefix())
    else:
        ssh_private_key = None
        ssh_username = None
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid}]
    nocheck = {}
    for job in jobs:
        job_id = settings.job_id(job)
        nocheck[job_id] = set()
        if taskid is None:
            tasks = [
                x.id for x in batch_client.task.list(
                    job_id,
                    task_list_options=batchmodels.TaskListOptions(select='id')
                )
            ]
        else:
            tasks = [taskid]
        tasks_to_term = []
        for task in tasks:
            if not util.confirm_action(
                    config, 'terminate {} task in job {}'.format(
                        task, job_id)):
                nocheck[job_id].add(task)
                continue
            tasks_to_term.append(task)
        if len(tasks_to_term) == 0:
            continue
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=_max_workers(tasks_to_term)) as executor:
            for task in tasks_to_term:
                executor.submit(
                    _terminate_task, batch_client, config, ssh_username,
                    ssh_private_key, native, force, job_id, task, nocheck)
    if wait:
        for job in jobs:
            job_id = settings.job_id(job)
            if taskid is None:
                tasks = [
                    x.id for x in batch_client.task.list(
                        job_id,
                        task_list_options=batchmodels.TaskListOptions(
                            select='id'
                        )
                    )
                ]
            else:
                tasks = [taskid]
            if len(tasks) == 0:
                continue
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=_max_workers(tasks)) as executor:
                for task in tasks:
                    try:
                        if task in nocheck[job_id]:
                            continue
                    except KeyError:
                        pass
                    executor.submit(
                        _wait_for_task_completion, batch_client, job_id, task)


def get_node_counts(batch_client, config, pool_id=None):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Get node state counts
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str pool_id: pool id
    """
    if util.is_none_or_empty(pool_id):
        pool_id = settings.pool_id(config)
    raw = None
    log = ['node state counts for pool {}'.format(pool_id)]
    try:
        if settings.raw(config):
            raw = util.print_raw_paged_output(
                batch_client.account.list_pool_node_counts,
                account_list_pool_node_counts_options=batchmodels.
                AccountListPoolNodeCountsOptions(
                    filter='poolId eq \'{}\''.format(pool_id)
                ),
                return_json=True
            )
            if len(raw) == 1:
                raw = {
                    pool_id: raw[0]
                }
        else:
            pc = batch_client.account.list_pool_node_counts(
                account_list_pool_node_counts_options=batchmodels.
                AccountListPoolNodeCountsOptions(
                    filter='poolId eq \'{}\''.format(pool_id)))
            try:
                pc = list(pc)[0]
            except IndexError:
                raise RuntimeError('pool {} does not exist'.format(pool_id))
    except batchmodels.BatchErrorException as ex:
        if 'pool does not exist' in ex.message.value:
            logger.error('{} pool does not exist'.format(pool_id))
        else:
            raise
    else:
        if not settings.raw(config):
            log.append('* dedicated: ({} total)'.format(pc.dedicated.total))
            log.append('  * creating: {}'.format(pc.dedicated.creating))
            log.append('  * idle: {}'.format(pc.dedicated.creating))
            log.append('  * leaving_pool: {}'.format(
                pc.dedicated.leaving_pool))
            log.append('  * offline: {}'.format(pc.dedicated.offline))
            log.append('  * preempted: {}'.format(pc.dedicated.preempted))
            log.append('  * rebooting: {}'.format(pc.dedicated.rebooting))
            log.append('  * reimaging: {}'.format(pc.dedicated.reimaging))
            log.append('  * running: {}'.format(pc.dedicated.running))
            log.append('  * start_task_failed: {}'.format(
                pc.dedicated.start_task_failed))
            log.append('  * starting: {}'.format(pc.dedicated.starting))
            log.append('  * unknown: {}'.format(pc.dedicated.unknown))
            log.append('  * unusable: {}'.format(pc.dedicated.unusable))
            log.append('  * waiting_for_start_task: {}'.format(
                pc.dedicated.waiting_for_start_task))
            log.append('* low priority: ({} total)'.format(
                pc.low_priority.total))
            log.append('  * creating: {}'.format(pc.low_priority.creating))
            log.append('  * idle: {}'.format(pc.low_priority.creating))
            log.append('  * leaving_pool: {}'.format(
                pc.low_priority.leaving_pool))
            log.append('  * offline: {}'.format(pc.low_priority.offline))
            log.append('  * preempted: {}'.format(pc.low_priority.preempted))
            log.append('  * rebooting: {}'.format(pc.low_priority.rebooting))
            log.append('  * reimaging: {}'.format(pc.low_priority.reimaging))
            log.append('  * running: {}'.format(pc.low_priority.running))
            log.append('  * start_task_failed: {}'.format(
                pc.low_priority.start_task_failed))
            log.append('  * starting: {}'.format(pc.low_priority.starting))
            log.append('  * unknown: {}'.format(pc.low_priority.unknown))
            log.append('  * unusable: {}'.format(pc.low_priority.unusable))
            log.append('  * waiting_for_start_task: {}'.format(
                pc.low_priority.waiting_for_start_task))
            logger.info(os.linesep.join(log))
    if util.is_not_empty(raw):
        util.print_raw_json(raw)


def list_nodes(
        batch_client, config, pool_id=None, nodes=None,
        start_task_failed=False, unusable=False):
    # type: (batch.BatchServiceClient, dict, str, list, bool, bool) -> None
    """Get a list of nodes
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str pool_id: pool id
    :param list nodes: list of nodes
    :param bool start_task_failed: nodes in start task failed
    :param bool unusable: nodes in unusable
    """
    if util.is_none_or_empty(pool_id):
        pool_id = settings.pool_id(config)
    if settings.raw(config):
        util.print_raw_paged_output(batch_client.compute_node.list, pool_id)
        return
    log = [('compute nodes for pool {} (filters: start_task_failed={} '
            'unusable={})').format(pool_id, start_task_failed, unusable)]
    if nodes is None:
        # add filter if specified
        filters = []
        if start_task_failed:
            filters.append('(state eq \'starttaskfailed\')')
        if unusable:
            filters.append('(state eq \'unusable\')')
        nodes = batch_client.compute_node.list(
            pool_id=pool_id,
            compute_node_list_options=batchmodels.ComputeNodeListOptions(
                filter=' or '.join(filters),
            ) if util.is_not_empty(filters) else None,
        )
    else:
        if start_task_failed and unusable:
            nodes = [
                node for node in nodes
                if node.state ==
                batchmodels.ComputeNodeState.start_task_failed or
                node.state == batchmodels.ComputeNodeState.unusable
            ]
        elif start_task_failed:
            nodes = [
                node for node in nodes
                if node.state ==
                batchmodels.ComputeNodeState.start_task_failed
            ]
        elif unusable:
            nodes = [
                node for node in nodes
                if node.state == batchmodels.ComputeNodeState.unusable
            ]
    i = 0
    for node in nodes:
        i += 1
        errors = ['  * errors:']
        if node.errors is not None:
            for err in node.errors:
                errors.append('    * {}: {}'.format(err.code, err.message))
                for de in err.error_details:
                    errors.append('      * {}: {}'.format(de.name, de.value))
        else:
            errors = ['  * no errors']
        st = ['  * start task:']
        if node.start_task_info is not None:
            if node.start_task_info.failure_info is not None:
                st.append(
                    '    * failure info: {}'.format(
                        node.start_task_info.failure_info.category.value))
                st.append(
                    '      * {}: {}'.format(
                        node.start_task_info.failure_info.code,
                        node.start_task_info.failure_info.message
                    )
                )
                for de in node.start_task_info.failure_info.details:
                    st.append('        * {}: {}'.format(de.name, de.value))
            else:
                if node.start_task_info.end_time is not None:
                    duration = (
                        node.start_task_info.end_time -
                        node.start_task_info.start_time
                    )
                else:
                    duration = 'n/a'
                st.extend([
                    '    * state: {}'.format(node.start_task_info.state.value),
                    '    * started: {}'.format(
                        node.start_task_info.start_time),
                    '    * completed: {}'.format(
                        node.start_task_info.end_time),
                    '    * duration: {}'.format(duration),
                    '    * result: {}'.format(
                        node.start_task_info.result.value
                        if node.start_task_info.result is not None else 'n/a'),
                    '    * exit code: {}'.format(
                        node.start_task_info.exit_code),
                ])
        else:
            st = ['  * no start task info']
        entry = [
            '* node id: {}'.format(node.id),
            '  * state: {} @ {}'.format(
                node.state.value, node.state_transition_time),
            '  * allocation time: {}'.format(node.allocation_time),
            '  * last boot time: {}'.format(node.last_boot_time),
            '  * scheduling state: {}'.format(node.scheduling_state.value),
            '  * agent:',
            '    * version: {}'.format(
                node.node_agent_info.version
                if node.node_agent_info is not None else 'pending'),
            '    * last update time: {}'.format(
                node.node_agent_info.last_update_time
                if node.node_agent_info is not None else 'pending'),
        ]
        entry.extend(errors)
        entry.extend(st)
        entry.extend([
            '  * vm size: {}'.format(node.vm_size),
            '  * dedicated: {}'.format(node.is_dedicated),
            '  * ip address: {}'.format(node.ip_address),
            '  * running tasks: {}'.format(node.running_tasks_count),
            '  * total tasks run: {}'.format(node.total_tasks_run),
            '  * total tasks succeeded: {}'.format(node.total_tasks_succeeded),
        ])
        log.extend(entry)
    if i == 0:
        logger.error(
            ('no nodes exist for pool {} (filters: start_task_failed={} '
             'unusable={})').format(pool_id, start_task_failed, unusable))
    else:
        logger.info(os.linesep.join(log))


def get_remote_login_settings(
        batch_client, config, nodes=None, suppress_output=False):
    # type: (batch.BatchServiceClient, dict, List[str], bool) -> dict
    """Get remote login settings
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    :param bool suppress_output: suppress output
    :rtype: dict
    :return: dict of node id -> remote login settings
    """
    pool_id = settings.pool_id(config)
    if nodes is None:
        nodes = batch_client.compute_node.list(
            pool_id,
            compute_node_list_options=batchmodels.ComputeNodeListOptions(
                select='id')
        )
    if settings.raw(config):
        raw = []
        for node in nodes:
            raw.append(util.print_raw_output(
                batch_client.compute_node.get_remote_login_settings,
                pool_id, node.id, return_json=True))
        util.print_raw_json(raw)
        return None
    ret = {}
    nodes = list(nodes)
    if len(nodes) > 0:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=_max_workers(nodes)) as executor:
            futures = {}
            for node in nodes:
                futures[node.id] = executor.submit(
                    batch_client.compute_node.get_remote_login_settings,
                    pool_id, node.id)
            for node_id in futures:
                ret[node_id] = futures[node_id].result()
        if util.on_python2():
            ret = collections.OrderedDict(sorted(ret.iteritems()))
        else:
            ret = collections.OrderedDict(sorted(ret.items()))
        if not suppress_output:
            for node_id in ret:
                logger.info('node {}: ip {} port {}'.format(
                    node_id, ret[node_id].remote_login_ip_address,
                    ret[node_id].remote_login_port))
    return ret


def get_remote_login_setting_for_node(batch_client, config, cardinal, node_id):
    # type: (batch.BatchServiceClient, dict, int, str) -> dict
    """Get remote login setting for a node
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param int cardinal: node cardinal number
    :param str node_id: node id
    :rtype: tuple
    :return: ip, port
    """
    pool_id = settings.pool_id(config)
    if node_id is None:
        if cardinal is None:
            raise ValueError('cardinal is invalid with no node_id specified')
        nodes = list(batch_client.compute_node.list(pool_id))
        if cardinal >= len(nodes):
            raise ValueError(
                ('cardinal value {} invalid for number of nodes {} in '
                 'pool {}').format(cardinal, len(nodes), pool_id))
        node_id = nodes[cardinal].id
    rls = batch_client.compute_node.get_remote_login_settings(
        pool_id, node_id)
    return rls.remote_login_ip_address, rls.remote_login_port


def egress_service_logs(
        batch_client, blob_client, config, cardinal=None, node_id=None,
        generate_sas=False, wait=False):
    # type: (batchsc.BatchServiceClient, azureblob.BlockBlobService, dict,
    #        int, str, bool, bool) -> None
    """Action: Pool Nodes Logs
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param int cardinal: cardinal node num
    :param str nodeid: node id
    :param bool generate_sas: generate sas
    :param bool wait: wait for upload to complete
    """
    pool_id = settings.pool_id(config)
    if node_id is None:
        if cardinal is None:
            raise ValueError('cardinal is invalid with no node_id specified')
        nodes = list(batch_client.compute_node.list(pool_id))
        if cardinal >= len(nodes):
            raise ValueError(
                ('cardinal value {} invalid for number of nodes {} in '
                 'pool {}').format(cardinal, len(nodes), pool_id))
        node_id = nodes[cardinal].id
    # get node allocation time
    node = batch_client.compute_node.get(pool_id, node_id)
    # generate container sas and create container
    bs = settings.batch_shipyard_settings(config)
    cont = bs.storage_entity_prefix + '-diaglogs'
    storage_settings = settings.credentials_storage(
        config, bs.storage_account_settings)
    sas = storage.create_blob_container_saskey(
        storage_settings, cont, 'egress', create_container=True)
    baseurl = 'https://{}.blob.{}/{}'.format(
        storage_settings.account, storage_settings.endpoint, cont)
    url = '{}?{}'.format(baseurl, sas)
    logger.info(
        ('egressing Batch service logs from compute node {} on pool {} '
         'to container {} on storage account {} beginning from {}').format(
             node_id, pool_id, cont, storage_settings.account,
             node.allocation_time))
    # issue service call to egress
    resp = batch_client.compute_node.upload_batch_service_logs(
        pool_id, node_id,
        upload_batch_service_logs_configuration=batchmodels.
        UploadBatchServiceLogsConfiguration(
            container_url=url,
            start_time=node.allocation_time,
        )
    )
    if resp.number_of_files_uploaded > 0:
        logger.info(
            'initiated upload of {} log files to {}/{}'.format(
                resp.number_of_files_uploaded, cont,
                resp.virtual_directory_name))
        # wait for upload to complete if specified
        if wait:
            # list blobs in vdir until we have the number specified
            logger.debug(
                ('waiting for {} log files to be uploaded; this may take '
                 'some time, please be patient').format(
                     resp.number_of_files_uploaded))
            count = 0
            while True:
                blobs = blob_client.list_blobs(
                    cont, prefix=resp.virtual_directory_name,
                    num_results=resp.number_of_files_uploaded)
                if len(list(blobs)) == resp.number_of_files_uploaded:
                    logger.info(
                        ('all {} files uploaded to {}/{} on storage '
                         'account {}').format(
                             resp.number_of_files_uploaded, cont,
                             resp.virtual_directory_name,
                             storage_settings.account))
                    break
                count += 1
                if count > 150:
                    logger.error('exceeded wait timeout for log egress')
                    return
                time.sleep(2)
        if generate_sas:
            sas = storage.create_saskey(
                storage_settings, cont, False, create=False, list_perm=True,
                read=True, write=False, delete=False, expiry_days=60)
            logger.info(
                'log location URL to share with support: {}?{}'.format(
                    baseurl, sas))
    else:
        logger.error('no log files to be uploaded')


def stream_file_and_wait_for_task(
        batch_client, config, filespec=None, disk=False):
    # type: (batch.BatchServiceClient, dict, str, bool) -> None
    """Stream a file and wait for task to complete
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str filespec: filespec (jobid,taskid,filename)
    :param bool disk: write to disk instead
    """
    if filespec is None:
        job_id = None
        task_id = None
        file = None
    else:
        job_id, task_id, file = filespec.split(',')
    if job_id is None:
        job_id = util.get_input('Enter job id: ')
    if task_id is None:
        task_id = util.get_input('Enter task id: ')
    if file is None:
        file = util.get_input(
            'Enter task-relative file path to stream [stdout.txt]: ')
    if file == '' or file is None:
        file = 'stdout.txt'
    # get first running task if specified
    if task_id == '@FIRSTRUNNING':
        logger.debug('attempting to get first running task in job {}'.format(
            job_id))
        while True:
            tasks = batch_client.task.list(
                job_id,
                task_list_options=batchmodels.TaskListOptions(
                    filter='state eq \'running\'',
                    select='id,state',
                ),
            )
            for task in tasks:
                task_id = task.id
                break
            if task_id == '@FIRSTRUNNING':
                time.sleep(1)
            else:
                break
    logger.debug('attempting to stream file {} from job={} task={}'.format(
        file, job_id, task_id))
    curr = 0
    completed = False
    notfound = 0
    dec = None
    try:
        fd = None
        if disk:
            fp = pathlib.Path(job_id, task_id, file)
            if (fp.exists() and not util.confirm_action(
                    config, 'overwrite {}'.format(fp))):
                return
            fp.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            logger.info('writing streamed data to disk: {}'.format(fp))
            fd = fp.open('wb', buffering=0)
        else:
            dec = codecs.getincrementaldecoder('utf8')()
        finalcheck = False
        while not completed:
            # get task file properties
            try:
                tfp = batch_client.file.get_properties_from_task(
                    job_id, task_id, file, raw=True)
            except batchmodels.BatchErrorException as ex:
                if ('The specified operation is not valid for the current '
                        'state of the resource.' in ex.message):
                    time.sleep(1)
                    continue
                elif ('The specified file does not exist.' in ex.message or
                      'The specified path does not exist.' in ex.message):
                    notfound += 1
                    if notfound > 20:
                        raise
                    time.sleep(1)
                    continue
                else:
                    raise
            size = int(tfp.response.headers['Content-Length'])
            # keep track of received bytes for this fragment as the
            # amount transferred can be less than the content length
            rbytes = 0
            if curr < size:
                frag = batch_client.file.get_from_task(
                    job_id, task_id, file,
                    batchmodels.FileGetFromTaskOptions(
                        ocp_range='bytes={}-{}'.format(curr, size))
                )
                for f in frag:
                    rbytes += len(f)
                    if fd is not None:
                        fd.write(f)
                    else:
                        print(dec.decode(f), end='')
            elif curr == size:
                task = batch_client.task.get(
                    job_id, task_id,
                    task_get_options=batchmodels.TaskGetOptions(
                        select='state')
                )
                if task.state == batchmodels.TaskState.completed:
                    # need to loop one more time the first time completed
                    # is noticed to get any remaining data
                    if not finalcheck:
                        finalcheck = True
                    else:
                        completed = True
                        if not disk:
                            print(dec.decode(bytes(), True))
            curr += rbytes
            if not completed and not finalcheck:
                time.sleep(1)
    finally:
        if fd is not None:
            fd.close()


def _get_task_file(batch_client, job_id, task_id, filename, fp):
    # type: (batch.BatchServiceClient, str, str, str,
    #        pathlib.Path) -> None
    """Get a files from a task
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job id
    :param str task_id: task id
    :param str filename: file name
    :param pathlib.Path fp: file path
    """
    stream = batch_client.file.get_from_task(job_id, task_id, filename)
    with fp.open('wb') as f:
        for fdata in stream:
            f.write(fdata)


def get_file_via_task(batch_client, config, filespec=None):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Get a file task style
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str filespec: filespec (jobid,taskid,filename)
    """
    if filespec is None:
        job_id = None
        task_id = None
        file = None
    else:
        job_id, task_id, file = filespec.split(',')
    if job_id is None:
        job_id = util.get_input('Enter job id: ')
    if task_id is None:
        task_id = util.get_input('Enter task id: ')
    if file is None:
        file = util.get_input(
            'Enter task-relative file path to retrieve [stdout.txt]: ')
    if file == '' or file is None:
        file = 'stdout.txt'
    # get first running task if specified
    if task_id == '@FIRSTRUNNING':
        logger.debug('attempting to get first running task in job {}'.format(
            job_id))
        while True:
            tasks = batch_client.task.list(
                job_id,
                task_list_options=batchmodels.TaskListOptions(
                    filter='state eq \'running\'',
                    select='id,state',
                ),
            )
            for task in tasks:
                task_id = task.id
                break
            if task_id == '@FIRSTRUNNING':
                time.sleep(1)
            else:
                break
    # check if file exists on disk; a possible race condition here is
    # understood
    fp = pathlib.Path(pathlib.Path(file).name)
    if (fp.exists() and
            not util.confirm_action(
                config, 'file overwrite of {}'.format(file))):
        raise RuntimeError('file already exists: {}'.format(file))
    logger.debug('attempting to retrieve file {} from job={} task={}'.format(
        file, job_id, task_id))
    _get_task_file(batch_client, job_id, task_id, file, fp)
    logger.debug('file {} retrieved from job={} task={} bytes={}'.format(
        file, job_id, task_id, fp.stat().st_size))


def get_all_files_via_task(batch_client, config, filespec=None):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Get all files from a task
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str filespec: filespec (jobid,taskid,include_pattern)
    """
    if filespec is None:
        job_id = None
        task_id = None
        incl = None
    else:
        job_id, task_id, incl = filespec.split(',')
    if job_id is None:
        job_id = util.get_input('Enter job id: ')
    if task_id is None:
        task_id = util.get_input('Enter task id: ')
    if incl is None:
        incl = util.get_input('Enter filter: ')
    if incl is not None and len(incl) == 0:
        incl = None
    # get first running task if specified
    if task_id == '@FIRSTRUNNING':
        logger.debug('attempting to get first running task in job {}'.format(
            job_id))
        while True:
            tasks = batch_client.task.list(
                job_id,
                task_list_options=batchmodels.TaskListOptions(
                    filter='state eq \'running\'',
                    select='id,state',
                ),
            )
            for task in tasks:
                task_id = task.id
                break
            if task_id == '@FIRSTRUNNING':
                time.sleep(1)
            else:
                break
    # iterate through all files in task and download them
    logger.debug('downloading files to {}/{}'.format(job_id, task_id))
    files = list(batch_client.file.list_from_task(
        job_id, task_id, recursive=True))
    i = 0
    if len(files) > 0:
        dirs_created = set('.')
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=_max_workers(files)) as executor:
            for file in files:
                if file.is_directory:
                    continue
                if incl is not None and not fnmatch.fnmatch(file.name, incl):
                    continue
                fp = pathlib.Path(job_id, task_id, file.name)
                if str(fp.parent) not in dirs_created:
                    fp.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                    dirs_created.add(str(fp.parent))
                executor.submit(
                    _get_task_file, batch_client, job_id, task_id,
                    file.name, fp)
                i += 1
    if i == 0:
        logger.error('no files found for task {} job {} include={}'.format(
            task_id, job_id, incl if incl is not None else ''))
    else:
        logger.info(
            'all task files retrieved from job={} task={} include={}'.format(
                job_id, task_id, incl if incl is not None else ''))


def _get_node_file(batch_client, pool_id, node_id, filename, fp):
    # type: (batch.BatchServiceClient, dict, str, str, str,
    #        pathlib.Path) -> None
    """Get a file from the node
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str pool_id: pool id
    :param str node_id: node id
    :param str filename: file name
    :param pathlib.Path fp: file path
    """
    stream = batch_client.file.get_from_compute_node(
        pool_id, node_id, filename)
    with fp.open('wb') as f:
        for fdata in stream:
            f.write(fdata)


def get_all_files_via_node(batch_client, config, filespec=None):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Get a file node style
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str filespec: filespec (nodeid,include_pattern)
    """
    if filespec is None:
        node_id = None
        incl = None
    else:
        node_id, incl = filespec.split(',')
    if node_id is None:
        node_id = util.get_input('Enter node id: ')
    if incl is None:
        incl = util.get_input('Enter filter: ')
    if node_id is None or len(node_id) == 0:
        raise ValueError('node id is invalid')
    if incl is not None and len(incl) == 0:
        incl = None
    pool_id = settings.pool_id(config)
    logger.debug('downloading files to {}/{}'.format(pool_id, node_id))
    files = list(batch_client.file.list_from_compute_node(
        pool_id, node_id, recursive=True))
    i = 0
    if len(files) > 0:
        dirs_created = set('.')
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=_max_workers(files)) as executor:
            for file in files:
                if file.is_directory:
                    continue
                if incl is not None and not fnmatch.fnmatch(file.name, incl):
                    continue
                fp = pathlib.Path(pool_id, node_id, file.name)
                if str(fp.parent) not in dirs_created:
                    fp.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                    dirs_created.add(str(fp.parent))
                executor.submit(
                    _get_node_file, batch_client, pool_id, node_id,
                    file.name, fp)
                i += 1
    if i == 0:
        logger.error('no files found for pool {} node {} include={}'.format(
            pool_id, node_id, incl if incl is not None else ''))
    else:
        logger.info(
            'all files retrieved from pool={} node={} include={}'.format(
                pool_id, node_id, incl if incl is not None else ''))


def get_file_via_node(batch_client, config, filespec=None):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Get a file node style
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str filespec: filespec (nodeid,filename)
    """
    if filespec is None:
        node_id = None
        file = None
    else:
        node_id, file = filespec.split(',')
    if node_id is None:
        node_id = util.get_input('Enter node id: ')
    if file is None:
        file = util.get_input(
            'Enter node-relative file path to retrieve: ')
    if node_id is None or len(node_id) == 0:
        raise ValueError('node id is invalid')
    if file == '' or file is None:
        raise RuntimeError('specified invalid file to retrieve')
    pool_id = settings.pool_id(config)
    # check if file exists on disk; a possible race condition here is
    # understood
    fp = pathlib.Path(pathlib.Path(file).name)
    if (fp.exists() and
            not util.confirm_action(
                config, 'file overwrite of {}'.format(file))):
        raise RuntimeError('file already exists: {}'.format(file))
    logger.debug('attempting to retrieve file {} from pool={} node={}'.format(
        file, pool_id, node_id))
    _get_node_file(batch_client, pool_id, node_id, file, fp)
    logger.debug('file {} retrieved from pool={} node={} bytes={}'.format(
        file, pool_id, node_id, fp.stat().st_size))


def log_job(job):
    """Log job
    :param job: job
    :rtype: list
    :return: log entries
    """
    log = []
    if job.execution_info.end_time is not None:
        duration = (
            job.execution_info.end_time - job.execution_info.start_time
        )
        tr = job.execution_info.terminate_reason
    else:
        duration = 'n/a'
        tr = 'n/a'
    log.extend([
        '* job id: {}'.format(job.id),
        '  * state: {} @ {}'.format(
            job.state.value, job.state_transition_time),
        '  * previous state: {} @ {}'.format(
            job.previous_state.value
            if job.previous_state is not None else 'n/a',
            job.previous_state_transition_time),
        '  * priority: {}'.format(job.priority),
        '  * on all tasks complete: {}'.format(
            job.on_all_tasks_complete.value),
        '  * on task failure: {}'.format(job.on_task_failure.value),
        '  * created: {}'.format(job.creation_time),
        '  * pool id: {}'.format(job.execution_info.pool_id),
        '  * started: {}'.format(job.execution_info.start_time),
        '  * completed: {}'.format(job.execution_info.end_time),
        '  * duration: {}'.format(duration),
        '  * terminate reason: {}'.format(tr),
    ])
    if util.is_not_empty(job.metadata):
        log.append('  * metadata:')
        for md in job.metadata:
            log.append('    * {}: {}'.format(md.name, md.value))
    if job.execution_info.scheduling_error is not None:
        log.extend([
            '  * scheduling error: {}'.format(
                job.execution_info.scheduling_error.category.value),
            '    * {}: {}'.format(
                job.execution_info.scheduling_error.code,
                job.execution_info.scheduling_error.message),
        ])
        for de in job.execution_info.scheduling_error.details:
            log.append('      * {}: {}'.format(de.name, de.value))
    return log


def log_job_schedule(js):
    """Log job schedule
    :param js: job schedule
    :rtype: list
    :return: log entries
    """
    log = [
        '* job schedule id: {}'.format(js.id),
        '  * state: {} @ {}'.format(
            js.state.value, js.state_transition_time),
        '  * previous state: {} @ {}'.format(
            js.previous_state.value
            if js.previous_state is not None else 'n/a',
            js.previous_state_transition_time),
        '  * pool id: {}'.format(js.job_specification.pool_info.pool_id),
        '  * do not run until: {}'.format(js.schedule.do_not_run_until),
        '  * do not run after: {}'.format(js.schedule.do_not_run_after),
        '  * recurrence interval: {}'.format(
            js.schedule.recurrence_interval),
        '  * next run time: {}'.format(
            js.execution_info.next_run_time),
        '  * recent job: {}'.format(
            js.execution_info.recent_job.id
            if js.execution_info.recent_job is not None else None),
        '  * created: {}'.format(js.creation_time),
        '  * completed: {}'.format(js.execution_info.end_time),
    ]
    return log


def get_job_or_job_schedule(batch_client, config, jobid, jobscheduleid):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str) -> None
    """Get job or job schedule
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id
    :param str jobscheduleid: job schedule id
    """
    if settings.raw(config):
        util.print_raw_output(batch_client.job.get, jobid)
        return
    if util.is_not_empty(jobid):
        job = batch_client.job.get(jobid)
        log = ['job info']
        log.extend(log_job(job))
    elif util.is_not_empty(jobscheduleid):
        js = batch_client.job_schedule.get(jobscheduleid)
        log = ['job schedule info']
        log.extend(log_job_schedule(js))
    logger.info(os.linesep.join(log))


def list_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """List all jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    if settings.raw(config):
        raw = {
            'jobs': util.print_raw_paged_output(
                batch_client.job.list, return_json=True),
            'job_schedules': util.print_raw_paged_output(
                batch_client.job_schedule.list, return_json=True),
        }
        util.print_raw_json(raw)
        return
    jobs = batch_client.job.list()
    log = ['list of jobs:']
    i = 0
    for job in jobs:
        log.extend(log_job(job))
        i += 1
    if i == 0:
        logger.error('no jobs found')
    else:
        logger.info(os.linesep.join(log))
    i = 0
    log = ['list of job schedules:']
    jobschedules = batch_client.job_schedule.list()
    for js in jobschedules:
        log.extend(log_job_schedule(js))
        i += 1
    if i == 0:
        logger.error('no job schedules found')
    else:
        logger.info(os.linesep.join(log))


def log_task(task, jobid):
    """Log task
    :param task: task struct
    :param str jobid: job id
    :rtype: list
    :return: list of log entries
    """
    fi = []
    if task.execution_info is not None:
        if task.execution_info.failure_info is not None:
            fi.append(
                '    * failure info: {}'.format(
                    task.execution_info.failure_info.
                    category.value))
            fi.append(
                '      * {}: {}'.format(
                    task.execution_info.failure_info.code,
                    task.execution_info.failure_info.message
                )
            )
            for de in task.execution_info.failure_info.details:
                fi.append('        * {}: {}'.format(
                    de.name, de.value))
        if (task.execution_info.end_time is not None and
                task.execution_info.start_time is not None):
            duration = (task.execution_info.end_time -
                        task.execution_info.start_time)
        else:
            duration = 'n/a'
    if task.exit_conditions is not None:
        default_job_action = (
            task.exit_conditions.default.job_action.value
            if task.exit_conditions.default.job_action
            is not None else 'n/a'
        )
        default_dependency_action = (
            task.exit_conditions.default.dependency_action.value
            if task.exit_conditions.default.dependency_action
            is not None else 'n/a'
        )
    else:
        default_job_action = 'n/a'
        default_dependency_action = 'n/a'
    ret = [
        '* task id: {}'.format(task.id),
        '  * job id: {}'.format(jobid),
        '  * state: {} @ {}'.format(
            task.state.value, task.state_transition_time),
        '  * previous state: {} @ {}'.format(
            task.previous_state.value
            if task.previous_state is not None else 'n/a',
            task.previous_state_transition_time),
        '  * has upstream dependencies: {}'.format(
            task.depends_on is not None),
        '  * default exit options:',
        '    * job action: {}'.format(default_job_action),
        '    * dependency action: {}'.format(
            default_dependency_action),
        '  * max retries: {}'.format(
            task.constraints.max_task_retry_count),
        '  * retention time: {}'.format(
            task.constraints.retention_time),
        '  * execution details:',
        '    * pool id: {}'.format(
            task.node_info.pool_id if task.node_info is not None
            else 'n/a'),
        '    * node id: {}'.format(
            task.node_info.node_id if task.node_info is not None
            else 'n/a'),
        '    * started: {}'.format(
            task.execution_info.start_time
            if task.execution_info is not None else 'n/a'),
        '    * completed: {}'.format(
            task.execution_info.end_time
            if task.execution_info is not None else 'n/a'),
        '    * duration: {}'.format(duration),
        '    * retry count: {}'.format(
            task.execution_info.retry_count),
        '    * requeue count: {}'.format(
            task.execution_info.requeue_count),
        '    * result: {}'.format(
            task.execution_info.result.value
            if task.execution_info.result is not None else 'n/a'),
        '    * exit code: {}'.format(
            task.execution_info.exit_code
            if task.execution_info is not None else 'n/a'),
    ]
    ret.extend(fi)
    return ret


def get_task(batch_client, config, jobid, taskid):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool, str, bool) -> bool
    """Get a single task for the specified job
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id
    :param str taskid: task id
    :rtype: bool
    :return: if tasks has completed
    """
    if settings.raw(config):
        util.print_raw_output(batch_client.task.get, jobid, taskid)
        return
    task = batch_client.task.get(jobid, taskid)
    log = ['task info']
    log.extend(log_task(task, jobid))
    logger.info(os.linesep.join(log))
    return task.state == batchmodels.TaskState.completed


def get_task_counts(batch_client, config, jobid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool, str, bool) -> bool
    """Get task counts for specified job
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to get task counts for
    """
    if util.is_none_or_empty(jobid):
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid}]
    raw = {}
    for job in jobs:
        jobid = settings.job_id(job)
        log = ['task counts for job {}'.format(jobid)]
        try:
            if settings.raw(config):
                raw[jobid] = util.print_raw_output(
                    batch_client.job.get_task_counts,
                    jobid,
                    return_json=True
                )
            else:
                tc = batch_client.job.get_task_counts(jobid)
        except batchmodels.BatchErrorException as ex:
            if 'The specified job does not exist' in ex.message.value:
                logger.error('{} job does not exist'.format(jobid))
                continue
            else:
                raise
        else:
            if not settings.raw(config):
                log.append('* active: {}'.format(tc.active))
                log.append('* running: {}'.format(tc.running))
                log.append('* completed: {}'.format(tc.completed))
                log.append('  * succeeded: {}'.format(tc.succeeded))
                log.append('  * failed: {}'.format(tc.failed))
                logger.info(os.linesep.join(log))
    if util.is_not_empty(raw):
        util.print_raw_json(raw)


def list_tasks(batch_client, config, all=False, jobid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool, str, bool) -> bool
    """List tasks for specified jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool all: all jobs
    :param str jobid: job id to list tasks from
    :rtype: bool
    :return: if all tasks have completed under job(s)
    """
    all_complete = True
    if all:
        jobs = batch_client.job.list()
    else:
        if util.is_none_or_empty(jobid):
            jobs = settings.job_specifications(config)
        else:
            jobs = [{'id': jobid}]
    raw = {}
    for job in jobs:
        if all:
            jobid = job.id
        else:
            jobid = settings.job_id(job)
        log = ['list of tasks for job {}'.format(jobid)]
        i = 0
        try:
            if settings.raw(config):
                raw[jobid] = util.print_raw_paged_output(
                    batch_client.task.list, jobid, return_json=True)
                continue
            tasks = batch_client.task.list(jobid)
            for task in tasks:
                log.extend(log_task(task, jobid))
                if task.state != batchmodels.TaskState.completed:
                    all_complete = False
                i += 1
        except batchmodels.BatchErrorException as ex:
            if 'The specified job does not exist' in ex.message.value:
                logger.error('{} job does not exist'.format(jobid))
                continue
            else:
                raise
        if i == 0:
            logger.error('no tasks found for job {}'.format(jobid))
        else:
            logger.info(os.linesep.join(log))
    if util.is_not_empty(raw):
        util.print_raw_json(raw)
    return all_complete


def list_task_files(batch_client, config, jobid=None, taskid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, str) -> None
    """List task files for specified jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to list
    :param str taskid: task id to list
    """
    if util.is_none_or_empty(jobid):
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid}]
    for job in jobs:
        jobid = settings.job_id(job)
        log = ['task file list for job {}'.format(jobid)]
        i = 0
        try:
            tasks = batch_client.task.list(
                jobid,
                task_list_options=batchmodels.TaskListOptions(select='id'))
            for task in tasks:
                if taskid is not None and taskid != task.id:
                    continue
                j = 0
                entry = [
                    '* task id: {}'.format(task.id),
                    '  * job id: {}'.format(jobid),
                ]
                files = batch_client.file.list_from_task(
                    jobid, task.id, recursive=True)
                for file in files:
                    if file.is_directory:
                        continue
                    entry.extend([
                        '  * file: {}'.format(file.name),
                        '    * last modified: {}'.format(
                            file.properties.last_modified),
                        '    * bytes: {}'.format(
                            file.properties.content_length),
                    ])
                    j += 1
                if j == 0:
                    entry.append(
                        '  * no files found'
                    )
                log.extend(entry)
                i += 1
        except batchmodels.BatchErrorException as ex:
            if 'The specified job does not exist' in ex.message.value:
                logger.error('{} job does not exist'.format(jobid))
                continue
            else:
                raise
        if i == 0:
            logger.error('no tasks found for job {}'.format(jobid))
        else:
            logger.info(os.linesep.join(log))


def generate_docker_login_settings(config, for_ssh=False):
    # type: (dict, bool) -> tuple
    """Generate docker login environment variables and command line
    for login/re-login
    :param dict config: configuration object
    :param bool for_ssh: for direct SSH use
    :rtype: tuple
    :return: (env vars, login cmds)
    """
    cmd = []
    env = []
    is_windows = settings.is_windows_pool(config)
    if is_windows and for_ssh:
        return (cmd, env)
    # get registries
    docker_registries = settings.docker_registries(config)
    singularity_registries = settings.singularity_registries(config)
    # get encryption settings
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    # create joinable arrays for env vars
    docker_servers = []
    docker_users = []
    docker_passwords = []
    singularity_servers = []
    singularity_users = []
    singularity_passwords = []
    for registry in docker_registries:
        if registry.registry_server is None:
            docker_servers.append('')
        else:
            docker_servers.append(registry.registry_server)
        docker_users.append(registry.user_name)
        docker_passwords.append(registry.password)
    for registry in singularity_registries:
        if registry.registry_server is None:
            singularity_servers.append('')
        else:
            singularity_servers.append(registry.registry_server)
        singularity_users.append(registry.user_name)
        singularity_passwords.append(registry.password)
    # populate command and env vars
    if len(docker_servers) > 0:
        # create either cmd or env for each
        value = ','.join(docker_servers)
        if for_ssh:
            cmd.append('export DOCKER_LOGIN_SERVER={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    name='DOCKER_LOGIN_SERVER', value=value)
            )
        value = ','.join(docker_users)
        if for_ssh:
            cmd.append('export DOCKER_LOGIN_USERNAME={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    name='DOCKER_LOGIN_USERNAME', value=value)
            )
        value = ','.join(docker_passwords)
        if for_ssh:
            cmd.append('export DOCKER_LOGIN_PASSWORD={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    name='DOCKER_LOGIN_PASSWORD',
                    value=crypto.encrypt_string(encrypt, value, config))
            )
    if len(singularity_servers) > 0:
        # create either cmd or env for each
        value = ','.join(singularity_servers)
        if for_ssh:
            cmd.append('export SINGULARITY_LOGIN_SERVER={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    name='SINGULARITY_LOGIN_SERVER', value=value)
            )
        value = ','.join(singularity_users)
        if for_ssh:
            cmd.append('export SINGULARITY_LOGIN_USERNAME={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    name='SINGULARITY_LOGIN_USERNAME', value=value)
            )
        value = ','.join(singularity_passwords)
        if for_ssh:
            cmd.append('export SINGULARITY_LOGIN_PASSWORD={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    name='SINGULARITY_LOGIN_PASSWORD',
                    value=crypto.encrypt_string(encrypt, value, config))
            )
    # unset env for ssh
    if for_ssh:
        env = None
    # append script execution
    start_mnt = '/'.join((
        settings.temp_disk_mountpoint(config),
        'batch', 'tasks', 'startup',
    ))
    cmd.append('pushd {}/wd'.format(start_mnt))
    cmd.append('./registry_login.sh{}'.format(' -e' if encrypt else ''))
    cmd.append('popd')
    return env, cmd


def check_jobs_for_auto_pool(config):
    # type: (dict) -> bool
    """Check jobs for auto pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :rtype: bool
    :return: if auto pool is enabled
    """
    # ensure all jobspecs uniformly have autopool or all off
    autopool = []
    for jobspec in settings.job_specifications(config):
        if settings.job_auto_pool(jobspec) is None:
            autopool.append(False)
        else:
            autopool.append(True)
    if autopool.count(False) == len(autopool):
        return False
    elif autopool.count(True) == len(autopool):
        logger.debug('autopool detected for jobs')
        return True
    else:
        raise ValueError('all jobs must have auto_pool enabled or disabled')


def _format_generic_task_id(prefix, padding, tasknum):
    # type: (str, bool, int) -> str
    """Format a generic task id from a task number
    :param str prefix: prefix
    :param int padding: zfill task number
    :param int tasknum: task number
    :rtype: str
    :return: generic task id
    """
    return '{}{}'.format(prefix, str(tasknum).zfill(padding))


def _generate_next_generic_task_id(
        batch_client, config, job_id, tasklist=None, reserved=None,
        task_map=None, last_task_id=None, is_merge_task=False,
        federation_id=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict, str,
    #        list, str, dict, str, bool, str) -> Tuple[list, str]
    """Generate the next generic task id
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str job_id: job id
    :param list tasklist: list of current (committed) tasks in job
    :param str reserved: reserved task id
    :param dict task_map: map of pending tasks to add to the job
    :param str last_task_id: last task id
    :param bool is_merge_task: is merge task
    :param str federation_id: federation id
    :rtype: tuple
    :return: (list of committed task ids for job, next generic docker task id)
    """
    # get prefix and padding settings
    prefix = settings.autogenerated_task_id_prefix(config)
    padding = settings.autogenerated_task_id_zfill(config)
    delimiter = prefix if util.is_not_empty(prefix) else ' '
    if is_merge_task:
        prefix = 'merge-{}'.format(prefix)
    # get filtered, sorted list of generic docker task ids
    try:
        if tasklist is None and util.is_none_or_empty(federation_id):
            tasklist = batch_client.task.list(
                job_id,
                task_list_options=batchmodels.TaskListOptions(
                    filter='startswith(id, \'{}\')'.format(prefix)
                    if util.is_not_empty(prefix) else None,
                    select='id'))
            tasklist = list(tasklist)
        tasknum = sorted(
            [int(x.id.split(delimiter)[-1]) for x in tasklist])[-1] + 1
    except (batchmodels.BatchErrorException, IndexError, TypeError):
        tasknum = 0
    if reserved is not None:
        tasknum_reserved = int(reserved.split(delimiter)[-1])
        while tasknum == tasknum_reserved:
            tasknum += 1
    id = _format_generic_task_id(prefix, padding, tasknum)
    if task_map is not None:
        while id in task_map:
            try:
                if (last_task_id is not None and
                        last_task_id.startswith(prefix)):
                    tasknum = int(last_task_id.split(delimiter)[-1])
                    last_task_id = None
            except Exception:
                last_task_id = None
            tasknum += 1
            id = _format_generic_task_id(prefix, padding, tasknum)
    return tasklist, id


def _submit_task_sub_collection(
        batch_client, job_id, start, end, slice, all_tasks, task_map):
    # type: (batch.BatchServiceClient, str, int, int, int, list, dict) -> None
    """Submits a sub-collection of tasks, do not call directly
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job to add to
    :param int start: start offset, includsive
    :param int end: end offset, exclusive
    :param int slice: slice width
    :param list all_tasks: list of all task ids
    :param dict task_map: task collection map to add
    """
    initial_slice = slice
    while True:
        chunk_end = start + slice
        if chunk_end > end:
            chunk_end = end
        chunk = all_tasks[start:chunk_end]
        logger.debug('submitting {} tasks ({} -> {}) to job {}'.format(
            len(chunk), start, chunk_end - 1, job_id))
        try:
            results = batch_client.task.add_collection(job_id, chunk)
        except batchmodels.BatchErrorException as e:
            if e.error.code == 'RequestBodyTooLarge':
                # collection contents are too large, reduce and retry
                if slice == 1:
                    raise
                slice = slice >> 1
                if slice < 1:
                    slice = 1
                logger.error(
                    ('task collection slice was too big, retrying with '
                     'slice={}').format(slice))
                continue
        else:
            # go through result and retry just failed tasks
            while True:
                retry = []
                for result in results.value:
                    if result.status == batchmodels.TaskAddStatus.client_error:
                        de = None
                        if result.error.values is not None:
                            de = [
                                '{}: {}'.format(x.key, x.value)
                                for x in result.error.values
                            ]
                        logger.error(
                            ('skipping retry of adding task {} as it '
                             'returned a client error (code={} message={} {}) '
                             'for job {}, taskspec: {}').format(
                                 result.task_id, result.error.code,
                                 result.error.message,
                                 ' '.join(de) if de is not None else '',
                                 job_id, task_map[result.task_id]))
                    elif (result.status ==
                          batchmodels.TaskAddStatus.server_error):
                        retry.append(task_map[result.task_id])
                if len(retry) > 0:
                    logger.debug('retrying adding {} tasks to job {}'.format(
                        len(retry), job_id))
                    results = batch_client.task.add_collection(job_id, retry)
                else:
                    break
        if chunk_end == end:
            break
        start = chunk_end
        slice = initial_slice


def _add_task_collection(batch_client, job_id, task_map):
    # type: (batch.BatchServiceClient, str, dict) -> None
    """Add a collection of tasks to a job
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job to add to
    :param dict task_map: task collection map to add
    """
    all_tasks = list(task_map.values())
    slice = 100  # can only submit up to 100 tasks at a time
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_EXECUTOR_WORKERS) as executor:
        for start in range(0, len(all_tasks), slice):
            end = start + slice
            if end > len(all_tasks):
                end = len(all_tasks)
            executor.submit(
                _submit_task_sub_collection, batch_client, job_id, start, end,
                end - start, all_tasks, task_map)
    logger.info('submitted all {} tasks to job {}'.format(
        len(task_map), job_id))


def _generate_non_native_env_dump(env_vars, envfile):
    # type: (dict, str) -> str
    """Generate env dump command for non-native tasks
    :param dict env_vars: env vars
    :param str envfile: env file
    """
    exclude = [
        '^{}='.format(x) for x in _ENV_EXCLUDE_LINUX if x not in env_vars
    ]
    if util.is_not_empty(exclude):
        return 'env | grep -vE "{}" > {}'.format('|'.join(exclude), envfile)
    else:
        return 'env | {}'.format(envfile)


def _generate_non_native_env_var(env_vars):
    # type: (dict, str) -> str
    """Generate env dump command for non-native tasks
    :param dict env_vars: env vars
    """
    exclude = [
        '^{}='.format(x) for x in _ENV_EXCLUDE_LINUX if x not in env_vars
    ]
    return '{}'.format('|'.join(exclude))


def _construct_mpi_command(pool, task):
    """Construct the MPI command for MPI tasks
    :parm task: task settings
    :rtype: tuple
    :return mpi command, ib env
    """
    ib_pkey_file = '$AZ_BATCH_NODE_STARTUP_DIR/wd/UCX_IB_PKEY'
    ib_env = {}
    mpi_opts = []
    mpi_opts.extend(task.multi_instance.mpi.options)
    processes_per_node = (
        task.multi_instance.mpi.processes_per_node)
    # set mpi options for the different runtimes
    if task.multi_instance.mpi.runtime.startswith('intelmpi'):
        if isinstance(processes_per_node, int):
            mpi_opts.extend([
                '-hosts $AZ_BATCH_HOST_LIST',
                '-np {}'.format(
                    task.multi_instance.num_instances *
                    processes_per_node
                ),
                '-perhost {}'.format(processes_per_node)
            ])
        elif isinstance(processes_per_node, str):
            mpi_opts.extend([
                '-hosts $AZ_BATCH_HOST_LIST',
                '-np $(expr {} \\* $({}))'.format(
                    task.multi_instance.num_instances,
                    processes_per_node
                ),
                '-perhost $({})'.format(processes_per_node)
            ])
        if task.infiniband:
            ib_env['I_MPI_FALLBACK'] = '0'
            # create a manpath entry for potentially buggy intel mpivars.sh
            ib_env['MANPATH'] = '/usr/share/man:/usr/local/man'
            if settings.is_networkdirect_rdma_pool(pool.vm_size):
                ib_env['I_MPI_FABRICS'] = 'shm:dapl'
                ib_env['I_MPI_DAPL_PROVIDER'] = 'ofa-v2-ib0'
                ib_env['I_MPI_DYNAMIC_CONNECTION'] = '0'
                ib_env['I_MPI_DAPL_TRANSLATION_CACHE'] = '0'
            elif settings.is_sriov_rdma_pool(pool.vm_size):
                # IntelMPI pre-2019
                if task.multi_instance.mpi.runtime == 'intelmpi-ofa':
                    ib_env['I_MPI_FABRICS'] = 'shm:ofa'
                else:
                    # IntelMPI 2019+
                    ib_env['I_MPI_FABRICS'] = 'shm:ofi'
                    ib_env['FI_PROVIDER'] = 'mlx'
    elif (task.multi_instance.mpi.runtime == 'mpich' or
          task.multi_instance.mpi.runtime == 'mvapich'):
        if isinstance(processes_per_node, int):
            mpi_opts.extend([
                '-hosts $AZ_BATCH_HOST_LIST',
                '-np {}'.format(
                    task.multi_instance.num_instances *
                    processes_per_node
                ),
                '-ppn {}'.format(processes_per_node)
            ])
        elif isinstance(processes_per_node, str):
            mpi_opts.extend([
                '-hosts $AZ_BATCH_HOST_LIST',
                '-np $(expr {} \\* $({}))'.format(
                    task.multi_instance.num_instances,
                    processes_per_node
                ),
                '-ppn $({})'.format(processes_per_node)
            ])
        if task.infiniband and settings.is_sriov_rdma_pool(pool.vm_size):
            mpi_opts.append(
                '-env $(cat {})'.format(ib_pkey_file))
    elif task.multi_instance.mpi.runtime == 'openmpi':
        if isinstance(processes_per_node, int):
            mpi_opts.extend([
                '--oversubscribe',
                '-host $AZ_BATCH_HOST_LIST',
                '-np {}'.format(
                    task.multi_instance.num_instances *
                    processes_per_node
                ),
                '--map-by ppr:{}:node'.format(processes_per_node)
            ])
        elif isinstance(processes_per_node, str):
            mpi_opts.extend([
                '--oversubscribe',
                '-host $AZ_BATCH_HOST_LIST',
                '-np $(expr {} \\* $({}))'.format(
                    task.multi_instance.num_instances,
                    processes_per_node
                ),
                '--map-by ppr:$({}):node'.format(
                    processes_per_node)
            ])
        if task.infiniband and settings.is_sriov_rdma_pool(pool.vm_size):
            mpi_opts.extend([
                '--mca pml ucx',
                '--mca btl ^vader,tcp,openib',
                '-x UCX_NET_DEVICES=mlx5_0:1',
                '-x $(cat {})'.format(ib_pkey_file)
            ])
        else:
            mpi_opts.append('--mca btl_tcp_if_include eth0')
    is_singularity = util.is_not_empty(task.singularity_image)
    if is_singularity:
        # build the singularity mpi command
        mpi_singularity_cmd = 'singularity {} {} {} {}'.format(
            task.singularity_cmd,
            ' '.join(task.run_options),
            task.singularity_image,
            task.command)
        mpi_command = '{} {} {}'.format(
            task.multi_instance.mpi.executable_path,
            ' '.join(mpi_opts),
            mpi_singularity_cmd
        )
    else:
        # build the docker mpi command
        if task.multi_instance.mpi.runtime == 'openmpi':
            mpi_opts.append('--allow-run-as-root')
        mpi_command = '{} {} {}'.format(
            task.multi_instance.mpi.executable_path,
            ' '.join(mpi_opts),
            task.command)
    return mpi_command, ib_env


def _construct_task(
        batch_client, blob_client, keyvault_client, config, federation_id,
        bxfile, bs, native, is_windows, tempdisk, allow_run_on_missing,
        docker_missing_images, singularity_missing_images, cloud_pool,
        pool, jobspec, job_id, job_env_vars, task_map, existing_tasklist,
        reserved_task_id, lasttaskid, is_merge_task, uses_task_dependencies,
        on_task_failure, container_image_refs, _task):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,
    #        azure.keyvault.KeyVaultClient, dict, str, tuple,
    #        settings.BatchShipyardSettings, bool, bool, str, bool,
    #        list, list, batchmodels.CloudPool, settings.PoolSettings,
    #        dict, str, dict, dict, list, str, str, bool, bool,
    #        batchmodels.OnTaskFailure, set, dict) -> tuple
    """Contruct a Batch task and add it to the task map
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param tuple bxfile: blobxfer file
    :param settings.BatchShipyardSettings bs: batch shipyard settings
    :param bool native: native pool
    :param bool is_windows: is windows pool
    :param str tempdisk: tempdisk
    :param bool allow_run_on_missing: allow run on missing image
    :param list docker_missing_images: docker missing images
    :param list singularity_missing_images: singularity missing images
    :param batchmodels.CloudPool cloud_pool: cloud pool
    :param settings.PoolSettings pool: pool settings
    :param dict jobspec: job spec
    :param dict job_env_vars: job env vars
    :param dict task_map: task map
    :param list existing_tasklist: existing task list
    :param str reserved_task_id: reserved task id
    :param str lasttaskid: last task id
    :param bool is_merge_task: is merge task
    :param bool uses_task_dependencies: uses task dependencies
    :param batchmodels.OntaskFailure on_task_failure: on task failure
    :param set container_image_refs: container image references
    :param dict _task: task spec
    :rtype: tuple
    :return: (list of committed task ids for job, task id added to task map,
        instance count for task, has gpu task, has ib task)
    """
    _task_id = settings.task_id(_task)
    if util.is_none_or_empty(_task_id):
        existing_tasklist, _task_id = _generate_next_generic_task_id(
            batch_client, config, job_id, tasklist=existing_tasklist,
            reserved=reserved_task_id, task_map=task_map,
            last_task_id=lasttaskid, is_merge_task=is_merge_task,
            federation_id=federation_id)
        settings.set_task_id(_task, _task_id)
    if util.is_none_or_empty(settings.task_name(_task)):
        settings.set_task_name(_task, '{}-{}'.format(job_id, _task_id))
    del _task_id
    task = settings.task_settings(
        cloud_pool, config, pool, jobspec, _task, federation_id=federation_id)
    is_singularity = util.is_not_empty(task.singularity_image)
    if util.is_not_empty(federation_id):
        if is_singularity:
            container_image_refs.add(task.singularity_image)
        else:
            container_image_refs.add(task.docker_image)
    task_ic = 1
    # retrieve keyvault task env vars
    if util.is_not_empty(
            task.environment_variables_keyvault_secret_id):
        task_env_vars = keyvault.get_secret(
            keyvault_client,
            task.environment_variables_keyvault_secret_id,
            value_is_json=True)
        task_env_vars = util.merge_dict(
            task.environment_variables, task_env_vars or {})
    else:
        task_env_vars = task.environment_variables
    # merge job and task env vars
    env_vars = util.merge_dict(job_env_vars, task_env_vars)
    del task_env_vars
    # set gpu env vars
    if task.gpu != 'disable':
        gpu_env = {
            'CUDA_CACHE_DISABLE': '0',
            'CUDA_CACHE_MAXSIZE': '1073741824',
            # use absolute path due to non-expansion
            'CUDA_CACHE_PATH': '{}/batch/tasks/.nv/ComputeCache'.format(
                tempdisk),
        }
        env_vars = util.merge_dict(env_vars, gpu_env)
        del gpu_env
    taskenv = []
    commands = {
        'mpi': None,
        'docker_exec': False,
        'preexec': None,
        'task': None,
        'login': None,
        'input': None,
        'output': None,
    }
    # check if this is a multi-instance task
    mis = None
    if settings.is_multi_instance_task(_task):
        if util.is_not_empty(task.multi_instance.coordination_command):
            if native:
                if is_windows:
                    cc = ' && '.join(task.multi_instance.coordination_command)
                else:
                    cc = '; '.join(task.multi_instance.coordination_command)
            else:
                coordcmd = [
                    _generate_non_native_env_dump(env_vars, task.envfile),
                ]
                coordcmd.extend(task.multi_instance.coordination_command)
                cc = util.wrap_commands_in_shell(
                    coordcmd, windows=is_windows, wait=False)
                del coordcmd
        else:
            # no-op for singularity
            if is_singularity:
                cc = ':'
        if not native and util.is_none_or_empty(cc):
            raise ValueError(
                ('coordination_command cannot be empty for this '
                 'configuration: native={} singularity={}').format(
                     native, is_singularity))
        mis = batchmodels.MultiInstanceSettings(
            number_of_instances=task.multi_instance.num_instances,
            coordination_command_line=cc,
            common_resource_files=[],
        )
        task_ic = task.multi_instance.num_instances
        del cc
        # add common resource files for multi-instance
        if util.is_not_empty(task.multi_instance.resource_files):
            for rf in task.multi_instance.resource_files:
                mis.common_resource_files.append(
                    batchmodels.ResourceFile(
                        file_path=rf.file_path,
                        http_url=rf.blob_source,
                        file_mode=rf.file_mode,
                    )
                )
        # set pre-exec command
        if util.is_not_empty(task.multi_instance.pre_execution_command):
            commands['preexec'] = task.multi_instance.pre_execution_command
        # set application command
        if native:
            if task.multi_instance.mpi is None:
                commands['task'] = [task.command]
            else:
                commands['mpi'], ib_env = _construct_mpi_command(pool, task)
                if util.is_not_empty(ib_env):
                    env_vars = util.merge_dict(env_vars, ib_env)
                del ib_env
                commands['task'] = [commands['mpi']]
            # insert preexec prior to task command for native
            if util.is_not_empty(commands['preexec']):
                commands['task'].insert(0, commands['preexec'])
        else:
            commands['task'] = []
            # for non-native do not set the RUNTIME so the user command is
            # executed as-is
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_ENV_EXCLUDE',
                    value=_generate_non_native_env_var(env_vars)
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_ENV_FILE',
                    value=task.envfile,
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_RUNTIME_CMD_OPTS',
                    value=(
                        ' '.join(task.run_options) if is_singularity
                        else ' '.join(task.docker_exec_options)
                    ),
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_RUNTIME_CMD',
                    value=(
                        task.singularity_cmd if is_singularity else
                        'exec'
                    ),
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_CONTAINER_IMAGE_NAME',
                    value=(
                        task.singularity_image if is_singularity else
                        task.name  # docker exec requires task name
                    ),
                )
            )
            if not is_singularity:
                commands['docker_exec'] = True
            if task.multi_instance.mpi is not None:
                commands['mpi'], ib_env = _construct_mpi_command(pool, task)
                if util.is_not_empty(ib_env):
                    env_vars = util.merge_dict(env_vars, ib_env)
                del ib_env
    else:
        if native:
            commands['task'] = [
                '{}'.format(' ' + task.command) if task.command else ''
            ]
        else:
            commands['task'] = []
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_ENV_EXCLUDE',
                    value=_generate_non_native_env_var(env_vars)
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_ENV_FILE',
                    value=task.envfile,
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_RUNTIME_CMD_OPTS',
                    value=' '.join(task.run_options)
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_RUNTIME',
                    value='singularity' if is_singularity else 'docker',
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_RUNTIME_CMD',
                    value=task.singularity_cmd if is_singularity else 'run',
                )
            )
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_CONTAINER_IMAGE_NAME',
                    value=(
                        task.singularity_image if is_singularity else
                        task.docker_image
                    ),
                )
            )
    output_files = None
    # get registry login if missing images
    if (not native and allow_run_on_missing and
            (len(docker_missing_images) > 0 or
             len(singularity_missing_images) > 0)):
        loginenv, commands['login'] = generate_docker_login_settings(config)
        taskenv.extend(loginenv)
    # digest any input_data
    commands['input'] = data.process_input_data(
        config, bxfile, _task, on_task=True)
    if native and commands['input'] is not None:
        raise RuntimeError(
            'input_data at task-level is not supported on '
            'native container pools')
    # digest any output data
    commands['output'] = data.process_output_data(config, bxfile, _task)
    if commands['output'] is not None:
        if native:
            output_files = commands['output']
            commands['output'] = None
    # populate task runner vars for non-native mode
    if not native:
        # set the correct runner script
        if commands['docker_exec']:
            commands['task'] = [
                '$AZ_BATCH_NODE_STARTUP_DIR/wd/'
                'shipyard_docker_exec_task_runner.sh'
            ]
        else:
            commands['task'] = [
                '$AZ_BATCH_NODE_STARTUP_DIR/wd/shipyard_task_runner.sh'
            ]
        # set system prologue command
        sys_prologue_cmd = []
        if util.is_not_empty(commands['login']):
            sys_prologue_cmd.extend(commands['login'])
        if util.is_not_empty(commands['input']):
            sys_prologue_cmd.append(commands['input'])
        if util.is_not_empty(sys_prologue_cmd):
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_SYSTEM_PROLOGUE_CMD',
                    value=util.wrap_commands_in_shell(
                        sys_prologue_cmd, windows=is_windows),
                )
            )
        del sys_prologue_cmd
        # set user prologue command
        if util.is_not_empty(commands['preexec']):
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_USER_PROLOGUE_CMD',
                    value=commands['preexec'],
                )
            )
        # set user command (task)
        taskenv.append(
            batchmodels.EnvironmentSetting(
                name='SHIPYARD_USER_CMD',
                value=commands['mpi'] or task.command,
            )
        )
        # set epilogue command
        if util.is_not_empty(commands['output']):
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_SYSTEM_EPILOGUE_CMD',
                    value=commands['output']
                )
            )
    # always add env vars in (host) task to be dumped into container
    # task (if non-native)
    if util.is_not_empty(env_vars):
        for key in env_vars:
            taskenv.append(
                batchmodels.EnvironmentSetting(name=key, value=env_vars[key])
            )
    del env_vars
    # add singularity only vars
    if is_singularity:
        taskenv.append(
            batchmodels.EnvironmentSetting(
                name='SINGULARITY_CACHEDIR',
                value=settings.get_singularity_cachedir(config)
            )
        )
        taskenv.append(
            batchmodels.EnvironmentSetting(
                name='SINGULARITY_SYPGPDIR',
                value=settings.get_singularity_sypgpdir(config)
            )
        )
    # create task
    if util.is_not_empty(commands['task']):
        if native:
            if is_windows:
                tc = ' && '.join(commands['task'])
            else:
                tc = '; '.join(commands['task'])
            tc = tc.strip()
        else:
            tc = util.wrap_commands_in_shell(
                commands['task'], windows=is_windows)
    else:
        tc = ''
    batchtask = batchmodels.TaskAddParameter(
        id=task.id,
        command_line=tc,
        user_identity=(
            _RUN_ELEVATED if task.run_elevated else _RUN_UNELEVATED
        ),
        resource_files=[],
        multi_instance_settings=mis,
        constraints=batchmodels.TaskConstraints(
            retention_time=task.retention_time,
            max_task_retry_count=task.max_task_retries,
            max_wall_clock_time=task.max_wall_time,
        ),
        environment_settings=taskenv,
        output_files=output_files,
    )
    del tc
    if native:
        batchtask.container_settings = batchmodels.TaskContainerSettings(
            container_run_options=' '.join(task.run_options),
            image_name=task.docker_image,
            working_directory=task.working_dir,
        )
    # add additional resource files
    if util.is_not_empty(task.resource_files):
        for rf in task.resource_files:
            batchtask.resource_files.append(
                batchmodels.ResourceFile(
                    file_path=rf.file_path,
                    http_url=rf.blob_source,
                    file_mode=rf.file_mode,
                )
            )
    # add task dependencies
    if (util.is_not_empty(task.depends_on) or
            util.is_not_empty(task.depends_on_range)):
        if util.is_not_empty(task.depends_on_range):
            task_id_ranges = [batchmodels.TaskIdRange(
                start=task.depends_on_range[0], end=task.depends_on_range[1])]
        else:
            task_id_ranges = None
        # need to convert depends_on into python list because it is read
        # from yaml as ruamel.yaml.comments.CommentedSeq. if pickled, this
        # results in an ModuleNotFoundError when loading.
        if util.is_not_empty(task.depends_on):
            task_depends_on = list(task.depends_on)
        else:
            task_depends_on = None
        batchtask.depends_on = batchmodels.TaskDependencies(
            task_ids=task_depends_on,
            task_id_ranges=task_id_ranges,
        )
    # add exit conditions
    if on_task_failure == batchmodels.OnTaskFailure.no_action:
        job_action = None
    else:
        job_action = task.default_exit_options.job_action
    if uses_task_dependencies:
        dependency_action = task.default_exit_options.dependency_action
    else:
        dependency_action = None
    if job_action is not None or dependency_action is not None:
        batchtask.exit_conditions = batchmodels.ExitConditions(
            default=batchmodels.ExitOptions(
                job_action=job_action,
                dependency_action=dependency_action,
            )
        )
    # create task
    if settings.verbose(config):
        if mis is not None:
            logger.debug(
                'multi-instance task coordination command: {}'.format(
                    mis.coordination_command_line))
        logger.debug('task: {} command: {}'.format(
            task.id, batchtask.command_line if native else task.command))
        if native:
            logger.debug('native run options: {}'.format(
                batchtask.container_settings.container_run_options))
    if task.id in task_map:
        raise RuntimeError(
            'duplicate task id detected: {} for job {}'.format(
                task.id, job_id))
    task_map[task.id] = batchtask
    return existing_tasklist, task.id, task_ic, task.gpu, task.infiniband


def _create_auto_scratch_volume(
        batch_client, blob_client, config, pool_id, job_id, shell_script):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,
    #        dict, str, str, tuple) -> None
    """Create auto scratch volume
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param str pool_id: pool id
    :param str job_id: job id
    :param tuple asfile: autoscratch file
    """
    # list jobs in pool and set port offset
    jobs = batch_client.job.list(
        job_list_options=batchmodels.JobListOptions(
            filter='executionInfo/poolId eq \'{}\''.format(pool_id))
    )
    offset = 1000 + 10 * (len(list(jobs)) - 1)
    del jobs
    # upload script
    sas_urls = storage.upload_resource_files(blob_client, [shell_script])
    # get pool current dedicated
    pool = batch_client.pool.get(pool_id)
    if pool.enable_auto_scale:
        logger.warning(
            'auto_scratch is not intended to be used with autoscale '
            'pools: {}'.format(pool_id))
    if pool.current_dedicated_nodes > 0:
        target_nodes = pool.current_dedicated_nodes
        logger.debug(
            'creating auto_scratch on {} number of dedicated nodes on '
            'pool {}'.format(target_nodes, pool_id))
    else:
        target_nodes = pool.current_low_priority_nodes
        logger.debug(
            'creating auto_scratch on {} number of low priority nodes on '
            'pool {}'.format(target_nodes, pool_id))
    if target_nodes == 0:
        raise RuntimeError(
            'Cannot create an auto_scratch volume with no current '
            'dedicated or low priority nodes')
    batchtask = batchmodels.TaskAddParameter(
        id=_AUTOSCRATCH_TASK_ID,
        multi_instance_settings=batchmodels.MultiInstanceSettings(
            number_of_instances=target_nodes,
            coordination_command_line=util.wrap_commands_in_shell([
                '$AZ_BATCH_TASK_DIR/{} setup {}'.format(
                    shell_script[0], job_id)]),
            common_resource_files=[
                batchmodels.ResourceFile(
                    file_path=shell_script[0],
                    http_url=sas_urls[shell_script[0]],
                    file_mode='0755'),
            ],
        ),
        command_line=util.wrap_commands_in_shell([
            '$AZ_BATCH_TASK_DIR/{} start {} {}'.format(
                shell_script[0], job_id, offset)]),
        user_identity=_RUN_ELEVATED,
    )
    # add task
    batch_client.task.add(job_id=job_id, task=batchtask)
    logger.debug(
        'waiting for auto scratch setup task {} in job {} to complete'.format(
            batchtask.id, job_id))
    # wait for beegfs beeond setup task to complete
    while True:
        batchtask = batch_client.task.get(job_id, batchtask.id)
        if batchtask.state == batchmodels.TaskState.completed:
            break
        time.sleep(1)
    if (batchtask.execution_info.result ==
            batchmodels.TaskExecutionResult.failure):
        raise RuntimeError('auto scratch setup failed')
    logger.info(
        'auto scratch setup task {} in job {} completed'.format(
            batchtask.id, job_id))


def add_jobs(
        batch_client, blob_client, table_client, queue_client, keyvault_client,
        config, autopool, jpfile, bxfile, asfile, recreate=False, tail=None,
        federation_id=None):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,
    #        azure.cosmosdb.TableClient, azurequeue.QueueService,
    #        azure.keyvault.KeyVaultClient, dict,
    #        batchmodels.PoolSpecification, tuple, tuple, tuple, bool, str,
    #        str) -> None
    """Add jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_client: queue_client
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param dict config: configuration dict
    :param batchmodels.PoolSpecification autopool: auto pool specification
    :param tuple jpfile: jobprep file
    :param tuple bxfile: blobxfer file
    :param tuple asfile: autoscratch file
    :param bool recreate: recreate job if completed
    :param str tail: tail specified file of last job/task added
    :param str federation_id: federation id
    """
    # check option compatibility
    if util.is_not_empty(federation_id):
        if autopool is not None:
            raise RuntimeError(
                'cannot create an auto-pool job within a federation')
        if recreate:
            raise RuntimeError(
                'cannot recreate a job within a federation')
        if tail is not None:
            raise RuntimeError(
                'cannot tail task output for the specified file within '
                'a federation')
    bs = settings.batch_shipyard_settings(config)
    pool = settings.pool_settings(config)
    native = settings.is_native_docker_pool(
        config, vm_config=pool.vm_configuration)
    is_windows = settings.is_windows_pool(
        config, vm_config=pool.vm_configuration)
    # check pool validity
    try:
        cloud_pool = batch_client.pool.get(pool.id)
    except batchmodels.BatchErrorException as ex:
        if 'The specified pool does not exist' in ex.message.value:
            cloud_pool = None
            if autopool is None and util.is_none_or_empty(federation_id):
                logger.error('{} pool does not exist'.format(pool.id))
                if not util.confirm_action(
                        config,
                        'add jobs to nonexistant pool {}'.format(pool.id)):
                    logger.error(
                        'not submitting jobs to nonexistant pool {}'.format(
                            pool.id))
                    return
        else:
            raise
    # checks for existing pool
    if autopool is None and cloud_pool is not None:
        # ensure pool is active
        if (util.is_none_or_empty(federation_id) and
                cloud_pool.state != batchmodels.PoolState.active):
            logger.error(
                'Cannot submit jobs to pool {} which is not in active '
                'state'.format(pool.id))
            return
        # ensure pool is at least version 3.8.0 as task runner is required
        try:
            _check_metadata_mismatch(
                'pool', cloud_pool.metadata, req_ge='3.8.0')
        except Exception as ex:
            logger.error(
                'Cannot submit jobs against a pool created with a prior '
                'version of Batch Shipyard. Please re-create your pool with '
                'a newer version of Batch Shipyard.')
            raise ex
    if settings.verbose(config):
        task_prog_mod = 1000
    else:
        task_prog_mod = 10000
    # pre-process jobs and tasks
    tempdisk = settings.temp_disk_mountpoint(config)
    docker_images = settings.global_resources_docker_images(config)
    singularity_images = settings.global_resources_singularity_images(config)
    autoscratch_avail = pool.per_job_auto_scratch
    autoscratch_avail = True
    lastjob = None
    lasttaskid = None
    tasksadded = False
    raw_output = {}
    for jobspec in settings.job_specifications(config):
        job_id = settings.job_id(jobspec)
        lastjob = job_id
        # perform checks:
        # 1. check docker images in task against pre-loaded on pool
        # 2. if tasks have exit condition job actions
        # 3. if tasks have dependencies, set it if so
        # 4. if there are multi-instance tasks
        auto_complete = settings.job_auto_complete(jobspec)
        jobschedule = None
        multi_instance = False
        mi_docker_container_name = None
        reserved_task_id = None
        on_task_failure = batchmodels.OnTaskFailure.no_action
        uses_task_dependencies = settings.job_force_enable_task_dependencies(
            jobspec)
        docker_missing_images = []
        singularity_missing_images = []
        allow_run_on_missing = settings.job_allow_run_on_missing(jobspec)
        existing_tasklist = None
        has_merge_task = settings.job_has_merge_task(jobspec)
        max_instance_count_in_job = 0
        instances_required_in_job = 0
        autoscratch_required = settings.job_requires_auto_scratch(jobspec)
        # set federation overrides from constraints
        if util.is_not_empty(federation_id):
            if autoscratch_required:
                raise ValueError(
                    'auto_scratch is incompatible with federations, please '
                    'use glusterfs_on_compute instead')
            fed_constraints = settings.job_federation_constraint_settings(
                jobspec, federation_id)
            if fed_constraints.pool.native is not None:
                native = fed_constraints.pool.native
            if fed_constraints.pool.windows is not None:
                is_windows = fed_constraints.pool.windows
            allow_run_on_missing = True
        else:
            fed_constraints = None
        if settings.verbose(config):
            logger.debug(
                'collating or generating tasks: please be patient, this may '
                'take a while if there is a large volume of tasks or if the '
                'job contains large task_factory specifications')
        ntasks = 0
        for task in settings.job_tasks(config, jobspec):
            ntasks += 1
            if ntasks % task_prog_mod == 0:
                logger.debug('{} tasks collated so far'.format(ntasks))
            # check if task docker image is set in config.json
            di = settings.task_docker_image(task)
            if util.is_not_empty(di) and di not in docker_images:
                if allow_run_on_missing:
                    logger.warning(
                        ('docker image {} not pre-loaded on pool for a '
                         'task specified in job {}').format(di, job_id))
                    docker_missing_images.append(di)
                else:
                    raise RuntimeError(
                        ('not submitting job {} with missing docker image {} '
                         'pre-load on pool {} without job-level '
                         'allow_run_on_missing_image option').format(
                             job_id, di, pool.id))
            si = settings.task_singularity_image(task)
            if util.is_not_empty(si) and si not in singularity_images:
                if allow_run_on_missing:
                    logger.warning(
                        ('singularity image {} not pre-loaded on pool for a '
                         'task specified in job {}').format(si, job_id))
                    singularity_missing_images.append(si)
                else:
                    raise RuntimeError(
                        ('not submitting job {} with missing singularity '
                         'image {} pre-load on pool {} without job-level '
                         'allow_run_on_missing_image option').format(
                             job_id, si, pool.id))
            del di
            del si
            if (on_task_failure != batchmodels.OnTaskFailure.
                    perform_exit_options_job_action and
                    settings.has_task_exit_condition_job_action(
                        jobspec, task)):
                on_task_failure = (
                    batchmodels.OnTaskFailure.perform_exit_options_job_action
                )
            # do not break, check to ensure ids are set on each task if
            # task dependencies are set
            if settings.has_depends_on_task(task) or has_merge_task:
                uses_task_dependencies = True
            if settings.is_multi_instance_task(task):
                if multi_instance and auto_complete:
                    raise ValueError(
                        'cannot specify more than one multi-instance task '
                        'per job with auto completion enabled')
                multi_instance = True
                mi_docker_container_name = settings.task_name(task)
                if util.is_none_or_empty(mi_docker_container_name):
                    _id = settings.task_id(task)
                    if util.is_none_or_empty(_id):
                        existing_tasklist, reserved_task_id = \
                            _generate_next_generic_task_id(
                                batch_client, config, job_id,
                                tasklist=existing_tasklist,
                                federation_id=federation_id)
                        settings.set_task_id(task, reserved_task_id)
                        _id = '{}-{}'.format(job_id, reserved_task_id)
                    settings.set_task_name(task, _id)
                    mi_docker_container_name = settings.task_name(task)
                    del _id
        # define max task retry count constraint for this task if set
        job_constraints = None
        max_task_retries = settings.job_max_task_retries(jobspec)
        max_wall_time = settings.job_max_wall_time(jobspec)
        if max_task_retries is not None or max_wall_time is not None:
            job_constraints = batchmodels.JobConstraints(
                max_task_retry_count=max_task_retries,
                max_wall_clock_time=max_wall_time,
            )
        # construct job prep
        jpcmd = []
        if not native and util.is_none_or_empty(federation_id):
            if len(docker_missing_images) > 0 and allow_run_on_missing:
                # we don't want symmetric difference as we just want to
                # block on pre-loaded images only
                dgr = list(set(docker_images) - set(docker_missing_images))
            else:
                dgr = docker_images
            if len(singularity_missing_images) > 0 and allow_run_on_missing:
                sgr = list(
                    set(singularity_images) - set(singularity_missing_images)
                )
            else:
                sgr = singularity_images
            gr = ''
            if len(dgr) > 0:
                gr = ','.join(dgr)
            gr = '{}#'.format(gr)
            if len(sgr) > 0:
                sgr = [util.singularity_image_name_on_disk(x) for x in sgr]
                gr = '{}{}'.format(gr, ','.join(sgr))
            if util.is_not_empty(gr):
                jpcmd.append('$AZ_BATCH_NODE_STARTUP_DIR/wd/{} "{}"'.format(
                    jpfile[0], gr))
            del dgr
            del sgr
            del gr
        # job prep: digest any input_data
        addlcmds = data.process_input_data(config, bxfile, jobspec)
        if addlcmds is not None:
            if util.is_not_empty(federation_id):
                tfm = 'mcr.microsoft.com/azure-batch/shipyard:{}-cargo'.format(
                    __version__)
                if tfm in addlcmds:
                    raise RuntimeError(
                        'input_data:azure_batch is not supported at the '
                        'job-level for federations')
            jpcmd.append(addlcmds)
        del addlcmds
        user_jp = settings.job_preparation_command(jobspec)
        if user_jp is not None:
            jpcmd.append(user_jp)
        del user_jp
        jptask = None
        if len(jpcmd) > 0:
            jptask = batchmodels.JobPreparationTask(
                command_line=util.wrap_commands_in_shell(
                    jpcmd, windows=is_windows),
                wait_for_success=True,
                user_identity=_RUN_ELEVATED,
                rerun_on_node_reboot_after_success=False,
                environment_settings=[
                    batchmodels.EnvironmentSetting(
                        name='SINGULARITY_CACHEDIR',
                        value=settings.get_singularity_cachedir(config)
                    ),
                    batchmodels.EnvironmentSetting(
                        name='SINGULARITY_SYPGPDIR',
                        value=settings.get_singularity_sypgpdir(config)
                    ),
                ],
            )
        del jpcmd
        # construct job release
        jrtask = None
        jrtaskcmd = []
        if autoscratch_required and autoscratch_avail:
            jrtaskcmd.append(
                '$AZ_BATCH_NODE_ROOT_DIR/workitems/{}/job-1/{}/{} '
                'stop {}'.format(
                    job_id, _AUTOSCRATCH_TASK_ID, asfile[0], job_id)
            )
        if multi_instance and auto_complete and not native:
            jrtaskcmd.extend([
                'docker kill {}'.format(mi_docker_container_name),
                'docker rm -v {}'.format(mi_docker_container_name)
            ])
        user_jr = settings.job_release_command(jobspec)
        if user_jr is not None:
            jrtaskcmd.append(user_jr)
        del user_jr
        if util.is_not_empty(jrtaskcmd):
            jrtask = batchmodels.JobReleaseTask(
                command_line=util.wrap_commands_in_shell(
                    jrtaskcmd, windows=is_windows),
                user_identity=_RUN_ELEVATED,
            )
            # job prep task must exist
            if jptask is None:
                jptask = batchmodels.JobPreparationTask(
                    command_line='echo',
                    wait_for_success=False,
                    user_identity=_RUN_ELEVATED,
                    rerun_on_node_reboot_after_success=False,
                )
        del jrtaskcmd
        # construct pool info
        if autopool is None:
            pool_info = batchmodels.PoolInformation(pool_id=pool.id)
        else:
            autopool_settings = settings.job_auto_pool(jobspec)
            if autopool_settings is None:
                raise ValueError(
                    'auto_pool settings is invalid for job {}'.format(
                        settings.job_id(jobspec)))
            if autopool_settings.pool_lifetime == 'job_schedule':
                autopool_plo = batchmodels.PoolLifetimeOption.job_schedule
            else:
                autopool_plo = batchmodels.PoolLifetimeOption(
                    autopool_settings.pool_lifetime)
            pool_info = batchmodels.PoolInformation(
                auto_pool_specification=batchmodels.AutoPoolSpecification(
                    auto_pool_id_prefix=pool.id,
                    pool_lifetime_option=autopool_plo,
                    keep_alive=autopool_settings.keep_alive,
                    pool=autopool,
                )
            )
        # get base env vars from job
        jevs = settings.job_environment_variables(jobspec)
        _jevs_secid = \
            settings.job_environment_variables_keyvault_secret_id(jobspec)
        if util.is_not_empty(_jevs_secid):
            _jevs = keyvault.get_secret(
                keyvault_client, _jevs_secid, value_is_json=True)
            jevs = util.merge_dict(jevs, _jevs or {})
            del _jevs
        del _jevs_secid
        job_env_vars = []
        for jev in jevs:
            job_env_vars.append(batchmodels.EnvironmentSetting(
                name=jev, value=jevs[jev]))
        # create jobschedule
        recurrence = settings.job_recurrence(jobspec)
        if recurrence is not None:
            if autoscratch_required:
                raise ValueError(
                    'auto_scratch is incompatible with recurrences, please '
                    'use glusterfs_on_compute instead')
            if recurrence.job_manager.monitor_task_completion:
                kill_job_on_completion = True
            else:
                kill_job_on_completion = False
            if auto_complete:
                if kill_job_on_completion:
                    logger.warning(
                        ('overriding monitor_task_completion with '
                         'auto_complete for job schedule {}').format(
                             job_id))
                    kill_job_on_completion = False
                on_all_tasks_complete = (
                    batchmodels.OnAllTasksComplete.terminate_job
                )
            else:
                if not kill_job_on_completion:
                    logger.error(
                        ('recurrence specified for job schedule {}, but '
                         'auto_complete and monitor_task_completion are '
                         'both disabled').format(job_id))
                    if not util.confirm_action(
                            config, 'continue adding job schedule {}'.format(
                                job_id)):
                        continue
                on_all_tasks_complete = (
                    batchmodels.OnAllTasksComplete.no_action
                )
            # check pool settings for kill job on completion
            if (kill_job_on_completion and
                    util.is_none_or_empty(federation_id)):
                if cloud_pool is not None:
                    total_vms = (
                        cloud_pool.current_dedicated_nodes +
                        cloud_pool.current_low_priority_nodes
                        if recurrence.job_manager.allow_low_priority_node
                        else 0
                    )
                    total_slots = cloud_pool.max_tasks_per_node * total_vms
                else:
                    total_vms = (
                        pool.vm_count.dedicated +
                        pool.vm_count.low_priority
                        if recurrence.job_manager.allow_low_priority_node
                        else 0
                    )
                    total_slots = pool.max_tasks_per_node * total_vms
                if total_slots == 1:
                    logger.error(
                        ('Only 1 scheduling slot available which is '
                         'incompatible with the monitor_task_completion '
                         'setting. Please add more nodes to pool {}.').format(
                             pool.id)
                    )
                    if not util.confirm_action(
                            config, 'continue adding job schedule {}'.format(
                                job_id)):
                        continue
            jmimgname = (
                'mcr.microsoft.com/azure-batch/shipyard:{}-cargo'.format(
                    __version__)
            )
            if is_windows:
                jmimgname = '{}-windows'.format(jmimgname)
                jscmdline = (
                    'C:\\batch-shipyard\\recurrent_job_manager.cmd{}'
                ).format(' --monitor' if kill_job_on_completion else '')
            else:
                jscmdline = (
                    '/opt/batch-shipyard/recurrent_job_manager.sh{}'
                ).format(' --monitor' if kill_job_on_completion else '')
            if native:
                jscs = batchmodels.TaskContainerSettings(
                    container_run_options='--rm',
                    image_name=jmimgname)
            else:
                jscs = None
                envfile = '.shipyard.envlist'
                jscmd = [
                    _generate_non_native_env_dump(jevs, envfile),
                ]
                bind = (
                    '-v $AZ_BATCH_TASK_DIR:$AZ_BATCH_TASK_DIR '
                    '-w $AZ_BATCH_TASK_WORKING_DIR'
                )
                jscmd.append(
                    ('docker run --rm --env-file {envfile} {bind} '
                     '{jmimgname} {jscmdline}').format(
                         envfile=envfile, bind=bind, jmimgname=jmimgname,
                         jscmdline=jscmdline)
                )
                jscmdline = util.wrap_commands_in_shell(
                    jscmd, windows=is_windows)
                del bind
                del jscmd
                del envfile
            del jmimgname
            jobschedule = batchmodels.JobScheduleAddParameter(
                id=job_id,
                schedule=batchmodels.Schedule(
                    do_not_run_until=recurrence.schedule.do_not_run_until,
                    do_not_run_after=recurrence.schedule.do_not_run_after,
                    start_window=recurrence.schedule.start_window,
                    recurrence_interval=recurrence.schedule.
                    recurrence_interval,
                ),
                job_specification=batchmodels.JobSpecification(
                    pool_info=pool_info,
                    priority=settings.job_priority(jobspec),
                    uses_task_dependencies=uses_task_dependencies,
                    on_all_tasks_complete=on_all_tasks_complete,
                    on_task_failure=on_task_failure,
                    constraints=job_constraints,
                    job_manager_task=batchmodels.JobManagerTask(
                        id='shipyard-jmtask',
                        command_line=jscmdline,
                        container_settings=jscs,
                        environment_settings=job_env_vars,
                        kill_job_on_completion=kill_job_on_completion,
                        user_identity=_RUN_ELEVATED,
                        run_exclusive=recurrence.job_manager.run_exclusive,
                        authentication_token_settings=batchmodels.
                        AuthenticationTokenSettings(
                            access=[batchmodels.AccessScope.job]),
                        allow_low_priority_node=recurrence.job_manager.
                        allow_low_priority_node,
                        resource_files=[],
                    ),
                    job_preparation_task=jptask,
                    job_release_task=jrtask,
                    metadata=[
                        batchmodels.MetadataItem(
                            name=settings.get_metadata_version_name(),
                            value=__version__,
                        ),
                    ],
                )
            )
            del jscs
            del jscmdline
        del recurrence
        # create job
        if jobschedule is None:
            job = batchmodels.JobAddParameter(
                id=job_id,
                pool_info=pool_info,
                constraints=job_constraints,
                uses_task_dependencies=uses_task_dependencies,
                on_task_failure=on_task_failure,
                job_preparation_task=jptask,
                job_release_task=jrtask,
                common_environment_settings=job_env_vars,
                metadata=[
                    batchmodels.MetadataItem(
                        name=settings.get_metadata_version_name(),
                        value=__version__,
                    ),
                ],
                priority=settings.job_priority(jobspec),
            )
            try:
                if util.is_none_or_empty(federation_id):
                    logger.info('Adding job {} to pool {}'.format(
                        job_id, pool.id))
                    batch_client.job.add(job)
                else:
                    logger.info(
                        'deferring adding job {} for federation {}'.format(
                            job_id, federation_id))
                if settings.verbose(config) and jptask is not None:
                    logger.debug('Job prep command: {}'.format(
                        jptask.command_line))
            except batchmodels.BatchErrorException as ex:
                if ('The specified job is already in a completed state.' in
                        ex.message.value):
                    if recreate:
                        # get job state
                        _job = batch_client.job.get(job_id)
                        if _job.state == batchmodels.JobState.completed:
                            delete_or_terminate_jobs(
                                batch_client, config, True, jobid=job_id,
                                wait=True)
                            time.sleep(1)
                            batch_client.job.add(job)
                    else:
                        raise
                elif 'The specified job already exists' in ex.message.value:
                    # cannot re-use an existing job if multi-instance due to
                    # job release requirement
                    if multi_instance and auto_complete:
                        raise
                    else:
                        # retrieve job and check for version consistency
                        _job = batch_client.job.get(job_id)
                        _check_metadata_mismatch('job', _job.metadata)
                        # check for task dependencies and job actions
                        # compatibility
                        if (uses_task_dependencies and
                                not _job.uses_task_dependencies):
                            raise RuntimeError(
                                ('existing job {} has an incompatible task '
                                 'dependency setting: existing={} '
                                 'desired={}').format(
                                     job_id, _job.uses_task_dependencies,
                                     uses_task_dependencies))
                        if (_job.on_task_failure != on_task_failure):
                            raise RuntimeError(
                                ('existing job {} has an incompatible '
                                 'on_task_failure setting: existing={} '
                                 'desired={}').format(
                                     job_id, _job.on_task_failure.value,
                                     on_task_failure.value))
                        if autoscratch_required:
                            try:
                                _astask = batch_client.task.get(
                                    job_id, _AUTOSCRATCH_TASK_ID)
                                if (_astask.execution_info.result ==
                                        batchmodels.TaskExecutionResult.
                                        success):
                                    autoscratch_required = False
                                else:
                                    raise RuntimeError(
                                        'existing job {} auto-scratch setup '
                                        'task failed'.format(job_id))
                            except batchmodels.BatchErrorException as ex:
                                if ('The specified task does not exist' in
                                        ex.message.value):
                                    raise RuntimeError(
                                        'existing job {} does not have an '
                                        'auto-scratch setup task'.format(
                                            job_id))
                else:
                    raise
            if autoscratch_required and autoscratch_avail:
                _create_auto_scratch_volume(
                    batch_client, blob_client, config, pool.id, job_id, asfile)
        del mi_docker_container_name
        # add all tasks under job
        container_image_refs = set()
        task_map = {}
        has_gpu_task = False
        has_ib_task = False
        logger.debug(
            'constructing {} task specifications for submission '
            'to job {}'.format(ntasks, job_id))
        ntasks = 0
        for _task in settings.job_tasks(config, jobspec):
            ntasks += 1
            if ntasks % task_prog_mod == 0:
                logger.debug('{} tasks constructed so far'.format(ntasks))
            existing_tasklist, lasttaskid, lasttaskic, gpu, ib = \
                _construct_task(
                    batch_client, blob_client, keyvault_client, config,
                    federation_id, bxfile, bs, native, is_windows, tempdisk,
                    allow_run_on_missing, docker_missing_images,
                    singularity_missing_images, cloud_pool,
                    pool, jobspec, job_id, jevs, task_map,
                    existing_tasklist, reserved_task_id, lasttaskid, False,
                    uses_task_dependencies, on_task_failure,
                    container_image_refs, _task
                )
            if not has_gpu_task and gpu:
                has_gpu_task = True
            if not has_ib_task and ib:
                has_ib_task = True
            instances_required_in_job += lasttaskic
            if lasttaskic > max_instance_count_in_job:
                max_instance_count_in_job = lasttaskic
        merge_task_id = None
        if has_merge_task:
            ntasks += 1
            _task = settings.job_merge_task(jobspec)
            existing_tasklist, merge_task_id, lasttaskic, gpu, ib = \
                _construct_task(
                    batch_client, blob_client, keyvault_client, config,
                    federation_id, bxfile, bs, native, is_windows, tempdisk,
                    allow_run_on_missing, docker_missing_images,
                    singularity_missing_images, cloud_pool,
                    pool, jobspec, job_id, jevs, task_map,
                    existing_tasklist, reserved_task_id, lasttaskid, True,
                    uses_task_dependencies, on_task_failure,
                    container_image_refs, _task)
            if not has_gpu_task and gpu:
                has_gpu_task = True
            if not has_ib_task and ib:
                has_ib_task = True
            instances_required_in_job += lasttaskic
            if lasttaskic > max_instance_count_in_job:
                max_instance_count_in_job = lasttaskic
            # set dependencies on merge task
            merge_task = task_map.pop(merge_task_id)
            merge_task.depends_on = batchmodels.TaskDependencies(
                task_ids=list(task_map.keys()),
            )
            # check task_ids len doesn't exceed max
            if len(''.join(merge_task.depends_on.task_ids)) >= 64000:
                raise RuntimeError(
                    ('merge_task dependencies for job {} are too large, '
                     'please limit the the number of tasks').format(job_id))
            # add merge task into map
            task_map[merge_task_id] = merge_task
        logger.debug(
            'submitting {} task specifications to job {}'.format(
                ntasks, job_id))
        del ntasks
        # construct required registries for federation
        registries = construct_registry_list_for_federation(
            config, federation_id, fed_constraints, container_image_refs)
        del container_image_refs
        # submit job schedule if required
        if jobschedule is not None:
            taskmaploc = 'jobschedules/{}/{}'.format(
                job_id, _TASKMAP_PICKLE_FILE)
            # pickle and upload task map
            sas_url = storage.pickle_and_upload(
                blob_client, task_map, taskmaploc, federation_id=federation_id)
            # attach as resource file to jm task
            jobschedule.job_specification.job_manager_task.resource_files.\
                append(
                    batchmodels.ResourceFile(
                        file_path=_TASKMAP_PICKLE_FILE,
                        http_url=sas_url,
                        file_mode='0640',
                    )
                )
            # submit job schedule
            if util.is_none_or_empty(federation_id):
                logger.info('Adding jobschedule {} to pool {}'.format(
                    job_id, pool.id))
                try:
                    batch_client.job_schedule.add(jobschedule)
                except Exception:
                    # delete uploaded task map
                    storage.delete_resource_file(blob_client, taskmaploc)
                    raise
            else:
                if storage.check_if_job_exists_in_federation(
                        table_client, federation_id, jobschedule.id):
                    # do not delete uploaded task map as the existing job
                    # schedule will require it
                    raise RuntimeError(
                        'job schedule {} exists in federation id {}'.format(
                            jobschedule.id, federation_id))
                kind = 'job_schedule'
                unique_id = uuid.uuid4()
                # ensure task dependencies are self-contained
                if uses_task_dependencies:
                    try:
                        task_map = rewrite_task_dependencies_for_federation(
                            table_client, federation_id, jobschedule.id, kind,
                            unique_id, task_map, merge_task_id)
                    except Exception:
                        # delete uploaded task map
                        storage.delete_resource_file(
                            blob_client, taskmaploc,
                            federation_id=federation_id)
                        raise
                    # pickle and re-upload task map
                    sas_url = storage.pickle_and_upload(
                        blob_client, task_map, taskmaploc,
                        federation_id=federation_id)
                logger.debug(
                    'submitting job schedule {} for federation {}'.format(
                        jobschedule.id, federation_id))
                # encapsulate job schedule/task map info in json
                queue_data, jsloc = \
                    generate_info_metadata_for_federation_message(
                        blob_client, config, unique_id, federation_id,
                        fed_constraints, registries, kind, jobschedule.id,
                        jobschedule, native, is_windows, auto_complete,
                        multi_instance, uses_task_dependencies,
                        has_gpu_task, has_ib_task, max_instance_count_in_job,
                        instances_required_in_job, has_merge_task,
                        merge_task_id, task_map
                    )
                # enqueue action to global queue
                logger.debug('enqueuing action {} to federation {}'.format(
                    unique_id, federation_id))
                try:
                    storage.add_job_to_federation(
                        table_client, queue_client, config, federation_id,
                        unique_id, queue_data, kind)
                except Exception:
                    # delete uploaded files
                    storage.delete_resource_file(
                        blob_client, taskmaploc, federation_id=federation_id)
                    storage.delete_resource_file(
                        blob_client, jsloc, federation_id=federation_id)
                    raise
                # add to raw output
                if settings.raw(config):
                    raw_output[jobschedule.id] = {
                        'federation': {
                            'id': federation_id,
                            'storage': {
                                'account': storage.get_storageaccount(),
                                'endpoint':
                                storage.get_storageaccount_endpoint(),
                            },
                        },
                        'kind': kind,
                        'action': 'add',
                        'unique_id': str(unique_id),
                        'tasks_per_recurrence': len(task_map),
                    }
        else:
            # add task collection to job
            if util.is_none_or_empty(federation_id):
                _add_task_collection(batch_client, job_id, task_map)
                # patch job if job autocompletion is needed
                if auto_complete:
                    batch_client.job.patch(
                        job_id=job_id,
                        job_patch_parameter=batchmodels.JobPatchParameter(
                            on_all_tasks_complete=batchmodels.
                            OnAllTasksComplete.terminate_job))
            else:
                if (storage.federation_requires_unique_job_ids(
                        table_client, federation_id) and
                        storage.check_if_job_exists_in_federation(
                            table_client, federation_id, job_id)):
                    raise RuntimeError(
                        'job {} exists in federation id {} requiring unique '
                        'job ids'.format(job_id, federation_id))
                kind = 'job'
                unique_id = uuid.uuid4()
                if uses_task_dependencies:
                    task_map = rewrite_task_dependencies_for_federation(
                        table_client, federation_id, job_id, kind, unique_id,
                        task_map, merge_task_id)
                logger.debug('submitting job {} for federation {}'.format(
                    job_id, federation_id))
                # encapsulate job/task map info in json
                queue_data, jloc = \
                    generate_info_metadata_for_federation_message(
                        blob_client, config, unique_id, federation_id,
                        fed_constraints, registries, kind, job_id, job,
                        native, is_windows, auto_complete, multi_instance,
                        uses_task_dependencies, has_gpu_task,
                        has_ib_task, max_instance_count_in_job,
                        instances_required_in_job, has_merge_task,
                        merge_task_id, task_map
                    )
                # enqueue action to global queue
                logger.debug('enqueuing action {} to federation {}'.format(
                    unique_id, federation_id))
                try:
                    storage.add_job_to_federation(
                        table_client, queue_client, config, federation_id,
                        unique_id, queue_data, kind)
                except Exception:
                    # delete uploaded files
                    storage.delete_resource_file(
                        blob_client, jloc, federation_id=federation_id)
                    raise
                # add to raw output
                if settings.raw(config):
                    raw_output[job_id] = {
                        'federation': {
                            'id': federation_id,
                            'storage': {
                                'account': storage.get_storageaccount(),
                                'endpoint':
                                storage.get_storageaccount_endpoint(),
                            },
                        },
                        'kind': kind,
                        'action': 'add',
                        'unique_id': str(unique_id),
                        'num_tasks': len(task_map),
                    }
        tasksadded = True
    # tail file if specified
    if tail:
        if not tasksadded:
            logger.error('no tasks added, so cannot tail a file')
        elif jobschedule is not None:
            logger.error('cannot tail a file from a jobschedule task')
        else:
            stream_file_and_wait_for_task(
                batch_client, config, filespec='{},{},{}'.format(
                    lastjob, lasttaskid, tail), disk=False)
    # output raw
    if util.is_not_empty(raw_output):
        print(json.dumps(raw_output, indent=4, sort_keys=True))


def generate_info_metadata_for_federation_message(
        blob_client, config, unique_id, federation_id, fed_constraints,
        registries, kind, target, data, native, is_windows, auto_complete,
        multi_instance, uses_task_dependencies, has_gpu_task, has_ib_task,
        max_instance_count_in_job, instances_required_in_job, has_merge_task,
        merge_task_id, task_map):
    info = {
        'version': '1',
        'action': {
            'method': 'add',
            'kind': kind,
        },
        kind: {
            'id': target,
            'data': data,
            'constraints': {
                'pool': {
                    'autoscale': {
                        'allow': fed_constraints.pool.autoscale_allow,
                        'exclusive': fed_constraints.pool.autoscale_exclusive,
                    },
                    'custom_image_arm_id':
                    fed_constraints.pool.custom_image_arm_id,
                    'location': fed_constraints.pool.location,
                    'low_priority_nodes': {
                        'allow': fed_constraints.pool.low_priority_nodes_allow,
                        'exclusive':
                        fed_constraints.pool.low_priority_nodes_exclusive,
                    },
                    'max_active_task_backlog': {
                        'ratio':
                        fed_constraints.pool.max_active_task_backlog_ratio,
                        'autoscale_exempt':
                        fed_constraints.pool.
                        max_active_task_backlog_autoscale_exempt,
                    },
                    'native': native,
                    'registries': registries,
                    'virtual_network_arm_id':
                    fed_constraints.pool.virtual_network_arm_id,
                    'windows': is_windows,
                },
                'compute_node': {
                    'vm_size': fed_constraints.compute_node.vm_size,
                    'cores': {
                        'amount': fed_constraints.compute_node.cores,
                        'schedulable_variance':
                        fed_constraints.compute_node.core_variance,
                    },
                    'memory': {
                        'amount': fed_constraints.compute_node.memory,
                        'schedulable_variance':
                        fed_constraints.compute_node.memory_variance,
                    },
                    'exclusive': fed_constraints.compute_node.exclusive,
                    'gpu': has_gpu_task or fed_constraints.compute_node.gpu,
                    'infiniband': has_ib_task or
                    fed_constraints.compute_node.infiniband,
                },
                'task': {
                    'auto_complete': auto_complete,
                    'has_multi_instance': multi_instance,
                    'has_task_dependencies': uses_task_dependencies,
                    'instance_counts': {
                        'max': max_instance_count_in_job,
                        'total': instances_required_in_job,
                    },
                },
            },
            'task_naming': {
                'prefix': settings.autogenerated_task_id_prefix(config),
                'padding': settings.autogenerated_task_id_zfill(config),
            },
        },
    }
    if kind == 'jobschedule':
        info[kind]['constraints']['task'][
            'tasks_per_recurrence'] = len(task_map)
    elif kind == 'job':
        info['task_map'] = task_map
    if has_merge_task:
        info[kind]['constraints']['task']['merge_task_id'] = merge_task_id
    # pickle json and upload
    loc = 'messages/{}.pickle'.format(unique_id)
    sas_url = storage.pickle_and_upload(
        blob_client, info, loc, federation_id=federation_id)
    # construct queue message
    info = {
        'version': '1',
        'federation_id': federation_id,
        'target': target,
        'blob_data': sas_url,
        'uuid': str(unique_id),
    }
    return info, loc


def construct_registry_list_for_federation(
        config, federation_id, fed_constraints, container_image_refs):
    if util.is_none_or_empty(federation_id):
        return None
    regs = settings.docker_registries(config, images=container_image_refs)
    # find docker hub repos
    dh_repos = set()
    for image in container_image_refs:
        tmp = image.split('/')
        if len(tmp) > 1:
            if '.' in tmp[0] or ':' in tmp[0] and tmp[0] != 'localhost':
                continue
            else:
                dh_repos.add('dockerhub-{}'.format(tmp[0]))
    if fed_constraints.pool.container_registries_private_docker_hub:
        req_regs = list(dh_repos)
    else:
        req_regs = []
    if util.is_not_empty(fed_constraints.pool.container_registries_public):
        pub_exclude = set(fed_constraints.pool.container_registries_public)
    else:
        pub_exclude = set()
    # filter registries according to constraints
    for cr in regs:
        if util.is_none_or_empty(cr.registry_server):
            continue
        else:
            if cr.registry_server not in pub_exclude:
                req_regs.append('{}-{}'.format(
                    cr.registry_server, cr.user_name))
    return req_regs if util.is_not_empty(req_regs) else None


def rewrite_task_dependencies_for_federation(
        table_client, federation_id, job_id, kind, unique_id, task_map,
        merge_task_id):
    # perform validation first
    # 1. no outside dependencies outside of task group
    # 2. for now, disallow task depends_on_range
    # TODO task depends_on range support:
    # - convert depends on range to explicit task depends on
    # 3. ensure the total length of dependencies for each task is less than
    # 64k chars
    ujid_req = storage.federation_requires_unique_job_ids(
        table_client, federation_id)
    uid = str(unique_id)[:8]
    all_tids = list(task_map.keys())
    task_remap = {}
    dep_len = 0
    for tid in task_map:
        if tid == merge_task_id:
            continue
        new_tid = '{}-{}'.format(tid, uid)
        if not ujid_req and len(new_tid) > 64:
            raise RuntimeError(
                'Cannot add unique suffix to task {} in {} {}. Please '
                'shorten the task id to a maximum of 55 characters.'.format(
                    tid, kind, job_id))
        t = task_map[tid]
        if t.depends_on is not None:
            if util.is_not_empty(t.depends_on.task_ids):
                new_dep = []
                for x in t.depends_on.task_ids:
                    if x not in all_tids:
                        raise RuntimeError(
                            '{} {} contains task dependencies not '
                            'self-contained in task group bound for '
                            'federation {}'.format(
                                kind, job_id, federation_id))
                    new_dep.append('{}-{}'.format(x, uid))
                if not ujid_req:
                    t.depends_on = batchmodels.TaskDependencies(
                        task_ids=new_dep
                    )
                    dep_len += len(''.join(new_dep))
            if util.is_not_empty(t.depends_on.task_id_ranges):
                raise RuntimeError(
                    '{} {} contains task dependency ranges, which are not '
                    'supported, bound for federation {}'.format(
                        kind, job_id, federation_id))
        if not ujid_req:
            t.id = new_tid
            task_remap[tid] = t
    # passed self-containment check, can stop here for unique job id
    # federations
    if ujid_req:
        logger.debug(
            'federation {} requires unique job ids, not rewriting task '
            'dependencies for {} {}'.format(federation_id, kind, job_id))
        return task_map
    # remap merge task
    if util.is_not_empty(merge_task_id):
        new_tid = '{}-{}'.format(merge_task_id, uid)
        if len(new_tid) > 64:
            raise RuntimeError(
                'Cannot add unique suffix to merge task {} in {} {}. Please '
                'shorten the task id to a maximum of 55 characters.'.format(
                    tid, kind, job_id))
        t = task_map[merge_task_id]
        t.depends_on = batchmodels.TaskDependencies(
            task_ids=list(task_remap.keys())
        )
        t.id = new_tid
        task_remap[new_tid] = t
        dep_len += len(new_tid)
    # check total dependency length
    if dep_len > 64000:
        raise RuntimeError(
            'Total number of dependencies for {} {} exceeds the maximum '
            'limit.'.format(kind, job_id))
    return task_remap
