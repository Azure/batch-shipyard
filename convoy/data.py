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
# non-stdlib imports
import azure.batch.models as batchmodels
# local imports
from . import crypto
from . import resource
from . import settings
from . import storage
from . import util
from .version import __version__

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_BLOBXFER_VERSION = '1.9.0'
_MEGABYTE = 1048576
_MAX_READ_BLOCKSIZE_BYTES = 4194304
_FILE_SPLIT_PREFIX = '_shipyard-'


def _get_gluster_paths(config):
    # type: (dict) -> Tuple[str, str]
    """Get Gluster paths
    :param dict config: configuration dict
    :rtype: tuple
    :return: (gluster host path, gluster container path)
    """
    gluster_host = None
    gluster_container = None
    sdv = settings.global_resources_shared_data_volumes(config)
    for sdvkey in sdv:
        if settings.is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
            gluster_host = '{}/{}'.format(
                settings.get_host_mounts_path(False),
                settings.get_gluster_on_compute_volume())
            gluster_container = settings.shared_data_volume_container_path(
                sdv, sdvkey).rstrip('/')
            break
    return (gluster_host, gluster_container)


def _convert_filter_to_blobxfer_option(includes, excludes):
    # type: (list, list) -> str
    """Converts filters to blobxfer options
    :param list includes: includes
    :param list excludes: excludes
    :rtype: str
    :return: blobxfer options
    """
    if util.is_not_empty(includes):
        src_incl = []
        for include in includes:
            src_incl.append('--include \"{}\"'.format(include))
    else:
        src_incl = None
    if util.is_not_empty(excludes):
        src_excl = []
        for exclude in excludes:
            src_excl.append('--exclude \"{}\"'.format(exclude))
    else:
        src_excl = None
    return '{} {}'.format(
        ' '.join(src_incl) if src_incl is not None else '',
        ' '.join(src_excl) if src_excl is not None else '',
    ).rstrip()


def _process_storage_input_data(config, input_data, on_task):
    # type: (dict, dict, bool) -> str
    """Process Azure storage input data to ingress
    :param dict config: configuration dict
    :param dict input_data: config spec with input_data
    :param bool on_task: if this is originating from a task spec
    :rtype: list
    :return: args to pass to blobxfer script
    """
    # get gluster host/container paths
    gluster_host, gluster_container = _get_gluster_paths(config)
    # parse storage input data blocks
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    args = []
    for xfer in input_data:
        storage_settings = settings.credentials_storage(
            config, settings.data_storage_account_settings(xfer))
        remote_path = settings.data_remote_path(xfer)
        # derive container from remote_path
        container = settings.data_container_from_remote_path(
            xfer, rp=remote_path)
        eo = settings.data_blobxfer_extra_options(xfer)
        # append appropriate option for fshare
        if settings.data_is_file_share(xfer) and '--mode file' not in eo:
            eo = '--mode file {}'.format(eo)
        if '--mode file' in eo:
            # create saskey for file share with rl perm
            saskey = storage.create_file_share_saskey(
                storage_settings, container, 'ingress')
        else:
            # create saskey for container with rl perm
            saskey = storage.create_blob_container_saskey(
                storage_settings, container, 'ingress')
        includes = settings.data_include(xfer)
        excludes = settings.data_exclude(xfer)
        # convert include/excludes into extra options
        filters = _convert_filter_to_blobxfer_option(includes, excludes)
        local_path = settings.data_local_path(xfer, on_task)
        # auto replace container path for gluster with host path
        if (util.is_not_empty(gluster_container) and
                local_path.startswith(gluster_container)):
            local_path = local_path.replace(gluster_container, gluster_host, 1)
        # construct argument
        # kind:encrypted:<sa:ep:saskey:remote_path>:local_path:eo
        creds = crypto.encrypt_string(
            encrypt,
            '{},{},{},{}'.format(
                storage_settings.account, storage_settings.endpoint,
                saskey, remote_path),
            config)
        args.append('"{bxver},i,{enc},{creds},{lp},{eo}"'.format(
            bxver=_BLOBXFER_VERSION,
            enc=encrypt,
            creds=creds,
            lp=local_path,
            eo=' '.join((filters, eo)).lstrip(),
        ))
    return args


