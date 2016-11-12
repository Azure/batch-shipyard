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
import collections
# non-stdlib imports
# local imports
from . import util

# global defines
_GPU_COMPUTE_INSTANCES = frozenset((
    'standard_nc6', 'standard_nc12', 'standard_nc24', 'standard_nc24r',
))
_GPU_VISUALIZATION_INSTANCES = frozenset((
    'standard_nv6', 'standard_nv12', 'standard_nv24',
))
_GPU_INSTANCES = _GPU_COMPUTE_INSTANCES.union(_GPU_VISUALIZATION_INSTANCES)
_RDMA_INSTANCES = frozenset((
    'standard_a8', 'standard_a9', 'standard_h16r', 'standard_h16mr',
    'standard_nc24r'
))
_VM_TCP_NO_TUNE = (
    'basic_a0', 'basic_a1', 'basic_a2', 'basic_a3', 'basic_a4', 'standard_a0',
    'standard_a1', 'standard_d1', 'standard_d2', 'standard_d1_v2',
    'standard_f1'
)
# named tuples
PoolSettings = collections.namedtuple(
    'PoolSettings', [
        'id', 'vm_size', 'vm_count', 'max_tasks_per_node',
        'inter_node_communication_enabled', 'publisher', 'offer', 'sku',
        'reboot_on_start_task_failed',
        'block_until_all_global_resources_loaded',
        'transfer_files_on_pool_creation',
        'input_data', 'gpu_driver', 'ssh', 'additional_node_prep_commands',
    ]
)
SSHSettings = collections.namedtuple(
    'SSHSettings', [
        'username', 'expiry_days', 'ssh_public_key',
        'generate_docker_tunnel_script', 'generated_file_export_path',
        'hpn_server_swap',
    ]
)
BatchCredentialsSettings = collections.namedtuple(
    'BatchCredentialsSettings', [
        'account', 'account_key', 'account_service_url'
    ]
)
StorageCredentialsSettings = collections.namedtuple(
    'StorageCredentialsSettings', [
        'account', 'account_key', 'endpoint'
    ]
)
BatchShipyardSettings = collections.namedtuple(
    'BatchShipyardSettings', [
        'storage_account_settings', 'storage_entity_prefix',
        'generated_sas_expiry_days', 'use_shipyard_docker_image',
        'store_timing_metrics',
    ]
)
DataReplicationSettings = collections.namedtuple(
    'DataReplicationSettings', [
        'peer_to_peer', 'non_peer_to_peer_concurrent_downloading',
    ]
)
PeerToPeerSettings = collections.namedtuple(
    'PeerToPeerSettings', [
        'enabled', 'compression', 'concurrent_source_downloads',
        'direct_download_seed_bias',
    ]
)


def can_tune_tcp(vm_size):
    # type: (str) -> bool
    """Check if TCP tuning on compute node should be performed
    :param str vm_size: vm size
    :rtype: bool
    :return: True if VM should be tuned
    """
    if vm_size.lower() in _VM_TCP_NO_TUNE:
        return False
    return True


def is_gpu_pool(vm_size):
    # type: (str) -> bool
    """Check if pool is GPU capable
    :param str vm_size: vm size
    :rtype: bool
    :return: if gpus are present
    """
    if vm_size.lower() in _GPU_INSTANCES:
        return True
    return False


def is_gpu_visualization_pool(vm_size):
    # type: (str) -> bool
    """Check if pool is for GPU visualization
    :param str vm_size: vm size
    :rtype: bool
    :return: if visualization gpus are present
    """
    if vm_size.lower() in _GPU_VISUALIZATION_INSTANCES:
        return True
    return False


def is_rdma_pool(vm_size):
    # type: (str) -> bool
    """Check if pool is IB/RDMA capable
    :param str vm_size: vm size
    :rtype: bool
    :return: if rdma is present
    """
    if vm_size.lower() in _RDMA_INSTANCES:
        return True
    return False


def temp_disk_mountpoint(config):
    # type: (dict) -> str
    """Get temporary disk mountpoint
    :param dict config: configuration object
    :rtype: str
    :return: temporary disk mount point
    """
    if pool_offer(config, lower=True) == 'ubuntuserver':
        return '/mnt'
    else:
        return '/mnt/resource'


# POOL CONFIG
def pool_specification(config):
    # type: (dict) -> dict
    """Get Pool specification config block
    :param dict config: configuration object
    :rtype: dict
    :return: pool specification
    """
    return config['pool_specification']


