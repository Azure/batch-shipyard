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
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import requests
import tempfile
import time
import uuid
# non-stdlib imports
import azure.batch.models as batchmodels
# local imports
from . import autoscale
from . import batch
from . import crypto
from . import data
from . import keyvault
from . import misc
from . import picket
from . import remotefs
from . import resource
from . import settings
from . import storage
from . import util
from .version import __version__

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_REQUEST_CHUNK_SIZE = 4194304
_ROOT_PATH = pathlib.Path(__file__).resolve().parent.parent
_RESOURCES_PATH = None
_NVIDIA_DRIVER = {
    'compute_cc37': {
        'url': (
            'http://us.download.nvidia.com/tesla/'
            '396.26/NVIDIA-Linux-x86_64-396.26-diagnostic.run'
        ),
        'sha256': (
            '1575fc9b5b328bd93f78f6c914a29520172f17500d02700ce3cd650ac5c70a05'
        ),
        'target': 'nvidia-driver_cc37.run'
    },
    'compute_cc6-7': {
        'url': (
            'http://us.download.nvidia.com/tesla/'
            '396.26/NVIDIA-Linux-x86_64-396.26-diagnostic.run'
        ),
        'sha256': (
            '1575fc9b5b328bd93f78f6c914a29520172f17500d02700ce3cd650ac5c70a05'
        ),
        'target': 'nvidia-driver_cc6-7.run'
    },
    'viz_cc52': {
        # https://go.microsoft.com/fwlink/?linkid=849941
        'url': (
            'https://gpudrivers.file.core.windows.net/nvinstance/Linux/'
            'NVIDIA-Linux-x86_64-390.42-grid.run?st=2018-04-03T01%3A34%3A00Z&'
            'se=2019-04-04T01%3A34%3A00Z&sp=rl&sv=2017-04-17&sr=s&'
            'sig=l3%2FQLZdtT5NL6BQTSOL5KsW%2FiKJK1Ly5iIi2PXpoaDU%3D'
        ),
        'sha256': (
            'de5bc9e5fc3683a231e5ae31ad6b148e54bf093f0f2186c21bb3f42b34985cf4'
        ),
        'target': 'nvidia-driver-grid.run'
    },
    'license': (
        'http://www.nvidia.com/content/DriverDownload-March2009'
        '/licence.php?lang=us'
    ),
}
_LIS_PACKAGE = {
    # https://aka.ms/lis
    'url': (
        'http://download.microsoft.com/download/6/8/F/'
        '68FE11B8-FAA4-4F8D-8C7D-74DA7F2CFC8C/lis-rpms-4.2.5.tar.gz'
    ),
    'sha256': (
        '90d802ef27bf1977444d60b2473bd0c3cb9188735a2bceaa6d8c955f60811d40'
    ),
    'target': 'lis.tar.gz',
    'intermediate': 'lis_compact.tar',
    'target_compact': 'lis_compact.tar.gz'
}
_PROMETHEUS = {
    'node_exporter': {
        'url': (
            'https://github.com/prometheus/node_exporter/releases/download/v'
            '0.16.0/node_exporter-0.16.0.linux-amd64.tar.gz'
        ),
        'sha256': (
            'e92a601a5ef4f77cce967266b488a978711dabc527a720bea26505cba426c029'
        ),
        'target': 'node_exporter.tar.gz'
    },
    'cadvisor': {
        'url': (
            'https://github.com/google/cadvisor/releases/download/v'
            '0.27.4/cadvisor'
        ),
        'sha256': (
            '378df92f532166251fa3f116beea26ca6364e45e3d6a63ea78b7627ea54bd303'
        ),
        'target': 'cadvisor',
        'target_compact': 'cadvisor.gz'
    },
}
_CASCADE_FILE = (
    'cascade.py',
    pathlib.Path(_ROOT_PATH, 'cascade/cascade.py')
)
_PERF_FILE = (
    'perf.py',
    pathlib.Path(_ROOT_PATH, 'cascade/perf.py')
)
_NODEPREP_FILE = (
    'shipyard_nodeprep.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_nodeprep.sh')
)
_NODEPREP_WINDOWS_FILE = (
    'shipyard_nodeprep_nativedocker.ps1',
    pathlib.Path(
        _ROOT_PATH,
        'scripts/windows/shipyard_nodeprep_nativedocker.ps1'
    )
)
_GLUSTERPREP_FILE = (
    'shipyard_glusterfs_on_compute.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_glusterfs_on_compute.sh')
)
_GLUSTERRESIZE_FILE = (
    'shipyard_glusterfs_on_compute_resize.sh',
    pathlib.Path(
        _ROOT_PATH, 'scripts/shipyard_glusterfs_on_compute_resize.sh')
)
_HPNSSH_FILE = (
    'shipyard_hpnssh.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_hpnssh.sh')
)
_IMAGE_BLOCK_FILE = (
    'wait_for_images.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/wait_for_images.sh')
)
_REGISTRY_LOGIN_FILE = (
    'registry_login.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/registry_login.sh')
)
_REGISTRY_LOGIN_WINDOWS_FILE = (
    'registry_login.ps1',
    pathlib.Path(_ROOT_PATH, 'scripts/windows/registry_login.ps1')
)
_BLOBXFER_FILE = (
    'shipyard_blobxfer.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_blobxfer.sh')
)
_BLOBXFER_WINDOWS_FILE = (
    'shipyard_blobxfer.ps1',
    pathlib.Path(_ROOT_PATH, 'scripts/windows/shipyard_blobxfer.ps1')
)
_REMOTEFSPREP_FILE = (
    'shipyard_remotefs_bootstrap.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_remotefs_bootstrap.sh')
)
_REMOTEFSADDBRICK_FILE = (
    'shipyard_remotefs_addbrick.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_remotefs_addbrick.sh')
)
_REMOTEFSSTAT_FILE = (
    'shipyard_remotefs_stat.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_remotefs_stat.sh')
)
_ALL_REMOTEFS_FILES = [
    _REMOTEFSPREP_FILE, _REMOTEFSADDBRICK_FILE, _REMOTEFSSTAT_FILE,
]
_MONITORINGPREP_FILE = (
    'shipyard_monitoring_bootstrap.sh',
    pathlib.Path(_ROOT_PATH, 'scripts/shipyard_monitoring_bootstrap.sh')
)
_MONITORINGSERVICES_FILE = (
    'docker-compose.yml',
    pathlib.Path(_ROOT_PATH, 'heimdall/docker-compose.yml')
)
_MONITORINGSERVICESNONGINX_FILE = (
    'docker-compose-nonginx.yml',
    pathlib.Path(_ROOT_PATH, 'heimdall/docker-compose-nonginx.yml')
)
_MONITORINGPROMCONF_FILE = (
    'prometheus.yml',
    pathlib.Path(_ROOT_PATH, 'heimdall/prometheus.yml')
)
_MONITORINGNGINXCONF_FILE = (
    'nginx.conf',
    pathlib.Path(_ROOT_PATH, 'heimdall/nginx.conf')
)
_MONITORINGGRAFANADASHBOARD_FILE = (
    'batch_shipyard_dashboard.json',
    pathlib.Path(_ROOT_PATH, 'heimdall/batch_shipyard_dashboard.json')
)
_CONFIGURABLE_MONITORING_FILES = {
    'compose': _MONITORINGSERVICES_FILE,
    'compose-nonginx': _MONITORINGSERVICESNONGINX_FILE,
    'prometheus': _MONITORINGPROMCONF_FILE,
    'nginx': _MONITORINGNGINXCONF_FILE,
    'dashboard': _MONITORINGGRAFANADASHBOARD_FILE,
}


def initialize_globals(verbose):
    # type: (bool) -> None
    """Initialize any runtime globals
    :param bool verbose: verbose
    """
    global _RESOURCES_PATH
    if _RESOURCES_PATH is None:
        _RESOURCES_PATH = _ROOT_PATH / 'resources'
        if not _RESOURCES_PATH.exists():
            _RESOURCES_PATH = pathlib.Path(
                tempfile.gettempdir()) / 'batch-shipyard-{}-resources'.format(
                    __version__)
            _RESOURCES_PATH.mkdir(parents=True, exist_ok=True)
        if verbose:
            logger.debug('initialized resources path to: {}'.format(
                _RESOURCES_PATH))


def populate_global_settings(config, fs_storage, pool_id=None):
    # type: (dict, bool) -> None
    """Populate global settings from config
    :param dict config: configuration dict
    :param bool fs_storage: adjust for fs context
    :param str pool_id: pool id override
    """
    bs = settings.batch_shipyard_settings(config)
    sc = settings.credentials_storage(config, bs.storage_account_settings)
    if fs_storage:
        # set postfix to empty for now, it will be populated with the
        # storage cluster during the actual calls
        postfix = ''
        if util.is_not_empty(pool_id):
            raise ValueError('pool id specified for fs_storage')
    else:
        bc = settings.credentials_batch(config)
        if util.is_none_or_empty(pool_id):
            pool_id = settings.pool_id(config, lower=True)
        postfix = '-'.join((bc.account.lower(), pool_id))
    storage.set_storage_configuration(
        bs.storage_entity_prefix,
        postfix,
        sc.account,
        sc.account_key,
        sc.endpoint,
        bs.generated_sas_expiry_days)


def fetch_credentials_conf_from_keyvault(
        keyvault_client, keyvault_uri, keyvault_credentials_secret_id):
    # type: (azure.keyvault.KeyVaultClient, str, str) -> dict
    """Fetch a credentials conf from keyvault
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param str keyvault_uri: keyvault uri
    :param str keyvault_credentials_secret_id: keyvault cred secret id
    :rtype: dict
    :return: credentials conf
    """
    if keyvault_uri is None:
        raise ValueError('credentials conf was not specified or is invalid')
    if keyvault_client is None:
        raise ValueError('no Azure KeyVault or AAD credentials specified')
    return keyvault.fetch_credentials_conf(
        keyvault_client, keyvault_uri, keyvault_credentials_secret_id)


def fetch_secrets_from_keyvault(keyvault_client, config):
    # type: (azure.keyvault.KeyVaultClient, dict) -> None
    """Fetch secrets with secret ids in config from keyvault
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param dict config: configuration dict
    """
    if keyvault_client is not None:
        keyvault.parse_secret_ids(keyvault_client, config)


def fetch_storage_account_keys_from_aad(
        storage_mgmt_client, config, fs_storage):
    # type: (azure.mgmt.storage.StorageManagementClient, dict, bool) -> None
    """Fetch secrets with secret ids in config from keyvault
    :param azure.mgmt.storage.StorageManagementClient storage_mgmt_client:
        storage client
    :param dict config: configuration dict
    :param bool fs_storage: adjust for fs context
    """
    if storage.populate_storage_account_keys_from_aad(
            storage_mgmt_client, config):
        populate_global_settings(config, fs_storage)


def _download_file(desc, pkg, dldict):
    # type: (str, pathlib.Path, dict) -> None
    """Download a file and check sha256
    :param str desc: description
    :param pathlib.Path pkg: package
    :param dict dldict: download dict
    """
    logger.debug('downloading {} to {}'.format(desc, dldict['target']))
    response = requests.get(dldict['url'], stream=True)
    with pkg.open('wb') as f:
        for chunk in response.iter_content(chunk_size=_REQUEST_CHUNK_SIZE):
            if chunk:
                f.write(chunk)
    logger.debug('wrote {} bytes to {}'.format(pkg.stat().st_size, pkg))
    # check sha256
    if util.compute_sha256_for_file(pkg, False) != dldict['sha256']:
        raise RuntimeError('sha256 mismatch for {}'.format(pkg))


def _setup_nvidia_driver_package(config, vm_size):
    # type: (dict, str) -> pathlib.Path
    """Set up the nvidia driver package
    :param dict config: configuration dict
    :param str vm_size: vm size
    :rtype: pathlib.Path
    :return: package path
    """
    gpu_type = settings.get_gpu_type_from_vm_size(vm_size)
    pkg = _RESOURCES_PATH / _NVIDIA_DRIVER[gpu_type]['target']
    # check to see if package is downloaded
    if (not pkg.exists() or
            util.compute_sha256_for_file(pkg, False) !=
            _NVIDIA_DRIVER[gpu_type]['sha256']):
        # display license link
        if not util.confirm_action(
                config,
                msg=('agreement with License for Customer Use of NVIDIA '
                     'Software @ {}').format(_NVIDIA_DRIVER['license']),
                allow_auto=True):
            raise RuntimeError(
                'Cannot proceed with deployment due to non-agreement with '
                'license for NVIDIA driver')
        else:
            logger.info('NVIDIA Software License accepted')
        # download driver
        _download_file('NVIDIA driver', pkg, _NVIDIA_DRIVER[gpu_type])
    return pkg


def _setup_lis_package(config, vm_size):
    # type: (dict, str) -> pathlib.Path
    """Set up the LIS package
    :param dict config: configuration dict
    :param str vm_size: vm size
    :rtype: pathlib.Path
    :return: package path
    """
    # check to see if lis is required first
    if not settings.is_lis_install_required(config, vm_size=vm_size):
        return None
    pkg = _RESOURCES_PATH / _LIS_PACKAGE['target']
    compact_pkg = _RESOURCES_PATH / _LIS_PACKAGE['target_compact']
    # check to see if package is downloaded
    if (not compact_pkg.exists() or not pkg.exists() or
            util.compute_sha256_for_file(pkg, False) !=
            _LIS_PACKAGE['sha256']):
        _download_file('LIS package', pkg, _LIS_PACKAGE)
        logger.debug('compacting LIS package')
        util.subprocess_with_output(
            'gunzip -f -k {}'.format(pkg), shell=True, suppress_output=True)
        tmp = pkg.parent / pkg.stem
        inter = pkg.parent / _LIS_PACKAGE['intermediate']
        tmp.replace(inter)
        util.subprocess_with_output(
            ('tar vf {} --wildcards --delete LISISO/Oracle* '
             '--delete LISISO/RHEL* --delete LISISO/CentOS5* '
             '--delete LISISO/CentOS6* --delete LISISO/CentOS70* '
             '--delete LISISO/CentOS71* --delete LISISO/CentOS72* '
             '--delete LISISO/CentOS73* ').format(inter),
            shell=True, suppress_output=True)
        util.subprocess_with_output(
            'gzip -f {}'.format(inter), shell=True, suppress_output=True)
        logger.debug('LIS package compacted: {} => {} bytes'.format(
            compact_pkg, compact_pkg.stat().st_size))
    return compact_pkg


def setup_prometheus_node_exporter():
    # type: (None) -> pathlib.Path
    """Setup node exporter package
    :return ne package
    """
    ne_pkg = _RESOURCES_PATH / _PROMETHEUS['node_exporter']['target']
    if (not ne_pkg.exists() or
            util.compute_sha256_for_file(ne_pkg, False) !=
            _PROMETHEUS['node_exporter']['sha256']):
        _download_file(
            'Prometheus Node Exporter', ne_pkg,
            _PROMETHEUS['node_exporter'])
    return ne_pkg


def _setup_prometheus_monitoring_tools(pool_settings):
    # type: settings.PoolSettings -> Tuple[pathlib.Path, pathlib.Path]
    """Setup the prometheus monitoring tools
    :param settings.PoolSettings pool_settings: pool settings
    :rtype: tuple
    :return: tuple of ne_pkg, ca_pkg
    """
    ne_pkg = None
    ca_pkg_compact = None
    if pool_settings.prometheus.ne_enabled:
        ne_pkg = setup_prometheus_node_exporter()
    if pool_settings.prometheus.ca_enabled:
        ca_pkg = _RESOURCES_PATH / _PROMETHEUS['cadvisor']['target']
        ca_pkg_compact = (
            _RESOURCES_PATH / _PROMETHEUS['cadvisor']['target_compact']
        )
        if (not ca_pkg.exists() or not ca_pkg_compact.exists() or
                util.compute_sha256_for_file(ca_pkg, False) !=
                _PROMETHEUS['cadvisor']['sha256']):
            _download_file('cAdvisor', ca_pkg, _PROMETHEUS['cadvisor'])
            logger.debug('compacting cAdvisor package')
            util.subprocess_with_output(
                'gzip -f -k {}'.format(ca_pkg), shell=True,
                suppress_output=True)
        logger.debug('cAdvisor package compacted: {} => {} bytes'.format(
            ca_pkg_compact, ca_pkg_compact.stat().st_size))
    return ne_pkg, ca_pkg_compact


def _generate_azure_mount_script_name(
        batch_account_name, pool_id, is_file_share, is_windows):
    # type: (str, str, bool, bool) -> pathlib.Path
    """Generate an azure blob/file mount script name
    :param str batch_account_name: batch account name
    :param str pool_id: pool id
    :param boo is_file_share: is file share
    :param bool is_windows: is windows
    :rtype: pathlib.Path
    :return: path to azure mount script
    """
    if is_file_share:
        prefix = 'azurefile'
    else:
        prefix = 'azureblob'
    return _RESOURCES_PATH / '{}-mount-{}-{}.{}'.format(
        prefix, batch_account_name.lower(), pool_id.lower(),
        'cmd' if is_windows else 'sh')


