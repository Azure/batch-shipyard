#!/usr/bin/env python3

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
from __future__ import print_function, unicode_literals
import argparse
import base64
import copy
import datetime
import json
import hashlib
import logging
import logging.handlers
import os
try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib
import platform
import subprocess
import sys
import tempfile
import time
try:
    import urllib.request as urllibreq
except ImportError:
    import urllib as urllibreq
import uuid
# non-stdlib imports
import azure.batch.batch_auth as batchauth
import azure.batch.batch_service_client as batch
import azure.batch.models as batchmodels
import azure.common
import azure.storage.blob as azureblob
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable
# function remaps
try:
    raw_input
except NameError:
    raw_input = input

# create logger
logger = logging.getLogger('shipyard')
# global defines
_PY2 = sys.version_info.major == 2
_ON_WINDOWS = platform.system() == 'Windows'
_AZUREFILE_DVD_BIN = {
    'url': (
        'https://github.com/Azure/azurefile-dockervolumedriver/releases'
        '/download/v0.5.1/azurefile-dockervolumedriver'
    ),
    'md5': 'ee14da21efdfda4bedd85a67adbadc14'
}
_NVIDIA_DOCKER = {
    'ubuntuserver': {
        'url': (
            'https://github.com/NVIDIA/nvidia-docker/releases'
            '/download/v1.0.0-rc.3/nvidia-docker_1.0.0.rc.3-1_amd64.deb'
        ),
        'md5': '49990712ebf3778013fae81ee67f6c79'
    }
}
_NVIDIA_DRIVER = 'nvidia-driver.run'
_STORAGEACCOUNT = None
_STORAGEACCOUNTKEY = None
_STORAGEACCOUNTEP = None
_STORAGE_CONTAINERS = {
    'blob_resourcefiles': None,
    'blob_torrents': None,
    'table_dht': None,
    'table_registry': None,
    'table_torrentinfo': None,
    'table_images': None,
    'table_globalresources': None,
    'table_perf': None,
    'queue_globalresources': None,
}
_MAX_REBOOT_RETRIES = 5
_NODEPREP_FILE = ('shipyard_nodeprep.sh', 'scripts/shipyard_nodeprep.sh')
_GLUSTERPREP_FILE = ('shipyard_glusterfs.sh', 'scripts/shipyard_glusterfs.sh')
_JOBPREP_FILE = ('docker_jp_block.sh', 'scripts/docker_jp_block.sh')
_CASCADE_FILE = ('cascade.py', 'cascade/cascade.py')
_SETUP_PR_FILE = (
    'setup_private_registry.py', 'cascade/setup_private_registry.py'
)
_PERF_FILE = ('perf.py', 'cascade/perf.py')
_REGISTRY_FILE = None
_VM_TCP_NO_TUNE = (
    'basic_a0', 'basic_a1', 'basic_a2', 'basic_a3', 'basic_a4', 'standard_a0',
    'standard_a1', 'standard_d1', 'standard_d2', 'standard_d1_v2',
    'standard_f1'
)
_SSH_KEY_PREFIX = 'id_rsa_shipyard'
_SSH_TUNNEL_SCRIPT = 'ssh_docker_tunnel_shipyard.sh'
_GENERIC_DOCKER_TASK_PREFIX = 'dockertask-'


def _setup_logger():
    # type: () -> None
    """Set up logger"""
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)sZ %(levelname)s %(funcName)s:%(lineno)d %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _populate_global_settings(config, action):
    # type: (dict, str) -> None
    """Populate global settings from config
    :param dict config: configuration dict
    :param str action: action
    """
    global _STORAGEACCOUNT, _STORAGEACCOUNTKEY, _STORAGEACCOUNTEP, \
        _REGISTRY_FILE
    ssel = config['batch_shipyard']['storage_account_settings']
    _STORAGEACCOUNT = config['credentials']['storage'][ssel]['account']
    _STORAGEACCOUNTKEY = config['credentials']['storage'][ssel]['account_key']
    try:
        _STORAGEACCOUNTEP = config['credentials']['storage'][ssel]['endpoint']
    except KeyError:
        _STORAGEACCOUNTEP = 'core.windows.net'
    try:
        sep = config['batch_shipyard']['storage_entity_prefix']
    except KeyError:
        sep = None
    if sep is None:
        sep = ''
    postfix = '-'.join(
        (config['credentials']['batch']['account'].lower(),
         config['pool_specification']['id'].lower()))
    _STORAGE_CONTAINERS['blob_resourcefiles'] = '-'.join(
        (sep + 'resourcefiles', postfix))
    _STORAGE_CONTAINERS['blob_torrents'] = '-'.join(
        (sep + 'torrents', postfix))
    _STORAGE_CONTAINERS['table_dht'] = sep + 'dht'
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    _STORAGE_CONTAINERS['table_images'] = sep + 'images'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'globalresources'
    _STORAGE_CONTAINERS['table_perf'] = sep + 'perf'
    _STORAGE_CONTAINERS['queue_globalresources'] = '-'.join(
        (sep + 'globalresources', postfix))
    if action != 'addpool':
        return
    try:
        dpre = config['docker_registry']['private']['enabled']
    except KeyError:
        dpre = False
    # set docker private registry file info
    if dpre:
        rf = None
        imgid = None
        try:
            rf = config['docker_registry']['private'][
                'docker_save_registry_file']
            imgid = config['docker_registry']['private'][
                'docker_save_registry_image_id']
            if rf is not None and len(rf) == 0:
                rf = None
            if imgid is not None and len(imgid) == 0:
                imgid = None
            if rf is None or imgid is None:
                raise KeyError()
        except KeyError:
            if rf is None:
                rf = 'resources/docker-registry-v2.tar.gz'
            imgid = None
        prf = pathlib.Path(rf)
        # attempt to package if registry file doesn't exist
        if not prf.exists() or prf.stat().st_size == 0 or imgid is None:
            logger.debug(
                'attempting to generate docker private registry tarball')
            try:
                imgid = subprocess.check_output(
                    'sudo docker images -q registry:2', shell=True).decode(
                        'utf-8').strip()
            except subprocess.CalledProcessError:
                rf = None
                imgid = None
            else:
                if len(imgid) == 12:
                    if rf is None:
                        rf = 'resources/docker-registry-v2.tar.gz'
                    prf = pathlib.Path(rf)
                    subprocess.check_call(
                        'sudo docker save registry:2 '
                        '| gzip -c > {}'.format(rf), shell=True)
        _REGISTRY_FILE = (prf.name if rf is not None else None, rf, imgid)
    else:
        _REGISTRY_FILE = (None, None, None)
    logger.info('private registry settings: {}'.format(_REGISTRY_FILE))


