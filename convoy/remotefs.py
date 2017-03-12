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
import json
import logging
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import socket
import struct
# non-stdlib imports
import azure.mgmt.compute.models as computemodels
import azure.mgmt.network.models as networkmodels
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
    if rfs.managed_disks.premium:
        account_type = computemodels.StorageAccountTypes.premium_lrs
    else:
        account_type = computemodels.StorageAccountTypes.standard_lrs
    logger.info('creating managed disk: {}'.format(disk_name))
    return compute_client.disks.create_or_update(
        resource_group_name=rfs.managed_disks.resource_group,
        disk_name=disk_name,
        disk=computemodels.Disk(
            location=rfs.location,
            account_type=account_type,
            disk_size_gb=rfs.managed_disks.disk_size_gb,
            creation_data=computemodels.CreationData(
                create_option=computemodels.DiskCreateOption.empty
            ),
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
        resource_client, rfs.managed_disks.resource_group, rfs.location)
    # iterate disks and create disks if they don't exist
    existing_disk_sizes = set()
    async_ops = []
    for disk_name in rfs.managed_disks.disk_ids:
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
                async_ops.append(
                    _create_managed_disk(compute_client, rfs, disk_name)
                )
            else:
                raise
    # block for all ops to complete if specified
    # note that if wait is not specified and there is no delay, the request
    # may not get acknowledged...
    if wait:
        if len(async_ops) > 0:
            logger.debug('waiting for all {} disks to be created'.format(
                len(async_ops)))
        for op in async_ops:
            disk = op.result()
            logger.info('{} created with size of {} GB'.format(
                disk.id, disk.disk_size_gb))


def delete_managed_disks(
        compute_client, config, name, resource_group=None, all=False,
        wait=False, confirm_override=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, str or list,
    #        bool, bool, bool) -> None
    """Delete managed disks
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param str or list name: specific disk name or list of names
    :param str resource_group: resource group of the disks
    :param bool all: delete all disks in resource group
    :param bool wait: wait for operation to complete
    :param bool confirm_override: override confirmation of delete
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    resource_group = resource_group or rfs.managed_disks.resource_group
    # set disks to delete
    if all:
        disks = [
            x[0].split('/')[-1] for x in list_disks(
                compute_client, config, resource_group=resource_group,
                restrict_scope=False)
        ]
    else:
        if util.is_none_or_empty(name):
            disks = rfs.managed_disks.disk_ids
        else:
            if isinstance(name, list):
                disks = name
            else:
                disks = [name]
    # iterate disks and delete them
    async_ops = []
    for disk_name in disks:
        if (not confirm_override and not util.confirm_action(
                config,
                'delete managed disk {} from resource group {}'.format(
                    disk_name, resource_group))):
            continue
        logger.info('deleting managed disk {} in resource group {}'.format(
            disk_name, resource_group))
        async_ops.append(
            compute_client.disks.delete(
                resource_group_name=resource_group, disk_name=disk_name)
        )
    # block for all ops to complete if specified
    if wait:
        if len(async_ops) > 0:
            logger.debug('waiting for all {} disks to be deleted'.format(
                len(async_ops)))
        for op in async_ops:
            op.result()
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
    confdisks = frozenset(rfs.managed_disks.disk_ids)
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
                disk.disk_size_gb, disk.account_type))
        ret.append((disk.id, disk.account_type))
        i += 1
    if i == 0:
        logger.error(
            ('no managed disks found in resource group {} '
             '[restrict_scope={}]').format(resource_group, restrict_scope))
    return ret


def ip_from_address_prefix(cidr, start_offset=None, max=None):
    # type: (str) -> str
    """Generator for ip addresses from CIDR notation
    :param str cidr: CIDR
    :param int start_offset: starting offset
    :param int max: max number of addresses to generate
    :rtype: str
    :return: next IP address
    """
    tmp = cidr.split('/')
    if len(tmp) != 2:
        raise ValueError('CIDR notation {} is invalid'.format(cidr))
    addr = struct.unpack('>L', socket.inet_aton(tmp[0]))[0]
    mask = int(tmp[1])
    if start_offset is None:
        start_offset = 0
    first = (addr & (~0 << (32 - mask))) + start_offset
    last = addr | ((1 << (32 - mask)) - 1)
    if max is not None:
        diff = last - first
        if diff > max:
            last = first + max - 1
    for i in range(first, last + 1):
        yield socket.inet_ntoa(struct.pack('>L', i))


def _create_network_security_group(network_client, rfs):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.RemoteFsSettings) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Create a network security group
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.RemoteFsSettings rfs: remote filesystem settings
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    nsg_name = '{}-nsg'.format(rfs.storage_cluster.hostname_prefix)
    # TODO check and fail if nsg exists
    # create security rules as found in settings
    priority = 100
    security_rules = []
    for nsi in rfs.storage_cluster.network_security.inbound:
        i = 0
        ir = rfs.storage_cluster.network_security.inbound[nsi]
        for sap in ir.source_address_prefix:
            proto = ir.protocol.lower()
            if proto == 'tcp':
                proto = networkmodels.SecurityRuleProtocol.tcp
            elif proto == 'udp':
                proto = networkmodels.SecurityRuleProtocol.udp
            elif proto == '*':
                proto = networkmodels.SecurityRuleProtocol.asterisk
            else:
                raise ValueError('Unknown protocol {} for rule {}'.format(
                    proto, nsi))
            security_rules.append(networkmodels.SecurityRule(
                name='{}_in-{}'.format(nsi, i),
                description='{} inbound ({})'.format(nsi, i),
                protocol=proto,
                source_port_range='*',
                destination_port_range=str(ir.destination_port_range),
                source_address_prefix=sap,
                destination_address_prefix='*',
                access=networkmodels.SecurityRuleAccess.allow,
                priority=priority,
                direction=networkmodels.SecurityRuleDirection.inbound)
            )
            priority += 1
            i += 1
    if len(security_rules) == 0:
        logger.warning(
            'no security rules to apply, not creating a network '
            'security group')
        return None
    logger.debug('creating network security group: {}'.format(nsg_name))
    return network_client.network_security_groups.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        network_security_group_name=nsg_name,
        parameters=networkmodels.NetworkSecurityGroup(
            location=rfs.location,
            security_rules=security_rules,
        ),
    )


def _create_public_ip(network_client, rfs, offset):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.RemoteFsSettings, networkmodels.Subnet, int) ->
    #        Tuple[int, msrestazure.azure_operation.AzureOperationPoller]
    """Create a network interface
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.RemoteFsSettings rfs: remote filesystem settings
    :param int offset: public ip number
    :rtype: tuple
    :return: (offset int, msrestazure.azure_operation.AzureOperationPoller)
    """
    pip_name = '{}-pip{}'.format(rfs.storage_cluster.hostname_prefix, offset)
    hostname = '{}{}'.format(rfs.storage_cluster.hostname_prefix, offset)
    # TODO check and fail if pip exists
    logger.debug('creating public ip: {}'.format(pip_name))
    return offset, network_client.public_ip_addresses.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        public_ip_address_name=pip_name,
        parameters=networkmodels.PublicIPAddress(
            location=rfs.location,
            idle_timeout_in_minutes=30,
            dns_settings=networkmodels.PublicIPAddressDnsSettings(
                domain_name_label=hostname,
            ),
            public_ip_allocation_method=(
                networkmodels.IPAllocationMethod.static if
                rfs.storage_cluster.static_public_ip else
                networkmodels.IPAllocationMethod.dynamic
            ),
            public_ip_address_version=networkmodels.IPVersion.ipv4,
        ),
    )


def _create_network_interface(
        network_client, rfs, subnet, nsg, private_ips, pips, offset):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.RemoteFsSettings, networkmodels.Subnet,
    #        networkmodels.NetworkSecurityGroup, List[str], dict, int) ->
    #        Tuple[int, networkmodels.PublicIPAddress,
    #              msrestazure.azure_operation.AzureOperationPoller]
    """Create a network interface
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.RemoteFsSettings rfs: remote filesystem settings
    :param networkmodels.Subnet subnet: virtual network subnet
    :param networkmodels.NetworkSecurityGroup nsg: network security group
    :param list private_ips: list of static private ips
    :param dict pips: public ip map
    :param int offset: network interface number
    :rtype: tuple
    :return: (offset int, msrestazure.azure_operation.AzureOperationPoller)
    """
    nic_name = '{}-ni{}'.format(rfs.storage_cluster.hostname_prefix, offset)
    # TODO check and fail if nic exists
    # create network ip config
    if private_ips is None:
        network_ip_config = networkmodels.NetworkInterfaceIPConfiguration(
            name=rfs.storage_cluster.hostname_prefix,
            subnet=subnet,
            public_ip_address=pips[offset],
        )
    else:
        network_ip_config = networkmodels.NetworkInterfaceIPConfiguration(
            name=rfs.storage_cluster.hostname_prefix,
            subnet=subnet,
            public_ip_address=pips[offset],
            private_ip_address=private_ips[offset],
            private_ip_allocation_method=networkmodels.
            IPAllocationMethod.static,
            private_ip_address_version=networkmodels.IPVersion.ipv4,

        )
    logger.debug('creating network interface: {}'.format(nic_name))
    return offset, network_client.network_interfaces.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        network_interface_name=nic_name,
        parameters=networkmodels.NetworkInterface(
            location=rfs.location,
            network_security_group=nsg,
            ip_configurations=[network_ip_config],
        ),
    )


def _create_virtual_machine(
        compute_client, rfs, availset, nics, disks, ssh_pub_key, offset):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.RemoteFsSettings, computemodels.AvailabilitySet,
    #        dict, dict, computemodels.SshPublicKey, int) ->
    #        Tuple[int, msrestazure.azure_operation.AzureOperationPoller]
    """Create a virtual machine
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param settings.RemoteFsSettings rfs: remote filesystem settings
    :param computemodels.AvailabilitySet availset: availability set
    :param dict nics: network interface map
    :param dict disks: data disk map
    :param computemodels.SshPublicKey ssh_pub_key: SSH public key
    :param int offset: vm number
    :rtype: tuple
    :return: (offset int, msrestazure.azure_operation.AzureOperationPoller)
    """
    vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, offset)
    # construct data disks array
    lun = 3
    data_disks = []
    for diskname in rfs.storage_cluster.vm_disk_map[offset].disk_array:
        data_disks.append(
            computemodels.DataDisk(
                lun=lun,
                name=diskname,
                create_option=computemodels.DiskCreateOption.attach,
                managed_disk=computemodels.ManagedDiskParameters(
                    id=disks[diskname][0],
                ),
            )
        )
        lun += 1
    # sub resource availbility set
    if availset is not None:
        availset = computemodels.SubResource(
            id=availset.id,
        )
    # create vm
    logger.debug('creating virtual machine: {}'.format(vm_name))
    return compute_client.virtual_machines.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        vm_name=vm_name,
        parameters=computemodels.VirtualMachine(
            location=rfs.location,
            hardware_profile={
                'vm_size': rfs.storage_cluster.vm_size,
            },
            availability_set=availset,
            storage_profile=computemodels.StorageProfile(
                image_reference=computemodels.ImageReference(
                    publisher='Canonical',
                    offer='UbuntuServer',
                    sku='16.04-LTS',
                    version='latest',
                ),
                data_disks=data_disks,
            ),
            network_profile=computemodels.NetworkProfile(
                network_interfaces=[
                    computemodels.NetworkInterfaceReference(
                        id=nics[offset].id,
                    ),
                ],
            ),
            os_profile=computemodels.OSProfile(
                computer_name=vm_name,
                admin_username=rfs.storage_cluster.ssh.username,
                linux_configuration=computemodels.LinuxConfiguration(
                    disable_password_authentication=True,
                    ssh=computemodels.SshConfiguration(
                        public_keys=[ssh_pub_key],
                    ),
                ),
            ),
        ),
    )


def _create_virtual_machine_extension(
        compute_client, rfs, bootstrap_file, blob_urls, vm_name, disks,
        private_ips, offset):
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
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    # construct vm extensions
    vm_ext_name = '{}-vmext{}'.format(
        rfs.storage_cluster.hostname_prefix, offset)
    # get premium storage settings
    premium = False
    for diskname in rfs.storage_cluster.vm_disk_map[offset].disk_array:
        if disks[diskname][1] == computemodels.StorageAccountTypes.premium_lrs:
            premium = True
            break
    # construct server options
    server_options = []
    st = rfs.storage_cluster.file_server.type
    so = rfs.storage_cluster.file_server.server_options
    # special processing for gluster (always create these options
    # if they don't exist)
    if st == 'glusterfs':
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
            if (st == 'glusterfs' and
                    (key == 'volume_name' or key == 'volume_type' or
                     key == 'transport')):
                continue
            server_options.append('{}:{}'.format(key, so[st][key]))
    logger.debug('server options: {}'.format(server_options))
    # construct bootstrap command
    cmd = './{bsf} {f}{i}{m}{n}{o}{p}{r}{s}{t}'.format(
        bsf=bootstrap_file,
        f=' -f {}'.format(rfs.storage_cluster.vm_disk_map[offset].filesystem),
        i=' -i {}'.format(
            ','.join(private_ips)) if util.is_not_empty(private_ips) else '',
        m=' -m {}'.format(rfs.storage_cluster.file_server.mountpoint),
        n=' -n' if settings.can_tune_tcp(rfs.storage_cluster.vm_size) else '',
        o=' -o "{}"'.format(','.join(server_options)) if util.is_not_empty(
            server_options) else '',
        p=' -p' if premium else '',
        r=' -r {}'.format(rfs.storage_cluster.vm_disk_map[offset].raid_level),
        s=' -s {}'.format(rfs.storage_cluster.file_server.type),
        t=' -t {}'.format(
            ','.join(rfs.storage_cluster.file_server.mount_options)
            if util.is_not_empty(rfs.storage_cluster.file_server.mount_options)
            else ''))
    # logger.debug('bootstrap command: {}'.format(cmd))
    logger.debug('creating virtual machine extension: {}'.format(vm_ext_name))
    return compute_client.virtual_machine_extensions.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        vm_name=vm_name,
        vm_extension_name=vm_ext_name,
        extension_parameters=computemodels.VirtualMachineExtension(
            location=rfs.location,
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
    as_name = '{}-as'.format(rfs.storage_cluster.hostname_prefix)
    logger.debug('creating availability set: {}'.format(as_name))
    return compute_client.availability_sets.create_or_update(
        resource_group_name=rfs.storage_cluster.resource_group,
        name=as_name,
        # user maximums for ud/fd
        parameters=computemodels.AvailabilitySet(
            location=rfs.location,
            platform_update_domain_count=20,
            platform_fault_domain_count=3,
            managed=True,
        )
    )


def create_storage_cluster(
        resource_client, compute_client, network_client, blob_client, config,
        bootstrap_file, remotefs_files):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService, dict, str,
    #        List[tuple]) -> None
    """Create a storage cluster
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str bootstrap_file: customscript bootstrap file
    :param list remotefs_files: remotefs shell scripts
    :param dict config: configuration dict
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    # create resource group if it doesn't exist
    resource.create_resource_group(
        resource_client, rfs.storage_cluster.resource_group, rfs.location)
    # check if cluster already exists
    logger.debug('checking if storage cluster {} exists'.format(
        rfs.storage_cluster.id))
    # construct disk map
    disk_map = {}
    disk_ids = list_disks(compute_client, config, restrict_scope=True)
    for disk_id, sat in disk_ids:
        disk_map[disk_id.split('/')[-1]] = (disk_id, sat)
    del disk_ids
    # check vms
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, i)
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
                    computemodels.StorageAccountTypes.premium_lrs and
                    not rfs.storage_cluster.vm_size.lower().endswith('s')):
                raise RuntimeError(
                    ('Premium storage requires a DS, DS_V2, FS, GS or LS '
                     'series vm_size instead of {}'.format(
                         rfs.storage_cluster.vm_size)))
    # create nsg
    nsg_op = _create_network_security_group(network_client, rfs)
    # create static private ip block
    if rfs.storage_cluster.file_server.type == 'nfs':
        private_ips = None
        logger.debug('using dynamic private ip address allocation')
    else:
        # start offset at 4
        private_ips = [
            x for x in ip_from_address_prefix(
                rfs.storage_cluster.virtual_network.subnet_address_prefix,
                start_offset=4,
                max=rfs.storage_cluster.vm_count)
        ]
        logger.debug('static private ip addresses to assign: {}'.format(
            private_ips))
    # create virtual network and subnet if specified
    vnet, subnet = resource.create_virtual_network_and_subnet(
        resource_client, network_client,
        rfs.storage_cluster.virtual_network.resource_group, rfs.location,
        rfs.storage_cluster.virtual_network)
    # create public ips
    async_ops = []
    for i in range(rfs.storage_cluster.vm_count):
        async_ops.append(_create_public_ip(network_client, rfs, i))
    logger.debug('waiting for public ips to be created')
    pips = {}
    for offset, op in async_ops:
        pip = op.result()
        logger.info(
            ('public ip: {} [provisioning_state={} ip_address={} '
             'public_ip_allocation={}]').format(
                 pip.id, pip.provisioning_state,
                 pip.ip_address, pip.public_ip_allocation_method))
        pips[offset] = pip
    async_ops.clear()
    # get nsg
    if nsg_op is None:
        nsg = None
    else:
        logger.debug('waiting for network security group to be created')
        nsg = nsg_op.result()
    # create nics
    nics = {}
    for i in range(rfs.storage_cluster.vm_count):
        async_ops.append(_create_network_interface(
            network_client, rfs, subnet, nsg, private_ips, pips, i))
    # create availability set if vm_count > 1
    availset = _create_availability_set(compute_client, rfs)
    # wait for nics to be created
    logger.debug('waiting for network interfaces to be created')
    for offset, op in async_ops:
        nic = op.result()
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
    async_ops.clear()
    # create universal ssh key for all vms if not specified
    if util.is_none_or_empty(rfs.storage_cluster.ssh.ssh_public_key):
        _, ssh_pub_key = crypto.generate_ssh_keypair(
            rfs.storage_cluster.ssh.generated_file_export_path,
            crypto.get_remotefs_ssh_key_prefix())
    else:
        ssh_pub_key = rfs.storage_cluster.ssh.ssh_public_key
    with open(ssh_pub_key, 'rb') as fd:
        key_data = fd.read().decode('utf8')
    ssh_pub_key = computemodels.SshPublicKey(
        path='/home/{}/.ssh/authorized_keys'.format(
            rfs.storage_cluster.ssh.username),
        key_data=key_data,
    )
    del key_data
    # create vms
    vms_async_ops = {}
    for i in range(rfs.storage_cluster.vm_count):
        vms_async_ops[i] = _create_virtual_machine(
            compute_client, rfs, availset, nics, disk_map, ssh_pub_key, i)
    # upload scripts to blob storage for customscript vm extension
    blob_urls = storage.upload_for_remotefs(blob_client, remotefs_files)
    # wait for vms to be created
    logger.info(
        'waiting for {} virtual machines to be created'.format(
            len(vms_async_ops)))
    vms = {}
    for offset in vms_async_ops:
        # cache vm
        vms[offset] = vms_async_ops[offset].result()
    del vms_async_ops
    logger.debug('{} virtual machines created'.format(len(vms)))
    # wait for all vms to be created before installing extensions to prevent
    # variability in wait times and timeouts during customscript
    vm_ext_ops = {}
    for i in range(rfs.storage_cluster.vm_count):
        # install vm extension
        vm_ext_ops[i] = _create_virtual_machine_extension(
            compute_client, rfs, bootstrap_file, blob_urls,
            vms[i].name, disk_map, private_ips, i)
    logger.debug('waiting for virtual machine extensions to be created')
    for offset in vm_ext_ops:
        # refresh public ip for vm
        pip = network_client.public_ip_addresses.get(
            resource_group_name=rfs.storage_cluster.resource_group,
            public_ip_address_name=pips[offset].name,
        )
        # get vm extension result
        vm_ext = vm_ext_ops[offset].result()
        vm = vms[offset]
        logger.info(
            'virtual machine: {} [provisioning_state={}/{} fqdn={} '
            'public_ip_address={} vm_size={}]'.format(
                vm.id, vm.provisioning_state, vm_ext.provisioning_state,
                pip.dns_settings.fqdn, pip.ip_address,
                vm.hardware_profile.vm_size))


