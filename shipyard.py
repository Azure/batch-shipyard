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
from __future__ import division, print_function, unicode_literals
import argparse
import json
import logging
import logging.handlers
try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib
import subprocess
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
# local imports
import convoy.batch
import convoy.crypto
import convoy.data
import convoy.storage
import convoy.util

# create logger
logger = logging.getLogger('shipyard')
# global defines
_VERSION = '2.0.0'
_ROOT_PATH = pathlib.Path(__file__).resolve().parent
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
_NODEPREP_FILE = (
    'shipyard_nodeprep.sh',
    str(pathlib.Path(_ROOT_PATH, 'scripts/shipyard_nodeprep.sh'))
)
_GLUSTERPREP_FILE = (
    'shipyard_glusterfs.sh',
    str(pathlib.Path(_ROOT_PATH, 'scripts/shipyard_glusterfs.sh'))
)
_HPNSSH_FILE = (
    'shipyard_hpnssh.sh',
    str(pathlib.Path(_ROOT_PATH, 'scripts/shipyard_hpnssh.sh'))
)
_JOBPREP_FILE = (
    'docker_jp_block.sh',
    str(pathlib.Path(_ROOT_PATH, 'scripts/docker_jp_block.sh'))
)
_BLOBXFER_FILE = (
    'shipyard_blobxfer.sh',
    str(pathlib.Path(_ROOT_PATH, 'scripts/shipyard_blobxfer.sh'))
)
_CASCADE_FILE = (
    'cascade.py',
    str(pathlib.Path(_ROOT_PATH, 'cascade/cascade.py'))
)
_SETUP_PR_FILE = (
    'setup_private_registry.py',
    str(pathlib.Path(_ROOT_PATH, 'cascade/setup_private_registry.py'))
)
_PERF_FILE = (
    'perf.py',
    str(pathlib.Path(_ROOT_PATH, 'cascade/perf.py'))
)
_VM_TCP_NO_TUNE = (
    'basic_a0', 'basic_a1', 'basic_a2', 'basic_a3', 'basic_a4', 'standard_a0',
    'standard_a1', 'standard_d1', 'standard_d2', 'standard_d1_v2',
    'standard_f1'
)


