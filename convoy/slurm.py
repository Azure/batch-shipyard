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
    absolute_import, division, print_function
)
from builtins import (  # noqa
    bytes, dict, int, list, object, range, str, ascii, chr, hex, input,
    next, oct, open, pow, round, super, filter, map, zip)
# stdlib imports
import functools
import logging
import json
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import time
import uuid
# non-stdlib imports
import azure.batch.models as batchmodels
import azure.mgmt.authorization.models as authmodels
import msrestazure.azure_exceptions
# local imports
from . import crypto
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
_SLURM_POOL_METADATA_CLUSTER_ID_KEY = 'BATCH_SHIPYARD_SLURM_CLUSTER_ID'


def _apply_slurm_config_to_batch_pools(
        compute_client, network_client, batch_client, config, cluster_id,
        cn_blob_urls, ssh_pub_key, ssh_priv_key):
    bs = settings.batch_shipyard_settings(config)
    sa = settings.slurm_credentials_storage(config)
    ss = settings.slurm_settings(config, 'controller')
    slurm_opts = settings.slurm_options_settings(config)
    slurm_sdv = settings.slurm_shared_data_volumes(config)
    sc_fstab_mounts = []
    for sc in slurm_sdv:
        fm, _ = remotefs.create_storage_cluster_mount_args(
            compute_client, network_client, config,
            sc.id, sc.host_mount_path)
        sc_fstab_mounts.append(fm)
    for partname in slurm_opts.elastic_partitions:
        part = slurm_opts.elastic_partitions[partname]
        pool_count = 0
        rdma_internode_count = 0
        # query pools
        for pool_id in part.batch_pools:
            bpool = part.batch_pools[pool_id]
            try:
                pool = batch_client.pool.get(pool_id)
            except batchmodels.BatchErrorException as ex:
                if 'The specified pool does not exist' in ex.message.value:
                    raise ValueError(
                        'pool {} does not exist for slurm partition {}'.format(
                            pool_id, partname))
                raise
            # maintain counts for rdma internode
            pool_count += 1
            if (pool.enable_inter_node_communication and settings.is_rdma_pool(
                    pool.vm_size)):
                rdma_internode_count += 1
            # ensure pool is compatible
            na_sku = (
                pool.virtual_machine_configuration.node_agent_sku_id.lower()
            )
            if na_sku.startswith('batch.node.windows'):
                raise RuntimeError(
                    'Cannot create a Slurm partition {} on a Windows '
                    'pool {}'.format(partname, pool.id))
            elif (na_sku != 'batch.node.centos 7' and
                  na_sku != 'batch.node.ubuntu 16.04' and
                  na_sku != 'batch.node.ubuntu 18.04'):
                raise RuntimeError(
                    'Cannot create a Slurm partition {} on pool {} with node '
                    'agent sku id {}'.format(partname, pool.id, na_sku))
            # check pool metadata to ensure it's not already
            # included in an existing cluster
            if util.is_not_empty(pool.metadata):
                skip_pool = False
                for kvp in pool.metadata:
                    if kvp.name == _SLURM_POOL_METADATA_CLUSTER_ID_KEY:
                        if kvp.value != cluster_id:
                            raise RuntimeError(
                                'Pool {} for Slurm partition {} is already '
                                'part of a Slurm cluster {}'.format(
                                    pool.id, partname, kvp.value))
                        else:
                            logger.warning(
                                'Pool {} for Slurm partition {} is already '
                                'part of this Slurm cluster {}'.format(
                                    pool.id, partname, cluster_id))
                            skip_pool = True
                if skip_pool:
                    continue
            # ensure all node counts are zero
            if (pool.target_dedicated_nodes > 0 or
                    pool.target_low_priority_nodes > 0 or
                    (pool.current_dedicated_nodes +
                     pool.current_low_priority_nodes > 0)):
                raise RuntimeError(
                    'Pool {} has non-zero node counts for Slurm '
                    'partition {}'.format(pool.id, partname))
            # check for pool autoscale
            if pool.enable_auto_scale:
                logger.warning(
                    'Pool {} is autoscale-enabled for Slurm '
                    'partition {}'.format(pool.id, partname))
            # check vnet is in same vnet as slurm controller
            if (pool.network_configuration is None or
                    pool.network_configuration.subnet_id is None):
                raise RuntimeError(
                    'Pool {} has no network configuration for Slurm '
                    'partition {}. Pools must reside in the same virtual '
                    'network as the controller.'.format(pool.id, partname))
            vnet_subid, vnet_rg, _, vnet_name, _ = util.explode_arm_subnet_id(
                pool.network_configuration.subnet_id)
            if util.is_not_empty(ss.virtual_network.arm_subnet_id):
                s_vnet_subid, s_vnet_rg, _, s_vnet_name, _ = \
                    util.explode_arm_subnet_id(
                        ss.virtual_network.arm_subnet_id)
            else:
                mc = settings.credentials_management(config)
                s_vnet_subid = mc.subscription_id
                s_vnet_rg = ss.virtual_network.resource_group
                s_vnet_name = ss.virtual_network.name
            if vnet_subid.lower() != s_vnet_subid.lower():
                raise RuntimeError(
                    'Pool {} for Slurm partition {} is not in the same '
                    'virtual network as the controller. Subscription Id '
                    'mismatch: pool {} controller {}'.format(
                        pool.id, partname, vnet_subid, s_vnet_subid))
            if vnet_rg.lower() != s_vnet_rg.lower():
                raise RuntimeError(
                    'Pool {} for Slurm partition {} is not in the same '
                    'virtual network as the controller. Resource group '
                    'mismatch: pool {} controller {}'.format(
                        pool.id, partname, vnet_rg, s_vnet_rg))
            if vnet_name.lower() != s_vnet_name.lower():
                raise RuntimeError(
                    'Pool {} for Slurm partition {} is not in the same '
                    'virtual network as the controller. Virtual Network name '
                    'mismatch: pool {} controller {}'.format(
                        pool.id, partname, vnet_name, s_vnet_name))
            # check for glusterfs on compute
            if ' -f ' in pool.start_task.command_line:
                logger.warning(
                    'Detected possible GlusterFS on compute on pool {} for '
                    'Slurm partition {}'.format(pool.id, partname))

            # disable pool autoscale
            if pool.enable_auto_scale:
                logger.info('disabling pool autoscale for {}'.format(pool.id))
                batch_client.pool.disable_pool_autoscale(pool.id)

            # patch pool
            # 1. copy existing start task
            # 2. add cluter id metadata
            # 3. modify storage cluster env var
            # 4. append blob sas to resource files
            # 5. append slurm compute node bootstrap to end of command

            # copy start task and add cluster id
            patch_param = batchmodels.PoolPatchParameter(
                start_task=pool.start_task,
                metadata=[
                    batchmodels.MetadataItem(
                        name=_SLURM_POOL_METADATA_CLUSTER_ID_KEY,
                        value=cluster_id),
                ]
            )
            # modify storage cluster env var
            env_settings = []
            for env in pool.start_task.environment_settings:
                if env.name == 'SHIPYARD_STORAGE_CLUSTER_FSTAB':
                    env_settings.append(
                        batchmodels.EnvironmentSetting(
                            name=env.name,
                            value='#'.join(sc_fstab_mounts)
                        )
                    )
                else:
                    env_settings.append(env)
            env_settings.append(
                batchmodels.EnvironmentSetting(
                    name='SHIPYARD_SLURM_CLUSTER_USER_SSH_PUBLIC_KEY',
                    value=ssh_pub_key)
            )
            patch_param.start_task.environment_settings = env_settings
            # add resource file
            for rf in cn_blob_urls:
                patch_param.start_task.resource_files.append(
                    batchmodels.ResourceFile(
                        file_path=rf,
                        http_url=cn_blob_urls[rf])
                )
            # modify start task command
            ss_login = settings.slurm_settings(config, 'login')
            assign_qn = '{}-{}'.format(
                cluster_id,
                util.hash_string('{}-{}'.format(
                    partname, bpool.batch_service_url, pool_id)))
            start_cmd = patch_param.start_task.command_line.split('\'')
            start_cmd[1] = (
                '{pre}; shipyard_slurm_computenode_nodeprep.sh '
                '{a}{i}{q}{s}{u}{v}'
            ).format(
                pre=start_cmd[1],
                a=' -a {}'.format(
                    settings.determine_cloud_type_from_aad(config)),
                i=' -i {}'.format(cluster_id),
                q=' -q {}'.format(assign_qn),
                s=' -s {}:{}:{}:{}'.format(
                    sa.account,
                    sa.account_key,
                    sa.endpoint,
                    bs.storage_entity_prefix
                ),
                u=' -u {}'.format(ss_login.ssh.username),
                v=' -v {}'.format(__version__),
            )
            patch_param.start_task.command_line = '\''.join(start_cmd)
            if settings.verbose(config):
                logger.debug('patching pool {} start task cmd={}'.format(
                    pool_id, patch_param.start_task.command_line))
            batch_client.pool.patch(pool_id, pool_patch_parameter=patch_param)

        # check rdma internode is for single partition only
        if rdma_internode_count > 0 and pool_count != 1:
            raise RuntimeError(
                'Attempting to create a Slurm partition {} with multiple '
                'pools with one pool being RDMA internode comm enabled. '
                'IB/RDMA communication cannot span across Batch pools'.format(
                    partname))