def resize_storage_cluster(
        compute_client, network_client, blob_client, config, bootstrap_file,
        addbrick_file, remotefs_files):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str, str,
    #        list) -> bool
    """Resize a storage cluster (increase size only for now)
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str bootstrap_file: bootstrap file
    :param str addbrick_file: glusterfs addbrick file
    :param list remotefs_files: remotefs files to upload
    :rtype: bool
    :return: if cluster was resized
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    # if storage cluster is not glusterfs, exit
    if rfs.storage_cluster.file_server.type != 'glusterfs':
        raise ValueError(
            'Resize is only supported on glusterfs storage clusters')
    # only allow certain types of resizes to proceed
    voltype = settings.get_file_server_glusterfs_volume_type(
        rfs.storage_cluster).lower()
    if 'stripe' in voltype:
        raise RuntimeError('Cannot resize glusterfs striped volumes')
    # construct disk map
    disk_map = {}
    disk_ids = list_disks(compute_client, config, restrict_scope=True)
    for disk_id, sat in disk_ids:
        disk_map[disk_id.split('/')[-1]] = (disk_id, sat)
    del disk_ids
    # get existing vms
    new_vms = []
    pe_vms = {}
    all_pe_disks = set()
    vnet_name = None
    subnet_name = None
    nsg_name = None
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, i)
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
                _get_resource_names_from_virtual_machine(
                    compute_client, network_client, rfs, vm)
        # add vm to map
        pe_vms[i] = entry
    # check early return conditions
    if len(new_vms) == 0:
        logger.warning(
            'no new virtual machines to add in storage cluster {}'.format(
                rfs.storage_cluster.id))
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
         'the storage cluster {}.'.format(rfs.storage_cluster.id)))
    # confirm before proceeding
    if not util.confirm_action(
            config, 'resize storage cluster {}'.format(
                rfs.storage_cluster.id)):
        return False
    # create static private ip block, start offset at 4
    private_ips = [
        x for x in ip_from_address_prefix(
            rfs.storage_cluster.virtual_network.subnet_address_prefix,
            start_offset=4,
            max=rfs.storage_cluster.vm_count)
    ]
    logger.debug('static private ip block: {}'.format(private_ips))
    # create public ips
    async_ops = []
    for i in new_vms:
        async_ops.append(_create_public_ip(network_client, rfs, i))
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
            compute_client, network_client, config, None, vm.name)
        break
    if settings.verbose(config):
        logger.debug('prober vm: {}'.format(ssh_info))
    # wait for pips
    logger.debug('waiting for public ips to be created')
    pips = {}
    for offset, op in async_ops:
        pip = op.result()
        logger.info(
            ('public ip: {} [provisioning_state={} ip_address={} '
             'public_ip_allocation={}]').format(
                 pip.id, pip.provisioning_state,
                 pip.ip_address, pip.public_ip_allocation_method))
        pips[offset] = pip
    async_ops.clear()
    # create nics
    nics = {}
    for i in new_vms:
        async_ops.append(_create_network_interface(
            network_client, rfs, subnet, nsg, private_ips, pips, i))
    # get availability set
    availset = compute_client.availability_sets.get(
        resource_group_name=rfs.storage_cluster.resource_group,
        availability_set_name='{}-as'.format(
            rfs.storage_cluster.hostname_prefix),
    )
    # wait for nics to be created
    logger.debug('waiting for network interfaces to be created')
    for offset, op in async_ops:
        nic = op.result()
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
    async_ops.clear()
    # create universal ssh key for all vms if not specified
    if util.is_none_or_empty(rfs.storage_cluster.ssh.ssh_public_key):
        # check if ssh key exists first in default location
        ssh_pub_key = pathlib.Path(
            rfs.storage_cluster.ssh.generated_file_export_path,
            crypto.get_remotefs_ssh_key_prefix() + '.pub')
        if not ssh_pub_key.exists():
            _, ssh_pub_key = crypto.generate_ssh_keypair(
                rfs.storage_cluster.ssh.generated_file_export_path,
                crypto.get_remotefs_ssh_key_prefix())
        else:
            ssh_pub_key = str(ssh_pub_key)
    else:
        ssh_pub_key = rfs.storage_cluster.ssh.ssh_public_key
    with open(ssh_pub_key, 'rb') as fd:
        key_data = fd.read().decode('utf8')
    ssh_pub_key = computemodels.SshPublicKey(
        path='/home/{}/.ssh/authorized_keys'.format(
            rfs.storage_cluster.ssh.username),
        key_data=key_data,
    )
    del key_data
    # create vms
    vms_async_ops = {}
    for i in new_vms:
        vms_async_ops[i] = _create_virtual_machine(
            compute_client, rfs, availset, nics, disk_map, ssh_pub_key, i)
    # upload scripts to blob storage for customscript vm extension
    blob_urls = storage.upload_for_remotefs(blob_client, remotefs_files)
    # gather all new private ips
    new_private_ips = {}
    for offset in nics:
        new_private_ips[offset] = nics[
            offset].ip_configurations[0].private_ip_address
    if settings.verbose(config):
        logger.debug('new private ips: {}'.format(new_private_ips))
    # wait for vms to be created
    logger.info(
        'waiting for {} virtual machines to be created'.format(
            len(vms_async_ops)))
    vms = {}
    for offset in vms_async_ops:
        # cache vm
        vms[offset] = vms_async_ops[offset].result()
    del vms_async_ops
    logger.debug('{} virtual machines created'.format(len(vms)))
    # wait for all vms to be created before installing extensions to prevent
    # variability in wait times and timeouts during customscript
    vm_ext_ops = {}
    for i in new_vms:
        # install vm extension
        vm_ext_ops[i] = _create_virtual_machine_extension(
            compute_client, rfs, bootstrap_file, blob_urls,
            vms[i].name, disk_map, private_ips, i)
    # execute special add brick script
    script_cmd = \
        '/opt/batch-shipyard/{asf} {c}{i}{n}{v}'.format(
            asf=addbrick_file,
            c=' -c {}'.format(rfs.storage_cluster.vm_count),
            i=' -i {}'.format(','.join(list(new_private_ips.values()))),
            n=' -n {}'.format(
                settings.get_file_server_glusterfs_volume_name(
                    rfs.storage_cluster)),
            v=' -v "{}"'.format(voltype),
        )
    ssh_priv_key, port, username, ip = ssh_info
    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no',
           '-o', 'UserKnownHostsFile={}'.format(os.devnull),
           '-i', str(ssh_priv_key), '-p', str(port),
           '{}@{}'.format(username, ip), 'sudo']
    cmd.extend(script_cmd.split())
    if settings.verbose(config):
        logger.debug('add brick command: {}'.format(cmd))
    proc = util.subprocess_nowait_pipe_stdout(cmd)
    stdout = proc.communicate()[0]
    logline = 'add brick script completed with ec={}'.format(proc.returncode)
    if proc.returncode != 0:
        logger.error(logline)
    else:
        logger.info(logline)
    del logline
    if util.is_not_empty(stdout):
        stdout = stdout.decode('utf8')
        if util.on_windows():
            stdout = stdout.replace('\n', os.linesep)
        logger.debug('add brick output:{}{}'.format(os.linesep, stdout))
    del stdout
    # wait for new vms to finish custom script extension processing
    logger.debug('waiting for virtual machine extensions to be created')
    for offset in vm_ext_ops:
        # refresh public ip for vm
        pip = network_client.public_ip_addresses.get(
            resource_group_name=rfs.storage_cluster.resource_group,
            public_ip_address_name=pips[offset].name,
        )
        # get vm extension result
        vm_ext = vm_ext_ops[offset].result()
        vm = vms[offset]
        logger.info(
            'virtual machine: {} [provisioning_state={}/{} fqdn={} '
            'public_ip_address={} vm_size={}]'.format(
                vm.id, vm.provisioning_state, vm_ext.provisioning_state,
                pip.dns_settings.fqdn, pip.ip_address,
                vm.hardware_profile.vm_size))


def expand_storage_cluster(
        compute_client, network_client, config, bootstrap_file,
        rebalance=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str,
    #        bool) -> bool
    """Expand a storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str bootstrap_file: bootstrap file
    :param bool rebalance: rebalance filesystem
    :rtype: bool
    :return: if cluster was expanded
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    # check if cluster exists
    logger.debug('checking if storage cluster {} exists'.format(
        rfs.storage_cluster.id))
    # construct disk map
    disk_map = {}
    disk_ids = list_disks(compute_client, config, restrict_scope=True)
    for disk_id, sat in disk_ids:
        disk_map[disk_id.split('/')[-1]] = (disk_id, sat)
    del disk_ids
    # check vms
    vms = {}
    new_disk_count = 0
    for i in range(rfs.storage_cluster.vm_count):
        # check if this vm filesystem supports expanding
        if (rfs.storage_cluster.vm_disk_map[i].filesystem != 'btrfs' and
                rfs.storage_cluster.vm_disk_map[i].raid_level == 0):
            raise RuntimeError(
                'Cannot expand mdadm-based RAID-0 volumes. Please re-create '
                'your storage cluster with btrfs using new disks.')
        vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, i)
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
                rfs.storage_cluster.id))
        return False
    if settings.verbose(config):
        logger.debug('expand settings:{}{}'.format(os.linesep, vms))
    if new_disk_count == 0:
        logger.error(
            'no new disks detected for storage cluster {}'.format(
                rfs.storage_cluster.id))
        return False
    # confirm before proceeding
    if not util.confirm_action(
            config, 'expand storage cluster {}'.format(
                rfs.storage_cluster.id)):
        return False
    # attach new data disks to each vm
    async_ops = []
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
                    computemodels.StorageAccountTypes.premium_lrs):
                premium = True
            vm.storage_profile.data_disks.append(
                computemodels.DataDisk(
                    lun=lun,
                    name=diskname,
                    create_option=computemodels.DiskCreateOption.attach,
                    managed_disk=computemodels.ManagedDiskParameters(
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
        async_ops.append(
            (key, premium, compute_client.virtual_machines.create_or_update(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm.name,
                parameters=vm)))
    # wait for async ops to complete
    if len(async_ops) == 0:
        logger.error('no operations started for expansion')
        return False
    logger.debug('waiting for disks to attach to virtual machines')
    for offset, premium, op in async_ops:
        vm = op.result()
        vms[offset]['vm'] = vm
        # execute bootstrap script via ssh
        script_cmd = \
            '/opt/batch-shipyard/{bsf} {a}{b}{f}{m}{p}{r}{s}'.format(
                bsf=bootstrap_file,
                a=' -a',
                b=' -b' if rebalance else '',
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
            compute_client, network_client, config, None, vm.name)
        cmd = ['ssh', '-o', 'StrictHostKeyChecking=no',
               '-o', 'UserKnownHostsFile={}'.format(os.devnull),
               '-i', str(ssh_priv_key), '-p', str(port),
               '{}@{}'.format(username, ip), 'sudo']
        cmd.extend(script_cmd.split())
        if settings.verbose(config):
            logger.debug('bootstrap command: {}'.format(cmd))
        proc = util.subprocess_nowait_pipe_stdout(cmd)
        stdout = proc.communicate()[0]
        if util.is_not_empty(stdout):
            stdout = stdout.decode('utf8')
            if util.on_windows():
                stdout = stdout.replace('\n', os.linesep)
        vms[offset]['status'] = proc.returncode
        vms[offset]['stdout'] = '>>stdout>> {}:{}{}'.format(
            vm.name, os.linesep, stdout)
    logger.info('disk attach operations completed')
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
    return True


def _get_resource_names_from_virtual_machine(
        compute_client, network_client, rfs, vm, nic=None, pip=None):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        settings.RemoteFsSettings, computemodels.VirtualMachine,
    #        networkmodels.NetworkInterface, networkmodels.PublicIPAddress) ->
    #        Tuple[str, str, str, str, str]
    """Get resource names from a virtual machine
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param rfs settings.RemoteFsSettings: remote fs settings
    :param vm computemodels.VirtualMachine: vm
    :param networkmodels.NetworkInterface nic: network interface
    :param networkmodels.PublicIPAddress pip: public ip
    :rtype: tuple
    :return: (nic_name, pip_name, subnet_name, vnet_name, nsg_name)
    """
    # get nic
    if nic is None:
        nic_id = vm.network_profile.network_interfaces[0].id
        tmp = nic_id.split('/')
        if tmp[-2] != 'networkInterfaces':
            raise RuntimeError('could not parse network interface id')
        nic_name = tmp[-1]
        nic = network_client.network_interfaces.get(
            resource_group_name=rfs.storage_cluster.resource_group,
            network_interface_name=nic_name,
        )
    else:
        nic_name = nic.name
    # get public ip
    if pip is None:
        pip_id = nic.ip_configurations[0].public_ip_address.id
        tmp = pip_id.split('/')
        if tmp[-2] != 'publicIPAddresses':
            raise RuntimeError('could not parse public ip address id')
        pip_name = tmp[-1]
    else:
        pip_name = pip.name
    # get subnet and vnet
    subnet_id = nic.ip_configurations[0].subnet.id
    tmp = subnet_id.split('/')
    if tmp[-2] != 'subnets' and tmp[-4] != 'virtualNetworks':
        raise RuntimeError('could not parse subnet id')
    subnet_name = tmp[-1]
    vnet_name = tmp[-3]
    # get nsg
    if nic.network_security_group is not None:
        nsg_id = nic.network_security_group.id
        tmp = nsg_id.split('/')
        if tmp[-2] != 'networkSecurityGroups':
            raise RuntimeError('could not parse network security group id')
        nsg_name = tmp[-1]
    else:
        nsg_name = None
    return (nic_name, pip_name, subnet_name, vnet_name, nsg_name)


def _delete_virtual_machine(compute_client, rg_name, vm_name):
    # type: (azure.mgmt.compute.ComputeManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete a virtual machine
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param str rg_name: resource group name
    :param str vm_name: vm name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deleting virtual machine {}'.format(vm_name))
    return compute_client.virtual_machines.delete(
        resource_group_name=rg_name,
        vm_name=vm_name,
    )


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


def _delete_network_interface(network_client, rg_name, nic_name):
    # type: (azure.mgmt.network.NetworkManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete a network interface
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str rg_name: resource group name
    :param str nic_name: network interface name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deleting network interface {}'.format(nic_name))
    return network_client.network_interfaces.delete(
        resource_group_name=rg_name,
        network_interface_name=nic_name,
    )


def _delete_network_security_group(network_client, rg_name, nsg_name):
    # type: (azure.mgmt.network.NetworkManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete a network security group
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str rg_name: resource group name
    :param str nsg_name: network security group name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deleting network security group {}'.format(nsg_name))
    return network_client.network_security_groups.delete(
        resource_group_name=rg_name,
        network_security_group_name=nsg_name,
    )


def _delete_public_ip(network_client, rg_name, pip_name):
    # type: (azure.mgmt.network.NetworkManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete a public ip
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str rg_name: resource group name
    :param str pip_name: public ip name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deleting public ip {}'.format(pip_name))
    return network_client.public_ip_addresses.delete(
        resource_group_name=rg_name,
        public_ip_address_name=pip_name,
    )


def _delete_subnet(network_client, rg_name, vnet_name, subnet_name):
    # type: (azure.mgmt.network.NetworkManagementClient, str, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete a subnet
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str rg_name: resource group name
    :param str vnet_name: virtual network name
    :param str subnet_name: subnet name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deleting subnet {} on virtual network {}'.format(
        subnet_name, vnet_name))
    return network_client.subnets.delete(
        resource_group_name=rg_name,
        virtual_network_name=vnet_name,
        subnet_name=subnet_name,
    )


def _delete_virtual_network(network_client, rg_name, vnet_name):
    # type: (azure.mgmt.network.NetworkManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete a virtual network
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str rg_name: resource group name
    :param str vnet_name: virtual network name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deleting virtual network {}'.format(vnet_name))
    return network_client.virtual_networks.delete(
        resource_group_name=rg_name,
        virtual_network_name=vnet_name,
    )


def delete_storage_cluster(
        resource_client, compute_client, network_client, config,
        delete_data_disks=False, delete_virtual_network=False,
        delete_resource_group=False, wait=False):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, bool, bool,
    #        bool, bool) -> None
    """Delete a storage cluster
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param bool delete_data_disks: delete managed data disks
    :param bool delete_virtual_network: delete vnet
    :param bool delete_resource_group: delete resource group
    :param bool wait: wait for completion
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
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
            config, 'delete storage cluster {}'.format(
                rfs.storage_cluster.id)):
        return
    # get vms and cache for concurent async ops
    resources = {}
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
            )
        except msrestazure.azure_exceptions.CloudError as e:
            if e.status_code == 404:
                logger.warning('virtual machine {} not found'.format(vm_name))
                continue
            else:
                raise
        else:
            # get resources connected to vm
            nic, pip, subnet, vnet, nsg = \
                _get_resource_names_from_virtual_machine(
                    compute_client, network_client, rfs, vm)
            resources[i] = {
                'vm': vm.name,
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
    # delete vms
    vm_ops = []
    for key in resources:
        vm_name = resources[key]['vm']
        vm_ops.append(_delete_virtual_machine(
            compute_client, rfs.storage_cluster.resource_group, vm_name))
    logger.info(
        'waiting for {} virtual machines to delete'.format(len(vm_ops)))
    for op in vm_ops:
        op.result()
    logger.info('{} virtual machines deleted'.format(len(vm_ops)))
    # delete nics
    nic_ops = []
    for key in resources:
        nic = resources[key]['nic']
        nic_ops.append(_delete_network_interface(
            network_client, rfs.storage_cluster.resource_group, nic))
    # wait for nics to delete
    logger.debug('waiting for network interfaces to delete')
    for op in nic_ops:
        op.result()
    logger.info('{} network interfaces deleted'.format(len(nic_ops)))
    # delete nsg
    deleted = set()
    nsg_ops = []
    for key in resources:
        nsg_name = resources[key]['nsg']
        if nsg_name in deleted:
            continue
        deleted.add(nsg_name)
        nsg_ops.append(_delete_network_security_group(
            network_client, rfs.storage_cluster.resource_group, nsg_name))
    deleted.clear()
    # delete public ips
    pip_ops = []
    for key in resources:
        pip = resources[key]['pip']
        pip_ops.append(_delete_public_ip(
            network_client, rfs.storage_cluster.resource_group, pip))
    logger.debug('waiting for public ips to delete')
    for op in pip_ops:
        op.result()
    logger.info('{} public ips deleted'.format(len(pip_ops)))
    # delete subnets
    for key in resources:
        subnet_ops = []
        subnet_name = resources[key]['subnet']
        vnet_name = resources[key]['vnet']
        if util.is_none_or_empty(subnet_name) or subnet_name in deleted:
            continue
        deleted.add(subnet_name)
        subnet_ops.append(_delete_subnet(
            network_client, rfs.storage_cluster.resource_group, vnet_name,
            subnet_name))
        logger.debug('waiting for subnets to delete')
        for op in subnet_ops:
            op.result()
        logger.info('{} subnets deleted'.format(len(subnet_ops)))
        subnet_ops.clear()
    deleted.clear()
    # delete vnet
    vnet_ops = []
    for key in resources:
        vnet_name = resources[key]['vnet']
        if util.is_none_or_empty(vnet_name) or vnet_name in deleted:
            continue
        deleted.add(vnet_name)
        vnet_ops.append(_delete_virtual_network(
            network_client, rfs.storage_cluster.resource_group, vnet_name))
    deleted.clear()
    # delete availability set
    for key in resources:
        as_name = resources[key]['as']
        if util.is_none_or_empty(as_name) or as_name in deleted:
            continue
        deleted.add(as_name)
        _delete_availability_set(
            compute_client, rfs.storage_cluster.resource_group, as_name)
        logger.info('availability set {} deleted'.format(as_name))
    deleted.clear()
    # delete data disks (delay from vm due to potential in use errors)
    data_disk_ops = []
    for key in resources:
        data_disks = resources[key]['data_disks']
        if len(data_disks) > 0:
            data_disk_ops.extend(delete_managed_disks(
                compute_client, config, data_disks,
                resource_group=rfs.managed_disks.resource_group, wait=False))
    # delete os disks (delay from vm due to potential in use errors)
    os_disk_ops = []
    for key in resources:
        os_disk = resources[key]['os_disk']
        os_disk_ops.extend(delete_managed_disks(
            compute_client, config, os_disk,
            resource_group=rfs.storage_cluster.resource_group, wait=False,
            confirm_override=True))
    # TODO check for 409s and retry
    # wait for nsgs and os disks to delete
    if wait:
        logger.debug('waiting for network security groups to delete')
        for op in nsg_ops:
            op.result()
        logger.info('{} network security groups deleted'.format(
            len(nsg_ops)))
        nsg_ops.clear()
        logger.debug('waiting for virtual networks to delete')
        for op in vnet_ops:
            op.result()
        logger.info('{} virtual networks deleted'.format(len(vnet_ops)))
        vnet_ops.clear()
        logger.debug('waiting for managed os disks to delete')
        for op in os_disk_ops:
            op.result()
        logger.info('{} managed os disks deleted'.format(
            len(os_disk_ops)))
        os_disk_ops.clear()
        if len(data_disk_ops) > 0:
            logger.debug('waiting for managed data disks to delete')
            for op in data_disk_ops:
                op.result()
            logger.info('{} managed data disks deleted'.format(
                len(data_disk_ops)))
            data_disk_ops.clear()


def _deallocate_virtual_machine(compute_client, rg_name, vm_name):
    # type: (azure.mgmt.compute.ComputeManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Deallocate a virtual machine
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param str rg_name: resource group name
    :param str vm_name: vm name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('deallocating virtual machine {}'.format(vm_name))
    return compute_client.virtual_machines.deallocate(
        resource_group_name=rg_name,
        vm_name=vm_name,
    )


def _start_virtual_machine(compute_client, rg_name, vm_name):
    # type: (azure.mgmt.compute.ComputeManagementClient, str, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Start a deallocated virtual machine
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param str rg_name: resource group name
    :param str vm_name: vm name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    logger.debug('starting virtual machine {}'.format(vm_name))
    return compute_client.virtual_machines.start(
        resource_group_name=rg_name,
        vm_name=vm_name,
    )


def suspend_storage_cluster(compute_client, config, wait=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, bool) -> None
    """Suspend a storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param bool wait: wait for suspension to complete
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    vms = []
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, i)
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
            config, 'suspend storage cluster {}'.format(
                rfs.storage_cluster.id)):
        return
    # deallocate each vm
    async_ops = []
    for vm in vms:
        async_ops.append(_deallocate_virtual_machine(
            compute_client, rfs.storage_cluster.resource_group, vm.name))
    if wait:
        logger.info(
            'waiting for {} virtual machines to deallocate'.format(
                len(async_ops)))
        for op in async_ops:
            op.result()
        logger.info('{} virtual machines deallocated'.format(len(async_ops)))


