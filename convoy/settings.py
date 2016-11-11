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
        'input_data', 'input_data_azure_storage',
        'gpu_driver', 'ssh', 'additional_node_prep_commands',
    ]
)
SSHSettings = collections.namedtuple(
    'SSHSettings', [
        'username', 'expiry_days', 'ssh_public_key',
        'generate_docker_tunnel_script', 'generated_file_export_path',
        'hpn_server_swap'
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