def pool_settings(config):
    # type: (dict) -> PoolSettings
    """Get Pool settings
    :param dict config: configuration object
    :rtype: PoolSettings
    :return: pool settings from specification
    """
    conf = pool_specification(config)
    try:
        max_tasks_per_node = conf['max_tasks_per_node']
    except KeyError:
        max_tasks_per_node = 1
    try:
        inter_node_communication_enabled = conf[
            'inter_node_communication_enabled']
    except KeyError:
        inter_node_communication_enabled = False
    try:
        reboot_on_start_task_failed = conf['reboot_on_start_task_failed']
    except KeyError:
        reboot_on_start_task_failed = False
    try:
        block_until_all_gr = conf['block_until_all_global_resources_loaded']
    except KeyError:
        block_until_all_gr = True
    try:
        transfer_files_on_pool_creation = conf[
            'transfer_files_on_pool_creation']
    except KeyError:
        transfer_files_on_pool_creation = False
    try:
        input_data = conf['input_data']
        if util.is_none_or_empty(input_data):
            raise KeyError()
    except KeyError:
        input_data = None
    try:
        ssh_username = conf['ssh']['username']
        if util.is_none_or_empty(ssh_username):
            raise KeyError()
    except KeyError:
        ssh_username = None
    try:
        ssh_expiry_days = conf['ssh']['expiry_days']
        if ssh_expiry_days is not None and ssh_expiry_days <= 0:
            raise KeyError()
    except KeyError:
        ssh_expiry_days = 7
    try:
        ssh_public_key = conf['ssh']['ssh_public_key']
        if util.is_none_or_empty(ssh_public_key):
            raise KeyError()
    except KeyError:
        ssh_public_key = None
    try:
        ssh_gen_docker_tunnel = conf['ssh']['generate_docker_tunnel_script']
    except KeyError:
        ssh_gen_docker_tunnel = False
    try:
        ssh_gen_file_path = conf['ssh']['generated_file_export_path']
        if util.is_none_or_empty(ssh_gen_file_path):
            raise KeyError()
    except KeyError:
        ssh_gen_file_path = None
    try:
        ssh_hpn = conf['ssh']['hpn_server_swap']
    except KeyError:
        ssh_hpn = False
    try:
        gpu_driver = conf['gpu']['nvidia_driver']['source']
        if util.is_none_or_empty(gpu_driver):
            raise KeyError()
    except KeyError:
        gpu_driver = None
    try:
        additional_node_prep_commands = conf['additional_node_prep_commands']
        if util.is_none_or_empty(additional_node_prep_commands):
            raise KeyError()
    except KeyError:
        additional_node_prep_commands = []
    return PoolSettings(
        id=conf['id'],
        vm_size=conf['vm_size'].lower(),  # normalize
        vm_count=conf['vm_count'],
        max_tasks_per_node=max_tasks_per_node,
        inter_node_communication_enabled=inter_node_communication_enabled,
        publisher=conf['publisher'],
        offer=conf['offer'],
        sku=conf['sku'],
        reboot_on_start_task_failed=reboot_on_start_task_failed,
        block_until_all_global_resources_loaded=block_until_all_gr,
        transfer_files_on_pool_creation=transfer_files_on_pool_creation,
        input_data=input_data,
        ssh=SSHSettings(
            username=ssh_username,
            expiry_days=ssh_expiry_days,
            ssh_public_key=ssh_public_key,
            generate_docker_tunnel_script=ssh_gen_docker_tunnel,
            generated_file_export_path=ssh_gen_file_path,
            hpn_server_swap=ssh_hpn,
        ),
        gpu_driver=gpu_driver,
        additional_node_prep_commands=additional_node_prep_commands,
    )


def remove_ssh_settings(config):
    # type: (dict) -> None
    """Remove ssh settings from pool specification
    :param dict config: configuration object
    """
    config['pool_specification'].pop('ssh', None)


def set_block_until_all_global_resources_loaded(config, flag):
    # type: (dict, bool) -> None
    """Set block until all global resources setting
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    config['pool_specification'][
        'block_until_all_global_resources_loaded'] = flag


def set_inter_node_communication_enabled(config, flag):
    # type: (dict, bool) -> None
    """Set inter node comm setting
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    config['pool_specification']['inter_node_communication_enabled'] = flag


def set_ssh_public_key(config, pubkey):
    # type: (dict, str) -> None
    """Set SSH public key setting
    :param dict config: configuration object
    :param str pubkey: public key to set
    """
    if 'ssh' not in config['pool_specification']:
        config['pool_specification']['ssh'] = {}
    config['pool_specification']['ssh']['ssh_public_key'] = pubkey


