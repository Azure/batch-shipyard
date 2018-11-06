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
import functools
import json
import logging
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import random
import time
# non-stdlib imports
import azure.mgmt.network.models as networkmodels
import azure.mgmt.resource.resources.models as rgmodels
import msrest.exceptions
import msrestazure.azure_exceptions
# local imports
from . import crypto
from . import settings
from . import storage
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)


class AsyncOperation(object):
    """Async Operation handler with automatic retry"""
    def __init__(
            self, partial, max_retries=-1, auto_invoke=True,
            retry_conflict=False):
        """Ctor for AsyncOperation
        :param AsyncOperation self: this
        :param functools.partial partial: partial object
        :param int max_retries: maximum number of retries before giving up
        :param bool auto_invoke: automatically invoke the async operation
        :param bool retry_conflict: retry 409 conflict errors
        """
        self._partial = partial
        self._retry_count = 0
        self._max_retries = max_retries
        self._retry_conflict = retry_conflict
        self._op = None
        self._noop = False
        if auto_invoke:
            self._invoke()

    def _invoke(self):
        """Invoke helper
        :param AsyncOperation self: this
        """
        if self._op is None:
            self._op = self._partial()
            if self._op is None:
                self._noop = True

    def result(self):
        """Wait on async operation result
        :param AsyncOperation self: this
        :rtype: object
        :return: result of async wait
        """
        alloc_failures = 0
        while True:
            last_status_code = None
            last_error_message = None
            if self._noop:
                return self._op  # will return None
            self._invoke()
            try:
                return self._op.result()
            except (msrest.exceptions.ClientException,
                    msrestazure.azure_exceptions.CloudError) as e:
                if e.status_code >= 400 and e.status_code < 500:
                    if not (e.status_code == 409 and self._retry_conflict):
                        logger.error('not retrying status_code={}'.format(
                            e.status_code))
                        raise
                if e.status_code == 200 and 'Allocation failed' in e.message:
                    alloc_failures += 1
                    if alloc_failures > 10:
                        raise
                self._retry_count += 1
                if (self._max_retries >= 0 and
                        self._retry_count > self._max_retries):
                    logger.error(
                        ('Ran out of retry attempts invoking {}(args={} '
                         'kwargs={}) status_code={}').format(
                             self._partial.func.__name__, self._partial.args,
                             self._partial.keywords, e.status_code))
                    raise
                last_status_code = e.status_code
                last_error_message = e.message
            self._op = None
            # randomly backoff
            time.sleep(random.randint(1, 3))
            logger.debug(
                ('Attempting retry of operation: {}, status={} message="{}" '
                 'retry_count={} max_retries={}').format(
                     self._partial.func.__name__, last_status_code,
                     last_error_message, self._retry_count,
                     self._max_retries if self._max_retries >= 0 else 'inf'))


def create_resource_group(resource_client, resource_group, location):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        str, str) -> None
    """Create a resource group if it doesn't exist
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param str resource_group: resource group name
    :param str location: location
    """
    # check if resource group exists
    exists = resource_client.resource_groups.check_existence(resource_group)
    # create resource group if it doesn't exist
    if not exists:
        logger.info('creating resource group: {}'.format(resource_group))
        resource_client.resource_groups.create_or_update(
            resource_group_name=resource_group,
            parameters=rgmodels.ResourceGroup(
                location=location,
            )
        )
    else:
        logger.debug('resource group {} exists'.format(resource_group))


