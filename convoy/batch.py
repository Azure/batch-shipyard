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
import tempfile
import time
# non-stdlib imports
import azure.batch.models as batchmodels
# local imports
import convoy.storage
import convoy.util

# create logger
logger = logging.getLogger(__name__)
convoy.util.setup_logger(logger)
# global defines
_MAX_REBOOT_RETRIES = 5
_SSH_TUNNEL_SCRIPT = 'ssh_docker_tunnel_shipyard.sh'
_GENERIC_DOCKER_TASK_PREFIX = 'dockertask-'
_GLUSTER_VOLUME = '.gluster/gv0'


def get_gluster_volume():
    # type: (None) -> str
    """Get gluster volume mount suffix
    :rtype: str
    :return: gluster volume mount
    """
    return _GLUSTER_VOLUME


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


def add_jobs(batch_client, blob_client, config, jpfile):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,
    #        tuple, dict) -> None
    """Add jobs
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param tuple jpfile: jobprep file
    """
    # get the pool inter-node comm setting
    pool_id = config['pool_specification']['id']
    _pool = batch_client.pool.get(pool_id)
    global_resources = []
    for gr in config['global_resources']['docker_images']:
        global_resources.append(gr)
    # TODO add global resources for non-docker resources
    jpcmdline = convoy.util.wrap_commands_in_shell([
        '$AZ_BATCH_NODE_SHARED_DIR/{} {}'.format(
            jpfile[0], ' '.join(global_resources))])
    for jobspec in config['job_specifications']:
        job = batchmodels.JobAddParameter(
            id=jobspec['id'],
            pool_info=batchmodels.PoolInformation(pool_id=pool_id),
            job_preparation_task=batchmodels.JobPreparationTask(
                command_line=jpcmdline,
                wait_for_success=True,
                run_elevated=True,
                rerun_on_node_reboot_after_success=False,
            )
        )
        # perform checks:
        # 1. if tasks have dependencies, set it if so
        # 2. if there are multi-instance tasks
        try:
            mi_ac = jobspec['multi_instance_auto_complete']
        except KeyError:
            mi_ac = True
        job.uses_task_dependencies = False
        multi_instance = False
        docker_container_name = None
        for task in jobspec['tasks']:
            # do not break, check to ensure ids are set on each task if
            # task dependencies are set
            if 'depends_on' in task and len(task['depends_on']) > 0:
                if ('id' not in task or task['id'] is None or
                        len(task['id']) == 0):
                    raise ValueError(
                        'task id is not specified, but depends_on is set')
                job.uses_task_dependencies = True
            if 'multi_instance' in task:
                if multi_instance and mi_ac:
                    raise ValueError(
                        'cannot specify more than one multi-instance task '
                        'per job with auto completion enabled')
                multi_instance = True
                docker_container_name = task['name']
        # add multi-instance settings
        set_terminate_on_all_tasks_complete = False
        if multi_instance and mi_ac:
            if (docker_container_name is None or
                    len(docker_container_name) == 0):
                raise ValueError(
                    'multi-instance task must be invoked with a named '
                    'container')
            set_terminate_on_all_tasks_complete = True
            job.job_release_task = batchmodels.JobReleaseTask(
                command_line=convoy.util.wrap_commands_in_shell(
                    ['docker stop {}'.format(docker_container_name),
                     'docker rm -v {}'.format(docker_container_name)]),
                run_elevated=True,
            )
        logger.info('Adding job: {}'.format(job.id))
        try:
            batch_client.job.add(job)
        except batchmodels.batch_error.BatchErrorException as ex:
            if 'The specified job already exists' in ex.message.value:
                # cannot re-use an existing job if multi-instance due to
                # job release requirement
                if multi_instance and mi_ac:
                    raise
            else:
                raise
        del mi_ac
        del multi_instance
        del docker_container_name
        # add all tasks under job
        for task in jobspec['tasks']:
            # get image name
            image = task['image']
            # get or generate task id
            try:
                task_id = task['id']
                if task_id is None or len(task_id) == 0:
                    raise KeyError()
            except KeyError:
                # get filtered, sorted list of generic docker task ids
                try:
                    tasklist = sorted(
                        filter(lambda x: x.id.startswith(
                            _GENERIC_DOCKER_TASK_PREFIX), list(
                                batch_client.task.list(job.id))),
                        key=lambda y: y.id)
                    tasknum = int(tasklist[-1].id.split('-')[-1]) + 1
                except (batchmodels.batch_error.BatchErrorException,
                        IndexError):
                    tasknum = 0
                task_id = '{0}{1:03d}'.format(
                    _GENERIC_DOCKER_TASK_PREFIX, tasknum)
            # set run and exec commands
            docker_run_cmd = 'docker run'
            docker_exec_cmd = 'docker exec'
            # get generic run opts
            try:
                run_opts = task['additional_docker_run_options']
            except KeyError:
                run_opts = []
            # parse remove container option
            try:
                rm_container = task['remove_container_after_exit']
            except KeyError:
                rm_container = False
            else:
                if rm_container and '--rm' not in run_opts:
                    run_opts.append('--rm')
            # parse name option
            try:
                name = task['name']
                if name is not None:
                    run_opts.append('--name {}'.format(name))
            except KeyError:
                name = None
            # parse labels option
            try:
                labels = task['labels']
                if labels is not None and len(labels) > 0:
                    for label in labels:
                        run_opts.append('-l {}'.format(label))
                del labels
            except KeyError:
                pass
            # parse ports option
            try:
                ports = task['ports']
                if ports is not None and len(ports) > 0:
                    for port in ports:
                        run_opts.append('-p {}'.format(port))
                del ports
            except KeyError:
                pass
            # parse entrypoint
            try:
                entrypoint = task['entrypoint']
                if entrypoint is not None:
                    run_opts.append('--entrypoint {}'.format(entrypoint))
                del entrypoint
            except KeyError:
                pass
            # parse data volumes
            try:
                data_volumes = task['data_volumes']
            except KeyError:
                pass
            else:
                if data_volumes is not None and len(data_volumes) > 0:
                    for key in data_volumes:
                        dvspec = config[
                            'global_resources']['docker_volumes'][
                                'data_volumes'][key]
                        try:
                            hostpath = dvspec['host_path']
                        except KeyError:
                            hostpath = None
                        if hostpath is not None and len(hostpath) > 0:
                            run_opts.append('-v {}:{}'.format(
                                hostpath, dvspec['container_path']))
                        else:
                            run_opts.append('-v {}'.format(
                                dvspec['container_path']))
            # parse shared data volumes
            try:
                shared_data_volumes = task['shared_data_volumes']
            except KeyError:
                pass
            else:
                if (shared_data_volumes is not None and
                        len(shared_data_volumes) > 0):
                    for key in shared_data_volumes:
                        dvspec = config[
                            'global_resources']['docker_volumes'][
                                'shared_data_volumes'][key]
                        if dvspec['volume_driver'] == 'glusterfs':
                            run_opts.append('-v {}/{}:{}'.format(
                                '$AZ_BATCH_NODE_SHARED_DIR',
                                _GLUSTER_VOLUME, dvspec['container_path']))
                        else:
                            run_opts.append('-v {}:{}'.format(
                                key, dvspec['container_path']))
            # get command
            try:
                command = task['command']
                if command is not None and len(command) == 0:
                    raise KeyError()
            except KeyError:
                command = None
            # get and create env var file
            envfile = '.shipyard.envlist'
            sas_urls = None
            try:
                env_vars = jobspec['environment_variables']
            except KeyError:
                env_vars = None
            try:
                infiniband = task['infiniband']
            except KeyError:
                infiniband = False
            # ensure we're on HPC VMs with inter node comm enabled
            sles_hpc = False
            if infiniband:
                if not _pool.enable_inter_node_communication:
                    raise RuntimeError(
                        ('cannot initialize an infiniband task on a '
                         'non-internode communication enabled '
                         'pool: {}').format(pool_id))
                if (_pool.vm_size.lower() != 'standard_a8' and
                        _pool.vm_size.lower() != 'standard_a9'):
                    raise RuntimeError(
                        ('cannot initialize an infiniband task on nodes '
                         'without RDMA, pool: {} vm_size: {}').format(
                             pool_id, _pool.vm_size))
                publisher = _pool.virtual_machine_configuration.\
                    image_reference.publisher.lower()
                offer = _pool.virtual_machine_configuration.\
                    image_reference.offer.lower()
                sku = _pool.virtual_machine_configuration.\
                    image_reference.sku.lower()
                supported = False
                # only centos-hpc and sles-hpc:12-sp1 are supported
                # for infiniband
                if publisher == 'openlogic' and offer == 'centos-hpc':
                    supported = True
                elif (publisher == 'suse' and offer == 'sles-hpc' and
                      sku == '12-sp1'):
                    supported = True
                    sles_hpc = True
                if not supported:
                    raise ValueError(
                        ('Unsupported infiniband VM config, publisher={} '
                         'offer={}').format(publisher, offer))
                del supported
            # ensure we're on n-series for gpu
            try:
                gpu = task['gpu']
            except KeyError:
                gpu = False
            if gpu:
                if not (_pool.vm_size.lower().startswith('standard_nc') or
                        _pool.vm_size.lower().startswith('standard_nv')):
                    raise RuntimeError(
                        ('cannot initialize a gpu task on nodes without '
                         'gpus, pool: {} vm_size: {}').format(
                             pool_id, _pool.vm_size))
                publisher = _pool.virtual_machine_configuration.\
                    image_reference.publisher.lower()
                offer = _pool.virtual_machine_configuration.\
                    image_reference.offer.lower()
                sku = _pool.virtual_machine_configuration.\
                    image_reference.sku.lower()
                # TODO other images as they become available with gpu support
                if (publisher != 'canonical' and offer != 'ubuntuserver' and
                        sku < '16.04.0-lts'):
                    raise ValueError(
                        ('Unsupported gpu VM config, publisher={} offer={} '
                         'sku={}').format(publisher, offer, sku))
                # override docker commands with nvidia docker wrapper
                docker_run_cmd = 'nvidia-docker run'
                docker_exec_cmd = 'nvidia-docker exec'
            try:
                task_ev = task['environment_variables']
                if env_vars is None:
                    env_vars = task_ev
                else:
                    env_vars = convoy.util.merge_dict(env_vars, task_ev)
            except KeyError:
                if infiniband:
                    env_vars = []
            if infiniband or (env_vars is not None and len(env_vars) > 0):
                envfileloc = '{}taskrf-{}/{}{}'.format(
                    config['batch_shipyard']['storage_entity_prefix'],
                    job.id, task_id, envfile)
                f = tempfile.NamedTemporaryFile(
                    mode='w', encoding='utf-8', delete=False)
                fname = f.name
                try:
                    for key in env_vars:
                        f.write('{}={}\n'.format(key, env_vars[key]))
                    if infiniband:
                        f.write('I_MPI_FABRICS=shm:dapl\n')
                        f.write('I_MPI_DAPL_PROVIDER=ofa-v2-ib0\n')
                        f.write('I_MPI_DYNAMIC_CONNECTION=0\n')
                        # create a manpath entry for potentially buggy
                        # intel mpivars.sh
                        f.write('MANPATH=/usr/share/man:/usr/local/man\n')
                    # close and upload env var file
                    f.close()
                    sas_urls = convoy.storage.upload_resource_files(
                        blob_client, config, [(envfileloc, fname)])
                finally:
                    os.unlink(fname)
                    del f
                    del fname
                if len(sas_urls) != 1:
                    raise RuntimeError('unexpected number of sas urls')
            # always add option for envfile
            run_opts.append('--env-file {}'.format(envfile))
            # add infiniband run opts
            if infiniband:
                run_opts.append('--net=host')
                run_opts.append('--ulimit memlock=9223372036854775807')
                run_opts.append('--device=/dev/hvnd_rdma')
                run_opts.append('--device=/dev/infiniband/rdma_cm')
                run_opts.append('--device=/dev/infiniband/uverbs0')
                run_opts.append('-v /etc/rdma:/etc/rdma:ro')
                if sles_hpc:
                    run_opts.append('-v /etc/dat.conf:/etc/dat.conf:ro')
                run_opts.append('-v /opt/intel:/opt/intel:ro')
            # mount batch root dir
            run_opts.append(
                '-v $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR')
            # set working directory
            run_opts.append('-w $AZ_BATCH_TASK_WORKING_DIR')
            # check if there are multi-instance tasks
            mis = None
            if 'multi_instance' in task:
                if not _pool.enable_inter_node_communication:
                    raise RuntimeError(
                        ('cannot run a multi-instance task on a '
                         'non-internode communication enabled '
                         'pool: {}').format(pool_id))
                # container must be named
                if name is None or len(name) == 0:
                    raise ValueError(
                        'multi-instance task must be invoked with a named '
                        'container')
                # docker exec command cannot be empty/None
                if command is None or len(command) == 0:
                    raise ValueError(
                        'multi-instance task must have an application command')
                # set docker run as coordination command
                try:
                    run_opts.remove('--rm')
                except ValueError:
                    pass
                # run in detached mode
                run_opts.append('-d')
                # ensure host networking stack is used
                if '--net=host' not in run_opts:
                    run_opts.append('--net=host')
                # get coordination command
                try:
                    coordination_command = task[
                        'multi_instance']['coordination_command']
                    if (coordination_command is not None and
                            len(coordination_command) == 0):
                        raise KeyError()
                except KeyError:
                    coordination_command = None
                cc_args = [
                    'env | grep AZ_BATCH_ >> {}'.format(envfile),
                    '{} {} {}{}'.format(
                        docker_run_cmd,
                        ' '.join(run_opts),
                        image,
                        '{}'.format(' ' + coordination_command)
                        if coordination_command else '')
                ]
                # create multi-instance settings
                num_instances = task['multi_instance']['num_instances']
                if not isinstance(num_instances, int):
                    if num_instances == 'pool_specification_vm_count':
                        num_instances = config[
                            'pool_specification']['vm_count']
                    elif num_instances == 'pool_current_dedicated':
                        num_instances = _pool.current_dedicated
                    else:
                        raise ValueError(
                            ('multi instance num instances setting '
                             'invalid: {}').format(num_instances))
                mis = batchmodels.MultiInstanceSettings(
                    number_of_instances=num_instances,
                    coordination_command_line=convoy.util.
                    wrap_commands_in_shell(cc_args, wait=False),
                    common_resource_files=[],
                )
                # add common resource files for multi-instance
                try:
                    rfs = task['multi_instance']['resource_files']
                except KeyError:
                    pass
                else:
                    for rf in rfs:
                        try:
                            fm = rf['file_mode']
                        except KeyError:
                            fm = None
                        mis.common_resource_files.append(
                            batchmodels.ResourceFile(
                                file_path=rf['file_path'],
                                blob_source=rf['blob_source'],
                                file_mode=fm,
                            )
                        )
                # set application command
                task_commands = [
                    '{} {} {}'.format(docker_exec_cmd, name, command)
                ]
            else:
                task_commands = [
                    'env | grep AZ_BATCH_ >> {}'.format(envfile),
                    '{} {} {}{}'.format(
                        docker_run_cmd,
                        ' '.join(run_opts),
                        image,
                        '{}'.format(' ' + command) if command else '')
                ]
            # create task
            batchtask = batchmodels.TaskAddParameter(
                id=task_id,
                command_line=convoy.util.wrap_commands_in_shell(task_commands),
                run_elevated=True,
                resource_files=[],
            )
            if mis is not None:
                batchtask.multi_instance_settings = mis
            if sas_urls is not None:
                batchtask.resource_files.append(
                    batchmodels.ResourceFile(
                        file_path=str(envfile),
                        blob_source=next(iter(sas_urls.values())),
                        file_mode='0640',
                    )
                )
            # add additional resource files
            try:
                rfs = task['resource_files']
            except KeyError:
                pass
            else:
                for rf in rfs:
                    try:
                        fm = rf['file_mode']
                    except KeyError:
                        fm = None
                    batchtask.resource_files.append(
                        batchmodels.ResourceFile(
                            file_path=rf['file_path'],
                            blob_source=rf['blob_source'],
                            file_mode=fm,
                        )
                    )
            # add task dependencies
            if 'depends_on' in task and len(task['depends_on']) > 0:
                batchtask.depends_on = batchmodels.TaskDependencies(
                    task_ids=task['depends_on']
                )
            # create task
            logger.info('Adding task {}: {}'.format(
                task_id, batchtask.command_line))
            if mis is not None:
                logger.info(
                    'multi-instance task coordination command: {}'.format(
                        mis.coordination_command_line))
            batch_client.task.add(job_id=job.id, task=batchtask)
            # update job if job autocompletion is needed
            if set_terminate_on_all_tasks_complete:
                batch_client.job.update(
                    job_id=job.id,
                    job_update_parameter=batchmodels.JobUpdateParameter(
                        pool_info=batchmodels.PoolInformation(pool_id=pool_id),
                        on_all_tasks_complete=batchmodels.
                        OnAllTasksComplete.terminate_job))
