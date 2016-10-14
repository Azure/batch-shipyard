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
import fnmatch
import logging
import math
import os
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
import convoy.batch
import convoy.util

# create logger
logger = logging.getLogger(__name__)
convoy.util.setup_logger(logger)
# global defines
_MEGABYTE = 1048576
_MAX_READ_BLOCKSIZE_BYTES = 4194304
_FILE_SPLIT_PREFIX = '_shipyard-'


def _singlenode_transfer(
        method, src, dst, username, ssh_private_key, rls, eo, reo):
    # type: (str, str, str, pathlib.Path, dict, str, str) -> None
    """Transfer data to a single node
    :param str src: source path
    :param str dst: destination path
    :param str username: username
    :param pathlib.Path: ssh private key
    :param dict rls: remote login settings
    :param str eo: ssh extra options
    :param str reo: rsync extra options
    """
    recursive = '-r' if pathlib.Path(src).is_dir() else ''
    _rls = next(iter(rls.values()))
    ip = _rls.remote_login_ip_address
    port = _rls.remote_login_port
    del _rls
    if method == 'scp':
        cmd = ('scp -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile=/dev/null -p '
               '{} {} -i {} -P {} {} {}@{}:"{}"'.format(
                   eo, recursive, ssh_private_key, port, shellquote(src),
                   username, ip, shellquote(dst)))
    elif method == 'rsync+ssh':
        cmd = ('rsync {} {} -e "ssh -T -x -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile=/dev/null '
               '{} -i {} -p {}" {} {}@{}:"{}"'.format(
                   reo, recursive, eo, ssh_private_key, port, shellquote(src),
                   username, ip, shellquote(dst)))
    else:
        raise ValueError('Unknown transfer method: {}'.format(method))
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


def _multinode_transfer(
        method, src, src_incl, src_excl, dst, username, ssh_private_key, rls,
        eo, reo, mpt, split):
    # type: (str, str, list, list, str, str, pathlib.Path, dict, str, str,
    #        int, int) -> None
    """Transfer data to multiple destination nodes simultaneously
    :param str method: transfer method
    :param str src: source path
    :param list src_incl: source include
    :param list src_excl: source exclude
    :param str dst: destination path
    :param str username: username
    :param pathlib.Path: ssh private key
    :param dict rls: remote login settings
    :param str eo: extra options
    :param str reo: rsync extra options
    :param int mpt: max parallel transfers per node
    :param int split: split files on MB size
    """
    psrc = pathlib.Path(src)
    # if source isn't a directory, convert it using src_incl
    if not psrc.is_dir():
        src_excl = None
        src_incl = [src]
        src = str(psrc.parent)
        psrc = psrc.parent
    # if split is specified, force to multinode_scp
    if split is not None and method != 'multinode_scp':
        logger.warning('forcing transfer method to multinode_scp with split')
        method = 'multinode_scp'
    buckets = {}
    files = {}
    rcodes = {}
    spfiles = []
    spfiles_count = {}
    spfiles_count_lock = threading.Lock()
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
            # check filters
            if src_excl is not None:
                inc = not any(
                    [fnmatch.fnmatch(entry.path, x) for x in src_excl])
            else:
                inc = True
            if src_incl is not None:
                inc = any([fnmatch.fnmatch(entry.path, x) for x in src_incl])
            if not inc:
                logger.debug('skipping file {} due to filters'.format(
                    entry.path))
                continue
            dstpath = '{}{}/{}'.format(dst, psrc.name, rel)
            # get key of min bucket values
            fsize = entry.stat().st_size
            if split is not None and fsize > split:
                nsplits = int(math.ceil(fsize / split))
                lpad = int(math.log10(nsplits)) + 1
                spfiles.append(dstpath)
                spfiles_count[dstpath] = nsplits
                n = 0
                curr = 0
                while True:
                    end = curr + split
                    if end > fsize:
                        end = fsize
                    key = min(buckets, key=buckets.get)
                    buckets[key] += (end - curr)
                    if n == 0:
                        dstfname = dstpath
                    else:
                        dstfname = '{}.{}{}'.format(
                            dstpath, _FILE_SPLIT_PREFIX, str(n).zfill(lpad))
                    files[key].append((entry.path, dstfname, curr, end))
                    if end == fsize:
                        break
                    curr = end
                    n += 1
            else:
                key = min(buckets, key=buckets.get)
                buckets[key] += fsize
                files[key].append((entry.path, dstpath, None, None))
            total_files += 1
    total_size = sum(buckets.values())
    if total_files == 0:
        logger.error('no files to ingress')
        return
    # create remote directories via ssh
    logger.debug('creating remote directories: {}'.format(dirs))
    dirs = ['mkdir -p {}/{}'.format(psrc.name, x) for x in list(dirs)]
    dirs.insert(0, 'cd {}'.format(dst))
    _rls = next(iter(rls.values()))
    ip = _rls.remote_login_ip_address
    port = _rls.remote_login_port
    del _rls
    mkdircmd = ('ssh -T -x -o StrictHostKeyChecking=no '
                '-o UserKnownHostsFile=/dev/null '
                '-i {} -p {} {}@{} {}'.format(
                    ssh_private_key, port, username, ip,
                    convoy.util.wrap_commands_in_shell(dirs)))
    rc = convoy.util.subprocess_with_output(
        mkdircmd, shell=True, suppress_output=True)
    if rc == 0:
        logger.info('remote directories created on {}'.format(dst))
    else:
        logger.error('remote directory creation failed')
        return
    del ip
    del port
    logger.info(
        'ingress data: {0:.4f} MiB in {1} files to transfer, using {2} max '
        'parallel transfers per node'.format(
            total_size / _MEGABYTE, total_files, mpt))
    logger.info('begin ingressing data from {} to {}'.format(
        src, dst))
    nodekeys = list(buckets.keys())
    threads = []
    start = datetime.datetime.now()
    for i in range(0, len(buckets)):
        nkey = nodekeys[i]
        thr = threading.Thread(
            target=_multinode_thread_worker,
            args=(method, mpt, nkey, rcodes, files[nkey],
                  spfiles_count, spfiles_count_lock,
                  rls[nkey].remote_login_ip_address,
                  rls[nkey].remote_login_port, username, ssh_private_key, eo,
                  reo)
        )
        threads.append(thr)
        thr.start()
    for i in range(0, len(buckets)):
        threads[i].join()
    diff = datetime.datetime.now() - start
    del threads
    success = True
    for nkey in rcodes:
        if rcodes[nkey] != 0:
            logger.error('data ingress failed to node: {}'.format(nkey))
            success = False
    if success:
        logger.info(
            'finished ingressing {0:.4f} MB of data in {1} files from {2} to '
            '{3} in {4:.2f} sec ({5:.3f} Mbit/s)'.format(
                total_size / _MEGABYTE, total_files, src, dst,
                diff.total_seconds(),
                (total_size * 8 / 1e6) / diff.total_seconds()))