def _process_batch_input_data(config, input_data, on_task):
    # type: (dict, dict, bool) -> str
    """Process Azure batch input data to ingress
    :param dict config: configuration dict
    :param dict input_data: config spec with input_data
    :param bool on_task: if this is originating from a task spec
    :rtype: list
    :return: args to pass to task file mover
    """
    # get batch creds
    bc = settings.credentials_batch(config)
    # fail (for now) if aad is being used
    if util.is_none_or_empty(bc.account_key):
        raise RuntimeError(
            'cannot move Azure Batch task input data without an account key')
    # construct arg
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    args = []
    for xfer in input_data:
        jobid = settings.input_data_job_id(xfer)
        taskid = settings.input_data_task_id(xfer)
        include = settings.data_include(xfer)
        if util.is_not_empty(include):
            include = ';'.join(include)
        else:
            include = ''
        exclude = settings.data_exclude(xfer)
        if util.is_not_empty(exclude):
            exclude = ';'.join(exclude)
        else:
            exclude = ''
        local_path = settings.data_local_path(xfer, on_task)
        creds = crypto.encrypt_string(
            encrypt,
            '{};{};{}'.format(
                bc.account, bc.account_service_url, bc.account_key),
            config)
        # construct argument
        # encrypt,creds,jobid,taskid,incl,excl,lp
        args.append('"{},{},{},{},{},{},{}"'.format(
            encrypt, creds, jobid, taskid, include, exclude, local_path))
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
    tfmimage = 'alfpark/batch-shipyard:{}-cargo'.format(__version__)
    is_windows = settings.is_windows_pool(config)
    if is_windows:
        bxcmd = ('powershell -ExecutionPolicy Unrestricted -command '
                 '%AZ_BATCH_NODE_STARTUP_DIR%\\wd\\{} {{}}').format(bxfile[0])
        tfmimage = '{}-windows'.format(tfmimage)
        tfmbind = (
            '-v %AZ_BATCH_NODE_ROOT_DIR%:%AZ_BATCH_NODE_ROOT_DIR% '
            '-w %AZ_BATCH_TASK_WORKING_DIR% '
            '-e "AZ_BATCH_NODE_STARTUP_DIR='
            '%AZ_BATCH_NODE_STARTUP_DIR%" '
        )
        tfmcmd = 'C:\\batch-shipyard\\task_file_mover.cmd'
        tfmpre = ''
        tfmpost = ''
    else:
        bxcmd = 'set -f; $AZ_BATCH_NODE_STARTUP_DIR/wd/{} {{}}; set +f'.format(
            bxfile[0])
        tfmbind = (
            '-v $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR '
            '-w $AZ_BATCH_TASK_WORKING_DIR '
            '-e "AZ_BATCH_NODE_STARTUP_DIR='
            '$AZ_BATCH_NODE_STARTUP_DIR" '
        )
        tfmcmd = '/opt/batch-shipyard/task_file_mover.sh'
        tfmpre = 'set -f; '
        tfmpost = '; set +f'
    ret = []
    input_data = settings.input_data(spec)
    if util.is_not_empty(input_data):
        for key in input_data:
            if key == 'azure_storage':
                args = _process_storage_input_data(
                    config, input_data[key], on_task)
                if is_windows:
                    cmds = []
                    for arg in args:
                        cmds.append('""{}""'.format(arg))
                    args = cmds
                ret.append(bxcmd.format(' '.join(args)))
            elif key == 'azure_batch':
                args = _process_batch_input_data(
                    config, input_data[key], on_task)
                if is_windows:
                    cmds = []
                    for arg in args:
                        cmds.append('""{}""'.format(arg))
                    args = cmds
                ret.append(
                    ('{tfmpre}docker run --rm -t {tfmbind} {tfmimage} '
                     '{tfmcmd} {args}{tfmpost}').format(
                         tfmpre=tfmpre, tfmbind=tfmbind, tfmimage=tfmimage,
                         tfmcmd=tfmcmd, tfmpost=tfmpost,
                         args=' '.join(args))
                )
            else:
                raise ValueError(
                    'unknown input_data method: {}'.format(key))
    if len(ret) > 0:
        return ';'.join(ret)
    else:
        return None


