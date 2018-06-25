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
import json
import logging
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
# non-stdlib imports
import msrestazure.azure_exceptions
# local imports
from . import crypto
from . import resource
from . import settings
from . import storage
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)


def _create_managed_disk(compute_client, rfs, disk_name):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.RemoteFsSettings, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Create a managed disk
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param settings.RemoteFsSettings rfs: remote filesystem settings
    :param str disk_name: disk name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async operation handle
    """
    account_type = (
        compute_client.disks.models.StorageAccountTypes.premium_lrs
        if rfs.managed_disks.premium else
        compute_client.disks.models.StorageAccountTypes.standard_lrs
    )
    logger.info('creating managed disk: {}'.format(disk_name))
    return compute_client.disks.create_or_update(
        resource_group_name=rfs.managed_disks.resource_group,
        disk_name=disk_name,
        disk=compute_client.disks.models.Disk(
            location=rfs.managed_disks.location,
            creation_data=compute_client.disks.models.CreationData(
                create_option=compute_client.disks.models.
                DiskCreateOption.empty,
            ),
            sku=compute_client.disks.models.DiskSku(
                name=account_type,
            ),
            os_type=compute_client.disks.models.OperatingSystemTypes.linux,
            disk_size_gb=rfs.managed_disks.disk_size_gb,
        ),
    )


def create_managed_disks(resource_client, compute_client, config, wait=True):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient, dict, bool) -> None
    """Create managed disks
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param bool wait: wait for operation to complete
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    # create resource group if it doesn't exist
    resource.create_resource_group(
        resource_client, rfs.managed_disks.resource_group,
        rfs.managed_disks.location)
    # iterate disks and create disks if they don't exist
    existing_disk_sizes = set()
    async_ops = {}
    for disk_name in rfs.managed_disks.disk_names:
        try:
            disk = compute_client.disks.get(
                resource_group_name=rfs.managed_disks.resource_group,
                disk_name=disk_name)
            logger.debug('{} exists [created={} size={} GB]'.format(
                disk.id, disk.time_created, disk.disk_size_gb))
            existing_disk_sizes.add(disk.disk_size_gb)
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                existing_disk_sizes.add(rfs.managed_disks.disk_size_gb)
                if len(existing_disk_sizes) != 1:
                    existing_disk_sizes.discard(rfs.managed_disks.disk_size_gb)
                    raise RuntimeError(
                        ('Inconsistent disk sizes for newly created disks '
                         '({} GB) to existing disks ({} GB)').format(
                             rfs.managed_disks.disk_size_gb,
                             existing_disk_sizes)
                    )
                async_ops[disk_name] = resource.AsyncOperation(
                    functools.partial(
                        _create_managed_disk, compute_client, rfs, disk_name))
            else:
                raise
    # block for all ops to complete if specified
    # note that if wait is not specified and there is no delay, the request
    # may not get acknowledged...
    if wait:
        if len(async_ops) > 0:
            logger.debug('waiting for all {} disks to provision'.format(
                len(async_ops)))
        for disk_name in async_ops:
            disk = async_ops[disk_name].result()
            logger.info('{} created with size of {} GB'.format(
                disk.id, disk.disk_size_gb))


def delete_managed_disks(
        resource_client, compute_client, config, name, resource_group=None,
        all=False, delete_resource_group=False, wait=False,
        confirm_override=False):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient, dict, str or list,
    #        bool, bool, bool, bool) -> dict
    """Delete managed disks
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str or list name: specific disk name or list of names
    :param str resource_group: resource group of the disks
    :param bool all: delete all disks in resource group
    :param bool delete_resource_group: delete resource group
    :param bool wait: wait for operation to complete
    :param bool confirm_override: override confirmation of delete
    :rtype: dict or None
    :return: dictionary of disk names -> async ops if wait is False,
        otherwise None
    """
    # retrieve remotefs settings if necessary
    rfs = None
    if resource_group is None:
        rfs = settings.remotefs_settings(config)
        resource_group = rfs.managed_disks.resource_group
    # delete rg if specified
    if delete_resource_group:
        if (not confirm_override and not util.confirm_action(
                config, 'delete resource group {}'.format(resource_group))):
            return
        logger.info('deleting resource group {}'.format(resource_group))
        async_delete = resource_client.resource_groups.delete(
            resource_group_name=resource_group)
        if wait:
            logger.debug('waiting for resource group {} to delete'.format(
                resource_group))
            async_delete.result()
            logger.info('resource group {} deleted'.format(
                resource_group))
        return
    # set disks to delete
    if all:
        disks = [
            x[0].split('/')[-1] for x in list_disks(
                compute_client, config, resource_group=resource_group,
                restrict_scope=False)
        ]
    else:
        if util.is_none_or_empty(name):
            if rfs is None:
                rfs = settings.remotefs_settings(config)
            disks = rfs.managed_disks.disk_names
        else:
            if isinstance(name, list):
                disks = name
            else:
                disks = [name]
    # iterate disks and delete them
    async_ops = {}
    for disk_name in disks:
        if (not confirm_override and not util.confirm_action(
                config,
                'delete managed disk {} from resource group {}'.format(
                    disk_name, resource_group))):
            continue
        logger.info('deleting managed disk {} in resource group {}'.format(
            disk_name, resource_group))
        async_ops[disk_name] = resource.AsyncOperation(functools.partial(
            compute_client.disks.delete, resource_group_name=resource_group,
            disk_name=disk_name), retry_conflict=True)
    # block for all ops to complete if specified
    if wait:
        if len(async_ops) > 0:
            logger.debug('waiting for all {} disks to be deleted'.format(
                len(async_ops)))
        for disk_name in async_ops:
            async_ops[disk_name].result()
        logger.info('{} managed disks deleted in resource group {}'.format(
            len(async_ops), resource_group))
    else:
        return async_ops


