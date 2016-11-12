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
from . import settings
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


def _adjust_general_settings(config):
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
    try:
        config['docker_registry']['login']
    except KeyError:
        pass
    else:
        raise ValueError(
            'Invalid docker_registry:login property found in global '
            'configuration. Please update your global configuration and '
            'credentials file. See the configuration doc for more '
            'information.')
    try:
        config['docker_registry']['storage_account_settings']
    except KeyError:
        pass
    else:
        raise ValueError(
            'Invalid docker_registry:storage_account_settings property '
            'found in global configuration. Please update your global '
            'configuration file. See the configuration doc for more '
            'information.')
    # adjust encryption settings on windows
    if util.on_windows():
        enc = settings.batch_shipyard_encryption_enabled(config)
        if enc:
            logger.warning(
                'disabling credential encryption due to script being run '
                'from Windows')
            settings.set_batch_shipyard_encryption_enabled(config, False)


def _populate_global_settings(config):
    # type: (dict) -> None
    """Populate global settings from config
    :param dict config: configuration dict
    """
    bs = settings.batch_shipyard_settings(config)
    sc = settings.credentials_storage(config, bs.storage_account_settings)
    bc = settings.credentials_batch(config)
    storage.set_storage_configuration(
        bs.storage_entity_prefix,
        '-'.join((bc.account.lower(), settings.pool_id(config, lower=True))),
        sc.account,
        sc.account_key,
        sc.endpoint,
        bs.generated_sas_expiry_days)


def _create_clients(config):
    # type: (dict) -> tuple
    """Create authenticated clients
    :param dict config: configuration dict
    :rtype: tuple
    :return: (batch client, blob client, queue client, table client)
    """
    bc = settings.credentials_batch(config)
    credentials = batchauth.SharedKeyCredentials(bc.account, bc.account_key)
    batch_client = batchsc.BatchServiceClient(
        credentials, base_url=bc.account_service_url)
    batch_client.config.add_user_agent('batch-shipyard/{}'.format(__version__))
    blob_client, queue_client, table_client = storage.create_clients()
    return batch_client, blob_client, queue_client, table_client


def initialize(config):
    # type: (dict) -> tuple
    """Initialize fleet and create authenticated clients
    :param dict config: configuration dict
    :rtype: tuple
    :return: (batch client, blob client, queue client, table client)
    """
    _adjust_general_settings(config)
    _populate_global_settings(config)
    return _create_clients(config)