def _spawn_next_transfer(
        method, file, ip, port, username, ssh_private_key, eo, reo,
        procs, psprocs, psdst):
    # type: (str, tuple, str, int, str, pathlib.Path, str, str, list,
    #        list, list) -> None
    """Spawn the next transfer given a file tuple
    :param str method: transfer method
    :param tuple file: file tuple
    :param str ip: ip address
    :param int port: port
    :param str username: username
    :param pathlib.Path: ssh private key
    :param str eo: extra options
    :param str reo: rsync extra options
    :param list procs: process list
    :param list psprocs: split files process list
    :param list psdst: split files dstpath list
    """
    src = file[0]
    dst = file[1]
    begin = file[2]
    end = file[3]
    if method == 'multinode_scp':
        if begin is None and end is None:
            cmd = ('scp -o StrictHostKeyChecking=no '
                   '-o UserKnownHostsFile=/dev/null -p '
                   '{} -i {} -P {} {} {}@{}:"{}"'.format(
                       eo, ssh_private_key, port, shellquote(src),
                       username, ip, shellquote(dst)))
        else:
            cmd = ('ssh -T -x -o StrictHostKeyChecking=no '
                   '-o UserKnownHostsFile=/dev/null '
                   '{} -i {} -p {} {}@{} \'cat > "{}"\''.format(
                       eo, ssh_private_key, port,
                       username, ip, shellquote(dst)))
    elif method == 'multinode_rsync+ssh':
        if begin is not None or end is not None:
            raise RuntimeError('cannot rsync with file offsets')
        cmd = ('rsync {} -e "ssh -T -x -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile=/dev/null '
               '{} -i {} -p {}" {} {}@{}:"{}"'.format(
                   reo, eo, ssh_private_key, port, shellquote(src),
                   username, ip, shellquote(dst)))
    else:
        raise ValueError('Unknown transfer method: {}'.format(method))
    if begin is None and end is None:
        procs.append(convoy.util.subprocess_nowait(cmd, shell=True))
    else:
        proc = convoy.util.subprocess_attach_stdin(cmd, shell=True)
        with open(src, 'rb') as f:
            f.seek(begin, 0)
            curr = begin
            while curr < end:
                buf = f.read(_MAX_READ_BLOCKSIZE_BYTES)
                if buf is None or len(buf) == 0:
                    break
                proc.stdin.write(buf)
                curr += len(buf)
            proc.stdin.close()
        psprocs.append(proc)
        dstsp = dst.split('.')
        if dstsp[-1].startswith(_FILE_SPLIT_PREFIX):
            dstpath = '.'.join(dstsp[:-1])
        else:
            dstpath = dst
        psdst.append(dstpath)