def list_disks(
        compute_client, config, resource_group=None, restrict_scope=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, str, bool) ->
    #        List[str, computemodels.StorageAccountTypes]
    """List managed disks
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str resource_group: resource group to list from
    :param bool restrict_scope: restrict scope to config
    :rtype: list
    :return list of (disk ids, disk account type)
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    confdisks = frozenset(rfs.managed_disks.disk_names)
    resource_group = resource_group or rfs.managed_disks.resource_group
    # list disks in resource group
    logger.debug(
        ('listing all managed disks in resource group {} '
         '[restrict_scope={}]').format(resource_group, restrict_scope))
    disks = compute_client.disks.list_by_resource_group(
        resource_group_name=resource_group)
    ret = []
    i = 0
    for disk in disks:
        if restrict_scope and disk.name not in confdisks:
            continue
        logger.info(
            '{} [provisioning_state={} created={} size={} type={}]'.format(
                disk.id, disk.provisioning_state, disk.time_created,
                disk.disk_size_gb, disk.sku.name))
        ret.append((disk.id, disk.sku.name))
        i += 1
    if i == 0:
        logger.error(
            ('no managed disks found in resource group {} '
             '[restrict_scope={}]').format(resource_group, restrict_scope))
    return ret


def _create_virtual_machine_extension(
        compute_client, rfs, bootstrap_file, blob_urls, vm_name, disks,
        private_ips, offset, verbose=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.RemoteFsSettings, str, List[str], str, dict, List[str],
    #        int) -> msrestazure.azure_operation.AzureOperationPoller
    """Create a virtual machine extension
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param settings.RemoteFsSettings rfs: remote filesystem settings
    :param str bootstrap_file: bootstrap file
    :param list blob_urls: blob urls
    :param str vm_name: vm name
    :param dict disks: data disk map
    :param list private_ips: list of static private ips
    :param int offset: vm number
    :param bool verbose: verbose logging
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    # construct vm extensions
    vm_ext_name = settings.generate_virtual_machine_extension_name(
        rfs.storage_cluster, offset)
    # get premium storage settings
    premium = False
    for diskname in rfs.storage_cluster.vm_disk_map[offset].disk_array:
        if (disks[diskname][1] ==
                compute_client.disks.models.StorageAccountTypes.premium_lrs):
            premium = True
            break
    # construct server options
    server_options = []
    st = rfs.storage_cluster.file_server.type
    so = rfs.storage_cluster.file_server.server_options
    # special processing for gluster
    if st == 'glusterfs':
        # always create the following options if they don't exist
        server_options.append(
            settings.get_file_server_glusterfs_volume_name(
                rfs.storage_cluster))
        server_options.append(
            settings.get_file_server_glusterfs_volume_type(
                rfs.storage_cluster))
        server_options.append(
            settings.get_file_server_glusterfs_transport(
                rfs.storage_cluster))
        # process key pairs
        if st in so:
            for key in so[st]:
                if (key == 'volume_name' or key == 'volume_type' or
                        key == 'transport'):
                    continue
                server_options.append('{}:{}'.format(key, so[st][key]))
        server_options = ','.join(server_options)
    elif st == 'nfs':
        try:
            nfs_hosts = so[st]
        except KeyError:
            nfs_hosts = None
        if util.is_none_or_empty(nfs_hosts):
            nfs_hosts = {'*': []}
        nfs_exports = []
        for host in nfs_hosts:
            opt = []
            for eo in nfs_hosts[host]:
                if (not eo.startswith('mountpath=') and
                        not eo.startswith('mp=')):
                    opt.append(eo)
            if util.is_none_or_empty(opt):
                opt.extend(['rw', 'sync', 'root_squash', 'no_subtree_check'])
            nfs_exports.append('{}%{}'.format(host, ','.join(opt)))
        server_options = ';'.join(nfs_exports)
        del nfs_hosts
        del nfs_exports
    logger.debug('server options: {}'.format(server_options))
    # create samba option
    if util.is_not_empty(rfs.storage_cluster.file_server.samba.share_name):
        samba = rfs.storage_cluster.file_server.samba
        smb = '{share}:{user}:{pw}:{uid}:{gid}:{ro}:{cm}:{dm}'.format(
            share=samba.share_name,
            user=samba.account.username,
            pw=samba.account.password,
            uid=samba.account.uid,
            gid=samba.account.gid,
            ro=samba.read_only,
            cm=samba.create_mask,
            dm=samba.directory_mask,
        )
    else:
        smb = None
    # construct bootstrap command
    if rfs.storage_cluster.prometheus.ne_enabled:
        if util.is_not_empty(rfs.storage_cluster.prometheus.ne_options):
            pneo = ','.join(rfs.storage_cluster.prometheus.ne_options)
        else:
            pneo = ''
        promopt = ' -e \'{},{}\''.format(
            rfs.storage_cluster.prometheus.ne_port, pneo)
        del pneo
    else:
        promopt = ''
    cmd = './{bsf} {c}{d}{e}{f}{i}{m}{n}{o}{p}{r}{s}{t}'.format(
        bsf=bootstrap_file,
        c=' -c \'{}\''.format(smb) if util.is_not_empty(smb) else '',
        d=' -d {}'.format(rfs.storage_cluster.hostname_prefix),
        e=promopt,
        f=' -f {}'.format(rfs.storage_cluster.vm_disk_map[offset].filesystem),
        i=' -i {}'.format(
            ','.join(private_ips)) if util.is_not_empty(private_ips) else '',
        m=' -m {}'.format(rfs.storage_cluster.file_server.mountpoint),
        n=' -n' if settings.can_tune_tcp(rfs.storage_cluster.vm_size) else '',
        o=' -o \'{}\''.format(server_options) if util.is_not_empty(
            server_options) else '',
        p=' -p' if premium else '',
        r=' -r {}'.format(rfs.storage_cluster.vm_disk_map[offset].raid_level),
        s=' -s {}'.format(rfs.storage_cluster.file_server.type),
        t=' -t {}'.format(
            ','.join(rfs.storage_cluster.file_server.mount_options)
            if util.is_not_empty(rfs.storage_cluster.file_server.mount_options)
            else ''))
    if verbose:
        logger.debug('bootstrap command: {}'.format(cmd))
    logger.debug('creating virtual machine extension: {}'.format(vm_ext_name))
    return compute_client.virtual_machine_extensions.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        vm_name=vm_name,
        vm_extension_name=vm_ext_name,
        extension_parameters=compute_client.virtual_machine_extensions.models.
        VirtualMachineExtension(
            location=rfs.storage_cluster.location,
            publisher='Microsoft.Azure.Extensions',
            virtual_machine_extension_type='CustomScript',
            type_handler_version='2.0',
            auto_upgrade_minor_version=True,
            settings={
                'fileUris': blob_urls,
            },
            protected_settings={
                'commandToExecute': cmd,
                'storageAccountName': storage.get_storageaccount(),
                'storageAccountKey': storage.get_storageaccount_key(),
            },
        ),
    )


def _create_availability_set(compute_client, rfs):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.RemoteFsSettings) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Create an availability set
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param settings.RemoteFsSettings rfs: remote filesystem settings
    :rtype: msrestazure.azure_operation.AzureOperationPoller or None
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    if rfs.storage_cluster.vm_count <= 1:
        logger.warning('insufficient vm_count for availability set')
        return None
    as_name = settings.generate_availability_set_name(rfs.storage_cluster)
    # check and fail if as exists
    try:
        compute_client.availability_sets.get(
            resource_group_name=rfs.storage_cluster.resource_group,
            availability_set_name=as_name,
        )
        raise RuntimeError('availability set {} exists'.format(as_name))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    logger.debug('creating availability set: {}'.format(as_name))
    return compute_client.availability_sets.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        availability_set_name=as_name,
        # user maximums ud, fd from settings due to region variability
        parameters=compute_client.virtual_machines.models.AvailabilitySet(
            location=rfs.storage_cluster.location,
            platform_update_domain_count=20,
            platform_fault_domain_count=rfs.storage_cluster.fault_domains,
            sku=compute_client.virtual_machines.models.Sku(
                name='Aligned',
            ),
        )
    )


