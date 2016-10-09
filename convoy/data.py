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
try:
    from shlex import quote as shellquote
except ImportError:
    from pipes import quote as shellquote
import threading
# local imports
import convoy.util

# create logger
logger = logging.getLogger(__name__)
convoy.util.setup_logger(logger)


def _scp_data(src, dst, username, ssh_private_key, rls, eo):
    # type: (str, str, str, pathlib.Path, dict, str, str) -> None
    """Secure copy data
    :param str src: source path
    :param str dst: destination path
    :param str username: username
    :param pathlib.Path: ssh private key
    :param dict rls: remote login settings
    :param str eo: extra options
    """
    recursive = '-r' if pathlib.Path(src).is_dir() else ''
    _rls = next(iter(rls.values()))
    ip = _rls.remote_login_ip_address
    port = _rls.remote_login_port
    del _rls
    cmd = ('scp -o StrictHostKeyChecking=no '
           '-o UserKnownHostsFile=/dev/null -p '
           '{} {} -i {} -P {} {} {}@{}:"{}"'.format(
               eo, recursive, ssh_private_key, port, shellquote(src),
               username, ip, shellquote(dst)))
    logger.info('begin ingressing data from {} to {}'.format(
        src, dst))
    start = datetime.datetime.now()
    rc = convoy.util.subprocess_with_output(cmd, shell=True)
    diff = datetime.datetime.now() - start
    if rc == 0:
        logger.info(
            'finished ingressing data from {0} to {1} in {2:.2f} sec'.format(
                src, dst, diff.total_seconds()))
    else:
        logger.error(
            'data ingress from {} to {} failed with return code: {}'.format(
                src, dst, rc))


def _multinode_scp_data(src, dst, username, ssh_private_key, rls, eo, mpt):
    # type: (str, str, str, pathlib.Path, dict, str, str, int) -> None
    """Secure copy data to multiple destination nodes simultaneously
    :param str src: source path
    :param str dst: destination path
    :param str username: username
    :param pathlib.Path: ssh private key
    :param dict rls: remote login settings
    :param str eo: extra options
    :param int mpt: max parallel transfers per node
    """
    psrc = pathlib.Path(src)
    if len(rls) == 1 or not psrc.is_dir():
        _scp_data(src, dst, username, ssh_private_key, rls, eo)
        return
    buckets = {}
    files = {}
    rcodes = {}
    for rkey in rls:
        buckets[rkey] = 0
        files[rkey] = []
        rcodes[rkey] = None
    # walk the directory structure
    # 1. construct a set of dirs to create on the remote side
    # 2. binpack files to different nodes
    total_files = 0
    dirs = set()
    for entry in convoy.util.scantree(src):
        rel = pathlib.Path(entry.path).relative_to(psrc)
        sparent = str(pathlib.Path(entry.path).relative_to(psrc).parent)
        if sparent != '.':
            dirs.add(sparent)
        if entry.is_file():
            dstpath = '{}{}/{}'.format(dst, psrc.name, rel)
            # get key of min bucket values
            key = min(buckets, key=buckets.get)
            buckets[key] += entry.stat().st_size
            files[key].append((entry.path, dstpath))
            total_files += 1
    total_size = sum(buckets.values())
    # create remote directories via ssh
    logger.debug('creating remote directories: {}'.format(dirs))
    dirs = ['mkdir -p {}/{}'.format(psrc.name, x) for x in list(dirs)]
    dirs.insert(0, 'cd {}'.format(dst))
    _rls = next(iter(rls.values()))
    ip = _rls.remote_login_ip_address
    port = _rls.remote_login_port
    del _rls
    mkdircmd = ('ssh -o StrictHostKeyChecking=no '
                '-o UserKnownHostsFile=/dev/null -x '
                '-i {} -p {} {}@{} {}'.format(
                    ssh_private_key, port, username, ip,
                    convoy.util.wrap_commands_in_shell(dirs)))
    rc = convoy.util.subprocess_with_output(mkdircmd.split())
    if rc == 0:
        logger.info('remote directories created on {}'.format(dst))
    else:
        logger.error('remote directory creation failed')
        return
    del ip
    del port
    # scp data to multiple nodes simultaneously
    if mpt is None:
        mpt = 1
    logger.info(
        'ingress data: {0:.4f} MiB in {1} files to transfer, using {2} max '
        'parallel transfers per node'.format(
            total_size / 1048576, total_files, mpt))
    logger.info('begin ingressing data from {} to {}'.format(
        src, dst))
    nodekeys = list(buckets.keys())
    threads = []
    start = datetime.datetime.now()
    for i in range(0, len(buckets)):
        nkey = nodekeys[i]
        thr = threading.Thread(
            target=_scp_thread_worker,
            args=(mpt, nkey, rcodes, files[nkey],
                  rls[nkey].remote_login_ip_address,
                  rls[nkey].remote_login_port, username, ssh_private_key, eo)
        )
        threads.append(thr)
        thr.start()
    for i in range(0, len(buckets)):
        threads[i].join()
    diff = datetime.datetime.now() - start
    success = True
    for nkey in rcodes:
        if rcodes[nkey] != 0:
            logger.error('data ingress failed to node: {}'.format(nkey))
            success = False
    if success:
        logger.info(
            'finished ingressing {0:.4f} MB of data in {1} files from {2} to '
            '{3} in {4:.2f} sec ({5:.3f} Mbit/s)'.format(
                total_size / 1048576, total_files, src, dst,
                diff.total_seconds(),
                (total_size * 8 / 1e6) / diff.total_seconds()))


