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
import logging
import math
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
try:
    from shlex import quote as shellquote
except ImportError:
    from pipes import quote as shellquote
import threading
import time
# local imports
from . import crypto
from . import storage
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_MEGABYTE = 1048576
_MAX_READ_BLOCKSIZE_BYTES = 4194304
_FILE_SPLIT_PREFIX = '_shipyard-'
_GLUSTER_VOLUME = '.gluster/gv0'


def get_gluster_volume():
    # type: (None) -> str
    """Get gluster volume mount suffix
    :rtype: str
    :return: gluster volume mount
    """
    return _GLUSTER_VOLUME


def _process_storage_input_data(config, input_data, on_task):
    # type: (dict, dict, bool) -> str
    """Process Azure storage input data to ingress
    :param dict config: configuration dict
    :param dict input_data: config spec with input_data
    :param bool on_task: if this is originating from a task spec
    :rtype: list
    :return: args to pass to blobxfer script
    """
    try:
        encrypt = config['batch_shipyard']['encryption']['enabled']
    except KeyError:
        encrypt = False
    args = []
    for xfer in input_data:
        storage_settings = config['credentials']['storage'][
            xfer['storage_account_settings']]
        try:
            container = xfer['container']
            if container is not None and len(container) == 0:
                container = None
        except KeyError:
            container = None
        try:
            fshare = xfer['file_share']
            if fshare is not None and len(fshare) == 0:
                fshare = None
        except KeyError:
            fshare = None
        if container is None and fshare is None:
            raise ValueError('container or file_share not specified')
        elif container is not None and fshare is not None:
            raise ValueError(
                'cannot specify both container and file_share at the '
                'same time')
        try:
            eo = xfer['blobxfer_extra_options']
            if eo is None:
                eo = ''
        except KeyError:
            eo = ''
        # configure for file share
        if fshare is not None:
            if '--fileshare' not in eo:
                eo = '--fileshare {}'.format(eo)
            # create saskey for file share with rl perm
            saskey = storage.create_file_share_saskey(
                storage_settings, fshare, 'ingress')
            # set container as fshare
            container = fshare
            del fshare
        else:
            # create saskey for container with rl perm
            saskey = storage.create_blob_container_saskey(
                storage_settings, container, 'ingress')
        try:
            include = xfer['include']
            if include is not None:
                if len(include) == 0:
                    include = ''
                elif len(include) == 1:
                    include = include[0]
                else:
                    raise ValueError(
                        'include for input_data from {}:{} cannot exceed '
                        '1 filter'.format(
                            xfer['storage_account_settings'], container))
            else:
                include = ''
        except KeyError:
            include = ''
        try:
            dst = xfer['destination']
        except KeyError:
            if on_task:
                dst = None
            else:
                raise
        if on_task and dst is None or len(dst) == 0:
            dst = '$AZ_BATCH_TASK_WORKING_DIR'
        # construct argument
        # kind:encrypted:<sa:ep:saskey:container>:include:eo:dst
        if encrypt:
            encstorage = '{}:{}:{}:{}'.format(
                storage_settings['account'], storage_settings['endpoint'],
                saskey, container)
            args.append('"ingress:true:{}:{}:{}:{}"'.format(
                crypto.encrypt_string(encrypt, encstorage, config),
                include, eo, dst))
        else:
            args.append('"ingress:false:{}:{}:{}:{}:{}:{}:{}"'.format(
                storage_settings['account'], storage_settings['endpoint'],
                saskey, container, include, eo, dst))
    return args


def _process_batch_input_data(config, input_data, on_task):
    # type: (dict, dict, bool) -> str
    """Process Azure batch input data to ingress
    :param dict config: configuration dict
    :param dict input_data: config spec with input_data
    :param bool on_task: if this is originating from a task spec
    :rtype: list
    :return: args to pass to blobxfer script
    """
    try:
        encrypt = config['batch_shipyard']['encryption']['enabled']
    except KeyError:
        encrypt = False
    args = []
    for xfer in input_data:
        jobid = xfer['job_id']
        taskid = xfer['task_id']
        try:
            include = xfer['include']
            if include is not None and len(include) == 0:
                include = ''
            else:
                include = ';'.join(include)
        except KeyError:
            include = ''
        if include is None:
            include = ''
        try:
            exclude = xfer['exclude']
            if exclude is not None and len(exclude) == 0:
                exclude = ''
            else:
                exclude = ';'.join(exclude)
        except KeyError:
            exclude = ''
        if exclude is None:
            exclude = ''
        try:
            dst = xfer['destination']
        except KeyError:
            if on_task:
                dst = None
            else:
                raise
        if on_task and dst is None or len(dst) == 0:
            dst = '$AZ_BATCH_TASK_WORKING_DIR'
        creds = crypto.encrypt_string(encrypt, '{};{};{}'.format(
            config['credentials']['batch']['account'],
            config['credentials']['batch']['account_service_url'],
            config['credentials']['batch']['account_key']), config)
        # construct argument
        # encrypt:creds:jobid:taskid:incl:excl:dst
        args.append('"{}:{}:{}:{}:{}:{}:{}"'.format(
            encrypt, creds, jobid, taskid, include, exclude, dst))
    return args


