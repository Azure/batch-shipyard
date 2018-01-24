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
import collections
import datetime
import fnmatch
import getpass
import logging
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import pickle
import ssl
import tempfile
import time
# non-stdlib imports
import azure.batch.models as batchmodels
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
_MAX_REBOOT_RETRIES = 5
_SSH_TUNNEL_SCRIPT = 'ssh_docker_tunnel_shipyard.sh'
_TASKMAP_PICKLE_FILE = 'taskmap.pickle'
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


def get_batch_account(batch_mgmt_client, config):
    # type: (azure.mgmt.batch.BatchManagementClient, dict) ->
    #        azure.mgmt.batch.models.BatchAccount
    """Get Batch account properties from ARM
    :param azure.mgmt.batch.BatchManagementClient batch_mgmt_client:
        batch management client
    :param dict config: configuration dict
    :rtype: azure.mgmt.batch.models.BatchAccount
    :return: Batch account
    """
    if batch_mgmt_client is None:
        raise RuntimeError(
            'Batch management client is invalid, please specify management '
            'aad credentials')
    bc = settings.credentials_batch(config)
    return batch_mgmt_client.batch_account.get(
        resource_group_name=bc.resource_group,
        account_name=bc.account,
    )


def list_node_agent_skus(batch_client):
    # type: (batch.BatchServiceClient) -> None
    """List all node agent skus
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    """
    node_agent_skus = batch_client.account.list_node_agent_skus()
    for sku in node_agent_skus:
        for img in sku.verified_image_references:
            logger.info(
                'os_type={} publisher={} offer={} sku={} node_agent={}'.format(
                    sku.os_type, img.publisher, img.offer, img.sku, sku.id))


def add_certificate_to_account(batch_client, config, rm_pfxfile=False):
    # type: (batch.BatchServiceClient, dict, bool) -> None
    """Adds a certificate to a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str sha1_cert_tp: sha1 thumbprint of pfx
    :param bool rm_pfxfile: remove PFX file from local disk
    """
    pfx = crypto.get_encryption_pfx_settings(config)
    # first check if this cert exists
    certs = batch_client.certificate.list()
    for cert in certs:
        if cert.thumbprint.lower() == pfx.sha1:
            logger.error(
                'cert with thumbprint {} already exists for account'.format(
                    pfx.sha1))
            # remove pfxfile
            if rm_pfxfile:
                os.unlink(pfx.filename)
            return
    # add cert to account
    if pfx.passphrase is None:
        pfx.passphrase = getpass.getpass('Enter password for PFX: ')
    logger.debug('adding pfx cert with thumbprint {} to account'.format(
        pfx.sha1))
    data = util.base64_encode_string(open(pfx.filename, 'rb').read())
    batch_client.certificate.add(
        certificate=batchmodels.CertificateAddParameter(
            pfx.sha1, 'sha1', data,
            certificate_format=batchmodels.CertificateFormat.pfx,
            password=pfx.passphrase)
    )
    # remove pfxfile
    if rm_pfxfile:
        os.unlink(pfx.filename)


def list_certificates_in_account(batch_client):
    # type: (batch.BatchServiceClient) -> None
    """List all certificates in a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    """
    i = 0
    log = ['list of certificates']
    certs = batch_client.certificate.list()
    for cert in certs:
        if cert.delete_certificate_error is not None:
            ce = '  * delete error: {}: {}'.format(
                cert.delete_certificate_error.code,
                cert.delete_certificate_error.message)
        else:
            ce = '  * no delete errors'
        log.extend([
            '* thumbprint: {}'.format(cert.thumbprint),
            '  * thumbprint algorithm: {}'.format(cert.thumbprint_algorithm),
            '  * state: {}'.format(cert.state),
            ce,
        ])
        i += 1
    if i == 0:
        logger.error('no certificates found')
    else:
        logger.info(os.linesep.join(log))


def del_certificate_from_account(batch_client, config):
    # type: (batch.BatchServiceClient, dict) -> None
    """Delete a certificate from a Batch account
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    pfx = crypto.get_encryption_pfx_settings(config)
    batch_client.certificate.delete('sha1', pfx.sha1)


def _reboot_node(batch_client, pool_id, node_id, wait):
    # type: (batch.BatchServiceClient, str, str, bool) -> None
    """Reboot a node in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str pool_id: pool id of node
    :param str node_id: node id to delete
    :param bool wait: wait for node to enter rebooting state
    """
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
    cascadelog = sep.join(('startup', 'wd', 'cascade.log'))
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
        batch_client, config, stopping_states, end_states, pool_id,
        reboot_on_failed):
    # type: (batch.BatchServiceClient, dict,
    #        List[batchmodels.ComputeNodeState],
    #        List[batchmodels.ComputeNodeState], str,
    #        bool) -> List[batchmodels.ComputeNode]
    """Wait for pool to enter steady state and all nodes to enter stopping
    states
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list stopping_states: list of node states to stop polling
    :param list end_states: list of acceptable end states
    :param str pool_id: pool id
    :param bool reboot_on_failed: reboot node on failed start state
    :rtype: list
    :return: list of nodes
    """
    logger.info(
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
            # attempt reboot if enabled for potentially transient errors
            if reboot_on_failed:
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
                pool_stats(batch_client, config, pool_id=pool_id)
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
            pool_stats(batch_client, config, pool_id=pool_id)
            if pool_settings.attempt_recovery_on_unusable:
                logger.warning(
                    'Unusable nodes detected, deleting unusable nodes')
                del_node(
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
            resize_pool(batch_client, config, wait=False)
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
                     pool.allocation_state,
                     pool.allocation_state_transition_time))
            if len(nodes) <= 3:
                for node in nodes:
                    logger.debug('{}: {}'.format(node.id, node.state))
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


def wait_for_pool_ready(batch_client, config, pool_id, addl_end_states=None):
    # type: (batch.BatchServiceClient, dict, str,
    #        List[batchmodels.ComputeNode]) -> List[batchmodels.ComputeNode]
    """Wait for pool to enter steady state and all nodes in end states
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
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
        batch_client, config, stopping_states, end_states, pool_id,
        settings.pool_settings(config).reboot_on_start_task_failed)
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