def _process_storage_output_data(config, native, is_windows, output_data):
    # type: (dict, bool, bool, dict) -> str
    """Process output data to egress to Azure storage
    :param dict config: configuration dict
    :param bool native: is native container pool
    :param bool is_windows: is windows pool
    :param dict output_data: config spec with output_data
    :rtype: list
    :return: OutputFiles or args to pass to blobxfer script
    """
    # get gluster host/container paths and encryption settings
    gluster_host, gluster_container = _get_gluster_paths(config)
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    # parse storage output data blocks
    args = []
    for xfer in output_data:
        storage_settings = settings.credentials_storage(
            config, settings.data_storage_account_settings(xfer))
        remote_path = settings.data_remote_path(xfer)
        # derive container from remote_path
        container = settings.data_container_from_remote_path(
            xfer, rp=remote_path)
        eo = settings.data_blobxfer_extra_options(xfer)
        if native and util.is_not_empty(eo):
            raise ValueError(
                'native container pool does not support '
                'blobxfer_extra_options')
        # append appropriate option for fshare
        if settings.data_is_file_share(xfer) and '--mode file' not in eo:
            eo = '--mode file {}'.format(eo)
        if '--mode file' in eo:
            if native:
                raise ValueError(
                    'native container pool does not support fileshares')
            # create saskey for file share with rwdl perm
            saskey = storage.create_file_share_saskey(
                storage_settings, container, 'egress', create_share=True)
        else:
            # create saskey for container with rwdl perm
            saskey = storage.create_blob_container_saskey(
                storage_settings, container, 'egress', create_container=True)
        includes = settings.data_include(xfer)
        excludes = settings.data_exclude(xfer)
        condition = settings.data_condition(xfer)
        # convert include/excludes into extra options
        filters = _convert_filter_to_blobxfer_option(includes, excludes)
        local_path = settings.data_local_path(xfer, True, task_wd=False)
        # auto replace container path for gluster with host path
        if (util.is_not_empty(gluster_container) and
                local_path.startswith(gluster_container)):
            local_path = local_path.replace(gluster_container, gluster_host, 1)
        if native:
            if util.is_not_empty(excludes):
                raise ValueError(
                    'native container pool does not support excludes')
            if is_windows:
                sep = '\\'
            else:
                sep = '/'
            if util.is_none_or_empty(includes):
                include = '**{}*'.format(sep)
            if not local_path.endswith(sep):
                fp = sep.join((local_path, include))
            else:
                fp = ''.join((local_path, include))
            if condition == 'taskcompletion':
                buc = batchmodels.OutputFileUploadCondition.task_completion
            elif condition == 'taskfailure':
                buc = batchmodels.OutputFileUploadCondition.task_failure
            elif condition == 'tasksuccess':
                buc = batchmodels.OutputFileUploadCondition.task_success
            of = batchmodels.OutputFile(
                file_pattern=fp,
                destination=batchmodels.OutputFileDestination(
                    container=batchmodels.OutputFileBlobContainerDestination(
                        path='',
                        container_url='{}?{}'.format(
                            storage.generate_blob_container_uri(
                                storage_settings, container),
                            saskey)
                    )
                ),
                upload_options=batchmodels.OutputFileUploadOptions(
                    upload_condition=buc
                ),
            )
            args.append(of)
        else:
            # construct argument
            # kind:encrypted:<sa:ep:saskey:remote_path>:local_path:eo
            creds = crypto.encrypt_string(
                encrypt,
                '{},{},{},{}'.format(
                    storage_settings.account, storage_settings.endpoint,
                    saskey, remote_path),
                config)
            args.append('"{bxver},e,{enc},{creds},{lp},{eo},{cond}"'.format(
                bxver=_BLOBXFER_VERSION,
                enc=encrypt,
                creds=creds,
                lp=local_path,
                eo=' '.join((filters, eo)).lstrip(),
                cond=condition,
            ))
    return args