def process_input_data(config, bxfile, spec, on_task=False):
    # type: (dict, tuple, dict, bool) -> str
    """Process input data to ingress
    :param dict config: configuration dict
    :param tuple bxfile: blobxfer script
    :param dict spec: config spec with input_data
    :param bool on_task: if this is originating from a task spec
    :rtype: str
    :return: additonal command
    """
    ret = []
    try:
        input_data = spec['input_data']
        if input_data is not None and len(input_data) > 0:
            for key in input_data:
                if key == 'azure_storage':
                    args = _process_storage_input_data(
                        config, input_data[key], on_task)
                    ret.append(
                        ('set -f; $AZ_BATCH_NODE_SHARED_DIR/{} {}; '
                         'set +f').format(bxfile[0], ' '.join(args)))
                elif key == 'azure_batch':
                    args = _process_batch_input_data(
                        config, input_data[key], on_task)
                    ret.append(
                        ('set -f; docker run --rm -t '
                         '-v $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR '
                         '-w $AZ_BATCH_TASK_WORKING_DIR '
                         '-e "AZ_BATCH_NODE_STARTUP_DIR='
                         '$AZ_BATCH_NODE_STARTUP_DIR" '
                         'alfpark/batch-shipyard:tfm-latest {}; '
                         'set +f'.format(' '.join(args))))
                else:
                    raise ValueError(
                        'unknown input_data method: {}'.format(key))
    except KeyError:
        pass
    if len(ret) > 0:
        return ';'.join(ret)
    else:
        return None


def _process_storage_output_data(config, output_data):
    # type: (dict, dict, bool) -> str
    """Process output data to egress to Azure storage
    :param dict config: configuration dict
    :param dict output_data: config spec with output_data
    :rtype: list
    :return: args to pass to blobxfer script
    """
    try:
        encrypt = config['batch_shipyard']['encryption']['enabled']
    except KeyError:
        encrypt = False
    args = []
    for xfer in output_data:
        storage_settings = config['credentials']['storage'][
            xfer['storage_account_settings']]
        try:
            container = xfer['container']
            if container is not None and len(container) == 0:
                container = None
        except KeyError:
            container = None
        try:
            fshare = xfer['file_share']
            if fshare is not None and len(fshare) == 0:
                fshare = None
        except KeyError:
            fshare = None
        if container is None and fshare is None:
            raise ValueError('container or file_share not specified')
        elif container is not None and fshare is not None:
            raise ValueError(
                'cannot specify both container and file_share at the '
                'same time')
        try:
            eo = xfer['blobxfer_extra_options']
            if eo is None:
                eo = ''
        except KeyError:
            eo = ''
        # configure for file share
        if fshare is not None:
            if '--fileshare' not in eo:
                eo = '--fileshare {}'.format(eo)
            # create saskey for file share with rwdl perm
            saskey = storage.create_file_share_saskey(
                storage_settings, fshare, 'egress', create_share=True)
            # set container as fshare
            container = fshare
            del fshare
        else:
            # create saskey for container with rwdl perm
            saskey = storage.create_blob_container_saskey(
                storage_settings, container, 'egress', create_container=True)
        try:
            include = xfer['include']
            if include is not None:
                if len(include) == 0:
                    include = ''
                elif len(include) == 1:
                    include = include[0]
                else:
                    raise ValueError(
                        'include for output_data from {}:{} cannot exceed '
                        '1 filter'.format(
                            xfer['storage_account_settings'], container))
            else:
                include = ''
        except KeyError:
            include = ''
        try:
            src = xfer['source']
        except KeyError:
            src = None
        if src is None or len(src) == 0:
            src = '$AZ_BATCH_TASK_DIR'
        # construct argument
        # kind:encrypted:<sa:ep:saskey:container>:include:eo:src
        if encrypt:
            encstorage = '{}:{}:{}:{}'.format(
                storage_settings['account'], storage_settings['endpoint'],
                saskey, container)
            args.append('"egress:true:{}:{}:{}:{}"'.format(
                crypto.encrypt_string(encrypt, encstorage, config),
                include, eo, src))
        else:
            args.append('"egress:false:{}:{}:{}:{}:{}:{}:{}"'.format(
                storage_settings['account'], storage_settings['endpoint'],
                saskey, container, include, eo, src))
    return args