def _setup_azureblob_mounts(blob_client, config, bc):
    # type: (azure.storage.blob.BlockBlobService, dict,
    #        settings.BatchCredentials) -> tuple
    """Set up the Azure Blob container via blobfuse
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param settings.BatchCredentials bc: batch creds
    :rtype: tuple
    :return: (bin path, service file path, service env file path,
        volume creation script path)
    """
    tmpmount = settings.temp_disk_mountpoint(config)
    # construct mount commands
    cmds = []
    sdv = settings.global_resources_shared_data_volumes(config)
    for svkey in sdv:
        if settings.is_shared_data_volume_azure_blob(sdv, svkey):
            sa = settings.credentials_storage(
                config,
                settings.azure_storage_account_settings(sdv, svkey))
            cont = settings.azure_blob_container_name(sdv, svkey)
            hmp = settings.azure_blob_host_mount_path(sa.account, cont)
            tmpmp = '{}/blobfuse-tmp/{}-{}'.format(tmpmount, sa.account, cont)
            cmds.append('mkdir -p {}'.format(hmp))
            cmds.append('chmod 0770 {}'.format(hmp))
            cmds.append('mkdir -p {}'.format(tmpmp))
            cmds.append('chown _azbatch:_azbatchgrp {}'.format(tmpmp))
            cmds.append('chmod 0770 {}'.format(tmpmp))
            conn = 'azblob-{}-{}.cfg'.format(sa.account, cont)
            cmds.append('cat > {} << EOF'.format(conn))
            cmds.append('accountName {}'.format(sa.account))
            cmds.append('accountKey {}'.format(sa.account_key))
            cmds.append('containerName {}'.format(cont))
            cmds.append('EOF')
            cmd = (
                'blobfuse {hmp} --tmp-path={tmpmp} -o attr_timeout=240 '
                '-o entry_timeout=240 -o negative_timeout=120 -o allow_other '
                '--config-file={conn}'
            ).format(hmp=hmp, tmpmp=tmpmp, conn=conn)
            # add any additional mount options
            mo = settings.shared_data_volume_mount_options(sdv, svkey)
            if util.is_not_empty(mo):
                opts = []
                for opt in mo:
                    if opt.strip() == '-o allow_other':
                        continue
                    opts.append(opt)
                cmd = '{} {}'.format(cmd, ' '.join(opts))
            cmds.append(cmd)
    # create file share mount command script
    if util.is_none_or_empty(cmds):
        raise RuntimeError('Generated Azure blob mount commands are invalid')
    volcreate = _generate_azure_mount_script_name(
        bc.account, settings.pool_id(config), False, False)
    newline = '\n'
    with volcreate.open('w', newline=newline) as f:
        f.write('#!/usr/bin/env bash')
        f.write(newline)
        f.write('set -e')
        f.write(newline)
        f.write('set -o pipefail')
        f.write(newline)
        for cmd in cmds:
            f.write(cmd)
            f.write(newline)
    return volcreate


def _setup_azurefile_mounts(blob_client, config, bc, is_windows):
    # type: (azure.storage.blob.BlockBlobService, dict,
    #        settings.BatchCredentials, bool) -> tuple
    """Set up the Azure File shares
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param settings.BatchCredentials bc: batch creds
    :param bool is_windows: is windows pool
    :rtype: tuple
    :return: (bin path, service file path, service env file path,
        volume creation script path)
    """
    # construct mount commands
    cmds = []
    sdv = settings.global_resources_shared_data_volumes(config)
    for svkey in sdv:
        if settings.is_shared_data_volume_azure_file(sdv, svkey):
            sa = settings.credentials_storage(
                config,
                settings.azure_storage_account_settings(sdv, svkey))
            share = settings.azure_file_share_name(sdv, svkey)
            hmp = settings.azure_file_host_mount_path(
                sa.account, share, is_windows)
            if is_windows:
                cmd = (
                    'net use \\\\{sa}.file.{ep}\{share} {sakey} '
                    '/user:Azure\{sa}'
                ).format(
                    sa=sa.account, ep=sa.endpoint, share=share,
                    sakey=sa.account_key)
                cmds.append(cmd)
                cmd = 'mklink /d {hmp} \\\\{sa}.file.{ep}\{share}'.format(
                    hmp=hmp, sa=sa.account, ep=sa.endpoint, share=share)
            else:
                cmd = (
                    'mount -t cifs //{sa}.file.{ep}/{share} {hmp} -o '
                    'vers=3.0,username={sa},password={sakey},'
                    'serverino'
                ).format(
                    sa=sa.account, ep=sa.endpoint, share=share, hmp=hmp,
                    sakey=sa.account_key)
                # add any additional mount options
                mo = settings.shared_data_volume_mount_options(sdv, svkey)
                if util.is_not_empty(mo):
                    opts = []
                    # retain backward compatibility with filemode/dirmode
                    # options from the old Azure File Docker volume driver
                    for opt in mo:
                        tmp = opt.split('=')
                        if tmp[0] == 'filemode':
                            opts.append('file_mode={}'.format(tmp[1]))
                        elif tmp[0] == 'dirmode':
                            opts.append('dir_mode={}'.format(tmp[1]))
                        else:
                            opts.append(opt)
                    cmd = '{},{}'.format(cmd, ','.join(opts))
            if not is_windows:
                cmds.append('mkdir -p {}'.format(hmp))
            cmds.append(cmd)
    # create file share mount command script
    if util.is_none_or_empty(cmds):
        raise RuntimeError('Generated Azure file mount commands are invalid')
    volcreate = _generate_azure_mount_script_name(
        bc.account, settings.pool_id(config), True, is_windows)
    newline = '\r\n' if is_windows else '\n'
    with volcreate.open('w', newline=newline) as f:
        if is_windows:
            f.write('@echo off')
            f.write(newline)
        else:
            f.write('#!/usr/bin/env bash')
            f.write(newline)
            f.write('set -e')
            f.write(newline)
            f.write('set -o pipefail')
            f.write(newline)
        for cmd in cmds:
            f.write(cmd)
            f.write(newline)
    return volcreate


def _create_storage_cluster_mount_args(
        compute_client, network_client, batch_mgmt_client, config, sc_id,
        bc, subnet_id):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.mgmt.batch.BatchManagementClient, dict, str,
    #        settings.BatchCredentials, str) -> Tuple[str, str]
    """Create storage cluster mount arguments
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param settings.BatchCredentials bc: batch creds
    :param str subnet_id: subnet id
    :rtype: tuple
    :return: (fstab mount, storage cluster arg)
    """
    fstab_mount = None
    sc_arg = None
    ba, _ = batch.get_batch_account(batch_mgmt_client, config)
    # check for vnet/subnet presence
    if util.is_none_or_empty(subnet_id):
        raise RuntimeError(
            'cannot mount a storage cluster without a valid virtual '
            'network or subnet')
    # get remotefs settings
    rfs = settings.remotefs_settings(config, sc_id)
    sc = rfs.storage_cluster
    # iterate through shared data volumes and fine storage clusters
    sdv = settings.global_resources_shared_data_volumes(config)
    if (sc_id not in sdv or
            not settings.is_shared_data_volume_storage_cluster(
                sdv, sc_id)):
        raise RuntimeError(
            'No storage cluster {} found in configuration'.format(sc_id))
    vnet_subid, vnet_rg, _, vnet_name, subnet_name = _explode_arm_subnet_id(
        subnet_id)
    # check for same vnet name
    if vnet_name.lower() != sc.virtual_network.name.lower():
        raise RuntimeError(
            'cannot link storage cluster {} on virtual '
            'network {} with pool virtual network {}'.format(
                sc_id, sc.virtual_network.name, vnet_name))
    # cross check vnet resource group
    if vnet_rg.lower() != sc.virtual_network.resource_group.lower():
        raise RuntimeError(
            'cannot link storage cluster {} virtual network in resource group '
            '{} with pool virtual network in resource group {}'.format(
                sc_id, sc.virtual_network.resource_group, vnet_rg))
    # cross check vnet subscription id
    _ba_tmp = ba.id.lower().split('/')
    if vnet_subid.lower() != _ba_tmp[2]:
        raise RuntimeError(
            'cannot link storage cluster {} virtual network in subscription '
            '{} with pool virtual network in subscription {}'.format(
                sc_id, vnet_subid, _ba_tmp[2]))
    del _ba_tmp
    # get vm count
    if sc.vm_count < 1:
        raise RuntimeError(
            'storage cluster {} vm_count {} is invalid'.format(
                sc_id, sc.vm_count))
    # get fileserver type
    if sc.file_server.type == 'nfs':
        # query first vm for info
        vm_name = settings.generate_virtual_machine_name(sc, 0)
        vm = compute_client.virtual_machines.get(
            resource_group_name=sc.resource_group,
            vm_name=vm_name,
        )
        nic = resource.get_nic_from_virtual_machine(
            network_client, sc.resource_group, vm)
        # get private ip of vm
        remote_ip = nic.ip_configurations[0].private_ip_address
        # construct mount options
        mo = '_netdev,noauto,nfsvers=4,intr'
        amo = settings.shared_data_volume_mount_options(sdv, sc_id)
        if util.is_not_empty(amo):
            if 'udp' in mo:
                raise RuntimeError(
                    ('udp cannot be specified as a mount option for '
                     'storage cluster {}').format(sc_id))
            if 'auto' in mo:
                raise RuntimeError(
                    ('auto cannot be specified as a mount option for '
                     'storage cluster {}').format(sc_id))
            if any([x.startswith('nfsvers=') for x in amo]):
                raise RuntimeError(
                    ('nfsvers cannot be specified as a mount option for '
                     'storage cluster {}').format(sc_id))
            if any([x.startswith('port=') for x in amo]):
                raise RuntimeError(
                    ('port cannot be specified as a mount option for '
                     'storage cluster {}').format(sc_id))
            mo = ','.join((mo, ','.join(amo)))
        # construct mount string for fstab
        fstab_mount = (
            '{remoteip}:{srcpath} {hmp}/{scid} '
            '{fstype} {mo} 0 2').format(
                remoteip=remote_ip,
                srcpath=sc.file_server.mountpoint,
                hmp=settings.get_host_mounts_path(False),
                scid=sc_id,
                fstype=sc.file_server.type,
                mo=mo)
    elif sc.file_server.type == 'glusterfs':
        # walk vms and find non-overlapping ud/fds
        primary_ip = None
        primary_ud = None
        primary_fd = None
        backup_ip = None
        backup_ud = None
        backup_fd = None
        vms = {}
        # first pass, attempt to populate all ip, ud/fd
        for i in range(sc.vm_count):
            vm_name = settings.generate_virtual_machine_name(sc, i)
            vm = compute_client.virtual_machines.get(
                resource_group_name=sc.resource_group,
                vm_name=vm_name,
                expand=compute_client.virtual_machines.models.
                InstanceViewTypes.instance_view,
            )
            nic = resource.get_nic_from_virtual_machine(
                network_client, sc.resource_group, vm)
            vms[i] = (vm, nic)
            # get private ip and ud/fd of vm
            remote_ip = nic.ip_configurations[0].private_ip_address
            ud = vm.instance_view.platform_update_domain
            fd = vm.instance_view.platform_fault_domain
            if primary_ip is None:
                primary_ip = remote_ip
                primary_ud = ud
                primary_fd = fd
            if backup_ip is None:
                if (primary_ip == backup_ip or primary_ud == ud or
                        primary_fd == fd):
                    continue
                backup_ip = remote_ip
                backup_ud = ud
                backup_fd = fd
        # second pass, fill in with at least non-overlapping update domains
        if backup_ip is None:
            for i in range(sc.vm_count):
                vm, nic = vms[i]
                remote_ip = nic.ip_configurations[0].private_ip_address
                ud = vm.instance_view.platform_update_domain
                fd = vm.instance_view.platform_fault_domain
                if primary_ud != ud:
                    backup_ip = remote_ip
                    backup_ud = ud
                    backup_fd = fd
                    break
        if primary_ip is None or backup_ip is None:
            raise RuntimeError(
                'Could not find either a primary ip {} or backup ip {} for '
                'glusterfs client mount'.format(primary_ip, backup_ip))
        logger.debug('primary ip/ud/fd={} backup ip/ud/fd={}'.format(
            (primary_ip, primary_ud, primary_fd),
            (backup_ip, backup_ud, backup_fd)))
        # construct mount options
        mo = '_netdev,noauto,transport=tcp,backupvolfile-server={}'.format(
            backup_ip)
        amo = settings.shared_data_volume_mount_options(sdv, sc_id)
        if util.is_not_empty(amo):
            if 'auto' in mo:
                raise RuntimeError(
                    ('auto cannot be specified as a mount option for '
                     'storage cluster {}').format(sc_id))
            if any([x.startswith('backupvolfile-server=') for x in amo]):
                raise RuntimeError(
                    ('backupvolfile-server cannot be specified as a mount '
                     'option for storage cluster {}').format(sc_id))
            if any([x.startswith('transport=') for x in amo]):
                raise RuntimeError(
                    ('transport cannot be specified as a mount option for '
                     'storage cluster {}').format(sc_id))
            mo = ','.join((mo, ','.join(amo)))
        # construct mount string for fstab, srcpath is the gluster volume
        fstab_mount = (
            '{remoteip}:/{srcpath} {hmp}/{scid} '
            '{fstype} {mo} 0 2').format(
                remoteip=primary_ip,
                srcpath=settings.get_file_server_glusterfs_volume_name(sc),
                hmp=settings.get_host_mounts_path(False),
                scid=sc_id,
                fstype=sc.file_server.type,
                mo=mo)
    else:
        raise NotImplementedError(
            ('cannot handle file_server type {} for storage '
             'cluster {}').format(sc.file_server.type, sc_id))
    if util.is_none_or_empty(fstab_mount):
        raise RuntimeError(
            ('Could not construct an fstab mount entry for storage '
             'cluster {}').format(sc_id))
    # construct sc_arg
    sc_arg = '{}:{}'.format(sc.file_server.type, sc_id)
    # log config
    if settings.verbose(config):
        logger.debug('storage cluster {} fstab mount: {}'.format(
            sc_id, fstab_mount))
    return (fstab_mount, sc_arg)


def _create_custom_linux_mount_args(config, mount_name):
    # type: (dict, str) -> str
    """Create a custom linux mount fstab entry
    :param dict config: configuration dict
    :param str mount_name: mount name
    :rtype: str
    :return: fstab entry
    """
    sdv = settings.global_resources_shared_data_volumes(config)
    fstab = settings.custom_linux_mount_fstab_options(sdv, mount_name)
    if 'noauto' in fstab.fs_mntops:
        raise RuntimeError(
            ('noauto cannot be specified as a mount option for custom '
             'linux mount {}').format(mount_name))
    elif 'auto' in fstab.fs_mntops:
        raise RuntimeError(
            ('auto cannot be specified as a mount option for custom '
             'linux mount {}').format(mount_name))
    fstab_mount = (
        '{fs_spec} {hmp}/{name} {fs_vfstype} noauto,{fs_mntops} {fs_freq} '
        '{fs_passno}').format(
            fs_spec=fstab.fs_spec,
            hmp=settings.get_host_mounts_path(False),
            name=mount_name,
            fs_vfstype=fstab.fs_vfstype,
            fs_mntops=fstab.fs_mntops,
            fs_freq=fstab.fs_freq,
            fs_passno=fstab.fs_passno)
    return fstab_mount


def _pick_node_agent_for_vm(batch_client, config, pool_settings):
    # type: (azure.batch.batch_service_client.BatchServiceClient,
    #        dict, settings.PoolSettings) -> (str, str)
    """Pick a node agent id for the vm
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param settings.PoolSettings pool_settings: pool settings
    :rtype: tuple
    :return: image reference to use, node agent id to use
    """
    publisher = pool_settings.vm_configuration.publisher
    offer = pool_settings.vm_configuration.offer
    sku = pool_settings.vm_configuration.sku
    # TODO special exception for CentOS HPC 7.1, 7.3 and normal 7.3, 7.4
    if publisher == 'openlogic':
        if ((offer == 'centos-hpc' and
                (sku == '7.1' or sku == '7.3')) or
                (offer == 'centos' and (sku == '7.3' or sku == '7.4'))):
            return ({
                'publisher': publisher,
                'offer': offer,
                'sku': sku,
                'version': pool_settings.vm_configuration.version,
            }, 'batch.node.centos 7')
    # support windows server semi annual
    if (publisher == 'microsoftwindowsserver' and
            offer == 'windowsserversemiannual' and
            sku == 'datacenter-core-1709-with-containers-smalldisk'):
        return ({
            'publisher': publisher,
            'offer': offer,
            'sku': sku,
            'version': pool_settings.vm_configuration.version,
        }, 'batch.node.windows amd64')
    # pick latest sku
    node_agent_skus = batch_client.account.list_node_agent_skus()
    skus_to_use = [
        (nas, image_ref) for nas in node_agent_skus
        for image_ref in sorted(
            nas.verified_image_references,
            key=lambda item: item.sku
        )
        if image_ref.publisher.lower() == publisher and
        image_ref.offer.lower() == offer and
        image_ref.sku.lower() == sku
    ]
    try:
        sku_to_use, image_ref_to_use = skus_to_use[-1]
    except IndexError:
        raise RuntimeError(
            ('Could not find an Azure Batch Node Agent Sku for this '
             'offer={} publisher={} sku={}. You can list the valid and '
             'available Marketplace images with the command: pool '
             'listskus').format(
                 pool_settings.vm_configuration.offer,
                 pool_settings.vm_configuration.publisher,
                 pool_settings.vm_configuration.sku))
    # set image version to use
    image_ref_to_use.version = pool_settings.vm_configuration.version
    logger.info('deploying vm config: {}'.format(image_ref_to_use))
    return (image_ref_to_use, sku_to_use.id)