def _scp_thread_worker(
        mpt, node_id, rcodes, files, ip, port, username, ssh_private_key, eo):
    # type: (int, str, dict, list, str, int, str, pathlib.Path, str) -> None
    """Worker thread code for secure copy to a node with a file list
    :param int mpt: max parallel transfers per node
    :param str node_id: node id
    :param dict rcodes: return codes dict
    :param list files: list of files to copy
    :param str ip: ip address
    :param int port: port
    :param str username: username
    :param pathlib.Path: ssh private key
    :param str eo: extra options
    """
    i = 0
    while True:
        procs = []
        for j in range(i, i + mpt):
            if j >= len(files):
                break
            file = files[j]
            src = file[0]
            dst = file[1]
            cmd = ('scp -o StrictHostKeyChecking=no '
                   '-o UserKnownHostsFile=/dev/null -p '
                   '{} -i {} -P {} {} {}@{}:"{}"'.format(
                       eo, ssh_private_key, port, shellquote(src), username,
                       ip, shellquote(dst)))
            procs.append(convoy.util.subprocess_nowait(cmd, shell=True))
        rc = convoy.util.subprocess_wait_all(procs)
        for _rc in rc:
            if _rc != 0:
                logger.error(
                    'data ingress to {} failed with return code: {}'.format(
                        node_id, _rc))
                rcodes[node_id] = _rc
                return
        i += len(procs)
        if i == len(files):
            break
    rcodes[node_id] = 0


def ingress_data(batch_client, config, gv, rls=None):
    # type: (batch.BatchServiceClient, dict, str, dict) -> None
    """Ingresses data into Azure Batch
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param str gv: gluster volume name
    :param dict rls: remote login settings
    """
    try:
        files = config['global_resources']['files']
    except KeyError:
        logger.debug('no files to ingress detected')
        return
    try:
        username = config['pool_specification']['ssh']['username']
    except KeyError:
        username = None
    if rls is None:
        rls = convoy.batch.get_remote_login_settings(batch_client, config)
    for fdict in files:
        src = fdict['source']
        try:
            shared = fdict['destination']['shared_data_volume']
        except KeyError:
            shared = None
        try:
            storage = fdict['destination']['storage_account_settings']
        except KeyError:
            storage = None
        if shared is not None and storage is not None:
            raise RuntimeError(
                'cannot specify both shared data volume and storage for the '
                'destination for source: {}'.format(src))
        if shared is not None:
            if username is None:
                raise RuntimeError(
                    'cannot ingress data to shared data volume without a '
                    'valid ssh user')
            try:
                method = fdict['destination']['data_transfer'][
                    'method'].lower()
            except KeyError:
                raise RuntimeError(
                    'no transfer method specified for data transfer of '
                    'source: {} to {}'.format(src, shared))
            try:
                eo = fdict['destination']['data_transfer']['extra_options']
                if eo is None:
                    eo = ''
            except KeyError:
                eo = ''
            try:
                mpt = fdict['destination']['data_transfer'][
                    'max_parallel_transfers_per_node']
                if mpt is not None and mpt <= 0:
                    mpt = None
            except KeyError:
                mpt = None
            try:
                ssh_private_key = pathlib.Path(
                    fdict['destination']['data_transfer']['ssh_private_key'])
            except KeyError:
                ssh_private_key = None
            # use default name for private key
            if ssh_private_key is None or len(ssh_private_key) == 0:
                ssh_private_key = pathlib.Path(convoy.util._SSH_KEY_PREFIX)
            if not ssh_private_key.exists():
                raise RuntimeError(
                    'ssh private key does not exist at: {}'.format(
                        ssh_private_key))
            # convert shared to actual path
            shared_data_volumes = config['global_resources'][
                'docker_volumes']['shared_data_volumes']
            for key in shared_data_volumes:
                if key == shared:
                    driver = shared_data_volumes[key]['volume_driver']
                    break
            if driver == 'glusterfs':
                if (config['pool_specification']['offer'].lower() ==
                        'ubuntuserver'):
                    dst = '/mnt/batch/tasks/shared/{}/'.format(gv)
                else:
                    dst = '/mnt/resource/batch/tasks/shared/{}/'.format(gv)
            else:
                raise RuntimeError(
                    'data ingress to {} not supported'.format(driver))
            if method == 'scp':
                _scp_data(src, dst, username, ssh_private_key, rls, eo)
            elif method == 'multinode_scp':
                _multinode_scp_data(
                    src, dst, username, ssh_private_key, rls, eo, mpt)
            elif method == 'rsync+ssh':
                raise NotImplementedError()
            else:
                raise RuntimeError(
                    'unknown transfer method: {}'.format(method))
        elif storage is not None:
            # container = fdict['destination']['container']
            raise NotImplementedError()
        else:
            raise RuntimeError(
                'invalid file transfer configuration: {}'.format(fdict))