def create_virtual_network_and_subnet(
        resource_client, network_client, resource_group, location,
        vnet_settings):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, str, str,
    #        settings.VirtualNetworkSettings) ->
    #        Tuple[networkmodels.VirtualNetwork, networkmodels.Subnet]
    """Create a Virtual network and subnet. This is a blocking function.
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str resource_group: resouce group name
    :param str location: location
    :param settings.VirtualNetworkSettings vnet: vnet settings
    :rtype: tuple
    :return: (virtual network, subnet)
    """
    # check if vnet already exists
    exists = False
    try:
        virtual_network = network_client.virtual_networks.get(
            resource_group_name=resource_group,
            virtual_network_name=vnet_settings.name,
        )
        if vnet_settings.existing_ok:
            logger.debug('virtual network {} already exists'.format(
                virtual_network.id))
            exists = True
        else:
            raise RuntimeError(
                'virtual network {} already exists'.format(virtual_network.id))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    if not exists:
        if not vnet_settings.create_nonexistant:
            raise RuntimeError(
                ('create_nonexistant setting is {} for virtual '
                 'network {}').format(
                     vnet_settings.create_nonexistant, vnet_settings.name))
        # create resource group if needed
        create_resource_group(resource_client, resource_group, location)
        logger.info('creating virtual network: {}'.format(vnet_settings.name))
        async_create = AsyncOperation(functools.partial(
            network_client.virtual_networks.create_or_update,
            resource_group_name=resource_group,
            virtual_network_name=vnet_settings.name,
            parameters=networkmodels.VirtualNetwork(
                location=location,
                address_space=networkmodels.AddressSpace(
                    address_prefixes=[
                        vnet_settings.address_space,
                    ],
                ),
            ),
        ))
        virtual_network = async_create.result()
    # attach subnet
    exists = False
    try:
        subnet = network_client.subnets.get(
            resource_group_name=resource_group,
            virtual_network_name=vnet_settings.name,
            subnet_name=vnet_settings.subnet_name,
        )
        if vnet_settings.existing_ok:
            logger.debug('subnet {} already exists'.format(subnet.id))
            exists = True
        else:
            raise RuntimeError(
                'subnet {} already exists'.format(subnet.id))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    if not exists:
        if not vnet_settings.create_nonexistant:
            raise RuntimeError(
                ('create_nonexistant setting is {} for virtual '
                 'network {} and subnet {}').format(
                     vnet_settings.create_nonexistant, vnet_settings.name,
                     vnet_settings.subnet_name))
        logger.info('attaching subnet {} to virtual network {}'.format(
            vnet_settings.subnet_name, vnet_settings.name))
        async_create = AsyncOperation(functools.partial(
            network_client.subnets.create_or_update,
            resource_group_name=resource_group,
            virtual_network_name=vnet_settings.name,
            subnet_name=vnet_settings.subnet_name,
            subnet_parameters=networkmodels.Subnet(
                address_prefix=vnet_settings.subnet_address_prefix
            )
        ))
        subnet = async_create.result()
    logger.info(
        ('virtual network: {} [provisioning_state={} address_space={} '
         'subnet={} address_prefix={}]').format(
             virtual_network.id, virtual_network.provisioning_state,
             virtual_network.address_space.address_prefixes,
             vnet_settings.subnet_name, subnet.address_prefix))
    return (virtual_network, subnet)


def get_nic_from_virtual_machine(network_client, resource_group, vm):
    # type: (azure.mgmt.network.NetworkManagementClient, str,
    #        computemodels.VirtualMachine) -> networkmodels.NetworkInterface
    """Get network interface and public ip from a virtual machine
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str resource_group: resource group name
    :param vm computemodels.VirtualMachine: vm
    :rtype: networkmodels.NetworkInterface
    :return: nic
    """
    nic_id = vm.network_profile.network_interfaces[0].id
    tmp = nic_id.split('/')
    if tmp[-2] != 'networkInterfaces':
        raise RuntimeError('could not parse network interface id')
    nic_name = tmp[-1]
    nic = network_client.network_interfaces.get(
        resource_group_name=resource_group,
        network_interface_name=nic_name,
    )
    return nic