def _get_pool_features(batch_client, config, pool_id, partname):
    try:
        pool = batch_client.pool.get(pool_id)
    except batchmodels.BatchErrorException as ex:
        if 'The specified pool does not exist' in ex.message.value:
            raise ValueError(
                'pool {} does not exist for slurm partition {}'.format(
                    pool_id, partname))
        raise
    vm_size = pool.vm_size.lower()
    num_gpus = 0
    gpu_class = None
    ib_class = None
    if settings.is_gpu_pool(vm_size):
        num_gpus = settings.get_num_gpus_from_vm_size(vm_size)
        gpu_class = settings.get_gpu_class_from_vm_size(vm_size)
    if settings.is_rdma_pool(vm_size):
        ib_class = settings.get_ib_class_from_vm_size(vm_size)
    return (vm_size, gpu_class, num_gpus, ib_class)


def _create_virtual_machine_extension(
        compute_client, network_client, config, vm_resource, bootstrap_file,
        blob_urls, vm_name, private_ips, fqdn, offset, cluster_id, kind,
        controller_vm_names, addl_prep, verbose=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.VmResource, str, List[str], str, List[str], str,
    #        int, str, bool
    #       ) -> msrestazure.azure_operation.AzureOperationPoller
    """Create a virtual machine extension
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param settings.VmResource vm_resource: VM resource
    :param str bootstrap_file: bootstrap file
    :param list blob_urls: blob urls
    :param str vm_name: vm name
    :param list private_ips: list of static private ips
    :param str fqdn: fqdn if public ip available
    :param int offset: vm number
    :param str cluster_id: cluster id
    :param bool verbose: verbose logging
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    bs = settings.batch_shipyard_settings(config)
    ss = settings.slurm_settings(config, kind)
    slurm_sdv = settings.slurm_shared_data_volumes(config)
    sc_args = []
    state_path = None
    for sc in slurm_sdv:
        _, sca = remotefs.create_storage_cluster_mount_args(
            compute_client, network_client, config,
            sc.id, sc.host_mount_path)
        sc_args.append(sca)
        if sc.store_slurmctld_state:
            state_path = '{}/.slurmctld_state'.format(sc.host_mount_path)
    # construct vm extensions
    vm_ext_name = settings.generate_virtual_machine_extension_name(
        vm_resource, offset)
    # try to get storage account resource group
    sa = settings.slurm_credentials_storage(config)
    # construct bootstrap command
    if kind == 'controller':
        if verbose:
            logger.debug('slurmctld state save path: {} on {}'.format(
                state_path, sc.id))
        ss_login = settings.slurm_settings(config, 'login')
        cmd = './{bsf}{a}{c}{i}{m}{p}{s}{u}{v}'.format(
            bsf=bootstrap_file[0],
            a=' -a {}'.format(settings.determine_cloud_type_from_aad(config)),
            c=' -c {}'.format(':'.join(controller_vm_names)),
            i=' -i {}'.format(cluster_id),
            m=' -m {}'.format(','.join(sc_args)) if util.is_not_empty(
                sc_args) else '',
            p=' -p {}'.format(state_path),
            s=' -s {}:{}:{}'.format(
                sa.account,
                sa.resource_group if util.is_not_empty(
                    sa.resource_group) else '',
                bs.storage_entity_prefix
            ),
            u=' -u {}'.format(ss_login.ssh.username),
            v=' -v {}'.format(__version__),
        )
    else:
        if settings.verbose(config):
            logger.debug('storage cluster args: {}'.format(sc_args))
        cmd = './{bsf}{a}{i}{login}{m}{s}{u}{v}'.format(
            bsf=bootstrap_file[0],
            a=' -a {}'.format(settings.determine_cloud_type_from_aad(config)),
            i=' -i {}'.format(cluster_id),
            login=' -l',
            m=' -m {}'.format(','.join(sc_args)) if util.is_not_empty(
                sc_args) else '',
            s=' -s {}:{}:{}'.format(
                sa.account,
                sa.resource_group if util.is_not_empty(
                    sa.resource_group) else '',
                bs.storage_entity_prefix
            ),
            u=' -u {}'.format(ss.ssh.username),
            v=' -v {}'.format(__version__),
        )
    if util.is_not_empty(addl_prep[kind]):
        tmp = pathlib.Path(addl_prep[kind])
        cmd = '{}; ./{}'.format(cmd, tmp.name)
        del tmp
    if verbose:
        logger.debug('{} bootstrap command: {}'.format(kind, cmd))
    logger.debug('creating virtual machine extension: {}'.format(vm_ext_name))
    return compute_client.virtual_machine_extensions.create_or_update(
        resource_group_name=vm_resource.resource_group,
        vm_name=vm_name,
        vm_extension_name=vm_ext_name,
        extension_parameters=compute_client.virtual_machine_extensions.models.
        VirtualMachineExtension(
            location=vm_resource.location,
            publisher='Microsoft.Azure.Extensions',
            virtual_machine_extension_type='CustomScript',
            type_handler_version='2.0',
            auto_upgrade_minor_version=True,
            settings={
                'fileUris': blob_urls,
            },
            protected_settings={
                'commandToExecute': cmd,
                'storageAccountName': sa.account,
                'storageAccountKey': sa.account_key,
            },
        ),
    )


def create_slurm_controller(
        auth_client, resource_client, compute_client, network_client,
        blob_client, table_client, queue_client, batch_client, config,
        resources_path, bootstrap_file, computenode_file, slurmpy_file,
        slurmreq_file, slurm_files):
    # type: (azure.mgmt.authorization.AuthorizationManagementClient,
    #        azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService,
    #        dict, pathlib.Path, Tuple[str, pathlib.Path],
    #        List[Tuple[str, pathlib.Path]]) -> None
    """Create a slurm controller
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
    :param pathlib.Path: resources path
    :param Tuple[str, pathlib.Path] bootstrap_file: customscript bootstrap file
    :param Tuple[str, pathlib.Path] computenode_file: compute node prep file
    :param List[Tuple[str, pathlib.Path]] slurm_files: slurm files
    """
    bs = settings.batch_shipyard_settings(config)
    slurm_opts = settings.slurm_options_settings(config)
    slurm_creds = settings.credentials_slurm(config)
    # construct slurm vm data structs
    ss = []
    ss_map = {}
    ss_kind = {}
    vm_counts = {}
    for kind in ('controller', 'login'):
        ss_kind[kind] = settings.slurm_settings(config, kind)
        vm_counts[kind] = settings.slurm_vm_count(config, kind)
        for _ in range(0, vm_counts[kind]):
            ss.append(ss_kind[kind])
            ss_map[len(ss) - 1] = kind
    # get subscription id for msi
    sub_id = settings.credentials_management(config).subscription_id
    if util.is_none_or_empty(sub_id):
        raise ValueError('Management subscription id not specified')
    # check if cluster already exists
    logger.debug('checking if slurm controller exists')
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=ss_kind['controller'].resource_group,
            vm_name=settings.generate_virtual_machine_name(
                ss_kind['controller'], 0)
        )
        raise RuntimeError(
            'Existing virtual machine {} found for slurm controller'.format(
                vm.id))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    # get shared file systems
    slurm_sdv = settings.slurm_shared_data_volumes(config)
    if util.is_none_or_empty(slurm_sdv):
        raise ValueError('shared_data_volumes must be specified')
    # confirm before proceeding
    if not util.confirm_action(config, 'create slurm cluster'):
        return
    # cluster id
    cluster_id = slurm_opts.cluster_id
    # create resource group if it doesn't exist
    resource.create_resource_group(
        resource_client, ss_kind['controller'].resource_group,
        ss_kind['controller'].location)
    # create storage containers
    storage.create_storage_containers_nonbatch(
        None, table_client, None, 'slurm')
    logger.info('creating Slurm cluster id: {}'.format(cluster_id))
    queue_client.create_queue(cluster_id)
    # fstab file
    sdv = settings.global_resources_shared_data_volumes(config)
    sc_fstab_mounts = []
    for sc in slurm_sdv:
        if not settings.is_shared_data_volume_storage_cluster(sdv, sc.id):
            raise ValueError(
                'non-storage cluster shared data volumes are currently '
                'not supported for Slurm clusters: {}'.format(sc.id))
        fm, _ = remotefs.create_storage_cluster_mount_args(
            compute_client, network_client, config,
            sc.id, sc.host_mount_path)
        sc_fstab_mounts.append(fm)
    fstab_file = resources_path / 'sdv.fstab'
    with fstab_file.open('wt') as f:
        f.write('#'.join(sc_fstab_mounts))
    del sc_fstab_mounts
    del sdv
    del slurm_sdv
    # compute nodes and partitions
    nodenames = []
    slurmpartinfo = []
    suspend_exc = []
    has_gpus = False
    for partname in slurm_opts.elastic_partitions:
        part = slurm_opts.elastic_partitions[partname]
        partnodes = []
        for pool_id in part.batch_pools:
            bpool = part.batch_pools[pool_id]
            bpool.features.append(bpool.compute_node_type)
            vm_size, gpu_class, num_gpus, ib_class = _get_pool_features(
                batch_client, config, pool_id, partname)
            bpool.features.append(vm_size)
            if gpu_class is not None:
                bpool.features.append('gpu')
                bpool.features.append(gpu_class)
                has_gpus = True
            if ib_class is not None:
                bpool.features.append('rdma')
                bpool.features.append(ib_class)
            features = ','.join(bpool.features)
            nodes = '{}-[0-{}]'.format(pool_id, bpool.max_compute_nodes - 1)
            nodenames.append(
                'NodeName={}{} Weight={}{} State=CLOUD\n'.format(
                    nodes,
                    ' Gres=gpu:{}'.format(num_gpus) if num_gpus > 0 else '',
                    bpool.weight,
                    ' Feature={}'.format(features if util.is_not_empty(
                        features) else '')))
            if bpool.reclaim_exclude_num_nodes > 0:
                suspend_exc.append('{}-[0-{}]'.format(
                    pool_id, bpool.reclaim_exclude_num_nodes - 1))
            partnodes.append(nodes)
            # create storage entities
            storage.create_slurm_partition(
                table_client, queue_client, config, cluster_id, partname,
                bpool.batch_service_url, pool_id, bpool.compute_node_type,
                bpool.max_compute_nodes, nodes)
        if util.is_not_empty(part.preempt_type):
            preempt_type = ' PreemptType={}'.format(part.preempt_type)
        else:
            preempt_type = ''
        if util.is_not_empty(part.preempt_mode):
            preempt_mode = ' PreemptMode={}'.format(part.preempt_mode)
        else:
            preempt_mode = ''
        if util.is_not_empty(part.over_subscribe):
            over_subscribe = ' OverSubscribe={}'.format(part.over_subscribe)
        else:
            over_subscribe = ''
        if util.is_not_empty(part.priority_tier):
            priority_tier = ' PriorityTier={}'.format(part.priority_tier)
        else:
            priority_tier = ''
        slurmpartinfo.append(
            'PartitionName={} Default={} MaxTime={}{}{}{}{} {} '
            'Nodes={}\n'.format(
                partname, part.default, part.max_runtime_limit,
                preempt_type, preempt_mode, over_subscribe, priority_tier,
                ' '.join(part.other_options), ','.join(partnodes)))
        del partnodes
    # configure files and write to resources
    with slurm_files['slurm'][1].open('r') as f:
        slurmdata = f.read()
    with slurm_files['slurmdbd'][1].open('r') as f:
        slurmdbddata = f.read()
    with slurm_files['slurmdbsql'][1].open('r') as f:
        slurmdbsqldata = f.read()
    slurmdata = slurmdata.replace(
        '{CLUSTER_NAME}', slurm_opts.cluster_id).replace(
            '{MAX_NODES}', str(slurm_opts.max_nodes)).replace(
                '{IDLE_RECLAIM_TIME_SEC}', str(int(
                    slurm_opts.idle_reclaim_time.total_seconds())))
    if util.is_not_empty(suspend_exc):
        slurmdata = slurmdata.replace(
            '#{SUSPEND_EXC_NODES}', 'SuspendExcNodes={}'.format(
                ','.join(suspend_exc)))
    if has_gpus:
        slurmdata = slurmdata.replace('#{GRES_TYPES}', 'GresTypes=gpu')
    unmanaged_partitions = []
    unmanaged_nodes = []
    for upart in slurm_opts.unmanaged_partitions:
        unmanaged_partitions.append(upart.partition)
        unmanaged_nodes.extend(upart.nodes)
    if util.is_not_empty(unmanaged_nodes):
        slurmdata = slurmdata.replace(
            '#{ADDITIONAL_NODES}', '\n'.join(unmanaged_nodes))
    if util.is_not_empty(unmanaged_partitions):
        slurmdata = slurmdata.replace(
            '#{ADDITIONAL_PARTITIONS}', '\n'.join(unmanaged_partitions))
    del unmanaged_partitions
    del unmanaged_nodes
    slurmdbddata = slurmdbddata.replace(
        '{SLURM_DB_PASSWORD}', slurm_creds.db_password)
    slurmdbsqldata = slurmdbsqldata.replace(
        '{SLURM_DB_PASSWORD}', slurm_creds.db_password)
    slurmconf = resources_path / slurm_files['slurm'][0]
    slurmdbdconf = resources_path / slurm_files['slurmdbd'][0]
    slurmdbsqlconf = resources_path / slurm_files['slurmdbsql'][0]
    with slurmconf.open('wt') as f:
        f.write(slurmdata)
        for node in nodenames:
            f.write(node)
        for part in slurmpartinfo:
            f.write(part)
    with slurmdbdconf.open('wt') as f:
        f.write(slurmdbddata)
    with slurmdbsqlconf.open('wt') as f:
        f.write(slurmdbsqldata)
    del slurmdata
    del slurmdbddata
    del slurmdbsqldata
    del nodenames
    del slurmpartinfo
    slurm_files = [
        bootstrap_file,
        slurmpy_file,
        slurmreq_file,
        (slurm_files['slurm'][0], slurmconf),
        (slurm_files['slurmdbd'][0], slurmdbdconf),
        (slurm_files['slurmdbsql'][0], slurmdbsqlconf),
        (fstab_file.name, fstab_file),
    ]
    addl_prep = {}
    for kind in ('controller', 'login'):
        addl_prep[kind] = settings.slurm_additional_prep_script(config, kind)
        if util.is_not_empty(addl_prep[kind]):
            tmp = pathlib.Path(addl_prep[kind])
            if not tmp.exists():
                raise RuntimeError('{} does not exist'.format(tmp))
            slurm_files.append((tmp.name, tmp))
            del tmp
    # create blob container
    sa = settings.slurm_credentials_storage(config)
    blob_container = '{}slurm-{}'.format(bs.storage_entity_prefix, cluster_id)
    blob_client.create_container(blob_container)
    # read or generate ssh keys
    ssh_pub_key = {}
    ssh_priv_key = {}
    for i in range(0, len(ss)):
        kind = ss_map[i]
        if kind in ssh_pub_key:
            continue
        priv_key = ss[i].ssh.ssh_private_key
        if util.is_not_empty(ss[i].ssh.ssh_public_key_data):
            key_data = ss[i].ssh.ssh_public_key_data
        else:
            # create universal ssh key for all vms if not specified
            pub_key = ss[i].ssh.ssh_public_key
            if pub_key is None:
                priv_key, pub_key = crypto.generate_ssh_keypair(
                    ss[i].ssh.generated_file_export_path,
                    crypto.get_slurm_ssh_key_prefix(ss_map[i]))
            # read public key data
            with pub_key.open('rb') as fd:
                key_data = fd.read().decode('utf8')
        if kind == 'login':
            if priv_key is None:
                raise ValueError('SSH private key for login nodes is invalid')
            tmp = pathlib.Path(priv_key)
            if not tmp.exists():
                raise ValueError(
                    'SSH private key for login nodes does not '
                    'exist: {}'.format(tmp))
            ssh_priv_key[kind] = tmp
            del tmp
        ssh_pub_key[kind] = \
            compute_client.virtual_machines.models.SshPublicKey(
                path='/home/{}/.ssh/authorized_keys'.format(
                    ss[i].ssh.username),
                key_data=key_data)
    # upload compute node files
    cn_files = [
        computenode_file,
        ('slurm_cluster_user_ssh_private_key', ssh_priv_key['login']),
    ]
    cn_blob_urls = storage.upload_to_container(
        blob_client, sa, cn_files, blob_container, gen_sas=True)
    # mutate pool configurations
    _apply_slurm_config_to_batch_pools(
        compute_client, network_client, batch_client, config, cluster_id,
        cn_blob_urls, ssh_pub_key['login'].key_data, ssh_priv_key['login'])
    del cn_files
    del ssh_priv_key
    # create file share for logs persistence and munge key
    storage.create_file_share_saskey(
        settings.credentials_storage(
            config,
            bs.storage_account_settings,
        ),
        '{}slurm'.format(bs.storage_entity_prefix),
        'ingress',
        create_share=True,
    )
    # upload scripts to blob storage for customscript vm extension
    blob_urls = list(storage.upload_to_container(
        blob_client, sa, slurm_files, blob_container, gen_sas=False).values())
    try:
        slurmconf.unlink()
    except OSError:
        pass
    try:
        slurmdbdconf.unlink()
    except OSError:
        pass
    try:
        slurmdbsqlconf.unlink()
    except OSError:
        pass
    try:
        fstab_file.unlink()
    except OSError:
        pass
    # async operation dictionary
    async_ops = {}
    # create nsg
    nsg_set = set()
    async_ops['nsg'] = {}
    for i in range(0, len(ss)):
        kind = ss_map[i]
        if kind in nsg_set:
            continue
        async_ops['nsg'][kind] = resource.AsyncOperation(functools.partial(
            resource.create_network_security_group, network_client, ss[i]))
        nsg_set.add(kind)
    del nsg_set
    # use static private ips for controller, dynamic ips for all others
    cont_private_ip_block = [
        x for x in util.ip_from_address_prefix(
            ss[0].virtual_network.subnet_address_prefix,
            start_offset=4,
            max=vm_counts['controller'])
    ]
    ip_offset = 0
    private_ips = {}
    for i in ss_map:
        if ss_map[i] == 'controller':
            private_ips[i] = cont_private_ip_block[ip_offset]
            ip_offset += 1
        else:
            private_ips[i] = None
    del cont_private_ip_block
    del ip_offset
    logger.debug('private ip assignment: {}'.format(private_ips))
    # create virtual network and subnet if specified
    vnet = {}
    subnet = {}
    for i in range(0, len(ss)):
        vnet[i], subnet[i] = resource.create_virtual_network_and_subnet(
            resource_client, network_client,
            ss[i].virtual_network.resource_group, ss[i].location,
            ss[i].virtual_network)
    # create public ips
    pips = None
    async_ops['pips'] = {}
    for i in range(0, len(ss)):
        if ss[i].public_ip.enabled:
            async_ops['pips'][i] = resource.AsyncOperation(functools.partial(
                resource.create_public_ip, network_client, ss[i], i))
            if pips is None:
                pips = {}
    if pips is not None:
        logger.debug('waiting for public ips to provision')
        for offset in async_ops['pips']:
            pip = async_ops['pips'][offset].result()
            logger.info(
                ('public ip: {} [provisioning_state={} ip_address={} '
                 'public_ip_allocation={}]').format(
                     pip.id, pip.provisioning_state,
                     pip.ip_address, pip.public_ip_allocation_method))
            pips[offset] = pip
    # get nsg
    logger.debug('waiting for network security groups to provision')
    nsg = {}
    for kind in async_ops['nsg']:
        nsg[kind] = async_ops['nsg'][kind].result()
    # create availability set if vm_count > 1, this call is not async
    availset = {}
    for kind in ('controller', 'login'):
        if vm_counts[kind] > 1:
            availset[kind] = resource.create_availability_set(
                compute_client, ss_kind[kind], vm_counts[kind])
        else:
            availset[kind] = None
    # create nics
    async_ops['nics'] = {}
    for i in range(0, len(ss)):
        kind = ss_map[i]
        async_ops['nics'][i] = resource.AsyncOperation(functools.partial(
            resource.create_network_interface, network_client, ss[i],
            subnet[i], nsg[kind], private_ips, pips, i))
    # wait for nics to be created
    logger.debug('waiting for network interfaces to provision')
    nics = {}
    for offset in async_ops['nics']:
        kind = ss_map[offset]
        nic = async_ops['nics'][offset].result()
        logger.info(
            ('network interface: {} [provisioning_state={} private_ip={} '
             'private_ip_allocation_method={} network_security_group={} '
             'accelerated_networking={}]').format(
                 nic.id, nic.provisioning_state,
                 nic.ip_configurations[0].private_ip_address,
                 nic.ip_configurations[0].private_ip_allocation_method,
                 nsg[kind].name if nsg[kind] is not None else None,
                 nic.enable_accelerated_networking))
        nics[offset] = nic
    # create vms
    async_ops['vms'] = {}
    for i in range(0, len(ss)):
        kind = ss_map[i]
        async_ops['vms'][i] = resource.AsyncOperation(functools.partial(
            resource.create_virtual_machine, compute_client, ss[i],
            availset[kind], nics, None, ssh_pub_key[kind], i, enable_msi=True,
            tags={
                'cluster_id': cluster_id,
                'node_kind': ss_map[i],
            },
        ))
    # wait for vms to be created
    logger.info(
        'waiting for {} virtual machines to provision'.format(
            len(async_ops['vms'])))
    vms = {}
    for offset in async_ops['vms']:
        vms[offset] = async_ops['vms'][offset].result()
    logger.debug('{} virtual machines created'.format(len(vms)))
    # create role assignments for msi identity
    logger.debug('assigning roles to msi identity')
    sub_scope = '/subscriptions/{}/'.format(sub_id)
    cont_role = None
    for role in auth_client.role_definitions.list(
            sub_scope, filter='roleName eq \'Contributor\''):
        cont_role = role.id
        break
    if cont_role is None:
        raise RuntimeError('Role Id not found for Reader')
    # sometimes the sp created is not added to the directory in time for
    # the following call, allow some retries before giving up
    attempts = 0
    role_assign_done = set()
    while attempts < 90:
        try:
            for i in range(0, len(ss)):
                if i in role_assign_done:
                    continue
                role_assign = auth_client.role_assignments.create(
                    scope=sub_scope,
                    role_assignment_name=uuid.uuid4(),
                    parameters=authmodels.RoleAssignmentCreateParameters(
                        role_definition_id=cont_role,
                        principal_id=vms[i].identity.principal_id
                    ),
                )
                role_assign_done.add(i)
                if settings.verbose(config):
                    logger.debug('reader role assignment: {}'.format(
                        role_assign))
            break
        except msrestazure.azure_exceptions.CloudError:
            time.sleep(2)
            attempts += 1
            if attempts == 90:
                raise
    del attempts
    cont_role = None
    for role in auth_client.role_definitions.list(
            sub_scope, filter='roleName eq \'Reader and Data Access\''):
        cont_role = role.id
        break
    if cont_role is None:
        raise RuntimeError('Role Id not found for Reader and Data Access')
    attempts = 0
    role_assign_done = set()
    while attempts < 30:
        try:
            for i in range(0, len(ss)):
                if i in role_assign_done:
                    continue
                role_assign = auth_client.role_assignments.create(
                    scope=sub_scope,
                    role_assignment_name=uuid.uuid4(),
                    parameters=authmodels.RoleAssignmentCreateParameters(
                        role_definition_id=cont_role,
                        principal_id=vms[i].identity.principal_id
                    ),
                )
                role_assign_done.add(i)
                if settings.verbose(config):
                    logger.debug(
                        'reader and data access role assignment: {}'.format(
                            role_assign))
            break
        except msrestazure.azure_exceptions.CloudError:
            time.sleep(2)
            attempts += 1
            if attempts == 30:
                raise
    del attempts
    # get ip info for vm
    fqdn = {}
    ipinfo = {}
    for i in range(0, len(ss)):
        if util.is_none_or_empty(pips):
            fqdn[i] = None
            ipinfo[i] = 'private_ip_address={}'.format(
                nics[i].ip_configurations[i].private_ip_address)
        else:
            # refresh public ip for vm
            pip = network_client.public_ip_addresses.get(
                resource_group_name=ss[i].resource_group,
                public_ip_address_name=pips[i].name,
            )
            fqdn[i] = pip.dns_settings.fqdn
            ipinfo[i] = 'fqdn={} public_ip_address={}'.format(
                fqdn[i], pip.ip_address)
    # gather all controller vm names
    controller_vm_names = []
    for i in range(0, len(ss)):
        if ss_map[i] == 'controller':
            controller_vm_names.append(vms[i].name)
    # install vm extension
    async_ops['vmext'] = {}
    for i in range(0, len(ss)):
        async_ops['vmext'][i] = resource.AsyncOperation(
            functools.partial(
                _create_virtual_machine_extension, compute_client,
                network_client, config, ss[i], bootstrap_file, blob_urls,
                vms[i].name, private_ips, fqdn[i], i, cluster_id, ss_map[i],
                controller_vm_names, addl_prep, settings.verbose(config)),
            max_retries=0,
        )
    logger.debug('waiting for virtual machine extensions to provision')
    for offset in async_ops['vmext']:
        # get vm extension result
        vm_ext = async_ops['vmext'][offset].result()
        vm = vms[offset]
        logger.info(
            ('virtual machine: {} [provisioning_state={}/{} '
             'vm_size={} {}]').format(
                vm.id, vm.provisioning_state, vm_ext.provisioning_state,
                vm.hardware_profile.vm_size, ipinfo[offset]))


def delete_slurm_controller(
        resource_client, compute_client, network_client, blob_client,
        table_client, queue_client, config, delete_virtual_network=False,
        delete_resource_group=False, generate_from_prefix=False, wait=False):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService,
    #        azure.storage.queue.QueueService,
    #        dict, bool, bool, bool, bool) -> None
    """Delete a slurm controller
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param dict config: configuration dict
    :param bool delete_virtual_network: delete vnet
    :param bool delete_resource_group: delete resource group
    :param bool generate_from_prefix: generate resources from hostname prefix
    :param bool wait: wait for completion
    """
    ss = []
    for kind in ('controller', 'login'):
        ss_kind = settings.slurm_settings(config, kind)
        for i in range(0, settings.slurm_vm_count(config, kind)):
            ss.append(ss_kind)
    # delete rg if specified
    if delete_resource_group:
        if util.confirm_action(
                config, 'delete resource group {}'.format(
                    ss.resource_group)):
            logger.info('deleting resource group {}'.format(
                ss[0].resource_group))
            async_delete = resource_client.resource_groups.delete(
                resource_group_name=ss[0].resource_group)
            if wait:
                logger.debug('waiting for resource group {} to delete'.format(
                    ss[0].resource_group))
                async_delete.result()
                logger.info('resource group {} deleted'.format(
                    ss[0].resource_group))
        return
    if not util.confirm_action(config, 'delete slurm controller'):
        return
    # get vms and cache for concurent async ops
    resources = {}
    for i in range(0, len(ss)):
        vm_name = settings.generate_virtual_machine_name(ss[i], i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=ss[i].resource_group,
                vm_name=vm_name,
            )
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                logger.warning('virtual machine {} not found'.format(vm_name))
                if generate_from_prefix:
                    logger.warning(
                        'OS and data disks for this virtual machine will not '
                        'be deleted, please use "fs disks del" to delete '
                        'those resources if desired')
                    resources[i] = {
                        'vm': settings.generate_virtual_machine_name(
                            ss[i], i),
                        'as': None,
                        'nic': settings.generate_network_interface_name(
                            ss[i], i),
                        'pip': settings.generate_public_ip_name(ss[i], i),
                        'subnet': None,
                        'nsg': settings.generate_network_security_group_name(
                            ss[i]),
                        'vnet': None,
                        'os_disk': None,
                    }
            else:
                raise
        else:
            # get resources connected to vm
            nic, pip, subnet, vnet, nsg = \
                resource.get_resource_names_from_virtual_machine(
                    compute_client, network_client, ss[i], vm)
            resources[i] = {
                'vm': vm.name,
                'arm_id': vm.id,
                'id': vm.vm_id,
                'as': None,
                'nic': nic,
                'pip': pip,
                'subnet': subnet,
                'nsg': nsg,
                'vnet': vnet,
                'os_disk': vm.storage_profile.os_disk.name,
                'tags': vm.tags,
            }
            # populate availability set
            if vm.availability_set is not None:
                resources[i]['as'] = vm.availability_set.id.split('/')[-1]
            # unset virtual network if not specified to delete
            if not delete_virtual_network:
                resources[i]['subnet'] = None
                resources[i]['vnet'] = None
    if len(resources) == 0:
        logger.warning('no resources deleted')
        return
    if settings.verbose(config):
        logger.debug('deleting the following resources:{}{}'.format(
            os.linesep, json.dumps(resources, sort_keys=True, indent=4)))
    try:
        cluster_id = resources[0]['tags']['cluster_id']
    except KeyError:
        if not generate_from_prefix:
            logger.error('cluster_id not found!')
        cluster_id = None
    # create async op holder
    async_ops = {}
    # delete vms
    async_ops['vms'] = {}
    for key in resources:
        vm_name = resources[key]['vm']
        async_ops['vms'][vm_name] = resource.AsyncOperation(functools.partial(
            resource.delete_virtual_machine, compute_client,
            ss[key].resource_group, vm_name), retry_conflict=True)
    logger.info(
        'waiting for {} virtual machines to delete'.format(
            len(async_ops['vms'])))
    for vm_name in async_ops['vms']:
        async_ops['vms'][vm_name].result()
    logger.info('{} virtual machines deleted'.format(len(async_ops['vms'])))
    # delete nics
    async_ops['nics'] = {}
    for key in resources:
        nic_name = resources[key]['nic']
        async_ops['nics'][nic_name] = resource.AsyncOperation(
            functools.partial(
                resource.delete_network_interface, network_client,
                ss[key].resource_group, nic_name),
            retry_conflict=True
        )
    # wait for nics to delete
    logger.debug('waiting for {} network interfaces to delete'.format(
        len(async_ops['nics'])))
    for nic_name in async_ops['nics']:
        async_ops['nics'][nic_name].result()
    logger.info('{} network interfaces deleted'.format(len(async_ops['nics'])))
    # delete os disks
    async_ops['os_disk'] = []
    for key in resources:
        os_disk = resources[key]['os_disk']
        if util.is_none_or_empty(os_disk):
            continue
        async_ops['os_disk'].append(remotefs.delete_managed_disks(
            resource_client, compute_client, config, os_disk,
            resource_group=ss[key].resource_group, wait=False,
            confirm_override=True))
    # delete nsg
    deleted = set()
    async_ops['nsg'] = {}
    for key in resources:
        nsg_name = resources[key]['nsg']
        if nsg_name in deleted:
            continue
        deleted.add(nsg_name)
        async_ops['nsg'][nsg_name] = resource.AsyncOperation(functools.partial(
            resource.delete_network_security_group, network_client,
            ss[key].resource_group, nsg_name), retry_conflict=True)
    deleted.clear()
    # delete public ips
    async_ops['pips'] = {}
    for key in resources:
        pip_name = resources[key]['pip']
        if util.is_none_or_empty(pip_name):
            continue
        async_ops['pips'][pip_name] = resource.AsyncOperation(
            functools.partial(
                resource.delete_public_ip, network_client,
                ss[key].resource_group, pip_name),
            retry_conflict=True
        )
    logger.debug('waiting for {} public ips to delete'.format(
        len(async_ops['pips'])))
    for pip_name in async_ops['pips']:
        async_ops['pips'][pip_name].result()
    logger.info('{} public ips deleted'.format(len(async_ops['pips'])))
    # delete subnets
    async_ops['subnets'] = {}
    for key in resources:
        subnet_name = resources[key]['subnet']
        vnet_name = resources[key]['vnet']
        if util.is_none_or_empty(subnet_name) or subnet_name in deleted:
            continue
        deleted.add(subnet_name)
        async_ops['subnets'][subnet_name] = resource.AsyncOperation(
            functools.partial(
                resource.delete_subnet, network_client,
                ss[key].virtual_network.resource_group, vnet_name,
                subnet_name),
            retry_conflict=True
        )
    logger.debug('waiting for {} subnets to delete'.format(
        len(async_ops['subnets'])))
    for subnet_name in async_ops['subnets']:
        async_ops['subnets'][subnet_name].result()
    logger.info('{} subnets deleted'.format(len(async_ops['subnets'])))
    deleted.clear()
    # delete vnet
    async_ops['vnets'] = {}
    for key in resources:
        vnet_name = resources[key]['vnet']
        if util.is_none_or_empty(vnet_name) or vnet_name in deleted:
            continue
        deleted.add(vnet_name)
        async_ops['vnets'][vnet_name] = resource.AsyncOperation(
            functools.partial(
                resource.delete_virtual_network, network_client,
                ss[key].virtual_network.resource_group, vnet_name),
            retry_conflict=True
        )
    deleted.clear()
    # delete availability set, this is synchronous
    for key in resources:
        as_name = resources[key]['as']
        if util.is_none_or_empty(as_name) or as_name in deleted:
            continue
        deleted.add(as_name)
        resource.delete_availability_set(
            compute_client, ss[key].resource_group, as_name)
        logger.info('availability set {} deleted'.format(as_name))
    deleted.clear()
    # clean up storage
    if util.is_not_empty(cluster_id):
        # delete file share directory
        bs = settings.batch_shipyard_settings(config)
        storage.delete_file_share_directory(
            settings.credentials_storage(
                config,
                bs.storage_account_settings,
            ),
            '{}slurm'.format(bs.storage_entity_prefix),
            cluster_id,
        )
        # delete queues and blobs
        queues = queue_client.list_queues(prefix=cluster_id)
        for queue in queues:
            logger.debug('deleting queue: {}'.format(queue.name))
            queue_client.delete_queue(queue.name)
        blob_container = '{}slurm-{}'.format(
            bs.storage_entity_prefix, cluster_id)
        logger.debug('deleting container: {}'.format(blob_container))
        blob_client.delete_container(blob_container)
        # clear slurm table for cluster
        storage.clear_slurm_table_entities(table_client, cluster_id)
    # delete boot diagnostics storage containers
    for key in resources:
        try:
            vm_name = resources[key]['vm']
            vm_id = resources[key]['id']
        except KeyError:
            pass
        else:
            storage.delete_storage_containers_boot_diagnostics(
                blob_client, vm_name, vm_id)
    # wait for all async ops to complete
    if wait:
        logger.debug('waiting for network security groups to delete')
        for nsg_name in async_ops['nsg']:
            async_ops['nsg'][nsg_name].result()
        logger.info('{} network security groups deleted'.format(
            len(async_ops['nsg'])))
        logger.debug('waiting for virtual networks to delete')
        for vnet_name in async_ops['vnets']:
            async_ops['vnets'][vnet_name].result()
        logger.info('{} virtual networks deleted'.format(
            len(async_ops['vnets'])))
        logger.debug('waiting for managed os disks to delete')
        count = 0
        for os_disk_set in async_ops['os_disk']:
            for os_disk in os_disk_set:
                os_disk_set[os_disk].result()
                count += 1
        logger.info('{} managed os disks deleted'.format(count))