def _explode_arm_subnet_id(arm_subnet_id):
    # type: (str) -> Tuple[str, str, str, str, str]
    """Parses components from ARM subnet id
    :param str arm_subnet_id: ARM subnet id
    :rtype: tuple
    :return: subid, rg, provider, vnet, subnet
    """
    tmp = arm_subnet_id.split('/')
    try:
        subid = tmp[2]
        rg = tmp[4]
        provider = tmp[6]
        vnet = tmp[8]
        subnet = tmp[10]
    except IndexError:
        raise ValueError(
            'Error parsing arm_subnet_id. Make sure the virtual network '
            'resource id is correct and is postfixed with the '
            '/subnets/<subnet_id> portion.')
    return subid, rg, provider, vnet, subnet


def _check_for_batch_aad(bc, rmsg):
    # type: (settings.BatchCredentialSettings, str) -> None
    """Check for Batch AAD
    :param settings.BatchCredentialsSettings bc: batch cred settings
    :param str rmsg: error message
    """
    if util.is_not_empty(bc.account_key):
        raise RuntimeError(
            'Cannot {} without Batch AAD credentials. Please ensure that '
            'an "account_key" is not specified under the "batch" section in '
            'credentials and an "aad" section is specified either directly '
            'under "credentials" or under "batch".')


def _pool_virtual_network_subnet_address_space_check(
        resource_client, network_client, config, pool_settings, bc):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict,
    #        settings.PoolSettings, settings.BatchCredentialsSettings) -> str
    """Pool Virtual Network and subnet address space check and create if
    specified
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param settings.PoolSettings pool_settings: pool settings
    :param settings.BatchCredentialsSettings bc: batch cred settings
    :rtype: str
    :return: subnet id
    """
    if (util.is_none_or_empty(pool_settings.virtual_network.arm_subnet_id) and
            util.is_none_or_empty(pool_settings.virtual_network.name)):
        logger.debug('no virtual network settings specified')
        return None
    # check if AAD is enabled
    _check_for_batch_aad(bc, 'allocate a pool with a virtual network')
    # get subnet object
    subnet_id = None
    if util.is_not_empty(pool_settings.virtual_network.arm_subnet_id):
        subnet_components = _explode_arm_subnet_id(
            pool_settings.virtual_network.arm_subnet_id)
        logger.debug(
            ('arm subnet id breakdown: subid={} rg={} provider={} vnet={} '
             'subnet={}').format(
                 subnet_components[0], subnet_components[1],
                 subnet_components[2], subnet_components[3],
                 subnet_components[4]))
        subnet_id = pool_settings.virtual_network.arm_subnet_id
        if network_client is None:
            logger.info('using virtual network subnet id: {}'.format(
                subnet_id))
            logger.warning(
                'cannot perform IP space validation without a valid '
                'network_client, please specify management AAD credentials '
                'to allow pre-validation')
            return subnet_id
        # retrieve address prefix for subnet
        _subnet = network_client.subnets.get(
            subnet_components[1], subnet_components[3], subnet_components[4])
    else:
        if util.is_not_empty(pool_settings.virtual_network.resource_group):
            _vnet_rg = pool_settings.virtual_network.resource_group
        else:
            _vnet_rg = bc.resource_group
        # create virtual network and subnet if specified
        _, _subnet = resource.create_virtual_network_and_subnet(
            resource_client, network_client, _vnet_rg, bc.location,
            pool_settings.virtual_network)
        del _vnet_rg
        subnet_id = _subnet.id
    # ensure address prefix for subnet is valid
    tmp = _subnet.address_prefix.split('/')
    if len(tmp) <= 1:
        raise RuntimeError(
            'subnet address_prefix is invalid for Batch pools: {}'.format(
                _subnet.address_prefix))
    mask = int(tmp[-1])
    # subtract 5 for guideline and Azure numbering start
    allowable_addresses = (1 << (32 - mask)) - 5
    logger.debug('subnet {} mask is {} and allows {} addresses'.format(
        _subnet.name, mask, allowable_addresses))
    pool_total_vm_count = (
        pool_settings.vm_count.dedicated +
        pool_settings.vm_count.low_priority
    )
    if allowable_addresses < pool_total_vm_count:
        raise RuntimeError(
            ('subnet {} mask is {} and allows {} addresses but desired '
             'pool vm_count is {}').format(
                 _subnet.name, mask, allowable_addresses, pool_total_vm_count))
    elif int(allowable_addresses * 0.9) <= pool_total_vm_count:
        # if within 90% tolerance, warn user due to potential
        # address shortage if other compute resources are in this subnet
        if not util.confirm_action(
                config,
                msg=('subnet {} mask is {} and allows {} addresses '
                     'but desired pool vm_count is {}, proceed?').format(
                         _subnet.name, mask, allowable_addresses,
                         pool_total_vm_count)):
            raise RuntimeError('Pool deployment rejected by user')
    logger.info('using virtual network subnet id: {}'.format(subnet_id))
    return subnet_id


def _construct_pool_object(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, config):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.mgmt.batch.BatchManagementClient,
    #        azure.batch.batch_service_client.BatchServiceClient,
    #        azure.storage.blob.BlockBlobService, dict) -> None
    """Construct a pool add parameter object for create pool along with
    uploading resource files
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    """
    # check shared data volume mounts before proceeding to allocate
    azureblob_vd = False
    azurefile_vd = False
    gluster_on_compute = False
    storage_cluster_mounts = []
    custom_linux_mounts = []
    try:
        sdv = settings.global_resources_shared_data_volumes(config)
        for sdvkey in sdv:
            if settings.is_shared_data_volume_azure_file(sdv, sdvkey):
                azurefile_vd = True
            elif settings.is_shared_data_volume_azure_blob(sdv, sdvkey):
                azureblob_vd = True
            elif settings.is_shared_data_volume_gluster_on_compute(
                    sdv, sdvkey):
                if gluster_on_compute:
                    raise ValueError(
                        'only one glusterfs on compute can be created')
                gluster_on_compute = True
            elif settings.is_shared_data_volume_storage_cluster(
                    sdv, sdvkey):
                storage_cluster_mounts.append(sdvkey)
            elif settings.is_shared_data_volume_custom_linux_mount(
                    sdv, sdvkey):
                custom_linux_mounts.append(sdvkey)
            else:
                raise ValueError('Unknown shared data volume: {}'.format(
                    settings.shared_data_volume_driver(sdv, sdvkey)))
    except KeyError:
        pass
    # retrieve settings
    pool_settings = settings.pool_settings(config)
    native = settings.is_native_docker_pool(
        config, vm_config=pool_settings.vm_configuration)
    is_windows = settings.is_windows_pool(
        config, vm_config=pool_settings.vm_configuration)
    # get autoscale settings
    if settings.is_pool_autoscale_enabled(config, pas=pool_settings.autoscale):
        asenable = True
        asformula = autoscale.get_formula(pool_settings)
        asei = pool_settings.autoscale.evaluation_interval
        if pool_settings.resize_timeout is not None:
            logger.warning(
                'ignoring resize timeout for autoscale-enabled pool')
    else:
        asenable = False
        asformula = None
        asei = None
    logger.debug('autoscale enabled: {}'.format(asenable))
    # task scheduling policy settings
    if util.is_not_empty(pool_settings.node_fill_type):
        task_scheduling_policy = batchmodels.TaskSchedulingPolicy(
            node_fill_type=batchmodels.ComputeNodeFillType(
                pool_settings.node_fill_type),
        )
    else:
        task_scheduling_policy = None
    # custom image settings
    custom_image_na = settings.pool_custom_image_node_agent(config)
    # check for virtual network settings
    bc = settings.credentials_batch(config)
    subnet_id = _pool_virtual_network_subnet_address_space_check(
        resource_client, network_client, config, pool_settings, bc)
    # construct fstab mounts for storage clusters
    sc_fstab_mounts = []
    sc_args = []
    if util.is_not_empty(storage_cluster_mounts):
        for sc_id in storage_cluster_mounts:
            fm, sca = _create_storage_cluster_mount_args(
                compute_client, network_client, batch_mgmt_client, config,
                sc_id, bc, subnet_id)
            sc_fstab_mounts.append(fm)
            sc_args.append(sca)
        if settings.verbose(config):
            logger.debug('storage cluster args: {}'.format(sc_args))
    del storage_cluster_mounts
    # constrcut fstab mounts for custom mounts
    custom_linux_fstab_mounts = []
    if util.is_not_empty(custom_linux_mounts):
        for id in custom_linux_mounts:
            custom_linux_fstab_mounts.append(
                _create_custom_linux_mount_args(config, id))
    del custom_linux_mounts
    # add encryption cert to account if specified
    encrypt = settings.batch_shipyard_encryption_enabled(config)
    if encrypt:
        pfx = crypto.get_encryption_pfx_settings(config)
        batch.add_certificate_to_account(
            batch_client, config, None, False, False, None)
    # construct block list
    block_for_gr = None
    if pool_settings.block_until_all_global_resources_loaded:
        block_for_gr_docker = ''
        block_for_gr_singularity = ''
        docker_images = settings.global_resources_docker_images(config)
        if len(docker_images) > 0:
            block_for_gr_docker = ','.join([x for x in docker_images])
        singularity_images = settings.global_resources_singularity_images(
            config)
        if len(singularity_images) > 0:
            block_for_gr_singularity = ','.join(
                [util.singularity_image_name_on_disk(x)
                 for x in singularity_images])
        if (util.is_none_or_empty(block_for_gr_docker) and
                util.is_none_or_empty(block_for_gr_singularity)):
            logger.warning(
                'no Docker and Singularity images specified in global '
                'resources')
        if native:
            # native pools will auto preload
            block_for_gr_docker = ''
        block_for_gr = '{}#{}'.format(
            block_for_gr_docker, block_for_gr_singularity)
    # shipyard settings
    bs = settings.batch_shipyard_settings(config)
    # data replication and peer-to-peer settings
    dr = settings.data_replication_settings(config)
    # create torrent flags
    torrentflags = '{}:{}:{}:{}'.format(
        dr.peer_to_peer.enabled, dr.concurrent_source_downloads,
        dr.peer_to_peer.direct_download_seed_bias,
        dr.peer_to_peer.compression)
    # create resource files list
    if is_windows:
        _rflist = [_REGISTRY_LOGIN_WINDOWS_FILE, _BLOBXFER_WINDOWS_FILE]
    else:
        _rflist = [_REGISTRY_LOGIN_FILE, _BLOBXFER_FILE]
    if not native and not is_windows:
        _rflist.append(_IMAGE_BLOCK_FILE)
        if not bs.use_shipyard_docker_image:
            _rflist.append(_CASCADE_FILE)
            if bs.store_timing_metrics:
                _rflist.append(_PERF_FILE)
    if pool_settings.ssh.hpn_server_swap:
        _rflist.append(_HPNSSH_FILE)
    # handle azure mounts
    if azureblob_vd:
        abms = _setup_azureblob_mounts(blob_client, config, bc)
        _rflist.append(('azureblob-mount.sh', abms))
    if azurefile_vd:
        afms = _setup_azurefile_mounts(blob_client, config, bc, is_windows)
        _rflist.append(
            ('azurefile-mount.{}'.format('cmd' if is_windows else 'sh'), afms)
        )
    # lis settings
    if (not is_windows and not native and
            util.is_none_or_empty(custom_image_na)):
        lis_pkg = _setup_lis_package(config, pool_settings.vm_size)
        if lis_pkg is not None:
            _rflist.append((lis_pkg.name, lis_pkg))
    else:
        lis_pkg = None
    # gpu settings
    if (not native and settings.is_gpu_pool(pool_settings.vm_size) and
            util.is_none_or_empty(custom_image_na)):
        if pool_settings.gpu_driver is None:
            gpu_driver = _setup_nvidia_driver_package(
                config, pool_settings.vm_size)
            _rflist.append((gpu_driver.name, gpu_driver))
        else:
            gpu_type = settings.get_gpu_type_from_vm_size(
                pool_settings.vm_size)
            gpu_driver = pathlib.Path(_NVIDIA_DRIVER[gpu_type]['target'])
        gpu_env = '{}:{}'.format(
            settings.is_gpu_visualization_pool(pool_settings.vm_size),
            gpu_driver.name)
    else:
        gpu_env = None
    # prometheus settings
    if (not is_windows and
            (pool_settings.prometheus.ne_enabled or
             pool_settings.prometheus.ca_enabled)):
        ne_pkg, ca_pkg = _setup_prometheus_monitoring_tools(pool_settings)
        if pool_settings.prometheus.ne_enabled:
            _rflist.append((ne_pkg.name, ne_pkg))
        if pool_settings.prometheus.ca_enabled:
            _rflist.append((ca_pkg.name, ca_pkg))
    # get container registries
    docker_registries = settings.docker_registries(config)
    # set additional start task commands (pre version)
    start_task = pool_settings.additional_node_prep_commands_pre
    # set vm configuration
    if native:
        if util.is_not_empty(custom_image_na):
            # check if AAD is enabled
            _check_for_batch_aad(bc, 'allocate a pool with a custom image')
            vmconfig = batchmodels.VirtualMachineConfiguration(
                image_reference=batchmodels.ImageReference(
                    virtual_machine_image_id=pool_settings.
                    vm_configuration.arm_image_id,
                ),
                node_agent_sku_id=pool_settings.vm_configuration.node_agent,
                license_type=pool_settings.vm_configuration.license_type,
            )
            logger.debug(
                ('deploying custom image to pool in native mode: {} '
                 'node agent: {}').format(
                     vmconfig.image_reference.virtual_machine_image_id,
                     vmconfig.node_agent_sku_id))
        else:
            image_ref, na_ref = _pick_node_agent_for_vm(
                batch_client, config, pool_settings)
            vmconfig = batchmodels.VirtualMachineConfiguration(
                image_reference=image_ref,
                node_agent_sku_id=na_ref,
                license_type=pool_settings.vm_configuration.license_type,
            )
            logger.debug('deploying pool in native mode')
        # attach container config
        vmconfig.container_configuration = batchmodels.ContainerConfiguration(
            container_image_names=settings.global_resources_docker_images(
                config),
            container_registries=docker_registries,
        )
    elif util.is_not_empty(custom_image_na):
        # check if AAD is enabled
        _check_for_batch_aad(bc, 'allocate a pool with a custom image')
        vmconfig = batchmodels.VirtualMachineConfiguration(
            image_reference=batchmodels.ImageReference(
                virtual_machine_image_id=pool_settings.
                vm_configuration.arm_image_id,
            ),
            node_agent_sku_id=pool_settings.vm_configuration.node_agent,
            license_type=pool_settings.vm_configuration.license_type,
        )
        logger.debug('deploying custom image: {} node agent: {}'.format(
            vmconfig.image_reference.virtual_machine_image_id,
            vmconfig.node_agent_sku_id))
    else:
        image_ref, na_ref = _pick_node_agent_for_vm(
            batch_client, config, pool_settings)
        vmconfig = batchmodels.VirtualMachineConfiguration(
            image_reference=image_ref,
            node_agent_sku_id=na_ref,
            license_type=pool_settings.vm_configuration.license_type,
        )
    # modify rflist and start task for node prep script
    if is_windows:
        if util.is_not_empty(custom_image_na):
            raise RuntimeError(
                'Native mode and Windows custom images is not supported')
        _rflist.append(_NODEPREP_WINDOWS_FILE)
        # create start task commandline
        start_task.append(
            ('powershell -ExecutionPolicy Unrestricted -command '
             '{npf}{a}{e}{u}{v}{x}').format(
                 npf=_NODEPREP_WINDOWS_FILE[0],
                 a=' -a' if azurefile_vd else '',
                 e=' -e {}'.format(pfx.sha1) if encrypt else '',
                 u=' -u' if util.is_not_empty(custom_image_na) else '',
                 v=' -v {}'.format(__version__),
                 x=' -x {}'.format(data._BLOBXFER_VERSION))
        )
    else:
        _rflist.append(_NODEPREP_FILE)
        # create start task commandline
        start_task.append(
            ('{npf}{a}{b}{c}{d}{e}{f}{g}{lis}{m}{n}{p}{s}{t}{u}'
             '{v}{w}{x}').format(
                npf=_NODEPREP_FILE[0],
                a=' -a' if azurefile_vd else '',
                b=' -b' if util.is_not_empty(block_for_gr) else '',
                c=' -c' if azureblob_vd else '',
                d=' -d' if bs.use_shipyard_docker_image else '',
                e=' -e {}'.format(pfx.sha1) if encrypt else '',
                f=' -f' if gluster_on_compute else '',
                g=' -g {}'.format(gpu_env) if gpu_env is not None else '',
                lis=' -l {}'.format(
                    lis_pkg.name) if lis_pkg is not None else '',
                m=' -m {}'.format(','.join(sc_args)) if util.is_not_empty(
                    sc_args) else '',
                n=' -n' if native else '',
                p=' -p {}'.format(bs.storage_entity_prefix) if (
                    bs.storage_entity_prefix) else '',
                s=' -s {}'.format(torrentflags),
                t=' -t' if settings.can_tune_tcp(
                    pool_settings.vm_size) else '',
                u=' -u' if util.is_not_empty(custom_image_na) else '',
                v=' -v {}'.format(__version__),
                w=' -w' if pool_settings.ssh.hpn_server_swap else '',
                x=' -x {}'.format(data._BLOBXFER_VERSION),
            )
        )
    # upload resource files
    sas_urls = storage.upload_resource_files(blob_client, config, _rflist)
    del _rflist
    # remove temporary az mount files created
    if azureblob_vd:
        try:
            abms.unlink()
            pass
        except OSError:
            pass
    if azurefile_vd:
        try:
            afms.unlink()
        except OSError:
            pass
    # digest any input data
    addlcmds = data.process_input_data(
        config, _BLOBXFER_WINDOWS_FILE if is_windows else _BLOBXFER_FILE,
        settings.pool_specification(config))
    if addlcmds is not None:
        start_task.append(addlcmds)
    del addlcmds
    # add additional start task commands (post version)
    start_task.extend(pool_settings.additional_node_prep_commands_post)
    # create pool param
    pool = batchmodels.PoolAddParameter(
        id=pool_settings.id,
        virtual_machine_configuration=vmconfig,
        vm_size=pool_settings.vm_size,
        target_dedicated_nodes=(
            pool_settings.vm_count.dedicated if not asenable else None
        ),
        target_low_priority_nodes=(
            pool_settings.vm_count.low_priority if not asenable else None
        ),
        resize_timeout=pool_settings.resize_timeout if not asenable else None,
        max_tasks_per_node=pool_settings.max_tasks_per_node,
        enable_inter_node_communication=pool_settings.
        inter_node_communication_enabled,
        start_task=batchmodels.StartTask(
            command_line=util.wrap_commands_in_shell(
                start_task, windows=is_windows, wait=False),
            user_identity=batch._RUN_ELEVATED,
            wait_for_success=True,
            environment_settings=[
                batchmodels.EnvironmentSetting('LC_ALL', 'en_US.UTF-8'),
            ],
            resource_files=[],
        ),
        enable_auto_scale=asenable,
        auto_scale_formula=asformula,
        auto_scale_evaluation_interval=asei,
        metadata=[
            batchmodels.MetadataItem(
                name=settings.get_metadata_version_name(),
                value=__version__,
            ),
        ],
        task_scheduling_policy=task_scheduling_policy,
        certificate_references=[]
    )
    if encrypt:
        if is_windows:
            pool.certificate_references.append(
                batchmodels.CertificateReference(
                    pfx.sha1, 'sha1',
                    visibility=[
                        batchmodels.CertificateVisibility.start_task,
                        batchmodels.CertificateVisibility.task,
                    ]
                )
            )
        else:
            pool.certificate_references.append(
                batchmodels.CertificateReference(
                    pfx.sha1, 'sha1',
                    visibility=[batchmodels.CertificateVisibility.start_task]
                )
            )
    if util.is_not_empty(pool_settings.certificates):
        pool.certificate_references.extend(pool_settings.certificates)
    for rf in sas_urls:
        pool.start_task.resource_files.append(
            batchmodels.ResourceFile(
                file_path=rf,
                blob_source=sas_urls[rf])
        )
    if not native:
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'SHIPYARD_STORAGE_ENV',
                crypto.encrypt_string(
                    encrypt, '{}:{}:{}'.format(
                        storage.get_storageaccount(),
                        storage.get_storageaccount_endpoint(),
                        storage.get_storageaccount_key()),
                    config)
            )
        )
        if pool_settings.gpu_driver and util.is_none_or_empty(custom_image_na):
            pool.start_task.resource_files.append(
                batchmodels.ResourceFile(
                    file_path=gpu_driver.name,
                    blob_source=pool_settings.gpu_driver,
                    file_mode='0755')
            )
    # add any additional specified resource files
    if util.is_not_empty(pool_settings.resource_files):
        for rf in pool_settings.resource_files:
            pool.start_task.resource_files.append(
                batchmodels.ResourceFile(
                    file_path=rf.file_path,
                    blob_source=rf.blob_source,
                    file_mode=rf.file_mode,
                )
            )
    # network settings (subnet and/or remote access control)
    if (subnet_id is not None or
            pool_settings.remote_access_control.allow is not None or
            pool_settings.remote_access_control.deny is not None):
        priority = 150
        rules = []
        inp = batchmodels.InboundNATPool(
            name='BatchShipyard-RemoteAccessControl',
            protocol=pool_settings.remote_access_control.protocol,
            backend_port=pool_settings.remote_access_control.backend_port,
            frontend_port_range_start=pool_settings.remote_access_control.
            starting_port,
            frontend_port_range_end=pool_settings.remote_access_control.
            starting_port + 999,
            network_security_group_rules=rules,
        )
        if pool_settings.remote_access_control.allow is not None:
            for ar in pool_settings.remote_access_control.allow:
                rules.append(batchmodels.NetworkSecurityGroupRule(
                    priority=priority,
                    access=batchmodels.NetworkSecurityGroupRuleAccess.allow,
                    source_address_prefix=ar,
                ))
                priority += 1
        if pool_settings.remote_access_control.deny is not None:
            for dr in pool_settings.remote_access_control.deny:
                rules.append(batchmodels.NetworkSecurityGroupRule(
                    priority=priority,
                    access=batchmodels.NetworkSecurityGroupRuleAccess.deny,
                    source_address_prefix=dr,
                ))
                priority += 1
        if util.is_not_empty(rules):
            pec = batchmodels.PoolEndpointConfiguration(
                inbound_nat_pools=[inp],
            )
        else:
            pec = None
        # add subnet and NAT rules
        pool.network_configuration = batchmodels.NetworkConfiguration(
            subnet_id=subnet_id,
            endpoint_configuration=pec,
        )
    # storage cluster settings
    if util.is_not_empty(sc_fstab_mounts):
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'SHIPYARD_STORAGE_CLUSTER_FSTAB',
                '#'.join(sc_fstab_mounts)
            )
        )
        del sc_args
        del sc_fstab_mounts
    # custom linux mount settings
    if util.is_not_empty(custom_linux_fstab_mounts):
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'SHIPYARD_CUSTOM_MOUNTS_FSTAB',
                '#'.join(custom_linux_fstab_mounts)
            )
        )
        del custom_linux_fstab_mounts
    # add optional environment variables
    if not native and bs.store_timing_metrics:
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('SHIPYARD_TIMING', '1')
        )
    # add docker login settings
    pool.start_task.environment_settings.extend(
        batch.generate_docker_login_settings(config)[0])
    # image preload setting
    if util.is_not_empty(block_for_gr):
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'SHIPYARD_CONTAINER_IMAGES_PRELOAD',
                block_for_gr,
            )
        )
    # Linux-only settings
    if not is_windows:
        # singularity env vars
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'SINGULARITY_TMPDIR',
                settings.get_singularity_tmpdir(config)
            )
        )
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'SINGULARITY_CACHEDIR',
                settings.get_singularity_cachedir(config)
            )
        )
        # prometheus env vars
        if pool_settings.prometheus.ne_enabled:
            pool.start_task.environment_settings.append(
                batchmodels.EnvironmentSetting(
                    'PROM_NODE_EXPORTER_PORT',
                    pool_settings.prometheus.ne_port
                )
            )
            if util.is_not_empty(pool_settings.prometheus.ne_options):
                pool.start_task.environment_settings.append(
                    batchmodels.EnvironmentSetting(
                        'PROM_NODE_EXPORTER_OPTIONS',
                        ','.join(pool_settings.prometheus.ne_options)
                    )
                )
        if pool_settings.prometheus.ca_enabled:
            pool.start_task.environment_settings.append(
                batchmodels.EnvironmentSetting(
                    'PROM_CADVISOR_PORT',
                    pool_settings.prometheus.ca_port
                )
            )
            if util.is_not_empty(pool_settings.prometheus.ca_options):
                pool.start_task.environment_settings.append(
                    batchmodels.EnvironmentSetting(
                        'PROM_CADVISOR_OPTIONS',
                        ','.join(pool_settings.prometheus.ca_options)
                    )
                )
    return (pool_settings, gluster_on_compute, pool)