def _populate_global_settings(config, action):
    # type: (dict, str) -> None
    """Populate global settings from config
    :param dict config: configuration dict
    :param str action: action
    """
    ssel = config['batch_shipyard']['storage_account_settings']
    try:
        sep = config['batch_shipyard']['storage_entity_prefix']
    except KeyError:
        sep = None
    if sep is None or len(sep) == 0:
        raise ValueError('storage_entity_prefix is invalid')
    postfix = '-'.join(
        (config['credentials']['batch']['account'].lower(),
         config['pool_specification']['id'].lower()))
    sa = config['credentials']['storage'][ssel]['account']
    sakey = config['credentials']['storage'][ssel]['account_key']
    try:
        saep = config['credentials']['storage'][ssel]['endpoint']
    except KeyError:
        saep = 'core.windows.net'
    convoy.storage.set_storage_configuration(
        sep, postfix, sa, sakey, saep)
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
                rf = _ROOT_PATH + '/resources/docker-registry-v2.tar.gz'
            imgid = None
        prf = pathlib.Path(rf)
        # attempt to package if registry file doesn't exist
        if not prf.exists() or prf.stat().st_size == 0 or imgid is None:
            logger.debug(
                'attempting to generate docker private registry tarball')
            try:
                imgid = convoy.util.decode_string(subprocess.check_output(
                    'sudo docker images -q registry:2', shell=True)).strip()
            except subprocess.CalledProcessError:
                rf = None
                imgid = None
            else:
                if len(imgid) == 12:
                    if rf is None:
                        rf = (_ROOT_PATH +
                              '/resources/docker-registry-v2.tar.gz')
                    prf = pathlib.Path(rf)
                    subprocess.check_call(
                        'sudo docker save registry:2 '
                        '| gzip -c > {}'.format(rf), shell=True)
        regfile = (prf.name if rf is not None else None, rf, imgid)
    else:
        regfile = (None, None, None)
    logger.info('private registry settings: {}'.format(regfile))
    convoy.storage.set_registry_file(regfile)


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
    batch_client.config.add_user_agent('batch-shipyard/{}'.format(_VERSION))
    blob_client, queue_client, table_client = convoy.storage.create_clients()
    return batch_client, blob_client, queue_client, table_client


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
        pkg = pathlib.Path(_ROOT_PATH, 'resources/nvidia-docker.deb')
    else:
        raise ValueError('Offer {} is unsupported with nvidia docker'.format(
            offer))
    # check to see if package is downloaded
    if (not pkg.exists() or
            convoy.util.compute_md5_for_file(pkg, False) !=
            _NVIDIA_DOCKER[offer]['md5']):
        response = urllibreq.urlopen(_NVIDIA_DOCKER[offer]['url'])
        with pkg.open('wb') as f:
            f.write(response.read())
        # check md5
        if (convoy.util.compute_md5_for_file(pkg, False) !=
                _NVIDIA_DOCKER[offer]['md5']):
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
    bin = pathlib.Path(_ROOT_PATH, 'resources/azurefile-dockervolumedriver')
    if (not bin.exists() or
            convoy.util.compute_md5_for_file(bin, False) !=
            _AZUREFILE_DVD_BIN['md5']):
        response = urllibreq.urlopen(_AZUREFILE_DVD_BIN['url'])
        with bin.open('wb') as f:
            f.write(response.read())
        # check md5
        if (convoy.util.compute_md5_for_file(bin, False) !=
                _AZUREFILE_DVD_BIN['md5']):
            raise RuntimeError('md5 mismatch for {}'.format(bin))
    if (publisher == 'canonical' and offer == 'ubuntuserver' and
            sku.startswith('14.04')):
        srv = pathlib.Path(
            _ROOT_PATH, 'resources/azurefile-dockervolumedriver.conf')
    else:
        srv = pathlib.Path(
            _ROOT_PATH, 'resources/azurefile-dockervolumedriver.service')
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
    srvenv = pathlib.Path(
        _ROOT_PATH, 'resources/azurefile-dockervolumedriver.env')
    with srvenv.open('wb') as f:
        f.write('AZURE_STORAGE_ACCOUNT={}\n'.format(sa))
        f.write('AZURE_STORAGE_ACCOUNT_KEY={}\n'.format(sakey))
        f.write('AZURE_STORAGE_BASE={}\n'.format(saep))
    # create docker volume mount command script
    volcreate = pathlib.Path(
        _ROOT_PATH, 'resources/azurefile-dockervolume-create.sh')
    with volcreate.open('wb') as f:
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
    # add encryption cert to account if specified
    encrypt = False
    encrypt_sha1tp = None
    try:
        encrypt = config['batch_shipyard']['encryption']['enabled']
        if encrypt:
            convoy.batch.add_certificate_to_account(batch_client, config)
            try:
                encrypt_sha1tp = config['batch_shipyard']['encryption'][
                    'pfx']['sha1_thumbprint']
            except KeyError:
                pfxfile = config['batch_shipyard']['encryption']['pfx'][
                    'filename']
                try:
                    passphrase = config['batch_shipyard']['encryption'][
                        'pfx']['passphrase']
                except KeyError:
                    passphrase = None
                encrypt_sha1tp = convoy.crypto.get_sha1_thumbprint_pfx(
                    pfxfile, passphrase)
                config['batch_shipyard']['encryption']['pfx'][
                    'sha1_thumbprint'] = encrypt_sha1tp
    except KeyError:
        pass
    publisher = config['pool_specification']['publisher']
    offer = config['pool_specification']['offer']
    sku = config['pool_specification']['sku']
    vm_count = config['pool_specification']['vm_count']
    vm_size = config['pool_specification']['vm_size']
    try:
        ingress_files = config[
            'pool_specification']['transfer_files_on_pool_creation']
    except KeyError:
        ingress_files = False
    # ingress data to Azure Blob Storage if specified
    storage_threads = []
    if ingress_files:
        storage_threads = convoy.data.ingress_data(
            batch_client, config, rls=None, kind='storage')
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
    regfile = convoy.storage.get_registry_file()
    if preg:
        preg = ' -r {}:{}:{}'.format(pcont, regfile[0], regfile[2])
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
    try:
        hpnssh = config['pool_specification']['ssh']['hpn_server_swap']
    except KeyError:
        hpnssh = False
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
    _rflist = [_NODEPREP_FILE, _JOBPREP_FILE, _BLOBXFER_FILE, regfile]
    if not use_shipyard_docker_image:
        _rflist.append(_CASCADE_FILE)
        _rflist.append(_SETUP_PR_FILE)
        if perf:
            _rflist.append(_PERF_FILE)
    if hpnssh:
        _rflist.append(_HPNSSH_FILE)
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
    sas_urls = convoy.storage.upload_resource_files(
        blob_client, config, _rflist)
    del _rflist
    # create start task commandline
    start_task = [
        '{} -o {} -s {}{}{}{}{}{}{}{}{}{}{}{}'.format(
            _NODEPREP_FILE[0],
            offer,
            sku,
            preg,
            torrentflags,
            ' -a' if azurefile_vd else '',
            ' -b {}'.format(block_for_gr) if block_for_gr else '',
            ' -d' if use_shipyard_docker_image else '',
            ' -e {}'.format(encrypt_sha1tp) if encrypt else '',
            ' -f' if gluster else '',
            ' -g {}'.format(gpu_env) if gpu_env is not None else '',
            ' -n' if vm_size.lower() not in _VM_TCP_NO_TUNE else '',
            ' -p {}'.format(prefix) if prefix else '',
            ' -w' if hpnssh else '',
        ),
    ]
    # add additional start task commands
    try:
        start_task.extend(
            config['pool_specification']['additional_node_prep_commands'])
    except KeyError:
        pass
    # digest any input_data
    addlcmds = convoy.data.process_input_data(
        config, _BLOBXFER_FILE, config['pool_specification'])
    if addlcmds is not None:
        start_task.append(addlcmds)
    del addlcmds
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
            command_line=convoy.util.wrap_commands_in_shell(
                start_task, wait=False),
            run_elevated=True,
            wait_for_success=True,
            environment_settings=[
                batchmodels.EnvironmentSetting('LC_ALL', 'en_US.UTF-8'),
                batchmodels.EnvironmentSetting(
                    'SHIPYARD_STORAGE_ENV',
                    convoy.crypto.encrypt_string(
                        encrypt, '{}:{}:{}'.format(
                            convoy.storage.get_storageaccount(),
                            convoy.storage.get_storageaccount_endpoint(),
                            convoy.storage.get_storageaccount_key()),
                        config)
                )
            ],
            resource_files=[],
        ),
    )
    if encrypt:
        pool.certificate_references = [
            batchmodels.CertificateReference(
                encrypt_sha1tp, 'sha1',
                visibility=[batchmodels.CertificateVisibility.starttask]
            )
        ]
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
                'SHIPYARD_PRIVATE_REGISTRY_STORAGE_ENV',
                convoy.crypto.encrypt_string(
                    encrypt, '{}:{}:{}'.format(
                        config['credentials']['storage'][ssel]['account'],
                        config['credentials']['storage'][ssel]['endpoint'],
                        config['credentials']['storage'][ssel]['account_key']),
                    config)
            )
        )
        del ssel
    if (dockeruser is not None and len(dockeruser) > 0 and
            dockerpw is not None and len(dockerpw) > 0):
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('DOCKER_LOGIN_USERNAME', dockeruser)
        )
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'DOCKER_LOGIN_PASSWORD',
                convoy.crypto.encrypt_string(encrypt, dockerpw, config))
        )
    if perf:
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('SHIPYARD_TIMING', '1')
        )
    # create pool
    nodes = convoy.batch.create_pool(batch_client, config, pool)
    # set up gluster if specified
    if gluster:
        _setup_glusterfs(batch_client, blob_client, config, nodes)
    # create admin user on each node if requested
    convoy.batch.add_ssh_user(batch_client, config, nodes)
    # log remote login settings
    rls = convoy.batch.get_remote_login_settings(batch_client, config, nodes)
    # ingress data to shared fs if specified
    if ingress_files:
        convoy.data.ingress_data(batch_client, config, rls=rls, kind='shared')
    # wait for storage ingress processes
    convoy.data.wait_for_storage_threads(storage_threads)