def process_output_data(config, bxfile, spec):
    # type: (dict, tuple, dict) -> str
    """Process output data to egress
    :param dict config: configuration dict
    :param tuple bxfile: blobxfer script
    :param dict spec: config spec with input_data
    :rtype: str
    :return: additonal command
    """
    ret = []
    try:
        output_data = spec['output_data']
        if output_data is not None and len(output_data) > 0:
            for key in output_data:
                if key == 'azure_storage':
                    args = _process_storage_output_data(
                        config, output_data[key])
                    ret.append(
                        ('set -f; $AZ_BATCH_NODE_SHARED_DIR/{} {}; '
                         'set +f').format(bxfile[0], ' '.join(args)))
                else:
                    raise ValueError(
                        'unknown output_data method: {}'.format(key))
    except KeyError:
        pass
    if len(ret) > 0:
        return ';'.join(ret)
    else:
        return None


def _singlenode_transfer(
        method, src, dst, rdp, username, ssh_private_key, rls, eo, reo):
    # type: (str, str, str, str, pathlib.Path, dict, str, str) -> None
    """Transfer data to a single node
    :param str src: source path
    :param str dst: destination path
    :param str rdp: relative destination path
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
    # modify dst with relative dest
    if rdp is not None and len(rdp) > 0:
        dst = '{}{}'.format(dst, rdp)
        # create relative path on host
        logger.debug('creating remote directory: {}'.format(dst))
        dirs = ['mkdir -p {}'.format(dst)]
        mkdircmd = ('ssh -T -x -o StrictHostKeyChecking=no '
                    '-o UserKnownHostsFile=/dev/null '
                    '-i {} -p {} {}@{} {}'.format(
                        ssh_private_key, port, username, ip,
                        util.wrap_commands_in_shell(dirs)))
        rc = util.subprocess_with_output(
            mkdircmd, shell=True, suppress_output=True)
        if rc == 0:
            logger.info('remote directories created on {}'.format(dst))
        else:
            logger.error('remote directory creation failed')
            return
        del dirs
    # transfer data
    if method == 'scp':
        cmd = ('scp -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile=/dev/null -p '
               '{} {} -i {} -P {} . {}@{}:"{}"'.format(
                   eo, recursive, ssh_private_key.resolve(), port,
                   username, ip, shellquote(dst)))
    elif method == 'rsync+ssh':
        cmd = ('rsync {} {} -e "ssh -T -x -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile=/dev/null '
               '{} -i {} -p {}" . {}@{}:"{}"'.format(
                   reo, recursive, eo, ssh_private_key.resolve(), port,
                   username, ip, shellquote(dst)))
    else:
        raise ValueError('Unknown transfer method: {}'.format(method))
    logger.info('begin ingressing data from {} to {}'.format(
        src, dst))
    start = datetime.datetime.now()
    rc = util.subprocess_with_output(cmd, shell=True, cwd=src)
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
        method, src, src_incl, src_excl, dst, rdp, username, ssh_private_key,
        rls, eo, reo, mpt, split):
    # type: (str, str, list, list, str, str, str, pathlib.Path, dict, str,
    #        str, int, int) -> None
    """Transfer data to multiple destination nodes simultaneously
    :param str method: transfer method
    :param str src: source path
    :param list src_incl: source include
    :param list src_excl: source exclude
    :param str dst: destination path
    :param str rdp: relative destination path
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
    if rdp is not None:
        dirs.add(rdp)
    for entry in util.scantree(src):
        rel = pathlib.Path(entry.path).relative_to(psrc)
        sparent = str(pathlib.Path(entry.path).relative_to(psrc).parent)
        if entry.is_file():
            srel = str(rel)
            # check filters
            if src_excl is not None:
                inc = not any([fnmatch.fnmatch(srel, x) for x in src_excl])
            else:
                inc = True
            if src_incl is not None:
                inc = any([fnmatch.fnmatch(srel, x) for x in src_incl])
            if not inc:
                logger.debug('skipping file {} due to filters'.format(
                    entry.path))
                continue
            if rdp is None:
                dstpath = '{}{}'.format(dst, rel)
            else:
                dstpath = '{}{}/{}'.format(dst, rdp, rel)
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
        # add directory to create
        if sparent != '.':
            if rdp is None:
                dirs.add(sparent)
            else:
                dirs.add('{}/{}'.format(rdp, sparent))
    total_size = sum(buckets.values())
    if total_files == 0:
        logger.error('no files to ingress')
        return
    # create remote directories via ssh
    if len(dirs) == 0:
        logger.debug('no remote directories to create')
    else:
        logger.debug('creating remote directories: {}'.format(dirs))
        dirs = ['mkdir -p {}'.format(x) for x in list(dirs)]
        dirs.insert(0, 'cd {}'.format(dst))
        _rls = next(iter(rls.values()))
        ip = _rls.remote_login_ip_address
        port = _rls.remote_login_port
        del _rls
        mkdircmd = ('ssh -T -x -o StrictHostKeyChecking=no '
                    '-o UserKnownHostsFile=/dev/null '
                    '-i {} -p {} {}@{} {}'.format(
                        ssh_private_key, port, username, ip,
                        util.wrap_commands_in_shell(dirs)))
        rc = util.subprocess_with_output(
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
    logger.info('begin ingressing data from {} to {}'.format(src, dst))
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
        procs.append(util.subprocess_nowait(cmd, shell=True))
    else:
        proc = util.subprocess_attach_stdin(cmd, shell=True)
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
        plist, n, rc = util.subprocess_wait_multi(psprocs, procs)
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
                               util.wrap_commands_in_shell(cmds)))
                procs.append(
                    util.subprocess_nowait(joincmd, shell=True))
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
    return thr


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
    cmd = [
        ('blobxfer {} {} {} --endpoint {} --upload --no-progressbar '
         '{} {}').format(
             storage_settings['account'], container, rsrc,
             storage_settings['endpoint'],
             '--include \'{}\''.format(src_incl)
             if src_incl is not None else '',
             eo)
    ]
    logger.info('begin ingressing data from {} to container {}'.format(
        src, container))
    proc = util.subprocess_nowait_pipe_stdout(
        util.wrap_commands_in_shell(cmd), shell=True, cwd=cwd, env=env)
    stdout = proc.communicate()[0]
    if proc.returncode != 0:
        logger.error(stdout.decode('utf8'))
        logger.error('data ingress failed from {} to container {}'.format(
            src, container))
    else:
        logger.info(stdout.decode('utf8'))