def create_storage_cluster(
        resource_client, compute_client, network_client, blob_client, config,
        sc_id, bootstrap_file, remotefs_files):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService, dict, str, str,
    #        List[tuple]) -> None
    """Create a storage cluster
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str sc_id: storage cluster id
    :param str bootstrap_file: customscript bootstrap file
    :param list remotefs_files: remotefs shell scripts
    :param dict config: configuration dict
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    # check if cluster already exists
    logger.debug('checking if storage cluster {} exists'.format(sc_id))
    # construct disk map
    disk_map = {}
    try:
        disk_names = list_disks(compute_client, config, restrict_scope=True)
        for disk_id, sat in disk_names:
            disk_map[disk_id.split('/')[-1]] = (disk_id, sat)
        del disk_names
    except msrestazure.azure_exceptions.CloudError as e:
        logger.error(
            'could not enumerate required disks for storage cluster {}'.format(
                sc_id))
        raise
    # check vms
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
            )
            raise RuntimeError(
                'Existing virtual machine {} found, cannot add this '
                'storage cluster'.format(vm.id))
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                pass
            else:
                raise
        # check if all referenced managed disks exist and premium sku
        # is specified if premium disk
        for disk in rfs.storage_cluster.vm_disk_map[i].disk_array:
            if disk not in disk_map:
                raise RuntimeError(
                    ('Referenced managed disk {} unavailable in set {} for '
                     'vm offset {}').format(disk, disk_map, i))
            if (disk_map[disk][1] ==
                    compute_client.disks.models.
                    StorageAccountTypes.premium_lrs and
                    not settings.is_premium_storage_vm_size(
                        rfs.storage_cluster.vm_size)):
                raise RuntimeError(
                    ('Premium storage requires premium storage capable '
                     'vm_size instead of {}'.format(
                         rfs.storage_cluster.vm_size)))
    # confirm before proceeding
    if not util.confirm_action(
            config, 'create storage cluster {}'.format(sc_id)):
        return
    # create resource group if it doesn't exist
    resource.create_resource_group(
        resource_client, rfs.storage_cluster.resource_group,
        rfs.storage_cluster.location)
    # create storage container
    storage.create_storage_containers_nonbatch(
        blob_client, None, None, 'remotefs')
    # upload scripts to blob storage for customscript vm extension
    blob_urls = storage.upload_for_nonbatch(
        blob_client, remotefs_files, 'remotefs')
    # async operation dictionary
    async_ops = {}
    # create nsg
    async_ops['nsg'] = resource.AsyncOperation(functools.partial(
        resource.create_network_security_group, network_client,
        rfs.storage_cluster))
    # create static private ip block
    if rfs.storage_cluster.file_server.type == 'nfs':
        private_ips = None
        logger.debug('using dynamic private ip address allocation')
    else:
        # follow Azure numbering scheme: start offset at 4
        private_ips = [
            x for x in util.ip_from_address_prefix(
                rfs.storage_cluster.virtual_network.subnet_address_prefix,
                start_offset=4,
                max=rfs.storage_cluster.vm_count)
        ]
        logger.debug('static private ip addresses to assign: {}'.format(
            private_ips))
    # create virtual network and subnet if specified
    vnet, subnet = resource.create_virtual_network_and_subnet(
        resource_client, network_client,
        rfs.storage_cluster.virtual_network.resource_group,
        rfs.storage_cluster.location,
        rfs.storage_cluster.virtual_network)
    # create public ips
    pips = None
    if rfs.storage_cluster.public_ip.enabled:
        async_ops['pips'] = {}
        for i in range(rfs.storage_cluster.vm_count):
            async_ops['pips'][i] = resource.AsyncOperation(functools.partial(
                resource.create_public_ip, network_client,
                rfs.storage_cluster, i))
        logger.debug('waiting for public ips to provision')
        pips = {}
        for offset in async_ops['pips']:
            pip = async_ops['pips'][offset].result()
            logger.info(
                ('public ip: {} [provisioning_state={} ip_address={} '
                 'public_ip_allocation={}]').format(
                     pip.id, pip.provisioning_state,
                     pip.ip_address, pip.public_ip_allocation_method))
            pips[offset] = pip
    else:
        logger.info('public ip is disabled for storage cluster: {}'.format(
            sc_id))
    # get nsg
    logger.debug('waiting for network security group to provision')
    nsg = async_ops['nsg'].result()
    # create nics
    async_ops['nics'] = {}
    for i in range(rfs.storage_cluster.vm_count):
        async_ops['nics'][i] = resource.AsyncOperation(functools.partial(
            resource.create_network_interface, network_client,
            rfs.storage_cluster, subnet, nsg, private_ips, pips, i))
    # create availability set if vm_count > 1, this call is not async
    availset = _create_availability_set(compute_client, rfs)
    # wait for nics to be created
    logger.debug('waiting for network interfaces to provision')
    nics = {}
    for offset in async_ops['nics']:
        nic = async_ops['nics'][offset].result()
        logger.info(
            ('network interface: {} [provisioning_state={} private_ip={} '
             'private_ip_allocation_method={} network_security_group={} '
             'accelerated_networking={}]').format(
                 nic.id, nic.provisioning_state,
                 nic.ip_configurations[0].private_ip_address,
                 nic.ip_configurations[0].private_ip_allocation_method,
                 nsg.name if nsg is not None else None,
                 nic.enable_accelerated_networking))
        nics[offset] = nic
    # read or generate ssh keys
    if util.is_not_empty(rfs.storage_cluster.ssh.ssh_public_key_data):
        key_data = rfs.storage_cluster.ssh.ssh_public_key_data
    else:
        # create universal ssh key for all vms if not specified
        ssh_pub_key = rfs.storage_cluster.ssh.ssh_public_key
        if ssh_pub_key is None:
            _, ssh_pub_key = crypto.generate_ssh_keypair(
                rfs.storage_cluster.ssh.generated_file_export_path,
                crypto.get_remotefs_ssh_key_prefix())
        # read public key data
        with ssh_pub_key.open('rb') as fd:
            key_data = fd.read().decode('utf8')
    ssh_pub_key = compute_client.virtual_machines.models.SshPublicKey(
        path='/home/{}/.ssh/authorized_keys'.format(
            rfs.storage_cluster.ssh.username),
        key_data=key_data,
    )
    # create vms
    async_ops['vms'] = {}
    for i in range(rfs.storage_cluster.vm_count):
        async_ops['vms'][i] = resource.AsyncOperation(functools.partial(
            resource.create_virtual_machine, compute_client,
            rfs.storage_cluster, availset, nics, disk_map, ssh_pub_key, i))
    # wait for vms to be created
    logger.info(
        'waiting for {} virtual machines to provision'.format(
            len(async_ops['vms'])))
    vms = {}
    for offset in async_ops['vms']:
        vms[offset] = async_ops['vms'][offset].result()
    logger.debug('{} virtual machines created'.format(len(vms)))
    # wait for all vms to be created before installing extensions to prevent
    # variability in wait times and timeouts during customscript
    async_ops['vmext'] = {}
    for i in range(rfs.storage_cluster.vm_count):
        # install vm extension
        async_ops['vmext'][i] = resource.AsyncOperation(
            functools.partial(
                _create_virtual_machine_extension, compute_client, rfs,
                bootstrap_file, blob_urls, vms[i].name, disk_map,
                private_ips, i, settings.verbose(config)),
            max_retries=0,
        )
    logger.debug('waiting for virtual machine extensions to provision')
    for offset in async_ops['vmext']:
        # get ip info for vm
        if util.is_none_or_empty(pips):
            ipinfo = 'private_ip_address={}'.format(
                nics[offset].ip_configurations[0].private_ip_address)
        else:
            # refresh public ip for vm
            pip = network_client.public_ip_addresses.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                public_ip_address_name=pips[offset].name,
            )
            ipinfo = 'fqdn={} public_ip_address={}'.format(
                pip.dns_settings.fqdn, pip.ip_address)
        # get vm extension result
        vm_ext = async_ops['vmext'][offset].result()
        vm = vms[offset]
        logger.info(
            ('virtual machine: {} [provisioning_state={}/{} '
             'vm_size={} {}]').format(
                vm.id, vm.provisioning_state, vm_ext.provisioning_state,
                vm.hardware_profile.vm_size, ipinfo))


def resize_storage_cluster(
        compute_client, network_client, blob_client, config, sc_id,
        bootstrap_file, addbrick_file, remotefs_files):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, str, str,
    #        list) -> bool
    """Resize a storage cluster (increase size only for now)
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param str bootstrap_file: bootstrap file
    :param str addbrick_file: glusterfs addbrick file
    :param list remotefs_files: remotefs files to upload
    :rtype: bool
    :return: if cluster was resized
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    # if storage cluster is not glusterfs, exit
    if rfs.storage_cluster.file_server.type != 'glusterfs':
        raise ValueError(
            'Resize is only supported on glusterfs storage clusters')
    # only allow certain types of resizes to proceed
    # for now disallow resize on all stripe volumes, can be relaxed in
    # the future
    voltype = settings.get_file_server_glusterfs_volume_type(
        rfs.storage_cluster).lower()
    if 'stripe' in voltype:
        raise RuntimeError('Cannot resize glusterfs striped volumes')
    # construct disk map
    disk_map = {}
    disk_names = list_disks(compute_client, config, restrict_scope=True)
    for disk_id, sat in disk_names:
        disk_map[disk_id.split('/')[-1]] = (disk_id, sat)
    del disk_names
    # get existing vms
    new_vms = []
    pe_vms = {}
    all_pe_disks = set()
    vnet_name = None
    subnet_name = None
    nsg_name = None
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
            )
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                new_vms.append(i)
                continue
            else:
                raise
        entry = {
            'vm': vm,
            'disks': set(),
        }
        for dd in vm.storage_profile.data_disks:
            entry['disks'].add(dd.name)
            all_pe_disks.add(dd.name.lower())
        # get vnet, subnet, nsg names
        if vnet_name is None or subnet_name is None or nsg_name is None:
            _, _, subnet_name, vnet_name, nsg_name = \
                resource.get_resource_names_from_virtual_machine(
                    compute_client, network_client, rfs.storage_cluster, vm)
        # add vm to map
        pe_vms[i] = entry
    # check early return conditions
    if len(new_vms) == 0:
        logger.warning(
            'no new virtual machines to add in storage cluster {}'.format(
                sc_id))
        return False
    # ensure that new disks to add are not already attached and
    # are provisioned
    for i in new_vms:
        for disk in rfs.storage_cluster.vm_disk_map[i].disk_array:
            if disk.lower() in all_pe_disks:
                raise RuntimeError(
                    'Disk {} for new VM {} is already attached'.format(
                        disk, i))
            # check disks for new vms are provisioned
            if disk not in disk_map:
                raise RuntimeError(
                    ('Disk {} for new VM {} is not provisioned in '
                     'resource group {}').format(
                         disk, i, rfs.storage_cluster.resource_group))
    logger.warning(
        ('**WARNING** cluster resize is an experimental feature and may lead '
         'to data loss, unavailability or an unrecoverable state for '
         'the storage cluster {}.'.format(sc_id)))
    # confirm before proceeding
    if not util.confirm_action(
            config, 'resize storage cluster {}'.format(sc_id)):
        return False
    # re-create storage container in case it got deleted
    storage.create_storage_containers_nonbatch(
        blob_client, None, None, 'remotefs')
    # upload scripts to blob storage for customscript vm extension
    blob_urls = storage.upload_for_nonbatch(
        blob_client, remotefs_files, 'remotefs')
    # create static private ip block, start offset at 4
    private_ips = [
        x for x in util.ip_from_address_prefix(
            rfs.storage_cluster.virtual_network.subnet_address_prefix,
            start_offset=4,
            max=rfs.storage_cluster.vm_count)
    ]
    logger.debug('static private ip block: {}'.format(private_ips))
    async_ops = {}
    # create public ips
    if rfs.storage_cluster.public_ip.enabled:
        async_ops['pips'] = {}
        for i in new_vms:
            async_ops['pips'][i] = resource.AsyncOperation(functools.partial(
                resource.create_public_ip, network_client,
                rfs.storage_cluster, i))
    else:
        logger.info('public ip is disabled for storage cluster: {}'.format(
            sc_id))
    # get subnet and nsg objects
    subnet = network_client.subnets.get(
        resource_group_name=rfs.storage_cluster.resource_group,
        virtual_network_name=vnet_name,
        subnet_name=subnet_name,
    )
    nsg = network_client.network_security_groups.get(
        resource_group_name=rfs.storage_cluster.resource_group,
        network_security_group_name=nsg_name,
    )
    # get ssh login info of prober vm
    ssh_info = None
    for i in pe_vms:
        vm = pe_vms[i]['vm']
        ssh_info = _get_ssh_info(
            compute_client, network_client, config, sc_id, None, vm.name)
        break
    if settings.verbose(config):
        logger.debug('prober vm: {}'.format(ssh_info))
    # wait for public ips
    pips = None
    if 'pips' in async_ops:
        logger.debug('waiting for public ips to provision')
        pips = {}
        for offset in async_ops['pips']:
            pip = async_ops['pips'][offset].result()
            logger.info(
                ('public ip: {} [provisioning_state={} ip_address={} '
                 'public_ip_allocation={}]').format(
                     pip.id, pip.provisioning_state,
                     pip.ip_address, pip.public_ip_allocation_method))
            pips[offset] = pip
    # create nics
    nics = {}
    async_ops['nics'] = {}
    for i in new_vms:
        async_ops['nics'][i] = resource.AsyncOperation(functools.partial(
            resource.create_network_interface, network_client,
            rfs.storage_cluster, subnet, nsg, private_ips, pips, i))
    # get availability set
    availset = compute_client.availability_sets.get(
        resource_group_name=rfs.storage_cluster.resource_group,
        availability_set_name=settings.generate_availability_set_name(
            rfs.storage_cluster),
    )
    # wait for nics to be created
    logger.debug('waiting for network interfaces to provision')
    for offset in async_ops['nics']:
        nic = async_ops['nics'][offset].result()
        logger.info(
            ('network interface: {} [provisioning_state={} private_ip={} '
             'private_ip_allocation_method={} network_security_group={} '
             'accelerated={}]').format(
                 nic.id, nic.provisioning_state,
                 nic.ip_configurations[0].private_ip_address,
                 nic.ip_configurations[0].private_ip_allocation_method,
                 nsg.name if nsg is not None else None,
                 nic.enable_accelerated_networking))
        nics[offset] = nic
    # read or generate ssh keys
    if util.is_not_empty(rfs.storage_cluster.ssh.ssh_public_key_data):
        key_data = rfs.storage_cluster.ssh.ssh_public_key_data
    else:
        # create universal ssh key for all vms if not specified
        ssh_pub_key = rfs.storage_cluster.ssh.ssh_public_key
        if ssh_pub_key is None:
            # check if ssh key exists first in default location
            ssh_pub_key = pathlib.Path(
                rfs.storage_cluster.ssh.generated_file_export_path,
                crypto.get_remotefs_ssh_key_prefix() + '.pub')
            if not ssh_pub_key.exists():
                _, ssh_pub_key = crypto.generate_ssh_keypair(
                    rfs.storage_cluster.ssh.generated_file_export_path,
                    crypto.get_remotefs_ssh_key_prefix())
        # read public key data
        with ssh_pub_key.open('rb') as fd:
            key_data = fd.read().decode('utf8')
    ssh_pub_key = compute_client.virtual_machines.models.SshPublicKey(
        path='/home/{}/.ssh/authorized_keys'.format(
            rfs.storage_cluster.ssh.username),
        key_data=key_data,
    )
    # create vms
    async_ops['vms'] = {}
    for i in new_vms:
        async_ops['vms'][i] = resource.AsyncOperation(functools.partial(
            resource.create_virtual_machine, compute_client,
            rfs.storage_cluster, availset, nics, disk_map, ssh_pub_key, i))
    # gather all new private ips
    new_private_ips = {}
    for offset in nics:
        new_private_ips[offset] = nics[
            offset].ip_configurations[0].private_ip_address
    if settings.verbose(config):
        logger.debug('new private ips: {}'.format(new_private_ips))
    # wait for vms to be created
    logger.info(
        'waiting for {} virtual machines to provision'.format(
            len(async_ops['vms'])))
    vm_hostnames = []
    vms = {}
    for offset in async_ops['vms']:
        vms[offset] = async_ops['vms'][offset].result()
        # generate vm names in list
        vm_hostnames.append(settings.generate_virtual_machine_name(
            rfs.storage_cluster, offset))
    logger.debug('{} virtual machines created: {}'.format(
        len(vms), vm_hostnames))
    # wait for all vms to be created before installing extensions to prevent
    # variability in wait times and timeouts during customscript
    async_ops['vmext'] = {}
    for i in new_vms:
        # install vm extension
        async_ops['vmext'][i] = resource.AsyncOperation(
            functools.partial(
                _create_virtual_machine_extension, compute_client, rfs,
                bootstrap_file, blob_urls, vms[i].name, disk_map, private_ips,
                i, settings.verbose(config)),
            max_retries=0,
        )
    logger.debug(
        'adding {} bricks to gluster volume, this may take a while'.format(
            len(async_ops['vmext'])))
    # execute special add brick script
    script_cmd = '/opt/batch-shipyard/{asf} {c}{d}{i}{n}{v}'.format(
        asf=addbrick_file,
        c=' -c {}'.format(rfs.storage_cluster.vm_count),
        d=' -d {}'.format(','.join(vm_hostnames)),
        i=' -i {}'.format(','.join(list(new_private_ips.values()))),
        n=' -n {}'.format(
            settings.get_file_server_glusterfs_volume_name(
                rfs.storage_cluster)),
        v=' -v \'{}\''.format(voltype),
    )
    if settings.verbose(config):
        logger.debug('add brick command: {}'.format(script_cmd))
    ssh_priv_key, port, username, ip = ssh_info
    proc = crypto.connect_or_exec_ssh_command(
        ip, port, ssh_priv_key, username, sync=False,
        command=['sudo', script_cmd])
    stdout, stderr = proc.communicate()
    logline = 'add brick script completed with ec={}'.format(proc.returncode)
    if util.is_not_empty(stdout):
        if util.on_python2():
            stdout = stdout.decode('utf8')
        if util.on_windows():
            stdout = stdout.replace('\n', os.linesep)
    if util.is_not_empty(stderr):
        if util.on_python2():
            stderr = stderr.decode('utf8')
        if util.on_windows():
            stderr = stderr.replace('\n', os.linesep)
    if proc.returncode != 0:
        logger.error(logline)
        logger.error('add brick stdout:{}{}'.format(os.linesep, stdout))
        logger.error('add brick stderr:{}{}'.format(os.linesep, stderr))
    else:
        logger.info(logline)
        logger.debug('add brick stdout:{}{}'.format(os.linesep, stdout))
    del logline
    del stdout
    del stderr
    # wait for new vms to finish custom script extension processing
    logger.debug('waiting for virtual machine extensions to provision')
    for offset in async_ops['vmext']:
        # get ip info for vm
        if util.is_none_or_empty(pips):
            ipinfo = 'private_ip_address={}'.format(
                nics[offset].ip_configurations[0].private_ip_address)
        else:
            # refresh public ip for vm
            pip = network_client.public_ip_addresses.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                public_ip_address_name=pips[offset].name,
            )
            ipinfo = 'fqdn={} public_ip_address={}'.format(
                pip.dns_settings.fqdn, pip.ip_address)
        # get vm extension result
        vm_ext = async_ops['vmext'][offset].result()
        vm = vms[offset]
        logger.info(
            ('virtual machine: {} [provisioning_state={}/{} '
             'vm_size={} {}]').format(
                vm.id, vm.provisioning_state, vm_ext.provisioning_state,
                vm.hardware_profile.vm_size, ipinfo))
    if proc.returncode == 0:
        logger.info('storage cluster {} resized'.format(sc_id))
    else:
        logger.critical('failed to resize cluster {}'.format(sc_id))