def process_output_data(config, bxfile, spec):
    # type: (dict, tuple, dict) -> str
    """Process output data to egress
    :param dict config: configuration dict
    :param tuple bxfile: blobxfer script
    :param dict spec: config spec with input_data
    :rtype: str or list
    :return: additonal commands or list of OutputFiles
    """
    native = settings.is_native_docker_pool(config)
    is_windows = settings.is_windows_pool(config)
    if is_windows:
        bxcmd = ('powershell -ExecutionPolicy Unrestricted -command '
                 '%AZ_BATCH_NODE_STARTUP_DIR%\\wd\\{} {{}}').format(bxfile[0])
    else:
        bxcmd = 'set -f; $AZ_BATCH_NODE_STARTUP_DIR/wd/{} {{}}; set +f'.format(
            bxfile[0])
    ret = []
    output_data = settings.output_data(spec)
    if util.is_not_empty(output_data):
        for key in output_data:
            if key == 'azure_storage':
                args = _process_storage_output_data(
                    config, native, is_windows, output_data[key])
                if native:
                    ret.extend(args)
                else:
                    if is_windows:
                        cmds = []
                        for arg in args:
                            cmds.append('""{}""'.format(arg))
                        args = cmds
                    ret.append(bxcmd.format(' '.join(args)))
            else:
                raise ValueError(
                    'unknown output_data method: {}'.format(key))
    if len(ret) > 0:
        if native:
            return ret
        else:
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
                    '-o UserKnownHostsFile={} -i {} -p {} {}@{} {}'.format(
                        os.devnull, ssh_private_key, port, username, ip,
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
               '-o UserKnownHostsFile={} -p {} {} -i {} '
               '-P {} {} {}@{}:"{}"'.format(
                   os.devnull, dest.data_transfer.scp_ssh_extra_options,
                   recursive, ssh_private_key.resolve(), port, cmdsrc,
                   username, ip, shellquote(dst)))
    elif dest.data_transfer.method == 'rsync+ssh':
        cmd = ('rsync {} {} -e "ssh -T -x -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile={} {} -i {} -p {}" {} {}@{}:"{}"'.format(
                   dest.data_transfer.rsync_extra_options, recursive,
                   os.devnull, dest.data_transfer.scp_ssh_extra_options,
                   ssh_private_key.resolve(), port, cmdsrc, username, ip,
                   shellquote(dst)))
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
                    '-o UserKnownHostsFile={} -i {} -p {} {}@{} {}'.format(
                        os.devnull, ssh_private_key, port, username, ip,
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
                   '-o UserKnownHostsFile={} -p {} -i {} '
                   '-P {} {} {}@{}:"{}"'.format(
                       os.devnull, eo, ssh_private_key.resolve(), port,
                       shellquote(src), username, ip, shellquote(dst)))
        else:
            cmd = ('ssh -T -x -o StrictHostKeyChecking=no '
                   '-o UserKnownHostsFile={} {} -i {} '
                   '-p {} {}@{} \'cat > "{}"\''.format(
                       os.devnull, eo, ssh_private_key.resolve(), port,
                       username, ip, shellquote(dst)))
    elif method == 'multinode_rsync+ssh':
        if begin is not None or end is not None:
            raise RuntimeError('cannot rsync with file offsets')
        cmd = ('rsync {} -e "ssh -T -x -o StrictHostKeyChecking=no '
               '-o UserKnownHostsFile={} {} -i {} -p {}" {} {}@{}:"{}"'.format(
                   reo, os.devnull, eo, ssh_private_key.resolve(), port,
                   shellquote(src), username, ip, shellquote(dst)))
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
                           '-o UserKnownHostsFile={} -i {} '
                           '-p {} {}@{} {}'.format(
                               os.devnull, ssh_private_key, port, username,
                               ip, util.wrap_commands_in_shell(cmds)))
                procs.append(
                    util.subprocess_nowait(joincmd, shell=True))
            else:
                completed += 1
        else:
            del procs[n]
            completed += 1
    rcodes[node_id] = 0


def _azure_blob_storage_transfer(storage_settings, data_transfer, source):
    # type: (settings.StorageCredentialsSettings,
    #        settings.DataTransferSettings,
    #        settings.SourceSettings) -> None
    """Initiate an azure blob storage transfer
    :param settings.StorageCredentialsSettings storage_settings:
        storage settings
    :param settings.DataTransferSettings data_transfer: data transfer settings
    :param settings.SourceSettings source: source settings
    """
    eo = data_transfer.blobxfer_extra_options
    # append appropriate option for fshare
    if data_transfer.is_file_share and '--mode file' not in eo:
        eo = '--mode file {}'.format(eo)
    thr = threading.Thread(
        target=_wrap_blobxfer_subprocess,
        args=(
            storage_settings,
            data_transfer.remote_path,
            source,
            eo,
        )
    )
    thr.start()
    return thr


