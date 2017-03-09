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
# non-stdlib imports
import azure.mgmt.network.models as networkmodels
import msrestazure.azure_exceptions
# local imports
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)


def create_virtual_network_and_subnet(
        network_client, resource_group, location, vnet_settings):
    # type: (azure.mgmt.network.NetworkManagementClient, str, str,
    #        settings.VirtualNetworkSettings) ->
    #        Tuple[networkmodels.VirtualNetwork, networkmodels.Subnet]
    """Create a Virtual network and subnet
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
        logger.info('creating virtual network: {}'.format(vnet_settings.name))
        async_create = network_client.virtual_networks.create_or_update(
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
        )
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
        async_create = network_client.subnets.create_or_update(
            resource_group_name=resource_group,
            virtual_network_name=vnet_settings.name,
            subnet_name=vnet_settings.subnet_name,
            subnet_parameters=networkmodels.Subnet(
                address_prefix=vnet_settings.subnet_address_prefix
            )
        )
        subnet = async_create.result()
    logger.info(
        ('virtual network: {} [provisioning_state={} address_space={} '
         'subnet={} address_prefix={}]').format(
             virtual_network.id, virtual_network.provisioning_state,
             virtual_network.address_space.address_prefixes,
             vnet_settings.subnet_name, subnet.address_prefix))
    return (virtual_network, subnet)