def expand_storage_cluster(
        compute_client, network_client, config, sc_id, bootstrap_file,
        rebalance=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, str,
    #        bool) -> bool
    """Expand a storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param str bootstrap_file: bootstrap file
    :param bool rebalance: rebalance filesystem
    :rtype: bool
    :return: if cluster was expanded
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    # check if cluster exists
    logger.debug('checking if storage cluster {} exists'.format(sc_id))
    # construct disk map
    disk_map = {}
    disk_names = list_disks(compute_client, config, restrict_scope=True)
    for disk_id, sat in disk_names:
        disk_map[disk_id.split('/')[-1]] = (disk_id, sat)
    del disk_names
    # check vms
    vms = {}
    new_disk_count = 0
    mdadm_expand = False
    for i in range(rfs.storage_cluster.vm_count):
        # check if this vm filesystem supports expanding
        if (rfs.storage_cluster.vm_disk_map[i].filesystem != 'btrfs' and
                rfs.storage_cluster.vm_disk_map[i].raid_level == 0):
            mdadm_expand = True
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
            )
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                raise RuntimeError(
                    'Virtual machine {} not found, cannot expand this '
                    'storage cluster'.format(vm_name))
            else:
                raise
        # create entry
        entry = {
            'vm': vm,
            'pe_disks': {
                'names': set(),
                'luns': [],
            },
            'new_disks': [],
        }
        # get attached disks
        for dd in vm.storage_profile.data_disks:
            entry['pe_disks']['names'].add(dd.name)
            entry['pe_disks']['luns'].append(dd.lun)
        # check if all referenced managed disks exist
        for disk in rfs.storage_cluster.vm_disk_map[i].disk_array:
            if disk not in disk_map:
                raise RuntimeError(
                    ('Referenced managed disk {} unavailable in set {} for '
                     'vm offset {}. Ensure that this disk has been '
                     'provisioned first.').format(disk, disk_map, i))
            if disk not in entry['pe_disks']['names']:
                entry['new_disks'].append(disk)
                new_disk_count += 1
        # check for proper raid setting and number of disks
        pe_len = len(entry['pe_disks']['names'])
        if pe_len <= 1 or rfs.storage_cluster.vm_disk_map[i].raid_level != 0:
            raise RuntimeError(
                'Cannot expand array from {} disk(s) or RAID level {}'.format(
                    pe_len, rfs.storage_cluster.vm_disk_map[i].raid_level))
        # add vm to map
        vms[i] = entry
    # check early return conditions
    if len(vms) == 0:
        logger.warning(
            'no virtual machines to expand in storage cluster {}'.format(
                sc_id))
        return False
    if settings.verbose(config):
        logger.debug('expand settings:{}{}'.format(os.linesep, vms))
    if new_disk_count == 0:
        logger.error(
            'no new disks detected for storage cluster {}'.format(sc_id))
        return False
    if mdadm_expand:
        logger.warning(
            '**WARNING** cluster expansion is being performed on mdadm-based '
            'RAID arrays. This feature is experimental and can take an '
            'extremely long time. Any interruption or unrecoverable '
            'failure can result in data loss.')
    del mdadm_expand
    # confirm before proceeding
    if not util.confirm_action(
            config, 'expand storage cluster {}'.format(sc_id)):
        return False
    # attach new data disks to each vm
    async_ops = {}
    for key in vms:
        entry = vms[key]
        if len(entry['new_disks']) == 0:
            logger.debug('no new disks to attach to virtual machine {}'.format(
                vm.id))
            continue
        vm = entry['vm']
        premium = False
        # sort lun array and get last element
        lun = sorted(entry['pe_disks']['luns'])[-1] + 1
        for diskname in entry['new_disks']:
            if (disk_map[diskname][1] ==
                    compute_client.disks.models.
                    StorageAccountTypes.premium_lrs):
                premium = True
            vm.storage_profile.data_disks.append(
                compute_client.disks.models.DataDisk(
                    lun=lun,
                    name=diskname,
                    create_option=compute_client.disks.models.
                    DiskCreateOptionTypes.attach,
                    managed_disk=compute_client.disks.models.
                    ManagedDiskParameters(
                        id=disk_map[diskname][0],
                    ),
                )
            )
            lun += 1
        logger.info(
            ('attaching {} additional data disks {} to virtual '
             'machine {}').format(
                len(entry['new_disks']), entry['new_disks'], vm.name))
        # update vm
        async_ops[key] = (
            premium,
            resource.AsyncOperation(functools.partial(
                compute_client.virtual_machines.create_or_update,
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm.name, parameters=vm))
        )
    # wait for async ops to complete
    if len(async_ops) == 0:
        logger.error('no operations started for expansion')
        return False
    logger.debug(
        'waiting for disks to attach to virtual machines and expanding '
        'the volume; please be patient as this can take a very long time')
    for offset in async_ops:
        premium, op = async_ops[offset]
        vm = op.result()
        vms[offset]['vm'] = vm
        # execute bootstrap script via ssh
        script_cmd = \
            '/opt/batch-shipyard/{bsf} {a}{b}{d}{f}{m}{p}{r}{s}'.format(
                bsf=bootstrap_file,
                a=' -a',
                b=' -b' if rebalance else '',
                d=' -d {}'.format(rfs.storage_cluster.hostname_prefix),
                f=' -f {}'.format(
                    rfs.storage_cluster.vm_disk_map[offset].filesystem),
                m=' -m {}'.format(
                    rfs.storage_cluster.file_server.mountpoint),
                p=' -p' if premium else '',
                r=' -r {}'.format(
                    rfs.storage_cluster.vm_disk_map[offset].raid_level),
                s=' -s {}'.format(rfs.storage_cluster.file_server.type),
            )
        ssh_priv_key, port, username, ip = _get_ssh_info(
            compute_client, network_client, config, sc_id, None, vm.name)
        if settings.verbose(config):
            logger.debug('bootstrap command: {}'.format(script_cmd))
        proc = crypto.connect_or_exec_ssh_command(
            ip, port, ssh_priv_key, username, sync=False,
            command=['sudo', script_cmd])
        stdout, stderr = proc.communicate()
        if util.is_not_empty(stdout):
            if util.on_python2():
                stdout = stdout.decode('utf8')
            if util.on_windows():
                stdout = stdout.replace('\n', os.linesep)
        if util.is_not_empty(stderr):
            if util.on_python2():
                stderr = stderr.decode('utf8')
            if util.on_windows():
                stderr = stderr.replace('\n', os.linesep)
        vms[offset]['status'] = proc.returncode
        vms[offset]['stdout'] = '>>stdout>> {}:{}{}'.format(
            vm.name, os.linesep, stdout)
        vms[offset]['stderr'] = '>>stderr>> {}:{}{}'.format(
            vm.name, os.linesep, stderr)
    logger.info('disk attach operations completed')
    succeeded = True
    for key in vms:
        entry = vms[key]
        vm = entry['vm']
        log = 'bootstrap exit code for virtual machine {}: {}'.format(
            vm.name, entry['status'])
        if entry['status'] == 0:
            logger.info(log)
            logger.debug(entry['stdout'])
        else:
            logger.error(log)
            logger.error(entry['stdout'])
            logger.error(entry['stderr'])
            succeeded = False
    if succeeded:
        logger.info('storage cluster {} expanded'.format(sc_id))
    else:
        logger.critical('failed to expand cluster {}'.format(sc_id))
    return succeeded


def _delete_availability_set(compute_client, rg_name, as_name):
    # type: (azure.mgmt.compute.ComputeManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete an availability set
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param str rg_name: resource group name
    :param str as_name: availability set name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deleting availability set {}'.format(as_name))
    return compute_client.availability_sets.delete(
        resource_group_name=rg_name,
        availability_set_name=as_name,
    )


def delete_storage_cluster(
        resource_client, compute_client, network_client, blob_client, config,
        sc_id, delete_data_disks=False, delete_virtual_network=False,
        delete_resource_group=False, generate_from_prefix=False, wait=False):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService, dict, str, bool,
    #        bool, bool, bool, bool) -> None
    """Delete a storage cluster
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param bool delete_data_disks: delete managed data disks
    :param bool delete_virtual_network: delete vnet
    :param bool delete_resource_group: delete resource group
    :param bool generate_from_prefix: generate resources from hostname prefix
    :param bool wait: wait for completion
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    # delete rg if specified
    if delete_resource_group:
        if util.confirm_action(
                config, 'delete resource group {}'.format(
                    rfs.storage_cluster.resource_group)):
            logger.info('deleting resource group {}'.format(
                rfs.storage_cluster.resource_group))
            async_delete = resource_client.resource_groups.delete(
                resource_group_name=rfs.storage_cluster.resource_group)
            if wait:
                logger.debug('waiting for resource group {} to delete'.format(
                    rfs.storage_cluster.resource_group))
                async_delete.result()
                logger.info('resource group {} deleted'.format(
                    rfs.storage_cluster.resource_group))
        return
    if not util.confirm_action(
            config, 'delete storage cluster {}'.format(sc_id)):
        return
    # get vms and cache for concurent async ops
    resources = {}
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
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
                            rfs.storage_cluster, i),
                        'as': None,
                        'nic': settings.generate_network_interface_name(
                            rfs.storage_cluster, i),
                        'pip': settings.generate_public_ip_name(
                            rfs.storage_cluster, i),
                        'subnet': None,
                        'nsg': settings.generate_network_security_group_name(
                            rfs.storage_cluster),
                        'vnet': None,
                        'os_disk': None,
                        'data_disks': [],
                    }
                    if rfs.storage_cluster.vm_count > 1:
                        resources[i]['as'] = \
                            settings.generate_availability_set_name(
                                rfs.storage_cluster)
                continue
            else:
                raise
        else:
            # get resources connected to vm
            nic, pip, subnet, vnet, nsg = \
                resource.get_resource_names_from_virtual_machine(
                    compute_client, network_client, rfs.storage_cluster, vm)
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
                'data_disks': [],
            }
            # populate availability set
            if vm.availability_set is not None:
                resources[i]['as'] = vm.availability_set.id.split('/')[-1]
            # populate data disks
            if delete_data_disks:
                for disk in vm.storage_profile.data_disks:
                    resources[i]['data_disks'].append(disk.name)
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
    # delete storage container
    storage.delete_storage_containers_nonbatch(
        blob_client, None, None, 'remotefs')
    # create async op holder
    async_ops = {}
    # delete vms
    async_ops['vms'] = {}
    for key in resources:
        vm_name = resources[key]['vm']
        async_ops['vms'][vm_name] = resource.AsyncOperation(functools.partial(
            resource.delete_virtual_machine, compute_client,
            rfs.storage_cluster.resource_group, vm_name), retry_conflict=True)
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
                rfs.storage_cluster.resource_group, nic_name),
            retry_conflict=True
        )
    # wait for nics to delete
    logger.debug('waiting for {} network interfaces to delete'.format(
        len(async_ops['nics'])))
    for nic_name in async_ops['nics']:
        async_ops['nics'][nic_name].result()
    logger.info('{} network interfaces deleted'.format(len(async_ops['nics'])))
    # delete data disks if specified
    async_ops['data_disks'] = []
    for key in resources:
        data_disks = resources[key]['data_disks']
        if util.is_none_or_empty(data_disks):
            continue
        if len(data_disks) > 0:
            async_ops['data_disks'].append(delete_managed_disks(
                resource_client, compute_client, config, data_disks,
                resource_group=rfs.managed_disks.resource_group, wait=False))
    # delete os disks
    async_ops['os_disk'] = []
    for key in resources:
        os_disk = resources[key]['os_disk']
        if util.is_none_or_empty(os_disk):
            continue
        async_ops['os_disk'].append(delete_managed_disks(
            resource_client, compute_client, config, os_disk,
            resource_group=rfs.storage_cluster.resource_group, wait=False,
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
            rfs.storage_cluster.resource_group, nsg_name), retry_conflict=True)
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
                rfs.storage_cluster.resource_group, pip_name),
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
                rfs.storage_cluster.virtual_network.resource_group,
                vnet_name, subnet_name),
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
                rfs.storage_cluster.virtual_network.resource_group, vnet_name),
            retry_conflict=True
        )
    deleted.clear()
    # delete availability set, this is synchronous
    for key in resources:
        as_name = resources[key]['as']
        if util.is_none_or_empty(as_name) or as_name in deleted:
            continue
        deleted.add(as_name)
        _delete_availability_set(
            compute_client, rfs.storage_cluster.resource_group, as_name)
        logger.info('availability set {} deleted'.format(as_name))
    deleted.clear()
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
        if len(async_ops['data_disks']) > 0:
            logger.debug('waiting for managed data disks to delete')
            count = 0
            for data_disk_set in async_ops['data_disks']:
                for data_disk in data_disk_set:
                    data_disk_set[data_disk].result()
                    count += 1
            logger.info('{} managed data disks deleted'.format(count))