def _wrap_commands_in_shell(commands, wait=True):
    # type: (List[str], bool) -> str
    """Wrap commands in a shell
    :param list commands: list of commands to wrap
    :param bool wait: add wait for background processes
    :rtype: str
    :return: wrapped commands
    """
    return '/bin/bash -c \'set -e; set -o pipefail; {}{}\''.format(
        '; '.join(commands), '; wait' if wait else '')


def _create_credentials(config):
    # type: (dict) -> tuple
    """Create authenticated clients
    :param dict config: configuration dict
    :rtype: tuple
    :return: (batch client, blob client, queue client, table client)
    """
    credentials = batchauth.SharedKeyCredentials(
        config['credentials']['batch']['account'],
        config['credentials']['batch']['account_key'])
    batch_client = batch.BatchServiceClient(
        credentials,
        base_url=config['credentials']['batch']['account_service_url'])
    blob_client = azureblob.BlockBlobService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=_STORAGEACCOUNTEP)
    queue_client = azurequeue.QueueService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=_STORAGEACCOUNTEP)
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=_STORAGEACCOUNTEP)
    return batch_client, blob_client, queue_client, table_client


def compute_md5_for_file(file, as_base64, blocksize=65536):
    # type: (pathlib.Path, bool, int) -> str
    """Compute MD5 hash for file
    :param pathlib.Path file: file to compute md5 for
    :param bool as_base64: return as base64 encoded string
    :param int blocksize: block size in bytes
    :rtype: str
    :return: md5 for file
    """
    hasher = hashlib.md5()
    with file.open('rb') as filedesc:
        while True:
            buf = filedesc.read(blocksize)
            if not buf:
                break
            hasher.update(buf)
        if as_base64:
            if _PY2:
                return base64.b64encode(hasher.digest())
            else:
                return str(base64.b64encode(hasher.digest()), 'ascii')
        else:
            return hasher.hexdigest()


def upload_resource_files(blob_client, config, files):
    # type: (azure.storage.blob.BlockBlobService, dict, List[tuple]) -> dict
    """Upload resource files to blob storage
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :rtype: dict
    :return: sas url dict
    """
    sas_urls = {}
    for file in files:
        # skip if no file is specified
        if file[0] is None:
            continue
        upload = True
        fp = pathlib.Path(file[1])
        if (_REGISTRY_FILE is not None and fp.name == _REGISTRY_FILE[0] and
                not fp.exists()):
            logger.debug('skipping optional docker registry image: {}'.format(
                _REGISTRY_FILE[0]))
            continue
        else:
            # check if blob exists
            try:
                prop = blob_client.get_blob_properties(
                    _STORAGE_CONTAINERS['blob_resourcefiles'], file[0])
                if (prop.properties.content_settings.content_md5 ==
                        compute_md5_for_file(fp, True)):
                    logger.debug(
                        'remote file is the same for {}, skipping'.format(
                            file[0]))
                    upload = False
            except azure.common.AzureMissingResourceHttpError:
                pass
        if upload:
            logger.info('uploading file: {}'.format(file[1]))
            blob_client.create_blob_from_path(
                _STORAGE_CONTAINERS['blob_resourcefiles'], file[0], file[1])
        sas_urls[file[0]] = 'https://{}.blob.{}/{}/{}?{}'.format(
            _STORAGEACCOUNT,
            _STORAGEACCOUNTEP,
            _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
            blob_client.generate_blob_shared_access_signature(
                _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
                permission=azureblob.BlobPermissions.READ,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=3)
            )
        )
    return sas_urls


def setup_nvidia_docker_package(blob_client, config):
    # type: (azure.storage.blob.BlockBlobService, dict) -> pathlib.Path
    """Set up the nvidia docker package
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :rtype: pathlib.Path
    :return: package path
    """
    offer = config['pool_specification']['offer'].lower()
    if offer == 'ubuntuserver':
        pkg = pathlib.Path('resources/nvidia-docker.deb')
    else:
        raise ValueError('Offer {} is unsupported with nvidia docker'.format(
            offer))
    # check to see if package is downloaded
    if (not pkg.exists() or
            compute_md5_for_file(pkg, False) != _NVIDIA_DOCKER[offer]['md5']):
        response = urllibreq.urlopen(_NVIDIA_DOCKER[offer]['url'])
        with pkg.open('wb') as f:
            f.write(response.read())
        # check md5
        if compute_md5_for_file(pkg, False) != _NVIDIA_DOCKER[offer]['md5']:
            raise RuntimeError('md5 mismatch for {}'.format(pkg))
    return pkg


