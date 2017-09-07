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
import logging
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import os
import time
import uuid
# non-stdlib imports
import azure.batch.models as batchmodels
# local imports
from . import crypto
from . import settings
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)

# global defines
_TENSORBOARD_LOG_ARGS = frozenset((
    '--tensorboard_logdir', '-tensorboard_logdir', '--logdir', '--log_dir',
    '--log-dir',
))


def tunnel_tensorboard(batch_client, config, jobid, taskid, logdir, image):
    # type: (batchsc.BatchServiceClient, dict, str, str, str, str) -> None
    """Action: Misc Tensorboard
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id to list
    :param str taskid: task id to list
    :param str logdir: log dir
    :param str image: tensorflow image to use
    """
    # ensure pool ssh private key exists
    pool = settings.pool_settings(config)
    ssh_priv_key = pool.ssh.ssh_private_key
    if ssh_priv_key is None:
        ssh_priv_key = pathlib.Path(
            pool.ssh.generated_file_export_path,
            crypto.get_ssh_key_prefix())
    if not ssh_priv_key.exists():
        raise RuntimeError(
            ('cannot tunnel to remote Tensorboard with non-existant RSA '
             'private key: {}').format(ssh_priv_key))
    if not crypto.check_ssh_private_key_filemode(ssh_priv_key):
        raise RuntimeError(
            'SSH private key filemode is too permissive: {}'.format(
                ssh_priv_key))
    # populate jobid if empty
    if util.is_none_or_empty(jobid):
        jobspecs = settings.job_specifications(config)
        jobid = settings.job_id(jobspecs[0])
    # get the last task for this job
    if util.is_none_or_empty(taskid):
        tasks = batch_client.task.list(
            jobid, task_list_options=batchmodels.TaskListOptions(select='id'))
        taskid = sorted([x.id for x in tasks])[-1]
    # wait for task to be running or completed
    logger.debug('waiting for task {} in job {} to reach a valid state'.format(
        taskid, jobid))
    while True:
        task = batch_client.task.get(jobid, taskid)
        if (task.state == batchmodels.TaskState.running or
                task.state == batchmodels.TaskState.completed):
            break
        logger.debug('waiting for task to enter running or completed state')
        time.sleep(1)
    # parse "--logdir" from task commandline
    if util.is_none_or_empty(logdir):
        for arg in _TENSORBOARD_LOG_ARGS:
            try:
                _tmp = task.command_line.index(arg)
            except ValueError:
                pass
            else:
                _tmp = task.command_line[_tmp + len(arg) + 1:]
                logdir = _tmp.split()[0].rstrip(';').rstrip('"').rstrip('\'')
                if not util.confirm_action(
                        config, 'use auto-detected logdir: {}'.format(logdir)):
                    logdir = None
                else:
                    logger.debug(
                        'using auto-detected logdir: {}'.format(logdir))
                    break
    if util.is_none_or_empty(logdir):
        raise RuntimeError(
            ('cannot automatically determine logdir for task {} in '
             'job {}, please retry command with explicit --logdir '
             'parameter').format(taskid, jobid))
    # construct absolute logpath
    logpath = pathlib.Path(
        settings.temp_disk_mountpoint(config)) / 'batch' / 'tasks'
    if logdir.startswith('$AZ_BATCH'):
        _tmp = logdir.index('/')
        _var = logdir[:_tmp]
        # shift off var
        logdir = logdir[_tmp + 1:]
        if _var == '$AZ_BATCH_NODE_ROOT_DIR':
            pass
        elif _var == '$AZ_BATCH_NODE_SHARED_DIR':
            logpath = logpath / 'shared'
        elif _var == '$AZ_BATCH_NODE_STARTUP_DIR':
            logpath = logpath / 'startup'
        elif _var == '$AZ_BATCH_TASK_WORKING_DIR':
            logpath = logpath / 'workitems' / jobid / 'job-1' / taskid / 'wd'
        else:
            raise RuntimeError(
                ('cannot automatically translate variable {} to absolute '
                 'path, please retry with an absolute path for '
                 '--logdir').format(_var))
    elif not logdir.startswith('/'):
        # default to task working directory
        logpath = logpath / 'workitems' / jobid / 'job-1' / taskid / 'wd'
    logpath = logpath / logdir
    if util.on_windows():
        logpath = str(logpath).replace('\\', '/')
    logger.debug('using logpath: {}'.format(logpath))
    # if logdir still has vars raise error
    if '$AZ_BATCH' in logdir:
        raise RuntimeError(
            ('cannot determine absolute logdir path for task {} in job {}, '
             'please retry with an absolute path for --logdir').format(
                 taskid, jobid))
    # determine tensorflow image to use
    tb = settings.get_tensorboard_docker_image()
    if util.is_none_or_empty(image):
        di = settings.global_resources_docker_images(config)
        di = [x for x in di if 'tensorflow' in x]
        if util.is_not_empty(di):
            image = di[0]
            if not util.confirm_action(
                    config,
                    'use auto-detected Docker image: {}'.format(image)):
                image = None
            else:
                logger.debug(
                    'using auto-detected Docker image: {}'.format(image))
        del di
    if util.is_none_or_empty(image):
        logger.warning(
            'no pre-loaded tensorflow Docker image detected on pool, '
            'using: {}'.format(tb[0]))
        image = tb[0]
    # get node remote login settings
    rls = batch_client.compute_node.get_remote_login_settings(
        pool.id, task.node_info.node_id)
    # set up tensorboard command
    if settings.is_gpu_pool(pool.vm_size):
        exe = 'nvidia-docker'
    else:
        exe = 'docker'
    name = str(uuid.uuid4()).split('-')[0]
    # map both ports (jupyter and tensorboard) to different host ports
    # to avoid conflicts
    host_port = 56006
    tb_ssh_args = [
        'ssh', '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile={}'.format(os.devnull),
        '-i', str(ssh_priv_key), '-p', str(rls.remote_login_port),
        '-t', '{}@{}'.format(pool.ssh.username, rls.remote_login_ip_address),
        ('sudo /bin/bash -c "{exe} run --rm --name={name} -p 58888:8888 '
         '-p {hostport}:{contport} -v {logdir}:/{jobid}.{taskid} {image} '
         'python {tbpy} --port={contport} --logdir=/{jobid}.{taskid}"').format(
             exe=exe, name=name, hostport=host_port, contport=tb[2],
             image=image, tbpy=tb[1], logdir=str(logpath), jobid=jobid,
             taskid=taskid)
    ]
    # set up ssh tunnel command
    tunnel_ssh_args = [
        'ssh', '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile={}'.format(os.devnull),
        '-i', str(ssh_priv_key), '-p', str(rls.remote_login_port), '-N',
        '-L', '{port}:localhost:{hostport}'.format(
            port=tb[2], hostport=host_port),
        '{}@{}'.format(pool.ssh.username, rls.remote_login_ip_address)
    ]
    # execute command and then tunnel
    tb_proc = None
    tunnel_proc = None
    try:
        tb_proc = util.subprocess_nowait_pipe_stdout(tb_ssh_args, shell=False)
        tunnel_proc = util.subprocess_nowait_pipe_stdout(
            tunnel_ssh_args, shell=False)
        logger.info(
            ('\n\n>> Please connect to Tensorboard at http://localhost:{}/'
             '\n\n>> Note that Tensorboard may take a while to start if the '
             'Docker is'
             '\n>> not present. Please keep retrying the URL every few '
             'seconds.'
             '\n\n>> Terminate your session with CTRL+C'
             '\n\n>> If you cannot terminate your session cleanly, run:'
             '\n     shipyard pool ssh --nodeid {} '
             'sudo docker kill {}\n').format(
                 tb[2], task.node_info.node_id, name))
        tb_proc.wait()
    finally:
        logger.debug(
            'attempting clean up of Tensorboard instance and SSH tunnel')
        try:
            if tunnel_proc is not None:
                tunnel_proc.poll()
                if tunnel_proc.returncode is None:
                    tunnel_proc.kill()
        except Exception as e:
            logger.exception(e)
        if tb_proc is not None:
            tb_proc.poll()
            if tb_proc.returncode is None:
                tb_proc.kill()