def start_storage_cluster(compute_client, config, wait=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict, bool) -> None
    """Starts a suspended storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param bool wait: wait for restart to complete
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    vms = []
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, i)
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
            config, 'start suspended storage cluster {}'.format(
                rfs.storage_cluster.id)):
        return
    # start each vm
    async_ops = []
    for vm in vms:
        async_ops.append(_start_virtual_machine(
            compute_client, rfs.storage_cluster.resource_group, vm.name))
    if wait:
        logger.info(
            'waiting for {} virtual machines to start'.format(len(async_ops)))
        for op in async_ops:
            op.result()
        logger.info('{} virtual machines started'.format(len(async_ops)))


def stat_storage_cluster(
        compute_client, network_client, config, status_script, detail=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, str,
    #        bool) -> None
    """Retrieve status of a storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param str status_script: status script
    :param bool detail: detailed status
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    # retrieve all vms
    vms = []
    for i in range(rfs.storage_cluster.vm_count):
        vm_name = '{}-vm{}'.format(rfs.storage_cluster.hostname_prefix, i)
        try:
            vm = compute_client.virtual_machines.get(
                resource_group_name=rfs.storage_cluster.resource_group,
                vm_name=vm_name,
                expand=computemodels.InstanceViewTypes.instance_view,
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
                rfs.storage_cluster.id))
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
        _, _, subnet, vnet, nsg = _get_resource_names_from_virtual_machine(
            compute_client, network_client, rfs, vm, nic=nic, pip=pip)
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
                compute_client, network_client, config, None, vm.name, pip=pip)
            offset = int(vm.name.split('-vm')[-1])
            script_cmd = '/opt/batch-shipyard/{sf} {f}{m}{n}{r}{s}'.format(
                sf=status_script,
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
            cmd = ['ssh', '-o', 'StrictHostKeyChecking=no',
                   '-o', 'UserKnownHostsFile={}'.format(os.devnull),
                   '-i', str(ssh_priv_key), '-p', str(port),
                   '{}@{}'.format(username, ip), 'sudo']
            cmd.extend(script_cmd.split())
            proc = util.subprocess_nowait_pipe_stdout(cmd)
            stdout = proc.communicate()[0]
            if util.is_not_empty(stdout):
                stdout = stdout.decode('utf8')
                if util.on_windows():
                    stdout = stdout.replace('\n', os.linesep)
            fsstatus.append(
                '>> File Server Status for {} ec={}:{}{}'.format(
                    vm.name, proc.returncode, os.linesep, stdout))
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
            'fqdn': pip.dns_settings.fqdn,
            'public_ip_address': pip.ip_address,
            'public_ip_allocation': pip.public_ip_allocation_method,
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
        rfs.storage_cluster.id, os.linesep, log))