def create_pool(batch_client, config, pool):
    # type: (batch.BatchServiceClient, dict, batchmodels.PoolAddParameter) ->
    #        List[batchmodels.ComputeNode]
    """Create pool if not exists
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
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
            raise
        else:
            logger.error('Pool {!r} already exists'.format(pool.id))
    # wait for pool idle
    return wait_for_pool_ready(batch_client, config, pool.id)


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
                username,
                is_admin=True,
                expiry_time=expiry,
                password=rdp_password,
                ssh_public_key=ssh_public_key_data,
            )
        )
    except batchmodels.batch_error.BatchErrorException as ex:
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
    for node in nodes:
        _add_admin_user_to_compute_node(
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
    for node in nodes:
        _add_admin_user_to_compute_node(
            batch_client, pool, node, pool.ssh.username, ssh_pub_key_data,
            None, expiry=expiry)
    # generate tunnel script if requested
    generate_ssh_tunnel_script(batch_client, pool, ssh_priv_key, nodes)


def generate_ssh_tunnel_script(batch_client, pool, ssh_priv_key, nodes):
    # type: (batch.BatchServiceClient, PoolSettings, str,
    #        List[batchmodels.ComputeNode]) -> None
    """Generate SSH tunneling script
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param PoolSettings pool: pool settings
    :param str ssh_priv_key: path to ssh private key
    :param list nodes: list of nodes
    """
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
    if nodes is None or len(list(nodes)) != pool.vm_count:
        nodes = batch_client.compute_node.list(pool.id)
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
        for node in nodes:
            rls = batch_client.compute_node.get_remote_login_settings(
                pool.id, node.id)
            fd.write('nodes[{}]={}\n'.format(i, node.id))
            fd.write('ips[{}]={}\n'.format(i, rls.remote_login_ip_address))
            fd.write('ports[{}]={}\n'.format(i, rls.remote_login_port))
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
    for node in nodes:
        try:
            batch_client.compute_node.delete_user(
                pool.id, node.id, pool.rdp.username)
            logger.debug('deleted user {} from node {}'.format(
                pool.rdp.username, node.id))
        except batchmodels.batch_error.BatchErrorException as ex:
            if 'The node user does not exist' not in ex.message.value:
                raise


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
    for node in nodes:
        try:
            batch_client.compute_node.delete_user(
                pool.id, node.id, pool.ssh.username)
            logger.debug('deleted user {} from node {}'.format(
                pool.ssh.username, node.id))
        except batchmodels.batch_error.BatchErrorException as ex:
            if 'The node user does not exist' not in ex.message.value:
                raise


def list_pools(batch_client):
    # type: (azure.batch.batch_service_client.BatchServiceClient) -> None
    """List pools
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    """
    i = 0
    log = ['list of pools']
    pools = batch_client.pool.list()
    for pool in pools:
        if util.is_not_empty(pool.resize_errors):
            errors = ['  * resize errors:']
            for err in pool.resize_errors:
                errors.append('    * {}: {}'.format(err.code, err.message))
        else:
            errors = ['  * no resize errors']
        entry = [
            '* pool id: {}'.format(pool.id),
            '  * vm size: {}'.format(pool.vm_size),
            '  * state: {}'.format(pool.state),
            '  * allocation state: {}'.format(pool.allocation_state),
        ]
        entry.extend(errors)
        entry.extend([
            '  * vm count:',
            '    * dedicated:',
            '      * current: {}'.format(pool.current_dedicated_nodes),
            '      * target: {}'.format(pool.target_dedicated_nodes),
            '    * low priority:',
            '      * current: {}'.format(pool.current_low_priority_nodes),
            '      * target: {}'.format(pool.target_low_priority_nodes),
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


def resize_pool(batch_client, config, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool) -> list
    """Resize a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
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
            batch_client, config, pool.id,
            addl_end_states=[batchmodels.ComputeNodeState.running])


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
    except batchmodels.batch_error.BatchErrorException as ex:
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
    for md in pool.metadata:
        if md.name == settings.get_metadata_version_name():
            version = md.value
            break
    log = [
        '* Batch Shipyard version: {}'.format(version),
        '* Total nodes: {}'.format(
            pool.current_dedicated_nodes + pool.current_low_priority_nodes
        ),
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
    pool = batch_client.pool.get(pool_id)
    if not pool.enable_auto_scale:
        logger.error(
            ('last execution information not available for autoscale '
             'disabled pool {}').format(pool_id))
        return
    _output_autoscale_result(pool.auto_scale_run)


def reboot_nodes(batch_client, config, all_start_task_failed, node_id):
    # type: (batch.BatchServiceClient, dict, bool, str) -> None
    """Reboot nodes in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool all_start_task_failed: reboot all start task failed nodes
    :param str node_id: node id to delete
    """
    pool_id = settings.pool_id(config)
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
            _reboot_node(batch_client, pool_id, node.id, False)
    else:
        _reboot_node(batch_client, pool_id, node_id, False)


def del_node(
        batch_client, config, all_start_task_failed, all_starting,
        all_unusable, node_id, suppress_confirm=False):
    # type: (batch.BatchServiceClient, dict, bool, bool, bool, str,
    #        bool) -> None
    """Delete a node in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool all_start_task_failed: delete all start task failed nodes
    :param bool all_starting: delete all starting nodes
    :param bool all_unusable: delete all unusable nodes
    :param str node_id: node id to delete
    :param bool suppress_confirm: suppress confirm ask
    """
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
        if util.is_none_or_empty(node_id):
            raise ValueError('node id is invalid')
        if suppress_confirm or util.confirm_action(
                config, 'delete node {} from {} pool'.format(
                    node_id, pool_id)):
            node_ids.append(node_id)
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
        except batchmodels.batch_error.BatchErrorException as ex:
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
    task_counts = batchmodels.TaskCounts(0, 0, 0, 0, 0, 'validated')
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
        if (tc.validation_status !=
                batchmodels.TaskCountValidationStatus.validated):
            task_counts.validation_status = tc.validation_status
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
        '* Total tasks: {} ({})'.format(
            total_tasks, task_counts.validation_status
        ),
        '  * Active: {}'.format(task_counts.active),
        '  * Running: {}'.format(task_counts.running),
        '  * Completed: {}'.format(task_counts.completed),
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
        except batchmodels.batch_error.BatchErrorException as ex:
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
        except batchmodels.batch_error.BatchErrorException as ex:
            if 'completed state.' in ex.message.value:
                pass
        else:
            logger.info('{} {} enabled'.format(text, job_id))


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
        for task in tasks:
            if not util.confirm_action(
                    config, 'delete {} task in job {}'.format(
                        task, job_id)):
                nocheck[job_id].add(task)
                continue
            logger.info('Deleting task: {}'.format(task))
            batch_client.task.delete(job_id, task)
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
            for task in tasks:
                try:
                    if task in nocheck[job_id]:
                        continue
                except KeyError:
                    pass
                try:
                    logger.debug(
                        'waiting for task {} in job {} to terminate'.format(
                            task, job_id))
                    while True:
                        batch_client.task.get(
                            job_id, task,
                            task_get_options=batchmodels.TaskGetOptions(
                                select='id')
                        )
                        time.sleep(1)
                except batchmodels.batch_error.BatchErrorException as ex:
                    if 'The specified task does not exist' in ex.message.value:
                        logger.info('task {} in job {} does not exist'.format(
                            task, job_id))
                        continue
                    else:
                        raise


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
        except batchmodels.batch_error.BatchErrorException as ex:
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
        except batchmodels.batch_error.BatchErrorException:
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
        except batchmodels.batch_error.BatchErrorException as ex:
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
            except batchmodels.batch_error.BatchErrorException as ex:
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
        except batchmodels.batch_error.BatchErrorException as ex:
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
            except batchmodels.batch_error.BatchErrorException as ex:
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
        except batchmodels.batch_error.BatchErrorException as ex:
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
            except batchmodels.batch_error.BatchErrorException as ex:
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
            'cannot terminate non-native Docker container without an SSH '
            'username')
    if not ssh_private_key.exists():
        raise RuntimeError(
            ('cannot terminate non-native Docker container with a '
             'non-existent SSH private key: {}').format(
                 ssh_private_key))
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
        ssh_private_key = pool.ssh.ssh_private_key
        if ssh_private_key is None:
            ssh_private_key = pathlib.Path(
                pool.ssh.generated_file_export_path,
                crypto.get_ssh_key_prefix())
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
        for task in tasks:
            _task = batch_client.task.get(job_id, task)
            # if completed, skip
            if (_task.state == batchmodels.TaskState.completed and
                    (not force or native)):
                logger.debug(
                    'Skipping termination of completed task {} on '
                    'job {}'.format(task, job_id))
                nocheck[job_id].add(task)
                continue
            if not util.confirm_action(
                    config, 'terminate {} task in job {}'.format(
                        task, job_id)):
                nocheck[job_id].add(task)
                continue
            logger.info('Terminating task: {}'.format(task))
            # directly send docker kill signal if running
            if (not native and
                    (_task.state == batchmodels.TaskState.running or force)):
                # check if task is a docker task
                if ('docker run' in _task.command_line or
                        'docker exec' in _task.command_line):
                    if (_task.multi_instance_settings is not None and
                            _task.multi_instance_settings.
                            number_of_instances > 1):
                        task_is_mi = True
                    else:
                        task_is_mi = False
                    _send_docker_kill_signal(
                        batch_client, config, pool.ssh.username,
                        ssh_private_key, _task.node_info.pool_id,
                        _task.node_info.node_id, job_id, task, task_is_mi)
                else:
                    batch_client.task.terminate(job_id, task)
            else:
                batch_client.task.terminate(job_id, task)
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
            for task in tasks:
                try:
                    if task in nocheck[job_id]:
                        continue
                except KeyError:
                    pass
                try:
                    logger.debug(
                        'waiting for task {} in job {} to terminate'.format(
                            task, job_id))
                    while True:
                        _task = batch_client.task.get(
                            job_id, task,
                            task_get_options=batchmodels.TaskGetOptions(
                                select='state')
                        )
                        if _task.state == batchmodels.TaskState.completed:
                            break
                        time.sleep(1)
                except batchmodels.batch_error.BatchErrorException as ex:
                    if ('The specified task does not exist'
                            not in ex.message.value):
                        raise