def setup_azurefile_volume_driver(blob_client, config):
    # type: (azure.storage.blob.BlockBlobService, dict) -> tuple
    """Set up the Azure File docker volume driver
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :rtype: tuple
    :return: (bin path, service file path, service env file path,
        volume creation script path)
    """
    publisher = config['pool_specification']['publisher'].lower()
    offer = config['pool_specification']['offer'].lower()
    sku = config['pool_specification']['sku'].lower()
    # check to see if binary is downloaded
    bin = pathlib.Path('resources/azurefile-dockervolumedriver')
    if (not bin.exists() or
            compute_md5_for_file(bin, False) != _AZUREFILE_DVD_BIN['md5']):
        response = urllibreq.urlopen(_AZUREFILE_DVD_BIN['url'])
        with bin.open('wb') as f:
            f.write(response.read())
        # check md5
        if compute_md5_for_file(bin, False) != _AZUREFILE_DVD_BIN['md5']:
            raise RuntimeError('md5 mismatch for {}'.format(bin))
    if (publisher == 'canonical' and offer == 'ubuntuserver' and
            sku.startswith('14.04')):
        srv = pathlib.Path('resources/azurefile-dockervolumedriver.conf')
    else:
        srv = pathlib.Path('resources/azurefile-dockervolumedriver.service')
    # construct systemd env file
    sa = None
    sakey = None
    saep = None
    for svkey in config[
            'global_resources']['docker_volumes']['shared_data_volumes']:
        conf = config[
            'global_resources']['docker_volumes']['shared_data_volumes'][svkey]
        if conf['volume_driver'] == 'azurefile':
            # check every entry to ensure the same storage account
            ssel = conf['storage_account_settings']
            _sa = config['credentials']['storage'][ssel]['account']
            if sa is not None and sa != _sa:
                raise ValueError(
                    'multiple storage accounts are not supported for '
                    'azurefile docker volume driver')
            sa = _sa
            sakey = config['credentials']['storage'][ssel]['account_key']
            saep = config['credentials']['storage'][ssel]['endpoint']
        elif conf['volume_driver'] != 'glusterfs':
            raise NotImplementedError(
                'Unsupported volume driver: {}'.format(conf['volume_driver']))
    if sa is None or sakey is None:
        raise RuntimeError(
            'storage account or storage account key not specified for '
            'azurefile docker volume driver')
    srvenv = pathlib.Path('resources/azurefile-dockervolumedriver.env')
    with srvenv.open('w', encoding='utf8') as f:
        f.write('AZURE_STORAGE_ACCOUNT={}\n'.format(sa))
        f.write('AZURE_STORAGE_ACCOUNT_KEY={}\n'.format(sakey))
        f.write('AZURE_STORAGE_BASE={}\n'.format(saep))
    # create docker volume mount command script
    volcreate = pathlib.Path('resources/azurefile-dockervolume-create.sh')
    with volcreate.open('w', encoding='utf8') as f:
        f.write('#!/usr/bin/env bash\n\n')
        for svkey in config[
                'global_resources']['docker_volumes']['shared_data_volumes']:
            conf = config[
                'global_resources']['docker_volumes'][
                    'shared_data_volumes'][svkey]
            if conf['volume_driver'] == 'glusterfs':
                continue
            opts = [
                '-o share={}'.format(conf['azure_file_share_name'])
            ]
            for opt in conf['mount_options']:
                opts.append('-o {}'.format(opt))
            f.write('docker volume create -d azurefile --name {} {}\n'.format(
                svkey, ' '.join(opts)))
    return bin, srv, srvenv, volcreate


