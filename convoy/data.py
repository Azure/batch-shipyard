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
from . import settings
from . import storage
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_MEGABYTE = 1048576
_MAX_READ_BLOCKSIZE_BYTES = 4194304
_FILE_SPLIT_PREFIX = '_shipyard-'


def _process_storage_input_data(config, input_data, on_task):
    # type: (dict, dict, bool) -> str
    """Process Azure storage input data to ingress
    :param dict config: configuration dict
    :param dict input_data: config spec with input_data
    :param bool on_task: if this is originating from a task spec
    :rtype: list
    :return: args to pass to blobxfer script
    """
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    args = []
    for xfer in input_data:
        storage_settings = settings.credentials_storage(
            config, settings.data_storage_account_settings(xfer))
        container = settings.data_container(xfer)
        fshare = settings.data_file_share(xfer)
        if container is None and fshare is None:
            raise ValueError('container or file_share not specified')
        elif container is not None and fshare is not None:
            raise ValueError(
                'cannot specify both container and file_share at the '
                'same time')
        eo = settings.data_blobxfer_extra_options(xfer)
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
        include = settings.data_include(xfer, True)
        dst = settings.input_data_destination(xfer, on_task)
        # construct argument
        # kind:encrypted:<sa:ep:saskey:container>:include:eo:dst
        creds = crypto.encrypt_string(
            encrypt,
            '{}:{}:{}:{}'.format(
                storage_settings.account, storage_settings.endpoint,
                saskey, container),
            config)
        args.append('"ingress:{}:{}:{}:{}:{}"'.format(
            encrypt, creds, include, eo, dst))
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
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    args = []
    for xfer in input_data:
        jobid = settings.input_data_job_id(xfer)
        taskid = settings.input_data_task_id(xfer)
        include = settings.data_include(xfer, False)
        exclude = settings.data_exclude(xfer)
        dst = settings.input_data_destination(xfer, on_task)
        bc = settings.credentials_batch(config)
        creds = crypto.encrypt_string(
            encrypt,
            '{};{};{}'.format(
                bc.account, bc.account_service_url, bc.account_key),
            config)
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
        input_data = settings.input_data(spec)
        if util.is_not_empty(input_data):
            for key in input_data:
                if key == 'azure_storage':
                    args = _process_storage_input_data(
                        config, input_data[key], on_task)
                    ret.append(
                        ('set -f; $AZ_BATCH_NODE_STARTUP_DIR/wd/{} {}; '
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
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    args = []
    for xfer in output_data:
        storage_settings = settings.credentials_storage(
            config, settings.data_storage_account_settings(xfer))
        container = settings.data_container(xfer)
        fshare = settings.data_file_share(xfer)
        if container is None and fshare is None:
            raise ValueError('container or file_share not specified')
        elif container is not None and fshare is not None:
            raise ValueError(
                'cannot specify both container and file_share at the '
                'same time')
        eo = settings.data_blobxfer_extra_options(xfer)
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
        include = settings.data_include(xfer, True)
        src = settings.output_data_source(xfer)
        # construct argument
        # kind:encrypted:<sa:ep:saskey:container>:include:eo:src
        creds = crypto.encrypt_string(
            encrypt,
            '{}:{}:{}:{}'.format(
                storage_settings.account, storage_settings.endpoint,
                saskey, container),
            config)
        args.append('"egress:{}:{}:{}:{}:{}"'.format(
            encrypt, creds, include, eo, src))
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
        output_data = settings.output_data(spec)
        if util.is_not_empty(output_data):
            for key in output_data:
                if key == 'azure_storage':
                    args = _process_storage_output_data(
                        config, output_data[key])
                    ret.append(
                        ('set -f; $AZ_BATCH_NODE_STARTUP_DIR/wd/{} {}; '
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


def _singlenode_transfer(dest, src, dst, username, ssh_private_key, rls):
    # type: (DestinationSettings, str, str, pathlib.Path, dict) -> None
    """Transfer data to a single node
    :param DestinationSettings dest: destination settings
    :param str src: source path
    :param str dst: destination path
    :param str username: username
    :param pathlib.Path: ssh private key
    :param dict rls: remote login settings
    """
    # get remote settings
    _rls = next(iter(rls.values()))
    ip = _rls.remote_login_ip_address
    port = _rls.remote_login_port
    del _rls
    # modify dst with relative dest
    if util.is_not_empty(dest.relative_destination_path):
        dst = '{}{}'.format(dst, dest.relative_destination_path)
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
    # determine if recursive flag must be set
    psrc = pathlib.Path(src)
    recursive = '-r' if psrc.is_dir() else ''
    # set command source path and adjust dst path
    if recursive:
        cmdsrc = '.'
    else:
        cmdsrc = shellquote(src)
    # transfer data
    if dest.data_transfer.method == 'scp':
        cmd = ('scp -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile=/dev/null -p '
               '{} {} -i {} -P {} {} {}@{}:"{}"'.format(
                   dest.data_transfer.scp_ssh_extra_options, recursive,
                   ssh_private_key.resolve(), port, cmdsrc,
                   username, ip, shellquote(dst)))
    elif dest.data_transfer.method == 'rsync+ssh':
        cmd = ('rsync {} {} -e "ssh -T -x -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile=/dev/null '
               '{} -i {} -p {}" {} {}@{}:"{}"'.format(
                   dest.data_transfer.rsync_extra_options, recursive,
                   dest.data_transfer.scp_ssh_extra_options,
                   ssh_private_key.resolve(), port,
                   cmdsrc, username, ip, shellquote(dst)))
    else:
        raise ValueError('Unknown transfer method: {}'.format(
            dest.data_transfer.method))
    logger.info('begin ingressing data from {} to {}'.format(
        src, dst))
    start = datetime.datetime.now()
    rc = util.subprocess_with_output(
        cmd, shell=True, cwd=src if recursive else None)
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
        method, dest, source, dst, username, ssh_private_key, rls, mpt):
    # type: (str, DestinationSettings, SourceSettings, str, str,
    #        pathlib.Path, dict, int) -> None
    """Transfer data to multiple destination nodes simultaneously
    :param str method: transfer method
    :param DestinationSettings dest: destination settings
    :param SourceSettings source: source settings
    :param str dst: destination path
    :param str username: username
    :param pathlib.Path: ssh private key
    :param dict rls: remote login settings
    :param int mpt: max parallel transfers per node
    """
    src = source.path
    src_incl = source.include
    src_excl = source.exclude
    psrc = pathlib.Path(src)
    # if source isn't a directory, convert it using src_incl
    if not psrc.is_dir():
        src_excl = None
        src_incl = [src]
        src = str(psrc.parent)
        psrc = psrc.parent
    # if split is specified, force to multinode_scp
    if (dest.data_transfer.split_files_megabytes is not None and
            method != 'multinode_scp'):
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
    if dest.relative_destination_path is not None:
        dirs.add(dest.relative_destination_path)
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
            if dest.relative_destination_path is None:
                dstpath = '{}{}'.format(dst, rel)
            else:
                dstpath = '{}{}/{}'.format(
                    dst, dest.relative_destination_path, rel)
            # get key of min bucket values
            fsize = entry.stat().st_size
            if (dest.data_transfer.split_files_megabytes is not None and
                    fsize > dest.data_transfer.split_files_megabytes):
                nsplits = int(math.ceil(
                    fsize / dest.data_transfer.split_files_megabytes))
                lpad = int(math.log10(nsplits)) + 1
                spfiles.append(dstpath)
                spfiles_count[dstpath] = nsplits
                n = 0
                curr = 0
                while True:
                    end = curr + dest.data_transfer.split_files_megabytes
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
            if dest.relative_destination_path is None:
                dirs.add(sparent)
            else:
                dirs.add('{}/{}'.format(
                    dest.relative_destination_path, sparent))
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
                  rls[nkey].remote_login_port, username, ssh_private_key,
                  dest.data_transfer.scp_ssh_extra_options,
                  dest.data_transfer.rsync_extra_options)
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


def _azure_blob_storage_transfer(storage_settings, container, source, eo):
    # type: (StorageCredentialsSettings, str, SourceSettings, str) -> None
    """Initiate an azure blob storage transfer
    :param StorageCredentialsSettings storage_settings: storage settings
    :param str container: container to transfer to
    :param SourceSettings source: source settings
    :param str eo: blobxfer extra options
    """
    thr = threading.Thread(
        target=_wrap_blobxfer_subprocess,
        args=(storage_settings, container, source, eo)
    )
    thr.start()
    return thr


def _wrap_blobxfer_subprocess(storage_settings, container, source, eo):
    # type: (StorageCredentialsSettings, str, SourceSettings, str) -> None
    """Wrapper function for blobxfer
    :param StorageCredentialsSettings storage_settings: storage settings
    :param str container: container to transfer to
    :param SourceSettings source: source settings
    :param str eo: blobxfer extra options
    """
    # peel off first source include into var
    if util.is_not_empty(source.include):
        src_incl = source.include[0]
        if util.is_none_or_empty(src_incl):
            src_incl = None
    else:
        src_incl = None
    psrc = pathlib.Path(source.path)
    cwd = str(psrc.parent)
    rsrc = psrc.relative_to(psrc.parent)
    env = os.environ.copy()
    env['BLOBXFER_STORAGEACCOUNTKEY'] = storage_settings.account_key
    cmd = [
        ('blobxfer {} {} {} --endpoint {} --upload --no-progressbar '
         '{} {}').format(
             storage_settings.account, container, rsrc,
             storage_settings.endpoint,
             '--include \'{}\''.format(src_incl)
             if src_incl is not None else '',
             eo)
    ]
    logger.info('begin ingressing data from {} to container {}'.format(
        source.path, container))
    proc = util.subprocess_nowait_pipe_stdout(
        util.wrap_commands_in_shell(cmd), shell=True, cwd=cwd, env=env)
    stdout = proc.communicate()[0]
    if proc.returncode != 0:
        logger.error(stdout.decode('utf8'))
        logger.error('data ingress failed from {} to container {}'.format(
            source.path, container))
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
    files = settings.global_resources_files(config)
    if util.is_none_or_empty(files):
        logger.info('no files to ingress detected')
        return
    pool = settings.pool_settings(config)
    storage_threads = []
    for fdict in files:
        source = settings.files_source_settings(fdict)
        dest = settings.files_destination_settings(fdict)
        if (dest.shared_data_volume is not None and
                dest.storage_account_settings is not None):
            raise RuntimeError(
                'cannot specify both shared data volume and storage for the '
                'destination for source: {}'.format(source.path))
        direct_single_node = False
        if dest.relative_destination_path is not None:
            if dest.storage_account_settings is not None:
                raise RuntimeError(
                    'cannot specify a relative destination path for ingress '
                    'to storage; use the --collate option in blobxfer '
                    'instead.')
            # check if this is going to a single vm
            if dest.shared_data_volume is None:
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
        if dest.shared_data_volume is not None or direct_single_node:
            if rls is None:
                logger.warning(
                    'skipping data ingress from {} to {} for pool with no '
                    'remote login settings or non-existent pool'.format(
                        source.path, dest.shared_data_volume))
                continue
            if kind == 'storage':
                logger.warning(
                    'skipping data ingress from {} to {} for pool as ingress '
                    'to shared file system not specified'.format(
                        source.path, dest.shared_data_volume))
                continue
            if pool.ssh.username is None:
                raise RuntimeError(
                    'cannot ingress data to shared data volume without a '
                    'valid SSH user')
            if dest.data_transfer.ssh_private_key is None:
                # use default name for private key
                ssh_private_key = pathlib.Path(crypto.get_ssh_key_prefix())
            else:
                ssh_private_key = dest.data_transfer.ssh_private_key
            if not ssh_private_key.exists():
                raise RuntimeError(
                    'ssh private key does not exist at: {}'.format(
                        ssh_private_key))
            logger.debug('using ssh_private_key from: {}'.format(
                ssh_private_key))
            # set base dst path
            dst = '{}/batch/tasks/'.format(
                settings.temp_disk_mountpoint(config))
            # convert shared to actual path
            if not direct_single_node:
                sdv = settings.global_resources_shared_data_volumes(config)
                for sdvkey in sdv:
                    if sdvkey == dest.shared_data_volume:
                        if settings.is_shared_data_volume_gluster(sdv, sdvkey):
                            dst = '{}shared/{}/'.format(
                                dst, settings.get_gluster_volume())
                        else:
                            raise RuntimeError(
                                'data ingress to {} not supported'.format(
                                    sdvkey))
                        break
            if (dest.data_transfer.method == 'scp' or
                    dest.data_transfer.method == 'rsync+ssh'):
                # split/source include/exclude will force multinode
                # transfer with mpt=1
                if (dest.data_transfer.split_files_megabytes is not None or
                        source.include is not None or
                        source.exclude is not None):
                    _multinode_transfer(
                        'multinode_' + dest.data_transfer.method, dest, source,
                        dst, pool.ssh.username, ssh_private_key, rls, 1)
                else:
                    _singlenode_transfer(
                        dest, source.path, dst, pool.ssh.username,
                        ssh_private_key, rls)
            elif (dest.data_transfer.method == 'multinode_scp' or
                  dest.data_transfer.method == 'multinode_rsync+ssh'):
                _multinode_transfer(
                    dest.data_transfer.method, dest, source, dst,
                    pool.ssh.username, ssh_private_key, rls,
                    dest.data_transfer.max_parallel_transfers_per_node)
            else:
                raise RuntimeError(
                    'unknown transfer method: {}'.format(
                        dest.data_transfer.method))
        elif dest.storage_account_settings is not None:
            if kind == 'shared':
                logger.warning(
                    'skipping data ingress from {} to {} for pool as ingress '
                    'to Azure Blob/File Storage not specified'.format(
                        source.path, storage))
                continue
            if (dest.data_transfer.container is None and
                    dest.data_transfer.file_share is None):
                raise ValueError('container or file_share not specified')
            elif (dest.data_transfer.container is not None and
                  dest.data_transfer.file_share is not None):
                raise ValueError(
                    'cannot specify both container and file_share at the '
                    'same time for source {}'.format(source.path))
            # set destination
            eo = dest.data_transfer.blobxfer_extra_options
            if dest.data_transfer.file_share is not None:
                # append appropriate option for fshare
                if '--fileshare' not in eo:
                    eo = '--fileshare {}'.format(eo)
                dst = dest.data_transfer.file_share
            else:
                dst = dest.data_transfer.container
            if util.is_not_empty(source.include):
                if len(source.include) > 1:
                    raise ValueError(
                        'include can only be a maximum of one filter for '
                        'ingress to Azure Blob/File Storage')
            if source.exclude is not None:
                raise ValueError(
                    'exclude cannot be specified for ingress to Azure '
                    'Blob/File Storage')
            thr = _azure_blob_storage_transfer(
                settings.credentials_storage(
                    config, dest.storage_account_settings),
                dst, source, eo)
            storage_threads.append(thr)
        else:
            raise RuntimeError(
                'invalid file transfer configuration: {}'.format(fdict))
    return storage_threads
