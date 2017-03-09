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
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
# non-stdlib imports
# local imports
from . import util

# global defines
_GLUSTER_VOLUME = '.gluster/gv0'
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
    'standard_a1', 'standard_a2', 'standard_a3', 'standard_a5', 'standard_a6',
    'standard_a1_v2', 'standard_a2_v2', 'standard_a3_v2', 'standard_a4_v2',
    'standard_a2m_v2', 'standard_a4m_v2', 'standard_d1', 'standard_d2',
    'standard_d1_v2', 'standard_f1'
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
        'virtual_network',
    ]
)
SSHSettings = collections.namedtuple(
    'SSHSettings', [
        'username', 'expiry_days', 'ssh_public_key',
        'generate_docker_tunnel_script', 'generated_file_export_path',
        'hpn_server_swap',
    ]
)
AADSettings = collections.namedtuple(
    'AADSettings', [
        'directory_id', 'application_id', 'auth_key', 'rsa_private_key_pem',
        'x509_cert_sha1_thumbprint', 'user', 'password', 'endpoint',
        'token_cache_file',
    ]
)
KeyVaultCredentialsSettings = collections.namedtuple(
    'KeyVaultCredentialsSettings', [
        'aad', 'keyvault_uri', 'keyvault_credentials_secret_id',
    ]
)
ManagementCredentialsSettings = collections.namedtuple(
    'ManagementCredentialsSettings', [
        'aad', 'subscription_id',
    ]
)
BatchCredentialsSettings = collections.namedtuple(
    'BatchCredentialsSettings', [
        'aad', 'account', 'account_key', 'account_service_url',
        'user_subscription', 'resource_group', 'subscription_id', 'location',
    ]
)
StorageCredentialsSettings = collections.namedtuple(
    'StorageCredentialsSettings', [
        'account', 'account_key', 'endpoint',
    ]
)
BatchShipyardSettings = collections.namedtuple(
    'BatchShipyardSettings', [
        'storage_account_settings', 'storage_entity_prefix',
        'generated_sas_expiry_days', 'use_shipyard_docker_image',
        'store_timing_metrics',
    ]
)
DockerRegistrySettings = collections.namedtuple(
    'DockerRegistrySettings', [
        'allow_public_docker_hub_pull_on_missing',
        'storage_account', 'container', 'server', 'port',
        'user', 'password',
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
SourceSettings = collections.namedtuple(
    'SourceSettings', [
        'path', 'include', 'exclude'
    ]
)
DestinationSettings = collections.namedtuple(
    'DestinationSettings', [
        'storage_account_settings', 'shared_data_volume',
        'relative_destination_path', 'data_transfer'
    ]
)
DataTransferSettings = collections.namedtuple(
    'DataTransferSettings', [
        'method', 'ssh_private_key', 'scp_ssh_extra_options',
        'rsync_extra_options', 'split_files_megabytes',
        'max_parallel_transfers_per_node',
        'container', 'file_share', 'blobxfer_extra_options',
    ]
)
TaskSettings = collections.namedtuple(
    'TaskSettings', [
        'id', 'image', 'name', 'docker_run_options', 'environment_variables',
        'environment_variables_keyvault_secret_id', 'envfile',
        'resource_files', 'command', 'infiniband', 'gpu', 'depends_on',
        'depends_on_range', 'max_task_retries', 'retention_time',
        'docker_run_cmd', 'docker_exec_cmd', 'multi_instance',
    ]
)
MultiInstanceSettings = collections.namedtuple(
    'MultiInstanceSettings', [
        'num_instances', 'coordination_command', 'resource_files',
    ]
)
ResourceFileSettings = collections.namedtuple(
    'ResourceFileSettings', [
        'file_path', 'blob_source', 'file_mode',
    ]
)
ManagedDisksSettings = collections.namedtuple(
    'ManagedDisksSettings', [
        'premium', 'disk_size_gb', 'disk_ids',
    ]
)
VirtualNetworkSettings = collections.namedtuple(
    'VirtualNetworkSettings', [
        'name', 'address_space', 'subnet_name', 'subnet_address_prefix',
        'existing_ok', 'create_nonexistant',
    ]
)
FileServerSettings = collections.namedtuple(
    'FileServerSettings', [
        'type', 'mountpoint',
    ]
)
InboundNetworkSecurityRule = collections.namedtuple(
    'InboundNetworkSecurityRule', [
        'destination_port_range', 'source_address_prefix', 'protocol',
    ]
)
NetworkSecuritySettings = collections.namedtuple(
    'NetworkSecuritySettings', [
        'inbound',
    ]
)
MappedVmDiskSettings = collections.namedtuple(
    'MappedVmDiskSettings', [
        'disk_array', 'filesystem', 'raid_level'
    ]
)
StorageClusterSettings = collections.namedtuple(
    'StorageClusterSettings', [
        'id', 'virtual_network', 'network_security', 'file_server',
        'vm_count', 'vm_size', 'static_public_ip', 'hostname_prefix', 'ssh',
        'vm_disk_map'
    ]
)
RemoteFsSettings = collections.namedtuple(
    'RemoteFsSettings', [
        'resource_group', 'location', 'managed_disks', 'storage_cluster',
    ]
)


def _kv_read_checked(conf, key, default=None):
    # type: (dict, str, obj) -> obj
    """Read a key as some value with a check against None and length
    :param dict conf: configuration dict
    :param str key: conf key
    :param obj default: default to assign
    :rtype: obj or None
    :return: value of key
    """
    try:
        ret = conf[key]
        if util.is_none_or_empty(ret):
            raise KeyError()
    except KeyError:
        ret = default
    return ret


def _kv_read(conf, key, default=None):
    # type: (dict, str, obj) ->w obj
    """Read a key as some value
    :param dict conf: configuration dict
    :param str key: conf key
    :param obj default: default to assign
    :rtype: obj or None
    :return: value of key
    """
    try:
        ret = conf[key]
    except KeyError:
        ret = default
    return ret


def get_gluster_volume():
    # type: (None) -> str
    """Get gluster volume mount suffix
    :rtype: str
    :return: gluster volume mount
    """
    return _GLUSTER_VOLUME


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


def is_gpu_compute_pool(vm_size):
    # type: (str) -> bool
    """Check if pool is for GPU compute
    :param str vm_size: vm size
    :rtype: bool
    :return: if compute gpus are present
    """
    if vm_size.lower() in _GPU_COMPUTE_INSTANCES:
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


def temp_disk_mountpoint(config, offer=None):
    # type: (dict) -> str
    """Get temporary disk mountpoint
    :param dict config: configuration object
    :param str offer: offer override
    :rtype: str
    :return: temporary disk mount point
    """
    if offer is None:
        offer = pool_offer(config, lower=True)
    else:
        offer = offer.lower()
    if offer == 'ubuntuserver':
        return '/mnt'
    else:
        return '/mnt/resource'


def verbose(config):
    # type: (dict) -> bool
    """Get verbose setting
    :param dict config: configuration object
    :rtype: bool
    :return: verbose setting
    """
    return config['_verbose']


def set_auto_confirm(config, flag):
    # type: (dict, bool) -> None
    """Set autoconfirm setting
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    config['_auto_confirm'] = flag


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
        ssh_expiry_days = 30
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
        ssh_gen_file_path = '.'
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
        virtual_network=virtual_network_settings(
            conf,
            default_existing_ok=True,
            default_create_nonexistant=False,
        ),
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
def raw_credentials(config, omit_keyvault):
    # type: (dict, bool) -> dict
    """Get raw credentials dictionary
    :param dict config: configuration object
    :param bool omit_keyvault: omit keyvault settings if present
    :rtype: dict
    :return: credentials dict
    """
    conf = config['credentials']
    if omit_keyvault:
        conf.pop('keyvault', None)
    return conf


def _aad_credentials(
        conf, default_endpoint=None, default_token_cache_file=None):
    # type: (dict, str) -> AADSettings
    """Retrieve AAD Settings
    :param dict config: configuration object
    :param str default_endpoint: default endpoint
    :param str default_token_cache_file: default token cache file
    :rtype: AADSettings
    :return: AAD settings
    """
    if 'aad' in conf:
        aad_directory_id = _kv_read_checked(conf['aad'], 'directory_id')
        aad_application_id = _kv_read_checked(conf['aad'], 'application_id')
        aad_auth_key = _kv_read_checked(conf['aad'], 'auth_key')
        aad_user = _kv_read_checked(conf['aad'], 'user')
        aad_password = _kv_read_checked(conf['aad'], 'password')
        aad_cert_private_key = _kv_read_checked(
            conf['aad'], 'rsa_private_key_pem')
        aad_cert_thumbprint = _kv_read_checked(
            conf['aad'], 'x509_cert_sha1_thumbprint')
        aad_endpoint = _kv_read_checked(
            conf['aad'], 'endpoint', default_endpoint)
        if 'token_cache' not in conf['aad']:
            conf['aad']['token_cache'] = {}
        token_cache_enabled = _kv_read(
            conf['aad']['token_cache'], 'enabled', True)
        if token_cache_enabled:
            token_cache_file = _kv_read_checked(
                conf['aad']['token_cache'], 'filename',
                default_token_cache_file)
        else:
            token_cache_file = None
        return AADSettings(
            directory_id=aad_directory_id,
            application_id=aad_application_id,
            auth_key=aad_auth_key,
            user=aad_user,
            password=aad_password,
            rsa_private_key_pem=aad_cert_private_key,
            x509_cert_sha1_thumbprint=aad_cert_thumbprint,
            endpoint=aad_endpoint,
            token_cache_file=token_cache_file,
        )
    else:
        return AADSettings(
            directory_id=None,
            application_id=None,
            auth_key=None,
            user=None,
            password=None,
            rsa_private_key_pem=None,
            x509_cert_sha1_thumbprint=None,
            endpoint=default_endpoint,
            token_cache_file=None,
        )


def credentials_keyvault(config):
    # type: (dict) -> KeyVaultCredentialsSettings
    """Get KeyVault settings
    :param dict config: configuration object
    :rtype: KeyVaultCredentialsSettings
    :return: Key Vault settings
    """
    try:
        conf = config['credentials']['keyvault']
    except (KeyError, TypeError):
        conf = {}
    keyvault_uri = _kv_read_checked(conf, 'uri')
    keyvault_credentials_secret_id = _kv_read_checked(
        conf, 'credentials_secret_id')
    return KeyVaultCredentialsSettings(
        aad=_aad_credentials(
            conf,
            default_endpoint='https://vault.azure.net',
            default_token_cache_file=(
                '.batch_shipyard_aad_keyvault_token.json'
            ),
        ),
        keyvault_uri=keyvault_uri,
        keyvault_credentials_secret_id=keyvault_credentials_secret_id,
    )


def credentials_management(config):
    # type: (dict) -> ManagementCredentialsSettings
    """Get Management settings
    :param dict config: configuration object
    :rtype: ManagementCredentialsSettings
    :return: Management settings
    """
    try:
        conf = config['credentials']['management']
    except (KeyError, TypeError):
        conf = {}
    subscription_id = _kv_read_checked(conf, 'subscription_id')
    return ManagementCredentialsSettings(
        aad=_aad_credentials(
            conf,
            default_endpoint='https://management.core.windows.net/',
            default_token_cache_file=(
                '.batch_shipyard_aad_management_token.json'
            ),
        ),
        subscription_id=subscription_id,
    )


def credentials_batch(config):
    # type: (dict) -> BatchCredentialsSettings
    """Get Batch credentials
    :param dict config: configuration object
    :rtype: BatchCredentialsSettings
    :return: batch creds
    """
    conf = config['credentials']['batch']
    account_key = _kv_read_checked(conf, 'account_key')
    account_service_url = conf['account_service_url']
    user_subscription = _kv_read(conf, 'user_subscription', False)
    resource_group = _kv_read_checked(conf, 'resource_group')
    # get subscription id from management section
    try:
        subscription_id = _kv_read_checked(
            config['credentials']['management'], 'subscription_id')
    except (KeyError, TypeError):
        subscription_id = None
    # parse location from url
    location = account_service_url.split('.')[1]
    return BatchCredentialsSettings(
        aad=_aad_credentials(
            conf,
            default_endpoint='https://batch.core.windows.net/',
            default_token_cache_file=(
                '.batch_shipyard_aad_batch_token.json'
            ),
        ),
        account=conf['account'],
        account_key=account_key,
        account_service_url=conf['account_service_url'],
        user_subscription=user_subscription,
        resource_group=resource_group,
        location=location,
        subscription_id=subscription_id,
    )


def credentials_batch_account_key_secret_id(config):
    # type: (dict) -> str
    """Get Batch account key KeyVault Secret Id
    :param dict config: configuration object
    :rtype: str
    :return: keyvault secret id
    """
    try:
        secid = config[
            'credentials']['batch']['account_key_keyvault_secret_id']
        if util.is_none_or_empty(secid):
            raise KeyError()
    except KeyError:
        return None
    return secid


def set_credentials_batch_account_key(config, bakey):
    # type: (dict, str) -> None
    """Set Batch account key
    :param dict config: configuration object
    :param str bakey: batch account key
    """
    config['credentials']['batch']['account_key'] = bakey


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


def iterate_storage_credentials(config):
    # type: (dict) -> str
    """Iterate storage credential storage select links
    :param dict config: configuration object
    :rtype: str
    :return: storage selector link
    """
    for conf in config['credentials']['storage']:
        yield conf


def credentials_storage_account_key_secret_id(config, ssel):
    # type: (dict, str) -> str
    """Get Storage account key KeyVault Secret Id
    :param dict config: configuration object
    :param str ssel: storage selector link
    :rtype: str
    :return: keyvault secret id
    """
    try:
        secid = config[
            'credentials']['storage'][ssel]['account_key_keyvault_secret_id']
        if util.is_none_or_empty(secid):
            raise KeyError()
    except KeyError:
        return None
    return secid


def set_credentials_storage_account_key(config, ssel, sakey):
    # type: (dict, str, str) -> None
    """Set Storage account key
    :param dict config: configuration object
    :param str ssel: storage selector link
    :param str sakey: storage account key
    """
    config['credentials']['storage'][ssel]['account_key'] = sakey


def docker_registry_login(config, server):
    # type: (dict, str) -> tuple
    """Get docker registry login settings
    :param dict config: configuration object
    :param str server: credentials for login server to retrieve
    :rtype: tuple
    :return: (user, pw)
    """
    try:
        user = config['credentials']['docker_registry'][server]['username']
        pw = config['credentials']['docker_registry'][server]['password']
        if util.is_none_or_empty(user) or util.is_none_or_empty(pw):
            raise KeyError()
    except KeyError:
        user = None
        pw = None
    return user, pw


def iterate_docker_registry_servers(config):
    # type: (dict) -> str
    """Iterate docker registry servers
    :param dict config: configuration object
    :rtype: str
    :return: docker registry name
    """
    try:
        for conf in config['credentials']['docker_registry']:
            yield conf
    except KeyError:
        pass


def credentials_docker_registry_password_secret_id(config, dr):
    # type: (dict, str) -> str
    """Get Docker registry password KeyVault Secret Id
    :param dict config: configuration object
    :param str dr: docker registry link
    :rtype: str
    :return: keyvault secret id
    """
    try:
        secid = config['credentials'][
            'docker_registry'][dr]['password_keyvault_secret_id']
        if util.is_none_or_empty(secid):
            raise KeyError()
    except KeyError:
        return None
    return secid


def set_credentials_docker_registry_password(config, dr, password):
    # type: (dict, str, str) -> None
    """Set Docker registry password
    :param dict config: configuration object
    :param str dr: docker registry link
    :param str password: password
    """
    config['credentials']['docker_registry'][dr]['password'] = password


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


def docker_registry_private_settings(config):
    # type: (dict) -> DockerRegistrySettings
    """Get docker private registry backed to azure storage settings
    :param dict config: configuration object
    :rtype: DockerRegistrySettings
    :return: docker registry settings
    """
    try:
        pregpubpull = config['docker_registry']['private'][
            'allow_public_docker_hub_pull_on_missing']
    except KeyError:
        pregpubpull = False
    try:
        server = config['docker_registry']['private']['server']
        if util.is_none_or_empty(server):
            raise KeyError()
        server = server.split(':')
        if len(server) == 1:
            port = 80
        elif len(server) == 2:
            port = int(server[1])
        else:
            raise ValueError('invalid docker registry server specification')
        server = server[0]
        # get login
        user, pw = docker_registry_login(config, server)
        if util.is_none_or_empty(user) or util.is_none_or_empty(pw):
            raise ValueError(
                'Docker registry login settings not specified for: {}'.format(
                    server))
    except KeyError:
        server = None
        port = None
        user = None
        pw = None
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
    if server is not None and sa is not None:
        raise ValueError(
            'cannot specify both a private registry server host and a '
            'private registry backed by Azure Storage')
    return DockerRegistrySettings(
        allow_public_docker_hub_pull_on_missing=pregpubpull,
        storage_account=sa,
        container=cont,
        server=server,
        port=port,
        user=user,
        password=pw,
    )


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


def files_source_settings(conf):
    # type: (dict) -> SourceSettings
    """Get global resources files source
    :param dict conf: configuration block
    :rtype: SourceSettings
    :return: source settings
    """
    path = conf['source']['path']
    if util.is_none_or_empty(path):
        raise ValueError('global resource files path is invalid')
    try:
        include = conf['source']['include']
        if util.is_none_or_empty(include):
            raise KeyError()
    except KeyError:
        include = None
    try:
        exclude = conf['source']['exclude']
        if util.is_none_or_empty(exclude):
            raise KeyError()
    except KeyError:
        exclude = None
    return SourceSettings(path=path, include=include, exclude=exclude)


def files_destination_settings(fdict):
    # type: (dict) -> DestinationSettings
    """Get global resources files destination
    :param dict fdict: configuration block
    :rtype: DestinationSettings
    :return: destination settings
    """
    conf = fdict['destination']
    try:
        shared = conf['shared_data_volume']
    except KeyError:
        shared = None
    try:
        storage = conf['storage_account_settings']
    except KeyError:
        storage = None
    try:
        rdp = conf['relative_destination_path']
        if rdp is not None:
            rdp = rdp.lstrip('/').rstrip('/')
            if len(rdp) == 0:
                rdp = None
    except KeyError:
        rdp = None
    try:
        method = conf['data_transfer']['method'].lower()
    except KeyError:
        if storage is None:
            raise RuntimeError(
                'no transfer method specified for data transfer of '
                'source: {} to {} rdp={}'.format(
                    files_source_settings(fdict).path, shared, rdp))
        else:
            method = None
    try:
        ssh_eo = conf['data_transfer']['scp_ssh_extra_options']
        if ssh_eo is None:
            raise KeyError()
    except KeyError:
        ssh_eo = ''
    try:
        rsync_eo = conf['data_transfer']['rsync_extra_options']
        if rsync_eo is None:
            raise KeyError()
    except KeyError:
        rsync_eo = ''
    try:
        mpt = conf['data_transfer']['max_parallel_transfers_per_node']
        if mpt is not None and mpt <= 0:
            raise KeyError()
    except KeyError:
        mpt = None
    # ensure valid mpt number
    if mpt is None:
        mpt = 1
    try:
        split = conf['data_transfer']['split_files_megabytes']
        if split is not None and split <= 0:
            raise KeyError()
        # convert to bytes
        if split is not None:
            split <<= 20
    except KeyError:
        split = None
    try:
        ssh_private_key = pathlib.Path(
            conf['data_transfer']['ssh_private_key'])
    except KeyError:
        ssh_private_key = None
    try:
        container = conf['data_transfer']['container']
        if util.is_none_or_empty(container):
            raise KeyError()
    except KeyError:
        container = None
    try:
        fshare = conf['data_transfer']['file_share']
        if util.is_none_or_empty(fshare):
            raise KeyError()
    except KeyError:
        fshare = None
    try:
        bx_eo = conf['data_transfer']['blobxfer_extra_options']
        if bx_eo is None:
            bx_eo = ''
    except KeyError:
        bx_eo = ''
    return DestinationSettings(
        storage_account_settings=storage,
        shared_data_volume=shared,
        relative_destination_path=rdp,
        data_transfer=DataTransferSettings(
            container=container,
            file_share=fshare,
            blobxfer_extra_options=bx_eo,
            method=method,
            ssh_private_key=ssh_private_key,
            scp_ssh_extra_options=ssh_eo,
            rsync_extra_options=rsync_eo,
            split_files_megabytes=split,
            max_parallel_transfers_per_node=mpt,
        )
    )


def global_resources_data_volumes(config):
    # type: (dict) -> dict
    """Get data volumes dictionary
    :param dict config: configuration object
    :rtype: dict
    :return: data volumes
    """
    try:
        dv = config['global_resources']['docker_volumes']['data_volumes']
        if util.is_none_or_empty(dv):
            raise KeyError()
    except KeyError:
        dv = {}
    return dv


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


def shared_data_volume_mount_options(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get shared data volume mount options
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: shared data volume mount options
    """
    try:
        mo = sdv[sdvkey]['mount_options']
    except KeyError:
        mo = None
    return mo


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


def is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
    # type: (dict, str) -> bool
    """Determine if shared data volume is a glusterfs share on compute
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: bool
    :return: if shared data volume is glusterfs on compute
    """
    return shared_data_volume_driver(
        sdv, sdvkey).lower() == 'glusterfs_on_compute'


def is_shared_data_volume_storage_cluster(sdv, sdvkey):
    # type: (dict, str) -> bool
    """Determine if shared data volume is a storage cluster
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: bool
    :return: if shared data volume is storage_cluster
    """
    return shared_data_volume_driver(sdv, sdvkey).lower() == 'storage_cluster'


# INPUT AND OUTPUT DATA SETTINGS
def input_data(conf):
    # type: (dict) -> str
    """Retrieve input data config block
    :param dict conf: configuration object
    :rtype: str
    :return: input data config block
    """
    try:
        id = conf['input_data']
        if util.is_none_or_empty(id):
            raise KeyError()
    except KeyError:
        id = None
    return id


def output_data(conf):
    # type: (dict) -> str
    """Retrieve output data config block
    :param dict conf: configuration object
    :rtype: str
    :return: output data config block
    """
    try:
        od = conf['output_data']
        if util.is_none_or_empty(od):
            raise KeyError()
    except KeyError:
        od = None
    return od


def data_storage_account_settings(conf):
    # type: (dict) -> str
    """Retrieve input data storage account settings link
    :param dict conf: configuration object
    :rtype: str
    :return: storage account link
    """
    return conf['storage_account_settings']


def data_container(conf):
    # type: (dict) -> str
    """Retrieve input data blob container name
    :param dict conf: configuration object
    :rtype: str
    :return: container name
    """
    try:
        container = conf['container']
        if util.is_none_or_empty(container):
            raise KeyError()
    except KeyError:
        container = None
    return container


def data_file_share(conf):
    # type: (dict) -> str
    """Retrieve input data file share name
    :param dict conf: configuration object
    :rtype: str
    :return: file share name
    """
    try:
        fshare = conf['file_share']
        if util.is_none_or_empty(fshare):
            raise KeyError()
    except KeyError:
        fshare = None
    return fshare


def data_blobxfer_extra_options(conf):
    # type: (dict) -> str
    """Retrieve input data blobxfer extra options
    :param dict conf: configuration object
    :rtype: str
    :return: blobxfer extra options
    """
    try:
        eo = conf['blobxfer_extra_options']
        if eo is None:
            eo = ''
    except KeyError:
        eo = ''
    return eo


def data_include(conf, one_allowable):
    # type: (dict, bool) -> str
    """Retrieve input data include fileters
    :param dict conf: configuration object
    :param bool one_allowable: if only one include filter is allowed
    :rtype: str
    :return: include filters
    """
    if one_allowable:
        try:
            include = conf['include']
            if include is not None:
                if len(include) == 0:
                    include = ''
                elif len(include) == 1:
                    include = include[0]
                else:
                    raise ValueError(
                        'include for input_data from {} cannot exceed '
                        '1 filter'.format(data_storage_account_settings(conf)))
            else:
                include = ''
        except KeyError:
            include = ''
    else:
        try:
            include = conf['include']
            if include is not None and len(include) == 0:
                include = ''
            else:
                include = ';'.join(include)
        except KeyError:
            include = ''
        if include is None:
            include = ''
    return include


def data_exclude(conf):
    # type: (dict) -> str
    """Retrieve input data exclude filters
    :param dict conf: configuration object
    :rtype: str
    :return: exclude filters
    """
    try:
        exclude = conf['exclude']
        if exclude is not None and len(exclude) == 0:
            exclude = ''
        else:
            exclude = ';'.join(exclude)
    except KeyError:
        exclude = ''
    if exclude is None:
        exclude = ''
    return exclude


def input_data_destination(conf, on_task):
    # type: (dict, bool) -> str
    """Retrieve input data destination
    :param dict conf: configuration object
    :param bool on_task: if input data is on the task spec
    :rtype: str
    :return: destination
    """
    try:
        dst = conf['destination']
        if util.is_none_or_empty(dst):
            raise KeyError()
    except KeyError:
        if on_task:
            dst = '$AZ_BATCH_TASK_WORKING_DIR'
        else:
            raise
    return dst


def input_data_job_id(conf):
    # type: (dict) -> str
    """Retrieve input data job id
    :param dict conf: configuration object
    :rtype: str
    :return: job id
    """
    return conf['job_id']


def input_data_task_id(conf):
    # type: (dict) -> str
    """Retrieve input data task id
    :param dict conf: configuration object
    :rtype: str
    :return: task id
    """
    return conf['task_id']


def output_data_source(conf):
    # type: (dict) -> str
    """Retrieve output data source
    :param dict conf: configuration object
    :rtype: str
    :return: source
    """
    try:
        src = conf['source']
        if util.is_none_or_empty(src):
            raise KeyError()
    except KeyError:
        src = '$AZ_BATCH_TASK_DIR'
    return src


# JOBS SETTINGS
def job_specifications(config):
    # type: (dict) -> dict
    """Get job specifications config block
    :param dict config: configuration object
    :rtype: dict
    :return: job specifications
    """
    return config['job_specifications']


def job_tasks(conf):
    # type: (dict) -> list
    """Get all tasks for job
    :param dict config: configuration object
    :rtype: list
    :return: list of tasks
    """
    return conf['tasks']


def job_id(conf):
    # type: (dict) -> str
    """Get job id of a job specification
    :param dict conf: job configuration object
    :rtype: str
    :return: job id
    """
    return conf['id']


def job_multi_instance_auto_complete(conf):
    # type: (dict) -> bool
    """Get multi-instance job autocompelte setting
    :param dict conf: job configuration object
    :rtype: bool
    :return: multi instance job autocomplete
    """
    try:
        mi_ac = conf['multi_instance_auto_complete']
    except KeyError:
        mi_ac = True
    return mi_ac


def job_environment_variables(conf):
    # type: (dict) -> str
    """Get env vars of a job specification
    :param dict conf: job configuration object
    :rtype: list
    :return: job env vars
    """
    try:
        env_vars = conf['environment_variables']
        if util.is_none_or_empty(env_vars):
            raise KeyError()
    except KeyError:
        env_vars = {}
    return env_vars


def job_environment_variables_keyvault_secret_id(conf):
    # type: (dict) -> str
    """Get keyvault env vars of a job specification
    :param dict conf: job configuration object
    :rtype: list
    :return: job env vars
    """
    try:
        secid = conf['environment_variables_keyvault_secret_id']
        if util.is_none_or_empty(secid):
            raise KeyError()
    except KeyError:
        secid = None
    return secid


def job_max_task_retries(conf):
    # type: (dict) -> int
    """Get number of times a task should be retried in a particular job
    :param dict conf: job configuration object
    :rtype: int
    :return: max task retry count
    """
    try:
        max_task_retries = conf['max_task_retries']
        if max_task_retries is None:
            raise KeyError()
    except KeyError:
        max_task_retries = None
    return max_task_retries


def has_depends_on_task(conf):
    # type: (dict) -> bool
    """Determines if task has task dependencies
    :param dict conf: job configuration object
    :rtype: bool
    :return: task has task dependencies
    """
    if ('depends_on' in conf and util.is_not_empty(conf['depends_on']) or
            'depends_on_range' in conf and
            util.is_not_empty(conf['depends_on_range'])):
        if 'id' not in conf or util.is_none_or_empty(conf['id']):
            raise ValueError(
                'task id is not specified, but depends_on or '
                'depends_on_range is set')
        return True
    return False


def is_multi_instance_task(conf):
    # type: (dict) -> bool
    """Determines if task is multi-isntance
    :param dict conf: job configuration object
    :rtype: bool
    :return: task is multi-instance
    """
    return 'multi_instance' in conf


def task_name(conf):
    # type: (dict) -> str
    """Get task name
    :param dict conf: job configuration object
    :rtype: str
    :return: task name
    """
    try:
        name = conf['name']
        if util.is_none_or_empty(name):
            raise KeyError()
    except KeyError:
        name = None
    return name


def set_task_name(conf, name):
    # type: (dict, str) -> None
    """Set task name
    :param dict conf: job configuration object
    :param str name: task name to set
    """
    conf['name'] = name


def task_id(conf):
    # type: (dict) -> str
    """Get task id
    :param dict conf: job configuration object
    :rtype: str
    :return: task id
    """
    try:
        id = conf['id']
        if util.is_none_or_empty(id):
            raise KeyError()
    except KeyError:
        id = None
    return id


def set_task_id(conf, id):
    # type: (dict, str) -> None
    """Set task id
    :param dict conf: job configuration object
    :param str id: task id to set
    """
    conf['id'] = id


def task_settings(pool, config, conf):
    # type: (azure.batch.models.CloudPool, dict, dict) -> TaskSettings
    """Get task settings
    :param azure.batch.models.CloudPool pool: cloud pool object
    :param dict config: configuration dict
    :param dict conf: job configuration object
    :rtype: TaskSettings
    :return: task settings
    """
    # id must be populated by the time this function is invoked
    task_id = conf['id']
    if util.is_none_or_empty(task_id):
        raise ValueError('task id is invalid')
    image = conf['image']
    if util.is_none_or_empty(image):
        raise ValueError('image is invalid')
    # get some pool props
    publisher = pool.virtual_machine_configuration.image_reference.\
        publisher.lower()
    offer = pool.virtual_machine_configuration.image_reference.offer.lower()
    sku = pool.virtual_machine_configuration.image_reference.sku.lower()
    # get depends on
    try:
        depends_on = conf['depends_on']
        if util.is_none_or_empty(depends_on):
            raise KeyError()
    except KeyError:
        depends_on = None
    try:
        depends_on_range = conf['depends_on_range']
        if util.is_none_or_empty(depends_on_range):
            raise KeyError()
        if len(depends_on_range) != 2:
            raise ValueError('depends_on_range requires 2 elements exactly')
        if (type(depends_on_range[0]) is not int or
                type(depends_on_range[1]) is not int):
            raise ValueError('depends_on_range requires integral members only')
    except KeyError:
        depends_on_range = None
    # get additional resource files
    try:
        rfs = conf['resource_files']
        if util.is_none_or_empty(rfs):
            raise KeyError()
        resource_files = []
        for rf in rfs:
            try:
                fm = rf['file_mode']
                if util.is_none_or_empty(fm):
                    raise KeyError()
            except KeyError:
                fm = None
            resource_files.append(
                ResourceFileSettings(
                    file_path=rf['file_path'],
                    blob_source=rf['blob_source'],
                    file_mode=fm,
                )
            )
    except KeyError:
        resource_files = None
    # get generic run opts
    try:
        run_opts = conf['additional_docker_run_options']
    except KeyError:
        run_opts = []
    # parse remove container option
    try:
        rm_container = conf['remove_container_after_exit']
    except KeyError:
        pass
    else:
        if rm_container and '--rm' not in run_opts:
            run_opts.append('--rm')
    # parse /dev/shm option
    try:
        shm_size = conf['shm_size']
        if util.is_none_or_empty(shm_size):
            raise KeyError()
    except KeyError:
        pass
    else:
        if not any(x.startswith('--shm-size=') for x in run_opts):
            run_opts.append('--shm-size={}'.format(shm_size))
    # parse name option, if not specified use task id
    try:
        name = conf['name']
        if util.is_none_or_empty(name):
            raise KeyError()
    except KeyError:
        name = task_id
        set_task_name(conf, name)
    run_opts.append('--name {}'.format(name))
    # parse labels option
    try:
        labels = conf['labels']
        if util.is_not_empty(labels):
            for label in labels:
                run_opts.append('-l {}'.format(label))
        del labels
    except KeyError:
        pass
    # parse ports option
    try:
        ports = conf['ports']
        if util.is_not_empty(ports):
            for port in ports:
                run_opts.append('-p {}'.format(port))
        del ports
    except KeyError:
        pass
    # parse entrypoint
    try:
        entrypoint = conf['entrypoint']
        if util.is_not_empty(entrypoint):
            run_opts.append('--entrypoint {}'.format(entrypoint))
        del entrypoint
    except KeyError:
        pass
    # get command
    try:
        command = conf['command']
        if util.is_none_or_empty(command):
            raise KeyError()
    except KeyError:
        command = None
    # parse data volumes
    try:
        data_volumes = conf['data_volumes']
        if util.is_none_or_empty(data_volumes):
            raise KeyError()
    except KeyError:
        pass
    else:
        dv = global_resources_data_volumes(config)
        for dvkey in data_volumes:
            try:
                hostpath = dv[dvkey]['host_path']
                if util.is_none_or_empty(hostpath):
                    raise KeyError()
            except KeyError:
                hostpath = None
            if util.is_not_empty(hostpath):
                run_opts.append('-v {}:{}'.format(
                    hostpath, dv[dvkey]['container_path']))
            else:
                run_opts.append('-v {}'.format(
                    dv[dvkey]['container_path']))
    # parse shared data volumes
    try:
        shared_data_volumes = conf['shared_data_volumes']
        if util.is_none_or_empty(shared_data_volumes):
            raise KeyError()
    except KeyError:
        pass
    else:
        sdv = global_resources_shared_data_volumes(config)
        for sdvkey in shared_data_volumes:
            if is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
                run_opts.append('-v {}/{}:{}'.format(
                    '$AZ_BATCH_NODE_SHARED_DIR',
                    get_gluster_volume(),
                    shared_data_volume_container_path(sdv, sdvkey)))
            else:
                run_opts.append('-v {}:{}'.format(
                    sdvkey, shared_data_volume_container_path(sdv, sdvkey)))
    # env vars
    try:
        env_vars = conf['environment_variables']
        if util.is_none_or_empty(env_vars):
            raise KeyError()
    except KeyError:
        env_vars = {}
    try:
        ev_secid = conf['environment_variables_keyvault_secret_id']
        if util.is_none_or_empty(ev_secid):
            raise KeyError()
    except KeyError:
        ev_secid = None
    # max_task_retries
    try:
        max_task_retries = conf['max_task_retries']
        if max_task_retries is None:
            raise KeyError()
    except KeyError:
        max_task_retries = None
    # retention time
    try:
        retention_time = conf['retention_time']
        if util.is_none_or_empty(retention_time):
            raise KeyError()
        retention_time = util.convert_string_to_timedelta(retention_time)
    except KeyError:
        retention_time = None
    # infiniband
    try:
        infiniband = conf['infiniband']
    except KeyError:
        infiniband = False
    # gpu
    try:
        gpu = conf['gpu']
    except KeyError:
        gpu = False
    # adjust for gpu settings
    if gpu:
        if not is_gpu_pool(pool.vm_size):
            raise RuntimeError(
                ('cannot initialize a gpu task on nodes without '
                 'gpus, pool: {} vm_size: {}').format(pool.id, pool.vm_size))
        # TODO other images as they become available with gpu support
        if (publisher != 'canonical' and offer != 'ubuntuserver' and
                sku < '16.04.0-lts'):
            raise ValueError(
                ('Unsupported gpu VM config, publisher={} offer={} '
                 'sku={}').format(publisher, offer, sku))
        # set docker commands with nvidia docker wrapper
        docker_run_cmd = 'nvidia-docker run'
        docker_exec_cmd = 'nvidia-docker exec'
    else:
        # set normal run and exec commands
        docker_run_cmd = 'docker run'
        docker_exec_cmd = 'docker exec'
    # adjust for infiniband
    if infiniband:
        if not pool.enable_inter_node_communication:
            raise RuntimeError(
                ('cannot initialize an infiniband task on a '
                 'non-internode communication enabled '
                 'pool: {}').format(pool.id))
        if not is_rdma_pool(pool.vm_size):
            raise RuntimeError(
                ('cannot initialize an infiniband task on nodes '
                 'without RDMA, pool: {} vm_size: {}').format(
                     pool.id, pool.vm_size))
        # only centos-hpc and sles-hpc:12-sp1 are supported
        # for infiniband
        if publisher == 'openlogic' and offer == 'centos-hpc':
            run_opts.append('-v /etc/rdma:/etc/rdma:ro')
            run_opts.append('-v /etc/rdma/dat.conf:/etc/dat.conf:ro')
        elif (publisher == 'suse' and offer == 'sles-hpc' and
              sku == '12-sp1'):
            run_opts.append('-v /etc/dat.conf:/etc/dat.conf:ro')
            run_opts.append('-v /etc/dat.conf:/etc/rdma/dat.conf:ro')
        else:
            raise ValueError(
                ('Unsupported infiniband VM config, publisher={} '
                 'offer={}').format(publisher, offer))
        # add infiniband run opts
        run_opts.append('-v /opt/intel:/opt/intel:ro')
        run_opts.append('--net=host')
        run_opts.append('--ulimit memlock=9223372036854775807')
        run_opts.append('--device=/dev/hvnd_rdma')
        run_opts.append('--device=/dev/infiniband/rdma_cm')
        run_opts.append('--device=/dev/infiniband/uverbs0')
    # mount batch root dir
    run_opts.append(
        '-v $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR')
    # set working directory
    run_opts.append('-w $AZ_BATCH_TASK_WORKING_DIR')
    # always add option for envfile
    envfile = '.shipyard.envlist'
    run_opts.append('--env-file {}'.format(envfile))
    # populate mult-instance settings
    if is_multi_instance_task(conf):
        if not pool.enable_inter_node_communication:
            raise RuntimeError(
                ('cannot run a multi-instance task on a '
                 'non-internode communication enabled '
                 'pool: {}').format(pool_id))
        # container must be named
        if util.is_none_or_empty(name):
            raise ValueError(
                'multi-instance task must be invoked with a named '
                'container')
        # docker exec command cannot be empty/None
        if util.is_none_or_empty(command):
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
            coordination_command = conf[
                'multi_instance']['coordination_command']
            if util.is_none_or_empty(coordination_command):
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
        # get num instances
        num_instances = conf['multi_instance']['num_instances']
        if not isinstance(num_instances, int):
            if num_instances == 'pool_specification_vm_count':
                num_instances = pool_vm_count(config)
            elif num_instances == 'pool_current_dedicated':
                num_instances = pool.current_dedicated
            else:
                raise ValueError(
                    ('multi instance num instances setting '
                     'invalid: {}').format(num_instances))
        # get common resource files
        try:
            mi_rfs = conf['multi_instance']['resource_files']
            if util.is_none_or_empty(mi_rfs):
                raise KeyError()
            mi_resource_files = []
            for rf in mi_rfs:
                try:
                    fm = rf['file_mode']
                    if util.is_none_or_empty(fm):
                        raise KeyError()
                except KeyError:
                    fm = None
                mi_resource_files.append(
                    ResourceFileSettings(
                        file_path=rf['file_path'],
                        blob_source=rf['blob_source'],
                        file_mode=fm,
                    )
                )
        except KeyError:
            mi_resource_files = None
    else:
        num_instances = 0
        cc_args = None
        mi_resource_files = None
    return TaskSettings(
        id=task_id,
        image=image,
        name=name,
        docker_run_options=run_opts,
        environment_variables=env_vars,
        environment_variables_keyvault_secret_id=ev_secid,
        envfile=envfile,
        resource_files=resource_files,
        max_task_retries=max_task_retries,
        retention_time=retention_time,
        command=command,
        infiniband=infiniband,
        gpu=gpu,
        depends_on=depends_on,
        depends_on_range=depends_on_range,
        docker_run_cmd=docker_run_cmd,
        docker_exec_cmd=docker_exec_cmd,
        multi_instance=MultiInstanceSettings(
            num_instances=num_instances,
            coordination_command=cc_args,
            resource_files=mi_resource_files,
        ),
    )


# REMOTEFS SETTINGS
def virtual_network_settings(
        config, default_existing_ok=False, default_create_nonexistant=True):
    # type: (dict) -> VirtualNetworkSettings
    """Get virtual network settings
    :param dict config: configuration dict
    :param bool default_existing_ok: default existing ok
    :param bool default_create_nonexistant: default create nonexistant
    :rtype: VirtualNetworkSettings
    :return: virtual network settings
    """
    try:
        conf = config['virtual_network']
    except KeyError:
        conf = {}
    name = _kv_read_checked(conf, 'name')
    address_space = _kv_read_checked(conf, 'address_space')
    existing_ok = _kv_read(conf, 'existing_ok', default_existing_ok)
    subnet_name = _kv_read_checked(conf['subnet'], 'name')
    subnet_address_prefix = _kv_read_checked(conf['subnet'], 'address_prefix')
    create_nonexistant = _kv_read(
        conf, 'create_nonexistant', default_create_nonexistant)
    return VirtualNetworkSettings(
        name=name,
        address_space=address_space,
        subnet_name=subnet_name,
        subnet_address_prefix=subnet_address_prefix,
        existing_ok=existing_ok,
        create_nonexistant=create_nonexistant,
    )


def remotefs_settings(config):
    # type: (dict) -> RemoteFsSettings
    """Get remote fs settings
    :param dict config: configuration dict
    :rtype: RemoteFsSettings
    :return: remote fs settings
    """
    # general settings
    conf = config['remote_fs']
    resource_group = conf['resource_group']
    if util.is_none_or_empty(resource_group):
        raise ValueError('invalid resource_group in remote_fs')
    location = conf['location']
    if util.is_none_or_empty(location):
        raise ValueError('invalid location in remote_fs')
    # managed disk settings
    md_conf = conf['managed_disks']
    md_premium = _kv_read(md_conf, 'premium', False)
    md_disk_size_gb = _kv_read(md_conf, 'disk_size_gb')
    md_disk_ids = _kv_read_checked(md_conf, 'disk_ids')
    # storage cluster settings
    sc_conf = conf['storage_cluster']
    sc_id = sc_conf['id']
    if util.is_none_or_empty(sc_id):
        raise ValueError('invalid id in remote_fs:storage_cluster')
    sc_vm_count = _kv_read(sc_conf, 'vm_count', 1)
    sc_vm_size = _kv_read_checked(sc_conf, 'vm_size')
    sc_static_public_ip = _kv_read(sc_conf, 'static_public_ip', False)
    sc_hostname_prefix = _kv_read_checked(sc_conf, 'hostname_prefix')
    # sc network security settings
    ns_conf = sc_conf['network_security']
    sc_ns_inbound = {
        'ssh': InboundNetworkSecurityRule(
            destination_port_range='22',
            source_address_prefix=_kv_read_checked(ns_conf, 'ssh', ['*']),
            protocol='tcp',
        ),
    }
    if not isinstance(sc_ns_inbound['ssh'].source_address_prefix, list):
        raise ValueError('expected list for ssh network security rule')
    if 'nfs' in ns_conf:
        sc_ns_inbound['nfs'] = InboundNetworkSecurityRule(
            destination_port_range='2049',
            source_address_prefix=_kv_read_checked(ns_conf, 'nfs', ['*']),
            protocol='tcp',
        )
        if not isinstance(sc_ns_inbound['nfs'].source_address_prefix, list):
            raise ValueError('expected list for nfs network security rule')
    if 'custom_inbound' in ns_conf:
        _reserved = frozenset(['ssh', 'nfs', 'glusterfs'])
        for key in ns_conf['custom_inbound']:
            # ensure key is not reserved
            if key.lower() in _reserved:
                raise ValueError(
                    ('custom inbound rule of name {} conflicts with a '
                     'reserved name {}').format(key, _reserved))
            sc_ns_inbound[key] = InboundNetworkSecurityRule(
                destination_port_range=_kv_read_checked(
                    ns_conf['custom_inbound'][key], 'destination_port_range'),
                source_address_prefix=_kv_read_checked(
                    ns_conf['custom_inbound'][key], 'source_address_prefix'),
                protocol=_kv_read_checked(
                    ns_conf['custom_inbound'][key], 'protocol'),
            )
            if not isinstance(sc_ns_inbound[key].source_address_prefix, list):
                raise ValueError(
                    'expected list for network security rule {} '
                    'source_address_prefix'.format(key))
    # sc file server settings
    fs_conf = sc_conf['file_server']
    sc_fs_type = _kv_read_checked(fs_conf, 'type')
    if util.is_none_or_empty(sc_fs_type):
        raise ValueError(
            'remote_fs:storage_cluster:file_server:type must be specified')
    # cross check against number of vms
    if sc_fs_type == 'nfs' and sc_vm_count != 1:
        raise ValueError(
            ('invalid combination of file_server:type {} and '
             'vm_count {}').format(sc_fs_type, sc_vm_count))
    sc_fs_mountpoint = _kv_read_checked(fs_conf, 'mountpoint')
    if util.is_none_or_empty(sc_fs_mountpoint):
        raise ValueError(
            'remote_fs:storage_cluster:file_server must be specified')
    # sc ssh settings
    ssh_conf = sc_conf['ssh']
    sc_ssh_username = _kv_read_checked(ssh_conf, 'username')
    sc_ssh_public_key = _kv_read_checked(ssh_conf, 'ssh_public_key')
    sc_ssh_gen_file_path = _kv_read_checked(
        ssh_conf, 'generated_file_export_path', '.')
    # sc vm disk map settings
    vmd_conf = sc_conf['vm_disk_map']
    _disk_set = frozenset(md_disk_ids)
    disk_map = {}
    for vmkey in vmd_conf:
        # ensure all disks in disk array are specified in managed disks
        disk_array = vmd_conf[vmkey]['disk_array']
        if not _disk_set.issuperset(set(disk_array)):
            raise ValueError(
                ('All disks {} for vm {} are not specified in '
                 'managed_disks:disk_ids ({})').format(
                     disk_array, vmkey, _disk_set))
        if len(disk_array) == 1:
            # disable raid
            raid_level = -1
        else:
            raid_level = vmd_conf[vmkey]['raid_level']
            if raid_level == 0 and len(disk_array) < 2:
                raise ValueError('RAID-0 arrays require at least two disks')
            if raid_level != 0:
                raise ValueError('Unsupported RAID level {}'.format(
                    raid_level))
        filesystem = vmd_conf[vmkey]['filesystem']
        if filesystem != 'btrfs' and not filesystem.startswith('ext'):
            raise ValueError('Unsupported filesystem type {}'.format(
                filesystem))
        disk_map[int(vmkey)] = MappedVmDiskSettings(
            disk_array=disk_array,
            filesystem=vmd_conf[vmkey]['filesystem'],
            raid_level=raid_level,
        )
    # check disk map against vm_count
    if len(disk_map) != sc_vm_count:
        raise ValueError(
            ('Number of entries in storage_cluster:vm_disk_map {} '
             'inconsistent with storage_cluster:vm_count {}').format(
                 len(disk_map), sc_vm_count))
    return RemoteFsSettings(
        resource_group=resource_group,
        location=location,
        managed_disks=ManagedDisksSettings(
            premium=md_premium,
            disk_size_gb=md_disk_size_gb,
            disk_ids=md_disk_ids,
        ),
        storage_cluster=StorageClusterSettings(
            id=sc_id,
            virtual_network=virtual_network_settings(
                sc_conf,
                default_existing_ok=False,
                default_create_nonexistant=True,
            ),
            network_security=NetworkSecuritySettings(
                inbound=sc_ns_inbound,
            ),
            file_server=FileServerSettings(
                type=sc_fs_type,
                mountpoint=sc_fs_mountpoint,
            ),
            vm_count=sc_vm_count,
            vm_size=sc_vm_size,
            static_public_ip=sc_static_public_ip,
            hostname_prefix=sc_hostname_prefix,
            ssh=SSHSettings(
                username=sc_ssh_username,
                expiry_days=9999,
                ssh_public_key=sc_ssh_public_key,
                generate_docker_tunnel_script=False,
                generated_file_export_path=sc_ssh_gen_file_path,
                hpn_server_swap=False,
            ),
            vm_disk_map=disk_map,
        ),
    )
