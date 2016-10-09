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

# stdlib imports
from __future__ import division, print_function, unicode_literals
import datetime
import logging
try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib
import os
import time
# non-stdlib imports
import azure.batch.models as batchmodels
# local imports
import convoy.util

# create logger
logger = logging.getLogger(__name__)
convoy.util.setup_logger(logger)
# global defines
_MAX_REBOOT_RETRIES = 5
_SSH_TUNNEL_SCRIPT = 'ssh_docker_tunnel_shipyard.sh'


def _reboot_node(batch_client, pool_id, node_id, wait):
    # type: (batch.BatchServiceClient, str, str, bool) -> None
    """Reboot a node in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
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


def _wait_for_pool_ready(batch_client, node_state, pool_id, reboot_on_failed):
    # type: (batch.BatchServiceClient, List[batchmodels.ComputeNodeState],
    #        str, bool) -> List[batchmodels.ComputeNode]
    """Wait for pool to enter "ready": steady state and all nodes idle
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param str pool_id: pool id
    :param bool reboot_on_failed: reboot node on failed start state
    :rtype: list
    :return: list of nodes
    """
    logger.info(
        'waiting for all nodes in pool {} to reach one of: {!r}'.format(
            pool_id, node_state))
    i = 0
    reboot_map = {}
    while True:
        # refresh pool to ensure that there is no resize error
        pool = batch_client.pool.get(pool_id)
        if pool.resize_error is not None:
            raise RuntimeError(
                'resize error encountered for pool {}: code={} msg={}'.format(
                    pool.id, pool.resize_error.code,
                    pool.resize_error.message))
        nodes = list(batch_client.compute_node.list(pool.id))
        if (reboot_on_failed and
                any(node.state == batchmodels.ComputeNodeState.starttaskfailed
                    for node in nodes)):
            for node in nodes:
                if (node.state ==
                        batchmodels.ComputeNodeState.starttaskfailed):
                    if node.id not in reboot_map:
                        reboot_map[node.id] = 0
                    if reboot_map[node.id] > _MAX_REBOOT_RETRIES:
                        raise RuntimeError(
                            ('ran out of reboot retries recovering node {} '
                             'in pool {}').format(node.id, pool.id))
                    _reboot_node(batch_client, pool.id, node.id, True)
                    reboot_map[node.id] += 1
            # refresh node list
            nodes = list(batch_client.compute_node.list(pool.id))
        if (len(nodes) >= pool.target_dedicated and
                all(node.state in node_state for node in nodes)):
            if any(node.state != batchmodels.ComputeNodeState.idle
                    for node in nodes):
                raise RuntimeError(
                    'node(s) of pool {} not in idle state'.format(pool.id))
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


def create_pool(batch_client, config, pool):
    # type: (batch.BatchServiceClient, dict, batchmodels.PoolAddParameter) ->
    #        List[batchmodels.ComputeNode]
    """Create pool if not exists
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param batchmodels.PoolAddParameter pool: pool addparameter object
    :rtype: list
    :return: list of nodes
    """
    # create pool if not exists
    try:
        logger.info('Attempting to create pool: {}'.format(pool.id))
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
    node_state = frozenset(
        (batchmodels.ComputeNodeState.starttaskfailed,
         batchmodels.ComputeNodeState.unusable,
         batchmodels.ComputeNodeState.idle)
    )
    try:
        reboot_on_failed = config[
            'pool_specification']['reboot_on_start_task_failed']
    except KeyError:
        reboot_on_failed = False
    nodes = _wait_for_pool_ready(
        batch_client, node_state, pool.id, reboot_on_failed)
    return nodes


def _add_admin_user_to_compute_node(
        batch_client, config, node, username, ssh_public_key):
    # type: (batch.BatchServiceClient, dict, str, batchmodels.ComputeNode,
    #        str) -> None
    """Adds an administrative user to the Batch Compute Node with a default
    expiry time of 7 days if not specified.
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param node: The compute node.
    :type node: `batchserviceclient.models.ComputeNode`
    :param str username: user name
    :param str ssh_public_key: ssh rsa public key
    """
    pool_id = config['pool_specification']['id']
    expiry = datetime.datetime.utcnow()
    try:
        td = config['pool_specification']['ssh']['expiry_days']
        expiry += datetime.timedelta(days=td)
    except KeyError:
        expiry += datetime.timedelta(days=7)
    logger.info('adding user {} to node {} in pool {}, expiry={}'.format(
        username, node.id, pool_id, expiry))
    try:
        batch_client.compute_node.add_user(
            pool_id,
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
        if 'The node user already exists' not in ex.message.value:
            raise


def add_ssh_user(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict,
    #        List[batchmodels.ComputeNode]) -> None
    """Add an SSH user to node and optionally generate an SSH tunneling script
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    """
    pool_id = config['pool_specification']['id']
    try:
        docker_user = config['pool_specification']['ssh']['username']
        if docker_user is None:
            raise KeyError()
    except KeyError:
        logger.info('not creating ssh user on pool {}'.format(pool_id))
    else:
        ssh_priv_key = None
        try:
            ssh_pub_key = config['pool_specification']['ssh']['ssh_public_key']
        except KeyError:
            ssh_pub_key = None
        try:
            gen_tunnel_script = config[
                'pool_specification']['ssh']['generate_tunnel_script']
        except KeyError:
            gen_tunnel_script = False
        # generate ssh key pair if not specified
        if ssh_pub_key is None:
            ssh_priv_key, ssh_pub_key = convoy.util.generate_ssh_keypair()
        # get node list if not provided
        if nodes is None:
            nodes = batch_client.compute_node.list(pool_id)
        for node in nodes:
            _add_admin_user_to_compute_node(
                batch_client, config, node, docker_user, ssh_pub_key)
        # generate tunnel script if requested
        if gen_tunnel_script:
            ssh_args = ['ssh']
            if ssh_priv_key is not None:
                ssh_args.append('-i')
                ssh_args.append(ssh_priv_key)
            ssh_args.extend([
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-p', '$2', '-N', '-L', '2375:localhost:2375',
                '{}@$1'.format(docker_user)])
            with open(_SSH_TUNNEL_SCRIPT, 'w') as fd:
                fd.write('#!/usr/bin/env bash\n')
                fd.write('set -e\n')
                fd.write(' '.join(ssh_args))
                fd.write('\n')
            os.chmod(_SSH_TUNNEL_SCRIPT, 0o755)
            logger.info('ssh tunnel script generated: {}'.format(
                _SSH_TUNNEL_SCRIPT))


def resize_pool(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Resize a pool
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool_id = config['pool_specification']['id']
    vm_count = int(config['pool_specification']['vm_count'])
    logger.info('Resizing pool {} to {}'.format(pool_id, vm_count))
    batch_client.pool.resize(
        pool_id=pool_id,
        pool_resize_parameter=batchmodels.PoolResizeParameter(
            target_dedicated=vm_count,
            resize_timeout=datetime.timedelta(minutes=20),
        )
    )


def del_pool(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Delete a pool
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool_id = config['pool_specification']['id']
    if not convoy.util.confirm_action(
            config, 'delete {} pool'.format(pool_id)):
        return
    logger.info('Deleting pool: {}'.format(pool_id))
    batch_client.pool.delete(pool_id)


def del_node(batch_client, config, node_id):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Delete a node in a pool
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param str node_id: node id to delete
    """
    if node_id is None or len(node_id) == 0:
        raise ValueError('node id is invalid')
    pool_id = config['pool_specification']['id']
    if not convoy.util.confirm_action(
            config, 'delete node {} from {} pool'.format(node_id, pool_id)):
        return
    logger.info('Deleting node {} from pool {}'.format(node_id, pool_id))
    batch_client.pool.remove_nodes(
        pool_id=pool_id,
        node_remove_parameter=batchmodels.NodeRemoveParameter(
            node_list=[node_id],
        )
    )