def list_nodes(batch_client, config, pool_id=None, nodes=None):
    # type: (batch.BatchServiceClient, dict, str, list) -> None
    """Get a list of nodes
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str pool_id: pool id
    :param list nodes: list of nodes
    """
    if util.is_none_or_empty(pool_id):
        pool_id = settings.pool_id(config)
    log = ['compute nodes for pool {}'.format(pool_id)]
    if nodes is None:
        nodes = batch_client.compute_node.list(pool_id)
    i = 0
    for node in nodes:
        i += 1
        errors = ['  * errors:']
        if node.errors is not None:
            for err in node.errors:
                errors.append('    * {}: {}'.format(err.code, err.message))
        else:
            errors = ['  * no errors']
        st = ['  * start task:']
        if node.start_task_info is not None:
            if node.start_task_info.failure_info is not None:
                st.append(
                    '    * failure info: {}, {}: {}'.format(
                        node.start_task_info.failure_info.category,
                        node.start_task_info.failure_info.code,
                        node.start_task_info.failure_info.message
                    )
                )
            else:
                if node.start_task_info.end_time is not None:
                    duration = (
                        node.start_task_info.end_time -
                        node.start_task_info.start_time
                    )
                else:
                    duration = 'n/a'
                st.extend([
                    '    * exit code: {}'.format(
                        node.start_task_info.exit_code),
                    '    * started: {}'.format(
                        node.start_task_info.start_time),
                    '    * completed: {}'.format(
                        node.start_task_info.end_time),
                    '    * duration: {}'.format(duration),
                ])
        else:
            st = ['  * no start task info']
        entry = [
            '* node id: {}'.format(node.id),
            '  * state: {}'.format(node.state),
            '  * scheduling state: {}'.format(node.scheduling_state),
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
        logger.error('no nodes exist for pool {}'.format(pool_id))
    else:
        logger.info(os.linesep.join(log))


def get_remote_login_settings(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict, List[str]) -> dict
    """Get remote login settings
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    :rtype: dict
    :return: dict of node id -> remote login settings
    """
    pool_id = settings.pool_id(config)
    if nodes is None:
        nodes = batch_client.compute_node.list(pool_id)
    ret = {}
    for node in nodes:
        rls = batch_client.compute_node.get_remote_login_settings(
            pool_id, node.id)
        logger.info('node {}: ip {} port {}'.format(
            node.id, rls.remote_login_ip_address, rls.remote_login_port))
        ret[node.id] = rls
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
        while True:
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
            if curr < size:
                frag = batch_client.file.get_from_task(
                    job_id, task_id, file,
                    batchmodels.FileGetFromTaskOptions(
                        ocp_range='bytes={}-{}'.format(curr, size))
                )
                for f in frag:
                    if fd is not None:
                        fd.write(f)
                    else:
                        print(f.decode('utf8'), end='')
                curr = size
            elif completed:
                if not disk:
                    print()
                break
            if not completed and curr == size:
                task = batch_client.task.get(
                    job_id, task_id,
                    task_get_options=batchmodels.TaskGetOptions(
                        select='state')
                )
                if task.state == batchmodels.TaskState.completed:
                    completed = True
            time.sleep(1)
    finally:
        if fd is not None:
            fd.close()


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
    stream = batch_client.file.get_from_task(job_id, task_id, file)
    with fp.open('wb') as f:
        for fdata in stream:
            f.write(fdata)
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
    files = batch_client.file.list_from_task(job_id, task_id, recursive=True)
    i = 0
    dirs_created = set('.')
    for file in files:
        if file.is_directory:
            continue
        if incl is not None and not fnmatch.fnmatch(file.name, incl):
            continue
        fp = pathlib.Path(job_id, task_id, file.name)
        if str(fp.parent) not in dirs_created:
            fp.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            dirs_created.add(str(fp.parent))
        stream = batch_client.file.get_from_task(job_id, task_id, file.name)
        with fp.open('wb') as f:
            for fdata in stream:
                f.write(fdata)
        i += 1
    if i == 0:
        logger.error('no files found for task {} job {} include={}'.format(
            task_id, job_id, incl if incl is not None else ''))
    else:
        logger.info(
            'all task files retrieved from job={} task={} include={}'.format(
                job_id, task_id, incl if incl is not None else ''))


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
    files = batch_client.file.list_from_compute_node(
        pool_id, node_id, recursive=True)
    i = 0
    dirs_created = set('.')
    for file in files:
        if file.is_directory:
            continue
        if incl is not None and not fnmatch.fnmatch(file.name, incl):
            continue
        fp = pathlib.Path(pool_id, node_id, file.name)
        if str(fp.parent) not in dirs_created:
            fp.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            dirs_created.add(str(fp.parent))
        stream = batch_client.file.get_from_compute_node(
            pool_id, node_id, file.name)
        with fp.open('wb') as f:
            for fdata in stream:
                f.write(fdata)
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
    stream = batch_client.file.get_from_compute_node(pool_id, node_id, file)
    with fp.open('wb') as f:
        for fdata in stream:
            f.write(fdata)
    logger.debug('file {} retrieved from pool={} node={} bytes={}'.format(
        file, pool_id, node_id, fp.stat().st_size))


def list_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """List all jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    jobs = batch_client.job.list()
    log = ['list of jobs:']
    i = 0
    for job in jobs:
        if job.execution_info.end_time is not None:
            duration = (
                job.execution_info.end_time - job.execution_info.start_time
            )
        else:
            duration = 'n/a'
        log.extend([
            '* job id: {}'.format(job.id),
            '  * state: {}'.format(job.state),
            '  * pool id: {}'.format(job.pool_info.pool_id),
            '  * started: {}'.format(job.execution_info.start_time),
            '  * completed: {}'.format(job.execution_info.end_time),
            '  * duration: {}'.format(duration),
        ])
        i += 1
    if i == 0:
        logger.error('no jobs found')
    else:
        logger.info(os.linesep.join(log))
    i = 0
    log = ['list of job schedules:']
    jobschedules = batch_client.job_schedule.list()
    for js in jobschedules:
        log.extend([
            '* job schedule id: {}'.format(js.id),
            '  * state: {}'.format(js.state),
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
        ])
        i += 1
    if i == 0:
        logger.error('no job schedules found')
    else:
        logger.info(os.linesep.join(log))


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
    for job in jobs:
        if all:
            jobid = job.id
        else:
            jobid = settings.job_id(job)
        log = ['list of tasks for job {}'.format(jobid)]
        i = 0
        try:
            tasks = batch_client.task.list(jobid)
            for task in tasks:
                fi = None
                if task.execution_info is not None:
                    if task.execution_info.failure_info is not None:
                        fi = '    * failure info: {}, {}: {}'.format(
                            task.execution_info.failure_info.category,
                            task.execution_info.failure_info.code,
                            task.execution_info.failure_info.message)
                    if (task.execution_info.end_time is not None and
                            task.execution_info.start_time is not None):
                        duration = (task.execution_info.end_time -
                                    task.execution_info.start_time)
                    else:
                        duration = 'n/a'
                log.extend([
                    '* task id: {}'.format(task.id),
                    '  * job id: {}'.format(jobid),
                    '  * state: {}'.format(task.state),
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
                    '    * exit code: {}'.format(
                        task.execution_info.exit_code
                        if task.execution_info is not None else 'n/a'),
                ])
                if fi is not None:
                    log.append(fi)
                if task.state != batchmodels.TaskState.completed:
                    all_complete = False
                i += 1
        except batchmodels.batch_error.BatchErrorException as ex:
            if 'The specified job does not exist' in ex.message.value:
                logger.error('{} job does not exist'.format(jobid))
                continue
            else:
                raise
        if i == 0:
            logger.error('no tasks found for job {}'.format(jobid))
        else:
            logger.info(os.linesep.join(log))
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
        except batchmodels.batch_error.BatchErrorException as ex:
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
                batchmodels.EnvironmentSetting('DOCKER_LOGIN_SERVER', value)
            )
        value = ','.join(docker_users)
        if for_ssh:
            cmd.append('export DOCKER_LOGIN_USERNAME={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting('DOCKER_LOGIN_USERNAME', value)
            )
        value = ','.join(docker_passwords)
        if for_ssh:
            cmd.append('export DOCKER_LOGIN_PASSWORD={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    'DOCKER_LOGIN_PASSWORD',
                    crypto.encrypt_string(encrypt, value, config))
            )
    if len(singularity_servers) > 0:
        # create either cmd or env for each
        value = ','.join(singularity_servers)
        if for_ssh:
            cmd.append('export SINGULARITY_LOGIN_SERVER={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    'SINGULARITY_LOGIN_SERVER', value)
            )
        value = ','.join(singularity_users)
        if for_ssh:
            cmd.append('export SINGULARITY_LOGIN_USERNAME={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    'SINGULARITY_LOGIN_USERNAME', value)
            )
        value = ','.join(singularity_passwords)
        if for_ssh:
            cmd.append('export SINGULARITY_LOGIN_PASSWORD={}'.format(value))
        else:
            env.append(
                batchmodels.EnvironmentSetting(
                    'SINGULARITY_LOGIN_PASSWORD',
                    crypto.encrypt_string(encrypt, value, config))
            )
        # if ssh append script execution
        if for_ssh:
            env = None
            start_mnt = '/'.join((
                settings.temp_disk_mountpoint(config),
                'batch', 'tasks', 'startup',
            ))
            cmd.append('cd {}/wd'.format(start_mnt))
            cmd.append('./registry_login.sh{}'.format(
                ' -e' if encrypt else ''))
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
        task_map=None, last_task_id=None, is_merge_task=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict, str,
    #        list, str, dict, str, bool) -> Tuple[list, str]
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
    :rtype: tuple
    :return: (list of committed task ids for job, next generic docker task id)
    """
    # get prefix and padding settings
    prefix = settings.autogenerated_task_id_prefix(config)
    if is_merge_task:
        prefix = 'merge-{}'.format(prefix)
    padding = settings.autogenerated_task_id_zfill(config)
    delimiter = prefix if util.is_not_empty(prefix) else ' '
    # get filtered, sorted list of generic docker task ids
    try:
        if util.is_none_or_empty(tasklist):
            tasklist = batch_client.task.list(
                job_id,
                task_list_options=batchmodels.TaskListOptions(
                    filter='startswith(id, \'{}\')'.format(prefix)
                    if util.is_not_empty(prefix) else None,
                    select='id'))
            tasklist = list(tasklist)
        tasknum = sorted(
            [int(x.id.split(delimiter)[-1]) for x in tasklist])[-1] + 1
    except (batchmodels.batch_error.BatchErrorException, IndexError,
            TypeError):
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


def _add_task_collection(batch_client, job_id, task_map):
    # type: (batch.BatchServiceClient, str, dict) -> None
    """Add a collection of tasks to a job
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job to add to
    :param dict task_map: task collection map to add
    """
    all_tasks = list(task_map.values())
    start = 0
    slice = 100  # can only submit up to 100 tasks at a time
    while True:
        end = start + slice
        if end > len(all_tasks):
            end = len(all_tasks)
        chunk = all_tasks[start:end]
        logger.debug('submitting {} tasks ({} -> {}) to job {}'.format(
            len(chunk), start, end - 1, job_id))
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
                        logger.error(
                            ('skipping retry of adding task {} as it '
                             'returned a client error (code={} message={}) '
                             'for job {}').format(
                                 result.task_id, result.error.code,
                                 result.error.message, job_id))
                    elif (result.status ==
                          batchmodels.TaskAddStatus.server_error):
                        retry.append(task_map[result.task_id])
                if len(retry) > 0:
                    logger.debug('retrying adding {} tasks to job {}'.format(
                        len(retry), job_id))
                    results = batch_client.task.add_collection(job_id, retry)
                else:
                    break
        if end == len(all_tasks):
            break
        start += slice
        slice = 100
    logger.info('submitted all {} tasks to job {}'.format(
        len(task_map), job_id))


def _construct_task(
        batch_client, blob_client, keyvault_client, config, bxfile,
        bs, native, is_windows, tempdisk, allow_run_on_missing,
        docker_missing_images, singularity_missing_images, cloud_pool,
        pool, jobspec, job_id, job_env_vars, task_map, existing_tasklist,
        reserved_task_id, lasttaskid, is_merge_task, _task):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,
    #        azure.keyvault.KeyVaultClient, dict, tuple,
    #        settings.BatchShipyardSettings, bool, bool, str, bool,
    #        list, list, batchmodels.CloudPool, settings.PoolSettings,
    #        dict, str, dict, dict, list, str, str, bool, dict) -> str
    """Contruct a Batch task and add it to the task map
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param dict config: configuration dict
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
    :param dict _task: task spec
    :rtype: str
    :return: task id added to task map
    """
    _task_id = settings.task_id(_task)
    if util.is_none_or_empty(_task_id):
        existing_tasklist, _task_id = _generate_next_generic_task_id(
            batch_client, config, job_id, tasklist=existing_tasklist,
            reserved=reserved_task_id, task_map=task_map,
            last_task_id=lasttaskid, is_merge_task=is_merge_task)
        settings.set_task_id(_task, _task_id)
    if util.is_none_or_empty(settings.task_name(_task)):
        settings.set_task_name(_task, '{}-{}'.format(job_id, _task_id))
    del _task_id
    task = settings.task_settings(
        cloud_pool, config, pool, jobspec, _task)
    is_singularity = util.is_not_empty(task.singularity_image)
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
    # get and create env var file
    sas_urls = None
    if util.is_not_empty(env_vars) or task.infiniband or task.gpu:
        envfileloc = '{}taskrf-{}/{}{}'.format(
            bs.storage_entity_prefix, job_id, task.id, task.envfile)
        f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        fname = f.name
        try:
            if util.is_not_empty(env_vars):
                for key in env_vars:
                    f.write('{}={}\n'.format(
                        key, env_vars[key]).encode('utf8'))
            if task.infiniband:
                ib_env = {
                    'I_MPI_FABRICS': 'shm:dapl',
                    'I_MPI_DAPL_PROVIDER': 'ofa-v2-ib0',
                    'I_MPI_DYNAMIC_CONNECTION': '0',
                    # create a manpath entry for potentially buggy
                    # intel mpivars.sh
                    'MANPATH': '/usr/share/man:/usr/local/man',
                }
                for key in ib_env:
                    f.write('{}={}\n'.format(key, ib_env[key]).encode('utf8'))
            if task.gpu:
                gpu_env = {
                    'CUDA_CACHE_DISABLE': '0',
                    'CUDA_CACHE_MAXSIZE': '1073741824',
                    # use absolute path due to non-expansion
                    'CUDA_CACHE_PATH': (
                        '{}/batch/tasks/.nv/ComputeCache').format(tempdisk),
                }
                for key in gpu_env:
                    f.write('{}={}\n'.format(key, gpu_env[key]).encode('utf8'))
            # close and upload env var file
            f.close()
            if not native and not is_singularity:
                sas_urls = storage.upload_resource_files(
                    blob_client, config, [(envfileloc, fname)])
        finally:
            os.unlink(fname)
            del f
            del fname
        if not native and not is_singularity and len(sas_urls) != 1:
            raise RuntimeError('unexpected number of sas urls')
    taskenv = []
    # check if this is a multi-instance task
    mis = None
    if settings.is_multi_instance_task(_task):
        if util.is_not_empty(task.multi_instance.coordination_command):
            cc = util.wrap_commands_in_shell(
                task.multi_instance.coordination_command,
                windows=is_windows, wait=False)
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
        del cc
        # add common resource files for multi-instance
        if util.is_not_empty(task.multi_instance.resource_files):
            for rf in task.multi_instance.resource_files:
                mis.common_resource_files.append(
                    batchmodels.ResourceFile(
                        file_path=rf.file_path,
                        blob_source=rf.blob_source,
                        file_mode=rf.file_mode,
                    )
                )
        # set application command
        if native:
            task_commands = [task.command]
        elif is_singularity:
            # add env vars
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    'SHIPYARD_SINGULARITY_COMMAND',
                    'singularity {} {} {}'.format(
                        task.singularity_cmd,
                        ' '.join(task.run_options),
                        task.singularity_image,
                    )
                )
            )
            # singularity command is passed as-is for multi-instance
            task_commands = [
                '{}'.format(' ' + task.command) if task.command else ''
            ]
        else:
            task_commands = [
                '{} {} {} {}'.format(
                    task.docker_exec_cmd,
                    ' '.join(task.docker_exec_options),
                    task.name,
                    task.command,
                )
            ]
    else:
        if native:
            task_commands = [
                '{}'.format(' ' + task.command) if task.command else ''
            ]
        elif is_singularity:
            task_commands = [
                'singularity {} {} {}{}'.format(
                    task.singularity_cmd,
                    ' '.join(task.run_options),
                    task.singularity_image,
                    '{}'.format(' ' + task.command) if task.command else '',
                )
            ]
        else:
            if is_windows:
                envgrep = 'set | findstr AZ_BATCH_ >> {}'.format(task.envfile)
            else:
                envgrep = 'env | grep AZ_BATCH_ >> {}'.format(task.envfile)
            task_commands = [
                envgrep,
                '{} {} {}{}'.format(
                    task.docker_run_cmd,
                    ' '.join(task.run_options),
                    task.docker_image,
                    '{}'.format(' ' + task.command) if task.command else '')
            ]
            del envgrep
    output_files = None
    # get registry login if missing images
    if (not native and allow_run_on_missing and
            (len(docker_missing_images) > 0 or
             len(singularity_missing_images) > 0)):
        taskenv, logincmd = generate_docker_login_settings(config)
        logincmd.extend(task_commands)
        task_commands = logincmd
    # digest any input_data
    addlcmds = data.process_input_data(config, bxfile, _task, on_task=True)
    if addlcmds is not None:
        if native:
            raise RuntimeError(
                'input_data at task-level is not supported on '
                'native container pools')
        task_commands.insert(0, addlcmds)
    # digest any output data
    addlcmds = data.process_output_data(config, bxfile, _task)
    if addlcmds is not None:
        if native:
            output_files = addlcmds
        else:
            task_commands.append(addlcmds)
    del addlcmds
    # set environment variables for native
    if native or is_singularity:
        if util.is_not_empty(env_vars):
            for key in env_vars:
                taskenv.append(
                    batchmodels.EnvironmentSetting(key, env_vars[key])
                )
        if task.infiniband:
            for key in ib_env:
                taskenv.append(
                    batchmodels.EnvironmentSetting(key, ib_env[key])
                )
            del ib_env
        # add singularity only vars
        if is_singularity:
            taskenv.append(
                batchmodels.EnvironmentSetting(
                    'SINGULARITY_CACHEDIR',
                    settings.get_singularity_cachedir(config)
                )
            )
            if task.gpu:
                for key in gpu_env:
                    taskenv.append(
                        batchmodels.EnvironmentSetting(key, gpu_env[key])
                    )
                del gpu_env
    del env_vars
    # create task
    if util.is_not_empty(task_commands):
        tc = util.wrap_commands_in_shell(task_commands, windows=is_windows)
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
            image_name=task.docker_image)
    # add envfile
    if sas_urls is not None:
        batchtask.resource_files.append(
            batchmodels.ResourceFile(
                file_path=str(task.envfile),
                blob_source=next(iter(sas_urls.values())),
                file_mode='0640',
            )
        )
        sas_urls = None
    # add additional resource files
    if util.is_not_empty(task.resource_files):
        for rf in task.resource_files:
            batchtask.resource_files.append(
                batchmodels.ResourceFile(
                    file_path=rf.file_path,
                    blob_source=rf.blob_source,
                    file_mode=rf.file_mode,
                )
            )
    # add task dependencies
    if (util.is_not_empty(task.depends_on) or
            util.is_not_empty(task.depends_on_range)):
        if util.is_not_empty(task.depends_on_range):
            task_id_ranges = [batchmodels.TaskIdRange(
                task.depends_on_range[0], task.depends_on_range[1])]
        else:
            task_id_ranges = None
        batchtask.depends_on = batchmodels.TaskDependencies(
            task_ids=task.depends_on,
            task_id_ranges=task_id_ranges,
        )
    # create task
    if settings.verbose(config):
        if mis is not None:
            logger.debug(
                'multi-instance task coordination command: {}'.format(
                    mis.coordination_command_line))
        logger.debug('task: {} command: {}'.format(
            task.id, batchtask.command_line))
        if native:
            logger.debug('native run options: {}'.format(
                batchtask.container_settings.container_run_options))
    if task.id in task_map:
        raise RuntimeError(
            'duplicate task id detected: {} for job {}'.format(
                task.id, job_id))
    task_map[task.id] = batchtask
    return task.id


