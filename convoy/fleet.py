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
import subprocess
import time
try:
    import urllib.request as urllibreq
except ImportError:
    import urllib as urllibreq
import uuid
# non-stdlib imports
import azure.batch.batch_auth as batchauth
import azure.batch.batch_service_client as batchsc
import azure.batch.models as batchmodels
# local imports
from . import batch
from . import crypto
from . import data
from . import storage
from . import util
from .version import __version__

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_ROOT_PATH = pathlib.Path(__file__).resolve().parent.parent
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
_GLUSTERRESIZE_FILE = (
    'shipyard_glusterfs_resize.sh',
    str(pathlib.Path(_ROOT_PATH, 'scripts/shipyard_glusterfs_resize.sh'))
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


def populate_global_settings(config, pool_add_action):
    # type: (dict, bool) -> None
    """Populate global settings from config
    :param dict config: configuration dict
    :param bool pool_add_action: call from pool add action
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
    try:
        sasexpiry = config['batch_shipyard']['generated_sas_expiry_days']
    except KeyError:
        sasexpiry = None
    storage.set_storage_configuration(
        sep, postfix, sa, sakey, saep, sasexpiry)
    if not pool_add_action:
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
                imgid = util.decode_string(subprocess.check_output(
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
    storage.set_registry_file(regfile)


def create_clients(config):
    # type: (dict) -> tuple
    """Create authenticated clients
    :param dict config: configuration dict
    :rtype: tuple
    :return: (batch client, blob client, queue client, table client)
    """
    credentials = batchauth.SharedKeyCredentials(
        config['credentials']['batch']['account'],
        config['credentials']['batch']['account_key'])
    batch_client = batchsc.BatchServiceClient(
        credentials,
        base_url=config['credentials']['batch']['account_service_url'])
    batch_client.config.add_user_agent('batch-shipyard/{}'.format(__version__))
    blob_client, queue_client, table_client = storage.create_clients()
    return batch_client, blob_client, queue_client, table_client


def _setup_nvidia_docker_package(blob_client, config):
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
            util.compute_md5_for_file(pkg, False) !=
            _NVIDIA_DOCKER[offer]['md5']):
        response = urllibreq.urlopen(_NVIDIA_DOCKER[offer]['url'])
        with pkg.open('wb') as f:
            f.write(response.read())
        # check md5
        if (util.compute_md5_for_file(pkg, False) !=
                _NVIDIA_DOCKER[offer]['md5']):
            raise RuntimeError('md5 mismatch for {}'.format(pkg))
    return pkg


def _setup_azurefile_volume_driver(blob_client, config):
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
            util.compute_md5_for_file(bin, False) !=
            _AZUREFILE_DVD_BIN['md5']):
        response = urllibreq.urlopen(_AZUREFILE_DVD_BIN['url'])
        with bin.open('wb') as f:
            f.write(response.read())
        # check md5
        if (util.compute_md5_for_file(bin, False) !=
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
        f.write('AZURE_STORAGE_ACCOUNT={}\n'.format(sa).encode('utf8'))
        f.write('AZURE_STORAGE_ACCOUNT_KEY={}\n'.format(sakey).encode('utf8'))
        f.write('AZURE_STORAGE_BASE={}\n'.format(saep).encode('utf8'))
    # create docker volume mount command script
    volcreate = pathlib.Path(
        _ROOT_PATH, 'resources/azurefile-dockervolume-create.sh')
    with volcreate.open('wb') as f:
        f.write(b'#!/usr/bin/env bash\n\n')
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
                svkey, ' '.join(opts)).encode('utf8'))
    return bin, srv, srvenv, volcreate


def _add_pool(batch_client, blob_client, config):
    # type: (batchsc.BatchServiceClient, azureblob.BlockBlobService,
    #        dict) -> None
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
            batch.add_certificate_to_account(batch_client, config)
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
                encrypt_sha1tp = crypto.get_sha1_thumbprint_pfx(
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
        storage_threads = data.ingress_data(
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
    regfile = storage.get_registry_file()
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
        afbin, afsrv, afenv, afvc = _setup_azurefile_volume_driver(
            blob_client, config)
        _rflist.append((afbin.name, str(afbin)))
        _rflist.append((afsrv.name, str(afsrv)))
        _rflist.append((afenv.name, str(afenv)))
        _rflist.append((afvc.name, str(afvc)))
    # gpu settings
    if (vm_size.lower().startswith('standard_nc') or
            vm_size.lower().startswith('standard_nv')):
        gpupkg = _setup_nvidia_docker_package(blob_client, config)
        _rflist.append((gpupkg.name, str(gpupkg)))
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
    sas_urls = storage.upload_resource_files(
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
    addlcmds = data.process_input_data(
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
            command_line=util.wrap_commands_in_shell(
                start_task, wait=False),
            run_elevated=True,
            wait_for_success=True,
            environment_settings=[
                batchmodels.EnvironmentSetting('LC_ALL', 'en_US.UTF-8'),
                batchmodels.EnvironmentSetting(
                    'SHIPYARD_STORAGE_ENV',
                    crypto.encrypt_string(
                        encrypt, '{}:{}:{}'.format(
                            storage.get_storageaccount(),
                            storage.get_storageaccount_endpoint(),
                            storage.get_storageaccount_key()),
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
                crypto.encrypt_string(
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
                crypto.encrypt_string(encrypt, dockerpw, config))
        )
    if perf:
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('SHIPYARD_TIMING', '1')
        )
    # create pool
    nodes = batch.create_pool(batch_client, config, pool)
    # set up gluster if specified
    if gluster:
        _setup_glusterfs(
            batch_client, blob_client, config, nodes, _GLUSTERPREP_FILE,
            cmdline=None)
    # create admin user on each node if requested
    batch.add_ssh_user(batch_client, config, nodes)
    # log remote login settings
    rls = batch.get_remote_login_settings(batch_client, config, nodes)
    # ingress data to shared fs if specified
    if ingress_files:
        data.ingress_data(batch_client, config, rls=rls, kind='shared')
    # wait for storage ingress processes
    data.wait_for_storage_threads(storage_threads)


def _setup_glusterfs(
        batch_client, blob_client, config, nodes, shell_script, cmdline=None):
    # type: (batchsc.BatchServiceClient, azureblob.BlockBlobService, dict,
    #        List[batchmodels.ComputeNode], str, str) -> None
    """Setup glusterfs via multi-instance task
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param list nodes: list of nodes
    :param str shell_script: glusterfs setup script to use
    :param str cmdline: coordination cmdline
    """
    # get volume type/options
    voltype = 'replica'
    volopts = None
    shared_data_volumes = config[
        'global_resources']['docker_volumes']['shared_data_volumes']
    for key in shared_data_volumes:
        try:
            if shared_data_volumes[key]['volume_driver'] == 'glusterfs':
                voltype = shared_data_volumes[key]['volume_type']
                volopts = shared_data_volumes[key]['volume_options']
        except KeyError:
            pass
    if volopts is not None and len(volopts) == 0:
        volopts = None
    pool_id = config['pool_specification']['id']
    job_id = 'shipyard-glusterfs-{}'.format(uuid.uuid4())
    job = batchmodels.JobAddParameter(
        id=job_id,
        pool_info=batchmodels.PoolInformation(pool_id=pool_id),
    )
    batch_client.job.add(job)
    # create coordination command line
    if cmdline is None:
        if config['pool_specification']['offer'].lower() == 'ubuntuserver':
            tempdisk = '/mnt'
        else:
            tempdisk = '/mnt/resource'
        cmdline = util.wrap_commands_in_shell([
            '$AZ_BATCH_TASK_DIR/{} {} {}'.format(
                shell_script[0], voltype.lower(), tempdisk)])
    # create application command line
    appcmd = [
        '[[ -f $AZ_BATCH_TASK_DIR/.glusterfs_success ]] || exit 1',
    ]
    if volopts is not None:
        for vo in volopts:
            appcmd.append('gluster volume set gv0 {}'.format(vo))
    # upload script
    sas_urls = storage.upload_resource_files(
        blob_client, config, [shell_script])
    batchtask = batchmodels.TaskAddParameter(
        id='gluster-setup',
        multi_instance_settings=batchmodels.MultiInstanceSettings(
            number_of_instances=config['pool_specification']['vm_count'],
            coordination_command_line=cmdline,
            common_resource_files=[
                batchmodels.ResourceFile(
                    file_path=shell_script[0],
                    blob_source=sas_urls[shell_script[0]],
                    file_mode='0755'),
            ],
        ),
        command_line=util.wrap_commands_in_shell(appcmd),
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
    if vm_count < 1:
        raise ValueError('invalid vm_count: {}'.format(vm_count))
    try:
        p2p = config['data_replication']['peer_to_peer']['enabled']
    except KeyError:
        p2p = False
    try:
        internode = config[
            'pool_specification']['inter_node_communication_enabled']
    except KeyError:
        internode = False
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
            internode = False
            logger.warning(
                ('disabling inter-node communication as pool size of {} '
                 'exceeds max limit of {} vms for setting').format(
                     vm_count, max_vms))
            config['pool_specification'][
                'inter_node_communication_enabled'] = internode
    # ensure settings p2p/internode settings are compatible
    if p2p and not internode:
        internode = True
        config['pool_specification'][
            'inter_node_communication_enabled'] = internode
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
    if util.on_windows():
        try:
            ssh_pub_key = config['pool_specification']['ssh']['ssh_public_key']
        except KeyError:
            ssh_pub_key = None
        if ssh_pub_key is None:
            logger.warning(
                'disabling ssh user creation due to script being run '
                'from Windows and no public key is specified')
            config['pool_specification'].pop('ssh', None)
    # glusterfs requires internode comms and more than 1 node
    try:
        num_gluster = 0
        shared = config['global_resources']['docker_volumes'][
            'shared_data_volumes']
        for sdvkey in shared:
            if shared[sdvkey]['volume_driver'] == 'glusterfs':
                if not internode:
                    # do not modify value and proceed since this interplays
                    # with p2p settings, simply raise exception and force
                    # user to reconfigure
                    raise ValueError(
                        'inter node communication in pool configuration '
                        'must be enabled for glusterfs')
                if vm_count <= 1:
                    raise ValueError('vm_count should exceed 1 for glusterfs')
                num_gluster += 1
                try:
                    if shared[sdvkey]['volume_type'] != 'replica':
                        raise ValueError(
                            'only replicated GlusterFS volumes are '
                            'currently supported')
                except KeyError:
                    pass
        if num_gluster > 1:
            raise ValueError(
                'cannot create more than one GlusterFS volume per pool')
    except KeyError:
        pass
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
        if util.on_windows() and shared and xfer_files_with_pool:
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


def adjust_general_settings(config):
    # type: (dict) -> None
    """Adjust general settings
    :param dict config: configuration dict
    """
    # check for deprecated properties
    try:
        config['pool_specification']['ssh_docker_tunnel']
    except KeyError:
        pass
    else:
        raise ValueError(
            'Invalid ssh_docker_tunnel property found in pool_specification. '
            'Please update your pool configuration file. See the '
            'configuration doc for more information.')
    # adjust encryption settings on windows
    if util.on_windows():
        try:
            enc = config['batch_shipyard']['encryption']['enabled']
        except KeyError:
            enc = False
        if enc:
            logger.warning(
                'disabling credential encryption due to script being run '
                'from Windows')
            config['encryption']['enabled'] = False


def action_cert_create(config):
    # type: (dict) -> None
    """Action: Cert Create
    :param dict config: configuration dict
    """
    sha1tp = crypto.generate_pem_pfx_certificates(config)
    logger.info('SHA1 Thumbprint: {}'.format(sha1tp))


def action_cert_add(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Cert Add
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.add_certificate_to_account(batch_client, config, False)


def action_cert_list(batch_client):
    # type: (batchsc.BatchServiceClient) -> None
    """Action: Cert List
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    """
    batch.list_certificates_in_account(batch_client)


def action_cert_del(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Cert Del
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.del_certificate_from_account(batch_client, config)


def action_pool_add(
        batch_client, blob_client, queue_client, table_client, config):
    # type: (batchsc.BatchServiceClient, azureblob.BlockBlobService,
    #        azurequeue.QueueService, azuretable.TableService, dict) -> None
    """Action: Pool Add
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    # first check if pool exists to prevent accidential metadata clear
    if batch_client.pool.exists(config['pool_specification']['id']):
        raise RuntimeError(
            'attempting to create a pool that already exists: {}'.format(
                config['pool_specification']['id']))
    storage.create_storage_containers(
        blob_client, queue_client, table_client, config)
    storage.clear_storage_containers(
        blob_client, queue_client, table_client, config)
    _adjust_settings_for_pool_creation(config)
    storage.populate_queues(queue_client, table_client, config)
    _add_pool(batch_client, blob_client, config)


def action_pool_list(batch_client):
    # type: (batchsc.BatchServiceClient) -> None
    """Action: Pool List
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    """
    batch.list_pools(batch_client)


def action_pool_delete(
        batch_client, blob_client, queue_client, table_client, config,
        wait=False):
    # type: (batchsc.BatchServiceClient, azureblob.BlockBlobService,
    #        azurequeue.QueueService, azuretable.TableService, dict,
    #        bool) -> None
    """Action: Pool Delete
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool wait: wait for pool to delete
    """
    deleted = False
    try:
        deleted = batch.del_pool(batch_client, config)
    except batchmodels.BatchErrorException as ex:
        logger.exception(ex)
        if 'The specified pool does not exist' in ex.message.value:
            deleted = True
    if deleted:
        storage.cleanup_with_del_pool(
            blob_client, queue_client, table_client, config)
        if wait:
            pool_id = config['pool_specification']['id']
            logger.debug('waiting for pool {} to delete'.format(pool_id))
            while batch_client.pool.exists(pool_id):
                time.sleep(3)


def action_pool_resize(batch_client, blob_client, config, wait):
    # type: (batchsc.BatchServiceClient, azureblob.BlockBlobService,
    #        dict, bool) -> None
    """Resize pool that may contain glusterfs
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param bool wait: wait for operation to complete
    """
    pool_id = config['pool_specification']['id']
    # check direction of resize
    vm_count = int(config['pool_specification']['vm_count'])
    _pool = batch_client.pool.get(pool_id)
    if vm_count == _pool.current_dedicated == _pool.target_dedicated:
        logger.error(
            'pool {} is already at {} nodes'.format(pool_id, vm_count))
        return
    resize_up = True
    if vm_count < _pool.target_dedicated:
        resize_up = False
    del _pool
    create_ssh_user = False
    # try to get handle on public key, avoid generating another set
    # of keys
    if resize_up:
        try:
            username = config['pool_specification']['ssh']['username']
            if username is None or len(username) == 0:
                raise KeyError()
        except KeyError:
            logger.info('not creating ssh user on new nodes of pool {}'.format(
                pool_id))
        else:
            try:
                ssh_pub_key = config['pool_specification']['ssh'][
                    'ssh_public_key']
            except KeyError:
                ssh_pub_key = None
            if ssh_pub_key is None:
                sfp = pathlib.Path(crypto.get_ssh_key_prefix() + '.pub')
                if sfp.exists():
                    logger.debug(
                        'setting public key for ssh user to: {}'.format(sfp))
                    config['pool_specification']['ssh'][
                        'ssh_public_key'] = str(sfp)
                    create_ssh_user = True
                else:
                    logger.warning(
                        ('not creating ssh user for new nodes of pool {} as '
                         'an existing ssh public key cannot be found').format(
                             pool_id))
                    create_ssh_user = False
    # check if this is a glusterfs-enabled pool
    voltype = 'replica'
    old_nodes = {}
    try:
        for svkey in config[
                'global_resources']['docker_volumes']['shared_data_volumes']:
            conf = config['global_resources']['docker_volumes'][
                'shared_data_volumes'][svkey]
            if conf['volume_driver'] == 'glusterfs':
                gluster_present = True
                try:
                    voltype = conf['volume_type']
                except KeyError:
                    pass
                break
    except KeyError:
        gluster_present = False
    logger.debug('glusterfs shared volume present: {}'.format(
        gluster_present))
    if gluster_present:
        logger.debug('forcing wait to True due to glusterfs')
        wait = True
    # cache old nodes
    if gluster_present or create_ssh_user:
        for node in batch_client.compute_node.list(pool_id):
            old_nodes[node.id] = node.ip_address
    # resize pool
    nodes = batch.resize_pool(batch_client, config, wait)
    # add ssh user to new nodes if present
    if create_ssh_user and resize_up:
        if wait:
            # get list of new nodes only
            new_nodes = [node for node in nodes if node.id not in old_nodes]
            # create admin user on each new node if requested
            batch.add_ssh_user(batch_client, config, nodes=new_nodes)
            # log remote login settings for new ndoes
            batch.get_remote_login_settings(
                batch_client, config, nodes=new_nodes)
            del new_nodes
        else:
            logger.warning('ssh user was not added as --wait was not given')
    # add brick for new nodes
    if gluster_present and resize_up:
        # get internal ip addresses of new nodes
        new_nodes = [
            node.ip_address for node in nodes if node.id not in old_nodes
        ]
        masterip = next(iter(old_nodes.values()))
        # get tempdisk mountpoint
        if config['pool_specification']['offer'].lower() == 'ubuntuserver':
            tempdisk = '/mnt'
        else:
            tempdisk = '/mnt/resource'
        # construct cmdline
        vm_count = config['pool_specification']['vm_count']
        cmdline = util.wrap_commands_in_shell([
            '$AZ_BATCH_TASK_DIR/{} {} {} {} {} {}'.format(
                _GLUSTERRESIZE_FILE[0], voltype.lower(), tempdisk, vm_count,
                masterip, ' '.join(new_nodes))])
        # setup gluster
        _setup_glusterfs(
            batch_client, blob_client, config, nodes, _GLUSTERRESIZE_FILE,
            cmdline=cmdline)


def action_pool_grls(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Grls
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.get_remote_login_settings(batch_client, config)


def action_pool_listnodes(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Listnodes
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.list_nodes(batch_client, config)


def action_pool_asu(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Asu
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.add_ssh_user(batch_client, config)
    batch.get_remote_login_settings(batch_client, config)


def action_pool_dsu(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Dsu
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.del_ssh_user(batch_client, config)


def action_pool_delnode(batch_client, config, nodeid):
    # type: (batchsc.BatchServiceClient, dict, str) -> None
    """Action: Pool Delnode
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param str nodeid: nodeid to delete
    """
    batch.del_node(batch_client, config, nodeid)


def action_jobs_add(batch_client, blob_client, config, recreate):
    # type: (batchsc.BatchServiceClient, azureblob.BlockBlobService,
    #        dict, bool) -> None
    """Action: Jobs Add
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param bool recreate: recreate jobs if completed
    """
    batch.add_jobs(
        batch_client, blob_client, config, _JOBPREP_FILE, _BLOBXFER_FILE,
        recreate)


def action_jobs_list(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Jobs List
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.list_jobs(batch_client, config)


def action_jobs_listtasks(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Jobs Listtasks
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.list_tasks(batch_client, config)


def action_jobs_termtasks(batch_client, config, jobid, taskid, wait, force):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool, bool) -> None
    """Action: Jobs Termtasks
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param str jobid: job id
    :param str taskid: task id
    :param bool wait: wait for action to complete
    :param bool force: force docker kill even if completed
    """
    if taskid is not None and jobid is None:
        raise ValueError(
            'cannot specify a task to terminate without the corresponding '
            'job id')
    if force and (taskid is None or jobid is None):
        raise ValueError('cannot force docker kill without task id/job id')
    batch.terminate_tasks(
        batch_client, config, jobid=jobid, taskid=taskid, wait=wait,
        force=force)


def action_jobs_deltasks(batch_client, config, jobid, taskid, wait):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool) -> None
    """Action: Jobs Deltasks
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param str jobid: job id
    :param str taskid: task id
    :param bool wait: wait for action to complete
    """
    if taskid is not None and jobid is None:
        raise ValueError(
            'cannot specify a task to delete without the corresponding '
            'job id')
    batch.del_tasks(
        batch_client, config, jobid=jobid, taskid=taskid, wait=wait)


def action_jobs_term(batch_client, config, all, jobid, wait):
    # type: (batchsc.BatchServiceClient, dict, bool, str, bool) -> None
    """Action: Jobs Term
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param bool all: all jobs
    :param str jobid: job id
    :param bool wait: wait for action to complete
    """
    if all:
        if jobid is not None:
            raise ValueError('cannot specify both --all and --jobid')
        batch.terminate_all_jobs(batch_client, config, wait=wait)
    else:
        batch.terminate_jobs(
            batch_client, config, jobid=jobid, wait=wait)


def action_jobs_del(batch_client, config, all, jobid, wait):
    # type: (batchsc.BatchServiceClient, dict, bool, str, bool) -> None
    """Action: Jobs Del
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param bool all: all jobs
    :param str jobid: job id
    :param bool wait: wait for action to complete
    """
    if all:
        if jobid is not None:
            raise ValueError('cannot specify both --all and --jobid')
        batch.del_all_jobs(batch_client, config, wait=wait)
    else:
        batch.del_jobs(batch_client, config, jobid=jobid, wait=wait)


def action_jobs_cmi(batch_client, config, delete):
    # type: (batchsc.BatchServiceClient, dict, bool) -> None
    """Action: Jobs Cmi
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param bool delete: delete all cmi jobs
    """
    if delete:
        batch.del_clean_mi_jobs(batch_client, config)
    else:
        batch.clean_mi_jobs(batch_client, config)
        batch.del_clean_mi_jobs(batch_client, config)


def action_storage_del(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Action: Storage Del
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    storage.delete_storage_containers(
        blob_client, queue_client, table_client, config)


def action_storage_clear(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Action: Storage Clear
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    storage.clear_storage_containers(
        blob_client, queue_client, table_client, config)


def action_data_stream(batch_client, config, filespec, disk):
    # type: (batchsc.BatchServiceClient, dict, str, bool) -> None
    """Action: Data Stream
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param str filespec: filespec of file to retrieve
    :param bool disk: write streamed data to disk instead
    """
    batch.stream_file_and_wait_for_task(batch_client, config, filespec, disk)


def action_data_listfiles(batch_client, config, jobid, taskid):
    # type: (batchsc.BatchServiceClient, dict, str, str) -> None
    """Action: Data Listfiles
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param str jobid: job id to list
    :param str taskid: task id to list
    """
    if taskid is not None and jobid is None:
        raise ValueError(
            'cannot specify a task to list files without the corresponding '
            'job id')
    batch.list_task_files(batch_client, config, jobid, taskid)


def action_data_getfile(batch_client, config, all, filespec):
    # type: (batchsc.BatchServiceClient, dict, bool, str) -> None
    """Action: Data Getfile
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param bool all: retrieve all files
    :param str filespec: filespec of file to retrieve
    """
    if all:
        batch.get_all_files_via_task(batch_client, config, filespec)
    else:
        batch.get_file_via_task(batch_client, config, filespec)


def action_data_getfilenode(batch_client, config, all, nodeid):
    # type: (batchsc.BatchServiceClient, dict, bool, str) -> None
    """Action: Data Getfilenode
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param bool all: retrieve all files
    :param str nodeid: node id to retrieve file from
    """
    if all:
        batch.get_all_files_via_node(batch_client, config, nodeid)
    else:
        batch.get_file_via_node(batch_client, config, nodeid)


def action_data_ingress(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Data Ingress
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    try:
        # ensure there are remote login settings
        rls = batch.get_remote_login_settings(
            batch_client, config, nodes=None)
        # ensure nodes are at least idle/running for shared ingress
        kind = 'all'
        if not batch.check_pool_nodes_runnable(
                batch_client, config):
            kind = 'storage'
    except batchmodels.BatchErrorException as ex:
        if 'The specified pool does not exist' in ex.message.value:
            rls = None
            kind = 'storage'
        else:
            raise
    storage_threads = data.ingress_data(
        batch_client, config, rls=rls, kind=kind)
    data.wait_for_storage_threads(storage_threads)