def add_pool(batch_client, blob_client, config):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,dict) -> None
    """Add a Batch pool to account
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    """
    publisher = config['pool_specification']['publisher']
    offer = config['pool_specification']['offer']
    sku = config['pool_specification']['sku']
    vm_count = config['pool_specification']['vm_count']
    vm_size = config['pool_specification']['vm_size']
    try:
        maxtasks = config['pool_specification']['max_tasks_per_node']
    except KeyError:
        maxtasks = 1
    try:
        internodecomm = config[
            'pool_specification']['inter_node_communication_enabled']
    except KeyError:
        internodecomm = False
    # cascade settings
    try:
        perf = config['batch_shipyard']['store_timing_metrics']
    except KeyError:
        perf = False
    # peer-to-peer settings
    try:
        p2p = config['data_replication']['peer_to_peer']['enabled']
    except KeyError:
        p2p = False
    if p2p:
        nonp2pcd = False
        try:
            p2psbias = config['data_replication'][
                'peer_to_peer']['direct_download_seed_bias']
            if p2psbias is None or p2psbias < 1:
                raise KeyError()
        except KeyError:
            p2psbias = vm_count // 10
            if p2psbias < 1:
                p2psbias = 1
        try:
            p2pcomp = config[
                'data_replication']['peer_to_peer']['compression']
        except KeyError:
            p2pcomp = True
    else:
        p2psbias = 0
        p2pcomp = False
        try:
            nonp2pcd = config[
                'data_replication']['non_peer_to_peer_concurrent_downloading']
        except KeyError:
            nonp2pcd = True
    # private registry settings
    try:
        pcont = config['docker_registry']['private']['container']
        pregpubpull = config['docker_registry']['private'][
            'allow_public_docker_hub_pull_on_missing']
        preg = config['docker_registry']['private']['enabled']
    except KeyError:
        preg = False
        pregpubpull = False
    # create private registry flags
    if preg:
        preg = ' -r {}:{}:{}'.format(
            pcont, _REGISTRY_FILE[0], _REGISTRY_FILE[2])
    else:
        preg = ''
    # create torrent flags
    torrentflags = ' -t {}:{}:{}:{}:{}'.format(
        p2p, nonp2pcd, p2psbias, p2pcomp, pregpubpull)
    # docker settings
    try:
        dockeruser = config['docker_registry']['login']['username']
        dockerpw = config['docker_registry']['login']['password']
    except KeyError:
        dockeruser = None
        dockerpw = None
    try:
        use_shipyard_docker_image = config[
            'batch_shipyard']['use_shipyard_docker_image']
    except KeyError:
        use_shipyard_docker_image = True
    try:
        block_for_gr = config[
            'pool_specification']['block_until_all_global_resources_loaded']
    except KeyError:
        block_for_gr = True
    if block_for_gr:
        block_for_gr = ','.join(
            [r for r in config['global_resources']['docker_images']])
    # check shared data volume mounts
    azurefile_vd = False
    gluster = False
    try:
        shared_data_volumes = config[
            'global_resources']['docker_volumes']['shared_data_volumes']
        for key in shared_data_volumes:
            if shared_data_volumes[key]['volume_driver'] == 'azurefile':
                azurefile_vd = True
            elif shared_data_volumes[key]['volume_driver'] == 'glusterfs':
                gluster = True
    except KeyError:
        pass
    # prefix settings
    try:
        prefix = config['batch_shipyard']['storage_entity_prefix']
        if len(prefix) == 0:
            prefix = None
    except KeyError:
        prefix = None
    # create resource files list
    _rflist = [_NODEPREP_FILE, _JOBPREP_FILE, _REGISTRY_FILE]
    if not use_shipyard_docker_image:
        _rflist.append(_CASCADE_FILE)
        _rflist.append(_SETUP_PR_FILE)
        if perf:
            _rflist.append(_PERF_FILE)
    # handle azurefile docker volume driver
    if azurefile_vd:
        afbin, afsrv, afenv, afvc = setup_azurefile_volume_driver(
            blob_client, config)
        _rflist.append((str(afbin.name), str(afbin)))
        _rflist.append((str(afsrv.name), str(afsrv)))
        _rflist.append((str(afenv.name), str(afenv)))
        _rflist.append((str(afvc.name), str(afvc)))
    # gpu settings
    if (vm_size.lower().startswith('standard_nc') or
            vm_size.lower().startswith('standard_nv')):
        gpupkg = setup_nvidia_docker_package(blob_client, config)
        _rflist.append((str(gpupkg.name), str(gpupkg)))
        gpu_env = '{}:{}:{}'.format(
            vm_size.lower().startswith('standard_nv'),
            _NVIDIA_DRIVER,
            gpupkg.name)
    else:
        gpu_env = None
    # pick latest sku
    node_agent_skus = batch_client.account.list_node_agent_skus()
    skus_to_use = [
        (nas, image_ref) for nas in node_agent_skus for image_ref in sorted(
            nas.verified_image_references, key=lambda item: item.sku)
        if image_ref.publisher.lower() == publisher.lower() and
        image_ref.offer.lower() == offer.lower() and
        image_ref.sku.lower() == sku.lower()
    ]
    sku_to_use, image_ref_to_use = skus_to_use[-1]
    # upload resource files
    sas_urls = upload_resource_files(blob_client, config, _rflist)
    del _rflist
    # create start task commandline
    start_task = [
        '{} -o {} -s {}{}{}{}{}{}{}{}{}{}'.format(
            _NODEPREP_FILE[0],
            offer,
            sku,
            preg,
            torrentflags,
            ' -a' if azurefile_vd else '',
            ' -b {}'.format(block_for_gr) if block_for_gr else '',
            ' -d' if use_shipyard_docker_image else '',
            ' -f' if gluster else '',
            ' -g {}'.format(gpu_env) if gpu_env is not None else '',
            ' -n' if vm_size.lower() not in _VM_TCP_NO_TUNE else '',
            ' -p {}'.format(prefix) if prefix else '',
        ),
    ]
    try:
        start_task.extend(
            config['pool_specification']['additional_node_prep_commands'])
    except KeyError:
        pass
    # create pool param
    pool = batchmodels.PoolAddParameter(
        id=config['pool_specification']['id'],
        virtual_machine_configuration=batchmodels.VirtualMachineConfiguration(
            image_reference=image_ref_to_use,
            node_agent_sku_id=sku_to_use.id),
        vm_size=vm_size,
        target_dedicated=vm_count,
        max_tasks_per_node=maxtasks,
        enable_inter_node_communication=internodecomm,
        start_task=batchmodels.StartTask(
            command_line=_wrap_commands_in_shell(start_task, wait=False),
            run_elevated=True,
            wait_for_success=True,
            environment_settings=[
                batchmodels.EnvironmentSetting('LC_ALL', 'en_US.UTF-8'),
                batchmodels.EnvironmentSetting(
                    'CASCADE_STORAGE_ENV',
                    '{}:{}:{}'.format(
                        _STORAGEACCOUNT,
                        _STORAGEACCOUNTEP,
                        _STORAGEACCOUNTKEY)
                )
            ],
            resource_files=[],
        ),
    )
    for rf in sas_urls:
        pool.start_task.resource_files.append(
            batchmodels.ResourceFile(
                file_path=rf,
                blob_source=sas_urls[rf])
        )
    if gpu_env:
        pool.start_task.resource_files.append(
            batchmodels.ResourceFile(
                file_path=_NVIDIA_DRIVER,
                blob_source=config[
                    'pool_specification']['gpu']['nvidia_driver']['source'],
                file_mode='0755')
        )
    if preg:
        ssel = config['docker_registry']['private']['storage_account_settings']
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'CASCADE_PRIVATE_REGISTRY_STORAGE_ENV',
                '{}:{}:{}'.format(
                    config['credentials']['storage'][ssel]['account'],
                    config['credentials']['storage'][ssel]['endpoint'],
                    config['credentials']['storage'][ssel]['account_key'])
            )
        )
        del ssel
    if (dockeruser is not None and len(dockeruser) > 0 and
            dockerpw is not None and len(dockerpw) > 0):
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('DOCKER_LOGIN_USERNAME', dockeruser)
        )
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('DOCKER_LOGIN_PASSWORD', dockerpw)
        )
    if perf:
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('CASCADE_TIMING', '1')
        )
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
    # set up gluster if specified
    if gluster:
        _setup_glusterfs(batch_client, blob_client, config, nodes)
    # create admin user on each node if requested
    add_ssh_tunnel_user(batch_client, config, nodes)
    # log remote login settings
    get_remote_login_settings(batch_client, config, nodes)