def wait_for_storage_threads(storage_threads):
    # type: (list) -> None
    """Wait for storage processes to complete
    :param list storage_threads: list of storage threads
    """
    i = 0
    nthreads = len(storage_threads)
    while nthreads > 0:
        alive = sum(thr.is_alive() for thr in storage_threads)
        if alive > 0:
            i += 1
            if i % 10 == 0:
                i = 0
                logger.debug(
                    'waiting for Azure Blob Storage transfer processes '
                    'to complete: {} active, {} completed'.format(
                        alive, nthreads - alive))
            time.sleep(1)
        else:
            for thr in storage_threads:
                thr.join()
            if nthreads > 0:
                logger.info('Azure Blob/File Storage transfer completed')
            break


def ingress_data(
        batch_client, config, rls=None, kind=None, current_dedicated=None):
    # type: (batch.BatchServiceClient, dict, dict, str, int) -> list
    """Ingresses data into Azure Batch
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param dict rls: remote login settings
    :param str kind: 'all', 'shared', or 'storage'
    :param int current_dedicated: current dedicated
    :rtype: list
    :return: list of storage threads
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
    storage_threads = []
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
        try:
            rdp = fdict['destination']['relative_destination_path']
            if rdp is not None:
                rdp = rdp.lstrip('/').rstrip('/')
        except KeyError:
            rdp = None
        if shared is not None and storage is not None:
            raise RuntimeError(
                'cannot specify both shared data volume and storage for the '
                'destination for source: {}'.format(src))
        direct_single_node = False
        if rdp is not None:
            if storage is not None:
                raise RuntimeError(
                    'cannot specify a relative destination path for ingress '
                    'to storage; use the --collate option in blobxfer '
                    'instead.')
            # check if this is going to a single vm
            if shared is None:
                if current_dedicated == 1:
                    direct_single_node = True
                elif current_dedicated is None:
                    raise ValueError('current_dedicated is not set')
                else:
                    raise RuntimeError(
                        'Cannot ingress data directly into compute node '
                        'host for pools with more than one node. Please use '
                        'a shared data volume as the ingress destination '
                        'instead.')
            else:
                if len(rdp) == 0:
                    rdp = None
        if shared is not None or direct_single_node:
            if rls is None:
                logger.warning(
                    'skipping data ingress from {} to {} for pool with no '
                    'remote login settings or non-existent pool'.format(
                        src, shared))
                continue
            if kind == 'storage':
                logger.warning(
                    'skipping data ingress from {} to {} for pool as ingress '
                    'to shared file system not specified'.format(src, shared))
                continue
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
                    crypto.get_ssh_key_prefix())
            if not ssh_private_key.exists():
                raise RuntimeError(
                    'ssh private key does not exist at: {}'.format(
                        ssh_private_key))
            logger.debug('using ssh_private_key from: {}'.format(
                ssh_private_key))
            # set base dst path
            if (config['pool_specification']['offer'].lower() ==
                    'ubuntuserver'):
                dst = '/mnt/batch/tasks/'
            else:
                dst = '/mnt/resource/batch/tasks/'
            # convert shared to actual path
            if not direct_single_node:
                shared_data_volumes = config['global_resources'][
                    'docker_volumes']['shared_data_volumes']
                for key in shared_data_volumes:
                    if key == shared:
                        driver = shared_data_volumes[key]['volume_driver']
                        break
                if driver == 'glusterfs':
                    dst = '{}{}/'.format(dst, _GLUSTER_VOLUME)
                else:
                    raise RuntimeError(
                        'data ingress to {} not supported'.format(driver))
            if method == 'scp' or method == 'rsync+ssh':
                # split/source include/exclude will force multinode
                # transfer with mpt=1
                if (split is not None or src_incl is not None or
                        src_excl is not None):
                    _multinode_transfer(
                        'multinode_' + method, src, src_incl, src_excl, dst,
                        rdp, username, ssh_private_key, rls, eo, reo, 1, split)
                else:
                    _singlenode_transfer(
                        method, src, dst, rdp, username, ssh_private_key,
                        rls, eo, reo)
            elif method == 'multinode_scp' or method == 'multinode_rsync+ssh':
                _multinode_transfer(
                    method, src, src_incl, src_excl, dst, rdp, username,
                    ssh_private_key, rls, eo, reo, mpt, split)
            else:
                raise RuntimeError(
                    'unknown transfer method: {}'.format(method))
        elif storage is not None:
            if kind == 'shared':
                logger.warning(
                    'skipping data ingress from {} to {} for pool as ingress '
                    'to Azure Blob/File Storage not specified'.format(
                        src, storage))
                continue
            try:
                container = fdict['destination']['data_transfer']['container']
                if container is not None and len(container) == 0:
                    container = None
            except KeyError:
                container = None
            try:
                fshare = fdict['destination']['data_transfer']['file_share']
                if fshare is not None and len(fshare) == 0:
                    fshare = None
            except KeyError:
                fshare = None
            if container is None and fshare is None:
                raise ValueError('container or file_share not specified')
            elif container is not None and fshare is not None:
                raise ValueError(
                    'cannot specify both container and file_share at the '
                    'same time for source {}'.format(src))
            try:
                eo = fdict['destination']['data_transfer'][
                    'blobxfer_extra_options']
                if eo is None:
                    eo = ''
            except KeyError:
                eo = ''
            # append appropriate option for fshare
            if fshare is not None:
                if '--fileshare' not in eo:
                    eo = '--fileshare {}'.format(eo)
                # set container as fshare
                container = fshare
                del fshare
            if src_incl is not None:
                if len(src_incl) > 1:
                    raise ValueError(
                        'include can only be a maximum of one filter for '
                        'ingress to Azure Blob/File Storage')
                # peel off first into var
                src_incl = src_incl[0]
            if src_excl is not None:
                raise ValueError(
                    'exclude cannot be specified for ingress to Azure '
                    'Blob/File Storage')
            thr = _azure_blob_storage_transfer(
                config['credentials']['storage'][storage], container, src,
                src_incl, eo)
            storage_threads.append(thr)
        else:
            raise RuntimeError(
                'invalid file transfer configuration: {}'.format(fdict))
    return storage_threads