def get_nic_and_pip_from_virtual_machine(
        network_client, resource_group, vm, nic=None):
    # type: (azure.mgmt.network.NetworkManagementClient, str,
    #        computemodels.VirtualMachine, networkmodels.NetworkInterface) ->
    #        Tuple[networkmodels.NetworkInterface,
    #        networkmodels.PublicIPAddress]
    """Get network interface and public ip from a virtual machine
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param str resource_group: resource group name
    :param networkmodels.NetworkInterface nic: nic
    :param vm computemodels.VirtualMachine: vm
    :rtype: tuple
    :return: (nic, pip)
    """
    # get nic
    if nic is None:
        nic = get_nic_from_virtual_machine(network_client, resource_group, vm)
    # get public ip
    if nic.ip_configurations[0].public_ip_address is not None:
        pip_id = nic.ip_configurations[0].public_ip_address.id
        tmp = pip_id.split('/')
        if tmp[-2] != 'publicIPAddresses':
            raise RuntimeError('could not parse public ip address id')
        pip_name = tmp[-1]
        pip = network_client.public_ip_addresses.get(
            resource_group_name=resource_group,
            public_ip_address_name=pip_name,
        )
    else:
        pip = None
    return (nic, pip)


def get_resource_names_from_virtual_machine(
        compute_client, network_client, vm_resource, vm, nic=None, pip=None):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource, computemodels.VirtualMachine,
    #        networkmodels.NetworkInterface, networkmodels.PublicIPAddress) ->
    #        Tuple[str, str, str, str, str]
    """Get resource names from a virtual machine
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_resource: VM resource
    :param computemodels.VirtualMachine vm: vm
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
            resource_group_name=vm_resource.resource_group,
            network_interface_name=nic_name,
        )
    else:
        nic_name = nic.name
    # get public ip
    if pip is None:
        if nic.ip_configurations[0].public_ip_address is not None:
            pip_id = nic.ip_configurations[0].public_ip_address.id
            tmp = pip_id.split('/')
            if tmp[-2] != 'publicIPAddresses':
                raise RuntimeError('could not parse public ip address id')
            pip_name = tmp[-1]
        else:
            pip_name = None
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


def create_network_security_group(network_client, vm_resource):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Create a network security group
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_resource: VM Resource
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    nsg_name = settings.generate_network_security_group_name(vm_resource)
    # check and fail if nsg exists
    try:
        network_client.network_security_groups.get(
            resource_group_name=vm_resource.resource_group,
            network_security_group_name=nsg_name,
        )
        raise RuntimeError('network security group {} exists'.format(nsg_name))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    # create security rules as found in settings
    priority = 100
    security_rules = []
    for nsi in vm_resource.network_security.inbound:
        i = 0
        ir = vm_resource.network_security.inbound[nsi]
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
                name=settings.generate_network_security_inbound_rule_name(
                    nsi, i),
                description=settings.
                generate_network_security_inbound_rule_description(nsi, i),
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
        resource_group_name=vm_resource.resource_group,
        network_security_group_name=nsg_name,
        parameters=networkmodels.NetworkSecurityGroup(
            location=vm_resource.location,
            security_rules=security_rules,
        ),
    )


def add_inbound_network_security_rule(
        network_client, vm_resource, rule_name, inbound_rule):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource, str, settings.InboundNetworkSecurityRule) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Add an inbound network security rule to an existing nsg
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_resource: VM Resource
    :param str rule_name: rule name
    :param settings.InboundNetworkSecurityRule inbound_rule: inbound rule
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    nsg_name = settings.generate_network_security_group_name(vm_resource)
    # check and fail if nsg exists
    highest_prio = 0
    try:
        rules = network_client.security_rules.list(
            resource_group_name=vm_resource.resource_group,
            network_security_group_name=nsg_name
        )
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    for rule in rules:
        if rule.name == rule_name:
            raise RuntimeError(
                'security rule {} for nsg {} exists'.format(
                    rule_name, nsg_name))
        if rule.priority < 65000 and rule.priority > highest_prio:
            highest_prio = rule.priority
    proto = inbound_rule.protocol.lower()
    if proto == 'tcp':
        proto = networkmodels.SecurityRuleProtocol.tcp
    elif proto == 'udp':
        proto = networkmodels.SecurityRuleProtocol.udp
    elif proto == '*':
        proto = networkmodels.SecurityRuleProtocol.asterisk
    else:
        raise ValueError('Unknown protocol {} for rule {}'.format(
            proto, rule_name))
    rule = networkmodels.SecurityRule(
        name=settings.generate_network_security_inbound_rule_name(
            rule_name, 0),
        description=settings.
        generate_network_security_inbound_rule_description(rule_name, 0),
        protocol=proto,
        source_port_range='*',
        destination_port_range=str(inbound_rule.destination_port_range),
        source_address_prefix=inbound_rule.source_address_prefix,
        destination_address_prefix='*',
        access=networkmodels.SecurityRuleAccess.allow,
        priority=highest_prio + 1,
        direction=networkmodels.SecurityRuleDirection.inbound
    )
    return network_client.security_rules.create_or_update(
        resource_group_name=vm_resource.resource_group,
        network_security_group_name=nsg_name,
        security_rule_name=rule.name,
        security_rule_parameters=rule,
    )


def remove_inbound_network_security_rule(
        network_client, vm_resource, rule_name):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource, str) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Delete an inbound network security rule to an existing nsg
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_resource: VM Resource
    :param str rule_name: rule name
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: async op poller
    """
    nsg_name = settings.generate_network_security_group_name(vm_resource)
    return network_client.security_rules.delete(
        resource_group_name=vm_resource.resource_group,
        network_security_group_name=nsg_name,
        security_rule_name=settings.
        generate_network_security_inbound_rule_name(
            rule_name, 0),
    )