def _construct_auto_pool_specification(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, config):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.mgmt.batch.BatchManagementClient,
    #        azure.batch.batch_service_client.BatchServiceClient,
    #        azure.storage.blob.BlockBlobService, dict) -> None
    """Construct an auto pool specification
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    """
    # upload resource files and construct pool add parameter object
    pool_settings, gluster_on_compute, pool = _construct_pool_object(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, config)
    # convert pool add parameter object to a pool specification object
    poolspec = batchmodels.PoolSpecification(
        vm_size=pool.vm_size,
        virtual_machine_configuration=pool.virtual_machine_configuration,
        max_tasks_per_node=pool.max_tasks_per_node,
        task_scheduling_policy=pool.task_scheduling_policy,
        resize_timeout=pool.resize_timeout,
        target_dedicated_nodes=pool.target_dedicated_nodes,
        target_low_priority_nodes=pool.target_low_priority_nodes,
        enable_auto_scale=pool.enable_auto_scale,
        auto_scale_formula=pool.auto_scale_formula,
        auto_scale_evaluation_interval=pool.auto_scale_evaluation_interval,
        enable_inter_node_communication=pool.enable_inter_node_communication,
        network_configuration=pool.network_configuration,
        start_task=pool.start_task,
        certificate_references=pool.certificate_references,
        metadata=pool.metadata,
    )
    # add auto pool env var for cascade
    poolspec.start_task.environment_settings.append(
        batchmodels.EnvironmentSetting('SHIPYARD_AUTOPOOL', 1)
    )
    return poolspec


def _add_pool(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, config):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.mgmt.batch.BatchManagementClient,
    #        azure.batch.batch_service_client.BatchServiceClient,
    #        azure.storage.blob.BlockBlobService, dict) -> None
    """Add a Batch pool to account
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    """
    # upload resource files and construct pool add parameter object
    pool_settings, gluster_on_compute, pool = _construct_pool_object(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, config)
    # ingress data to Azure Blob Storage if specified
    storage_threads = []
    if pool_settings.transfer_files_on_pool_creation:
        storage_threads = data.ingress_data(
            batch_client, compute_client, network_client, config, rls=None,
            kind='storage')
    # create pool
    nodes = batch.create_pool(batch_client, config, pool)
    _pool = batch_client.pool.get(pool.id)
    pool_current_vm_count = (
        _pool.current_dedicated_nodes + _pool.current_low_priority_nodes
    )
    pool_target_vm_count = (
        _pool.target_dedicated_nodes + _pool.target_low_priority_nodes
    )
    if util.is_none_or_empty(nodes) and pool_target_vm_count > 0:
        raise RuntimeError(
            ('No nodes could be allocated for pool: {}. If the pool is '
             'comprised entirely of low priority nodes, then there may not '
             'have been enough available capacity in the region to satisfy '
             'your request. Please inspect the pool for resize errors and '
             'issue pool resize to try again.').format(pool.id))
    # set up gluster on compute if specified
    if gluster_on_compute and pool_current_vm_count > 0:
        _setup_glusterfs(
            batch_client, blob_client, config, nodes, _GLUSTERPREP_FILE,
            cmdline=None)
    # create admin user on each node if requested
    if pool_current_vm_count > 0:
        try:
            batch.add_rdp_user(batch_client, config, nodes)
        except Exception as e:
            logger.exception(e)
        try:
            batch.add_ssh_user(batch_client, config, nodes)
        except Exception as e:
            logger.exception(e)
            logger.error(
                'Could not add SSH users to nodes. Please ensure ssh-keygen '
                'is available in your PATH or cwd. Skipping data ingress if '
                'specified.')
        else:
            rls = None
            # ingress data to shared fs if specified
            if pool_settings.transfer_files_on_pool_creation:
                if rls is None:
                    rls = batch.get_remote_login_settings(
                        batch_client, config, nodes=nodes,
                        suppress_output=True)
                data.ingress_data(
                    batch_client, compute_client, network_client, config,
                    rls=rls, kind='shared',
                    total_vm_count=pool_current_vm_count)
            # log remote login settings
            if rls is None:
                if pool_current_vm_count <= 100:
                    batch.get_remote_login_settings(
                        batch_client, config, nodes=nodes,
                        suppress_output=False)
                else:
                    logger.info(
                        'Not listing remote login settings due to VM count. '
                        'If you need a list of remote login settings for all '
                        'nodes in the pool, issue the "pool nodes grls" '
                        'command.')
    # wait for storage ingress processes
    data.wait_for_storage_threads(storage_threads)