def suspend_storage_cluster(compute_client, config, sc_id, wait=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, str,
    #        bool) -> None
    """Suspend a storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param bool wait: wait for suspension to complete
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    vms = []
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
            )
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                logger.error('virtual machine {} not found'.format(vm_name))
                continue
            else:
                raise
        else:
            vms.append(vm)
    if len(vms) == 0:
        logger.warning('no virtual machines to suspend')
        return
    # check if glusterfs and warn
    if rfs.storage_cluster.file_server.type == 'glusterfs':
        logger.warning(
            '**WARNING** Suspending a glusterfs cluster is risky. Depending '
            'upon the volume type and state of the bricks at the time of '
            'suspension, a variety of issues can occur such as: unsuccessful '
            'restart of the cluster, split-brain states, or even data loss.')
    if not util.confirm_action(
            config, 'suspend storage cluster {}'.format(sc_id)):
        return
    # deallocate each vm
    async_ops = {}
    for vm in vms:
        async_ops[vm.name] = resource.AsyncOperation(functools.partial(
            resource.deallocate_virtual_machine, compute_client,
            rfs.storage_cluster.resource_group, vm.name), retry_conflict=True)
    if wait:
        logger.info(
            'waiting for {} virtual machines to deallocate'.format(
                len(async_ops)))
        for vm_name in async_ops:
            async_ops[vm_name].result()
        logger.info('{} virtual machines deallocated'.format(len(async_ops)))


def start_storage_cluster(compute_client, config, sc_id, wait=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, str,
    #        bool) -> None
    """Starts a suspended storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param bool wait: wait for restart to complete
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    vms = []
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
            )
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                raise RuntimeError(
                    'virtual machine {} not found'.format(vm_name))
            else:
                raise
        else:
            vms.append(vm)
    if len(vms) == 0:
        logger.error('no virtual machines to restart')
        return
    if not util.confirm_action(
            config, 'start suspended storage cluster {}'.format(sc_id)):
        return
    # start each vm
    async_ops = {}
    for vm in vms:
        async_ops[vm.name] = resource.AsyncOperation(functools.partial(
            resource.start_virtual_machine, compute_client,
            rfs.storage_cluster.resource_group, vm.name))
    if wait:
        logger.info(
            'waiting for {} virtual machines to start'.format(len(async_ops)))
        for vm_name in async_ops:
            async_ops[vm_name].result()
        logger.info('{} virtual machines started'.format(len(async_ops)))