def create_public_ip(network_client, vm_resource, offset):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource, int) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Create a public IP
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_resource: VM Resource
    :param int offset: public ip number
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    pip_name = settings.generate_public_ip_name(vm_resource, offset)
    # check and fail if pip exists
    try:
        network_client.public_ip_addresses.get(
            resource_group_name=vm_resource.resource_group,
            public_ip_address_name=pip_name,
        )
        raise RuntimeError('public ip {} exists'.format(pip_name))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    if vm_resource.zone is not None:
        zone = [vm_resource.zone]
    else:
        zone = None
    hostname = settings.generate_hostname(vm_resource, offset)
    logger.debug('creating public ip: {} label={} zone={}'.format(
        pip_name, hostname, zone))
    return network_client.public_ip_addresses.create_or_update(
        resource_group_name=vm_resource.resource_group,
        public_ip_address_name=pip_name,
        parameters=networkmodels.PublicIPAddress(
            location=vm_resource.location,
            idle_timeout_in_minutes=30,
            dns_settings=networkmodels.PublicIPAddressDnsSettings(
                domain_name_label=hostname,
            ),
            public_ip_allocation_method=(
                networkmodels.IPAllocationMethod.static if
                vm_resource.public_ip.static else
                networkmodels.IPAllocationMethod.dynamic
            ),
            public_ip_address_version=networkmodels.IPVersion.ipv4,
            zones=zone,
        ),
    )


