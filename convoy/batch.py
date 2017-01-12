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
import datetime
import fnmatch
import getpass
import logging
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import os
import tempfile
import time
# non-stdlib imports
import azure.batch.models as batchmodels
# local imports
from . import crypto
from . import data
from . import settings
from . import storage
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_MAX_REBOOT_RETRIES = 5
_SSH_TUNNEL_SCRIPT = 'ssh_docker_tunnel_shipyard.sh'
_GENERIC_DOCKER_TASK_PREFIX = 'dockertask-'


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
    certs = batch_client.certificate.list()
    for cert in certs:
        if cert.delete_certificate_error is not None:
            ce = 'delete_error=(code={} msg={})'.format(
                cert.delete_certificate_error.code,
                cert.delete_certificate_error.message)
        else:
            ce = ''
        logger.info('{}={} [state={}{}]'.format(
            cert.thumbprint_algorithm, cert.thumbprint, cert.state, ce))
        i += 1
    if i == 0:
        logger.error('no certificates found')


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
    logger.info('Rebooting node {} from pool {}'.format(node_id, pool_id))
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
    pool_id = settings.pool_id(config)
    if nodeid is None:
        nodes = batch_client.compute_node.list(pool_id)
    else:
        nodes = [batch_client.compute_node.get(pool_id, nodeid)]
    # for any node in state start task failed, retrieve the stdout and stderr
    for node in nodes:
        if node.state == batchmodels.ComputeNodeState.starttaskfailed:
            settings.set_auto_confirm(config, True)
            get_all_files_via_node(
                batch_client, config,
                filespec='{},{}'.format(node.id, 'startup/std*.txt'))


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
    i = 0
    reboot_map = {}
    while True:
        # refresh pool to ensure that there is no resize error
        pool = batch_client.pool.get(pool_id)
        if pool.resize_error is not None:
            raise RuntimeError(
                'Resize error encountered for pool {}: code={} msg={}'.format(
                    pool.id, pool.resize_error.code,
                    pool.resize_error.message))
        nodes = list(batch_client.compute_node.list(pool.id))
        # check if any nodes are in start task failed state
        if (any(node.state == batchmodels.ComputeNodeState.starttaskfailed
                for node in nodes)):
            # attempt reboot if enabled for potentially transient errors
            if reboot_on_failed:
                for node in nodes:
                    if (node.state !=
                            batchmodels.ComputeNodeState.starttaskfailed):
                        continue
                    if node.id not in reboot_map:
                        reboot_map[node.id] = 0
                        logger.error(
                            ('Detected start task failure, attempting to '
                             'retrieve stdout/stderr for error diagnosis '
                             'from node {}').format(node.id))
                        _retrieve_outputs_from_failed_nodes(
                            batch_client, config, nodeid=node.id)
                    if reboot_map[node.id] > _MAX_REBOOT_RETRIES:
                        list_nodes(batch_client, config)
                        raise RuntimeError(
                            ('Ran out of reboot retries for recovery. '
                             'Please inspect both the node status above and '
                             'stdout.txt/stderr.txt files within the '
                             '{}/{}/startup directory in the current working '
                             'directory if available. If this error '
                             'appears non-transient, please submit an '
                             'issue on GitHub').format(
                                 pool.id, node.id))
                    _reboot_node(batch_client, pool.id, node.id, True)
                    reboot_map[node.id] += 1
                # refresh node list to reflect rebooting states
                nodes = list(batch_client.compute_node.list(pool.id))
            else:
                # fast path check for start task failures in non-reboot mode
                logger.error(
                    'Detected start task failure, attempting to retrieve '
                    'stdout/stderr for error diagnosis from nodes')
                _retrieve_outputs_from_failed_nodes(batch_client, config)
                list_nodes(batch_client, config)
                raise RuntimeError(
                    ('Please inspect both the node status above and '
                     'stdout.txt/stderr.txt files within the '
                     '{}/<nodes>/startup directory in the current working '
                     'directory if available. If this error appears '
                     'non-transient, please submit an issue on '
                     'GitHub.').format(pool.id))
        if (len(nodes) == pool.target_dedicated and
                all(node.state in stopping_states for node in nodes)):
            if any(node.state not in end_states for node in nodes):
                # list nodes of pool
                list_nodes(batch_client, config)
                raise RuntimeError(
                    ('Node(s) of pool {} not in {} state. Please inspect the '
                     'state of nodes in the pool above. If this appears to '
                     'be a transient error, please retry pool creation by '
                     'deleting and recreating the pool.').format(
                         pool.id, end_states))
            else:
                return nodes
        i += 1
        if i % 3 == 0:
            i = 0
            logger.debug('waiting for {} nodes to reach desired state'.format(
                pool.target_dedicated))
            for node in nodes:
                logger.debug('{}: {}'.format(node.id, node.state))
        time.sleep(10)


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
        batchmodels.ComputeNodeState.starttaskfailed,
        batchmodels.ComputeNodeState.unusable,
        batchmodels.ComputeNodeState.idle
    ]
    base_end_states = [batchmodels.ComputeNodeState.idle]
    if addl_end_states is not None and len(addl_end_states) > 0:
        base_stopping_states.extend(addl_end_states)
        base_end_states.extend(addl_end_states)
    stopping_states = frozenset(base_stopping_states)
    end_states = frozenset(base_end_states)
    nodes = _block_for_nodes_ready(
        batch_client, config, stopping_states, end_states, pool_id,
        settings.pool_settings(config).reboot_on_start_task_failed)
    list_nodes(batch_client, config, nodes=nodes)
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
    if (len(nodes) >= pool.target_dedicated and
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
        batch_client, config, node, username, ssh_public_key):
    # type: (batch.BatchServiceClient, dict, str, batchmodels.ComputeNode,
    #        str) -> None
    """Adds an administrative user to the Batch Compute Node with a default
    expiry time of 7 days if not specified.
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param node: The compute node.
    :type node: `azure.batch.batch_service_client.models.ComputeNode`
    :param str username: user name
    :param str ssh_public_key: ssh rsa public key
    """
    pool = settings.pool_settings(config)
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
                password=None,
                ssh_public_key=open(ssh_public_key, 'rb').read().decode('utf8')
            )
        )
    except batchmodels.batch_error.BatchErrorException as ex:
        if 'The specified node user already exists' in ex.message.value:
            logger.warning('user {} already exists on node {}'.format(
                username, node.id))
        else:
            raise


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
    if util.is_none_or_empty(pool.ssh.username):
        logger.info('not creating ssh user on pool {}'.format(pool.id))
        return
    # generate ssh key pair if not specified
    if pool.ssh.ssh_public_key is None:
        ssh_priv_key, ssh_pub_key = crypto.generate_ssh_keypair(
            pool.ssh.generated_file_export_path)
    else:
        ssh_priv_key = None
        ssh_pub_key = pool.ssh.ssh_public_key
    # get node list if not provided
    if nodes is None:
        nodes = batch_client.compute_node.list(pool.id)
    for node in nodes:
        _add_admin_user_to_compute_node(
            batch_client, config, node, pool.ssh.username, ssh_pub_key)
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
    if pool.ssh.generate_docker_tunnel_script:
        if nodes is None or len(list(nodes)) != pool.vm_count:
            nodes = batch_client.compute_node.list(pool.id)
        if ssh_priv_key is None:
            ssh_priv_key = pathlib.Path(
                pool.ssh.generated_file_export_path, crypto._SSH_KEY_PREFIX)
        ssh_args = [
            'ssh', '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
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
            fd.write(' >/dev/null 2>&1 &\n')
            fd.write('pid=$!\n')
            fd.write('echo ssh tunnel pid is $pid\n')
            fd.write(
                'echo execute docker commands with DOCKER_HOST=: or with '
                'option: -H :\n')
        os.chmod(str(tunnelscript), 0o755)
        logger.info('ssh tunnel script generated: {}'.format(tunnelscript))


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
    pools = batch_client.pool.list()
    for pool in pools:
        if pool.resize_error is not None:
            re = ' resize_error=(code={} msg={})'.format(
                pool.resize_error.code, pool.resize_error.message)
        else:
            re = ''
        logger.info(
            ('pool_id={} [state={} allocation_state={}{} vm_size={}, '
             'vm_count={} target_vm_count={}]'.format(
                 pool.id, pool.state, pool.allocation_state, re, pool.vm_size,
                 pool.current_dedicated, pool.target_dedicated)))
        i += 1
    if i == 0:
        logger.error('no pools found')


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
    pool_id = settings.pool_id(config)
    vm_count = settings.pool_vm_count(config)
    logger.info('Resizing pool {} to {} compute nodes'.format(
        pool_id, vm_count))
    batch_client.pool.resize(
        pool_id=pool_id,
        pool_resize_parameter=batchmodels.PoolResizeParameter(
            target_dedicated=vm_count,
            resize_timeout=datetime.timedelta(minutes=20),
        )
    )
    if wait:
        return wait_for_pool_ready(
            batch_client, config, pool_id,
            addl_end_states=[batchmodels.ComputeNodeState.running])


def del_pool(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> bool
    """Delete a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :rtype: bool
    :return: if pool was deleted
    """
    pool_id = settings.pool_id(config)
    if not util.confirm_action(
            config, 'delete {} pool'.format(pool_id)):
        return False
    logger.info('Deleting pool: {}'.format(pool_id))
    batch_client.pool.delete(pool_id)
    return True


def del_node(batch_client, config, node_id):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Delete a node in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str node_id: node id to delete
    """
    if util.is_none_or_empty(node_id):
        raise ValueError('node id is invalid')
    pool_id = settings.pool_id(config)
    if not util.confirm_action(
            config, 'delete node {} from {} pool'.format(node_id, pool_id)):
        return
    logger.info('Deleting node {} from pool {}'.format(node_id, pool_id))
    batch_client.pool.remove_nodes(
        pool_id=pool_id,
        node_remove_parameter=batchmodels.NodeRemoveParameter(
            node_list=[node_id],
        )
    )


def del_jobs(batch_client, config, jobid=None, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, bool) -> None
    """Delete jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to delete
    :param bool wait: wait for jobs to delete
    """
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid}]
    nocheck = set()
    for job in jobs:
        job_id = settings.job_id(job)
        if not util.confirm_action(
                config, 'delete {} job'.format(job_id)):
            nocheck.add(job_id)
            continue
        logger.info('Deleting job: {}'.format(job_id))
        batch_client.job.delete(job_id)
    if wait:
        for job in jobs:
            job_id = settings.job_id(job)
            if job_id in nocheck:
                continue
            try:
                logger.debug('waiting for job {} to delete'.format(job_id))
                while True:
                    batch_client.job.get(job_id)
                    time.sleep(1)
            except batchmodels.batch_error.BatchErrorException as ex:
                if 'The specified job does not exist' in ex.message.value:
                    continue


def del_all_jobs(batch_client, config, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool) -> None
    """Delete all jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool wait: wait for jobs to delete
    """
    check = set()
    logger.debug('Getting list of all jobs...')
    jobs = batch_client.job.list()
    for job in jobs:
        if not util.confirm_action(
                config, 'delete {} job'.format(job.id)):
            continue
        logger.info('Deleting job: {}'.format(job.id))
        batch_client.job.delete(job.id)
        check.add(job.id)
    if wait:
        for job_id in check:
            try:
                logger.debug('waiting for job {} to delete'.format(job_id))
                while True:
                    batch_client.job.get(job_id)
                    time.sleep(1)
            except batchmodels.batch_error.BatchErrorException as ex:
                if 'The specified job does not exist' in ex.message.value:
                    continue


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
    # first terminate tasks, force wait for completion
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
            tasks = [x.id for x in batch_client.task.list(job_id)]
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
                tasks = [x.id for x in batch_client.task.list(job_id)]
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
                        batch_client.task.get(job_id, task)
                        time.sleep(1)
                except batchmodels.batch_error.BatchErrorException as ex:
                    if 'The specified task does not exist' in ex.message.value:
                        continue


def clean_mi_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Clean up multi-instance jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    for job in settings.job_specifications(config):
        job_id = settings.job_id(job)
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
        cleanup_tasks = [x.id for x in batch_client.task.list(cleanup_job_id)]
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
                        ], wait=False),
                    ),
                    command_line='/bin/sh -c "exit 0"',
                    run_elevated=True,
                )
                batch_client.task.add(job_id=cleanup_job_id, task=batchtask)
                logger.debug(
                    ('Waiting for docker multi-instance clean up task {} '
                     'for job {} to complete').format(batchtask.id, job_id))
                # wait for cleanup task to complete before adding another
                while True:
                    batchtask = batch_client.task.get(
                        cleanup_job_id, batchtask.id)
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


def terminate_jobs(batch_client, config, jobid=None, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str, bool) -> None
    """Terminate jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to terminate
    :param bool wait: wait for job to terminate
    """
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid}]
    nocheck = set()
    for job in jobs:
        job_id = settings.job_id(job)
        if not util.confirm_action(
                config, 'terminate {} job'.format(job_id)):
            nocheck.add(job_id)
            continue
        logger.info('Terminating job: {}'.format(job_id))
        batch_client.job.terminate(job_id)
    if wait:
        for job in jobs:
            job_id = settings.job_id(job)
            if job_id in nocheck:
                continue
            try:
                logger.debug('waiting for job {} to terminate'.format(job_id))
                while True:
                    _job = batch_client.job.get(job_id)
                    if _job.state == batchmodels.JobState.completed:
                        break
                    time.sleep(1)
            except batchmodels.batch_error.BatchErrorException as ex:
                if 'The specified job does not exist' in ex.message.value:
                    continue


def terminate_all_jobs(batch_client, config, wait=False):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        bool) -> None
    """Terminate all jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool wait: wait for jobs to terminate
    """
    check = set()
    logger.debug('Getting list of all jobs...')
    jobs = batch_client.job.list()
    for job in jobs:
        if not util.confirm_action(
                config, 'terminate {} job'.format(job.id)):
            continue
        logger.info('Terminating job: {}'.format(job.id))
        batch_client.job.terminate(job.id)
        check.add(job.id)
    if wait:
        for job_id in check:
            try:
                logger.debug('waiting for job {} to terminate'.format(job_id))
                while True:
                    _job = batch_client.job.get(job_id)
                    if _job.state == batchmodels.JobState.completed:
                        break
                    time.sleep(1)
            except batchmodels.batch_error.BatchErrorException as ex:
                if 'The specified job does not exist' in ex.message.value:
                    continue


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
                    tasks = settings.job_tasks(job)
                    task_name = settings.task_name(tasks[0])
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
        ssh_args = [
            'ssh', '-o', 'StrictHostKeyChecking=no', '-o',
            'UserKnownHostsFile=/dev/null', '-i', str(ssh_private_key),
            '-p', str(rls.remote_login_port), '-t',
            '{}@{}'.format(username, rls.remote_login_ip_address),
            ('sudo /bin/bash -c "docker kill {tn}; '
             'docker ps -qa -f name={tn} | '
             'xargs --no-run-if-empty docker rm -v"').format(tn=task_name)
        ]
        rc = util.subprocess_with_output(ssh_args, shell=False)
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
    # get ssh login settings
    pool = settings.pool_settings(config)
    if util.is_none_or_empty(pool.ssh.username):
        raise ValueError(
            'cannot terminate docker container without an SSH username')
    ssh_private_key = pathlib.Path(
        pool.ssh.generated_file_export_path, crypto.get_ssh_key_prefix())
    if not ssh_private_key.exists():
        raise RuntimeError('ssh private key at {} not found'.format(
            ssh_private_key))
    if jobid is None:
        jobs = settings.job_specifications(config)
    else:
        jobs = [{'id': jobid}]
    nocheck = {}
    for job in jobs:
        job_id = settings.job_id(job)
        nocheck[job_id] = set()
        if taskid is None:
            tasks = [x.id for x in batch_client.task.list(job_id)]
        else:
            tasks = [taskid]
        for task in tasks:
            _task = batch_client.task.get(job_id, task)
            # if completed, skip
            if _task.state == batchmodels.TaskState.completed and not force:
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
            if _task.state == batchmodels.TaskState.running or force:
                if (_task.multi_instance_settings is not None and
                        _task.multi_instance_settings.number_of_instances > 1):
                    task_is_mi = True
                else:
                    task_is_mi = False
                _send_docker_kill_signal(
                    batch_client, config, pool.ssh.username, ssh_private_key,
                    _task.node_info.pool_id, _task.node_info.node_id,
                    job_id, task, task_is_mi)
            else:
                batch_client.task.terminate(job_id, task)
    if wait:
        for job in jobs:
            job_id = settings.job_id(job)
            if taskid is None:
                tasks = [x.id for x in batch_client.task.list(job_id)]
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
                        _task = batch_client.task.get(job_id, task)
                        if _task.state == batchmodels.TaskState.completed:
                            break
                        time.sleep(1)
                except batchmodels.batch_error.BatchErrorException as ex:
                    if 'The specified task does not exist' in ex.message.value:
                        continue


def list_nodes(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict, list) -> None
    """Get a list of nodes
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param lsit nodes: list of nodes
    """
    pool_id = settings.pool_id(config)
    logger.debug('listing nodes for pool {}'.format(pool_id))
    if nodes is None:
        nodes = batch_client.compute_node.list(pool_id)
    for node in nodes:
        if node.errors is not None:
            info = ' error=(code={} message={})'.format(
                node.errors.code, node.errors.message)
        else:
            info = ''
        if node.start_task_info is not None:
            if node.start_task_info.scheduling_error is not None:
                info += (' start_task_scheduling_error=(category={} code={} '
                         'message={})').format(
                             node.start_task_info.scheduling_error.category,
                             node.start_task_info.scheduling_error.code,
                             node.start_task_info.scheduling_error.message)
            else:
                info += ' start_task_exit_code={}'.format(
                    node.start_task_info.exit_code)
        logger.info(
            ('node_id={} [state={}{} scheduling_state={} ip_address={} '
             'vm_size={} total_tasks_run={} running_tasks_count={} '
             'total_tasks_succeeded={}]').format(
                 node.id, node.state, info, node.scheduling_state,
                 node.ip_address, node.vm_size, node.total_tasks_run,
                 node.running_tasks_count, node.total_tasks_succeeded))


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
    end = 0
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
                tfp = batch_client.file.get_node_file_properties_from_task(
                    job_id, task_id, file, raw=True)
            except batchmodels.BatchErrorException as ex:
                if ('The specified operation is not valid for the current '
                        'state of the resource.' in ex.message):
                    time.sleep(1)
                    continue
                elif 'The specified file does not exist.' in ex.message:
                    notfound += 1
                    if notfound > 10:
                        raise
                    time.sleep(1)
                    continue
                else:
                    raise
            size = int(tfp.response.headers['Content-Length'])
            if size != end and curr != size:
                end = size
                frag = batch_client.file.get_from_task(
                    job_id, task_id, file,
                    batchmodels.FileGetFromTaskOptions(
                        ocp_range='bytes={}-{}'.format(curr, end))
                )
                for f in frag:
                    if fd is not None:
                        fd.write(f)
                    else:
                        print(f.decode('utf8'), end='')
                curr = end
            elif completed:
                if not disk:
                    print()
                break
            if not completed:
                task = batch_client.task.get(job_id, task_id)
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
    i = 0
    for job in jobs:
        logger.info('job_id={} [state={} pool_id={}]'.format(
            job.id, job.state, job.pool_info.pool_id))
        i += 1
    if i == 0:
        logger.error('no jobs found')


def list_tasks(batch_client, config, jobid=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict,
    #        str) -> None
    """List tasks for specified jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str jobid: job id to list tasks from
    """
    for job in settings.job_specifications(config):
        job_id = settings.job_id(job)
        if jobid is not None and job_id != jobid:
            continue
        i = 0
        try:
            tasks = batch_client.task.list(job_id)
            for task in tasks:
                if task.execution_info is not None:
                    if task.execution_info.scheduling_error is not None:
                        ei = (' scheduling_error=(category={} code={} '
                              'message={})').format(
                                  task.execution_info.
                                  scheduling_error.category,
                                  task.execution_info.
                                  scheduling_error.code,
                                  task.execution_info.
                                  scheduling_error.message)
                    else:
                        if (task.execution_info.end_time is not None and
                                task.execution_info.start_time is not None):
                            duration = (task.execution_info.end_time -
                                        task.execution_info.start_time)
                        else:
                            duration = 'n/a'
                        ei = (' start_time={} end_time={} duration={} '
                              'exit_code={}').format(
                                  task.execution_info.start_time,
                                  task.execution_info.end_time,
                                  duration,
                                  task.execution_info.exit_code)
                else:
                    ei = ''
                logger.info(
                    'job_id={} task_id={} [state={} pool_id={} '
                    'node_id={}{}]'.format(
                        job_id, task.id, task.state, task.node_info.pool_id,
                        task.node_info.node_id, ei))
                i += 1
        except batchmodels.batch_error.BatchErrorException as ex:
            if 'The specified job does not exist' in ex.message.value:
                logger.error('{} job does not exist'.format(job_id))
                continue
        if i == 0:
            logger.error('no tasks found for job {}'.format(job_id))


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
    for job in settings.job_specifications(config):
        job_id = settings.job_id(job)
        if jobid is not None and job_id != jobid:
            continue
        i = 0
        try:
            tasks = batch_client.task.list(job_id)
            for task in tasks:
                if taskid is not None and taskid != task.id:
                    continue
                j = 0
                files = batch_client.file.list_from_task(
                    job_id, task.id, recursive=True)
                for file in files:
                    if file.is_directory:
                        continue
                    logger.info(
                        'task_id={} file={} [job_id={} lmt={} '
                        'bytes={}]'.format(
                            task.id, file.name, job_id,
                            file.properties.last_modified,
                            file.properties.content_length))
                    j += 1
                if j == 0:
                    logger.error('no files found for task {} job {}'.format(
                        task.id, job['id']))
                i += 1
        except batchmodels.batch_error.BatchErrorException as ex:
            if 'The specified job does not exist' in ex.message.value:
                logger.error('{} job does not exist'.format(job_id))
                continue
        if i == 0:
            logger.error('no tasks found for job {}'.format(job_id))


def _generate_next_generic_task_id(batch_client, job_id, reserved=None):
    # type: (azure.batch.batch_service_client.BatchServiceClient, str,
    #        str) -> str
    """Generate the next generic task id
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job id
    :param str reserved: reserved task id
    :rtype: str
    :return: returns a generic docker task id
    """
    # get filtered, sorted list of generic docker task ids
    try:
        tasklist = sorted(filter(
            lambda x: x.id.startswith(_GENERIC_DOCKER_TASK_PREFIX),
            (batch_client.task.list(job_id))), key=lambda y: y.id)
        tasknum = int(tasklist[-1].id.split('-')[-1]) + 1
    except (batchmodels.batch_error.BatchErrorException, IndexError):
        tasknum = 0
    if reserved is not None:
        tasknum_reserved = int(reserved.split('-')[-1])
        while tasknum == tasknum_reserved:
            tasknum += 1
    return '{0}{1:03d}'.format(_GENERIC_DOCKER_TASK_PREFIX, tasknum)


def add_jobs(
        batch_client, blob_client, config, jpfile, bxfile, recreate=False,
        tail=None):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,
    #        dict, tuple, tuple, bool, str) -> None
    """Add jobs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param tuple jpfile: jobprep file
    :param tuple bxfile: blobxfer file
    :param bool recreate: recreate job if completed
    :param str tail: tail specified file of last job/task added
    """
    # get the pool inter-node comm setting
    bs = settings.batch_shipyard_settings(config)
    pool = settings.pool_settings(config)
    _pool = batch_client.pool.get(pool.id)
    global_resources = []
    for gr in settings.global_resources_docker_images(config):
        global_resources.append(gr)
    lastjob = None
    lasttask = None
    for jobspec in settings.job_specifications(config):
        jpcmd = ['$AZ_BATCH_NODE_STARTUP_DIR/wd/{} {}'.format(
            jpfile[0], ' '.join(global_resources))]
        # digest any input_data
        addlcmds = data.process_input_data(config, bxfile, jobspec)
        if addlcmds is not None:
            jpcmd.append(addlcmds)
        del addlcmds
        jpcmdline = util.wrap_commands_in_shell(jpcmd)
        del jpcmd
        job = batchmodels.JobAddParameter(
            id=settings.job_id(jobspec),
            pool_info=batchmodels.PoolInformation(pool_id=pool.id),
            job_preparation_task=batchmodels.JobPreparationTask(
                command_line=jpcmdline,
                wait_for_success=True,
                run_elevated=True,
                rerun_on_node_reboot_after_success=False,
            ),
            uses_task_dependencies=False,
        )
        lastjob = job.id
        # perform checks:
        # 1. if tasks have dependencies, set it if so
        # 2. if there are multi-instance tasks
        mi_ac = settings.job_multi_instance_auto_complete(config)
        multi_instance = False
        mi_docker_container_name = None
        reserved_task_id = None
        for task in settings.job_tasks(jobspec):
            # do not break, check to ensure ids are set on each task if
            # task dependencies are set
            if settings.has_depends_on_task(task):
                job.uses_task_dependencies = True
            if settings.is_multi_instance_task(task):
                if multi_instance and mi_ac:
                    raise ValueError(
                        'cannot specify more than one multi-instance task '
                        'per job with auto completion enabled')
                multi_instance = True
                mi_docker_container_name = settings.task_name(task)
                if util.is_none_or_empty(mi_docker_container_name):
                    _id = settings.task_id(task)
                    if util.is_none_or_empty(_id):
                        reserved_task_id = _generate_next_generic_task_id(
                            batch_client, job.id)
                        settings.set_task_id(task, reserved_task_id)
                        _id = '{}-{}'.format(job.id, reserved_task_id)
                    settings.set_task_name(task, _id)
                    mi_docker_container_name = settings.task_name(task)
                    del _id
        # add multi-instance settings
        set_terminate_on_all_tasks_complete = False
        if multi_instance and mi_ac:
            set_terminate_on_all_tasks_complete = True
            job.job_release_task = batchmodels.JobReleaseTask(
                command_line=util.wrap_commands_in_shell(
                    ['docker kill {}'.format(mi_docker_container_name),
                     'docker rm -v {}'.format(mi_docker_container_name)]),
                run_elevated=True,
            )
        logger.info('Adding job: {}'.format(job.id))
        try:
            batch_client.job.add(job)
        except batchmodels.batch_error.BatchErrorException as ex:
            if ('The specified job is already in a completed state.' in
                    ex.message.value):
                if recreate:
                    # get job state
                    _job = batch_client.job.get(job.id)
                    if _job.state == batchmodels.JobState.completed:
                        del_jobs(
                            batch_client, config, jobid=job.id, wait=True)
                        time.sleep(1)
                        batch_client.job.add(job)
                else:
                    raise
            elif 'The specified job already exists' in ex.message.value:
                # cannot re-use an existing job if multi-instance due to
                # job release requirement
                if multi_instance and mi_ac:
                    raise
            else:
                raise
        del mi_ac
        del multi_instance
        del mi_docker_container_name
        # get base env vars from job
        job_env_vars = settings.job_environment_variables(jobspec)
        # add all tasks under job
        for _task in settings.job_tasks(jobspec):
            _task_id = settings.task_id(_task)
            if util.is_none_or_empty(_task_id):
                _task_id = _generate_next_generic_task_id(
                    batch_client, job.id, reserved_task_id)
                settings.set_task_id(_task, _task_id)
            if util.is_none_or_empty(settings.task_name(_task)):
                settings.set_task_name(_task, '{}-{}'.format(job.id, _task_id))
            del _task_id
            task = settings.task_settings(_pool, config, _task)
            # merge job env vars into task env vars
            if job_env_vars is None:
                env_vars = task.environment_variables
            else:
                env_vars = util.merge_dict(
                    job_env_vars, task.environment_variables)
            # get and create env var file
            sas_urls = None
            if util.is_not_empty(env_vars) or task.infiniband or task.gpu:
                envfileloc = '{}taskrf-{}/{}{}'.format(
                    bs.storage_entity_prefix, job.id, task.id, task.envfile)
                f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
                fname = f.name
                try:
                    if util.is_not_empty(env_vars):
                        for key in env_vars:
                            f.write('{}={}\n'.format(
                                key, env_vars[key]).encode('utf8'))
                    if task.infiniband:
                        f.write(b'I_MPI_FABRICS=shm:dapl\n')
                        f.write(b'I_MPI_DAPL_PROVIDER=ofa-v2-ib0\n')
                        f.write(b'I_MPI_DYNAMIC_CONNECTION=0\n')
                        # create a manpath entry for potentially buggy
                        # intel mpivars.sh
                        f.write(b'MANPATH=/usr/share/man:/usr/local/man\n')
                    if task.gpu:
                        f.write(b'CUDA_CACHE_DISABLE=0\n')
                        f.write(b'CUDA_CACHE_MAXSIZE=1073741824\n')
                        # use absolute path due to non-expansion
                        f.write(
                            ('CUDA_CACHE_PATH={}/batch/tasks/'
                             '.nv/ComputeCache\n').format(
                                 settings.temp_disk_mountpoint(
                                     config)).encode('utf8'))
                    # close and upload env var file
                    f.close()
                    sas_urls = storage.upload_resource_files(
                        blob_client, config, [(envfileloc, fname)])
                finally:
                    os.unlink(fname)
                    del f
                    del fname
                if len(sas_urls) != 1:
                    raise RuntimeError('unexpected number of sas urls')
            # check if this is a multi-instance task
            mis = None
            if settings.is_multi_instance_task(_task):
                mis = batchmodels.MultiInstanceSettings(
                    number_of_instances=task.multi_instance.num_instances,
                    coordination_command_line=util.wrap_commands_in_shell(
                        task.multi_instance.coordination_command, wait=False),
                    common_resource_files=[],
                )
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
                task_commands = [
                    '{} {} {}'.format(
                        task.docker_exec_cmd, task.name, task.command)
                ]
            else:
                task_commands = [
                    'env | grep AZ_BATCH_ >> {}'.format(task.envfile),
                    '{} {} {}{}'.format(
                        task.docker_run_cmd,
                        ' '.join(task.docker_run_options),
                        task.image,
                        '{}'.format(
                            ' ' + task.command) if task.command else '')
                ]
            # digest any input_data
            addlcmds = data.process_input_data(
                config, bxfile, _task, on_task=True)
            if addlcmds is not None:
                task_commands.insert(0, addlcmds)
            # digest any output data
            addlcmds = data.process_output_data(
                config, bxfile, _task)
            if addlcmds is not None:
                task_commands.append(addlcmds)
            del addlcmds
            # create task
            batchtask = batchmodels.TaskAddParameter(
                id=task.id,
                command_line=util.wrap_commands_in_shell(task_commands),
                run_elevated=True,
                resource_files=[],
                multi_instance_settings=mis,
            )
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
                    logger.info(
                        'Multi-instance task coordination command: {}'.format(
                            mis.coordination_command_line))
                logger.info('Adding task: {} command: {}'.format(
                    task.id, batchtask.command_line))
            else:
                logger.info('Adding task: {}'.format(task.id))
            batch_client.task.add(job_id=job.id, task=batchtask)
            # update job if job autocompletion is needed
            if set_terminate_on_all_tasks_complete:
                batch_client.job.update(
                    job_id=job.id,
                    job_update_parameter=batchmodels.JobUpdateParameter(
                        pool_info=batchmodels.PoolInformation(pool_id=pool.id),
                        on_all_tasks_complete=batchmodels.
                        OnAllTasksComplete.terminate_job))
            lasttask = task.id
    # tail file if specified
    if tail:
        stream_file_and_wait_for_task(
            batch_client, config, filespec='{},{},{}'.format(
                lastjob, lasttask, tail), disk=False)