def _setup_glusterfs(batch_client, blob_client, config, nodes):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService, dict,
    #        List[batchmodels.ComputeNode]) -> None
    """Setup glusterfs via multi-instance task
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param list nodes: list of nodes
    """
    pool_id = config['pool_specification']['id']
    job_id = 'shipyard-glusterfs-{}'.format(uuid.uuid4())
    job = batchmodels.JobAddParameter(
        id=job_id,
        pool_info=batchmodels.PoolInformation(pool_id=pool_id),
    )
    batch_client.job.add(job)
    if config['pool_specification']['offer'].lower() == 'ubuntuserver':
        tempdisk = '/mnt'
    else:
        tempdisk = '/mnt/resource'
    # upload script
    sas_urls = upload_resource_files(blob_client, config, [_GLUSTERPREP_FILE])
    batchtask = batchmodels.TaskAddParameter(
        id='gluster-setup',
        multi_instance_settings=batchmodels.MultiInstanceSettings(
            number_of_instances=config['pool_specification']['vm_count'],
            coordination_command_line=_wrap_commands_in_shell([
                '$AZ_BATCH_TASK_DIR/{} {}'.format(
                    _GLUSTERPREP_FILE[0], tempdisk),
            ]),
            common_resource_files=[
                batchmodels.ResourceFile(
                    file_path=_GLUSTERPREP_FILE[0],
                    blob_source=sas_urls[_GLUSTERPREP_FILE[0]],
                    file_mode='0755'),
            ],
        ),
        command_line=(
            '/bin/bash -c "[[ -f $AZ_BATCH_TASK_DIR/'
            '.glusterfs_success ]] || exit 1"'),
        run_elevated=True,
    )
    batch_client.task.add(job_id=job_id, task=batchtask)
    logger.debug(
        'waiting for glusterfs setup task {} in job {} to complete'.format(
            batchtask.id, job_id))
    # wait for gluster fs setup task to complete
    while True:
        batchtask = batch_client.task.get(job_id, batchtask.id)
        if batchtask.state == batchmodels.TaskState.completed:
            break
        time.sleep(1)
    # ensure all nodes have glusterfs success file
    if nodes is None:
        nodes = batch_client.compute_node.list(pool_id)
    success = True
    for node in nodes:
        try:
            batch_client.file.get_node_file_properties_from_compute_node(
                pool_id, node.id,
                ('workitems/{}/job-1/gluster-setup/wd/'
                 '.glusterfs_success').format(job_id))
        except batchmodels.BatchErrorException:
            logger.error('gluster success file absent on node {}'.format(
                node.id))
            success = False
            break
    # delete job
    batch_client.job.delete(job_id)
    if not success:
        raise RuntimeError('glusterfs setup failed')
    logger.info(
        'glusterfs setup task {} in job {} completed'.format(
            batchtask.id, job_id))