def _wrap_blobxfer_subprocess(storage_settings, remote_path, source, eo):
    # type: (StorageCredentialsSettings, str, SourceSettings, str) -> None
    """Wrapper function for blobxfer
    :param StorageCredentialsSettings storage_settings: storage settings
    :param str remote_path: remote path to transfer to
    :param SourceSettings source: source settings
    :param str eo: blobxfer extra options
    """
    # generate include/exclude options
    filters = _convert_filter_to_blobxfer_option(
        source.include, source.exclude)
    # get correct path
    psrc = pathlib.Path(source.path)
    cwd = str(psrc.parent)
    rsrc = psrc.relative_to(psrc.parent)
    # generate env
    env = os.environ.copy()
    env['BLOBXFER_STORAGE_ACCOUNT_KEY'] = storage_settings.account_key
    # set cmd
    cmd = [
        ('blobxfer upload --storage-account {sa} --remote-path {rp} '
         '--local-path {lp} --endpoint {ep} --no-progress-bar '
         '{filters} {eo}').format(
             sa=storage_settings.account,
             rp=remote_path,
             lp=rsrc,
             ep=storage_settings.endpoint,
             filters=filters,
             eo=eo)
    ]
    logger.info('begin ingressing data from {} to remote path {}'.format(
        source.path, remote_path))
    proc = util.subprocess_nowait_pipe_stdout(
        util.wrap_local_commands_in_shell(cmd), shell=True, cwd=cwd, env=env)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        if stderr is not None:
            logger.error(stderr.decode('utf8'))
        if stdout is not None:
            logger.error(stdout.decode('utf8'))
        logger.error('data ingress failed from {} to remote path {}'.format(
            source.path, remote_path))
    else:
        if stdout is not None:
            logger.debug(stdout.decode('utf8'))