def create_network_interface(
        network_client, vm_resource, subnet, nsg, private_ips, pips, offset):
    # type: (azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource, networkmodels.Subnet,
    #        networkmodels.NetworkSecurityGroup, List[str], dict, int) ->
    #        msrestazure.azure_operation.AzureOperationPoller
    """Create a network interface
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_resource: VM Resource
    :param networkmodels.Subnet subnet: virtual network subnet
    :param networkmodels.NetworkSecurityGroup nsg: network security group
    :param list private_ips: list of static private ips
    :param dict pips: public ip map
    :param int offset: network interface number
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    nic_name = settings.generate_network_interface_name(vm_resource, offset)
    # check and fail if nic exists
    try:
        network_client.network_interfaces.get(
            resource_group_name=vm_resource.resource_group,
            network_interface_name=nic_name,
        )
        raise RuntimeError('network interface {} exists'.format(nic_name))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    if util.is_none_or_empty(pips):
        pip = None
        logger.debug('not assigning public ip to network interface {}'.format(
            nic_name))
    else:
        pip = pips[offset]
        logger.debug('assigning public ip {} to network interface {}'.format(
            pip.name, nic_name))
    # create network ip config
    if private_ips is None:
        network_ip_config = networkmodels.NetworkInterfaceIPConfiguration(
            name=vm_resource.hostname_prefix,
            subnet=subnet,
            public_ip_address=pip,
        )
    else:
        network_ip_config = networkmodels.NetworkInterfaceIPConfiguration(
            name=vm_resource.hostname_prefix,
            subnet=subnet,
            public_ip_address=pip,
            private_ip_address=private_ips[offset],
            private_ip_allocation_method=networkmodels.
            IPAllocationMethod.static,
            private_ip_address_version=networkmodels.IPVersion.ipv4,

        )
    logger.debug('creating network interface: {}'.format(nic_name))
    return network_client.network_interfaces.create_or_update(
        resource_group_name=vm_resource.resource_group,
        network_interface_name=nic_name,
        parameters=networkmodels.NetworkInterface(
            location=vm_resource.location,
            network_security_group=nsg,
            ip_configurations=[network_ip_config],
            enable_accelerated_networking=vm_resource.accelerated_networking,
        ),
    )


def create_virtual_machine(
        compute_client, vm_resource, availset, nics, disks, ssh_pub_key,
        offset, enable_msi=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.VmResource, computemodels.AvailabilitySet,
    #        dict, dict, computemodels.SshPublicKey, int, bool) ->
    #        Tuple[int, msrestazure.azure_operation.AzureOperationPoller]
    """Create a virtual machine
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param settings.VmResource vm_resource: VM Resource
    :param computemodels.AvailabilitySet availset: availability set
    :param dict nics: network interface map
    :param dict disks: data disk map
    :param computemodels.SshPublicKey ssh_pub_key: SSH public key
    :param int offset: vm number
    :param bool enable_msi: enable system MSI
    :rtype: tuple
    :return: (offset int, msrestazure.azure_operation.AzureOperationPoller)
    """
    vm_name = settings.generate_virtual_machine_name(vm_resource, offset)
    # construct data disks array
    lun = 0
    data_disks = []
    if util.is_not_empty(disks):
        for diskname in vm_resource.vm_disk_map[offset].disk_array:
            data_disks.append(
                compute_client.disks.models.DataDisk(
                    lun=lun,
                    name=diskname,
                    create_option=compute_client.disks.models.
                    DiskCreateOptionTypes.attach,
                    managed_disk=compute_client.disks.models.
                    ManagedDiskParameters(
                        id=disks[diskname][0],
                    ),
                )
            )
            lun += 1
    if vm_resource.zone is not None:
        zone = [vm_resource.zone]
    else:
        zone = None
    # sub resource availbility set
    if availset is not None:
        availset = compute_client.virtual_machines.models.SubResource(
            id=availset.id,
        )
    # managed service identity
    identity = None
    if enable_msi:
        identity = compute_client.virtual_machines.models.\
            VirtualMachineIdentity(
                type=compute_client.virtual_machines.models.
                ResourceIdentityType.system_assigned,
            )
    # create vm
    logger.debug(
        'creating virtual machine: {} availset={} zone={}'.format(
            vm_name, availset.id if availset is not None else None, zone))
    return compute_client.virtual_machines.create_or_update(
        resource_group_name=vm_resource.resource_group,
        vm_name=vm_name,
        parameters=compute_client.virtual_machines.models.VirtualMachine(
            location=vm_resource.location,
            hardware_profile=compute_client.virtual_machines.models.
            HardwareProfile(
                vm_size=vm_resource.vm_size,
            ),
            availability_set=availset,
            storage_profile=compute_client.virtual_machines.models.
            StorageProfile(
                image_reference=compute_client.virtual_machines.models.
                ImageReference(
                    publisher='Canonical',
                    offer='UbuntuServer',
                    sku='18.04-LTS',
                    version='latest',
                ),
                data_disks=data_disks,
            ),
            network_profile=compute_client.virtual_machines.models.
            NetworkProfile(
                network_interfaces=[
                    compute_client.virtual_machines.models.
                    NetworkInterfaceReference(
                        id=nics[offset].id,
                    ),
                ],
            ),
            os_profile=compute_client.virtual_machines.models.OSProfile(
                computer_name=vm_name,
                admin_username=vm_resource.ssh.username,
                linux_configuration=compute_client.virtual_machines.models.
                LinuxConfiguration(
                    disable_password_authentication=True,
                    ssh=compute_client.virtual_machines.models.
                    SshConfiguration(
                        public_keys=[ssh_pub_key],
                    ),
                ),
            ),
            diagnostics_profile=compute_client.virtual_machines.models.
            DiagnosticsProfile(
                boot_diagnostics=compute_client.virtual_machines.models.
                BootDiagnostics(
                    enabled=True,
                    storage_uri='https://{}.blob.{}'.format(
                        storage.get_storageaccount(),
                        storage.get_storageaccount_endpoint(),
                    ),
                ),
            ),
            identity=identity,
            zones=zone,
        ),
    )


def create_msi_virtual_machine_extension(
        compute_client, vm_resource, vm_name, offset, verbose=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.VmResource, str, int,
    #        bool) -> msrestazure.azure_operation.AzureOperationPoller
    """Create a virtual machine extension
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param settings.VmResource vm_resource: VM resource
    :param str vm_name: vm name
    :param int offset: vm number
    :param bool verbose: verbose logging
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    vm_ext_name = settings.generate_virtual_machine_msi_extension_name(
        vm_resource, offset)
    logger.debug('creating virtual machine extension: {}'.format(vm_ext_name))
    return compute_client.virtual_machine_extensions.create_or_update(
        resource_group_name=vm_resource.resource_group,
        vm_name=vm_name,
        vm_extension_name=vm_ext_name,
        extension_parameters=compute_client.virtual_machine_extensions.models.
        VirtualMachineExtension(
            location=vm_resource.location,
            publisher='Microsoft.ManagedIdentity',
            virtual_machine_extension_type='ManagedIdentityExtensionForLinux',
            type_handler_version='1.0',
            auto_upgrade_minor_version=True,
            settings={
                'port': 50342,
            },
        ),
    )