def add_ssh_tunnel_user(batch_client, config, nodes=None):
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
        docker_user = config[
            'pool_specification']['ssh_docker_tunnel']['username']
        if docker_user is None:
            raise KeyError()
    except KeyError:
        logger.info('not creating ssh tunnel user on pool {}'.format(pool_id))
    else:
        ssh_priv_key = None
        try:
            ssh_pub_key = config[
                'pool_specification']['ssh_docker_tunnel']['ssh_public_key']
        except KeyError:
            ssh_pub_key = None
        try:
            gen_tunnel_script = config[
                'pool_specification']['ssh_docker_tunnel'][
                    'generate_tunnel_script']
        except KeyError:
            gen_tunnel_script = False
        # generate ssh key pair if not specified
        if ssh_pub_key is None:
            ssh_priv_key, ssh_pub_key = generate_ssh_keypair()
        # get node list if not provided
        if nodes is None:
            nodes = batch_client.compute_node.list(pool_id)
        for node in nodes:
            add_admin_user_to_compute_node(
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


def generate_ssh_keypair():
    # type: (str) -> tuple
    """Generate an ssh keypair for use with user logins
    :param str key_fileprefix: key file prefix
    :rtype: tuple
    :return: (private key filename, public key filename)
    """
    pubkey = _SSH_KEY_PREFIX + '.pub'
    try:
        if os.path.exists(_SSH_KEY_PREFIX):
            old = _SSH_KEY_PREFIX + '.old'
            if os.path.exists(old):
                os.remove(old)
            os.rename(_SSH_KEY_PREFIX, old)
    except OSError:
        pass
    try:
        if os.path.exists(pubkey):
            old = pubkey + '.old'
            if os.path.exists(old):
                os.remove(old)
            os.rename(pubkey, old)
    except OSError:
        pass
    logger.info('generating ssh key pair')
    subprocess.check_call(
        ['ssh-keygen', '-f', _SSH_KEY_PREFIX, '-t', 'rsa', '-N', ''''''])
    return (_SSH_KEY_PREFIX, pubkey)


def add_admin_user_to_compute_node(
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
        td = config['pool_specification']['ssh_docker_tunnel']['expiry_days']
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


def _add_global_resource(
        queue_client, table_client, config, pk, p2pcsd, grtype):
    # type: (azurequeue.QueueService, azuretable.TableService, dict, str,
    #        bool, str) -> None
    """Add global resources
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str pk: partition key
    :param int p2pcsd: peer-to-peer concurrent source downloads
    :param str grtype: global resources type
    """
    try:
        for gr in config['global_resources'][grtype]:
            if grtype == 'docker_images':
                prefix = 'docker'
            else:
                raise NotImplementedError()
            resource = '{}:{}'.format(prefix, gr)
            logger.info('adding global resource: {}'.format(resource))
            table_client.insert_or_replace_entity(
                _STORAGE_CONTAINERS['table_globalresources'],
                {
                    'PartitionKey': pk,
                    'RowKey': hashlib.sha1(
                        resource.encode('utf8')).hexdigest(),
                    'Resource': resource,
                }
            )
            for _ in range(0, p2pcsd):
                queue_client.put_message(
                    _STORAGE_CONTAINERS['queue_globalresources'], resource)
    except KeyError:
        pass


def populate_queues(queue_client, table_client, config):
    # type: (azurequeue.QueueService, azuretable.TableService, dict) -> None
    """Populate queues
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    try:
        preg = config['docker_registry']['private']['enabled']
    except KeyError:
        preg = False
    pk = '{}${}'.format(
        config['credentials']['batch']['account'],
        config['pool_specification']['id'])
    # if using docker public hub, then populate registry table with hub
    if not preg:
        table_client.insert_or_replace_entity(
            _STORAGE_CONTAINERS['table_registry'],
            {
                'PartitionKey': pk,
                'RowKey': 'registry.hub.docker.com',
                'Port': 80,
            }
        )
    # get p2pcsd setting
    try:
        p2p = config['data_replication']['peer_to_peer']['enabled']
    except KeyError:
        p2p = False
    if p2p:
        try:
            p2pcsd = config['data_replication']['peer_to_peer'][
                'concurrent_source_downloads']
            if p2pcsd is None or p2pcsd < 1:
                raise KeyError()
        except KeyError:
            p2pcsd = config['pool_specification']['vm_count'] // 6
            if p2pcsd < 1:
                p2pcsd = 1
    else:
        p2pcsd = 1
    # add global resources
    _add_global_resource(
        queue_client, table_client, config, pk, p2pcsd, 'docker_images')


def _adjust_settings_for_pool_creation(config):
    # type: (dict) -> None
    """Adjust settings for pool creation
    :param dict config: configuration dict
    """
    publisher = config['pool_specification']['publisher'].lower()
    offer = config['pool_specification']['offer'].lower()
    sku = config['pool_specification']['sku'].lower()
    vm_size = config['pool_specification']['vm_size']
    # enforce publisher/offer/sku restrictions
    allowed = False
    shipyard_container_required = True
    if publisher == 'canonical':
        if offer == 'ubuntuserver':
            if sku >= '14.04.0-lts':
                allowed = True
                if sku >= '16.04.0-lts':
                    shipyard_container_required = False
    elif publisher == 'credativ':
        if offer == 'debian':
            if sku >= '8':
                allowed = True
    elif publisher == 'openlogic':
        if offer.startswith('centos'):
            if sku >= '7':
                allowed = True
    elif publisher == 'redhat':
        if offer == 'rhel':
            if sku >= '7':
                allowed = True
    elif publisher == 'suse':
        if offer.startswith('sles'):
            if sku >= '12-sp1':
                allowed = True
        elif offer == 'opensuse-leap':
            if sku >= '42':
                allowed = True
        elif offer == 'opensuse':
            if sku == '13.2':
                allowed = True
    # check for valid image if gpu, currently only ubuntu 16.04 is supported
    if ((vm_size.lower().startswith('standard_nc') or
         vm_size.lower().startswith('standard_nv')) and
            (publisher != 'canonical' and offer != 'ubuntuserver' and
             sku < '16.04.0-lts')):
        allowed = False
    # oracle linux is not supported due to UEKR4 requirement
    if not allowed:
        raise ValueError(
            ('Unsupported Docker Host VM Config, publisher={} offer={} '
             'sku={} vm_size={}').format(publisher, offer, sku, vm_size))
    # adjust for shipyard container requirement
    if shipyard_container_required:
        config['batch_shipyard']['use_shipyard_docker_image'] = True
        logger.warning(
            ('forcing shipyard docker image to be used due to '
             'VM config, publisher={} offer={} sku={}').format(
                 publisher, offer, sku))
    # adjust inter node comm setting
    vm_count = int(config['pool_specification']['vm_count'])
    try:
        p2p = config['data_replication']['peer_to_peer']['enabled']
    except KeyError:
        p2p = False
    try:
        internode = config[
            'pool_specification']['inter_node_communication_enabled']
    except KeyError:
        internode = True
    max_vms = 20 if publisher == 'microsoftwindowsserver' else 40
    if vm_count > max_vms:
        if p2p:
            logger.warning(
                ('disabling peer-to-peer transfer as pool size of {} exceeds '
                 'max limit of {} vms for inter-node communication').format(
                     vm_count, max_vms))
            if 'data_replication' not in config:
                config['data_replication'] = {}
            if 'peer_to_peer' not in config['data_replication']:
                config['data_replication']['peer_to_peer'] = {}
            config['data_replication']['peer_to_peer']['enabled'] = False
            p2p = False
        if internode:
            logger.warning(
                ('disabling inter-node communication as pool size of {} '
                 'exceeds max limit of {} vms for setting').format(
                     vm_count, max_vms))
            config['pool_specification'][
                'inter_node_communication_enabled'] = False
            internode = False
    # ensure settings p2p/internode settings are compatible
    if p2p and not internode:
        config['pool_specification']['inter_node_communication_enabled'] = True
        logger.warning(
            'force enabling inter-node communication due to peer-to-peer '
            'transfer')
    # adjust ssh settings on windows
    if _ON_WINDOWS:
        try:
            ssh_pub_key = config[
                'pool_specification']['ssh_docker_tunnel']['ssh_public_key']
        except KeyError:
            ssh_pub_key = None
        if ssh_pub_key is None:
            logger.warning(
                'disabling ssh docker tunnel creation due to script being '
                'run from Windows')
            config['pool_specification'].pop('ssh_docker_tunnel', None)


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


def _confirm_action(config, msg=None):
    # type: (dict) -> bool
    """Confirm action with user before proceeding
    :param dict config: configuration dict
    :rtype: bool
    :return: if user confirmed or not
    """
    if config['_auto_confirm']:
        return True
    if msg is None:
        msg = 'action'
    user = raw_input('Confirm {} [y/n]: '.format(msg))
    if user.lower() in ['y', 'yes']:
        return True
    return False


def del_pool(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Delete a pool
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool_id = config['pool_specification']['id']
    if not _confirm_action(config, 'delete {} pool'.format(pool_id)):
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
    if not _confirm_action(
            config, 'delete node {} from {} pool'.format(node_id, pool_id)):
        return
    logger.info('Deleting node {} from pool {}'.format(node_id, pool_id))
    batch_client.pool.remove_nodes(
        pool_id=pool_id,
        node_remove_parameter=batchmodels.NodeRemoveParameter(
            node_list=[node_id],
        )
    )


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


def add_jobs(batch_client, blob_client, config):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService,dict) -> None
    """Add jobs
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    """
    # get the pool inter-node comm setting
    pool_id = config['pool_specification']['id']
    _pool = batch_client.pool.get(pool_id)
    global_resources = []
    for gr in config['global_resources']['docker_images']:
        global_resources.append(gr)
    # TODO add global resources for non-docker resources
    jpcmdline = _wrap_commands_in_shell([
        '$AZ_BATCH_NODE_SHARED_DIR/{} {}'.format(
            _JOBPREP_FILE[0], ' '.join(global_resources))])
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
                command_line=_wrap_commands_in_shell(
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
                            run_opts.append('-v {}:{}'.format(
                                '$AZ_BATCH_NODE_SHARED_DIR/.gluster/gv0',
                                dvspec['container_path']))
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
                    env_vars = merge_dict(env_vars, task_ev)
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
                    sas_urls = upload_resource_files(
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
                    coordination_command_line=_wrap_commands_in_shell(
                        cc_args, wait=False),
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
                command_line=_wrap_commands_in_shell(task_commands),
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


def del_jobs(batch_client, config):
    # type: (azure.batch.batch_service_client.BatchServiceClient, dict) -> None
    """Delete jobs
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    """
    for job in config['job_specifications']:
        job_id = job['id']
        if not _confirm_action(config, 'delete {} job'.format(job_id)):
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
                        coordination_command_line=_wrap_commands_in_shell([
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
        if not _confirm_action(config, 'terminate {} job'.format(job_id)):
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
        if not _confirm_action(config, 'delete {} job'.format(job.id)):
            continue
        logger.info('Deleting job: {}'.format(job.id))
        batch_client.job.delete(job.id)


def get_remote_login_settings(batch_client, config, nodes=None):
    # type: (batch.BatchServiceClient, dict, List[str], bool) -> None
    """Get remote login settings
    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param dict config: configuration dict
    :param list nodes: list of nodes
    """
    pool_id = config['pool_specification']['id']
    if nodes is None:
        nodes = batch_client.compute_node.list(pool_id)
    for node in nodes:
        rls = batch_client.compute_node.get_remote_login_settings(
            pool_id, node.id)
        logger.info('node {}: ip {} port {}'.format(
            node.id, rls.remote_login_ip_address, rls.remote_login_port))


def stream_file_and_wait_for_task(batch_client, filespec=None):
    # type: (batch.BatchServiceClient, str) -> None
    """Stream a file and wait for task to complete (streams for a maximum
    of 30 minutes)
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
        job_id = raw_input('Enter job id: ')
    if task_id is None:
        task_id = raw_input('Enter task id: ')
    if file is None:
        file = raw_input(
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
    timeout = datetime.timedelta(minutes=30)
    time_to_timeout_at = datetime.datetime.now() + timeout
    while datetime.datetime.now() < time_to_timeout_at:
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
            # get stdout.txt
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
        job_id = raw_input('Enter job id: ')
    if task_id is None:
        task_id = raw_input('Enter task id: ')
    if file is None:
        file = raw_input(
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
            not _confirm_action(config, 'file overwrite of {}'.format(file))):
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
    file = raw_input('Enter node-relative file path to retrieve: ')
    if file == '' or file is None:
        raise RuntimeError('specified invalid file to retrieve')
    # check if file exists on disk; a possible race condition here is
    # understood
    fp = pathlib.Path(pathlib.Path(file).name)
    if (fp.exists() and
            not _confirm_action(config, 'file overwrite of {}'.format(file))):
        raise RuntimeError('file already exists: {}'.format(file))
    logger.debug('attempting to retrieve file {} from pool={} node={}'.format(
        file, pool_id, node_id))
    stream = batch_client.file.get_from_compute_node(pool_id, node_id, file)
    with fp.open('wb') as f:
        for data in stream:
            f.write(data)
    logger.debug('file {} retrieved from pool={} node={} bytes={}'.format(
        file, pool_id, node_id, fp.stat().st_size))


def delete_storage_containers(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Delete storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            blob_client.delete_container(_STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            table_client.delete_table(_STORAGE_CONTAINERS[key])
        elif key.startswith('queue_'):
            queue_client.delete_queue(_STORAGE_CONTAINERS[key])


def _clear_blobs(blob_client, container):
    # type: (azureblob.BlockBlobService, str) -> None
    """Clear blobs in container
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str container: container to clear blobs from
    """
    logger.info('deleting blobs: {}'.format(container))
    blobs = blob_client.list_blobs(container)
    for blob in blobs:
        blob_client.delete_blob(container, blob.name)


def _clear_blob_task_resourcefiles(blob_client, container, config):
    # type: (azureblob.BlockBlobService, str, dict) -> None
    """Clear task resource file blobs in container
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str container: container to clear blobs from
    :param dict config: configuration dict
    """
    envfileloc = '{}taskrf-'.format(
        config['batch_shipyard']['storage_entity_prefix'])
    logger.info('deleting blobs with prefix: {}'.format(envfileloc))
    blobs = blob_client.list_blobs(container, prefix=envfileloc)
    for blob in blobs:
        blob_client.delete_blob(container, blob.name)


def _clear_table(table_client, table_name, config):
    """Clear table entities
    :param azure.storage.table.TableService table_client: table client
    :param str table_name: table name
    :param dict config: configuration dict
    """
    # type: (azuretable.TableService, str, dict) -> None
    logger.info('clearing table: {}'.format(table_name))
    ents = table_client.query_entities(
        table_name, filter='PartitionKey eq \'{}${}\''.format(
            config['credentials']['batch']['account'],
            config['pool_specification']['id'])
    )
    # batch delete entities
    i = 0
    bet = azuretable.TableBatch()
    for ent in ents:
        bet.delete_entity(ent['PartitionKey'], ent['RowKey'])
        i += 1
        if i == 100:
            table_client.commit_batch(table_name, bet)
            bet = azuretable.TableBatch()
            i = 0
    if i > 0:
        table_client.commit_batch(table_name, bet)


def clear_storage_containers(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Clear storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    try:
        perf = config['batch_shipyard']['store_timing_metrics']
    except KeyError:
        perf = False
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            # TODO this is temp to preserve registry upload
            if key != 'blob_resourcefiles':
                _clear_blobs(blob_client, _STORAGE_CONTAINERS[key])
            else:
                _clear_blob_task_resourcefiles(
                    blob_client, _STORAGE_CONTAINERS[key], config)
        elif key.startswith('table_'):
            try:
                _clear_table(table_client, _STORAGE_CONTAINERS[key], config)
            except azure.common.AzureMissingResourceHttpError:
                if key != 'table_perf' or perf:
                    raise
        elif key.startswith('queue_'):
            logger.info('clearing queue: {}'.format(_STORAGE_CONTAINERS[key]))
            queue_client.clear_messages(_STORAGE_CONTAINERS[key])


def create_storage_containers(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Create storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    try:
        perf = config['batch_shipyard']['store_timing_metrics']
    except KeyError:
        perf = False
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            logger.info(
                'creating container: {}'.format(_STORAGE_CONTAINERS[key]))
            blob_client.create_container(_STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            if key == 'table_perf' and not perf:
                continue
            logger.info('creating table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.create_table(_STORAGE_CONTAINERS[key])
        elif key.startswith('queue_'):
            logger.info('creating queue: {}'.format(_STORAGE_CONTAINERS[key]))
            queue_client.create_queue(_STORAGE_CONTAINERS[key])


def merge_dict(dict1, dict2):
    # type: (dict, dict) -> dict
    """Recursively merge dictionaries: dict2 on to dict1. This differs
    from dict.update() in that values that are dicts are recursively merged.
    Note that only dict value types are merged, not lists, etc.

    :param dict dict1: dictionary to merge to
    :param dict dict2: dictionary to merge with
    :rtype: dict
    :return: merged dictionary
    """
    if not isinstance(dict1, dict) or not isinstance(dict2, dict):
        raise ValueError('dict1 or dict2 is not a dictionary')
    result = copy.deepcopy(dict1)
    for k, v in dict2.items():
        if k in result and isinstance(result[k], dict):
            result[k] = merge_dict(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def main():
    """Main function"""
    # get command-line args
    args = parseargs()
    args.action = args.action.lower()

    if args.configdir is not None:
        if args.credentials is None:
            args.credentials = str(pathlib.Path(
                args.configdir, 'credentials.json'))
        if args.config is None:
            args.config = str(pathlib.Path(args.configdir, 'config.json'))
        if args.pool is None:
            args.pool = str(pathlib.Path(args.configdir, 'pool.json'))

    if args.credentials is None:
        raise ValueError('credentials json not specified')
    if args.config is None:
        raise ValueError('config json not specified')

    with open(args.credentials, 'r') as f:
        config = json.load(f)
    with open(args.config, 'r') as f:
        config = merge_dict(config, json.load(f))
    try:
        with open(args.pool, 'r') as f:
            config = merge_dict(config, json.load(f))
    except ValueError:
        raise
    except Exception:
        config['pool_specification'] = {
            'id': args.poolid
        }
    if args.action in ('addjobs', 'cleanmijobs', 'deljobs', 'termjobs'):
        if args.configdir is not None and args.jobs is None:
                args.jobs = str(pathlib.Path(args.configdir, 'jobs.json'))
        try:
            with open(args.jobs, 'r') as f:
                config = merge_dict(config, json.load(f))
        except ValueError:
            raise
        except Exception:
            config['job_specifications'] = [{
                'id': args.jobid
            }]
    if args.verbose:
        logger.debug('config:\n' + json.dumps(config, indent=4))
    _populate_global_settings(config, args.action)
    config['_auto_confirm'] = args.yes

    batch_client, blob_client, queue_client, table_client = \
        _create_credentials(config)

    if args.action == 'addpool':
        # first check if pool exists to prevent accidential metadata clear
        if batch_client.pool.exists(config['pool_specification']['id']):
            raise RuntimeError(
                'attempting to create a pool that already exists: {}'.format(
                    config['pool_specification']['id']))
        create_storage_containers(
            blob_client, queue_client, table_client, config)
        clear_storage_containers(
            blob_client, queue_client, table_client, config)
        _adjust_settings_for_pool_creation(config)
        populate_queues(queue_client, table_client, config)
        add_pool(batch_client, blob_client, config)
    elif args.action == 'resizepool':
        resize_pool(batch_client, config)
    elif args.action == 'delpool':
        del_pool(batch_client, config)
    elif args.action == 'addsshuser':
        add_ssh_tunnel_user(batch_client, config)
        get_remote_login_settings(batch_client, config)
    elif args.action == 'delnode':
        del_node(batch_client, config, args.nodeid)
    elif args.action == 'addjobs':
        add_jobs(batch_client, blob_client, config)
    elif args.action == 'cleanmijobs':
        clean_mi_jobs(batch_client, config)
    elif args.action == 'termjobs':
        terminate_jobs(batch_client, config)
    elif args.action == 'deljobs':
        del_jobs(batch_client, config)
    elif args.action == 'delcleanmijobs':
        del_clean_mi_jobs(batch_client, config)
    elif args.action == 'delalljobs':
        del_all_jobs(batch_client, config)
    elif args.action == 'grls':
        get_remote_login_settings(batch_client, config)
    elif args.action == 'streamfile':
        stream_file_and_wait_for_task(batch_client, args.filespec)
    elif args.action == 'gettaskfile':
        get_file_via_task(batch_client, config, args.filespec)
    elif args.action == 'getnodefile':
        get_file_via_node(batch_client, config, args.nodeid)
    elif args.action == 'delstorage':
        delete_storage_containers(
            blob_client, queue_client, table_client, config)
    elif args.action == 'clearstorage':
        clear_storage_containers(
            blob_client, queue_client, table_client, config)
    else:
        raise ValueError('Unknown action: {}'.format(args.action))


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Batch Shipyard: Provision and Execute Docker Workloads '
        'on Azure Batch')
    parser.set_defaults(verbose=False, yes=False)
    parser.add_argument(
        'action', help='addpool, addjobs, addsshuser, cleanmijobs, '
        'termjobs, deljobs, delcleanmijobs, delalljobs, delpool, delnode, '
        'grls, streamfile, gettaskfile, getnodefile, clearstorage, delstorage')
    parser.add_argument(
        '-v', '--verbose', dest='verbose', action='store_true',
        help='verbose output')
    parser.add_argument(
        '-y', '--yes', dest='yes', action='store_true',
        help='assume yes for all yes/no confirmations')
    parser.add_argument(
        '--credentials',
        help='credentials json config. required for all actions')
    parser.add_argument(
        '--config',
        help='global json config for option. required for all actions')
    parser.add_argument(
        '--configdir',
        help='configdir where all config files can be found. json config '
        'file must be named exactly the same as the switch option, e.g., '
        'pool.json for --pool. individually specified configuration options '
        'take precedence over this option.')
    parser.add_argument(
        '--pool',
        help='pool json config. required for most actions')
    parser.add_argument(
        '--jobs',
        help='jobs json config. required for job-related actions')
    parser.add_argument(
        '--nodeid',
        help='node id for delnode or getnodefile action')
    parser.add_argument(
        '--filespec',
        help='parameter for action streamfile/gettaskfile: '
        'jobid:taskid:filename')
    return parser.parse_args()

if __name__ == '__main__':
    _setup_logger()
    main()