def set_hpn_server_swap(config, flag):
    # type: (dict, bool) -> None
    """Set SSH HPN server swap setting
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    if 'ssh' not in config['pool_specification']:
        config['pool_specification']['ssh'] = {}
    config['pool_specification']['ssh']['hpn_server_swap'] = flag


def pool_id(config, lower=False):
    # type: (dict, bool) -> str
    """Get Pool id
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: str
    :return: pool id
    """
    id = config['pool_specification']['id']
    return id.lower() if lower else id


def pool_vm_count(config):
    # type: (dict) -> int
    """Get Pool vm count
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: int
    :return: pool vm count
    """
    return config['pool_specification']['vm_count']


def pool_publisher(config, lower=False):
    # type: (dict, bool) -> str
    """Get Pool publisher
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: str
    :return: pool publisher
    """
    pub = config['pool_specification']['publisher']
    return pub.lower() if lower else pub


def pool_offer(config, lower=False):
    # type: (dict, bool) -> str
    """Get Pool offer
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: str
    :return: pool offer
    """
    offer = config['pool_specification']['offer']
    return offer.lower() if lower else offer


def pool_sku(config, lower=False):
    # type: (dict, bool) -> str
    """Get Pool sku
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: str
    :return: pool sku
    """
    sku = config['pool_specification']['sku']
    return sku.lower() if lower else sku


# CREDENTIALS SETTINGS
def credentials_batch(config):
    # type: (dict) -> BatchCredentialsSettings
    """Get Batch credentials
    :param dict config: configuration object
    :rtype: BatchCredentialsSettings
    :return: batch creds
    """
    conf = config['credentials']['batch']
    return BatchCredentialsSettings(
        account=conf['account'],
        account_key=conf['account_key'],
        account_service_url=conf['account_service_url']
    )


def credentials_storage(config, ssel):
    # type: (dict, str) -> StorageCredentialsSettings
    """Get specific storage credentials
    :param dict config: configuration object
    :param str ssel: storage selector link
    :rtype: StorageCredentialsSettings
    :return: storage creds
    """
    conf = config['credentials']['storage'][ssel]
    try:
        ep = conf['endpoint']
        if util.is_none_or_empty(ep):
            raise KeyError()
    except KeyError:
        ep = 'core.windows.net'
    return StorageCredentialsSettings(
        account=conf['account'],
        account_key=conf['account_key'],
        endpoint=ep,
    )


def docker_registry_hub_login(config):
    # type: (dict) -> tuple
    """Get docker registry hub login settings
    :param dict config: configuration object
    :rtype: tuple
    :return: (user, pw)
    """
    try:
        user = config['credentials']['docker_registry']['hub']['username']
        pw = config['credentials']['docker_registry']['hub']['password']
        if util.is_none_or_empty(user) or util.is_none_or_empty(pw):
            raise KeyError()
    except KeyError:
        user = None
        pw = None
    return user, pw


# GLOBAL SETTINGS
def batch_shipyard_settings(config):
    # type: (dict) -> BatchShipyardSettings
    """Get batch shipyard settings
    :param dict config: configuration object
    :rtype: BatchShipyardSettings
    :return: batch shipyard settings
    """
    conf = config['batch_shipyard']
    stlink = conf['storage_account_settings']
    if util.is_none_or_empty(stlink):
        raise ValueError('batch_shipyard:storage_account_settings is invalid')
    try:
        sep = conf['storage_entity_prefix']
        if sep is None:
            raise KeyError()
    except KeyError:
        sep = 'shipyard'
    try:
        sasexpiry = conf['generated_sas_expiry_days']
    except KeyError:
        sasexpiry = None
    try:
        use_shipyard_image = conf['use_shipyard_docker_image']
    except KeyError:
        use_shipyard_image = True
    try:
        store_timing = conf['store_timing_metrics']
    except KeyError:
        store_timing = False
    return BatchShipyardSettings(
        storage_account_settings=stlink,
        storage_entity_prefix=sep,
        generated_sas_expiry_days=sasexpiry,
        use_shipyard_docker_image=use_shipyard_image,
        store_timing_metrics=store_timing,
    )


def set_use_shipyard_docker_image(config, flag):
    # type: (dict, bool) -> None
    """Set shipyard docker image use
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    config['batch_shipyard']['use_shipyard_docker_image'] = flag