def delete_virtual_machine(compute_client, rg_name, vm_name):
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


def delete_network_interface(network_client, rg_name, nic_name):
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


def delete_network_security_group(network_client, rg_name, nsg_name):
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


def delete_public_ip(network_client, rg_name, pip_name):
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


def delete_subnet(network_client, rg_name, vnet_name, subnet_name):
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


def delete_virtual_network(network_client, rg_name, vnet_name):
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


def deallocate_virtual_machine(compute_client, rg_name, vm_name):
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


def get_ssh_info(
        compute_client, network_client, vm_res, ssh_key_prefix=None, nic=None,
        pip=None):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource, str, networkmodes.NetworkInterface,
    #        networkmodels.PublicIPAddress) ->
    #        Tuple[pathlib.Path, int, str, str]
    """Get SSH info to a federation proxy
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_res: resource
    :param str ssh_key_prefix: ssh key prefix
    :param networkmodels.NetworkInterface nic: network interface
    :param networkmodels.PublicIPAddress pip: public ip
    :rtype: tuple
    :return (ssh private key, port, username, ip)
    """
    vm_name = settings.generate_virtual_machine_name(vm_res, 0)
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=vm_res.resource_group,
            vm_name=vm_name,
        )
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            raise RuntimeError('virtual machine {} not found'.format(vm_name))
        else:
            raise
    # get connection ip
    if vm_res.public_ip.enabled:
        # get pip connected to vm
        if pip is None:
            _, pip = get_nic_and_pip_from_virtual_machine(
                network_client, vm_res.resource_group, vm)
        ip_address = pip.ip_address
    else:
        if nic is None:
            nic, _ = get_nic_and_pip_from_virtual_machine(
                network_client, vm_res.resource_group, vm)
        ip_address = nic.ip_configurations[0].private_ip_address
    # return connection info for vm
    if vm_res.ssh.ssh_private_key is not None:
        ssh_priv_key = vm_res.ssh.ssh_private_key
    else:
        ssh_priv_key = pathlib.Path(
            vm_res.ssh.generated_file_export_path, ssh_key_prefix)
    if not ssh_priv_key.exists():
        raise RuntimeError('SSH private key file not found at: {}'.format(
            ssh_priv_key))
    return ssh_priv_key, 22, vm.os_profile.admin_username, ip_address