def _setup_glusterfs(
        batch_client, blob_client, config, nodes, shell_script, cmdline=None):
    # type: (batchsc.BatchServiceClient, azure.storage.blob.BlockBlobService,
    #        dict, List[batchmodels.ComputeNode], str, str) -> None
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
    voltype = None
    volopts = None
    sdv = settings.global_resources_shared_data_volumes(config)
    for sdvkey in sdv:
        try:
            if settings.is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
                voltype = settings.gluster_volume_type(sdv, sdvkey)
                volopts = settings.gluster_volume_options(sdv, sdvkey)
                break
        except KeyError:
            pass
    if voltype is None:
        raise RuntimeError('glusterfs volume not defined')
    pool_id = settings.pool_id(config)
    job_id = 'shipyard-glusterfs-{}'.format(uuid.uuid4())
    job = batchmodels.JobAddParameter(
        id=job_id,
        pool_info=batchmodels.PoolInformation(pool_id=pool_id),
    )
    # create coordination command line
    if cmdline is None:
        tempdisk = settings.temp_disk_mountpoint(config)
        cmdline = util.wrap_commands_in_shell([
            '$AZ_BATCH_TASK_DIR/{} {} {}'.format(
                shell_script[0], voltype.lower(), tempdisk)])
    # create application command line
    appcmd = [
        '[[ -f $AZ_BATCH_TASK_WORKING_DIR/.glusterfs_success ]] || exit 1',
    ]
    if volopts is not None:
        for vo in volopts:
            appcmd.append('gluster volume set {} {}'.format(
                settings.get_gluster_default_volume_name(), vo))
    # upload script
    sas_urls = storage.upload_resource_files(
        blob_client, config, [shell_script])
    # get pool current dedicated
    pool = batch_client.pool.get(pool_id)
    batchtask = batchmodels.TaskAddParameter(
        id='gluster-setup',
        multi_instance_settings=batchmodels.MultiInstanceSettings(
            number_of_instances=pool.current_dedicated_nodes,
            coordination_command_line=cmdline,
            common_resource_files=[
                batchmodels.ResourceFile(
                    file_path=shell_script[0],
                    blob_source=sas_urls[shell_script[0]],
                    file_mode='0755'),
            ],
        ),
        command_line=util.wrap_commands_in_shell(appcmd),
        user_identity=batch._RUN_ELEVATED,
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
            batch_client.file.get_properties_from_compute_node(
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


def _execute_command_on_pool_over_ssh_with_keyed_output(
        batch_client, config, pool, desc, cmd):
    # type: (batchsc.BatchServiceClient, dict, batchmodels.CloudPool, str,
    #        list) -> dict
    """Execute a command on all nodes in pool over ssh
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param batchmodels.CloudPool pool: cloud pool
    :param str desc: description of action
    :param list cmd: command
    :rtype: dict
    :return: keyed stdout by node id
    """
    # TODO NYI disable SSH commands with windows pools
    is_windows = settings.is_windows_pool(config)
    if is_windows:
        raise RuntimeError(
            '{} is currently not supported for windows pools'.format(desc))
    # check if there are nodes to run command on
    if (pool.current_dedicated_nodes == 0 and
            pool.current_low_priority_nodes == 0):
        logger.warning('pool {} has no compute nodes'.format(pool.id))
        return
    _pool = settings.pool_settings(config)
    # get ssh settings
    username = _pool.ssh.username
    if util.is_none_or_empty(username):
        raise ValueError(
            'cannot {} without an SSH username'.format(desc))
    ssh_private_key = _pool.ssh.ssh_private_key
    if ssh_private_key is None:
        ssh_private_key = pathlib.Path(
            _pool.ssh.generated_file_export_path, crypto.get_ssh_key_prefix())
    if not ssh_private_key.exists():
        raise RuntimeError('SSH private key file not found at: {}'.format(
            ssh_private_key))
    # set command
    command = ['sudo', '/bin/bash -c \'{}\''.format(' && '.join(cmd))]
    if settings.verbose(config):
        logger.debug('executing command: {}'.format(command))
    # iterate through all nodes
    nodes = batch_client.compute_node.list(pool.id)
    procs = {}
    stdout = {}
    stderr = {}
    failures = False
    for node in nodes:
        rls = batch_client.compute_node.get_remote_login_settings(
            pool.id, node.id)
        procs[node.id] = crypto.connect_or_exec_ssh_command(
            rls.remote_login_ip_address, rls.remote_login_port,
            ssh_private_key, username, sync=False, tty=False,
            command=command)
        if len(procs) >= 40:
            logger.debug('waiting for {} processes to complete'.format(
                len(procs)))
            for key in procs:
                stdout[key], stderr[key] = procs[key].communicate()
            rcs, _, _ = util.subprocess_wait_all(
                list(procs.values()), poll=True)
            if any([x != 0 for x in rcs]):
                if settings.verbose(config):
                    logger.warning('return codes: {}'.format(rcs))
                    logger.warning('stdout: {}'.format(stdout))
                    logger.warning('stderr: {}'.format(stderr))
                failures = True
            procs = []
            del rcs
    if len(procs) > 0:
        logger.debug('waiting for {} processes to complete'.format(
            len(procs)))
        for key in procs:
            stdout[key], stderr[key] = procs[key].communicate()
        rcs, _, _ = util.subprocess_wait_all(list(procs.values()), poll=True)
        if any([x != 0 for x in rcs]):
            if settings.verbose(config):
                logger.warning('return codes: {}'.format(rcs))
                logger.warning('stdout: {}'.format(stdout))
                logger.warning('stderr: {}'.format(stderr))
            failures = True
        del procs
        del rcs
    if failures:
        raise RuntimeError(
            'failures detected performing {} on pool: {}'.format(
                desc, pool.id))
    else:
        logger.info('{} completed for pool: {}'.format(desc, pool.id))
    return stdout


def _log_stdout_by_nodeid(config, pool_id, desc, stdout):
    # type: (dict, str, str, list) -> None
    """Log stdout returned by keyed SSH remote execution
    :param dict config: configuration dict
    :param str pool_id: pool id
    :param str desc: description
    :param list stdout: keyed stdout by node id
    """
    if settings.raw(config):
        raw = {
            'pool_id': pool_id,
            'nodes': {},
        }
        for key in stdout:
            raw['nodes'][key] = []
            for line in stdout[key].split('\n'):
                if len(line) == 0:
                    continue
                raw['nodes'][key].append(line)
        util.print_raw_json(raw)
    else:
        log = [
            'stdout for {} on pool {}'.format(desc, pool_id)
        ]
        for key in stdout:
            log.append('* node id: {}'.format(key))
            for line in stdout[key].split('\n'):
                if len(line) == 0:
                    continue
                log.append('  >> {}'.format(line))
        logger.info(os.linesep.join(log))


def _docker_system_prune_over_ssh(batch_client, config, volumes):
    # type: (batchsc.BatchServiceClient, dict, bool) -> None
    """Prune docker system data over ssh
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool volumes: remove volumes as well
    """
    pool_id = settings.pool_id(config)
    if not util.confirm_action(
            config,
            msg='prune all unused Docker data on pool {}'.format(pool_id)):
        return
    pool = batch_client.pool.get(pool_id)
    desc = 'prune unused data'
    cmd = [
        'docker system prune -f{}'.format(' --volumes' if volumes else '')
    ]
    stdout = _execute_command_on_pool_over_ssh_with_keyed_output(
        batch_client, config, pool, desc, cmd)
    _log_stdout_by_nodeid(config, pool_id, desc, stdout)


def _zap_all_container_processes_over_ssh(batch_client, config, remove, stop):
    # type: (batchsc.BatchServiceClient, dict, bool, bool) -> None
    """Zap all docker container processes over ssh
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param bool remove: remove exited containers as well
    :param bool stop: docker stop instead of kill
    """
    pool_id = settings.pool_id(config)
    if not util.confirm_action(
            config,
            msg='zap all Docker containers on pool {}'.format(pool_id)):
        return
    pool = batch_client.pool.get(pool_id)
    desc = 'zap all container processes'
    cmd = [
        'docker ps -q | xargs -r docker {}'.format('stop' if stop else 'kill'),
    ]
    if remove:
        cmd.append('docker ps -aq -f status=exited | xargs -r docker rm')
    stdout = _execute_command_on_pool_over_ssh_with_keyed_output(
        batch_client, config, pool, desc, cmd)
    _log_stdout_by_nodeid(config, pool_id, desc, stdout)


def _update_container_images(
        batch_client, config, docker_image=None, docker_image_digest=None,
        singularity_image=None, force_ssh=False):
    # type: (batchsc.BatchServiceClient, dict, str, str, str, bool) -> None
    """Update container images in pool
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    :param str docker_image: docker image to update
    :param str docker_image_digest: digest to update to
    :param str singularity_image: singularity image to update
    :param bool force_ssh: force update over SSH
    """
    # first check that peer-to-peer is disabled for pool
    pool_id = settings.pool_id(config)
    try:
        if settings.data_replication_settings(config).peer_to_peer.enabled:
            raise RuntimeError(
                'cannot update container images for a pool with peer-to-peer '
                'image distribution')
    except KeyError:
        pass
    native = settings.is_native_docker_pool(config)
    if native and not force_ssh:
        logger.debug('forcing update via SSH due to native mode')
        force_ssh = True
    # if image is not specified use images from global config
    singularity_images = None
    if util.is_none_or_empty(docker_image):
        docker_images = settings.global_resources_docker_images(config)
    else:
        # log warning if it doesn't exist in global resources
        if docker_image not in settings.global_resources_docker_images(config):
            logger.warning(
                ('docker image {} is not specified as a global resource '
                 'for pool {}').format(docker_image, pool_id))
        if docker_image_digest is None:
            docker_images = [docker_image]
        else:
            docker_images = ['{}@{}'.format(docker_image, docker_image_digest)]
    if util.is_none_or_empty(singularity_image):
        singularity_images = settings.global_resources_singularity_images(
            config)
    else:
        # log warning if it doesn't exist in global resources
        if (singularity_image not in
                settings.global_resources_singularity_images(config)):
            logger.warning(
                ('singularity image {} is not specified as a global resource '
                 'for pool {}').format(singularity_image, pool_id))
        singularity_images = [singularity_image]
    if (util.is_none_or_empty(docker_images) and
            util.is_none_or_empty(singularity_images)):
        logger.error('no images detected or specified to update')
        return
    # get pool current dedicated
    pool = batch_client.pool.get(pool_id)
    # check pool current vms is > 0. There is no reason to run updateimages
    # if pool has no nodes in it. When the pool is resized up, the nodes
    # will always fetch either :latest if untagged or the latest :tag if
    # updated in the upstream registry
    if (pool.current_dedicated_nodes == 0 and
            pool.current_low_priority_nodes == 0):
        logger.warning(
            ('not executing updateimages command as the current number of '
             'compute nodes is zero for pool {}').format(pool_id))
        return
    # force ssh on some paths
    if not force_ssh:
        if pool.current_low_priority_nodes > 0:
            logger.debug('forcing update via SSH due to low priority nodes')
            force_ssh = True
        if (pool.current_dedicated_nodes > 1 and
                not pool.enable_inter_node_communication):
            logger.debug(
                'forcing update via SSH due to non-internode communicaton '
                'enabled pool')
            force_ssh = True
    # check pool metadata version
    if util.is_none_or_empty(pool.metadata):
        logger.warning('pool version metadata not present')
    else:
        for md in pool.metadata:
            if (md.name == settings.get_metadata_version_name() and
                    md.value != __version__):
                logger.warning(
                    'pool version metadata mismatch: pool={} cli={}'.format(
                        md.value, __version__))
                break
    # perform windows compat checks
    is_windows = settings.is_windows_pool(config)
    if is_windows:
        if force_ssh:
            raise RuntimeError('cannot update images via SSH on windows')
        if util.is_not_empty(singularity_images):
            raise RuntimeError(
                'invalid configuration: windows pool with singularity images')
    # create coordination command line
    # 1. log in again in case of cred expiry
    # 2. pull images with respect to registry
    # 3. tag images that are in a private registry
    # 4. prune docker images with no tag
    taskenv, coordcmd = batch.generate_docker_login_settings(config, force_ssh)
    if util.is_not_empty(docker_images):
        coordcmd.extend(['docker pull {}'.format(x) for x in docker_images])
        coordcmd.append(
            'docker images --filter dangling=true -q --no-trunc | '
            'xargs --no-run-if-empty docker rmi')
    if util.is_not_empty(singularity_images):
        coordcmd.extend([
            'export SINGULARITY_TMPDIR={}'.format(
                settings.get_singularity_tmpdir(config)),
            'export SINGULARITY_CACHEDIR={}'.format(
                settings.get_singularity_cachedir(config)),
        ])
        coordcmd.extend(
            ['singularity pull -F {}'.format(x) for x in singularity_images]
        )
        coordcmd.append('chown -R _azbatch:_azbatchgrp {}'.format(
            settings.get_singularity_cachedir(config)))
    if force_ssh:
        stdout = _execute_command_on_pool_over_ssh_with_keyed_output(
            batch_client, config, pool, 'update container images', coordcmd)
        _log_stdout_by_nodeid(config, pool_id, 'uci', stdout)
        return
    if not is_windows:
        # update taskenv for Singularity
        taskenv.append(
            batchmodels.EnvironmentSetting(
                'SINGULARITY_TMPDIR',
                settings.get_singularity_tmpdir(config)
            )
        )
        taskenv.append(
            batchmodels.EnvironmentSetting(
                'SINGULARITY_CACHEDIR',
                settings.get_singularity_cachedir(config)
            )
        )
    coordcmd = util.wrap_commands_in_shell(coordcmd, windows=is_windows)
    # create job for update
    job_id = 'shipyard-updateimages-{}'.format(uuid.uuid4())
    job = batchmodels.JobAddParameter(
        id=job_id,
        pool_info=batchmodels.PoolInformation(pool_id=pool_id),
    )
    # create task
    batchtask = batchmodels.TaskAddParameter(
        id='update-container-images',
        command_line=coordcmd,
        environment_settings=taskenv,
        user_identity=batch._RUN_ELEVATED,
    )
    # create multi-instance task for pools with more than 1 node
    if pool.current_dedicated_nodes > 1:
        batchtask.multi_instance_settings = batchmodels.MultiInstanceSettings(
            number_of_instances=pool.current_dedicated_nodes,
            coordination_command_line=coordcmd,
        )
        # create application command line
        if is_windows:
            appcmd = util.wrap_commands_in_shell(['rem'], windows=is_windows)
        else:
            appcmd = util.wrap_commands_in_shell([':'], windows=is_windows)
        batchtask.command_line = appcmd
    if settings.verbose(config):
        logger.debug('update command: {}'.format(coordcmd))
    # add job and task
    batch_client.job.add(job)
    batch_client.task.add(job_id=job_id, task=batchtask)
    logger.debug(
        ('waiting for update container images task {} in job {} '
         'to complete').format(batchtask.id, job_id))
    # wait for task to complete
    while True:
        batchtask = batch_client.task.get(job_id, batchtask.id)
        if batchtask.state == batchmodels.TaskState.completed:
            break
        time.sleep(1)
    # stream out the stdout file for diagnosis of issues
    batch.stream_file_and_wait_for_task(
        batch_client, config, filespec='{},{},{}'.format(
            job_id, batchtask.id, 'stdout.txt'))
    # clean up
    batch_client.job.delete(job_id)
    if batchtask.execution_info.exit_code != 0:
        raise RuntimeError('update container images job failed')
    logger.info(
        'update container images task {} in job {} completed'.format(
            batchtask.id, job_id))


def _docker_ps_over_ssh(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """docker ps in pool over ssh
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool_id = settings.pool_id(config)
    pool = batch_client.pool.get(pool_id)
    desc = 'docker ps'
    cmd = ['docker ps -a']
    stdout = _execute_command_on_pool_over_ssh_with_keyed_output(
        batch_client, config, pool, desc, cmd)
    _log_stdout_by_nodeid(config, pool_id, desc, stdout)


def _list_docker_images(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """List Docker images in pool over ssh
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param dict config: configuration dict
    """
    pool_id = settings.pool_id(config)
    pool = batch_client.pool.get(pool_id)
    cmd = ['docker images --format "{{.ID}} {{.Repository}}:{{.Tag}}"']
    stdout = _execute_command_on_pool_over_ssh_with_keyed_output(
        batch_client, config, pool, 'list docker images', cmd)
    # process stdout
    node_images = {}
    all_images = {}
    for key in stdout:
        node_images[key] = set()
        spout = stdout[key].split('\n')
        for out in spout:
            if util.is_not_empty(out):
                dec = out.split()
                if (not dec[1].startswith('alfpark/batch-shipyard') and
                        not dec[1].startswith('alfpark/blobxfer')):
                    node_images[key].add(dec[0])
                    if dec[0] not in all_images:
                        all_images[dec[0]] = dec[1]
    # find set intersection among all nodes
    intersecting_images = set.intersection(*list(node_images.values()))
    if settings.raw(config):
        raw = {
            'pool_id': pool.id,
            'common': {},
            'mismatched': {}
        }
        for key in intersecting_images:
            raw['common'][key] = all_images[key]
    else:
        logger.info(
            'Common Docker images across all nodes in pool {}:{}{}'.format(
                pool.id,
                os.linesep,
                os.linesep.join(
                    ['{} {}'.format(key, all_images[key])
                     for key in intersecting_images])
            ))
    # find mismatched images on nodes
    for node in node_images:
        images = set(node_images[node])
        diff = images.difference(intersecting_images)
        if len(diff) > 0:
            if settings.raw(config):
                if node not in raw['mismatched']:
                    raw['mismatched'][node] = {}
                for key in diff:
                    raw['mismatched'][node][key] = all_images[key]
            else:
                logger.warning(
                    'Docker images present only on node {}:{}{}'.format(
                        node, os.linesep,
                        os.linesep.join(
                            ['{} {}'.format(key, all_images[key])
                             for key in diff])
                    ))
    if settings.raw(config):
        util.print_raw_json(raw)


def _adjust_settings_for_pool_creation(config):
    # type: (dict) -> None
    """Adjust settings for pool creation
    :param dict config: configuration dict
    """
    # get settings
    pool = settings.pool_settings(config)
    publisher = settings.pool_publisher(config, lower=True)
    offer = settings.pool_offer(config, lower=True)
    sku = settings.pool_sku(config, lower=True)
    node_agent = settings.pool_custom_image_node_agent(config)
    if util.is_not_empty(node_agent) and util.is_not_empty(sku):
        raise ValueError(
            'cannot specify both a platform_image and a custom_image in the '
            'pool specification')
    is_windows = settings.is_windows_pool(config)
    bs = settings.batch_shipyard_settings(config)
    # enforce publisher/offer/sku restrictions
    allowed = False
    shipyard_container_required = True
    # oracle linux is not supported due to UEKR4 requirement
    if publisher == 'canonical':
        if offer == 'ubuntuserver':
            if sku == '16.04-lts':
                allowed = True
                shipyard_container_required = False
            elif sku == '18.04-lts':
                allowed = True
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
            if sku >= '12-sp2':
                allowed = True
    elif publisher == 'microsoftwindowsserver':
        if offer == 'windowsserver':
            if sku == '2016-datacenter-with-containers':
                allowed = True
        elif offer == 'windowsserversemiannual':
            if sku == 'datacenter-core-1709-with-containers-smalldisk':
                allowed = True
    # check if allowed for gpu (if gpu vm size)
    if allowed:
        allowed = settings.gpu_configuration_check(
            config, vm_size=pool.vm_size)
    if not allowed and util.is_none_or_empty(node_agent):
        raise ValueError(
            ('unsupported Docker (and/or GPU) Host VM Config, publisher={} '
             'offer={} sku={} vm_size={}').format(
                 publisher, offer, sku, pool.vm_size))
    # ensure HPC offers are matched with RDMA sizes
    if (not is_windows and (
            (offer == 'centos-hpc' or offer == 'sles-hpc') and
            not settings.is_rdma_pool(pool.vm_size))):
        raise ValueError(
            ('cannot allocate an HPC VM config of publisher={} offer={} '
             'sku={} with a non-RDMA vm_size={}').format(
                 publisher, offer, sku, pool.vm_size))
    # compute total vm count
    pool_total_vm_count = pool.vm_count.dedicated + pool.vm_count.low_priority
    # adjust for shipyard container requirement
    if (not bs.use_shipyard_docker_image and
            (shipyard_container_required or util.is_not_empty(node_agent))):
        settings.set_use_shipyard_docker_image(config, True)
        logger.debug(
            ('forcing shipyard docker image to be used due to '
             'VM config, publisher={} offer={} sku={}').format(
                 publisher, offer, sku))
    # re-read pool and data replication settings
    pool = settings.pool_settings(config)
    dr = settings.data_replication_settings(config)
    native = settings.is_native_docker_pool(
        config, vm_config=pool.vm_configuration)
    # ensure singularity images are not specified for native pools
    if native:
        images = settings.global_resources_singularity_images(config)
        if util.is_not_empty(images):
            raise ValueError(
                'cannot specify a native container pool with Singularity '
                'images as global resources')
    # ensure settings p2p/as/internode settings are compatible
    if dr.peer_to_peer.enabled:
        if native:
            raise ValueError(
                'cannot enable peer-to-peer and native container pools')
        if settings.is_pool_autoscale_enabled(config, pas=pool.autoscale):
            raise ValueError('cannot enable peer-to-peer and autoscale')
        if pool.inter_node_communication_enabled:
            logger.warning(
                'force enabling inter-node communication due to peer-to-peer '
                'transfer')
            settings.set_inter_node_communication_enabled(config, True)
    # hpn-ssh can only be used for Ubuntu currently
    try:
        if (pool.ssh.hpn_server_swap and
                ((publisher != 'canonical' and offer != 'ubuntuserver') or
                 util.is_not_empty(node_agent))):
            logger.warning('cannot enable HPN SSH swap on {} {} {}'.format(
                publisher, offer, sku))
            settings.set_hpn_server_swap(config, False)
    except KeyError:
        pass
    # force disable block for global resources if ingressing data
    if (pool.transfer_files_on_pool_creation and
            pool.block_until_all_global_resources_loaded):
        logger.warning(
            'disabling block until all global resources loaded with '
            'transfer files on pool creation enabled')
        settings.set_block_until_all_global_resources_loaded(config, False)
    # re-read pool settings
    pool = settings.pool_settings(config)
    # ensure internode is not enabled for mix node pools
    if (pool.inter_node_communication_enabled and
            pool.vm_count.dedicated > 0 and pool.vm_count.low_priority > 0):
        raise ValueError(
            'inter node communication cannot be enabled with both '
            'dedicated and low priority nodes')
    # check shared data volume settings
    try:
        num_gluster = 0
        sdv = settings.global_resources_shared_data_volumes(config)
        for sdvkey in sdv:
            if settings.is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
                if is_windows:
                    raise ValueError(
                        'glusterfs on compute is not supported on windows')
                if settings.is_pool_autoscale_enabled(
                        config, pas=pool.autoscale):
                    raise ValueError(
                        'glusterfs on compute cannot be installed on an '
                        'autoscale-enabled pool')
                if not pool.inter_node_communication_enabled:
                    # do not modify value and proceed since this interplays
                    # with p2p settings, simply raise exception and force
                    # user to reconfigure
                    raise ValueError(
                        'inter node communication in pool configuration '
                        'must be enabled for glusterfs on compute')
                if pool.vm_count.low_priority > 0:
                    raise ValueError(
                        'glusterfs on compute cannot be installed on pools '
                        'with low priority nodes')
                if pool.vm_count.dedicated <= 1:
                    raise ValueError(
                        'vm_count dedicated should exceed 1 for glusterfs '
                        'on compute')
                if pool.max_tasks_per_node > 1:
                    raise ValueError(
                        'max_tasks_per_node cannot exceed 1 for glusterfs '
                        'on compute')
                num_gluster += 1
                try:
                    if settings.gluster_volume_type(sdv, sdvkey) != 'replica':
                        raise ValueError(
                            'only replicated GlusterFS volumes are '
                            'currently supported')
                except KeyError:
                    pass
            elif settings.is_shared_data_volume_storage_cluster(sdv, sdvkey):
                if is_windows:
                    raise ValueError(
                        'storage cluster mounting is not supported on windows')
            elif settings.is_shared_data_volume_azure_blob(sdv, sdvkey):
                if is_windows:
                    raise ValueError(
                        'azure blob mounting is not supported on windows')
                if native:
                    raise ValueError(
                        'azure blob mounting is not supported on native '
                        'container pools')
                if offer == 'ubuntuserver':
                    if sku < '16.04-lts':
                        raise ValueError(
                            ('azure blob mounting is not supported '
                             'on publisher={} offer={} sku={}').format(
                                 publisher, offer, sku))
                elif not offer.startswith('centos'):
                    raise ValueError(
                        ('azure blob mounting is not supported '
                         'on publisher={} offer={} sku={}').format(
                             publisher, offer, sku))
            elif settings.is_shared_data_volume_custom_linux_mount(
                    sdv, sdvkey):
                if is_windows:
                    raise ValueError(
                        'custom linux mounting is not supported on windows')
        if num_gluster > 1:
            raise ValueError(
                'cannot create more than one GlusterFS on compute volume '
                'per pool')
    except KeyError:
        pass
    # check data ingress on pool creation on windows
    if is_windows and pool.transfer_files_on_pool_creation:
        raise ValueError(
            'cannot transfer files on pool creation to windows compute nodes')
    # check singularity images are not present for windows
    if (is_windows and util.is_not_empty(
            settings.global_resources_singularity_images(config))):
        raise ValueError('cannot deploy Singularity images on windows pools')
    # check pool count of 0 and remote login
    if pool_total_vm_count == 0:
        if is_windows:
            # TODO RDP check
            pass
        else:
            if util.is_not_empty(pool.ssh.username):
                logger.warning('cannot add SSH user with zero target nodes')
    # ensure unusable recovery is not enabled for custom image
    if (pool.attempt_recovery_on_unusable and
            not settings.is_platform_image(
                config, vm_config=pool.vm_configuration)):
        logger.warning(
            'override attempt recovery on unusable due to custom image')
        settings.set_attempt_recovery_on_unusable(config, False)
    # currently prometheus monitoring is only available on Linux nodes
    if (is_windows and
            (pool.prometheus.ne_enabled or pool.prometheus.ca_enabled)):
        raise ValueError(
            'Prometheus monitoring is only available for Linux nodes')


def _check_settings_for_auto_pool(config):
    # type: (dict) -> None
    """Check settings for autopool
    :param dict config: configuration dict
    """
    # check glusterfs on compute
    try:
        sdv = settings.global_resources_shared_data_volumes(config)
        for sdvkey in sdv:
            if settings.is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
                raise ValueError(
                    'GlusterFS on compute is not possible with autopool')
                break
    except KeyError:
        pass
    # get settings
    pool = settings.pool_settings(config)
    # check local data movement to pool
    if pool.transfer_files_on_pool_creation:
        raise ValueError('Cannot ingress data on pool creation with autopool')
    # check ssh
    if util.is_not_empty(pool.ssh.username):
        logger.warning('cannot add SSH user with autopool')


def _check_resource_client(resource_client):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient) -> None
    """Check resource client validity"""
    if resource_client is None:
        raise RuntimeError(
            'resource management client is invalid, ensure you have '
            'specified proper "management" credentials')


def _check_compute_client(compute_client):
    # type: (azure.mgmt.resource.compute.ComputeManagementClient) -> None
    """Check compute client validity"""
    if compute_client is None:
        raise RuntimeError(
            'compute management client is invalid, ensure you have '
            'specified proper "management" credentials')


def _check_network_client(network_client):
    # type: (azure.mgmt.resource.network.NetworkManagementClient) -> None
    """Check network client validity"""
    if network_client is None:
        raise RuntimeError(
            'network management client is invalid, ensure you have '
            'specified proper "management" credentials')


def _check_keyvault_client(keyvault_client):
    # type: (azure.keyvault.KeyVaultClient) -> None
    """Check keyvault client validity"""
    if keyvault_client is None:
        raise RuntimeError(
            'keyvault client is invalid, ensure you have specified '
            'proper "keyvault" credentials')


def _check_batch_client(batch_client):
    # type: (batchsc.BatchServiceClient) -> None
    """Check batch client validity"""
    if batch_client is None:
        raise RuntimeError(
            'batch client is invalid, ensure you have specified '
            'proper "batch" credentials')


def action_account_info(batch_mgmt_client, config, name, resource_group):
    # type: (azure.mgmt.batch.BatchManagementClient, dict, str, str) -> None
    """Action: Account Info
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param dict config: configuration dict
    :param str account_name: account name
    :param str resource_group: resource group of Batch account
    """
    batch.log_batch_account_info(
        batch_mgmt_client, config, account_name=name,
        resource_group=resource_group)


def action_account_list(batch_mgmt_client, config, resource_group):
    # type: (azure.mgmt.batch.BatchManagementClient, dict, str) -> None
    """Action: Account List
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param dict config: configuration dict
    :param str resource_group: resource group limiter
    """
    batch.log_batch_account_list(
        batch_mgmt_client, config, resource_group=resource_group)


def action_account_quota(batch_mgmt_client, config, location):
    # type: (azure.mgmt.batch.BatchManagementClient, dict, str) -> None
    """Action: Account Quota
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param dict config: configuration dict
    :param str location: location
    """
    batch.log_batch_account_service_quota(
        batch_mgmt_client, config, location)


def action_fs_disks_add(resource_client, compute_client, config):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient, dict) -> None
    """Action: Fs Disks Add
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    """
    _check_resource_client(resource_client)
    _check_compute_client(compute_client)
    remotefs.create_managed_disks(resource_client, compute_client, config)


def action_fs_disks_del(
        resource_client, compute_client, config, name, resource_group, all,
        delete_resource_group, wait):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient, dict, str,
    #        str, bool, bool, bool) -> None
    """Action: Fs Disks Del
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str name: disk name
    :param str resource_group: resource group
    :param bool all: delete all in resource group
    :param bool delete_resource_group: delete resource group
    :param bool wait: wait for operation to complete
    """
    _check_compute_client(compute_client)
    remotefs.delete_managed_disks(
        resource_client, compute_client, config, name, resource_group, all,
        delete_resource_group, wait, confirm_override=False)


def action_fs_disks_list(
        compute_client, config, resource_group, restrict_scope):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, str,
    #        bool) -> None
    """Action: Fs Disks List
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str resource_group: resource group
    :param bool restrict_scope: restrict scope to config
    """
    _check_compute_client(compute_client)
    remotefs.list_disks(compute_client, config, resource_group, restrict_scope)


def action_fs_cluster_add(
        resource_client, compute_client, network_client, blob_client,
        config, storage_cluster_id):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService, dict, str) -> None
    """Action: Fs Cluster Add
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    """
    _check_resource_client(resource_client)
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    storage.set_storage_remotefs_container(storage_cluster_id)
    rfs = settings.remotefs_settings(config, storage_cluster_id)
    # add node exporter if enabled
    if rfs.storage_cluster.prometheus.ne_enabled:
        ne_pkg = setup_prometheus_node_exporter()
        _ALL_REMOTEFS_FILES.append((ne_pkg.name, ne_pkg))
    remotefs.create_storage_cluster(
        resource_client, compute_client, network_client, blob_client, config,
        storage_cluster_id, _REMOTEFSPREP_FILE[0], _ALL_REMOTEFS_FILES)


def action_fs_cluster_resize(
        compute_client, network_client, blob_client, config,
        storage_cluster_id):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService, dict, str) -> None
    """Action: Fs Cluster Resize
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    """
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    remotefs.resize_storage_cluster(
        compute_client, network_client, blob_client, config,
        storage_cluster_id, _REMOTEFSPREP_FILE[0], _REMOTEFSADDBRICK_FILE[0],
        _ALL_REMOTEFS_FILES)


def action_fs_cluster_del(
        resource_client, compute_client, network_client, blob_client, config,
        storage_cluster_id, delete_all_resources, delete_data_disks,
        delete_virtual_network, generate_from_prefix, wait):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService, dict, str, bool, bool,
    #        bool, bool, bool) -> None
    """Action: Fs Cluster Add
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    :param bool delete_all_resources: delete all resources
    :param bool delete_data_disks: delete data disks
    :param bool delete_virtual_network: delete virtual network
    :param bool generate_from_prefix: generate resources from hostname prefix
    :param bool wait: wait for deletion to complete
    """
    _check_resource_client(resource_client)
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    if (generate_from_prefix and
            (delete_all_resources or delete_data_disks or
             delete_virtual_network)):
        raise ValueError(
            'Cannot specify generate_from_prefix and a delete_* option')
    storage.set_storage_remotefs_container(storage_cluster_id)
    remotefs.delete_storage_cluster(
        resource_client, compute_client, network_client, blob_client, config,
        storage_cluster_id, delete_data_disks=delete_data_disks,
        delete_virtual_network=delete_virtual_network,
        delete_resource_group=delete_all_resources,
        generate_from_prefix=generate_from_prefix, wait=wait)


def action_fs_cluster_expand(
        compute_client, network_client, config, storage_cluster_id, rebalance):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str,
    #        bool) -> None
    """Action: Fs Cluster Expand
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    :param bool rebalance: rebalance filesystem
    """
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    if remotefs.expand_storage_cluster(
            compute_client, network_client, config, storage_cluster_id,
            _REMOTEFSPREP_FILE[0], rebalance):
        action_fs_cluster_status(
            compute_client, network_client, config, storage_cluster_id,
            detail=True, hosts=False)


def action_fs_cluster_suspend(
        compute_client, config, storage_cluster_id, wait):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, str,
    #        bool) -> None
    """Action: Fs Cluster Suspend
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    :param bool wait: wait for suspension to complete
    """
    _check_compute_client(compute_client)
    remotefs.suspend_storage_cluster(
        compute_client, config, storage_cluster_id, wait)


def action_fs_cluster_start(
        compute_client, network_client, config, storage_cluster_id, wait):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str,
    #        bool) -> None
    """Action: Fs Cluster Start
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    :param bool wait: wait for restart to complete
    """
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    remotefs.start_storage_cluster(
        compute_client, config, storage_cluster_id, wait)
    if wait:
        action_fs_cluster_status(
            compute_client, network_client, config, storage_cluster_id,
            detail=False, hosts=False)


def action_fs_cluster_status(
        compute_client, network_client, config, storage_cluster_id,
        detail, hosts):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, bool,
    #        bool) -> None
    """Action: Fs Cluster Status
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    :param bool detail: detailed status
    :param bool hosts: dump info for /etc/hosts
    """
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    remotefs.stat_storage_cluster(
        compute_client, network_client, config, storage_cluster_id,
        _REMOTEFSSTAT_FILE[0], detail, hosts)


def action_fs_cluster_ssh(
        compute_client, network_client, config, storage_cluster_id,
        cardinal, hostname, tty, command):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, int,
    #        str, bool, tuple) -> None
    """Action: Fs Cluster Ssh
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str storage_cluster_id: storage cluster id
    :param int cardinal: cardinal number
    :param str hostname: hostname
    :param bool tty: allocate pseudo-tty
    :param tuple command: command
    """
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    if cardinal is not None and hostname is not None:
        raise ValueError('cannot specify both cardinal and hostname options')
    if cardinal is None and hostname is None:
        logger.warning(
            'assuming node cardinal of 0 as no cardinal or hostname option '
            'was specified')
        cardinal = 0
    if cardinal is not None and cardinal < 0:
            raise ValueError('invalid cardinal option value')
    remotefs.ssh_storage_cluster(
        compute_client, network_client, config, storage_cluster_id,
        cardinal, hostname, tty, command)


def action_keyvault_add(keyvault_client, config, keyvault_uri, name):
    # type: (azure.keyvault.KeyVaultClient, dict, str, str) -> None
    """Action: Keyvault Add
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param dict config: configuration dict
    :param str keyvault_uri: keyvault uri
    :param str name: secret name
    """
    _check_keyvault_client(keyvault_client)
    keyvault.store_credentials_conf(
        keyvault_client, config, keyvault_uri, name)


def action_keyvault_del(keyvault_client, keyvault_uri, name):
    # type: (azure.keyvault.KeyVaultClient, str, str) -> None
    """Action: Keyvault Del
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param str keyvault_uri: keyvault uri
    :param str name: secret name
    """
    _check_keyvault_client(keyvault_client)
    keyvault.delete_secret(keyvault_client, keyvault_uri, name)


def action_keyvault_list(keyvault_client, keyvault_uri):
    # type: (azure.keyvault.KeyVaultClient, str) -> None
    """Action: Keyvault List
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param str keyvault_uri: keyvault uri
    """
    _check_keyvault_client(keyvault_client)
    keyvault.list_secrets(keyvault_client, keyvault_uri)


def action_cert_create(config, file_prefix, pfx_password):
    # type: (dict, str, str) -> None
    """Action: Cert Create
    :param dict config: configuration dict
    :param str file_prefix: prefix of file to create
    :param str pfx_password: pfx password
    """
    sha1tp = crypto.generate_pem_pfx_certificates(
        config, file_prefix, pfx_password)
    logger.info('SHA1 Thumbprint: {}'.format(sha1tp))


def action_cert_add(
        batch_client, config, file, pem_no_certs, pem_public_key,
        pfx_password):
    # type: (batchsc.BatchServiceClient, dict, str, bool, bool, str) -> None
    """Action: Cert Add
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param str file: file to add
    :param bool pem_no_certs: don't export certs from pem
    :param bool pem_public_key: only add public key from pem
    :param str pfx_password: pfx password
    """
    _check_batch_client(batch_client)
    if pem_public_key or pem_no_certs:
        if util.is_not_empty(file) and not file.lower().endswith('.pem'):
            raise ValueError(
                'cannot specify a --pem-* option and a non-PEM file')
        elif util.is_none_or_empty(file):
            raise ValueError('cannot specify --pem-* option and no file')
    batch.add_certificate_to_account(
        batch_client, config, file, pem_no_certs, pem_public_key, pfx_password)


def action_cert_list(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Cert List
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.list_certificates_in_account(batch_client, config)


def action_cert_del(batch_client, config, sha1):
    # type: (batchsc.BatchServiceClient, dict, List[str]) -> None
    """Action: Cert Del
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param dict config: configuration dict
    :param list sha1: list of sha1 thumbprints to delete
    """
    _check_batch_client(batch_client)
    batch.del_certificate_from_account(batch_client, config, sha1)


def action_pool_listskus(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Listskus
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.list_node_agent_skus(batch_client, config)


def action_pool_add(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, table_client, config):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.mgmt.batch.BatchManagementClient,
    #        azure.batch.batch_service_client.BatchServiceClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService, dict) -> None
    """Action: Pool Add
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    # first check if pool exists to prevent accidential metadata clear
    if batch_client.pool.exists(settings.pool_id(config)):
        raise RuntimeError(
            'attempting to create a pool that already exists: {}'.format(
                settings.pool_id(config)))
    _adjust_settings_for_pool_creation(config)
    storage.create_storage_containers(blob_client, table_client, config)
    storage.clear_storage_containers(blob_client, table_client, config)
    if not settings.is_native_docker_pool(config):
        storage.populate_global_resource_blobs(
            blob_client, table_client, config)
    _add_pool(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, config
    )


def action_pool_list(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool List
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.list_pools(batch_client, config)


def action_pool_delete(
        batch_client, blob_client, table_client, config, pool_id=None,
        wait=False):
    # type: (batchsc.BatchServiceClient, azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService, dict, str, bool) -> None
    """Action: Pool Delete
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str pool_id: poolid to delete
    :param bool wait: wait for pool to delete
    """
    _check_batch_client(batch_client)
    deleted = False
    try:
        deleted = batch.del_pool(batch_client, config, pool_id=pool_id)
    except batchmodels.BatchErrorException as ex:
        if ('The specified pool does not exist' in ex.message.value or
                'The specified pool has been marked for deletion' in
                ex.message.value):
            deleted = True
        else:
            logger.exception(ex)
    if deleted:
        # reset storage settings to target poolid if required
        if util.is_not_empty(pool_id):
            populate_global_settings(config, False, pool_id=pool_id)
        else:
            pool_id = settings.pool_id(config)
        storage.cleanup_with_del_pool(
            blob_client, table_client, config, pool_id=pool_id)
        if wait:
            logger.debug('waiting for pool {} to delete'.format(pool_id))
            while batch_client.pool.exists(pool_id):
                time.sleep(3)


def action_pool_resize(batch_client, blob_client, config, wait):
    # type: (batchsc.BatchServiceClient, azure.storage.blob.BlockBlobService,
    #        dict, bool) -> None
    """Resize pool that may contain glusterfs
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param bool wait: wait for operation to complete
    """
    _check_batch_client(batch_client)
    pool = settings.pool_settings(config)
    # check direction of resize
    _pool = batch_client.pool.get(pool.id)
    if (pool.vm_count.dedicated == _pool.current_dedicated_nodes ==
            _pool.target_dedicated_nodes and
            pool.vm_count.low_priority == _pool.current_low_priority_nodes ==
            _pool.target_low_priority_nodes):
        logger.error(
            'pool {} is already at {} nodes'.format(pool.id, pool.vm_count))
        return
    resize_up_d = False
    resize_up_lp = False
    if pool.vm_count.dedicated > _pool.current_dedicated_nodes:
        resize_up_d = True
    if pool.vm_count.low_priority > _pool.current_low_priority_nodes:
        resize_up_lp = True
    del _pool
    create_ssh_user = False
    # try to get handle on public key, avoid generating another set
    # of keys
    if resize_up_d or resize_up_lp:
        if pool.ssh.username is None:
            logger.info('not creating ssh user on new nodes of pool {}'.format(
                pool.id))
        else:
            if pool.ssh.ssh_public_key is None:
                sfp = pathlib.Path(crypto.get_ssh_key_prefix() + '.pub')
                if sfp.exists():
                    logger.debug(
                        'setting public key for ssh user to: {}'.format(sfp))
                    settings.set_ssh_public_key(config, str(sfp))
                    create_ssh_user = True
                else:
                    logger.warning(
                        ('not creating ssh user for new nodes of pool {} as '
                         'an existing ssh public key cannot be found').format(
                             pool.id))
                    create_ssh_user = False
    # check if this is a glusterfs-enabled pool
    gluster_present = False
    voltype = None
    try:
        sdv = settings.global_resources_shared_data_volumes(config)
        for sdvkey in sdv:
            if settings.is_shared_data_volume_gluster_on_compute(sdv, sdvkey):
                gluster_present = True
                try:
                    voltype = settings.gluster_volume_type(sdv, sdvkey)
                except KeyError:
                    pass
                break
    except KeyError:
        pass
    logger.debug('glusterfs shared volume present: {}'.format(
        gluster_present))
    if gluster_present:
        if resize_up_lp:
            raise RuntimeError(
                'cannot resize up a pool with glusterfs_on_compute and '
                'low priority nodes')
        logger.debug('forcing wait to True due to glusterfs')
        wait = True
    # cache old nodes
    old_nodes = {}
    if gluster_present or create_ssh_user:
        for node in batch_client.compute_node.list(pool.id):
            old_nodes[node.id] = node.ip_address
    # resize pool
    nodes = batch.resize_pool(batch_client, config, wait)
    # add ssh user to new nodes if present
    if create_ssh_user and (resize_up_d or resize_up_lp):
        if wait:
            # get list of new nodes only
            new_nodes = [node for node in nodes if node.id not in old_nodes]
            # create admin user on each new node if requested
            batch.add_ssh_user(batch_client, config, nodes=new_nodes)
            # log remote login settings for new nodes
            batch.get_remote_login_settings(
                batch_client, config, nodes=new_nodes, suppress_output=False)
            del new_nodes
        else:
            logger.warning('ssh user was not added as --wait was not given')
    # add brick for new nodes
    if gluster_present and resize_up_d:
        # get pool current dedicated
        _pool = batch_client.pool.get(pool.id)
        # ensure current dedicated is the target
        if pool.vm_count.dedicated != _pool.current_dedicated_nodes:
            raise RuntimeError(
                ('cannot perform glusterfs setup on new nodes, unexpected '
                 'current dedicated {} to vm_count {}').format(
                     _pool.current_dedicated_nodes, pool.vm_count.dedicated))
        del _pool
        # get internal ip addresses of new nodes
        new_nodes = [
            node.ip_address for node in nodes if node.id not in old_nodes
        ]
        masterip = next(iter(old_nodes.values()))
        # get tempdisk mountpoint
        tempdisk = settings.temp_disk_mountpoint(config)
        # construct cmdline
        cmdline = util.wrap_commands_in_shell([
            '$AZ_BATCH_TASK_DIR/{} {} {} {} {} {}'.format(
                _GLUSTERRESIZE_FILE[0], voltype.lower(), tempdisk,
                pool.vm_count.dedicated, masterip, ' '.join(new_nodes))])
        # setup gluster
        _setup_glusterfs(
            batch_client, blob_client, config, nodes, _GLUSTERRESIZE_FILE,
            cmdline=cmdline)


def action_pool_nodes_grls(
        batch_client, config, no_generate_tunnel_script):
    # type: (batchsc.BatchServiceClient, dict, bool) -> None
    """Action: Pool Nodes Grls
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool no_generate_tunnel_script: disable generating tunnel script
    """
    _check_batch_client(batch_client)
    rls = batch.get_remote_login_settings(
        batch_client, config, nodes=None, suppress_output=False)
    if not no_generate_tunnel_script:
        batch.generate_ssh_tunnel_script(
            batch_client, config, None, nodes=None, rls=rls)


def action_pool_nodes_list(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Nodes List
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.list_nodes(batch_client, config)


def action_pool_nodes_zap(batch_client, config, remove, stop):
    # type: (batchsc.BatchServiceClient, dict, bool, bool) -> None
    """Action: Pool Nodes Zap
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool remove: remove containers all exited containers
    :param bool stop: docker stop instead of kill
    """
    _check_batch_client(batch_client)
    _zap_all_container_processes_over_ssh(batch_client, config, remove, stop)


def action_pool_nodes_prune(batch_client, config, volumes):
    # type: (batchsc.BatchServiceClient, dict, bool) -> None
    """Action: Pool Nodes Prune
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool volumes: remove volumes as well
    """
    _check_batch_client(batch_client)
    _docker_system_prune_over_ssh(batch_client, config, volumes)


def action_pool_nodes_ps(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Nodes Ps
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    _docker_ps_over_ssh(batch_client, config)


def action_pool_user_add(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool User Add
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    if settings.is_windows_pool(config):
        batch.add_rdp_user(batch_client, config)
    else:
        batch.add_ssh_user(batch_client, config)


def action_pool_user_del(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict) -> None
    """Action: Pool Dru
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    if settings.is_windows_pool(config):
        batch.del_rdp_user(batch_client, config)
    else:
        batch.del_ssh_user(batch_client, config)


def action_pool_ssh(batch_client, config, cardinal, nodeid, tty, command):
    # type: (batchsc.BatchServiceClient, dict, int, str, bool, tuple) -> None
    """Action: Pool Ssh
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param int cardinal: cardinal node num
    :param str nodeid: node id
    :param bool tty: allocate pseudo-tty
    :param tuple command: command to execute
    """
    _check_batch_client(batch_client)
    if cardinal is not None and nodeid is not None:
        raise ValueError('cannot specify both cardinal and nodeid options')
    if cardinal is None and nodeid is None:
        logger.warning(
            'assuming node cardinal of 0 as no cardinal or nodeid option '
            'was specified')
        cardinal = 0
    if cardinal is not None and cardinal < 0:
        raise ValueError('invalid cardinal option value')
    pool = settings.pool_settings(config)
    ssh_private_key = pool.ssh.ssh_private_key
    if ssh_private_key is None:
        ssh_private_key = pathlib.Path(
            pool.ssh.generated_file_export_path, crypto.get_ssh_key_prefix())
    ip, port = batch.get_remote_login_setting_for_node(
        batch_client, config, cardinal, nodeid)
    crypto.connect_or_exec_ssh_command(
        ip, port, ssh_private_key, pool.ssh.username, tty=tty,
        command=command)


def action_pool_rdp(batch_client, config, cardinal, nodeid, no_auto=False):
    # type: (batchsc.BatchServiceClient, dict, int, str, bool) -> None
    """Action: Pool Rdp
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param int cardinal: cardinal node num
    :param str nodeid: node id
    :param bool no_auto: no auto login
    """
    _check_batch_client(batch_client)
    if cardinal is not None and nodeid is not None:
        raise ValueError('cannot specify both cardinal and nodeid options')
    if cardinal is None and nodeid is None:
        logger.warning(
            'assuming node cardinal of 0 as no cardinal or nodeid option '
            'was specified')
        cardinal = 0
    if cardinal is not None and cardinal < 0:
            raise ValueError('invalid cardinal option value')
    pool = settings.pool_settings(config)
    ip, port = batch.get_remote_login_setting_for_node(
        batch_client, config, cardinal, nodeid)
    if not no_auto and util.is_not_empty(pool.rdp.password):
        rc = util.subprocess_with_output(
            'cmdkey.exe /generic:TERMSRV/{ip} /user:{user} /pass:{pw}'.format(
                ip=ip, port=port, user=pool.rdp.username,
                pw=pool.rdp.password),
            shell=True)
        if rc != 0:
            logger.warning('cmdkey exit code: {}'.format(rc))
    util.subprocess_nowait(
        'mstsc.exe /v:{ip}:{port}'.format(ip=ip, port=port), shell=True)
    if not no_auto and util.is_not_empty(pool.rdp.password):
        time.sleep(2)
        rc = util.subprocess_with_output(
            'cmdkey.exe /delete:TERMSRV/{}'.format(ip), shell=True)
        if rc != 0:
            logger.warning('cmdkey exit code: {}'.format(rc))


def action_pool_nodes_del(
        batch_client, config, all_start_task_failed, all_starting,
        all_unusable, nodeid):
    # type: (batchsc.BatchServiceClient, dict, bool, bool, bool, list) -> None
    """Action: Pool Nodes Del
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool all_start_task_failed: delete all start task failed nodes
    :param bool all_starting: delete all starting nodes
    :param bool all_unusable: delete all unusable nodes
    :param list nodeid: list of nodeids to delete
    """
    _check_batch_client(batch_client)
    if ((all_start_task_failed or all_starting or all_unusable) and
            nodeid is not None):
        raise ValueError(
            'cannot specify all start task failed nodes or unusable with '
            'a specific node id')
    batch.del_nodes(
        batch_client, config, all_start_task_failed, all_starting,
        all_unusable, nodeid)


def action_pool_nodes_reboot(
        batch_client, config, all_start_task_failed, nodeid):
    # type: (batchsc.BatchServiceClient, dict, bool, list) -> None
    """Action: Pool Nodes Reboot
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool all_start_task_failed: reboot all start task failed nodes
    :param list nodeid: list of nodeids to reboot
    """
    _check_batch_client(batch_client)
    if all_start_task_failed and nodeid is not None:
        raise ValueError(
            'cannot specify all start task failed nodes with a specific '
            'node id')
    batch.reboot_nodes(batch_client, config, all_start_task_failed, nodeid)


def action_diag_logs_upload(
        batch_client, blob_client, config, cardinal, nodeid, wait):
    # type: (batchsc.BatchServiceClient, azure.storage.blob.BlockBlobService,
    #        dict, int, str, bool) -> None
    """Action: Diag Logs Upload
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param int cardinal: cardinal node num
    :param str nodeid: node id
    :param bool wait: wait for upload to complete
    """
    _check_batch_client(batch_client)
    if cardinal is not None and nodeid is not None:
        raise ValueError('cannot specify both cardinal and nodeid options')
    if cardinal is None and nodeid is None:
        logger.warning(
            'assuming node cardinal of 0 as no cardinal or nodeid option '
            'was specified')
        cardinal = 0
    if cardinal is not None and cardinal < 0:
        raise ValueError('invalid cardinal option value')
    batch.egress_service_logs(
        batch_client, blob_client, config, cardinal, nodeid, wait)


def action_pool_images_update(
        batch_client, config, docker_image, docker_image_digest,
        singularity_image, ssh):
    # type: (batchsc.BatchServiceClient, dict, str, str, str, bool) -> None
    """Action: Pool Images Update
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str docker_image: docker image to update
    :param str docker_image_digest: docker image digest to update to
    :param str singularity_image: singularity image to update
    :param bool ssh: use direct SSH update mode
    """
    _check_batch_client(batch_client)
    if docker_image_digest is not None and docker_image is None:
        raise ValueError(
            'cannot specify a digest to update to without the image')
    _update_container_images(
        batch_client, config, docker_image, docker_image_digest,
        singularity_image, force_ssh=ssh)


def action_pool_images_list(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool) -> None
    """Action: Pool Images List
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    _list_docker_images(batch_client, config)


def action_pool_stats(batch_client, config, pool_id):
    # type: (batchsc.BatchServiceClient, dict, str) -> None
    """Action: Pool Stats
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str pool_id: pool id
    """
    _check_batch_client(batch_client)
    batch.pool_stats(batch_client, config, pool_id=pool_id)


def action_pool_autoscale_disable(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool) -> None
    """Action: Pool Autoscale Disable
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.pool_autoscale_disable(batch_client, config)


def action_pool_autoscale_enable(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool) -> None
    """Action: Pool Autoscale Enable
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.pool_autoscale_enable(batch_client, config)


def action_pool_autoscale_evaluate(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool) -> None
    """Action: Pool Autoscale Evaluate
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.pool_autoscale_evaluate(batch_client, config)


def action_pool_autoscale_lastexec(batch_client, config):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool) -> None
    """Action: Pool Autoscale Lastexec
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    """
    _check_batch_client(batch_client)
    batch.pool_autoscale_lastexec(batch_client, config)


def action_jobs_add(
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client, blob_client, table_client, keyvault_client, config,
        recreate, tail):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.mgmt.batch.BatchManagementClient,
    #        azure.batch.batch_service_client.BatchServiceClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService,
    #        azure.keyvault.KeyVaultClient, dict, bool, str) -> None
    """Action: Jobs Add
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.mgmt.batch.BatchManagementClient: batch_mgmt_client
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.keyvault.KeyVaultClient keyvault_client: keyvault client
    :param dict config: configuration dict
    :param bool recreate: recreate jobs if completed
    :param str tail: file to tail or last job and task added
    """
    _check_batch_client(batch_client)
    # check for job autopools
    autopool = batch.check_jobs_for_auto_pool(config)
    if autopool:
        # check to ensure pool id is within 20 chars
        pool_id = settings.pool_id(config)
        if len(pool_id) > 20:
            raise ValueError(
                'pool id must be less than 21 characters: {}'.format(pool_id))
        # check if a pool id with existing pool id exists
        try:
            batch_client.pool.get(pool_id)
        except batchmodels.BatchErrorException as ex:
            if 'The specified pool does not exist' in ex.message.value:
                pass
        else:
            raise RuntimeError(
                'pool with id of {} already exists'.format(pool_id))
        _adjust_settings_for_pool_creation(config)
        # create storage containers and clear
        storage.create_storage_containers(blob_client, table_client, config)
        storage.clear_storage_containers(blob_client, table_client, config)
        if not settings.is_native_docker_pool(config):
            storage.populate_global_resource_blobs(
                blob_client, table_client, config)
        # create autopool specification object
        autopool = _construct_auto_pool_specification(
            resource_client, compute_client, network_client, batch_mgmt_client,
            batch_client, blob_client, config
        )
        # check settings and warn
        _check_settings_for_auto_pool(config)
    else:
        autopool = None
    # add jobs
    is_windows = settings.is_windows_pool(config)
    batch.add_jobs(
        batch_client, blob_client, keyvault_client, config, autopool,
        _IMAGE_BLOCK_FILE,
        _BLOBXFER_WINDOWS_FILE if is_windows else _BLOBXFER_FILE,
        recreate, tail)


def action_jobs_list(batch_client, config, jobid, jobscheduleid):
    # type: (batchsc.BatchServiceClient, dict, str, str) -> None
    """Action: Jobs List
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id
    :param str jobscheduleid: job schedule id
    """
    _check_batch_client(batch_client)
    if util.is_not_empty(jobid):
        batch.get_job_or_job_schedule(
            batch_client, config, jobid, jobscheduleid)
    else:
        batch.list_jobs(batch_client, config)


def action_jobs_tasks_list(
        batch_client, config, all, jobid, poll_until_tasks_complete, taskid):
    # type: (batchsc.BatchServiceClient, dict, bool, str, bool, str) -> None
    """Action: Jobs Tasks List
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool all: all jobs
    :param str jobid: job id
    :param bool poll_until_tasks_complete: poll until tasks complete
    :param str taskid: task id
    """
    _check_batch_client(batch_client)
    if all and jobid is not None:
        raise ValueError('cannot specify both --all and --jobid')
    if settings.raw(config) and poll_until_tasks_complete:
        raise ValueError(
            'cannot specify --poll_until_tasks_complete and --raw')
    while True:
        if util.is_not_empty(taskid):
            all_complete = batch.get_task(batch_client, config, jobid, taskid)
        else:
            all_complete = batch.list_tasks(
                batch_client, config, all=all, jobid=jobid)
        if not poll_until_tasks_complete or all_complete:
            break
        time.sleep(5)


def action_jobs_tasks_term(batch_client, config, jobid, taskid, wait, force):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool, bool) -> None
    """Action: Jobs Tasks Term
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id
    :param str taskid: task id
    :param bool wait: wait for action to complete
    :param bool force: force docker kill even if completed
    """
    _check_batch_client(batch_client)
    if taskid is not None and jobid is None:
        raise ValueError(
            'cannot specify a task to terminate without the corresponding '
            'job id')
    if force and (taskid is None or jobid is None):
        raise ValueError('cannot force docker kill without task id/job id')
    batch.terminate_tasks(
        batch_client, config, jobid=jobid, taskid=taskid, wait=wait,
        force=force)


def action_jobs_tasks_del(batch_client, config, jobid, taskid, wait):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool) -> None
    """Action: Jobs Tasks Del
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id
    :param str taskid: task id
    :param bool wait: wait for action to complete
    """
    _check_batch_client(batch_client)
    if taskid is not None and jobid is None:
        raise ValueError(
            'cannot specify a task to delete without the corresponding '
            'job id')
    batch.del_tasks(
        batch_client, config, jobid=jobid, taskid=taskid, wait=wait)


def action_jobs_del_or_term(
        batch_client, blob_client, table_client, config, delete, all_jobs,
        all_jobschedules, jobid, jobscheduleid, termtasks, wait):
    # type: (batchsc.BatchServiceClient, azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService, dict, bool, bool, str, str,
    #        bool, bool) -> None
    """Action: Jobs Del or Term
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool all_jobs: all jobs
    :param bool all_jobschedules: all job schedules
    :param str jobid: job id
    :param str jobscheduleid: job schedule id
    :param bool termtasks: terminate tasks prior
    :param bool wait: wait for action to complete
    """
    _check_batch_client(batch_client)
    if jobid is not None and jobscheduleid is not None:
        raise ValueError('cannot specify both --jobid and --jobscheduleid')
    if all_jobs:
        if jobid is not None:
            raise ValueError('cannot specify both --all-jobs and --jobid')
        batch.delete_or_terminate_all_jobs(
            batch_client, config, delete, termtasks=termtasks, wait=wait)
    elif all_jobschedules:
        if jobscheduleid is not None:
            raise ValueError(
                'cannot specify both --all-jobschedules and --jobscheduleid')
        if termtasks:
            raise ValueError(
                'Cannot specify --termtasks with --all-jobschedules. '
                'Please terminate tasks with each individual job first.')
        batch.delete_or_terminate_all_job_schedules(
            batch_client, config, delete, wait=wait)
    else:
        # check for autopool
        if util.is_none_or_empty(jobid):
            autopool = batch.check_jobs_for_auto_pool(config)
            if autopool:
                # check if a pool id with existing pool id exists
                try:
                    batch_client.pool.get(settings.pool_id(config))
                except batchmodels.BatchErrorException as ex:
                    if 'The specified pool does not exist' in ex.message.value:
                        pass
                else:
                    autopool = False
        else:
            autopool = False
        # terminate the jobs
        batch.delete_or_terminate_jobs(
            batch_client, config, delete, jobid=jobid,
            jobscheduleid=jobscheduleid, termtasks=termtasks, wait=wait)
        # if autopool, delete the storage
        if autopool:
            storage.cleanup_with_del_pool(blob_client, table_client, config)


def action_jobs_cmi(batch_client, config, delete):
    # type: (batchsc.BatchServiceClient, dict, bool) -> None
    """Action: Jobs Cmi
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool delete: delete all cmi jobs
    """
    _check_batch_client(batch_client)
    if delete:
        batch.del_clean_mi_jobs(batch_client, config)
    else:
        batch.clean_mi_jobs(batch_client, config)
        batch.del_clean_mi_jobs(batch_client, config)


def action_jobs_migrate(
        batch_client, config, jobid, jobscheduleid, poolid, requeue,
        terminate, wait):
    # type: (batchsc.BatchServiceClient, dict, str, str, str, bool, bool,
    #        bool) -> None
    """Action: Jobs Migrate
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id to migrate to in lieu of config
    :param str jobscheduleid: job schedule id to migrate to in lieu of config
    :param str poolid: pool id to migrate to in lieu of config
    :param bool requeue: requeue action
    :param bool terminate: terminate action
    :param bool wait: wait action
    """
    _check_batch_client(batch_client)
    if jobid is not None:
        if jobscheduleid is not None:
            raise ValueError('cannot specify both --jobid and --jobscheduleid')
        if [requeue, terminate, wait].count(True) != 1:
            raise ValueError(
                'must specify only one option of --requeue, --terminate, '
                '--wait')
    if requeue:
        action = 'requeue'
    elif terminate:
        action = 'terminate'
    elif wait:
        action = 'wait'
    else:
        action = None
    # check jobs to see if targetted pool id is the same
    batch.check_pool_for_job_migration(
        batch_client, config, jobid=jobid, jobscheduleid=jobscheduleid,
        poolid=poolid)
    if not util.confirm_action(
            config, msg='migration of jobs or job schedules'):
        return
    logger.warning(
        'ensure that the new target pool has the proper Docker images '
        'loaded, or you have enabled allow_run_on_missing_image')
    # disable job and wait for disabled state
    batch.disable_jobs(
        batch_client, config, action, jobid=jobid, jobscheduleid=jobscheduleid,
        suppress_confirm=True)
    # patch job
    batch.update_job_with_pool(
        batch_client, config, jobid=jobid, jobscheduleid=jobscheduleid,
        poolid=poolid)
    # enable job
    batch.enable_jobs(
        batch_client, config, jobid=jobid, jobscheduleid=jobscheduleid)


def action_jobs_disable(
        batch_client, config, jobid, jobscheduleid, requeue, terminate, wait):
    # type: (batchsc.BatchServiceClient, dict, str, str, bool, bool,
    #        bool) -> None
    """Action: Jobs Disable
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id to disable to in lieu of config
    :param str jobscheduleid: job schedule id to disable to in lieu of config
    :param bool requeue: requeue action
    :param bool terminate: terminate action
    :param bool wait: wait action
    """
    _check_batch_client(batch_client)
    if jobid is not None:
        if jobscheduleid is not None:
            raise ValueError('cannot specify both --jobid and --jobscheduleid')
        if [requeue, terminate, wait].count(True) != 1:
            raise ValueError(
                'must specify only one option of --requeue, --terminate, '
                '--wait')
    if requeue:
        action = 'requeue'
    elif terminate:
        action = 'terminate'
    elif wait:
        action = 'wait'
    else:
        action = None
    batch.disable_jobs(
        batch_client, config, action, jobid=jobid,
        jobscheduleid=jobscheduleid, disabling_state_ok=True)


def action_jobs_enable(batch_client, config, jobid, jobscheduleid):
    # type: (batchsc.BatchServiceClient, dict, str, str) -> None
    """Action: Jobs Enable
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id to enable to in lieu of config
    :param str jobscheduleid: job schedule id to enable to in lieu of config
    """
    _check_batch_client(batch_client)
    batch.enable_jobs(
        batch_client, config, jobid=jobid, jobscheduleid=jobscheduleid)


def action_jobs_stats(batch_client, config, job_id):
    # type: (batchsc.BatchServiceClient, dict, str) -> None
    """Action: Jobs Stats
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str job_id: job id
    """
    _check_batch_client(batch_client)
    batch.job_stats(batch_client, config, jobid=job_id)


def action_storage_del(
        blob_client, table_client, config, clear_tables, poolid):
    # type: (azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService, dict, bool, str) -> None
    """Action: Storage Del
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool clear_tables: clear tables instead of deleting
    :param str poolid: pool id to target
    """
    # reset storage settings to target poolid
    if util.is_not_empty(poolid):
        populate_global_settings(config, False, pool_id=poolid)
    if clear_tables:
        storage.clear_storage_containers(
            blob_client, table_client, config, tables_only=True,
            pool_id=poolid)
    storage.delete_storage_containers(
        blob_client, table_client, config, skip_tables=clear_tables)


def action_storage_clear(blob_client, table_client, config, poolid):
    # type: (azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService, dict, str) -> None
    """Action: Storage Clear
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str poolid: pool id to target
    """
    # reset storage settings to target poolid
    if util.is_not_empty(poolid):
        populate_global_settings(config, False, pool_id=poolid)
    storage.clear_storage_containers(
        blob_client, table_client, config, pool_id=poolid)


def action_storage_sas_create(
        config, storage_account, path, file, create, read, write, delete):
    # type: (dict, str, str, bool, bool, bool, bool, bool) -> None
    """Action: Storage Sas Create
    :param dict config: configuration dict
    :param str storage_account: storage account
    :param str path: path
    :param bool file: file sas
    :param bool create: create perm
    :param bool read: read perm
    :param bool write: write perm
    :param bool delete: delete perm
    """
    # reset storage settings to target poolid
    creds = settings.credentials_storage(config, storage_account)
    sas = storage.create_saskey(creds, path, file, create, read, write, delete)
    logger.info('generated SAS URL: https://{}.{}.{}/{}?{}'.format(
        creds.account, 'file' if file else 'blob', creds.endpoint, path, sas))


def action_data_files_stream(batch_client, config, filespec, disk):
    # type: (batchsc.BatchServiceClient, dict, str, bool) -> None
    """Action: Data Files Stream
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str filespec: filespec of file to retrieve
    :param bool disk: write streamed data to disk instead
    """
    _check_batch_client(batch_client)
    batch.stream_file_and_wait_for_task(batch_client, config, filespec, disk)


def action_data_files_list(batch_client, config, jobid, taskid):
    # type: (batchsc.BatchServiceClient, dict, str, str) -> None
    """Action: Data Files List
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id to list
    :param str taskid: task id to list
    """
    _check_batch_client(batch_client)
    if taskid is not None and jobid is None:
        raise ValueError(
            'cannot specify a task to list files without the corresponding '
            'job id')
    batch.list_task_files(batch_client, config, jobid, taskid)


def action_data_files_task(batch_client, config, all, filespec):
    # type: (batchsc.BatchServiceClient, dict, bool, str) -> None
    """Action: Data Files Task
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool all: retrieve all files
    :param str filespec: filespec of file to retrieve
    """
    _check_batch_client(batch_client)
    if all:
        batch.get_all_files_via_task(batch_client, config, filespec)
    else:
        batch.get_file_via_task(batch_client, config, filespec)


def action_data_files_node(batch_client, config, all, nodeid):
    # type: (batchsc.BatchServiceClient, dict, bool, str) -> None
    """Action: Data Files Node
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param bool all: retrieve all files
    :param str nodeid: node id to retrieve file from
    """
    _check_batch_client(batch_client)
    if all:
        batch.get_all_files_via_node(batch_client, config, nodeid)
    else:
        batch.get_file_via_node(batch_client, config, nodeid)


def action_data_ingress(
        batch_client, compute_client, network_client, config, to_fs):
    # type: (batchsc.BatchServiceClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str) -> None
    """Action: Data Ingress
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str to_fs: ingress to remote filesystem
    """
    pool_total_vm_count = None
    if util.is_none_or_empty(to_fs):
        try:
            # get pool current dedicated
            pool = batch_client.pool.get(settings.pool_id(config))
            pool_total_vm_count = (
                pool.current_dedicated_nodes + pool.current_low_priority_nodes
            )
            del pool
            # ensure there are remote login settings
            rls = batch.get_remote_login_settings(
                batch_client, config, nodes=None, suppress_output=True)
            # ensure nodes are at least idle/running for shared ingress
            kind = 'all'
            if not batch.check_pool_nodes_runnable(batch_client, config):
                kind = 'storage'
        except batchmodels.BatchErrorException as ex:
            if 'The specified pool does not exist' in ex.message.value:
                rls = None
                kind = 'storage'
            else:
                raise
    else:
        rls = None
        kind = 'remotefs'
        if compute_client is None or network_client is None:
            raise RuntimeError(
                'required ARM clients are invalid, please provide management '
                'AAD credentials')
    storage_threads = data.ingress_data(
        batch_client, compute_client, network_client, config, rls=rls,
        kind=kind, total_vm_count=pool_total_vm_count, to_fs=to_fs)
    data.wait_for_storage_threads(storage_threads)


def action_misc_tensorboard(
        batch_client, config, jobid, taskid, logdir, image):
    # type: (batchsc.BatchServiceClient, dict, str, str, str, str) -> None
    """Action: Misc Tensorboard
    :param azure.batch.batch_service_client.BatchServiceClient batch_client:
        batch client
    :param dict config: configuration dict
    :param str jobid: job id to list
    :param str taskid: task id to list
    :param str logdir: log dir
    :param str image: tensorflow image to use
    """
    _check_batch_client(batch_client)
    if util.is_none_or_empty(jobid):
        jobspecs = settings.job_specifications(config)
        if len(jobspecs) != 1:
            raise ValueError(
                'The number of jobs in the specified jobs config is not '
                'one. Please specify which job with --jobid.')
        if util.is_not_empty(taskid):
            raise ValueError(
                'cannot specify a task to tunnel Tensorboard to without the '
                'corresponding job id')
    misc.tunnel_tensorboard(batch_client, config, jobid, taskid, logdir, image)


def action_monitor_create(
        auth_client, resource_client, compute_client, network_client,
        blob_client, table_client, config):
    # type: (azure.mgmt.authorization.AuthorizationManagementClient,
    #        azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService, dict) -> None
    """Action: Monitor Create
    :param azure.mgmt.authorization.AuthorizationManagementClient auth_client:
        auth client
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    _check_resource_client(resource_client)
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    # ensure aad creds are populated
    mgmt_aad = settings.credentials_management(config)
    if (util.is_none_or_empty(mgmt_aad.subscription_id) or
            util.is_none_or_empty(mgmt_aad.aad.authority_url)):
        raise ValueError('management aad credentials are invalid')
    picket.create_monitoring_resource(
        auth_client, resource_client, compute_client, network_client,
        blob_client, table_client, config, _RESOURCES_PATH,
        _MONITORINGPREP_FILE, _CONFIGURABLE_MONITORING_FILES)


def action_monitor_add(table_client, config, poolid, fscluster):
    # type: (azure.cosmosdb.table.TableService, dict, List[str],
    #        List[str]) -> None
    """Action: Monitor Add
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param list poolid: list of pool ids to monitor
    :param list fscluster: list of fs clusters to monitor
    """
    if util.is_none_or_empty(poolid) and util.is_none_or_empty(fscluster):
        logger.error('no monitoring resources specified to add')
        return
    # ensure that we are operating in AAD mode for batch
    if util.is_not_empty(poolid):
        bc = settings.credentials_batch(config)
        _check_for_batch_aad(bc, 'add pool monitors')
    fsmap = None
    if util.is_not_empty(fscluster):
        fsmap = {}
        for sc_id in fscluster:
            rfs = settings.remotefs_settings(config, sc_id)
            sc = rfs.storage_cluster
            vms = []
            if sc.file_server.type == 'nfs':
                vm_name = settings.generate_virtual_machine_name(sc, 0)
                vms.append(vm_name)
            elif sc.file_server.type == 'glusterfs':
                for i in range(sc.vm_count):
                    vm_name = settings.generate_virtual_machine_name(sc, i)
                    vms.append(vm_name)
            fsmap[sc_id] = {
                'type': sc.file_server.type,
                'rg': sc.resource_group,
                'ne_port': sc.prometheus.ne_port,
                'as': settings.generate_availability_set_name(sc),
                'vms': vms,
            }
    storage.add_resources_to_monitor(table_client, config, poolid, fsmap)


def action_monitor_list(table_client, config):
    # type: (azure.cosmosdb.table.TableService, dict) -> None
    """Action: Monitor List
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    storage.list_monitored_resources(table_client, config)


def action_monitor_remove(table_client, config, all, poolid, fscluster):
    # type: (azure.cosmosdb.table.TableService, dict, bool, List[str],
    #        List[str]) -> None
    """Action: Monitor Remove
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool all: all resource monitors
    :param list poolid: list of pool ids to remove from monitoring
    :param list fscluster: list of fs clusters to monitor
    """
    # ensure that we are operating in AAD mode for batch
    if not all and util.is_not_empty(poolid):
        bc = settings.credentials_batch(config)
        _check_for_batch_aad(bc, 'remove pool monitors')
    if (not all and util.is_none_or_empty(poolid) and
            util.is_none_or_empty(fscluster)):
        logger.error('no monitoring resources specified to remove')
        return
    if all and (util.is_not_empty(poolid) or util.is_not_empty(fscluster)):
        raise ValueError(
            'cannot specify --all with specific monitoring resources to '
            'remove')
    storage.remove_resources_from_monitoring(
        table_client, config, all, poolid, fscluster)


def action_monitor_ssh(
        compute_client, network_client, config, tty, command):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict,
    #        bool, tuple) -> None
    """Action: Monitor Ssh
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param bool tty: allocate pseudo-tty
    :param tuple command: command
    """
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    picket.ssh_monitoring_resource(
        compute_client, network_client, config, tty, command)


def action_monitor_suspend(compute_client, config, wait):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, bool) -> None
    """Action: Monitor Suspend
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param bool wait: wait for suspension to complete
    """
    _check_compute_client(compute_client)
    picket.suspend_monitoring_resource(compute_client, config, wait)


def action_monitor_start(compute_client, config, wait):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, bool) -> None
    """Action: Monitor Start
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param bool wait: wait for restart to complete
    """
    _check_compute_client(compute_client)
    picket.start_monitoring_resource(compute_client, config, wait)


def action_monitor_destroy(
        resource_client, compute_client, network_client, blob_client,
        table_client, config, delete_all_resources, delete_virtual_network,
        generate_from_prefix, wait):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService, dict, bool, bool,
    #        bool, bool) -> None
    """Action: Monitor Destroy
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool delete_all_resources: delete all resources
    :param bool delete_virtual_network: delete virtual network
    :param bool generate_from_prefix: generate resources from hostname prefix
    :param bool wait: wait for deletion to complete
    """
    _check_resource_client(resource_client)
    _check_compute_client(compute_client)
    _check_network_client(network_client)
    if (generate_from_prefix and
            (delete_all_resources or delete_virtual_network)):
        raise ValueError(
            'Cannot specify generate_from_prefix and a delete_* option')
    picket.delete_monitoring_resource(
        resource_client, compute_client, network_client, blob_client,
        table_client, config, delete_virtual_network=delete_virtual_network,
        delete_resource_group=delete_all_resources,
        generate_from_prefix=generate_from_prefix, wait=wait)