def batch_shipyard_encryption_enabled(config):
    # type: (dict) -> bool
    """Get credential encryption enabled setting
    :param dict config: configuration object
    :rtype: bool
    :return: if credential encryption is enabled
    """
    try:
        encrypt = config['batch_shipyard']['encryption']['enabled']
    except KeyError:
        encrypt = False
    return encrypt


def set_batch_shipyard_encryption_enabled(config, flag):
    # type: (dict, bool) -> None
    """Set credential encryption enabled setting
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    if 'encryption' not in config['batch_shipyard']:
        config['batch_shipyard']['encryption'] = {}
    config['batch_shipyard']['encryption']['enabled'] = flag


def batch_shipyard_encryption_pfx_filename(config):
    # type: (dict) -> str
    """Get filename of pfx cert
    :param dict config: configuration object
    :rtype: str
    :return: pfx filename
    """
    try:
        pfxfile = config['batch_shipyard']['encryption']['pfx']['filename']
    except KeyError:
        pfxfile = None
    return pfxfile


def batch_shipyard_encryption_pfx_passphrase(config):
    # type: (dict) -> str
    """Get passphrase of pfx cert
    :param dict config: configuration object
    :rtype: str
    :return: pfx passphrase
    """
    try:
        passphrase = config['batch_shipyard']['encryption'][
            'pfx']['passphrase']
    except KeyError:
        passphrase = None
    return passphrase


def batch_shipyard_encryption_pfx_sha1_thumbprint(config):
    # type: (dict) -> str
    """Get sha1 tp of pfx cert
    :param dict config: configuration object
    :rtype: str
    :return: pfx sha1 thumbprint
    """
    try:
        tp = config['batch_shipyard']['encryption']['pfx']['sha1_thumbprint']
    except KeyError:
        tp = None
    return tp


def set_batch_shipyard_encryption_pfx_sha1_thumbprint(config, tp):
    # type: (dict, str) -> None
    """Set sha1 tp of pfx cert
    :param dict config: configuration object
    """
    config['batch_shipyard']['encryption']['pfx']['sha1_thumbprint'] = tp


def batch_shipyard_encryption_public_key_pem(config):
    # type: (dict) -> str
    """Get filename of pem public key
    :param dict config: configuration object
    :rtype: str
    :return: pem filename
    """
    try:
        pem = config['batch_shipyard']['encryption']['public_key_pem']
    except KeyError:
        pem = None
    return pem


def docker_registry_private_allow_public_pull(config):
    # type: (dict) -> bool
    """Get public docker hub pull on missing setting
    :param dict config: configuration object
    :rtype: bool
    :return: if public pull is allowed on missing
    """
    try:
        pregpubpull = config['docker_registry']['private'][
            'allow_public_docker_hub_pull_on_missing']
    except KeyError:
        pregpubpull = False
    return pregpubpull


def docker_registry_azure_storage(config):
    # type: (dict) -> tuple
    """Get docker private registry backed to azure storage settings
    :param dict config: configuration object
    :rtype: tuple
    :return: (storage account name, container)
    """
    try:
        sa = config['docker_registry']['private']['azure_storage'][
            'storage_account_settings']
        if util.is_none_or_empty(sa):
            raise KeyError()
        cont = config['docker_registry']['private']['azure_storage'][
            'container']
        if util.is_none_or_empty(cont):
            raise KeyError()
    except KeyError:
        sa = None
        cont = None
    return sa, cont


def data_replication_settings(config):
    # type: (dict) -> DataReplicationSettings
    """Get data replication settings
    :param dict config: configuration object
    :rtype: DataReplicationSettings
    :return: data replication settings
    """
    try:
        conf = config['data_replication']
    except KeyError:
        conf = {}
    try:
        nonp2pcd = conf['non_peer_to_peer_concurrent_downloading']
    except KeyError:
        nonp2pcd = True
    try:
        conf = config['data_replication']['peer_to_peer']
    except KeyError:
        conf = {}
    try:
        p2p_enabled = conf['enabled']
    except KeyError:
        p2p_enabled = False
    try:
        p2p_compression = conf['compression']
    except KeyError:
        p2p_compression = True
    try:
        p2p_concurrent_source_downloads = conf['concurrent_source_downloads']
        if (p2p_concurrent_source_downloads is None or
                p2p_concurrent_source_downloads < 1):
            raise KeyError()
    except KeyError:
        p2p_concurrent_source_downloads = pool_vm_count(config) // 6
        if p2p_concurrent_source_downloads < 1:
            p2p_concurrent_source_downloads = 1
    try:
        p2p_direct_download_seed_bias = conf['direct_download_seed_bias']
        if (p2p_direct_download_seed_bias is None or
                p2p_direct_download_seed_bias < 1):
            raise KeyError()
    except KeyError:
        p2p_direct_download_seed_bias = pool_vm_count(config) // 10
        if p2p_direct_download_seed_bias < 1:
            p2p_direct_download_seed_bias = 1
    return DataReplicationSettings(
        peer_to_peer=PeerToPeerSettings(
            enabled=p2p_enabled,
            compression=p2p_compression,
            concurrent_source_downloads=p2p_concurrent_source_downloads,
            direct_download_seed_bias=p2p_direct_download_seed_bias
        ),
        non_peer_to_peer_concurrent_downloading=nonp2pcd
    )


def set_peer_to_peer_enabled(config, flag):
    # type: (dict, bool) -> None
    """Set peer to peer enabled setting
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    if 'data_replication' not in config:
        config['data_replication'] = {}
    if 'peer_to_peer' not in config['data_replication']:
        config['data_replication']['peer_to_peer'] = {}
    config['data_replication']['peer_to_peer']['enabled'] = flag