def ssh_to_virtual_machine_resource(
        compute_client, network_client, vm_res, ssh_key_prefix, tty, command):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        settings.VmResource, str, bool, tuple) -> None
    """SSH to a node
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param settings.VmResource vm_res: resource
    :param str ssh_key_prefix: ssh key prefix
    :param bool tty: allocate pseudo-tty
    :param tuple command: command to execute
    """
    ssh_priv_key, port, username, ip = get_ssh_info(
        compute_client, network_client, vm_res, ssh_key_prefix=ssh_key_prefix)
    crypto.connect_or_exec_ssh_command(
        ip, port, ssh_priv_key, username, tty=tty, command=command)


def suspend_virtual_machine_resource(
        compute_client, config, vm_res, wait=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict,
    #        settings.VmResource, bool) -> None
    """Suspend a monitoring resource
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param settings.VmResource vm_res: resource
    :param bool wait: wait for suspension to complete
    """
    vm_name = settings.generate_virtual_machine_name(vm_res, 0)
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=vm_res.resource_group,
            vm_name=vm_name,
        )
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            logger.error('virtual machine {} not found'.format(vm_name))
            return
        else:
            raise
    if not util.confirm_action(
            config, 'suspend virtual machine resource {}'.format(vm.name)):
        return
    # deallocate vm
    async_op = AsyncOperation(functools.partial(
        deallocate_virtual_machine, compute_client,
        vm_res.resource_group, vm.name), retry_conflict=True)
    if wait:
        logger.info('waiting for virtual machine {} to deallocate'.format(
            vm.name))
        async_op.result()
        logger.info('virtual machine {} deallocated'.format(vm.name))


def start_virtual_machine(compute_client, rg_name, vm_name):
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


def start_virtual_machine_resource(
        compute_client, config, vm_res, wait=False):
    # type: (azure.mgmt.compute.ComputeManagementClient, dict,
    #        settings.VmResource, bool) -> None
    """Starts a suspended virtual machine resource
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    :param settings.VmResource vm_res: resource
    :param bool wait: wait for restart to complete
    """
    vm_name = settings.generate_virtual_machine_name(vm_res, 0)
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=vm_res.resource_group,
            vm_name=vm_name,
        )
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            logger.error('virtual machine {} not found'.format(vm_name))
            return
        else:
            raise
    if not util.confirm_action(
            config, 'start suspended virtual machine resource {}'.format(
                vm.name)):
        return
    # start vm
    async_op = AsyncOperation(functools.partial(
        start_virtual_machine, compute_client,
        vm_res.resource_group, vm.name))
    if wait:
        logger.info('waiting for virtual machine {} to start'.format(
            vm.name))
        async_op.result()
        logger.info('virtual machine {} started'.format(vm.name))


def stat_virtual_machine_resource(
        compute_client, network_client, config, vm_res):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient, dict,
    #        settings.VmResource) -> None
    """Retrieve status of a virtual machine resource
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param dict config: configuration dict
    :param settings.VmResource vm_res: resource
    """
    # retrieve all vms
    vm_name = settings.generate_virtual_machine_name(vm_res, 0)
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=vm_res.resource_group,
            vm_name=vm_name,
            expand=compute_client.virtual_machines.models.
            InstanceViewTypes.instance_view,
        )
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            logger.error('virtual machine {} not found'.format(vm_name))
            return
        else:
            raise
    # fetch vm status
    vmstatus = {}
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
    nic, pip = get_nic_and_pip_from_virtual_machine(
        network_client, vm_res.resource_group, vm)
    # get resource names (pass cached data to prevent another lookup)
    _, _, subnet, vnet, nsg = \
        get_resource_names_from_virtual_machine(
            compute_client, network_client, vm_res, vm, nic=nic, pip=pip)
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
    log = '{}'.format(json.dumps(vmstatus, sort_keys=True, indent=4))
    if settings.raw(config):
        print(log)
    else:
        logger.info('virtual machine resource status:{}{}'.format(
            os.linesep, log))
