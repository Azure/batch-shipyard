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
import logging
# non-stdlib imports
import azure.mgmt.network.models as networkmodels
import azure.mgmt.resource.resources.models as rgmodels
import msrest.exceptions
import msrestazure.azure_exceptions
# local imports
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)


class AsyncOperation(object):
    """Async Operation handler with automatic retry"""
    def __init__(
            self, partial, max_retries=-1, auto_invoke=True,
            retry_notfound=False):
        """Ctor for AsyncOperation
        :param AsyncOperation self: this
        :param functools.partial partial: partial object
        :param int max_retries: maximum number of retries before giving up
        :param bool auto_invoke: automatically invoke the async operation
        :param bool retry_notfound: retry on not found (404) errors
        """
        self._partial = partial
        self._retry_count = 0
        self._max_retries = max_retries
        self._retry_notfound = retry_notfound
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
        while True:
            if self._noop:
                return self._op  # will return None
            self._invoke()
            try:
                return self._op.result()
            except (msrest.exceptions.ClientException,
                    msrestazure.azure_exceptions.CloudError) as e:
                if e.status_code == 404 and not self._retry_notfound:
                    raise
                self._retry_count += 1
                if (self._max_retries >= 0 and
                        self._retry_count > self._max_retries):
                    logger.error(
                        ('Ran out of retry attempts invoking {}(args={} '
                         'kwargs={})').format(
                             self._partial.func.__name__, self._partial.args,
                             self._partial.keywords))
                    raise
            self._op = None
            logger.debug(
                ('Attempting retry of operation: {}, retry_count={} '
                 'max_retries={}').format(
                     self._partial.func.__name__, self._retry_count,
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
    pip_id = nic.ip_configurations[0].public_ip_address.id
    tmp = pip_id.split('/')
    if tmp[-2] != 'publicIPAddresses':
        raise RuntimeError('could not parse public ip address id')
    pip_name = tmp[-1]
    pip = network_client.public_ip_addresses.get(
        resource_group_name=resource_group,
        public_ip_address_name=pip_name,
    )
    return (nic, pip)