def _multinode_thread_worker(
        method, mpt, node_id, rcodes, files, spfiles_count,
        spfiles_count_lock, ip, port, username, ssh_private_key, eo, reo):
    # type: (str, int, str, dict, list, dict, threading.Lock, str, int, str,
    #        pathlib.Path, str, str) -> None
    """Worker thread code for data transfer to a node with a file list
    :param str method: transfer method
    :param int mpt: max parallel transfers per node
    :param str node_id: node id
    :param dict rcodes: return codes dict
    :param list files: list of files to copy
    :param dict spfiles_count: split files count dict
    :param threading.Lock spfiles_count_lock: split files count lock
    :param str ip: ip address
    :param int port: port
    :param str username: username
    :param pathlib.Path: ssh private key
    :param str eo: extra options
    :param str reo: rsync extra options
    """
    procs = []
    psprocs = []
    psdst = []
    completed = 0
    i = 0
    while completed != len(files):
        xfers = len(procs) + len(psprocs)
        while xfers < mpt and i < len(files):
            file = files[i]
            _spawn_next_transfer(
                method, file, ip, port, username, ssh_private_key, eo, reo,
                procs, psprocs, psdst)
            xfers = len(procs) + len(psprocs)
            i += 1
        plist, n, rc = convoy.util.subprocess_wait_multi(psprocs, procs)
        if rc != 0:
            logger.error(
                'data ingress to {} failed with return code: {}'.format(
                    node_id, rc))
            rcodes[node_id] = rc
            return
        if plist == psprocs:
            dstpath = psdst[n]
            del psdst[n]
            del psprocs[n]
            join = False
            with spfiles_count_lock:
                spfiles_count[dstpath] = spfiles_count[dstpath] - 1
                if spfiles_count[dstpath] == 0:
                    join = True
            if join:
                logger.debug('joining files on compute node to {}'.format(
                    dstpath))
                cmds = [
                    'cat {}.* >> {}'.format(dstpath, dstpath),
                    'rm -f {}.*'.format(dstpath)
                ]
                joincmd = ('ssh -T -x -o StrictHostKeyChecking=no '
                           '-o UserKnownHostsFile=/dev/null '
                           '-i {} -p {} {}@{} {}'.format(
                               ssh_private_key, port, username, ip,
                               convoy.util.wrap_commands_in_shell(cmds)))
                procs.append(
                    convoy.util.subprocess_nowait(
                        joincmd, shell=True, suppress_output=True))
            else:
                completed += 1
        else:
            del procs[n]
            completed += 1
    rcodes[node_id] = 0


def _azure_blob_storage_transfer(
        storage_settings, container, src, src_incl, eo):
    # type: (dict, str, str, str, str) -> None
    """Initiate an azure blob storage transfer
    :param dict storage_settings: storage settings
    :param str container: container to transfer to
    :param str src: source directory
    :param str src_incl: source include filter
    :param str eo: blobxfer extra options
    """
    thr = threading.Thread(
        target=_wrap_blobxfer_subprocess,
        args=(storage_settings, container, src, src_incl, eo)
    )
    thr.start()


def _wrap_blobxfer_subprocess(storage_settings, container, src, src_incl, eo):
    # type: (dict, str, str, str, str) -> None
    """Wrapper function for blobxfer
    :param dict storage_settings: storage settings
    :param str container: container to transfer to
    :param str src: source directory
    :param str src_incl: source include filter
    :param str eo: blobxfer extra options
    """
    psrc = pathlib.Path(src)
    cwd = str(psrc.parent)
    rsrc = psrc.relative_to(psrc.parent)
    env = os.environ.copy()
    env['BLOBXFER_STORAGEACCOUNTKEY'] = storage_settings['account_key']
    cmd = ['blobxfer {} {} {} --upload --no-progressbar {} {}'.format(
        storage_settings['account'], container, rsrc,
        '--include \'{}\''.format(src_incl) if src_incl is not None else '',
        eo)]
    logger.info('begin ingressing data from {} to container {}'.format(
        src, container))
    proc = convoy.util.subprocess_nowait_pipe_stdout(
        convoy.util.wrap_commands_in_shell(cmd), shell=True, cwd=cwd, env=env)
    stdout = proc.communicate()[0]
    if proc.returncode != 0:
        logger.error(stdout.decode('utf8'))
        logger.error('data ingress failed from {} to container {}'.format(
            src, container))
    else:
        logger.info(stdout.decode('utf8'))