def wait_for_storage_threads(storage_threads):
    # type: (list) -> None
    """Wait for storage processes to complete
    :param list storage_threads: list of storage threads
    """
    if storage_threads is None:
        return
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
        batch_client, compute_client, network_client, config, rls=None,
        kind=None, total_vm_count=None, to_fs=None):
    # type: (batch.BatchServiceClient,
    #        azure.mgmt.compute.ComputeManagementClient, dict, dict, str,
    #        int, str) -> list
    """Ingresses data into Azure
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param dict rls: remote login settings
    :param str kind: 'all', 'shared', 'storage', or 'remotefs'
    :param int total_vm_count: total current vm count
    :param str to_fs: to remote filesystem
    :rtype: list
    :return: list of storage threads
    """
    storage_threads = []
    files = settings.global_resources_files(config)
    if util.is_none_or_empty(files):
        logger.info('no files to ingress detected')
        return storage_threads
    pool = settings.pool_settings(config)
    is_windows = settings.is_windows_pool(config)
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
                if total_vm_count == 1:
                    direct_single_node = True
                elif kind == 'storage':
                    # this is to prevent total_vm_count check below for
                    # non shared/all targets and will force continuation
                    # of the loop below
                    direct_single_node = True
                elif total_vm_count is None:
                    raise ValueError('total_vm_count is not set')
                else:
                    raise RuntimeError(
                        'Cannot ingress data directly into compute node '
                        'host for pools with more than one node. Please use '
                        'a shared data volume as the ingress destination '
                        'instead.')
        if dest.shared_data_volume is not None or direct_single_node:
            if kind == 'storage':
                logger.warning(
                    'skipping data ingress from {} to {} for pool as ingress '
                    'to shared file system not specified'.format(
                        source.path, dest.shared_data_volume))
                continue
            if is_windows:
                logger.error(
                    ('cannot data ingress from {} to pool {} with windows '
                     'compute nodes').format(source.path, pool.id))
                continue
            # get rfs settings
            rfs = None
            dst_rfs = False
            # set base dst path
            dst = '{}/batch/tasks/mounts'.format(
                settings.temp_disk_mountpoint(config))
            # convert shared to actual path
            if not direct_single_node:
                sdv = settings.global_resources_shared_data_volumes(config)
                for sdvkey in sdv:
                    if sdvkey == dest.shared_data_volume:
                        if settings.is_shared_data_volume_gluster_on_compute(
                                sdv, sdvkey):
                            if kind == 'remotefs':
                                continue
                            dst = '{}/{}/'.format(
                                dst, settings.get_gluster_on_compute_volume())
                        elif settings.is_shared_data_volume_storage_cluster(
                                sdv, sdvkey):
                            if kind != 'remotefs' or sdvkey != to_fs:
                                continue
                            if rfs is None:
                                rfs = settings.remotefs_settings(config, to_fs)
                            dst = rfs.storage_cluster.file_server.mountpoint
                            # add trailing directory separator if needed
                            if dst[-1] != '/':
                                dst = dst + '/'
                            dst_rfs = True
                        else:
                            raise RuntimeError(
                                'data ingress to {} not supported'.format(
                                    sdvkey))
                        break
            # skip entries that are a mismatch if remotefs transfer
            # is selected
            if kind == 'remotefs':
                if not dst_rfs:
                    continue
            else:
                if dst_rfs:
                    continue
            # set ssh info
            if dst_rfs:
                username = rfs.storage_cluster.ssh.username
                #  retrieve public ips from all vms in named storage cluster
                rls = {}
                for i in range(rfs.storage_cluster.vm_count):
                    vm_name = '{}-vm{}'.format(
                        rfs.storage_cluster.hostname_prefix, i)
                    vm = compute_client.virtual_machines.get(
                        resource_group_name=rfs.storage_cluster.resource_group,
                        vm_name=vm_name,
                    )
                    _, pip = resource.get_nic_and_pip_from_virtual_machine(
                        network_client, rfs.storage_cluster.resource_group, vm)
                    # create compute node rls settings with sc vm ip/port
                    rls[vm_name] = \
                        batchmodels.ComputeNodeGetRemoteLoginSettingsResult(
                            remote_login_ip_address=pip.ip_address,
                            remote_login_port=22)
            else:
                username = pool.ssh.username
            if rls is None:
                logger.warning(
                    'skipping data ingress from {} to {} for pool with no '
                    'remote login settings or non-existent pool'.format(
                        source.path, dest.shared_data_volume))
                continue
            if username is None:
                raise RuntimeError(
                    'cannot ingress data to shared data volume without a '
                    'valid SSH user')
            # try to get valid ssh private key (from various config blocks)
            ssh_private_key = dest.data_transfer.ssh_private_key
            if ssh_private_key is None:
                ssh_private_key = pool.ssh.ssh_private_key
            if ssh_private_key is None:
                ssh_private_key = pathlib.Path(crypto.get_ssh_key_prefix())
                if not ssh_private_key.exists():
                    raise RuntimeError(
                        'specified SSH private key is invalid or does not '
                        'exist')
            logger.debug('using ssh_private_key from: {}'.format(
                ssh_private_key))
            if (dest.data_transfer.method == 'scp' or
                    dest.data_transfer.method == 'rsync+ssh'):
                # split/source include/exclude will force multinode
                # transfer with mpt=1
                if (dest.data_transfer.split_files_megabytes is not None or
                        source.include is not None or
                        source.exclude is not None):
                    _multinode_transfer(
                        'multinode_' + dest.data_transfer.method, dest,
                        source, dst, username, ssh_private_key, rls, 1)
                else:
                    _singlenode_transfer(
                        dest, source.path, dst, username, ssh_private_key,
                        rls)
            elif (dest.data_transfer.method == 'multinode_scp' or
                  dest.data_transfer.method == 'multinode_rsync+ssh'):
                _multinode_transfer(
                    dest.data_transfer.method, dest, source, dst,
                    username, ssh_private_key, rls,
                    dest.data_transfer.max_parallel_transfers_per_node)
            else:
                raise RuntimeError(
                    'unknown transfer method: {}'.format(
                        dest.data_transfer.method))
        elif dest.storage_account_settings is not None:
            if kind == 'shared':
                logger.warning(
                    'skipping data ingress from {} for pool as ingress '
                    'to Azure Blob/File Storage not specified'.format(
                        source.path))
                continue
            thr = _azure_blob_storage_transfer(
                settings.credentials_storage(
                    config, dest.storage_account_settings),
                dest.data_transfer, source)
            storage_threads.append(thr)
        else:
            raise RuntimeError(
                'invalid file transfer configuration: {}'.format(fdict))
    return storage_threads