def global_resources_docker_images(config):
    # type: (dict) -> list
    """Get list of docker images
    :param dict config: configuration object
    :rtype: list
    :return: docker images
    """
    try:
        images = config['global_resources']['docker_images']
        if util.is_none_or_empty(images):
            raise KeyError()
    except KeyError:
        images = []
    return images


def global_resources_files(config):
    # type: (dict) -> list
    """Get list of global files ingress
    :param dict config: configuration object
    :rtype: list
    :return: global files ingress list
    """
    try:
        files = config['global_resources']['files']
        if util.is_none_or_empty(files):
            raise KeyError()
    except KeyError:
        files = []
    return files


def is_direct_transfer(filespair):
    # type: (dict) -> bool
    """Determine if src/dst pair for files ingress is a direct compute node
    transfer
    :param dict filespair: src/dst pair
    :rtype: bool
    :return: if ingress is direct
    """
    return 'storage_account_settings' not in filespair['destination']


def global_resources_shared_data_volumes(config):
    # type: (dict) -> dict
    """Get shared data volumes dictionary
    :param dict config: configuration object
    :rtype: dict
    :return: shared data volumes
    """
    try:
        sdv = config['global_resources']['docker_volumes'][
            'shared_data_volumes']
        if util.is_none_or_empty(sdv):
            raise KeyError()
    except KeyError:
        sdv = {}
    return sdv


def shared_data_volume_driver(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get shared data volume driver
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: volume driver
    """
    return sdv[sdvkey]['volume_driver']


def shared_data_volume_container_path(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get shared data volume container path
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: container path
    """
    return sdv[sdvkey]['container_path']


def azure_file_storage_account_settings(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get azure file storage account link
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: storage account link
    """
    return sdv[sdvkey]['storage_account_settings']


def azure_file_share_name(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get azure file share name
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: azure file share name
    """
    return sdv[sdvkey]['azure_file_share_name']


def azure_file_mount_options(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get azure file mount options
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: azure file mount options
    """
    try:
        mo = sdv[sdvkey]['mount_options']
    except KeyError:
        mo = None
    return mo


def gluster_volume_type(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get gluster volume type
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: gluster volume type
    """
    try:
        vt = sdv[sdvkey]['volume_type']
        if util.is_none_or_empty(vt):
            raise KeyError()
    except KeyError:
        vt = 'replica'
    return vt


def gluster_volume_options(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get gluster volume options
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: gluster volume options
    """
    try:
        vo = sdv[sdvkey]['volume_options']
        if util.is_none_or_empty(vo):
            raise KeyError()
    except KeyError:
        vo = None
    return vo


def is_shared_data_volume_azure_file(sdv, sdvkey):
    # type: (dict, str) -> bool
    """Determine if shared data volume is an azure file share
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: bool
    :return: if shared data volume is azure file
    """
    return shared_data_volume_driver(sdv, sdvkey).lower() == 'azurefile'


def is_shared_data_volume_gluster(sdv, sdvkey):
    # type: (dict, str) -> bool
    """Determine if shared data volume is a glusterfs share
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: bool
    :return: if shared data volume is glusterfs
    """
    return shared_data_volume_driver(sdv, sdvkey).lower() == 'glusterfs'