def ingress_data(batch_client, config, rls=None):
    # type: (batch.BatchServiceClient, dict, dict) -> None
    """Ingresses data into Azure Batch
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
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
    for fdict in files:
        src = fdict['source']['path']
        try:
            src_incl = fdict['source']['include']
            if src_incl is not None and len(src_incl) == 0:
                src_incl = None
        except KeyError:
            src_incl = None
        try:
            src_excl = fdict['source']['exclude']
            if src_excl is not None and len(src_excl) == 0:
                src_excl = None
        except KeyError:
            src_excl = None
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
                eo = fdict['destination']['data_transfer'][
                    'scp_ssh_extra_options']
                if eo is None:
                    eo = ''
            except KeyError:
                eo = ''
            try:
                reo = fdict['destination']['data_transfer'][
                    'rsync_extra_options']
                if reo is None:
                    reo = ''
            except KeyError:
                reo = ''
            try:
                mpt = fdict['destination']['data_transfer'][
                    'max_parallel_transfers_per_node']
                if mpt is not None and mpt <= 0:
                    mpt = None
            except KeyError:
                mpt = None
            # ensure valid mpt number
            if mpt is None:
                mpt = 1
            try:
                split = fdict['destination']['data_transfer'][
                    'split_files_megabytes']
                if split is not None and split <= 0:
                    split = None
                # convert to bytes
                if split is not None:
                    split <<= 20
            except KeyError:
                split = None
            try:
                ssh_private_key = pathlib.Path(
                    fdict['destination']['data_transfer']['ssh_private_key'])
            except KeyError:
                # use default name for private key
                ssh_private_key = pathlib.Path(
                    convoy.util.get_ssh_key_prefix())
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
                    dst = '/mnt/batch/tasks/shared/{}/'.format(
                        convoy.batch.get_gluster_volume())
                else:
                    dst = '/mnt/resource/batch/tasks/shared/{}/'.format(
                        convoy.batch.get_gluster_volume())
            else:
                raise RuntimeError(
                    'data ingress to {} not supported'.format(driver))
            if rls is None:
                rls = convoy.batch.get_remote_login_settings(
                    batch_client, config)
            if method == 'scp' or method == 'rsync+ssh':
                # split/source include/exclude will force multinode
                # transfer with mpt=1
                if (split is not None or src_incl is not None or
                        src_excl is not None):
                    _multinode_transfer(
                        'multinode_' + method, src, src_incl, src_excl, dst,
                        username, ssh_private_key, rls, eo, reo, 1, split)
                else:
                    _singlenode_transfer(
                        method, src, dst, username, ssh_private_key, rls, eo,
                        reo)
            elif method == 'multinode_scp' or method == 'multinode_rsync+ssh':
                _multinode_transfer(
                    method, src, src_incl, src_excl, dst, username,
                    ssh_private_key, rls, eo, reo, mpt, split)
            else:
                raise RuntimeError(
                    'unknown transfer method: {}'.format(method))
        elif storage is not None:
            try:
                container = fdict['destination']['data_transfer']['container']
                if container is not None and len(container) == 0:
                    container = None
            except KeyError:
                container = None
            if container is None:
                raise ValueError('container is invalid')
            if src_incl is not None:
                if len(src_incl) > 1:
                    raise ValueError(
                        'include can only be a maximum of one filter for '
                        'ingress to Azure Blob Storage')
                # peel off first into var
                src_incl = src_incl[0]
            if src_excl is not None:
                raise ValueError(
                    'exclude cannot be specified for ingress to Azure Blob '
                    'Storage')
            try:
                eo = fdict['destination']['data_transfer'][
                    'blobxfer_extra_options']
                if eo is None:
                    eo = ''
            except KeyError:
                eo = ''
            _azure_blob_storage_transfer(
                config['credentials']['storage'][storage], container, src,
                src_incl, eo)
        else:
            raise RuntimeError(
                'invalid file transfer configuration: {}'.format(fdict))