def _setup_glusterfs(batch_client, blob_client, config, nodes):
    # type: (batch.BatchServiceClient, azureblob.BlockBlobService, dict,
    #        List[batchmodels.ComputeNode]) -> None
    """Setup glusterfs via multi-instance task
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
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
    sas_urls = convoy.storage.upload_resource_files(
        blob_client, config, [_GLUSTERPREP_FILE])
    batchtask = batchmodels.TaskAddParameter(
        id='gluster-setup',
        multi_instance_settings=batchmodels.MultiInstanceSettings(
            number_of_instances=config['pool_specification']['vm_count'],
            coordination_command_line=convoy.util.wrap_commands_in_shell([
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
    # hpn-ssh can only be used for Ubuntu currently
    try:
        if (config['pool_specification']['ssh']['hpn_server_swap'] and
                publisher != 'canonical' and offer != 'ubuntuserver'):
            logger.warning('cannot enable HPN SSH swap on {} {} {}'.format(
                publisher, offer, sku))
            config['pool_specification']['ssh']['hpn_server_swap'] = False
    except KeyError:
        pass
    # adjust ssh settings on windows
    if convoy.util.on_windows():
        try:
            ssh_pub_key = config['pool_specification']['ssh']['ssh_public_key']
        except KeyError:
            ssh_pub_key = None
        if ssh_pub_key is None:
            logger.warning(
                'disabling ssh user creation due to script being run '
                'from Windows and no public key is specified')
            config['pool_specification'].pop('ssh', None)
    # ensure file transfer settings
    try:
        xfer_files_with_pool = config['pool_specification'][
            'transfer_files_on_pool_creation']
    except KeyError:
        xfer_files_with_pool = False
        config['pool_specification'][
            'transfer_files_on_pool_creation'] = xfer_files_with_pool
    try:
        files = config['global_resources']['files']
        shared = False
        for fdict in files:
            if 'shared_data_volume' in fdict['destination']:
                shared = True
                break
        if convoy.util.on_windows() and shared and xfer_files_with_pool:
            raise RuntimeError(
                'cannot transfer files to shared data volume on Windows')
    except KeyError:
        pass
    # force disable block for global resources if ingressing data
    try:
        block_for_gr = config[
            'pool_specification']['block_until_all_global_resources_loaded']
    except KeyError:
        block_for_gr = True
    if xfer_files_with_pool and block_for_gr:
        logger.warning(
            'disabling block until all global resources loaded with '
            'transfer files on pool creation enabled')
        config['pool_specification'][
            'block_until_all_global_resources_loaded'] = False


def _adjust_general_settings(config):
    # type: (dict) -> None
    """Adjust general settings
    :param dict config: configuration dict
    """
    # adjust encryption settings on windows
    if convoy.util.on_windows():
        try:
            enc = config['batch_shipyard']['encryption']['enabled']
        except KeyError:
            enc = False
        if enc:
            logger.warning(
                'disabling credential encryption due to script being run '
                'from Windows')
            config['encryption']['enabled'] = False


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
        config = convoy.util.merge_dict(config, json.load(f))
    try:
        with open(args.pool, 'r') as f:
            config = convoy.util.merge_dict(config, json.load(f))
    except ValueError:
        raise
    except Exception:
        config['pool_specification'] = {
            'id': args.poolid
        }
    if args.action in (
            'addjobs', 'cleanmijobs', 'delcleanmijobs', 'deljobs',
            'termjobs', 'listtasks', 'listtaskfiles'):
        if args.configdir is not None and args.jobs is None:
                args.jobs = str(pathlib.Path(args.configdir, 'jobs.json'))
        try:
            with open(args.jobs, 'r') as f:
                config = convoy.util.merge_dict(config, json.load(f))
        except ValueError:
            raise
        except Exception:
            config['job_specifications'] = [{
                'id': args.jobid
            }]
    if args.verbose:
        logger.debug('config:\n' + json.dumps(config, indent=4))
    config['_verbose'] = args.verbose
    _populate_global_settings(config, args.action)
    config['_auto_confirm'] = args.yes

    batch_client, blob_client, queue_client, table_client = \
        _create_credentials(config)

    _adjust_general_settings(config)

    if args.action == 'addpool':
        # first check if pool exists to prevent accidential metadata clear
        if batch_client.pool.exists(config['pool_specification']['id']):
            raise RuntimeError(
                'attempting to create a pool that already exists: {}'.format(
                    config['pool_specification']['id']))
        convoy.storage.create_storage_containers(
            blob_client, queue_client, table_client, config)
        convoy.storage.clear_storage_containers(
            blob_client, queue_client, table_client, config)
        _adjust_settings_for_pool_creation(config)
        convoy.storage.populate_queues(queue_client, table_client, config)
        add_pool(batch_client, blob_client, config)
    elif args.action == 'resizepool':
        convoy.batch.resize_pool(batch_client, config)
    elif args.action == 'delpool':
        convoy.batch.del_pool(batch_client, config)
        convoy.storage.cleanup_with_del_pool(
            blob_client, queue_client, table_client, config)
    elif args.action == 'addsshuser':
        convoy.batch.add_ssh_user(batch_client, config)
        convoy.batch.get_remote_login_settings(batch_client, config)
    elif args.action == 'delnode':
        convoy.batch.del_node(batch_client, config, args.nodeid)
    elif args.action == 'addjobs':
        convoy.batch.add_jobs(
            batch_client, blob_client, config, _JOBPREP_FILE, _BLOBXFER_FILE)
    elif args.action == 'cleanmijobs':
        convoy.batch.clean_mi_jobs(batch_client, config)
    elif args.action == 'termjobs':
        convoy.batch.terminate_jobs(batch_client, config)
    elif args.action == 'deljobs':
        convoy.batch.del_jobs(batch_client, config)
    elif args.action == 'delcleanmijobs':
        convoy.batch.del_clean_mi_jobs(batch_client, config)
    elif args.action == 'delalljobs':
        convoy.batch.del_all_jobs(batch_client, config)
    elif args.action == 'grls':
        convoy.batch.get_remote_login_settings(batch_client, config)
    elif args.action == 'streamfile':
        convoy.batch.stream_file_and_wait_for_task(batch_client, args.filespec)
    elif args.action == 'gettaskfile':
        convoy.batch.get_file_via_task(batch_client, config, args.filespec)
    elif args.action == 'gettaskallfiles':
        convoy.batch.get_all_files_via_task(
            batch_client, config, args.filespec)
    elif args.action == 'getnodefile':
        convoy.batch.get_file_via_node(batch_client, config, args.nodeid)
    elif args.action == 'ingressdata':
        try:
            # ensure there are remote login settings
            rls = convoy.batch.get_remote_login_settings(
                batch_client, config, nodes=None)
            # ensure nodes are at least idle/running for shared ingress
            kind = 'all'
            if not convoy.batch.check_pool_nodes_runnable(
                    batch_client, config):
                kind = 'storage'
        except batchmodels.BatchErrorException as ex:
            if 'The specified pool does not exist' in ex.message.value:
                rls = None
                kind = 'storage'
            else:
                raise
        storage_threads = convoy.data.ingress_data(
            batch_client, config, rls=rls, kind=kind)
        convoy.data.wait_for_storage_threads(storage_threads)
    elif args.action == 'listjobs':
        convoy.batch.list_jobs(batch_client, config)
    elif args.action == 'listtasks':
        convoy.batch.list_tasks(batch_client, config)
    elif args.action == 'listtaskfiles':
        convoy.batch.list_task_files(batch_client, config)
    elif args.action == 'createcert':
        sha1tp = convoy.crypto.generate_pem_pfx_certificates(config)
        logger.info('SHA1 Thumbprint: {}'.format(sha1tp))
    elif args.action == 'addcert':
        convoy.batch.add_certificate_to_account(batch_client, config, False)
    elif args.action == 'delcert':
        convoy.batch.del_certificate_from_account(batch_client, config)
    elif args.action == 'delstorage':
        convoy.storage.delete_storage_containers(
            blob_client, queue_client, table_client, config)
    elif args.action == 'clearstorage':
        convoy.storage.clear_storage_containers(
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
        'grls, streamfile, gettaskfile, gettaskallfiles, getnodefile, '
        'ingressdata, listjobs, listtasks, listtaskfiles, createcert, '
        'addcert, delcert, clearstorage, delstorage')
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
    parser.add_argument('--version', action='version', version=_VERSION)
    return parser.parse_args()

if __name__ == '__main__':
    convoy.util.setup_logger(logger)
    main()