def _setup_nvidia_docker_package(blob_client, config):
    # type: (azure.storage.blob.BlockBlobService, dict) -> pathlib.Path
    """Set up the nvidia docker package
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :rtype: pathlib.Path
    :return: package path
    """
    offer = settings.pool_offer(config, lower=True)
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
    publisher = settings.pool_publisher(config, lower=True)
    offer = settings.pool_offer(config, lower=True)
    sku = settings.pool_sku(config, lower=True)
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
    sdv = settings.global_resources_shared_data_volumes(config)
    for svkey in sdv:
        if settings.is_shared_data_volume_azure_file(sdv, svkey):
            # check every entry to ensure the same storage account
            _sa = settings.credentials_storage(
                config,
                settings.azure_file_storage_account_settings(sdv, svkey))
            if sa is not None and sa.account != _sa.account:
                raise ValueError(
                    'multiple storage accounts are not supported for '
                    'azurefile docker volume driver')
            sa = _sa
        elif not settings.is_shared_data_volume_gluster(sdv, svkey):
            raise NotImplementedError(
                'Unsupported volume driver: {}'.format(
                    settings.shared_data_volume_driver(sdv, svkey)))
    if sa is None:
        raise RuntimeError(
            'storage account not specified for azurefile docker volume driver')
    srvenv = pathlib.Path(
        _ROOT_PATH, 'resources/azurefile-dockervolumedriver.env')
    with srvenv.open('wb') as f:
        f.write('AZURE_STORAGE_ACCOUNT={}\n'.format(sa.account).encode('utf8'))
        f.write('AZURE_STORAGE_ACCOUNT_KEY={}\n'.format(
            sa.account_key).encode('utf8'))
        f.write('AZURE_STORAGE_BASE={}\n'.format(sa.endpoint).encode('utf8'))
    # create docker volume mount command script
    volcreate = pathlib.Path(
        _ROOT_PATH, 'resources/azurefile-dockervolume-create.sh')
    with volcreate.open('wb') as f:
        f.write(b'#!/usr/bin/env bash\n\n')
        for svkey in sdv:
            if settings.is_shared_data_volume_gluster(sdv, svkey):
                continue
            opts = [
                '-o share={}'.format(settings.azure_file_share_name(
                    sdv, svkey))
            ]
            mo = settings.azure_file_mount_options(sdv, svkey)
            if mo is not None:
                for opt in mo:
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
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    if encrypt:
        pfx = crypto.get_encryption_pfx_settings(config)
        batch.add_certificate_to_account(batch_client, config)
    # retrieve settings
    pool_settings = settings.pool_settings(config)
    block_for_gr = None
    if pool_settings.block_until_all_global_resources_loaded:
        images = settings.global_resources_docker_images(config)
        if len(images) > 0:
            block_for_gr = ','.join([x for x in images])
    # ingress data to Azure Blob Storage if specified
    storage_threads = []
    if pool_settings.transfer_files_on_pool_creation:
        storage_threads = data.ingress_data(
            batch_client, config, rls=None, kind='storage')
    # shipyard settings
    bs = settings.batch_shipyard_settings(config)
    # data replication and peer-to-peer settings
    dr = settings.data_replication_settings(config)
    # create torrent flags
    torrentflags = ' -t {}:{}:{}:{}:{}'.format(
        dr.peer_to_peer.enabled, dr.non_peer_to_peer_concurrent_downloading,
        dr.peer_to_peer.direct_download_seed_bias,
        dr.peer_to_peer.compression,
        settings.docker_registry_private_allow_public_pull(config))
    # azure blob storage backed private registry settings
    psa, pcont = settings.docker_registry_azure_storage(config)
    # check shared data volume mounts
    azurefile_vd = False
    gluster = False
    try:
        sdv = settings.global_resources_shared_data_volumes(config)
        for sdvkey in sdv:
            if settings.is_shared_data_volume_azure_file(sdv, sdvkey):
                azurefile_vd = True
            elif settings.is_shared_data_volume_gluster(sdv, sdvkey):
                gluster = True
            else:
                raise ValueError('Unknown shared data volume: {}'.format(
                    settings.shared_data_volume_driver(sdv, sdvkey)))
    except KeyError:
        pass
    # create resource files list
    _rflist = [_NODEPREP_FILE, _JOBPREP_FILE, _BLOBXFER_FILE]
    if not bs.use_shipyard_docker_image:
        _rflist.append(_CASCADE_FILE)
        _rflist.append(_SETUP_PR_FILE)
        if bs.store_timing_metrics:
            _rflist.append(_PERF_FILE)
    if pool_settings.ssh.hpn_server_swap:
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
    if settings.is_gpu_pool(pool_settings.vm_size):
        gpupkg = _setup_nvidia_docker_package(blob_client, config)
        _rflist.append((gpupkg.name, str(gpupkg)))
        gpu_env = '{}:{}:{}'.format(
            settings.is_gpu_visualization_pool(pool_settings.vm_size),
            _NVIDIA_DRIVER,
            gpupkg.name)
    else:
        gpu_env = None
    # pick latest sku
    node_agent_skus = batch_client.account.list_node_agent_skus()
    skus_to_use = [
        (nas, image_ref) for nas in node_agent_skus for image_ref in sorted(
            nas.verified_image_references, key=lambda item: item.sku)
        if image_ref.publisher.lower() == pool_settings.publisher.lower() and
        image_ref.offer.lower() == pool_settings.offer.lower() and
        image_ref.sku.lower() == pool_settings.sku.lower()
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
            pool_settings.offer,
            pool_settings.sku,
            torrentflags,
            ' -a' if azurefile_vd else '',
            ' -b {}'.format(block_for_gr) if block_for_gr else '',
            ' -d' if bs.use_shipyard_docker_image else '',
            ' -e {}'.format(pfx.sha1) if encrypt else '',
            ' -f' if gluster else '',
            ' -g {}'.format(gpu_env) if gpu_env is not None else '',
            ' -n' if settings.can_tune_tcp(pool_settings.vm_size) else '',
            ' -p {}'.format(
                bs.storage_entity_prefix) if bs.storage_entity_prefix else '',
            ' -r {}'.format(pcont) if pcont else '',
            ' -w' if pool_settings.ssh.hpn_server_swap else '',
        ),
    ]
    # add additional start task commands
    start_task.extend(pool_settings.additional_node_prep_commands)
    # digest any input data
    addlcmds = data.process_input_data(
        config, _BLOBXFER_FILE, settings.pool_specification(config))
    if addlcmds is not None:
        start_task.append(addlcmds)
    del addlcmds
    # create pool param
    pool = batchmodels.PoolAddParameter(
        id=pool_settings.id,
        virtual_machine_configuration=batchmodels.VirtualMachineConfiguration(
            image_reference=image_ref_to_use,
            node_agent_sku_id=sku_to_use.id),
        vm_size=pool_settings.vm_size,
        target_dedicated=pool_settings.vm_count,
        max_tasks_per_node=pool_settings.max_tasks_per_node,
        enable_inter_node_communication=pool_settings.
        inter_node_communication_enabled,
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
                pfx.sha1, 'sha1',
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
                blob_source=pool_settings.gpu_driver,
                file_mode='0755')
        )
    if psa:
        psa = settings.credentials_storage(config, psa)
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'SHIPYARD_PRIVATE_REGISTRY_STORAGE_ENV',
                crypto.encrypt_string(
                    encrypt, '{}:{}:{}'.format(
                        psa.account, psa.endpoint, psa.account_key),
                    config
                )
            )
        )
    hubuser, hubpw = settings.docker_registry_hub_login(config)
    if hubuser:
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'DOCKER_LOGIN_HUB_USERNAME', hubuser)
        )
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'DOCKER_LOGIN_HUB_PASSWORD',
                crypto.encrypt_string(encrypt, hubpw, config))
        )
    if bs.store_timing_metrics:
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
    if pool_settings.transfer_files_on_pool_creation:
        _pool = batch_client.pool.get(pool.id)
        data.ingress_data(
            batch_client, config, rls=rls, kind='shared',
            current_dedicated=_pool.current_dedicated)
        del _pool
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
        '[[ -f $AZ_BATCH_TASK_WORKING_DIR/.glusterfs_success ]] || exit 1',
    ]
    if volopts is not None:
        for vo in volopts:
            appcmd.append('gluster volume set gv0 {}'.format(vo))
    # upload script
    sas_urls = storage.upload_resource_files(
        blob_client, config, [shell_script])
    # get pool current dedicated
    pool = batch_client.pool.get(pool_id)
    batchtask = batchmodels.TaskAddParameter(
        id='gluster-setup',
        multi_instance_settings=batchmodels.MultiInstanceSettings(
            number_of_instances=pool.current_dedicated,
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
    # add job and task
    batch_client.job.add(job)
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


def _update_docker_images(batch_client, config, image=None, digest=None):
    # type: (batchsc.BatchServiceClient, dict, str, str) -> None
    """Update docker images in pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str image: docker image to update
    :param str digest: digest to update to
    """
    # first check that peer-to-peer is disabled for pool
    pool_id = config['pool_specification']['id']
    try:
        if config['data_replication']['peer_to_peer']['enabled']:
            raise RuntimeError(
                'cannot update docker images for a pool with peer-to-peer '
                'image distribution')
    except KeyError:
        pass
    # mark if these are private registry images
    registry = ''
    try:
        psa = config['docker_registry']['private']['azure_storage'][
            'storage_account_settings']
        if psa is None or len(psa) == 0:
            raise KeyError()
    except KeyError:
        psa = None
    if psa is not None:
        registry = 'localhost:5000/'
    del psa

    # TODO ACR private registry images

    # if image is specified, check that it exists for this pool
    if image is not None:
        if image not in config['global_resources']['docker_images']:
            raise RuntimeError(
                ('cannot update docker image {} not specified as a global '
                 'resource for pool').format(image))
        else:
            if digest is None:
                images = [image]
            else:
                images = ['{}@{}'.format(image, digest)]
    else:
        images = config['global_resources']['docker_images']
    # create job for update
    job_id = 'shipyard-udi-{}'.format(uuid.uuid4())
    job = batchmodels.JobAddParameter(
        id=job_id,
        pool_info=batchmodels.PoolInformation(pool_id=pool_id),
    )
    # create coordination command line
    # 1. log in again in case of cred expiry
    # 2. pull images with respect to registry
    # 3. tag images that are in a private registry
    # 4. prune docker images with no tag
    taskenv = []
    coordcmd = []
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    hubuser, hubpw = settings.docker_registry_hub_login(config)
    if hubuser:
        taskenv.append(batchmodels.EnvironmentSetting(
            'DOCKER_LOGIN_HUB_USERNAME', hubuser))
        taskenv.append(batchmodels.EnvironmentSetting(
            'DOCKER_LOGIN_HUB_PASSWORD',
            crypto.encrypt_string(encrypt, hubpw, config)))
        if encrypt:
            coordcmd.append(
                'DOCKER_LOGIN_HUB_PASSWORD='
                '`echo $DOCKER_LOGIN_HUB_PASSWORD | base64 -d | '
                'openssl rsautl -decrypt -inkey '
                '$AZ_BATCH_NODE_STARTUP_DIR/certs/key.pem`')
        coordcmd.append(
            'docker login -u $DOCKER_LOGIN_HUB_USERNAME '
            '-p $DOCKER_LOGIN_HUB_PASSWORD')
    coordcmd.extend(['docker pull {}{}'.format(registry, x) for x in images])
    if registry != '':
        coordcmd.extend(
            ['docker tag {}{} {}'.format(registry, x, x) for x in images])
    coordcmd.append(
        'docker images --filter dangling=true -q --no-trunc | '
        'xargs --no-run-if-empty docker rmi')
    coordcmd.append('touch .udi_success')
    coordcmd = util.wrap_commands_in_shell(coordcmd)
    # create task
    batchtask = batchmodels.TaskAddParameter(
        id='update-docker-images',
        command_line=coordcmd,
        environment_settings=taskenv,
        run_elevated=True,
    )
    # get pool current dedicated
    pool = batch_client.pool.get(pool_id)
    # create multi-instance task for pools with more than 1 node
    if pool.current_dedicated > 1:
        batchtask.multi_instance_settings = batchmodels.MultiInstanceSettings(
            number_of_instances=pool.current_dedicated,
            coordination_command_line=coordcmd,
        )
        # create application command line
        appcmd = util.wrap_commands_in_shell([
            '[[ -f $AZ_BATCH_TASK_WORKING_DIR/.udi_success ]] || exit 1'])
        batchtask.command_line = appcmd
    # add job and task
    batch_client.job.add(job)
    batch_client.task.add(job_id=job_id, task=batchtask)
    logger.debug(
        ('waiting for update docker images task {} in job {} '
         'to complete').format(batchtask.id, job_id))
    # wait for task to complete
    while True:
        batchtask = batch_client.task.get(job_id, batchtask.id)
        if batchtask.state == batchmodels.TaskState.completed:
            break
        time.sleep(1)
    # ensure all nodes have success file if multi-instance
    success = True
    if pool.current_dedicated > 1:
        nodes = batch_client.compute_node.list(pool_id)
        for node in nodes:
            try:
                batch_client.file.get_node_file_properties_from_compute_node(
                    pool_id, node.id,
                    ('workitems/{}/job-1/update-docker-images/wd/'
                     '.udi_success').format(job_id))
            except batchmodels.BatchErrorException:
                logger.error('udi success file absent on node {}'.format(
                    node.id))
                success = False
                break
    else:
        task = batch_client.task.get(job_id, batchtask.id)
        if task.execution_info is None or task.execution_info.exit_code != 0:
            success = False
            # stream stderr to console
            batch.stream_file_and_wait_for_task(
                batch_client, config,
                '{},update-docker-images,stderr.txt'.format(job_id))
    # delete job
    batch_client.job.delete(job_id)
    if not success:
        raise RuntimeError('update docker images job failed')
    logger.info(
        'update docker images task {} in job {} completed'.format(
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
    vm_count = config['pool_specification']['vm_count']
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
    vm_count = config['pool_specification']['vm_count']
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
        # get pool current dedicated
        _pool = batch_client.pool.get(pool_id)
        # ensure current dedicated is the target
        vm_count = config['pool_specification']['vm_count']
        if vm_count != _pool.current_dedicated:
            raise RuntimeError(
                ('cannot perform glusterfs setup on new nodes, unexpected '
                 'current dedicated {} to vm_count {}').format(
                     _pool.current_dedicated, vm_count))
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


def action_pool_udi(batch_client, config, image, digest):
    # type: (batchsc.BatchServiceClient, dict, str, str) -> None
    """Action: Pool Udi
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param str image: image to update
    :param str digest: digest to update to
    """
    if digest is not None and image is None:
        raise ValueError(
            'cannot specify a digest to update to without the image')
    _update_docker_images(batch_client, config, image, digest)


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


def action_jobs_listtasks(batch_client, config, jobid):
    # type: (batchsc.BatchServiceClient, dict, str) -> None
    """Action: Jobs Listtasks
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    batch.list_tasks(batch_client, config, jobid)


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
    pool_cd = None
    try:
        # get pool current dedicated
        pool = batch_client.pool.get(config['pool_specification']['id'])
        pool_cd = pool.current_dedicated
        del pool
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
        batch_client, config, rls=rls, kind=kind, current_dedicated=pool_cd)
    data.wait_for_storage_threads(storage_threads)