def add_jobs(
        batch_client, blob_client, keyvault_client, config, autopool, jpfile,
        bxfile, recreate=False, tail=None):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,
    #        azure.keyvault.KeyVaultClient, dict,
    #        batchmodels.PoolSpecification, tuple, tuple, bool, str) -> None
    """Add jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param dict config: configuration dict
    :param batchmodels.PoolSpecification autopool: auto pool specification
    :param tuple jpfile: jobprep file
    :param tuple bxfile: blobxfer file
    :param bool recreate: recreate job if completed
    :param str tail: tail specified file of last job/task added
    """
    # get the pool inter-node comm setting
    bs = settings.batch_shipyard_settings(config)
    pool = settings.pool_settings(config)
    native = settings.is_native_docker_pool(
        config, vm_config=pool.vm_configuration)
    is_windows = settings.is_windows_pool(
        config, vm_config=pool.vm_configuration)
    try:
        cloud_pool = batch_client.pool.get(pool.id)
    except batchmodels.batch_error.BatchErrorException as ex:
        if 'The specified pool does not exist' in ex.message.value:
            cloud_pool = None
            if autopool is None:
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
    tempdisk = settings.temp_disk_mountpoint(config)
    docker_images = settings.global_resources_docker_images(config)
    singularity_images = settings.global_resources_singularity_images(config)
    lastjob = None
    lasttaskid = None
    jobschedule = None
    tasksadded = False
    for jobspec in settings.job_specifications(config):
        job_id = settings.job_id(jobspec)
        lastjob = job_id
        # perform checks:
        # 1. check docker images in task against pre-loaded on pool
        # 2. if tasks have dependencies, set it if so
        # 3. if there are multi-instance tasks
        auto_complete = settings.job_auto_complete(jobspec)
        multi_instance = False
        mi_docker_container_name = None
        reserved_task_id = None
        uses_task_dependencies = False
        docker_missing_images = []
        singularity_missing_images = []
        allow_run_on_missing = settings.job_allow_run_on_missing(jobspec)
        existing_tasklist = None
        has_merge_task = settings.job_has_merge_task(jobspec)
        for task in settings.job_tasks(config, jobspec):
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
                                tasklist=existing_tasklist)
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
        if not native:
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
            jpcmd.append(addlcmds)
        del addlcmds
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
                        'SINGULARITY_CACHEDIR',
                        settings.get_singularity_cachedir(config)
                    ),
                ],
            )
        del jpcmd
        # construct job release for multi-instance auto-complete
        jrtask = None
        if multi_instance and auto_complete and not native:
            jrtask = batchmodels.JobReleaseTask(
                command_line=util.wrap_commands_in_shell(
                    ['docker kill {}'.format(mi_docker_container_name),
                     'docker rm -v {}'.format(mi_docker_container_name)],
                    windows=is_windows),
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
        # create jobschedule
        recurrence = settings.job_recurrence(jobspec)
        if recurrence is not None:
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
            if kill_job_on_completion:
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
            jmimgname = 'alfpark/batch-shipyard:{}-cargo'.format(__version__)
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
                if is_windows:
                    envgrep = (
                        'set | findstr AZ_BATCH_ >> .shipyard-jmtask.envlist'
                    )
                    bind = (
                        '-v %AZ_BATCH_TASK_DIR%:%AZ_BATCH_TASK_DIR% '
                        '-w %AZ_BATCH_TASK_WORKING_DIR%'
                    )
                else:
                    envgrep = (
                        'env | grep AZ_BATCH_ >> .shipyard-jmtask.envlist'
                    )
                    bind = (
                        '-v $AZ_BATCH_TASK_DIR:$AZ_BATCH_TASK_DIR '
                        '-w $AZ_BATCH_TASK_WORKING_DIR'
                    )
                jscmdline = util.wrap_commands_in_shell([
                    envgrep,
                    ('docker run --rm --env-file .shipyard-jmtask.envlist '
                     '{bind} {jmimgname} {jscmdline}').format(
                         bind=bind, jmimgname=jmimgname, jscmdline=jscmdline)
                ], windows=is_windows)
                del bind
                del envgrep
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
                    constraints=job_constraints,
                    job_manager_task=batchmodels.JobManagerTask(
                        id='shipyard-jmtask',
                        command_line=jscmdline,
                        container_settings=jscs,
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
        else:
            jobschedule = None
        del recurrence
        # create job
        if jobschedule is None:
            job = batchmodels.JobAddParameter(
                id=job_id,
                pool_info=pool_info,
                constraints=job_constraints,
                uses_task_dependencies=uses_task_dependencies,
                job_preparation_task=jptask,
                job_release_task=jrtask,
                metadata=[
                    batchmodels.MetadataItem(
                        name=settings.get_metadata_version_name(),
                        value=__version__,
                    ),
                ],
                priority=settings.job_priority(jobspec),
            )
            logger.info('Adding job {} to pool {}'.format(job_id, pool.id))
            try:
                batch_client.job.add(job)
                if settings.verbose(config) and jptask is not None:
                    logger.debug('Job prep command: {}'.format(
                        jptask.command_line))
            except batchmodels.batch_error.BatchErrorException as ex:
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
                else:
                    raise
        del multi_instance
        del mi_docker_container_name
        del uses_task_dependencies
        # get base env vars from job
        job_env_vars = settings.job_environment_variables(jobspec)
        _job_env_vars_secid = \
            settings.job_environment_variables_keyvault_secret_id(jobspec)
        if util.is_not_empty(_job_env_vars_secid):
            jevs = keyvault.get_secret(
                keyvault_client, _job_env_vars_secid, value_is_json=True)
            job_env_vars = util.merge_dict(job_env_vars, jevs or {})
            del jevs
        del _job_env_vars_secid
        # add all tasks under job
        task_map = {}
        for _task in settings.job_tasks(config, jobspec):
            lasttaskid = _construct_task(
                batch_client, blob_client, keyvault_client, config, bxfile,
                bs, native, is_windows, tempdisk, allow_run_on_missing,
                docker_missing_images, singularity_missing_images, cloud_pool,
                pool, jobspec, job_id, job_env_vars, task_map,
                existing_tasklist, reserved_task_id, lasttaskid, False, _task)
        if has_merge_task:
            _task = settings.job_merge_task(jobspec)
            merge_task_id = _construct_task(
                batch_client, blob_client, keyvault_client, config, bxfile,
                bs, native, is_windows, tempdisk, allow_run_on_missing,
                docker_missing_images, singularity_missing_images, cloud_pool,
                pool, jobspec, job_id, job_env_vars, task_map,
                existing_tasklist, reserved_task_id, lasttaskid, True, _task)
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
        # submit job schedule if required
        if jobschedule is not None:
            taskmaploc = '{}jsrf-{}/{}'.format(
                bs.storage_entity_prefix, job_id, _TASKMAP_PICKLE_FILE)
            # pickle and upload task map
            f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
            fname = f.name
            try:
                with open(fname, 'wb') as f:
                    pickle.dump(task_map, f, protocol=pickle.HIGHEST_PROTOCOL)
                f.close()
                sas_urls = storage.upload_resource_files(
                    blob_client, config, [(taskmaploc, fname)])
            finally:
                os.unlink(fname)
                del f
                del fname
            if len(sas_urls) != 1:
                raise RuntimeError('unexpected number of sas urls')
            # attach as resource file to jm task
            jobschedule.job_specification.job_manager_task.resource_files.\
                append(
                    batchmodels.ResourceFile(
                        file_path=_TASKMAP_PICKLE_FILE,
                        blob_source=next(iter(sas_urls.values())),
                        file_mode='0640',
                    )
                )
            # submit job schedule
            logger.info('Adding jobschedule {} to pool {}'.format(
                job_id, pool.id))
            batch_client.job_schedule.add(jobschedule)
        else:
            # add task collection to job
            _add_task_collection(batch_client, job_id, task_map)
            # patch job if job autocompletion is needed
            if auto_complete:
                batch_client.job.patch(
                    job_id=job_id,
                    job_patch_parameter=batchmodels.JobPatchParameter(
                        on_all_tasks_complete=batchmodels.
                        OnAllTasksComplete.terminate_job))
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