def _get_ssh_info(
        compute_client, network_client, config, cardinal, hostname, pip=None):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, int,
    #        str, networkmodels.PublicIPAddress) -> None
    """SSH to a node in storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param int cardinal: cardinal number
    :param str hostname: hostname
    :param networkmodels.PublicIPAddress pip: public ip
    :rtype: tuple
    :return (ssh private key, port, username, ip)
    """
    # retrieve remotefs settings
    rfs = settings.remotefs_settings(config)
    # retrieve specific vm
    if cardinal is not None:
        vm_name = '{}-vm{}'.format(
            rfs.storage_cluster.hostname_prefix, cardinal)
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
    # get pip connected to vm
    if pip is None:
        _, pip = resource.get_nic_and_pip_from_virtual_machine(
            network_client, rfs.storage_cluster.resource_group, vm)
    # connect to vm
    ssh_priv_key = pathlib.Path(
        rfs.storage_cluster.ssh.generated_file_export_path,
        crypto.get_remotefs_ssh_key_prefix())
    if not ssh_priv_key.exists():
        raise RuntimeError('SSH private key file not found at: {}'.format(
            ssh_priv_key))
    return ssh_priv_key, 22, vm.os_profile.admin_username, pip.ip_address


def ssh_storage_cluster(
        compute_client, network_client, config, cardinal, hostname):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict, int,
    #        str) -> None
    """SSH to a node in storage cluster
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param int cardinal: cardinal number
    :param str hostname: hostname
    """
    ssh_priv_key, port, username, ip = _get_ssh_info(
        compute_client, network_client, config, cardinal, hostname)
    # connect to vm
    logger.info('connecting to virtual machine {}:{} with key {}'.format(
        ip, port, ssh_priv_key))
    util.subprocess_with_output(
        ['ssh', '-o', 'StrictHostKeyChecking=no',
         '-o', 'UserKnownHostsFile={}'.format(os.devnull),
         '-i', str(ssh_priv_key), '-p', str(port),
         '{}@{}'.format(username, ip)])
