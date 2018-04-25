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
import datetime
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
# non-stdlib imports
import azure.batch.models as batchmodels
import dateutil.parser
# local imports
from . import task_factory
from . import util

# global defines
_METADATA_VERSION_NAME = 'batch_shipyard_version'
_GLUSTER_DEFAULT_VOLNAME = 'gv0'
_GLUSTER_ON_COMPUTE_VOLUME = 'gluster_on_compute/{}'.format(
    _GLUSTER_DEFAULT_VOLNAME)
_HOST_MOUNTS_DIR = '$AZ_BATCH_NODE_ROOT_DIR/mounts'
_HOST_MOUNTS_DIR_WINDOWS = '%AZ_BATCH_NODE_ROOT_DIR%\\mounts'
_TENSORBOARD_DOCKER_IMAGE = (
    'gcr.io/tensorflow/tensorflow',
    '/usr/local/lib/python2.7/dist-packages/tensorboard/main.py',
    6006
)
_GPU_CUDA9_INSTANCES = frozenset((
    'standard_nc6', 'standard_nc12', 'standard_nc24', 'standard_nc24r',
))
_GPU_COMPUTE_INSTANCES = frozenset((
    # standard_nc
    'standard_nc6', 'standard_nc12', 'standard_nc24', 'standard_nc24r',
    # standard_nc_v2
    'standard_nc6s_v2', 'standard_nc12s_v2', 'standard_nc24s_v2',
    'standard_nc24rs_v2',
    # standard nc_v3
    'standard_nc6s_v3', 'standard_nc12s_v3', 'standard_nc24s_v3',
    'standard_nc24rs_v3',
    # standard_nd
    'standard_nd6s', 'standard_nd12s', 'standard_nd24s', 'standard_nd24rs',
))
_GPU_VISUALIZATION_INSTANCES = frozenset((
    # standard_nv
    'standard_nv6', 'standard_nv12', 'standard_nv24',
))
_GPU_INSTANCES = _GPU_COMPUTE_INSTANCES.union(_GPU_VISUALIZATION_INSTANCES)
_RDMA_INSTANCES = frozenset((
    # standard_a
    'standard_a8', 'standard_a9',
    # standard_h
    'standard_h16r', 'standard_h16mr',
    # standard_nc
    'standard_nc24r',
    # standard_nc_v2
    'standard_nc24rs_v2',
    # standard_nc_v3
    'standard_nc24rs_v3',
    # standard_nd
    'standard_nd24rs',
))
_PREMIUM_STORAGE_INSTANCE_PREFIXES = frozenset((
    'standard_ds', 'standard_gs',
))
_PREMIUM_STORAGE_INSTANCE_SUFFIXES = frozenset((
    's', 's_v2', 's_v3',
))
_VM_TCP_NO_TUNE = frozenset((
    # basic
    'basic_a0', 'basic_a1', 'basic_a2', 'basic_a3', 'basic_a4',
    # standard_a
    'standard_a0', 'standard_a1', 'standard_a2', 'standard_a3', 'standard_a5',
    'standard_a6',
    # standard_a_v2
    'standard_a1_v2', 'standard_a2_v2', 'standard_a4_v2', 'standard_a2m_v2',
    'standard_a4m_v2',
    # standard_d
    'standard_d1', 'standard_ds1', 'standard_d2', 'standard_ds2',
    # standard_d_v2
    'standard_d1_v2', 'standard_ds1_v2',
    # standard_d_v3
    'standard_d2_v3', 'standard_d2s_v3',
    # standard_e_v3
    'standard_e2_v3', 'standard_e2s_v3',
    # standard_f
    'standard_f1', 'standard_f1s',
    # standard_f_v2
    'standard_f2s_v2',
    # standard_b
    'standard_b1s', 'standard_b1ms', 'standard_b2s', 'standard_b2ms',
    'standard_b4ms', 'standard_b8ms',
))
_SINGULARITY_COMMANDS = frozenset(('exec', 'run'))
_FORBIDDEN_MERGE_TASK_PROPERTIES = frozenset((
    'depends_on', 'depends_on_range', 'multi_instance', 'task_factory'
))
# named tuples
PoolVmCountSettings = collections.namedtuple(
    'PoolVmCountSettings', [
        'dedicated',
        'low_priority',
    ]
)
PoolVmPlatformImageSettings = collections.namedtuple(
    'PoolVmPlatformImageSettings', [
        'publisher',
        'offer',
        'sku',
        'version',
        'native',
        'license_type',
    ]
)
PoolVmCustomImageSettings = collections.namedtuple(
    'PoolVmCustomImageSettings', [
        'arm_image_id',
        'node_agent',
        'native',
        'license_type',
    ]
)
PoolAutoscaleScenarioSettings = collections.namedtuple(
    'PoolAutoscaleScenarioSettings', [
        'name',
        'maximum_vm_count',
        'node_deallocation_option',
        'sample_lookback_interval',
        'required_sample_percentage',
        'rebalance_preemption_percentage',
        'bias_last_sample',
        'bias_node_type',
    ]
)
PoolAutoscaleSettings = collections.namedtuple(
    'PoolAutoscaleSettings', [
        'evaluation_interval',
        'formula',
        'scenario',
    ]
)
PoolAutopoolSettings = collections.namedtuple(
    'PoolAutopoolSettings', [
        'pool_lifetime',
        'keep_alive',
    ]
)
PoolSettings = collections.namedtuple(
    'PoolSettings', [
        'id', 'vm_size', 'vm_count', 'resize_timeout', 'max_tasks_per_node',
        'inter_node_communication_enabled', 'vm_configuration',
        'reboot_on_start_task_failed', 'attempt_recovery_on_unusable',
        'block_until_all_global_resources_loaded',
        'transfer_files_on_pool_creation', 'input_data', 'resource_files',
        'gpu_driver', 'ssh', 'rdp', 'additional_node_prep_commands_pre',
        'additional_node_prep_commands_post', 'virtual_network',
        'autoscale', 'node_fill_type', 'remote_access_control',
        'certificates',
    ]
)
SSHSettings = collections.namedtuple(
    'SSHSettings', [
        'username', 'expiry_days', 'ssh_public_key', 'ssh_public_key_data',
        'ssh_private_key', 'generate_docker_tunnel_script',
        'generated_file_export_path', 'hpn_server_swap',
    ]
)
RDPSettings = collections.namedtuple(
    'RDPSettings', [
        'username', 'expiry_days', 'password',
    ]
)
RemoteAccessControl = collections.namedtuple(
    'RemoteAccessControl', [
        'starting_port', 'backend_port', 'protocol', 'allow', 'deny',
    ]
)
AADSettings = collections.namedtuple(
    'AADSettings', [
        'directory_id', 'application_id', 'auth_key', 'rsa_private_key_pem',
        'x509_cert_sha1_thumbprint', 'user', 'password', 'endpoint',
        'token_cache_file', 'authority_url',
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
        'resource_group', 'subscription_id', 'location',
    ]
)
StorageCredentialsSettings = collections.namedtuple(
    'StorageCredentialsSettings', [
        'account', 'account_key', 'endpoint', 'resource_group',
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
        'peer_to_peer', 'concurrent_source_downloads',
    ]
)
PeerToPeerSettings = collections.namedtuple(
    'PeerToPeerSettings', [
        'enabled', 'compression', 'direct_download_seed_bias',
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
        'max_parallel_transfers_per_node', 'is_file_share',
        'remote_path', 'blobxfer_extra_options',
    ]
)
JobScheduleSettings = collections.namedtuple(
    'JobScheduleSettings', [
        'do_not_run_until', 'do_not_run_after', 'start_window',
        'recurrence_interval',
    ]
)
JobManagerSettings = collections.namedtuple(
    'JobManagerSettings', [
        'allow_low_priority_node', 'run_exclusive', 'monitor_task_completion',
    ]
)
JobRecurrenceSettings = collections.namedtuple(
    'JobRecurrenceSettings', [
        'schedule', 'job_manager',
    ]
)
UserIdentitySettings = collections.namedtuple(
    'UserIdentitySettings', [
        'default_pool_admin', 'specific_user_uid', 'specific_user_gid',
    ]
)
TaskFactoryStorageSettings = collections.namedtuple(
    'TaskFactoryStorageSettings', [
        'storage_settings', 'storage_link_name', 'container', 'remote_path',
        'is_file_share', 'include', 'exclude',
    ]
)
TaskExitOptions = collections.namedtuple(
    'TaskExitOptions', [
        'job_action', 'dependency_action',
    ]
)
TaskSettings = collections.namedtuple(
    'TaskSettings', [
        'id', 'docker_image', 'singularity_image', 'name', 'run_options',
        'docker_exec_options', 'singularity_cmd', 'run_elevated',
        'environment_variables', 'environment_variables_keyvault_secret_id',
        'envfile', 'resource_files', 'command', 'infiniband', 'gpu',
        'depends_on', 'depends_on_range', 'max_task_retries', 'max_wall_time',
        'retention_time', 'docker_run_cmd', 'docker_exec_cmd',
        'multi_instance', 'default_exit_options',
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
        'resource_group', 'premium', 'disk_size_gb', 'disk_names',
    ]
)
VirtualNetworkSettings = collections.namedtuple(
    'VirtualNetworkSettings', [
        'arm_subnet_id', 'name', 'resource_group', 'address_space',
        'subnet_name', 'subnet_address_prefix', 'existing_ok',
        'create_nonexistant',
    ]
)
SambaAccountSettings = collections.namedtuple(
    'SambaAccountSettings', [
        'username', 'password', 'uid', 'gid',
    ]
)
SambaSettings = collections.namedtuple(
    'SambaSettings', [
        'share_name', 'account', 'read_only', 'create_mask',
        'directory_mask',
    ]
)
FileServerSettings = collections.namedtuple(
    'FileServerSettings', [
        'type', 'mountpoint', 'mount_options', 'server_options', 'samba',
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
        'disk_array', 'filesystem', 'raid_level',
    ]
)
PublicIpSettings = collections.namedtuple(
    'PublicIpSettings', [
        'enabled', 'static',
    ]
)
StorageClusterSettings = collections.namedtuple(
    'StorageClusterSettings', [
        'id', 'resource_group', 'virtual_network', 'network_security',
        'file_server', 'vm_count', 'vm_size', 'fault_domains', 'public_ip',
        'hostname_prefix', 'ssh', 'vm_disk_map', 'accelerated_networking',
    ]
)
RemoteFsSettings = collections.namedtuple(
    'RemoteFsSettings', [
        'location', 'managed_disks', 'storage_cluster',
    ]
)
CustomMountFstabSettings = collections.namedtuple(
    'CustomMountFstabSettings', [
        'fs_spec', 'fs_vfstype', 'fs_mntops', 'fs_freq', 'fs_passno',
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
    # type: (dict, str, obj) -> obj
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


def get_metadata_version_name():
    # type: (None) -> str
    """Get metadata version name
    :rtype: str
    :return: metadata version name
    """
    return _METADATA_VERSION_NAME


def get_tensorboard_docker_image():
    # type: (None) -> Tuple[str, str]
    """Get tensorboard docker image
    :rtype: tuple
    :return: (tensorboard docker image,
        absolute path to tensorboard.py, container port)
    """
    return _TENSORBOARD_DOCKER_IMAGE


def get_gluster_default_volume_name():
    # type: (None) -> str
    """Get gluster default volume name
    :rtype: str
    :return: gluster default volume name
    """
    return _GLUSTER_DEFAULT_VOLNAME


def get_gluster_on_compute_volume():
    # type: (None) -> str
    """Get gluster on compute volume mount suffix
    :rtype: str
    :return: gluster on compute volume mount
    """
    return _GLUSTER_ON_COMPUTE_VOLUME


def get_host_mounts_path(is_windows):
    # type: (bool) -> str
    """Get host mounts path
    :param bool is_windows: is windows pool
    :rtype: str
    :return: host mounts dir
    """
    return _HOST_MOUNTS_DIR_WINDOWS if is_windows else _HOST_MOUNTS_DIR


def get_singularity_tmpdir(config):
    # type: (dict) -> str
    """Get Singularity tmpdir var
    :param dict config: configuration dict
    :rtype: str
    :return: singularity tmpdir
    """
    if is_windows_pool(config):
        sep = '\\'
    else:
        sep = '/'
    return sep.join((temp_disk_mountpoint(config), 'singularity', 'tmp'))


def get_singularity_cachedir(config):
    # type: (dict) -> str
    """Get Singularity cachedir var
    :param dict config: configuration dict
    :rtype: str
    :return: singularity cachedir
    """
    if is_windows_pool(config):
        sep = '\\'
    else:
        sep = '/'
    return sep.join((temp_disk_mountpoint(config), 'singularity', 'cache'))


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


def get_gpu_type_from_vm_size(vm_size):
    # type: (str) -> str
    """Get GPU type as string
    :param str vm_size: vm size
    :rtype: str
    :return: type of gpu and compute capability
    """
    if is_gpu_compute_pool(vm_size):
        if vm_size.lower() in _GPU_CUDA9_INSTANCES:
            return 'compute_cc37'
        else:
            return 'compute_cc6-7'
    elif is_gpu_visualization_pool(vm_size):
        return 'viz_cc52'
    else:
        return None


def gpu_configuration_check(config, vm_size=None):
    # type: (dict, str) -> bool
    """Check if OS is allowed with a GPU VM
    :param dict config: configuration dict
    :param str vm_size: vm size
    :rtype: bool
    :return: if configuration is allowed
    """
    # if this is not a gpu sku, always allow
    if util.is_none_or_empty(vm_size):
        vm_size = pool_settings(config).vm_size
    if not is_gpu_pool(vm_size):
        return True
    # always allow gpu with custom images
    node_agent = pool_custom_image_node_agent(config)
    if util.is_not_empty(node_agent):
        return True
    # check for platform image support
    publisher = pool_publisher(config, lower=True)
    offer = pool_offer(config, lower=True)
    sku = pool_sku(config, lower=True)
    if publisher == 'microsoft-azure-batch':
        return True
    elif (publisher == 'canonical' and offer == 'ubuntuserver' and
            sku > '16.04'):
        return True
    elif publisher == 'openlogic':
        if offer == 'centos-hpc' and sku == '7.3':
            return True
        elif offer == 'centos' and sku == '7.3':
            return True
    return False


def is_native_docker_pool(config, vm_config=None):
    # type: (dict, any) -> bool
    """Check if vm configuration has native docker support
    :param dict config: configuration dict
    :param any vm_config: vm configuration
    :rtype: bool
    :return: if vm configuration has native docker support
    """
    if vm_config is None:
        vm_config = _populate_pool_vm_configuration(config)
    return vm_config.native


def is_windows_pool(config, vm_config=None):
    # type: (dict, any) -> bool
    """Check if pool is Windows
    :param dict config: configuration dict
    :param any vm_config: vm configuration
    :rtype: bool
    :return: pool is Windows
    """
    if vm_config is None:
        vm_config = _populate_pool_vm_configuration(config)
    if is_platform_image(config, vm_config=vm_config):
        return vm_config.publisher == 'microsoftwindowsserver'
    else:
        return vm_config.node_agent.startswith('batch.node.windows')


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


def is_premium_storage_vm_size(vm_size):
    # type: (str) -> bool
    """Check if vm size is premium storage compatible
    :pararm str vm_size: vm size
    :rtype: bool
    :return: if vm size is premium storage compatible
    """
    if any([vm_size.lower().endswith(x)
            for x in _PREMIUM_STORAGE_INSTANCE_SUFFIXES]):
        return True
    elif any([vm_size.lower().startswith(x)
              for x in _PREMIUM_STORAGE_INSTANCE_PREFIXES]):
        return True
    return False


def is_platform_image(config, vm_config=None):
    # type (dict, PoolVmConfiguration) -> bool
    """If pool is on a platform image
    :param dict config: configuration object
    :param bool vm_config: vm configuration
    :rtype: bool
    :return: if on platform image
    """
    if vm_config is None:
        vm_config = _populate_pool_vm_configuration(config)
    return isinstance(vm_config, PoolVmPlatformImageSettings)


def temp_disk_mountpoint(config, offer=None):
    # type: (dict) -> str
    """Get temporary disk mountpoint
    :param dict config: configuration object
    :param str offer: offer override
    :rtype: str
    :return: temporary disk mount point
    """
    if offer is None:
        vmconfig = _populate_pool_vm_configuration(config)
        if is_platform_image(config, vm_config=vmconfig):
            offer = pool_offer(config, lower=True)
        else:
            if vmconfig.node_agent.lower().startswith('batch.node.ubuntu'):
                offer = 'ubuntu'
            elif vmconfig.node_agent.lower().startswith('batch.node.windows'):
                offer = 'windowsserver'
            else:
                offer = '!ubuntu'
    else:
        offer = offer.lower()
    if offer.startswith('ubuntu'):
        return '/mnt'
    elif offer.startswith('windows'):
        return 'D:\\batch'
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


def raw(config):
    # type: (dict) -> bool
    """Get raw setting
    :param dict config: configuration object
    :rtype: bool
    :return: raw setting
    """
    return config['_raw']


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


def _pool_vm_count(config, conf=None):
    # type: (dict, dict) -> PoolVmCountSettings
    """Get Pool vm count settings
    :param dict config: configuration object
    :param dict conf: vm_count object
    :rtype: PoolVmCountSettings
    :return: pool vm count settings
    """
    if conf is None:
        conf = pool_specification(config)['vm_count']
    return PoolVmCountSettings(
        dedicated=_kv_read(conf, 'dedicated', 0),
        low_priority=_kv_read(conf, 'low_priority', 0),
    )


def pool_vm_configuration(config, key):
    # type: (dict, str) -> dict
    """Get Pool VM configuration
    :param dict config: configuration object
    :param str key: vm config key
    :rtype: str
    :return: pool vm config
    """
    try:
        conf = _kv_read_checked(
            config['pool_specification']['vm_configuration'], key)
    except KeyError:
        conf = None
    if conf is None:
        return config['pool_specification']
    else:
        return conf


def _populate_pool_vm_configuration(config):
    # type: (dict) -> dict
    """Populate Pool VM configuration
    :param dict config: configuration object
    :rtype: PoolVmPlatformImageSettings or PoolVmCustomImageSettings
    :return: pool vm config
    """
    conf = pool_vm_configuration(config, 'platform_image')
    if 'publisher' in conf:
        publisher = conf['publisher'].lower()
        offer = conf['offer'].lower()
        sku = str(conf['sku']).lower()
        # auto convert windows native if detected
        if ((publisher == 'microsoftwindowsserver' and
             offer == 'windowsserver' and
             sku == '2016-datacenter-with-containers') or
                (publisher == 'microsoftwindowsserver' and
                 offer == 'windowsserversemiannual' and
                 sku == 'datacenter-core-1709-with-containers-smalldisk')):
            vm_config = PoolVmPlatformImageSettings(
                publisher=publisher,
                offer=offer,
                sku=sku,
                version=_kv_read_checked(conf, 'version', default='latest'),
                native=True,
                license_type=_kv_read_checked(conf, 'license_type'),
            )
        else:
            vm_config = PoolVmPlatformImageSettings(
                publisher=publisher,
                offer=offer,
                sku=sku,
                version=_kv_read_checked(conf, 'version', default='latest'),
                native=False,
                license_type=None,
            )
        # TODO re-enable this when platform support is available
        # auto convert vm config to native if specified
        if False:  # _kv_read(conf, 'native', default=False):
            if (vm_config.publisher == 'canonical' and
                    vm_config.offer == 'ubuntuserver' and
                    vm_config.sku == '16.04-lts'):
                vm_config = PoolVmPlatformImageSettings(
                    publisher='microsoft-azure-batch',
                    offer='ubuntu-server-container-preview',
                    sku='16-04-lts',
                    version='latest',
                    native=True,
                    license_type=None,
                )
            elif (vm_config.publisher == 'openlogic' and
                  vm_config.offer == 'centos' and
                  vm_config.sku == '7.3'):
                vm_config = PoolVmPlatformImageSettings(
                    publisher='microsoft-azure-batch',
                    offer='centos-container-preview',
                    sku='7-3',
                    version='latest',
                    native=True,
                    license_type=None,
                )
            elif (vm_config.publisher == 'openlogic' and
                  vm_config.offer == 'centos-hpc' and
                  vm_config.sku == '7.3'):
                vm_config = PoolVmPlatformImageSettings(
                    publisher='microsoft-azure-batch',
                    offer='centos-container-rdma-preview',
                    sku='7-3',
                    version='latest',
                    native=True,
                    license_type=None,
                )
        return vm_config
    else:
        conf = pool_vm_configuration(config, 'custom_image')
        node_agent = conf['node_agent'].lower()
        if node_agent == 'batch.node.windows amd64':
            native = True
            license_type = _kv_read_checked(conf, 'license_type')
        else:
            native = _kv_read(conf, 'native', default=False)
            license_type = None
        return PoolVmCustomImageSettings(
            arm_image_id=_kv_read_checked(conf, 'arm_image_id'),
            node_agent=node_agent,
            native=native,
            license_type=license_type,
        )


def pool_autoscale_settings(config):
    # type: (dict) -> PoolAutoscaleSettings
    """Get Pool autoscale settings
    :param dict config: configuration object
    :rtype: PoolAutoscaleSettings
    :return: pool autoscale settings from specification
    """
    conf = pool_specification(config)
    conf = _kv_read_checked(conf, 'autoscale', {})
    ei = _kv_read_checked(conf, 'evaluation_interval')
    if util.is_not_empty(ei):
        ei = util.convert_string_to_timedelta(ei)
    else:
        ei = datetime.timedelta(minutes=15)
    scenconf = _kv_read_checked(conf, 'scenario')
    if scenconf is not None:
        mvc = _kv_read_checked(scenconf, 'maximum_vm_count')
        if mvc is None:
            raise ValueError('maximum_vm_count must be specified')
        ndo = _kv_read_checked(
            scenconf, 'node_deallocation_option', 'taskcompletion')
        if (ndo is not None and
                ndo not in (
                    'requeue', 'terminate', 'taskcompletion', 'retaineddata')):
            raise ValueError(
                'invalid node_deallocation_option: {}'.format(ndo))
        sli = _kv_read_checked(scenconf, 'sample_lookback_interval')
        if util.is_not_empty(sli):
            sli = util.convert_string_to_timedelta(sli)
        else:
            sli = datetime.timedelta(minutes=10)
        scenario = PoolAutoscaleScenarioSettings(
            name=_kv_read_checked(scenconf, 'name').lower(),
            maximum_vm_count=_pool_vm_count(config, conf=mvc),
            node_deallocation_option=ndo,
            sample_lookback_interval=sli,
            required_sample_percentage=_kv_read(
                scenconf, 'required_sample_percentage', 70),
            rebalance_preemption_percentage=_kv_read(
                scenconf, 'rebalance_preemption_percentage', None),
            bias_last_sample=_kv_read(
                scenconf, 'bias_last_sample', True),
            bias_node_type=_kv_read_checked(
                scenconf, 'bias_node_type', 'auto').lower(),
        )
    else:
        scenario = None
    return PoolAutoscaleSettings(
        evaluation_interval=ei,
        formula=_kv_read_checked(conf, 'formula'),
        scenario=scenario,
    )


def is_pool_autoscale_enabled(config, pas=None):
    # type: (dict, PoolAutoscaleSettings) -> bool
    """Check if pool autoscale is enabled
    :param dict config: configuration object
    :param PoolAutoscaleSettings pas: pool autoscale settings
    :rtype: bool
    :return: if pool autoscale is enabled
    """
    if pas is None:
        pas = pool_autoscale_settings(config)
    return util.is_not_empty(pas.formula) or pas.scenario is not None


def pool_settings(config):
    # type: (dict) -> PoolSettings
    """Get Pool settings
    :param dict config: configuration object
    :rtype: PoolSettings
    :return: pool settings from specification
    """
    conf = pool_specification(config)
    max_tasks_per_node = _kv_read(conf, 'max_tasks_per_node', default=1)
    resize_timeout = _kv_read_checked(conf, 'resize_timeout')
    if util.is_not_empty(resize_timeout):
        resize_timeout = util.convert_string_to_timedelta(resize_timeout)
    else:
        resize_timeout = None
    inter_node_communication_enabled = _kv_read(
        conf, 'inter_node_communication_enabled', default=False)
    reboot_on_start_task_failed = _kv_read(
        conf, 'reboot_on_start_task_failed', default=False)
    attempt_recovery_on_unusable = _kv_read(
        conf, 'attempt_recovery_on_unusable', default=False)
    block_until_all_gr = _kv_read(
        conf, 'block_until_all_global_resources_loaded', default=True)
    transfer_files_on_pool_creation = _kv_read(
        conf, 'transfer_files_on_pool_creation', default=False)
    try:
        input_data = conf['input_data']
        if util.is_none_or_empty(input_data):
            raise KeyError()
    except KeyError:
        input_data = None
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
    # ssh settings
    try:
        sshconf = conf['ssh']
        ssh_username = _kv_read_checked(sshconf, 'username')
        if util.is_none_or_empty(ssh_username):
            raise KeyError()
    except KeyError:
        ssh_username = None
        ssh_expiry_days = None
        ssh_public_key = None
        ssh_public_key_data = None
        ssh_private_key = None
        ssh_gen_docker_tunnel = None
        ssh_gen_file_path = '.'
        ssh_hpn = None
    else:
        ssh_expiry_days = _kv_read(sshconf, 'expiry_days', 30)
        if ssh_expiry_days <= 0:
            ssh_expiry_days = 30
        ssh_public_key = _kv_read_checked(sshconf, 'ssh_public_key')
        if util.is_not_empty(ssh_public_key):
            ssh_public_key = pathlib.Path(ssh_public_key)
        ssh_public_key_data = _kv_read_checked(sshconf, 'ssh_public_key_data')
        ssh_private_key = _kv_read_checked(sshconf, 'ssh_private_key')
        if util.is_not_empty(ssh_private_key):
            ssh_private_key = pathlib.Path(ssh_private_key)
        if (ssh_public_key is not None and
                util.is_not_empty(ssh_public_key_data)):
            raise ValueError(
                'cannot specify both an SSH public key file and data')
        if (ssh_public_key is None and
                util.is_none_or_empty(ssh_public_key_data) and
                ssh_private_key is not None):
            raise ValueError(
                'cannot specify an SSH private key with no public '
                'key specified')
        ssh_gen_docker_tunnel = _kv_read(
            sshconf, 'generate_docker_tunnel_script', False)
        ssh_gen_file_path = _kv_read_checked(
            sshconf, 'generated_file_export_path', '.')
        ssh_hpn = _kv_read(sshconf, 'hpn_server_swap', False)
    # rdp settings
    try:
        rdpconf = conf['rdp']
        rdp_username = _kv_read_checked(rdpconf, 'username')
        if util.is_none_or_empty(rdp_username):
            raise KeyError()
    except KeyError:
        rdp_username = None
        rdp_expiry_days = None
        rdp_password = None
    else:
        rdp_expiry_days = _kv_read(rdpconf, 'expiry_days', 30)
        if rdp_expiry_days <= 0:
            rdp_expiry_days = 30
        rdp_password = _kv_read_checked(rdpconf, 'password')
    # remote access control
    rac = _kv_read_checked(conf, 'remote_access_control', default={})
    rac = RemoteAccessControl(
        starting_port=_kv_read(rac, 'starting_port', default=49000),
        backend_port='22' if ssh_username is not None else '3389',
        protocol='tcp',
        allow=_kv_read_checked(rac, 'allow'),
        deny=_kv_read_checked(rac, 'deny'),
    )
    if (rac.starting_port < 1 or
            (rac.starting_port > 49000 and rac.starting_port <= 55000) or
            rac.starting_port > 64536):
        raise ValueError('starting_port is invalid or in a reserved range')
    # gpu driver
    try:
        gpu_driver = _kv_read_checked(conf['gpu']['nvidia_driver'], 'source')
    except KeyError:
        gpu_driver = None
    # additional node prep
    addl_node_prep = _kv_read_checked(
        conf, 'additional_node_prep_commands', default={})
    additional_node_prep_commands_pre = _kv_read_checked(
        addl_node_prep, 'pre', default=[])
    additional_node_prep_commands_post = _kv_read_checked(
        addl_node_prep, 'post', default=[])
    # certificates
    certdict = _kv_read_checked(conf, 'certificates', default={})
    certs = []
    for tp in certdict:
        visibility = []
        for vis in certdict[tp]['visibility']:
            if vis == 'remote_user':
                visibility.append(
                    batchmodels.CertificateVisibility.remote_user)
            elif vis == 'start_task':
                visibility.append(batchmodels.CertificateVisibility.start_task)
            elif vis == 'task':
                visibility.append(batchmodels.CertificateVisibility.task)
        certs.append(batchmodels.CertificateReference(
            thumbprint=tp, thumbprint_algorithm='sha1',
            visibility=visibility
        ))
    return PoolSettings(
        id=conf['id'],
        vm_size=conf['vm_size'].lower(),  # normalize
        vm_count=_pool_vm_count(config),
        resize_timeout=resize_timeout,
        max_tasks_per_node=max_tasks_per_node,
        inter_node_communication_enabled=inter_node_communication_enabled,
        vm_configuration=_populate_pool_vm_configuration(config),
        reboot_on_start_task_failed=reboot_on_start_task_failed,
        attempt_recovery_on_unusable=attempt_recovery_on_unusable,
        block_until_all_global_resources_loaded=block_until_all_gr,
        transfer_files_on_pool_creation=transfer_files_on_pool_creation,
        input_data=input_data,
        resource_files=resource_files,
        ssh=SSHSettings(
            username=ssh_username,
            expiry_days=ssh_expiry_days,
            ssh_public_key=ssh_public_key,
            ssh_public_key_data=ssh_public_key_data,
            ssh_private_key=ssh_private_key,
            generate_docker_tunnel_script=ssh_gen_docker_tunnel,
            generated_file_export_path=ssh_gen_file_path,
            hpn_server_swap=ssh_hpn,
        ),
        rdp=RDPSettings(
            username=rdp_username,
            expiry_days=rdp_expiry_days,
            password=rdp_password,
        ),
        gpu_driver=gpu_driver,
        additional_node_prep_commands_pre=additional_node_prep_commands_pre,
        additional_node_prep_commands_post=additional_node_prep_commands_post,
        virtual_network=virtual_network_settings(
            conf,
            default_existing_ok=True,
            default_create_nonexistant=False,
        ),
        autoscale=pool_autoscale_settings(config),
        node_fill_type=_kv_read_checked(conf, 'node_fill_type'),
        remote_access_control=rac,
        certificates=certs,
    )


def set_attempt_recovery_on_unusable(config, flag):
    # type: (dict, bool) -> None
    """Set attempt recovery on unusable setting
    :param dict config: configuration object
    :param bool flag: flag to set
    """
    config['pool_specification']['attempt_recovery_on_unusable'] = flag


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


def pool_publisher(config, lower=False):
    # type: (dict, bool) -> str
    """Get Pool publisher
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: str
    :return: pool publisher
    """
    conf = pool_vm_configuration(config, 'platform_image')
    pub = _kv_read_checked(conf, 'publisher')
    return pub.lower() if lower and util.is_not_empty(pub) else pub


def pool_offer(config, lower=False):
    # type: (dict, bool) -> str
    """Get Pool offer
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: str
    :return: pool offer
    """
    conf = pool_vm_configuration(config, 'platform_image')
    offer = _kv_read_checked(conf, 'offer')
    return offer.lower() if lower and util.is_not_empty(offer) else offer


def pool_sku(config, lower=False):
    # type: (dict, bool) -> str
    """Get Pool sku
    :param dict config: configuration object
    :param bool lower: lowercase return
    :rtype: str
    :return: pool sku
    """
    conf = pool_vm_configuration(config, 'platform_image')
    try:
        sku = str(conf['sku'])
        if util.is_none_or_empty(sku):
            raise KeyError()
    except (KeyError, TypeError):
        sku = None
    return sku.lower() if lower and util.is_not_empty(sku) else sku


def pool_custom_image_node_agent(config):
    # type: (dict) -> str
    """Get Pool node agent from custom image
    :param dict config: configuration object
    :rtype: str
    :return: pool node agent
    """
    conf = pool_vm_configuration(config, 'custom_image')
    return _kv_read_checked(conf, 'node_agent')


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
        conf, service, default_endpoint=None, default_token_cache_file=None):
    # type: (dict, str) -> AADSettings
    """Retrieve AAD Settings
    :param dict conf: credentials configuration object
    :param str service: credentials section service name
    :param str default_endpoint: default endpoint
    :param str default_token_cache_file: default token cache file
    :rtype: AADSettings
    :return: AAD settings
    """
    super_aad = _kv_read_checked(conf, 'aad', default={})
    if service in conf:
        service_aad = _kv_read_checked(conf[service], 'aad', default={})
    else:
        service_aad = {}
    if util.is_not_empty(super_aad) or util.is_not_empty(service_aad):
        aad_directory_id = (
            _kv_read_checked(service_aad, 'directory_id') or
            _kv_read_checked(super_aad, 'directory_id')
        )
        aad_application_id = (
            _kv_read_checked(service_aad, 'application_id') or
            _kv_read_checked(super_aad, 'application_id')
        )
        aad_auth_key = (
            _kv_read_checked(service_aad, 'auth_key') or
            _kv_read_checked(super_aad, 'auth_key')
        )
        aad_user = (
            _kv_read_checked(service_aad, 'user') or
            _kv_read_checked(super_aad, 'user')
        )
        aad_password = (
            _kv_read_checked(service_aad, 'password') or
            _kv_read_checked(super_aad, 'password')
        )
        aad_cert_private_key = (
            _kv_read_checked(service_aad, 'rsa_private_key_pem') or
            _kv_read_checked(super_aad, 'rsa_private_key_pem')
        )
        aad_cert_thumbprint = (
            _kv_read_checked(service_aad, 'x509_cert_sha1_thumbprint') or
            _kv_read_checked(super_aad, 'x509_cert_sha1_thumbprint')
        )
        aad_authority_url = (
            _kv_read_checked(service_aad, 'authority_url') or
            _kv_read_checked(super_aad, 'authority_url')
        )
        aad_endpoint = _kv_read_checked(
            service_aad, 'endpoint', default=default_endpoint)
        token_cache = _kv_read_checked(service_aad, 'token_cache', default={})
        if _kv_read(token_cache, 'eanbled', default=True):
            token_cache_file = _kv_read_checked(
                token_cache, 'filename', default=default_token_cache_file)
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
            authority_url=aad_authority_url,
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
            authority_url=None,
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
    return KeyVaultCredentialsSettings(
        aad=_aad_credentials(
            config['credentials'],
            'keyvault',
            default_endpoint='https://vault.azure.net',
            default_token_cache_file=(
                '.batch_shipyard_aad_keyvault_token.json'
            ),
        ),
        keyvault_uri=_kv_read_checked(conf, 'uri'),
        keyvault_credentials_secret_id=_kv_read_checked(
            conf, 'credentials_secret_id'),
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
    return ManagementCredentialsSettings(
        aad=_aad_credentials(
            config['credentials'],
            'management',
            default_endpoint='https://management.azure.com/',
            default_token_cache_file=(
                '.batch_shipyard_aad_management_token.json'
            ),
        ),
        subscription_id=_kv_read_checked(conf, 'subscription_id'),
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
    resource_group = _kv_read_checked(conf, 'resource_group')
    test_cluster = _kv_read(conf, 'test_cluster', False)
    # get subscription id from management section
    try:
        subscription_id = _kv_read_checked(
            config['credentials']['management'], 'subscription_id')
    except (KeyError, TypeError):
        subscription_id = None
    # parse location from url
    tmp = account_service_url.split('.')
    location = tmp[1]
    # parse account name from url
    if test_cluster:
        account = account_service_url.split('/')[-1]
    else:
        account = tmp[0].split('/')[-1]
    return BatchCredentialsSettings(
        aad=_aad_credentials(
            config['credentials'],
            'batch',
            default_endpoint='https://batch.core.windows.net/',
            default_token_cache_file=(
                '.batch_shipyard_aad_batch_token.json'
            ),
        ),
        account=account,
        account_key=account_key,
        account_service_url=conf['account_service_url'],
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


def credentials_storage_aad(config):
    # type: (dict) -> AADSettings
    """Get storage AAD credentials
    :param dict config: configuration object
    :rtype: AADSettings
    :return: storage aad settings
    """
    if 'aad' in config['credentials']['storage']:
        return _aad_credentials(
            config['credentials'],
            'storage',
            default_endpoint='https://management.azure.com/',
            default_token_cache_file=(
                '.batch_shipyard_aad_storage_token.json'
            ),
        )
    else:
        return _aad_credentials(
            config['credentials'],
            'management',
            default_endpoint='https://management.azure.com/',
            default_token_cache_file=(
                '.batch_shipyard_aad_storage_token.json'
            ),
        )


def credentials_storage(config, ssel):
    # type: (dict, str) -> StorageCredentialsSettings
    """Get specific storage credentials
    :param dict config: configuration object
    :param str ssel: storage selector link
    :rtype: StorageCredentialsSettings
    :return: storage creds
    """
    try:
        conf = config['credentials']['storage'][ssel]
    except KeyError:
        raise ValueError(
            ('Could not find storage account alias {} in credentials:storage '
             'configuration. Please ensure the storage account alias '
             'exists.').format(ssel))
    return StorageCredentialsSettings(
        account=conf['account'],
        account_key=_kv_read_checked(conf, 'account_key'),
        endpoint=_kv_read_checked(
            conf, 'endpoint', default='core.windows.net'),
        resource_group=_kv_read_checked(conf, 'resource_group'),
    )


def iterate_storage_credentials(config):
    # type: (dict) -> str
    """Iterate storage credential storage select links
    :param dict config: configuration object
    :rtype: str
    :return: storage selector link
    """
    for conf in config['credentials']['storage']:
        if conf == 'aad':
            continue
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


def set_credentials_storage_account(config, ssel, sakey, ep=None):
    # type: (dict, str, str, str) -> None
    """Set Storage account key and endpoint
    :param dict config: configuration object
    :param str ssel: storage selector link
    :param str sakey: storage account key
    :param str ep: endpoint
    """
    config['credentials']['storage'][ssel]['account_key'] = sakey
    if util.is_not_empty(ep):
        config['credentials']['storage'][ssel]['endpoint'] = ep


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


def singularity_registry_login(config, server):
    # type: (dict, str) -> tuple
    """Get singularity registry login settings
    :param dict config: configuration object
    :param str server: credentials for login server to retrieve
    :rtype: tuple
    :return: (user, pw)
    """
    try:
        user = config['credentials']['singularity_registry'][
            server]['username']
        pw = config['credentials']['singularity_registry'][
            server]['password']
        if util.is_none_or_empty(user) or util.is_none_or_empty(pw):
            raise KeyError()
    except KeyError:
        user = None
        pw = None
    return user, pw


def credentials_iterate_registry_servers(config, is_docker):
    # type: (dict, bool) -> str
    """Iterate registry servers
    :param dict config: configuration object
    :param bool is_docker: is a docker registry
    :rtype: str
    :return: registry server name
    """
    if is_docker:
        kind = 'docker_registry'
    else:
        kind = 'singularity_registry'
    try:
        for conf in config['credentials'][kind]:
            yield conf
    except KeyError:
        pass


def credentials_registry_password_secret_id(config, link, is_docker):
    # type: (dict, str, bool) -> str
    """Get registry password KeyVault Secret Id
    :param dict config: configuration object
    :param str link: registry link
    :param bool is_docker: is docker registry
    :rtype: str
    :return: keyvault secret id
    """
    if is_docker:
        kind = 'docker_registry'
    else:
        kind = 'singularity_registry'
    try:
        secid = config['credentials'][kind][link][
            'password_keyvault_secret_id']
        if util.is_none_or_empty(secid):
            raise KeyError()
    except KeyError:
        return None
    return secid


def set_credentials_registry_password(config, link, is_docker, password):
    # type: (dict, str, bool, str) -> None
    """Set registry password
    :param dict config: configuration object
    :param str link: registry link
    :param bool is_docker: is docker registry
    :param str password: password
    """
    if is_docker:
        kind = 'docker_registry'
    else:
        kind = 'singularity_registry'
    config['credentials'][kind][link]['password'] = password


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


def docker_registries(config):
    # type: (dict) -> list
    """Get Docker registries specified
    :param dict config: configuration object
    :rtype: list
    :return: list of batchmodels.ContainerRegistry objects
    """
    servers = []
    try:
        servers.extend(
            config['global_resources']['additional_registries']['docker'])
    except KeyError:
        pass
    # parse images for servers
    images = global_resources_docker_images(config)
    for image in images:
        tmp = image.split('/')
        if len(tmp) > 1:
            if '.' in tmp[0] or ':' in tmp[0] and tmp[0] != 'localhost':
                servers.append(tmp[0])
    # create unique set
    servers = set(servers)
    # get login info for each registry
    registries = []
    # add docker hub if found
    hubuser, hubpw = docker_registry_login(config, 'hub')
    if util.is_not_empty(hubuser) or util.is_not_empty(hubpw):
        registries.append(
            batchmodels.ContainerRegistry(
                registry_server=None,
                user_name=hubuser,
                password=hubpw,
            )
        )
    del hubuser
    del hubpw
    for server in servers:
        user, pw = docker_registry_login(config, server)
        if util.is_none_or_empty(user) or util.is_none_or_empty(pw):
            # registries can be public with a specified server
            continue
        registries.append(
            batchmodels.ContainerRegistry(
                registry_server=server,
                user_name=user,
                password=pw,
            )
        )
    return registries


def singularity_registries(config):
    # type: (dict) -> list
    """Get Singularity registries specified
    :param dict config: configuration object
    :rtype: list
    :return: list of batchmodels.ContainerRegistry objects
    """
    servers = []
    try:
        servers.extend(
            config['global_resources']['additional_registries']['singularity'])
    except KeyError:
        pass
    # parse images for servers
    images = global_resources_singularity_images(config)
    for image in images:
        tmp = image.split('/')
        if len(tmp) > 1:
            if '.' in tmp[0] or ':' in tmp[0] and tmp[0] != 'localhost':
                servers.append(tmp[0])
    # get login info for each registry
    registries = []
    # add docker hub if found and no servers are specified
    if len(servers) == 0:
        hubuser, hubpw = docker_registry_login(config, 'hub')
        if util.is_not_empty(hubuser) or util.is_not_empty(hubpw):
            registries.append(
                batchmodels.ContainerRegistry(
                    registry_server=None,
                    user_name=hubuser,
                    password=hubpw,
                )
            )
        del hubuser
        del hubpw
    for server in servers:
        user, pw = singularity_registry_login(config, server)
        if util.is_none_or_empty(user) or util.is_none_or_empty(pw):
            # registries can be public with a specified server
            continue
        registries.append(
            batchmodels.ContainerRegistry(
                registry_server=server,
                user_name=user,
                password=pw,
            )
        )
    # TODO currently limit to a single server due to env var limit
    if len(registries) > 1:
        raise ValueError(
            'cannot currently specify more than 1 Singularity registry server')
    return registries


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
        concurrent_source_downloads = conf['concurrent_source_downloads']
        if concurrent_source_downloads is None:
            raise KeyError()
    except KeyError:
        concurrent_source_downloads = 10
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
    pool_vm_count = _pool_vm_count(config)
    total_vm_count = pool_vm_count.dedicated + pool_vm_count.low_priority
    try:
        p2p_direct_download_seed_bias = conf['direct_download_seed_bias']
        if (p2p_direct_download_seed_bias is None or
                p2p_direct_download_seed_bias < 1):
            raise KeyError()
    except KeyError:
        p2p_direct_download_seed_bias = total_vm_count // 10
        if p2p_direct_download_seed_bias < 1:
            p2p_direct_download_seed_bias = 1
    return DataReplicationSettings(
        peer_to_peer=PeerToPeerSettings(
            enabled=p2p_enabled,
            compression=p2p_compression,
            direct_download_seed_bias=p2p_direct_download_seed_bias
        ),
        concurrent_source_downloads=concurrent_source_downloads,
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


def global_resources_singularity_images(config):
    # type: (dict) -> list
    """Get list of singularity images
    :param dict config: configuration object
    :rtype: list
    :return: singularity images
    """
    try:
        images = config['global_resources']['singularity_images']
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
    source = _kv_read_checked(conf, 'source', default={})
    path = _kv_read_checked(source, 'path')
    if util.is_none_or_empty(path):
        raise ValueError('global resource files path is invalid')
    return SourceSettings(
        path=path,
        include=_kv_read_checked(source, 'include'),
        exclude=_kv_read_checked(source, 'exclude'),
    )


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
    data_transfer = _kv_read_checked(conf, 'data_transfer', default={})
    method = _kv_read_checked(data_transfer, 'method')
    if util.is_none_or_empty(method):
        if storage is None:
            raise RuntimeError(
                'no transfer method specified for data transfer of '
                'source: {} to {} rdp={}'.format(
                    files_source_settings(fdict).path, shared, rdp))
        else:
            method = None
    else:
        method = method.lower()
    ssh_eo = _kv_read_checked(
        data_transfer, 'scp_ssh_extra_options', default='')
    rsync_eo = _kv_read_checked(
        data_transfer, 'rsync_extra_options', default='')
    try:
        mpt = data_transfer['max_parallel_transfers_per_node']
        if mpt is not None and mpt <= 0:
            raise KeyError()
    except KeyError:
        mpt = None
    # ensure valid mpt number
    if mpt is None:
        mpt = 1
    try:
        split = data_transfer['split_files_megabytes']
        if split is not None and split <= 0:
            raise KeyError()
        # convert to bytes
        if split is not None:
            split <<= 20
    except KeyError:
        split = None
    ssh_private_key = _kv_read_checked(data_transfer, 'ssh_private_key')
    if util.is_not_empty(ssh_private_key):
        ssh_private_key = pathlib.Path(ssh_private_key)
    return DestinationSettings(
        storage_account_settings=storage,
        shared_data_volume=shared,
        relative_destination_path=rdp,
        data_transfer=DataTransferSettings(
            is_file_share=data_is_file_share(data_transfer),
            remote_path=data_remote_path(data_transfer),
            blobxfer_extra_options=data_blobxfer_extra_options(data_transfer),
            method=method,
            ssh_private_key=ssh_private_key,
            scp_ssh_extra_options=ssh_eo,
            rsync_extra_options=rsync_eo,
            split_files_megabytes=split,
            max_parallel_transfers_per_node=mpt,
        )
    )


def _global_resources_volumes(config):
    # type: (dict) -> dict
    """Get global resources volumes dictionary
    :param dict config: configuration object
    :rtype: dict
    :return: volumes
    """
    try:
        vols = config['global_resources']['volumes']
        if util.is_none_or_empty(vols):
            raise KeyError()
    except KeyError:
        vols = {}
    return vols


def global_resources_data_volumes(config):
    # type: (dict) -> dict
    """Get data volumes dictionary
    :param dict config: configuration object
    :rtype: dict
    :return: data volumes
    """
    try:
        dv = _global_resources_volumes(config)['data_volumes']
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
        sdv = _global_resources_volumes(config)['shared_data_volumes']
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
        if is_shared_data_volume_custom_linux_mount(sdv, sdvkey):
            mo = sdv[sdvkey]['fstab_entry']['fs_mntops']
        else:
            mo = sdv[sdvkey]['mount_options']
    except KeyError:
        mo = None
    return mo


def azure_storage_account_settings(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get azure storage account link
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


def azure_blob_container_name(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get azure blob container name
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: azure blob container name
    """
    return sdv[sdvkey]['azure_blob_container_name']


def azure_file_host_mount_path(storage_account_name, share_name, is_windows):
    # type: (str, str, bool) -> str
    """Get azure file share host mount path
    :param str storage_account_name: storage account name
    :param str share_name: file share name
    :param bool is_windows: is windows
    :rtype: str
    :return: host mount path for azure file share
    """
    return '{root}{sep}azfile-{sa}-{share}'.format(
        root=get_host_mounts_path(is_windows),
        sep='\\' if is_windows else '/',
        sa=storage_account_name,
        share=share_name)


def azure_blob_host_mount_path(storage_account_name, container_name):
    # type: (str, str) -> str
    """Get azure blob container host mount path
    :param str storage_account_name: storage account name
    :param str container_name: container name
    :rtype: str
    :return: host mount path for azure file share
    """
    return '{root}/azblob-{sa}-{cont}'.format(
        root=get_host_mounts_path(False),
        sa=storage_account_name,
        cont=container_name)


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


def custom_linux_mount_fstab_options(sdv, sdvkey):
    # type: (dict, str) -> str
    """Get custom mount fstab options
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: str
    :return: custom mount fstab options
    """
    try:
        fstab = sdv[sdvkey]['fstab_entry']
        if util.is_none_or_empty(fstab):
            raise KeyError()
        fs_spec = _kv_read_checked(fstab, 'fs_spec')
        if util.is_none_or_empty(fs_spec):
            raise ValueError(
                ('fs_spec for fstab_entry of custom mount {} is '
                 'invalid').format(sdvkey))
        fs_vfstype = _kv_read_checked(fstab, 'fs_vfstype')
        if util.is_none_or_empty(fs_vfstype):
            raise ValueError(
                ('fs_vfstype for fstab_entry of custom mount {} is '
                 'invalid').format(sdvkey))
        fs_mntops = _kv_read_checked(fstab, 'fs_mntops', default='defaults')
        fs_freq = _kv_read(fstab, 'fs_freq', default=0)
        fs_passno = _kv_read(fstab, 'fs_passno', default=0)
    except KeyError:
        return None
    return CustomMountFstabSettings(
        fs_spec=fs_spec,
        fs_vfstype=fs_vfstype,
        fs_mntops=fs_mntops,
        fs_freq=fs_freq,
        fs_passno=fs_passno,
    )


def is_shared_data_volume_azure_file(sdv, sdvkey):
    # type: (dict, str) -> bool
    """Determine if shared data volume is an azure file share
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: bool
    :return: if shared data volume is azure file
    """
    return shared_data_volume_driver(sdv, sdvkey).lower() == 'azurefile'


def is_shared_data_volume_azure_blob(sdv, sdvkey):
    # type: (dict, str) -> bool
    """Determine if shared data volume is an azure blob container via fuse
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: bool
    :return: if shared data volume is azure blob
    """
    return shared_data_volume_driver(sdv, sdvkey).lower() == 'azureblob'


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


def is_shared_data_volume_custom_linux_mount(sdv, sdvkey):
    # type: (dict, str) -> bool
    """Determine if shared data volume is a custom linux mount
    :param dict sdv: shared_data_volume configuration object
    :param str sdvkey: key to sdv
    :rtype: bool
    :return: if shared data volume is a custom linux mount
    """
    return (
        shared_data_volume_driver(sdv, sdvkey).lower() == 'custom_linux_mount'
    )


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


def data_remote_path(conf):
    # type: (dict) -> str
    """Retrieve remote path on Azure Storage for data transfer
    :param dict conf: configuration object
    :rtype: str
    :return: remote path
    """
    return _kv_read_checked(conf, 'remote_path')


def data_container_from_remote_path(conf, rp=None):
    # type: (dict, str) -> str
    """Get Container or File share name from remote path
    :param dict conf: configuration object
    :param str rp: remote path
    :rtype: str
    :return: container/fshare name
    """
    if rp is None:
        rp = data_remote_path(conf)
    if util.is_none_or_empty(rp):
        raise ValueError(
            'cannot derive container name from invalid remote_path')
    return rp.split('/')[0]


def data_local_path(conf, on_task, task_wd=True):
    # type: (dict, bool) -> str
    """Retrieve local path for data transfer
    :param dict conf: configuration object
    :param bool on_task: if input data is on the task spec
    :param bool task_wd: if path is not specified use task working dir, else
        use task dir
    :rtype: str
    :return: local path
    """
    try:
        dst = conf['local_path']
        if util.is_none_or_empty(dst):
            raise KeyError()
    except KeyError:
        if on_task:
            if task_wd:
                dst = '$AZ_BATCH_TASK_WORKING_DIR'
            else:
                dst = '$AZ_BATCH_TASK_DIR'
        else:
            raise
    return dst


def data_is_file_share(conf):
    # type: (dict) -> bool
    """Retrieve if data transfer originates/destined for file share
    :param dict conf: configuration object
    :rtype: bool
    :return: is Azure file share
    """
    return _kv_read(conf, 'is_file_share', default=False)


def data_blobxfer_extra_options(conf):
    # type: (dict) -> str
    """Retrieve input data blobxfer extra options
    :param dict conf: configuration object
    :rtype: str
    :return: blobxfer extra options
    """
    return _kv_read_checked(conf, 'blobxfer_extra_options', default='')


def data_include(conf):
    # type: (dict) -> str
    """Retrieve input data include filters
    :param dict conf: configuration object
    :rtype: str
    :return: include filters
    """
    return _kv_read_checked(conf, 'include', [])


def data_exclude(conf):
    # type: (dict) -> str
    """Retrieve input data exclude filters
    :param dict conf: configuration object
    :rtype: str
    :return: exclude filters
    """
    return _kv_read_checked(conf, 'exclude', [])


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


# JOBS SETTINGS
def job_specifications(config):
    # type: (dict) -> dict
    """Get job specifications config block
    :param dict config: configuration object
    :rtype: dict
    :return: job specifications
    """
    try:
        return config['job_specifications']
    except KeyError:
        raise ValueError(
            'job_specifications is not found or invalid, did you specify a '
            'jobs configuration file?')


def autogenerated_task_id_prefix(config):
    # type: (dict) -> str
    """Get the autogenerated task id prefix to use
    :param dict config: configuration object
    :rtype: str
    :return: auto-gen task id prefix
    """
    conf = _kv_read_checked(
        config['batch_shipyard'], 'autogenerated_task_id', {}
    )
    # do not use _kv_read_checked for prefix we want to allow empty string
    try:
        prefix = conf['prefix']
        if prefix is None:
            raise KeyError()
    except KeyError:
        prefix = 'task-'
    return prefix


def autogenerated_task_id_zfill(config):
    # type: (dict) -> int
    """Get the autogenerated task zfill setting to use
    :param dict config: configuration object
    :rtype: int
    :return: auto-gen task number zfill
    """
    conf = _kv_read_checked(
        config['batch_shipyard'], 'autogenerated_task_id', {}
    )
    return _kv_read(conf, 'zfill_width', 5)


def job_tasks(config, conf):
    # type: (dict, dict) -> list
    """Get all tasks for job
    :param dict config: configuration object
    :param dict conf: job configuration object
    :rtype: list
    :return: list of tasks
    """
    for _task in conf['tasks']:
        if 'task_factory' in _task:
            # get storage settings if applicable
            if 'file' in _task['task_factory']:
                az = _task['task_factory']['file']['azure_storage']
                drp = data_remote_path(az)
                tfstorage = TaskFactoryStorageSettings(
                    storage_settings=credentials_storage(
                        config, data_storage_account_settings(az)),
                    storage_link_name=az['storage_account_settings'],
                    container=data_container_from_remote_path(None, drp),
                    remote_path=drp,
                    is_file_share=data_is_file_share(az),
                    include=_kv_read_checked(az, 'include'),
                    exclude=_kv_read_checked(az, 'exclude'),
                )
            else:
                tfstorage = None
            for task in task_factory.generate_task(_task, tfstorage):
                task['##tfgen'] = True
                yield task
        else:
            yield _task


def job_id(conf):
    # type: (dict) -> str
    """Get job id of a job specification
    :param dict conf: job configuration object
    :rtype: str
    :return: job id
    """
    return conf['id']


def job_auto_complete(conf):
    # type: (dict) -> bool
    """Get job (and multi-instance) autocomplete setting
    :param dict conf: job configuration object
    :rtype: bool
    :return: job autocomplete
    """
    try:
        ac = conf['auto_complete']
    except KeyError:
        ac = False
    return ac


def job_auto_pool(conf):
    # type: (dict) -> PoolAutopoolSettings
    """Get job autopool setting
    :param dict conf: job configuration object
    :rtype: PoolAutopoolSettings
    :return: job autopool settings
    """
    ap = _kv_read_checked(conf, 'auto_pool')
    if ap is not None:
        return PoolAutopoolSettings(
            pool_lifetime=_kv_read_checked(
                ap, 'pool_lifetime', 'job').lower(),
            keep_alive=_kv_read(ap, 'keep_alive', False),
        )
    else:
        return None


def job_recurrence(conf):
    # type: (dict) -> JobRecurrenceSettings
    """Get job recurrence setting
    :param dict conf: job configuration object
    :rtype: JobRecurrenceSettings
    :return: job recurrence settings
    """
    rec = _kv_read_checked(conf, 'recurrence')
    if rec is not None:
        do_not_run_until = _kv_read_checked(
            rec['schedule'], 'do_not_run_until')
        if do_not_run_until is not None:
            do_not_run_until = dateutil.parser.parse(do_not_run_until)
        do_not_run_after = _kv_read_checked(
            rec['schedule'], 'do_not_run_after')
        if do_not_run_after is not None:
            do_not_run_after = dateutil.parser.parse(do_not_run_after)
        start_window = _kv_read_checked(rec['schedule'], 'start_window')
        if start_window is not None:
            start_window = util.convert_string_to_timedelta(start_window)
        recurrence_interval = util.convert_string_to_timedelta(
            _kv_read_checked(rec['schedule'], 'recurrence_interval')
        )
        jm = _kv_read_checked(rec, 'job_manager', {})
        return JobRecurrenceSettings(
            schedule=JobScheduleSettings(
                do_not_run_until=do_not_run_until,
                do_not_run_after=do_not_run_after,
                start_window=start_window,
                recurrence_interval=recurrence_interval,
            ),
            job_manager=JobManagerSettings(
                allow_low_priority_node=_kv_read(
                    jm, 'allow_low_priority_node', True),
                run_exclusive=_kv_read(jm, 'run_exclusive', False),
                monitor_task_completion=_kv_read(
                    jm, 'monitor_task_completion', False),
            )
        )
    else:
        return None


def job_priority(conf):
    # type: (dict) -> int
    """Get job priority setting
    :param dict conf: job configuration object
    :rtype: bool
    :return: job autocomplete
    """
    pri = _kv_read(conf, 'priority', 0)
    if pri < -1000 or pri > 1000:
        raise ValueError('job priority is invalid: {}'.format(pri))
    return pri


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


def job_max_wall_time(conf):
    # type: (dict) -> int
    """Get maximum wall time for any task of a job
    :param dict conf: job configuration object
    :rtype: datetime.timedelta
    :return: max wall time
    """
    max_wall_time = _kv_read_checked(conf, 'max_wall_time')
    if util.is_not_empty(max_wall_time):
        max_wall_time = util.convert_string_to_timedelta(max_wall_time)
    return max_wall_time


def job_allow_run_on_missing(conf):
    # type: (dict) -> int
    """Get allow task run on missing image
    :param dict conf: job configuration object
    :rtype: bool
    :return: allow run on missing image
    """
    try:
        allow = conf['allow_run_on_missing_image']
        if allow is None:
            raise KeyError()
    except KeyError:
        allow = False
    return allow


def job_has_merge_task(conf):
    # type: (dict) -> bool
    """Determines if job has a merge task
    :param dict conf: job configuration object
    :rtype: bool
    :return: job has merge task
    """
    try:
        merge = conf['merge_task']
    except KeyError:
        return False
    else:
        if any(x in merge for x in _FORBIDDEN_MERGE_TASK_PROPERTIES):
            raise ValueError(
                'merge_task has one or more forbidden properties: {}'.format(
                    _FORBIDDEN_MERGE_TASK_PROPERTIES))
    return True


def job_merge_task(conf):
    # type: (dict) -> dict
    """Gets merge task
    :param dict conf: job configuration object
    :rtype: dict
    :return: merge task
    """
    return conf['merge_task']


def has_depends_on_task(conf):
    # type: (dict) -> bool
    """Determines if task has task dependencies
    :param dict conf: task configuration object
    :rtype: bool
    :return: task has task dependencies
    """
    if ('depends_on' in conf and util.is_not_empty(conf['depends_on']) or
            'depends_on_range' in conf and
            util.is_not_empty(conf['depends_on_range'])):
        if (('id' not in conf or util.is_none_or_empty(conf['id'])) and
                ('##tfgen' not in conf or not conf['##tfgen'])):
            raise ValueError(
                'task id is not specified, but depends_on or '
                'depends_on_range is set')
        return True
    return False


def has_task_exit_condition_job_action(jobspec, conf):
    # type: (dict, dict) -> bool
    """Determines if task has task exit condition job action
    :param dict jobspec: job configuration object
    :param dict conf: task configuration object
    :rtype: bool
    :return: task has exit condition job action
    """
    try:
        conf['exit_conditions']['default']['exit_options']['job_action']
    except KeyError:
        try:
            jobspec['exit_conditions']['default']['exit_options']['job_action']
        except KeyError:
            return False
    return True


def is_multi_instance_task(conf):
    # type: (dict) -> bool
    """Determines if task is multi-isntance
    :param dict conf: task configuration object
    :rtype: bool
    :return: task is multi-instance
    """
    return 'multi_instance' in conf


def task_name(conf):
    # type: (dict) -> str
    """Get task name
    :param dict conf: task configuration object
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


def task_docker_image(conf):
    # type: (dict) -> str
    """Get docker image used by task
    :param dict conf: task configuration object
    :rtype: str
    :return: docker image used by task
    """
    return (
        _kv_read_checked(conf, 'docker_image') or
        _kv_read_checked(conf, 'image')
    )


def task_singularity_image(conf):
    # type: (dict) -> str
    """Get singularity image used by task
    :param dict conf: task configuration object
    :rtype: str
    :return: singularity image used by task
    """
    return _kv_read_checked(conf, 'singularity_image')


def set_task_name(conf, name):
    # type: (dict, str) -> None
    """Set task name
    :param dict conf: task configuration object
    :param str name: task name to set
    """
    conf['name'] = name


def task_id(conf):
    # type: (dict) -> str
    """Get task id
    :param dict conf: task configuration object
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
    :param dict conf: task configuration object
    :param str id: task id to set
    """
    conf['id'] = id


def task_settings(cloud_pool, config, poolconf, jobspec, conf):
    # type: (azure.batch.models.CloudPool, dict, PoolSettings, dict,
    #        dict) -> TaskSettings
    """Get task settings
    :param azure.batch.models.CloudPool cloud_pool: cloud pool object
    :param dict config: configuration dict
    :param PoolSettings poolconf: pool settings
    :param dict jobspec: job specification
    :param dict conf: task configuration object
    :rtype: TaskSettings
    :return: task settings
    """
    native = is_native_docker_pool(config, vm_config=poolconf.vm_configuration)
    is_windows = is_windows_pool(config, vm_config=poolconf.vm_configuration)
    # id must be populated by the time this function is invoked
    task_id = conf['id']
    if util.is_none_or_empty(task_id):
        raise ValueError('task id is invalid')
    # check task id length
    if len(task_id) > 64:
        raise ValueError('task id exceeds 64 characters')
    docker_image = task_docker_image(conf)
    singularity_image = _kv_read_checked(conf, 'singularity_image')
    if (util.is_none_or_empty(docker_image) and
            util.is_none_or_empty(singularity_image)):
        raise ValueError('Container image is unspecified or invalid')
    if (util.is_not_empty(docker_image) and
            util.is_not_empty(singularity_image)):
        raise ValueError(
            'Cannot specify both a Docker and Singularity image for a task')
    if util.is_not_empty(singularity_image) and native:
        raise ValueError(
            'Cannot run Singularity containers on native container '
            'support pools')
    if is_windows and util.is_not_empty(singularity_image):
        raise ValueError(
            'Cannot run Singularity containers on windows pools')
    # get some pool props
    publisher = None
    offer = None
    node_agent = None
    if cloud_pool is None:
        pool_id = poolconf.id
        vm_size = poolconf.vm_size
        inter_node_comm = poolconf.inter_node_communication_enabled
        is_custom_image = not is_platform_image(
            config, vm_config=poolconf.vm_configuration)
        if is_custom_image:
            node_agent = poolconf.vm_configuration.node_agent
        else:
            publisher = poolconf.vm_configuration.publisher.lower()
            offer = poolconf.vm_configuration.offer.lower()
    else:
        pool_id = cloud_pool.id
        vm_size = cloud_pool.vm_size.lower()
        inter_node_comm = cloud_pool.enable_inter_node_communication
        is_custom_image = util.is_not_empty(
            cloud_pool.virtual_machine_configuration.image_reference.
            virtual_machine_image_id)
        if is_custom_image:
            node_agent = cloud_pool.virtual_machine_configuration.\
                node_agent_sku_id.lower()
        else:
            publisher = cloud_pool.virtual_machine_configuration.\
                image_reference.publisher.lower()
            offer = cloud_pool.virtual_machine_configuration.\
                image_reference.offer.lower()
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
        if not (isinstance(depends_on_range[0], int) and
                isinstance(depends_on_range[1], int)):
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
    docker_exec_options = []
    singularity_cmd = None
    run_elevated = True
    if util.is_not_empty(docker_image):
        run_opts = _kv_read_checked(
            conf, 'additional_docker_run_options', default=[])
        if '--privileged' in run_opts:
            docker_exec_options.append('--privileged')
    else:
        run_opts = _kv_read_checked(
            conf, 'additional_singularity_options', default=[])
        singularity_execution = _kv_read_checked(
            conf, 'singularity_execution', default={})
        singularity_cmd = _kv_read_checked(
            singularity_execution, 'cmd', default='exec')
        run_elevated = _kv_read(
            singularity_execution, 'elevated', default=False)
        if singularity_cmd not in _SINGULARITY_COMMANDS:
            raise ValueError('singularity_cmd is invalid: {}'.format(
                singularity_cmd))
    # docker specific options
    name = None
    if util.is_not_empty(docker_image):
        # parse remove container option
        rm_container = _kv_read(conf, 'remove_container_after_exit')
        if rm_container is None:
            rm_container = _kv_read(
                jobspec, 'remove_container_after_exit', default=True)
        if rm_container and '--rm' not in run_opts:
            run_opts.append('--rm')
        del rm_container
        # parse /dev/shm option
        shm_size = (
            _kv_read(conf, 'shm_size') or
            _kv_read_checked(jobspec, 'shm_size')
        )
        if (util.is_not_empty(shm_size) and
                not any(x.startswith('--shm-size=') for x in run_opts)):
            run_opts.append('--shm-size={}'.format(shm_size))
        del shm_size
        # parse name option, if not specified use task id
        name = _kv_read_checked(conf, 'name')
        if util.is_none_or_empty(name):
            name = task_id
            set_task_name(conf, name)
        run_opts.append('--name {}'.format(name))
        # parse labels option
        labels = _kv_read_checked(conf, 'labels')
        if util.is_not_empty(labels):
            for label in labels:
                run_opts.append('-l {}'.format(label))
        del labels
        # parse ports option
        ports = _kv_read_checked(conf, 'ports')
        if util.is_not_empty(ports):
            for port in ports:
                run_opts.append('-p {}'.format(port))
        del ports
        # parse entrypoint
        entrypoint = _kv_read_checked(conf, 'entrypoint')
        if util.is_not_empty(entrypoint):
            run_opts.append('--entrypoint {}'.format(entrypoint))
        del entrypoint
        # get user identity settings
        if not is_windows:
            ui = _kv_read_checked(jobspec, 'user_identity', {})
            ui_default_pool_admin = _kv_read(ui, 'default_pool_admin', False)
            ui_specific = _kv_read(ui, 'specific_user', {})
            ui_specific_uid = _kv_read(ui_specific, 'uid')
            ui_specific_gid = _kv_read(ui_specific, 'gid')
            del ui
            del ui_specific
            if ui_default_pool_admin and ui_specific_uid is not None:
                raise ValueError(
                    'cannot specify both default_pool_admin and '
                    'specific_user:uid/gid at the same time')
            ui = UserIdentitySettings(
                default_pool_admin=ui_default_pool_admin,
                specific_user_uid=ui_specific_uid,
                specific_user_gid=ui_specific_gid,
            )
            # append user identity options
            uiopt = None
            attach_ui = False
            if ui.default_pool_admin:
                # run as the default pool admin user. note that this is
                # *undocumented* behavior and may break at anytime
                uiopt = '-u `id -u _azbatch`:`id -g _azbatch`'
                attach_ui = True
            elif ui.specific_user_uid is not None:
                if ui.specific_user_gid is None:
                    raise ValueError(
                        'cannot specify a user identity uid without a gid')
                uiopt = '-u {}:{}'.format(
                    ui.specific_user_uid, ui.specific_user_gid)
                attach_ui = True
            if util.is_not_empty(uiopt):
                run_opts.append(uiopt)
                docker_exec_options.append(uiopt)
            if attach_ui:
                run_opts.append('-v /etc/passwd:/etc/passwd:ro')
                run_opts.append('-v /etc/group:/etc/group:ro')
                run_opts.append('-v /etc/sudoers:/etc/sudoers:ro')
            del attach_ui
            del ui
            del uiopt
    # get command
    command = _kv_read_checked(conf, 'command')
    # parse data volumes
    data_volumes = _kv_read_checked(jobspec, 'data_volumes')
    tdv = _kv_read_checked(conf, 'data_volumes')
    if util.is_not_empty(tdv):
        if util.is_not_empty(data_volumes):
            # check for intersection
            if len(set(data_volumes).intersection(set(tdv))) > 0:
                raise ValueError('data volumes must be unique')
            data_volumes.extend(tdv)
        else:
            data_volumes = tdv
    del tdv
    # binding order matters for Singularity
    bindparm = '-v' if util.is_not_empty(docker_image) else '-B'
    # get working dir default
    def_wd = _kv_read_checked(
        conf, 'default_working_dir',
        default=_kv_read_checked(jobspec, 'default_working_dir')
    )
    if util.is_none_or_empty(def_wd) or def_wd == 'batch':
        if is_windows:
            def_wd = '%AZ_BATCH_TASK_WORKING_DIR%'
        else:
            def_wd = '$AZ_BATCH_TASK_WORKING_DIR'
    # bind root dir and set working dir
    if not native:
        # mount batch root dir
        if is_windows:
            run_opts.append(
                '{} %AZ_BATCH_NODE_ROOT_DIR%:%AZ_BATCH_NODE_ROOT_DIR%'.format(
                    bindparm))
        else:
            run_opts.append(
                '{} $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR'.format(
                    bindparm))
        # set working directory if not already set
        if def_wd != 'container':
            if util.is_not_empty(docker_image):
                if not any((x.startswith('-w ') or x.startswith('--workdir '))
                           for x in run_opts):
                    run_opts.append('-w {}'.format(def_wd))
            else:
                if not any(x.startswith('--pwd ') for x in run_opts):
                    run_opts.append('--pwd {}'.format(def_wd))
    if util.is_not_empty(data_volumes):
        dv = global_resources_data_volumes(config)
        for dvkey in data_volumes:
            try:
                hostpath = _kv_read_checked(dv[dvkey], 'host_path')
            except KeyError:
                raise ValueError(
                    ('ensure that the {} data volume exists in the '
                     'global configuration').format(dvkey))
            bindopt = _kv_read_checked(dv[dvkey], 'bind_options', default='')
            if util.is_not_empty(bindopt):
                bindopt = ':{}'.format(bindopt)
            if util.is_not_empty(hostpath):
                run_opts.append('{} {}:{}{}'.format(
                    bindparm, hostpath, dv[dvkey]['container_path'], bindopt))
            else:
                if util.is_not_empty(bindopt):
                    run_opts.append('{bp} {cp}:{cp}{bo}'.format(
                        bp=bindparm, cp=dv[dvkey]['container_path'],
                        bo=bindopt))
                else:
                    run_opts.append('{} {}'.format(
                        bindparm, dv[dvkey]['container_path']))
    del data_volumes
    # parse shared data volumes
    shared_data_volumes = _kv_read_checked(jobspec, 'shared_data_volumes')
    tsdv = _kv_read_checked(conf, 'shared_data_volumes')
    if util.is_not_empty(tsdv):
        if util.is_not_empty(shared_data_volumes):
            # check for intersection
            if len(set(shared_data_volumes).intersection(set(tsdv))) > 0:
                raise ValueError('shared data volumes must be unique')
            shared_data_volumes.extend(tsdv)
        else:
            shared_data_volumes = tsdv
    del tsdv
    if util.is_not_empty(shared_data_volumes):
        sdv = global_resources_shared_data_volumes(config)
        for sdvkey in shared_data_volumes:
            try:
                bindopt = _kv_read_checked(
                    sdv[sdvkey], 'bind_options', default='')
            except KeyError:
                raise ValueError(
                    ('ensure that the {} shared data volume exists in the '
                     'global configuration').format(sdvkey))
            if util.is_not_empty(bindopt):
                bindopt = ':{}'.format(bindopt)
            if is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
                run_opts.append('{} {}/{}:{}{}'.format(
                    bindparm,
                    _HOST_MOUNTS_DIR,
                    get_gluster_on_compute_volume(),
                    shared_data_volume_container_path(sdv, sdvkey),
                    bindopt))
            elif is_shared_data_volume_storage_cluster(sdv, sdvkey):
                run_opts.append('{} {}/{}:{}{}'.format(
                    bindparm,
                    _HOST_MOUNTS_DIR,
                    sdvkey,
                    shared_data_volume_container_path(sdv, sdvkey),
                    bindopt))
            elif is_shared_data_volume_azure_blob(sdv, sdvkey):
                sa = credentials_storage(
                    config,
                    azure_storage_account_settings(sdv, sdvkey))
                cont_name = azure_blob_container_name(sdv, sdvkey)
                hmp = azure_blob_host_mount_path(sa.account, cont_name)
                run_opts.append('{} {}:{}{}'.format(
                    bindparm,
                    hmp,
                    shared_data_volume_container_path(sdv, sdvkey),
                    bindopt))
            elif is_shared_data_volume_azure_file(sdv, sdvkey):
                sa = credentials_storage(
                    config,
                    azure_storage_account_settings(sdv, sdvkey))
                share_name = azure_file_share_name(sdv, sdvkey)
                hmp = azure_file_host_mount_path(
                    sa.account, share_name, is_windows)
                run_opts.append('{} {}:{}{}'.format(
                    bindparm,
                    hmp,
                    shared_data_volume_container_path(sdv, sdvkey),
                    bindopt))
            elif is_shared_data_volume_custom_linux_mount(sdv, sdvkey):
                run_opts.append('{} {}/{}:{}{}'.format(
                    bindparm,
                    _HOST_MOUNTS_DIR,
                    sdvkey,
                    shared_data_volume_container_path(sdv, sdvkey),
                    bindopt))
            else:
                raise RuntimeError(
                    'unknown shared data volume type: {}'.format(sdvkey))
    del shared_data_volumes
    # env vars
    env_vars = _kv_read_checked(conf, 'environment_variables', default={})
    ev_secid = _kv_read_checked(
        conf, 'environment_variables_keyvault_secret_id')
    # constraints
    max_task_retries = _kv_read(conf, 'max_task_retries')
    max_wall_time = _kv_read_checked(conf, 'max_wall_time')
    if util.is_not_empty(max_wall_time):
        max_wall_time = util.convert_string_to_timedelta(max_wall_time)
    retention_time = (
        _kv_read_checked(conf, 'retention_time') or
        _kv_read_checked(jobspec, 'retention_time')
    )
    if util.is_not_empty(retention_time):
        retention_time = util.convert_string_to_timedelta(retention_time)
    # exit conditions, right now specific exit codes/ranges are not supported
    job_default_eo = _kv_read_checked(
        _kv_read_checked(
            _kv_read_checked(
                jobspec,
                'exit_conditions',
                default={}
            ),
            'default',
            default={}
        ),
        'exit_options',
        default={}
    )
    task_default_eo = _kv_read_checked(
        _kv_read_checked(
            _kv_read_checked(
                conf,
                'exit_conditions',
                default={}
            ),
            'default',
            default={}
        ),
        'exit_options',
        default={}
    )
    job_action = batchmodels.JobAction(
        _kv_read_checked(
            task_default_eo,
            'job_action',
            default=batchmodels.JobAction(
                _kv_read_checked(job_default_eo, 'job_action', default='none')
            )
        )
    )
    dependency_action = batchmodels.DependencyAction(
        _kv_read_checked(
            task_default_eo,
            'dependency_action',
            default=batchmodels.DependencyAction(
                _kv_read_checked(
                    job_default_eo, 'dependency_action', default='block')
            )
        )
    )
    # gpu
    gpu = _kv_read(conf, 'gpu')
    if gpu is None:
        gpu = _kv_read(jobspec, 'gpu')
    # if not specified check for gpu pool and implicitly enable
    if gpu is None:
        if is_gpu_pool(vm_size) and not is_windows:
            gpu = True
        else:
            gpu = False
    # adjust for gpu settings
    if gpu:
        if not is_gpu_pool(vm_size):
            raise RuntimeError(
                ('cannot initialize a gpu task on nodes without '
                 'gpus: pool={} vm_size={}').format(pool_id, vm_size))
        # set docker commands with nvidia docker wrapper
        docker_run_cmd = 'nvidia-docker run'
        docker_exec_cmd = 'nvidia-docker exec'
        if util.is_not_empty(singularity_image):
            run_opts.append('--nv')
    else:
        # set normal run and exec commands
        docker_run_cmd = 'docker run'
        docker_exec_cmd = 'docker exec'
    # infiniband
    infiniband = _kv_read(conf, 'infiniband')
    if infiniband is None:
        _kv_read(jobspec, 'infiniband')
    # if not specified, check for rdma pool and implicitly enable
    if infiniband is None:
        if is_rdma_pool(vm_size) and inter_node_comm and not is_windows:
            infiniband = True
        else:
            infiniband = False
    # adjust for infiniband
    if infiniband:
        if not inter_node_comm:
            raise RuntimeError(
                ('cannot initialize an infiniband task on a '
                 'non-internode communication enabled '
                 'pool: {}').format(pool_id))
        if not is_rdma_pool(vm_size):
            raise RuntimeError(
                ('cannot initialize an infiniband task on nodes '
                 'without RDMA: pool={} vm_size={}').format(
                     pool_id, vm_size))
        # mount /opt/intel for all container types
        run_opts.append('{} /opt/intel:/opt/intel:ro'.format(bindparm))
        if not native:
            if util.is_not_empty(docker_image):
                # common run opts
                run_opts.append('--net=host')
                run_opts.append('--ulimit memlock=9223372036854775807')
                run_opts.append('--device=/dev/infiniband/rdma_cm')
                run_opts.append('--device=/dev/infiniband/uverbs0')
            else:
                # ensure singularity opts do not have network namespace
                # or contain options
                try:
                    run_opts.remove('-c')
                except ValueError:
                    pass
                try:
                    run_opts.remove('--contain')
                except ValueError:
                    pass
                try:
                    run_opts.remove('-C')
                except ValueError:
                    pass
                try:
                    run_opts.remove('--containall')
                except ValueError:
                    pass
                try:
                    run_opts.remove('-n')
                except ValueError:
                    pass
                try:
                    run_opts.remove('--net')
                except ValueError:
                    pass
            # only centos-hpc and sles-hpc are supported for infiniband
            if ((publisher == 'openlogic' and offer == 'centos-hpc') or
                    (is_custom_image and
                     node_agent.startswith('batch.node.centos'))):
                run_opts.append('{} /etc/rdma:/etc/rdma:ro'.format(bindparm))
                run_opts.append(
                    '{} /etc/rdma/dat.conf:/etc/dat.conf:ro'.format(bindparm))
            elif ((publisher == 'suse' and offer == 'sles-hpc') or
                  (is_custom_image and
                   node_agent.startswith('batch.node.opensuse'))):
                run_opts.append('{} /etc/dat.conf:/etc/dat.conf:ro'.format(
                    bindparm))
                run_opts.append(
                    '{} /etc/dat.conf:/etc/rdma/dat.conf:ro'.format(bindparm))
                if util.is_not_empty(docker_image):
                    run_opts.append('--device=/dev/hvnd_rdma')
            else:
                raise ValueError(
                    ('Unsupported infiniband VM config, publisher={} '
                     'offer={}').format(publisher, offer))
    # always add option for envfile
    envfile = None
    if util.is_not_empty(docker_image):
        envfile = '.shipyard.envlist'
        if not native:
            run_opts.append('--env-file {}'.format(envfile))
    # populate mult-instance settings
    if is_multi_instance_task(conf):
        if not inter_node_comm:
            raise RuntimeError(
                ('cannot run a multi-instance task on a '
                 'non-internode communication enabled '
                 'pool: {}').format(pool_id))
        # Docker container must be named
        if util.is_not_empty(docker_image):
            if util.is_none_or_empty(name):
                raise ValueError(
                    'multi-instance task with a Docker image must be invoked '
                    'with a named container')
        # application command cannot be empty/None
        if util.is_none_or_empty(command):
            raise ValueError(
                'multi-instance task must have an application command')
        # set docker run options for coordination command
        if util.is_not_empty(docker_image):
            if not native:
                try:
                    run_opts.remove('--rm')
                except ValueError:
                    pass
                # run in detached mode
                run_opts.append('-d')
                # ensure host networking stack is used
                if '--net=host' not in run_opts:
                    run_opts.append('--net=host')
        else:
            # ensure network namespace is not enabled
            try:
                run_opts.remove('-n')
            except ValueError:
                pass
            try:
                run_opts.remove('--net')
            except ValueError:
                pass
        # get coordination command
        try:
            coordination_command = conf[
                'multi_instance']['coordination_command']
            if util.is_none_or_empty(coordination_command):
                raise KeyError()
            coordination_command = '{}'.format(' ' + coordination_command)
        except KeyError:
            # manually set coordination command to ssh for native
            # containers in daemon mode if not specified
            if native:
                coordination_command = '/usr/sbin/sshd -p 23'
            else:
                coordination_command = ''
        if native or util.is_not_empty(singularity_image):
            if util.is_not_empty(coordination_command):
                cc_args = [coordination_command]
            else:
                cc_args = None
        else:
            if is_windows:
                envgrep = 'set | findstr AZ_BATCH_ >> {}'.format(envfile)
            else:
                envgrep = 'env | grep AZ_BATCH_ >> {}'.format(envfile)
            cc_args = [
                envgrep,
                '{} {} {}{}'.format(
                    docker_run_cmd,
                    ' '.join(run_opts),
                    docker_image,
                    coordination_command),
            ]
            del envgrep
        del coordination_command
        # get num instances
        num_instances = conf['multi_instance']['num_instances']
        if not isinstance(num_instances, int):
            # TODO remove deprecation path
            if (num_instances == 'pool_specification_vm_count_dedicated' or
                    num_instances == 'pool_specification_vm_count'):
                pool_vm_count = _pool_vm_count(config)
                num_instances = pool_vm_count.dedicated
            elif num_instances == 'pool_specification_vm_count_low_priority':
                pool_vm_count = _pool_vm_count(config)
                num_instances = pool_vm_count.low_priority
            elif (num_instances == 'pool_current_dedicated' or
                  num_instances == 'pool_current_low_priority'):
                if cloud_pool is None:
                    raise RuntimeError(
                        ('Cannot retrieve current dedicated count for '
                         'pool: {}. Ensure pool exists.)'.format(pool_id)))
                if num_instances == 'pool_current_dedicated':
                    num_instances = cloud_pool.current_dedicated_nodes
                elif num_instances == 'pool_current_low_priority':
                    num_instances = cloud_pool.current_low_priority_nodes
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
        docker_image=docker_image,
        singularity_image=singularity_image,
        name=name,
        run_options=run_opts,
        docker_exec_options=docker_exec_options,
        environment_variables=env_vars,
        environment_variables_keyvault_secret_id=ev_secid,
        envfile=envfile,
        resource_files=resource_files,
        max_task_retries=max_task_retries,
        max_wall_time=max_wall_time,
        retention_time=retention_time,
        command=command,
        infiniband=infiniband,
        gpu=gpu,
        depends_on=depends_on,
        depends_on_range=depends_on_range,
        docker_run_cmd=docker_run_cmd,
        docker_exec_cmd=docker_exec_cmd,
        singularity_cmd=singularity_cmd,
        run_elevated=run_elevated,
        multi_instance=MultiInstanceSettings(
            num_instances=num_instances,
            coordination_command=cc_args,
            resource_files=mi_resource_files,
        ),
        default_exit_options=TaskExitOptions(
            job_action=job_action,
            dependency_action=dependency_action,
        ),
    )


# REMOTEFS SETTINGS
def virtual_network_settings(
        config, default_resource_group=None, default_existing_ok=False,
        default_create_nonexistant=True):
    # type: (dict) -> VirtualNetworkSettings
    """Get virtual network settings
    :param dict config: configuration dict
    :param str default_resource_group: default resource group
    :param bool default_existing_ok: default existing ok
    :param bool default_create_nonexistant: default create nonexistant
    :rtype: VirtualNetworkSettings
    :return: virtual network settings
    """
    conf = _kv_read_checked(config, 'virtual_network', {})
    arm_subnet_id = _kv_read_checked(conf, 'arm_subnet_id')
    name = _kv_read_checked(conf, 'name')
    if util.is_not_empty(arm_subnet_id) and util.is_not_empty(name):
        raise ValueError(
            'cannot specify both arm_subnet_id and virtual_network.name')
    resource_group = _kv_read_checked(
        conf, 'resource_group', default_resource_group)
    address_space = _kv_read_checked(conf, 'address_space')
    existing_ok = _kv_read(conf, 'existing_ok', default_existing_ok)
    create_nonexistant = _kv_read(
        conf, 'create_nonexistant', default_create_nonexistant)
    sub_conf = _kv_read_checked(conf, 'subnet', {})
    subnet_name = _kv_read_checked(sub_conf, 'name')
    if util.is_not_empty(name) and util.is_none_or_empty(subnet_name):
        raise ValueError(
            'subnet name not specified on virtual_network: {}'.format(name))
    subnet_address_prefix = _kv_read_checked(sub_conf, 'address_prefix')
    return VirtualNetworkSettings(
        arm_subnet_id=arm_subnet_id,
        name=name,
        resource_group=resource_group,
        address_space=address_space,
        subnet_name=subnet_name,
        subnet_address_prefix=subnet_address_prefix,
        existing_ok=existing_ok,
        create_nonexistant=create_nonexistant,
    )


def fileserver_settings(config, vm_count):
    conf = _kv_read_checked(config, 'file_server', {})
    sc_fs_type = _kv_read_checked(conf, 'type')
    if util.is_none_or_empty(sc_fs_type):
        raise ValueError('file_server:type must be specified')
    sc_fs_type = sc_fs_type.lower()
    # cross check against number of vms
    if ((sc_fs_type == 'nfs' and vm_count != 1) or
            (sc_fs_type == 'glusterfs' and vm_count <= 1)):
        raise ValueError(
            ('invalid combination of file_server:type {} and '
             'vm_count {}').format(sc_fs_type, vm_count))
    sc_fs_mountpoint = _kv_read_checked(conf, 'mountpoint')
    if util.is_none_or_empty(sc_fs_mountpoint):
        raise ValueError('file_server must be specified')
    sc_mo = _kv_read_checked(conf, 'mount_options')
    # get server options
    so_conf = _kv_read_checked(conf, 'server_options', {})
    # get samba options
    sc_samba = _kv_read_checked(conf, 'samba', {})
    smb_share_name = _kv_read_checked(sc_samba, 'share_name')
    sc_samba_account = _kv_read_checked(sc_samba, 'account', {})
    smb_account = SambaAccountSettings(
        username=_kv_read_checked(sc_samba_account, 'username', 'nobody'),
        password=_kv_read_checked(sc_samba_account, 'password'),
        uid=_kv_read(sc_samba_account, 'uid'),
        gid=_kv_read(sc_samba_account, 'gid'),
    )
    if smb_account.username != 'nobody':
        if util.is_none_or_empty(smb_account.password):
            raise ValueError(
                'samba account password is invalid for username {}'.format(
                    smb_account.username))
        if '\n' in smb_account.password:
            raise ValueError(
                'samba account password contains invalid characters')
        if smb_account.uid is None or smb_account.gid is None:
            raise ValueError(
                ('samba account uid and/or gid is invalid for '
                 'username {}').format(smb_account.username))
    smb_ro = _kv_read(sc_samba, 'read_only', False)
    if smb_ro:
        smb_ro = 'yes'
    else:
        smb_ro = 'no'
    smb_cm = _kv_read_checked(sc_samba, 'create_mask', '0700')
    smb_dm = _kv_read_checked(sc_samba, 'directory_mask', '0700')
    return FileServerSettings(
        type=sc_fs_type,
        mountpoint=sc_fs_mountpoint,
        mount_options=sc_mo,
        server_options=so_conf,
        samba=SambaSettings(
            share_name=smb_share_name,
            account=smb_account,
            read_only=smb_ro,
            create_mask=smb_cm,
            directory_mask=smb_dm,
        ),
    )


def remotefs_settings(config, sc_id=None):
    # type: (dict, str) -> RemoteFsSettings
    """Get remote fs settings
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :rtype: RemoteFsSettings
    :return: remote fs settings
    """
    # general settings
    try:
        conf = config['remote_fs']
        if util.is_none_or_empty(conf):
            raise KeyError
    except KeyError:
        raise ValueError(
            'remote_fs settings are invalid or missing. Did you specify an '
            'fs configuration file?')
    resource_group = _kv_read_checked(conf, 'resource_group')
    location = conf['location']
    if util.is_none_or_empty(location):
        raise ValueError('invalid location in remote_fs')
    # managed disk settings
    md_conf = conf['managed_disks']
    md_rg = _kv_read_checked(md_conf, 'resource_group', resource_group)
    if util.is_none_or_empty(md_rg):
        raise ValueError('invalid managed_disks:resource_group in remote_fs')
    md_premium = _kv_read(md_conf, 'premium', False)
    md_disk_size_gb = _kv_read(md_conf, 'disk_size_gb')
    md_disk_names = _kv_read_checked(md_conf, 'disk_names')
    md = ManagedDisksSettings(
        resource_group=md_rg,
        premium=md_premium,
        disk_size_gb=md_disk_size_gb,
        disk_names=md_disk_names,
    )
    if util.is_none_or_empty(sc_id):
        return RemoteFsSettings(
            location=location,
            managed_disks=md,
            storage_cluster=None,
        )
    # storage cluster settings
    try:
        sc_conf = conf['storage_clusters'][sc_id]
    except KeyError:
        raise ValueError(
            ('Storage cluster {} is not defined in the given fs '
             'configuration file').format(sc_id))
    sc_rg = _kv_read_checked(sc_conf, 'resource_group', resource_group)
    if util.is_none_or_empty(md_rg):
        raise ValueError('invalid resource_group in remote_fs')
    sc_vm_count = _kv_read(sc_conf, 'vm_count', 1)
    sc_vm_size = _kv_read_checked(sc_conf, 'vm_size')
    sc_fault_domains = _kv_read(sc_conf, 'fault_domains', 2)
    if sc_fault_domains < 2 or sc_fault_domains > 3:
        raise ValueError('fault_domains must be in range [2, 3]: {}'.format(
            sc_fault_domains))
    sc_hostname_prefix = _kv_read_checked(sc_conf, 'hostname_prefix')
    sc_accel_net = _kv_read(sc_conf, 'accelerated_networking', False)
    # public ip settings
    pip_conf = _kv_read_checked(sc_conf, 'public_ip', {})
    sc_pip_enabled = _kv_read(pip_conf, 'enabled', True)
    sc_pip_static = _kv_read(pip_conf, 'static', False)
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
            source_address_prefix=_kv_read_checked(ns_conf, 'nfs'),
            protocol='tcp',
        )
        if not isinstance(sc_ns_inbound['nfs'].source_address_prefix, list):
            raise ValueError('expected list for nfs network security rule')
    if 'glusterfs' in ns_conf:
        # glusterd and management ports
        sc_ns_inbound['glusterfs-management'] = InboundNetworkSecurityRule(
            destination_port_range='24007-24008',
            source_address_prefix=_kv_read_checked(ns_conf, 'glusterfs'),
            protocol='tcp',
        )
        # gluster brick ports: only 1 port per vm is needed as there will
        # only be 1 brick per vm (brick is spread across RAID)
        sc_ns_inbound['glusterfs-bricks'] = InboundNetworkSecurityRule(
            destination_port_range='49152',
            source_address_prefix=_kv_read_checked(ns_conf, 'glusterfs'),
            protocol='tcp',
        )
        # only need to check one for glusterfs
        if not isinstance(
                sc_ns_inbound['glusterfs-management'].source_address_prefix,
                list):
            raise ValueError(
                'expected list for glusterfs network security rule')
    if 'smb' in ns_conf:
        sc_ns_inbound['smb'] = InboundNetworkSecurityRule(
            destination_port_range='445',
            source_address_prefix=_kv_read_checked(ns_conf, 'smb'),
            protocol='tcp',
        )
        if not isinstance(sc_ns_inbound['smb'].source_address_prefix, list):
            raise ValueError('expected list for smb network security rule')
    if 'custom_inbound_rules' in ns_conf:
        # reserve keywords (current and expected possible future support)
        _reserved = frozenset([
            'ssh', 'nfs', 'glusterfs', 'smb', 'cifs', 'samba', 'zfs',
            'beegfs', 'cephfs',
        ])
        for key in ns_conf['custom_inbound_rules']:
            # ensure key is not reserved
            if key.lower() in _reserved:
                raise ValueError(
                    ('custom inbound rule of name {} conflicts with a '
                     'reserved name {}').format(key, _reserved))
            sc_ns_inbound[key] = InboundNetworkSecurityRule(
                destination_port_range=_kv_read_checked(
                    ns_conf['custom_inbound_rules'][key],
                    'destination_port_range'),
                source_address_prefix=_kv_read_checked(
                    ns_conf['custom_inbound_rules'][key],
                    'source_address_prefix'),
                protocol=_kv_read_checked(
                    ns_conf['custom_inbound_rules'][key], 'protocol'),
            )
            if not isinstance(sc_ns_inbound[key].source_address_prefix, list):
                raise ValueError(
                    'expected list for network security rule {} '
                    'source_address_prefix'.format(key))
    # sc file server settings
    file_server = fileserver_settings(sc_conf, sc_vm_count)
    # sc ssh settings
    ssh_conf = sc_conf['ssh']
    sc_ssh_username = _kv_read_checked(ssh_conf, 'username')
    sc_ssh_public_key = _kv_read_checked(ssh_conf, 'ssh_public_key')
    if util.is_not_empty(sc_ssh_public_key):
        sc_ssh_public_key = pathlib.Path(sc_ssh_public_key)
    sc_ssh_public_key_data = _kv_read_checked(ssh_conf, 'ssh_public_key_data')
    sc_ssh_private_key = _kv_read_checked(ssh_conf, 'ssh_private_key')
    if util.is_not_empty(sc_ssh_private_key):
        sc_ssh_private_key = pathlib.Path(sc_ssh_private_key)
    if (sc_ssh_public_key is not None and
            util.is_not_empty(sc_ssh_public_key_data)):
        raise ValueError('cannot specify both an SSH public key file and data')
    if (sc_ssh_public_key is None and
            util.is_none_or_empty(sc_ssh_public_key_data) and
            sc_ssh_private_key is not None):
        raise ValueError(
            'cannot specify an SSH private key with no public key specified')
    sc_ssh_gen_file_path = _kv_read_checked(
        ssh_conf, 'generated_file_export_path', '.')
    # ensure ssh username and samba username are not the same
    if file_server.samba.account.username == sc_ssh_username:
        raise ValueError(
            'SSH username and samba account username cannot be the same')
    # sc vm disk map settings
    vmd_conf = sc_conf['vm_disk_map']
    _disk_set = frozenset(md_disk_names)
    disk_map = {}
    for vmkey in vmd_conf:
        # ensure all disks in disk array are specified in managed disks
        disk_array = vmd_conf[vmkey]['disk_array']
        if not _disk_set.issuperset(set(disk_array)):
            raise ValueError(
                ('All disks {} for vm {} are not specified in '
                 'managed_disks:disk_names ({})').format(
                     disk_array, vmkey, _disk_set))
        raid_level = _kv_read(vmd_conf[vmkey], 'raid_level', -1)
        if len(disk_array) == 1 and raid_level != -1:
            raise ValueError(
                'Cannot specify a RAID-level with 1 disk in array')
        else:
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
            ('Number of entries in vm_disk_map {} inconsistent with '
             'vm_count {}').format(len(disk_map), sc_vm_count))
    return RemoteFsSettings(
        location=location,
        managed_disks=ManagedDisksSettings(
            resource_group=md_rg,
            premium=md_premium,
            disk_size_gb=md_disk_size_gb,
            disk_names=md_disk_names,
        ),
        storage_cluster=StorageClusterSettings(
            id=sc_id,
            resource_group=sc_rg,
            virtual_network=virtual_network_settings(
                sc_conf,
                default_resource_group=sc_rg,
                default_existing_ok=False,
                default_create_nonexistant=True,
            ),
            network_security=NetworkSecuritySettings(
                inbound=sc_ns_inbound,
            ),
            file_server=file_server,
            vm_count=sc_vm_count,
            vm_size=sc_vm_size,
            fault_domains=sc_fault_domains,
            accelerated_networking=sc_accel_net,
            public_ip=PublicIpSettings(
                enabled=sc_pip_enabled,
                static=sc_pip_static,
            ),
            hostname_prefix=sc_hostname_prefix,
            ssh=SSHSettings(
                username=sc_ssh_username,
                expiry_days=9999,
                ssh_public_key=sc_ssh_public_key,
                ssh_public_key_data=sc_ssh_public_key_data,
                ssh_private_key=sc_ssh_private_key,
                generate_docker_tunnel_script=False,
                generated_file_export_path=sc_ssh_gen_file_path,
                hpn_server_swap=False,
            ),
            vm_disk_map=disk_map,
        ),
    )


def generate_availability_set_name(sc):
    # type: (StorageClusterSettings) -> str
    """Generate an availabilty set name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: availability set name
    """
    return '{}-as'.format(sc.hostname_prefix)


def generate_virtual_machine_name(sc, i):
    # type: (StorageClusterSettings) -> str
    """Generate a virtual machine name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: vm name
    """
    return '{}-vm{}'.format(sc.hostname_prefix, str(i).zfill(3))


def get_offset_from_virtual_machine_name(vm_name):
    # type: (StorageClusterSettings) -> int
    """Gets the virtual machine offset given a vm name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: int
    :return: vm offset
    """
    return int(vm_name.split('-vm')[-1])


def generate_virtual_machine_extension_name(sc, i):
    # type: (StorageClusterSettings) -> str
    """Generate a virtual machine extension name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: vm extension name
    """
    return '{}-vmext{}'.format(sc.hostname_prefix, str(i).zfill(3))


def generate_network_security_group_name(sc):
    # type: (StorageClusterSettings) -> str
    """Generate a network security group name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: nsg name
    """
    return '{}-nsg'.format(sc.hostname_prefix)


def generate_network_security_inbound_rule_name(rule_name, i):
    # type: (StorageClusterSettings) -> str
    """Generate a network security inbound rule name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: inbound rule name
    """
    return '{}_in-{}'.format(rule_name, str(i).zfill(3))


def generate_network_security_inbound_rule_description(rule_name, i):
    # type: (StorageClusterSettings) -> str
    """Generate a network security inbound rule description
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: inbound description
    """
    return '{} inbound ({})'.format(rule_name, str(i).zfill(3))


def generate_public_ip_name(sc, i):
    # type: (StorageClusterSettings) -> str
    """Generate a public ip name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: public ip name
    """
    return '{}-pip{}'.format(sc.hostname_prefix, str(i).zfill(3))


def generate_hostname(sc, i):
    # type: (StorageClusterSettings) -> str
    """Generate a hostname (dns label prefix)
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: hostname
    """
    return '{}{}'.format(sc.hostname_prefix, str(i).zfill(3))


def generate_network_interface_name(sc, i):
    # type: (StorageClusterSettings) -> str
    """Generate a network inetrface name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: network interface name
    """
    return '{}-ni{}'.format(sc.hostname_prefix, str(i).zfill(3))


def get_file_server_glusterfs_volume_name(sc):
    # type: (StorageClusterSettings) -> str
    """Get the glusterfs volume name
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: glusterfs volume name
    """
    try:
        volname = sc.file_server.server_options['glusterfs']['volume_name']
    except KeyError:
        volname = get_gluster_default_volume_name()
    return volname


def get_file_server_glusterfs_volume_type(sc):
    # type: (StorageClusterSettings) -> str
    """Get the glusterfs volume type
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: glusterfs volume type
    """
    try:
        voltype = sc.file_server.server_options[
            'glusterfs']['volume_type'].lower()
    except KeyError:
        voltype = 'distributed'
    return voltype


def get_file_server_glusterfs_transport(sc):
    # type: (StorageClusterSettings) -> str
    """Get the glusterfs transport
    :param StorageClusterSettings sc: storage cluster settings
    :rtype: str
    :return: glusterfs transport
    """
    try:
        transport = sc.file_server.server_options[
            'glusterfs']['transport'].lower()
        if transport != 'tcp':
            raise ValueError('Only tcp is supported as transport')
    except KeyError:
        transport = 'tcp'
    return transport