def del_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Delete jobs
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    for job in config['job_specifications']:
        job_id = job['id']
        if not convoy.util.confirm_action(
                config, 'delete {} job'.format(job_id)):
            continue
        logger.info('Deleting job: {}'.format(job_id))
        batch_client.job.delete(job_id)


def clean_mi_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Clean up multi-instance jobs
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    for job in config['job_specifications']:
        job_id = job['id']
        cleanup_job_id = 'shipyardcleanup-' + job_id
        cleanup_job = batchmodels.JobAddParameter(
            id=cleanup_job_id,
            pool_info=batchmodels.PoolInformation(
                pool_id=config['pool_specification']['id']),
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
                        coordination_command_line=convoy.util.
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
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    for job in config['job_specifications']:
        job_id = job['id']
        cleanup_job_id = 'shipyardcleanup-' + job_id
        logger.info('deleting job: {}'.format(cleanup_job_id))
        try:
            batch_client.job.delete(cleanup_job_id)
        except batchmodels.batch_error.BatchErrorException:
            pass


def terminate_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Terminate jobs
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    for job in config['job_specifications']:
        job_id = job['id']
        if not convoy.util.confirm_action(
                config, 'terminate {} job'.format(job_id)):
            continue
        logger.info('Terminating job: {}'.format(job_id))
        batch_client.job.terminate(job_id)


def del_all_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Delete all jobs
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    logger.debug('Getting list of all jobs...')
    jobs = batch_client.job.list()
    for job in jobs:
        if not convoy.util.confirm_action(
                config, 'delete {} job'.format(job.id)):
            continue
        logger.info('Deleting job: {}'.format(job.id))
        batch_client.job.delete(job.id)


def get_remote_login_settings(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict, List[str], bool) -> dict
    """Get remote login settings
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    :rtype: dict
    :return: dict of node id -> remote login settings
    """
    pool_id = config['pool_specification']['id']
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


def stream_file_and_wait_for_task(batch_client, filespec=None):
    # type: (batch.BatchServiceClient, str) -> None
    """Stream a file and wait for task to complete
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param str filespec: filespec (jobid:taskid:filename)
    """
    if filespec is None:
        job_id = None
        task_id = None
        file = None
    else:
        job_id, task_id, file = filespec.split(':')
    if job_id is None:
        job_id = convoy.util.get_input('Enter job id: ')
    if task_id is None:
        task_id = convoy.util.get_input('Enter task id: ')
    if file is None:
        file = convoy.util.get_input(
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
                print(f.decode('utf8'), end='')
            curr = end
        elif completed:
            print()
            break
        if not completed:
            task = batch_client.task.get(job_id, task_id)
            if task.state == batchmodels.TaskState.completed:
                completed = True
        time.sleep(1)


def get_file_via_task(batch_client, config, filespec=None):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Get a file task style
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param str filespec: filespec (jobid:taskid:filename)
    """
    if filespec is None:
        job_id = None
        task_id = None
        file = None
    else:
        job_id, task_id, file = filespec.split(':')
    if job_id is None:
        job_id = convoy.util.get_input('Enter job id: ')
    if task_id is None:
        task_id = convoy.util.get_input('Enter task id: ')
    if file is None:
        file = convoy.util.get_input(
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
            not convoy.util.confirm_action(
                config, 'file overwrite of {}'.format(file))):
        raise RuntimeError('file already exists: {}'.format(file))
    logger.debug('attempting to retrieve file {} from job={} task={}'.format(
        file, job_id, task_id))
    stream = batch_client.file.get_from_task(job_id, task_id, file)
    with fp.open('wb') as f:
        for data in stream:
            f.write(data)
    logger.debug('file {} retrieved from job={} task={} bytes={}'.format(
        file, job_id, task_id, fp.stat().st_size))


def get_file_via_node(batch_client, config, node_id):
    # type: (batch.BatchServiceClient, dict, str) -> None
    """Get a file node style
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param str nodeid: node id
    """
    if node_id is None or len(node_id) == 0:
        raise ValueError('node id is invalid')
    pool_id = config['pool_specification']['id']
    file = convoy.util.get_input('Enter node-relative file path to retrieve: ')
    if file == '' or file is None:
        raise RuntimeError('specified invalid file to retrieve')
    # check if file exists on disk; a possible race condition here is
    # understood
    fp = pathlib.Path(pathlib.Path(file).name)
    if (fp.exists() and
            not convoy.util.confirm_action(
                config, 'file overwrite of {}'.format(file))):
        raise RuntimeError('file already exists: {}'.format(file))
    logger.debug('attempting to retrieve file {} from pool={} node={}'.format(
        file, pool_id, node_id))
    stream = batch_client.file.get_from_compute_node(pool_id, node_id, file)
    with fp.open('wb') as f:
        for data in stream:
            f.write(data)
    logger.debug('file {} retrieved from pool={} node={} bytes={}'.format(
        file, pool_id, node_id, fp.stat().st_size))