def stat_storage_cluster(
        compute_client, network_client, config, sc_id, status_script,
        detail=False, hosts=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, str,
    #        bool, bool) -> None
    """Retrieve status of a storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param str status_script: status script
    :param bool detail: detailed status
    :param bool hosts: dump info for /etc/hosts
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    # retrieve all vms
    vms = []
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
                expand=compute_client.virtual_machines.models.
                InstanceViewTypes.instance_view,
            )
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                logger.error('virtual machine {} not found'.format(vm_name))
            else:
                raise
        else:
            vms.append((vm, i))
    if len(vms) == 0:
        logger.error(
            'no virtual machines to query for storage cluster {}'.format(
                sc_id))
        return
    # fetch vm status
    fsstatus = []
    vmstatus = {}
    for vm, offset in vms:
        powerstate = None
        for status in vm.instance_view.statuses:
            if status.code.startswith('PowerState'):
                powerstate = status.code
        diskstates = []
        if util.is_not_empty(vm.instance_view.disks):
            for disk in vm.instance_view.disks:
                for status in disk.statuses:
                    diskstates.append(status.code)
        # get nic/pip connected to vm
        nic, pip = resource.get_nic_and_pip_from_virtual_machine(
            network_client, rfs.storage_cluster.resource_group, vm)
        # get resource names (pass cached data to prevent another lookup)
        _, _, subnet, vnet, nsg = \
            resource.get_resource_names_from_virtual_machine(
                compute_client, network_client, rfs.storage_cluster, vm,
                nic=nic, pip=pip)
        # stat data disks
        disks = {}
        total_size_gb = 0
        for dd in vm.storage_profile.data_disks:
            total_size_gb += dd.disk_size_gb
            disks[dd.name] = {
                'lun': dd.lun,
                'caching': str(dd.caching),
                'disk_size_gb': dd.disk_size_gb,
                'type': str(dd.managed_disk.storage_account_type),
            }
        disks['disk_array_size_gb'] = total_size_gb
        # detailed settings: run stat script via ssh
        if detail:
            ssh_priv_key, port, username, ip = _get_ssh_info(
                compute_client, network_client, config, sc_id, None, vm.name,
                nic=nic, pip=pip)
            offset = settings.get_offset_from_virtual_machine_name(vm.name)
            script_cmd = '/opt/batch-shipyard/{sf} {c}{f}{m}{n}{r}{s}'.format(
                sf=status_script,
                c=' -c' if util.is_not_empty(
                    rfs.storage_cluster.file_server.samba.share_name) else '',
                f=' -f {}'.format(
                    rfs.storage_cluster.vm_disk_map[offset].filesystem),
                m=' -m {}'.format(
                    rfs.storage_cluster.file_server.mountpoint),
                n=' -n {}'.format(
                    settings.get_file_server_glusterfs_volume_name(
                        rfs.storage_cluster)),
                r=' -r {}'.format(
                    rfs.storage_cluster.vm_disk_map[offset].raid_level),
                s=' -s {}'.format(rfs.storage_cluster.file_server.type),
            )
            proc = crypto.connect_or_exec_ssh_command(
                ip, port, ssh_priv_key, username, sync=False,
                command=['sudo', script_cmd])
            stdout = proc.communicate()[0]
            if util.is_not_empty(stdout):
                if util.on_python2():
                    stdout = stdout.decode('utf8')
                if util.on_windows():
                    stdout = stdout.replace('\n', os.linesep)
            fsstatfmt = '>> File Server Status for {} ec={}:{}{}'
            if util.on_python2():
                fsstatfmt = unicode(fsstatfmt)  # noqa
            fsstatus.append(
                fsstatfmt.format(vm.name, proc.returncode, os.linesep, stdout))
        vmstatus[vm.name] = {
            'vm_size': vm.hardware_profile.vm_size,
            'powerstate': powerstate,
            'provisioning_state': vm.provisioning_state,
            'availability_set':
            vm.availability_set.id.split('/')[-1]
            if vm.availability_set is not None else None,
            'update_domain/fault_domain': '{}/{}'.format(
                vm.instance_view.platform_update_domain,
                vm.instance_view.platform_fault_domain),
            'fqdn': pip.dns_settings.fqdn if pip is not None else None,
            'public_ip_address': pip.ip_address if pip is not None else None,
            'public_ip_allocation':
            pip.public_ip_allocation_method if pip is not None else None,
            'private_ip_address': nic.ip_configurations[0].private_ip_address,
            'private_ip_allocation':
            nic.ip_configurations[0].private_ip_allocation_method,
            'admin_username': vm.os_profile.admin_username,
            'accelerated_networking': nic.enable_accelerated_networking,
            'virtual_network': vnet,
            'subnet': subnet,
            'network_security_group': nsg,
            'data_disks': disks,
        }
    if detail:
        log = '{}{}{}{}'.format(
            json.dumps(vmstatus, sort_keys=True, indent=4),
            os.linesep, os.linesep,
            '{}{}'.format(os.linesep, os.linesep).join(
                fsstatus) if detail else '')
    else:
        log = '{}'.format(json.dumps(vmstatus, sort_keys=True, indent=4))
    logger.info('storage cluster {} virtual machine status:{}{}'.format(
        sc_id, os.linesep, log))
    if hosts:
        if rfs.storage_cluster.file_server.type != 'glusterfs':
            raise ValueError('hosts option not compatible with glusterfs')
        print(('{}>> Ensure that you have enabled the "glusterfs" network '
               'security rule.{}>> Add the following entries to your '
               '/etc/hosts to mount the gluster volume.{}>> Mount the '
               'source as -t glusterfs from {}:/{}{}'.format(
                   os.linesep, os.linesep, os.linesep, next(iter(vmstatus)),
                   settings.get_file_server_glusterfs_volume_name(
                       rfs.storage_cluster), os.linesep)))
        for vmname in vmstatus:
            print('{} {}'.format(
                vmstatus[vmname]['public_ip_address'], vmname))


def _get_ssh_info(
        compute_client, network_client, config, sc_id, cardinal, hostname,
        nic=None, pip=None):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, int,
    #        str, networkmodes.NetworkInterface,
    #        networkmodels.PublicIPAddress) ->
    #        Tuple[pathlib.Path, int, str, str]
    """SSH to a node in storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param int cardinal: cardinal number
    :param str hostname: hostname
    :param networkmodels.NetworkInterface nic: network interface
    :param networkmodels.PublicIPAddress pip: public ip
    :rtype: tuple
    :return (ssh private key, port, username, ip)
    """
    # retrieve remotefs settings
    if util.is_none_or_empty(sc_id):
        raise ValueError('storage cluster id not specified')
    rfs = settings.remotefs_settings(config, sc_id)
    # retrieve specific vm
    if cardinal is not None:
        vm_name = settings.generate_virtual_machine_name(
            rfs.storage_cluster, cardinal)
    else:
        vm_name = hostname
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=rfs.storage_cluster.resource_group,
            vm_name=vm_name,
        )
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            raise RuntimeError('virtual machine {} not found'.format(vm_name))
        else:
            raise
    # get connection ip
    if rfs.storage_cluster.public_ip.enabled:
        # get pip connected to vm
        if pip is None:
            _, pip = resource.get_nic_and_pip_from_virtual_machine(
                network_client, rfs.storage_cluster.resource_group, vm)
        ip_address = pip.ip_address
    else:
        if nic is None:
            nic, _ = resource.get_nic_and_pip_from_virtual_machine(
                network_client, rfs.storage_cluster.resource_group, vm)
        ip_address = nic.ip_configurations[0].private_ip_address
    # return connection info for vm
    if rfs.storage_cluster.ssh.ssh_private_key is not None:
        ssh_priv_key = rfs.storage_cluster.ssh.ssh_private_key
    else:
        ssh_priv_key = pathlib.Path(
            rfs.storage_cluster.ssh.generated_file_export_path,
            crypto.get_remotefs_ssh_key_prefix())
    if not ssh_priv_key.exists():
        raise RuntimeError('SSH private key file not found at: {}'.format(
            ssh_priv_key))
    return ssh_priv_key, 22, vm.os_profile.admin_username, ip_address


def ssh_storage_cluster(
        compute_client, network_client, config, sc_id, cardinal, hostname,
        tty, command):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, int,
    #        str, bool, tuple) -> None
    """SSH to a node in storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str sc_id: storage cluster id
    :param int cardinal: cardinal number
    :param str hostname: hostname
    :param bool tty: allocate pseudo-tty
    :param tuple command: command to execute
    """
    ssh_priv_key, port, username, ip = _get_ssh_info(
        compute_client, network_client, config, sc_id, cardinal, hostname)
    crypto.connect_or_exec_ssh_command(
        ip, port, ssh_priv_key, username, tty=tty, command=command)
