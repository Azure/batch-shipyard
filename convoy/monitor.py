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
import time
import uuid
# non-stdlib imports
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


def _create_virtual_machine_extension(
        compute_client, config, vm_resource, bootstrap_file, blob_urls,
        vm_name, private_ips, fqdn, offset, verbose=False):
    # type: (azure.mgmt.compute.ComputeManagementClient,
    #        settings.VmResource, str, List[str], str, List[str], str,
    #        int, bool) -> msrestazure.azure_operation.AzureOperationPoller
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
    :param bool verbose: verbose logging
    :rtype: msrestazure.azure_operation.AzureOperationPoller
    :return: msrestazure.azure_operation.AzureOperationPoller
    """
    # construct vm extensions
    vm_ext_name = settings.generate_virtual_machine_extension_name(
        vm_resource, offset)
    # try to get storage account resource group
    ssel = settings.batch_shipyard_settings(config).storage_account_settings
    rg = settings.credentials_storage(config, ssel).resource_group
    # get services config
    servconf = settings.monitoring_services_settings(config)
    # construct bootstrap command
    cmd = './{bsf}{a}{d}{f}{le}{p}{s}{v}'.format(
        bsf=bootstrap_file[0],
        a=' -a {}'.format(settings.determine_cloud_type_from_aad(config)),
        d=' -d {}'.format(fqdn) if util.is_not_empty(fqdn) else '',
        f=' -f' if servconf.lets_encrypt_staging else '',
        le=' -l' if servconf.lets_encrypt_enabled else '',
        p=' -p {}'.format(servconf.resource_polling_interval),
        s=' -s {}:{}:{}'.format(
            storage.get_storageaccount(),
            storage.get_storage_table_monitoring(),
            rg if util.is_not_empty(rg) else '',
        ),
        v=' -v {}'.format(__version__),
    )
    if verbose:
        logger.debug('bootstrap command: {}'.format(cmd))
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
                'storageAccountName': storage.get_storageaccount(),
                'storageAccountKey': storage.get_storageaccount_key(),
            },
        ),
    )


def create_monitoring_resource(
        auth_client, resource_client, compute_client, network_client,
        blob_client, table_client, config, resources_path, bootstrap_file,
        monitoring_files):
    # type: (azure.mgmt.authorization.AuthorizationManagementClient,
    #        azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService,
    #        dict, str, pathlib.Path, Tuple[str, pathlib.Path],
    #        List[Tuple[str, pathlib.Path]]) -> None
    """Create a monitoring resource
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
    :param List[Tuple[str, pathlib.Path]] monitoring_files:
        configurable monitoring files
    """
    ms = settings.monitoring_settings(config)
    # get subscription id for msi
    sub_id = settings.credentials_management(config).subscription_id
    if util.is_none_or_empty(sub_id):
        raise ValueError('Management subscription id not specified')
    # check if cluster already exists
    logger.debug('checking if monitoring resource exists')
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=ms.resource_group,
            vm_name=settings.generate_virtual_machine_name(ms, 0)
        )
        raise RuntimeError(
            'Existing virtual machine {} found for monitoring'.format(vm.id))
    except msrestazure.azure_exceptions.CloudError as e:
        if e.status_code == 404:
            pass
        else:
            raise
    # confirm before proceeding
    if not util.confirm_action(config, 'create monitoring resource'):
        return
    # create resource group if it doesn't exist
    resource.create_resource_group(
        resource_client, ms.resource_group, ms.location)
    # check for conflicting options
    servconf = settings.monitoring_services_settings(config)
    if servconf.lets_encrypt_enabled and not ms.public_ip.enabled:
        raise ValueError(
            'cannot create a monitoring resource without a public ip and '
            'lets encrypt enabled')
    # create storage container
    storage.create_storage_containers_nonbatch(
        blob_client, table_client, None, 'monitoring')
    # configure yaml files and write to resources
    if servconf.lets_encrypt_enabled and ms.public_ip.enabled:
        with monitoring_files['compose'][1].open('r') as f:
            compdata = f.read()
    else:
        with monitoring_files['compose-nonginx'][1].open('r') as f:
            compdata = f.read()
    with monitoring_files['prometheus'][1].open('r') as f:
        promdata = f.read()
    with monitoring_files['nginx'][1].open('r') as f:
        nginxdata = f.read()
    compdata = compdata.replace(
        '{GRAFANA_ADMIN_USER}', servconf.grafana.admin_user).replace(
            '{GRAFANA_ADMIN_PASSWORD}', servconf.grafana.admin_password)
    if servconf.prometheus.port is not None:
        if servconf.lets_encrypt_enabled and ms.public_ip.enabled:
            compdata = compdata.replace(
                '{PROMETHEUS_PORT}', '- "{p}:{p}"'.format(
                    p=servconf.prometheus.port))
            nginxdata = nginxdata.replace(
                '{PROMETHEUS_PORT}', servconf.prometheus.port)
        else:
            compdata = compdata.replace(
                '{PROMETHEUS_PORT}', servconf.prometheus.port)
    else:
        if servconf.lets_encrypt_enabled and ms.public_ip.enabled:
            compdata = compdata.replace('{PROMETHEUS_PORT}', '')
            nginxdata = nginxdata.replace('{PROMETHEUS_PORT}', '9090')
        else:
            compdata = compdata.replace('{PROMETHEUS_PORT}', '9090')
    promdata = promdata.replace(
        '{PROMETHEUS_SCRAPE_INTERVAL}', servconf.prometheus.scrape_interval)
    compyml = resources_path / monitoring_files['compose'][0]
    promyml = resources_path / monitoring_files['prometheus'][0]
    nginxconf = resources_path / monitoring_files['nginx'][0]
    with compyml.open('wt') as f:
        f.write(compdata)
    with promyml.open('wt') as f:
        f.write(promdata)
    with nginxconf.open('wt') as f:
        f.write(nginxdata)
    del compdata
    del promdata
    del nginxdata
    monitoring_files = [
        bootstrap_file,
        monitoring_files['dashboard'],
        (monitoring_files['compose'][0], compyml),
        (monitoring_files['prometheus'][0], promyml),
        (monitoring_files['nginx'][0], nginxconf),
    ]
    add_dash = None
    if util.is_not_empty(servconf.grafana.additional_dashboards):
        add_dash = resources_path / 'additional_dashboards.txt'
        with add_dash.open('wt') as f:
            for key in servconf.grafana.additional_dashboards:
                f.write('{},{}\n'.format(
                    key, servconf.grafana.additional_dashboards[key]))
        monitoring_files.append((add_dash.name, add_dash))
    # upload scripts to blob storage for customscript vm extension
    blob_urls = storage.upload_for_nonbatch(
        blob_client, monitoring_files, 'monitoring')
    try:
        compyml.unlink()
    except OSError:
        pass
    try:
        promyml.unlink()
    except OSError:
        pass
    try:
        nginxconf.unlink()
    except OSError:
        pass
    if add_dash is not None:
        try:
            add_dash.unlink()
        except OSError:
            pass
    # async operation dictionary
    async_ops = {}
    # create nsg
    async_ops['nsg'] = resource.AsyncOperation(functools.partial(
        resource.create_network_security_group, network_client, ms))
    # use dynamic ips for private
    private_ips = None
    logger.debug('using dynamic private ip address allocation')
    # create virtual network and subnet if specified
    vnet, subnet = resource.create_virtual_network_and_subnet(
        resource_client, network_client,
        ms.virtual_network.resource_group, ms.location,
        ms.virtual_network)
    # create public ips
    pips = None
    if ms.public_ip.enabled:
        async_ops['pips'] = {}
        async_ops['pips'][0] = resource.AsyncOperation(functools.partial(
            resource.create_public_ip, network_client, ms, 0))
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
        logger.info('public ip is disabled for monitoring resource')
    # get nsg
    logger.debug('waiting for network security group to provision')
    nsg = async_ops['nsg'].result()
    # create nics
    async_ops['nics'] = {}
    async_ops['nics'][0] = resource.AsyncOperation(functools.partial(
        resource.create_network_interface, network_client, ms, subnet, nsg,
        private_ips, pips, 0))
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
    if util.is_not_empty(ms.ssh.ssh_public_key_data):
        key_data = ms.ssh.ssh_public_key_data
    else:
        # create universal ssh key for all vms if not specified
        ssh_pub_key = ms.ssh.ssh_public_key
        if ssh_pub_key is None:
            _, ssh_pub_key = crypto.generate_ssh_keypair(
                ms.ssh.generated_file_export_path,
                crypto.get_monitoring_ssh_key_prefix())
        # read public key data
        with ssh_pub_key.open('rb') as fd:
            key_data = fd.read().decode('utf8')
    ssh_pub_key = compute_client.virtual_machines.models.SshPublicKey(
        path='/home/{}/.ssh/authorized_keys'.format(ms.ssh.username),
        key_data=key_data,
    )
    # create vms
    async_ops['vms'] = {}
    async_ops['vms'][0] = resource.AsyncOperation(functools.partial(
        resource.create_virtual_machine, compute_client, ms, None, nics,
        None, ssh_pub_key, 0, enable_msi=True))
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
            sub_scope, filter='roleName eq \'Reader\''):
        cont_role = role.id
        break
    if cont_role is None:
        raise RuntimeError('Role Id not found for Reader')
    # sometimes the sp created is not added to the directory in time for
    # the following call, allow some retries before giving up
    attempts = 0
    while attempts < 90:
        try:
            role_assign = auth_client.role_assignments.create(
                scope=sub_scope,
                role_assignment_name=uuid.uuid4(),
                parameters=authmodels.RoleAssignmentCreateParameters(
                    role_definition_id=cont_role,
                    principal_id=vms[0].identity.principal_id
                ),
            )
            break
        except msrestazure.azure_exceptions.CloudError:
            time.sleep(2)
            attempts += 1
            if attempts == 90:
                raise
    del attempts
    if settings.verbose(config):
        logger.debug('reader role assignment: {}'.format(role_assign))
    cont_role = None
    for role in auth_client.role_definitions.list(
            sub_scope, filter='roleName eq \'Reader and Data Access\''):
        cont_role = role.id
        break
    if cont_role is None:
        raise RuntimeError('Role Id not found for Reader and Data Access')
    role_assign = auth_client.role_assignments.create(
        scope=sub_scope,
        role_assignment_name=uuid.uuid4(),
        parameters=authmodels.RoleAssignmentCreateParameters(
            role_definition_id=cont_role,
            principal_id=vms[0].identity.principal_id
        ),
    )
    if settings.verbose(config):
        logger.debug('reader and data access role assignment: {}'.format(
            role_assign))
    # get ip info for vm
    if util.is_none_or_empty(pips):
        fqdn = None
        ipinfo = 'private_ip_address={}'.format(
            nics[offset].ip_configurations[0].private_ip_address)
    else:
        # refresh public ip for vm
        pip = network_client.public_ip_addresses.get(
            resource_group_name=ms.resource_group,
            public_ip_address_name=pips[offset].name,
        )
        fqdn = pip.dns_settings.fqdn
        ipinfo = 'fqdn={} public_ip_address={}'.format(fqdn, pip.ip_address)
        # temporary enable port 80 for ACME challenge if fqdn is present
        if servconf.lets_encrypt_enabled:
            isr = settings.InboundNetworkSecurityRule(
                destination_port_range='80',
                source_address_prefix='*',
                protocol='tcp',
            )
            logger.debug('creating temporary port 80 rule for ACME challenge')
            async_ops['port80'] = resource.AsyncOperation(functools.partial(
                resource.add_inbound_network_security_rule, network_client, ms,
                'acme80', isr))
    # ensure port 80 rule is ready
    if servconf.lets_encrypt_enabled and ms.public_ip.enabled:
        async_ops['port80'].result()
    # install vm extension
    async_ops['vmext'] = {}
    async_ops['vmext'][0] = resource.AsyncOperation(
        functools.partial(
            _create_virtual_machine_extension, compute_client, config, ms,
            bootstrap_file, blob_urls, vms[0].name,
            private_ips, fqdn, 0, settings.verbose(config)),
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
                vm.hardware_profile.vm_size, ipinfo))
    # disable port 80 for ACME challenge
    if servconf.lets_encrypt_enabled and ms.public_ip.enabled:
        logger.debug('removing temporary port 80 rule for ACME challenge')
        async_ops['port80'] = resource.AsyncOperation(functools.partial(
            resource.remove_inbound_network_security_rule, network_client, ms,
            'acme80'))
        async_ops['port80'].result()
    # output connection info
    if ms.public_ip.enabled:
        logger.info(
            ('To connect to Grafana, open a web browser and go '
             'to https://{}').format(fqdn))
        if servconf.prometheus.port is not None:
            logger.info(
                ('To connect to Prometheus, open a web browser and go '
                 'to https://{}:{}').format(fqdn, servconf.prometheus.port))
    else:
        logger.info(
            ('To connect to Grafana, open a web browser and go '
             'to http://{} within the virtual network').format(
                 nics[offset].ip_configurations[0].private_ip_address))
        if servconf.prometheus.port is not None:
            logger.info(
                ('To connect to Prometheus, open a web browser and go '
                 'to http://{}:{} within the virtual network').format(
                     nics[offset].ip_configurations[0].private_ip_address,
                     servconf.prometheus.port))


def delete_monitoring_resource(
        resource_client, compute_client, network_client, blob_client,
        table_client, config, delete_virtual_network=False,
        delete_resource_group=False, generate_from_prefix=False, wait=False):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient,
    #        azure.mgmt.network.NetworkManagementClient,
    #        azure.storage.blob.BlockBlobService,
    #        azure.cosmosdb.table.TableService,
    #        dict, bool, bool, bool, bool) -> None
    """Delete a resource monitor
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param azure.mgmt.network.NetworkManagementClient network_client:
        network client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool delete_virtual_network: delete vnet
    :param bool delete_resource_group: delete resource group
    :param bool generate_from_prefix: generate resources from hostname prefix
    :param bool wait: wait for completion
    """
    ms = settings.monitoring_settings(config)
    # delete rg if specified
    if delete_resource_group:
        if util.confirm_action(
                config, 'delete resource group {}'.format(
                    ms.resource_group)):
            logger.info('deleting resource group {}'.format(
                ms.resource_group))
            async_delete = resource_client.resource_groups.delete(
                resource_group_name=ms.resource_group)
            if wait:
                logger.debug('waiting for resource group {} to delete'.format(
                    ms.resource_group))
                async_delete.result()
                logger.info('resource group {} deleted'.format(
                    ms.resource_group))
        return
    if not util.confirm_action(config, 'delete monitoring resource'):
        return
    # get vms and cache for concurent async ops
    resources = {}
    i = 0
    vm_name = settings.generate_virtual_machine_name(ms, i)
    try:
        vm = compute_client.virtual_machines.get(
            resource_group_name=ms.resource_group,
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
                    'vm': settings.generate_virtual_machine_name(ms, i),
                    'as': None,
                    'nic': settings.generate_network_interface_name(ms, i),
                    'pip': settings.generate_public_ip_name(ms, i),
                    'subnet': None,
                    'nsg': settings.generate_network_security_group_name(ms),
                    'vnet': None,
                    'os_disk': None,
                }
        else:
            raise
    else:
        # get resources connected to vm
        nic, pip, subnet, vnet, nsg = \
            resource.get_resource_names_from_virtual_machine(
                compute_client, network_client, ms, vm)
        resources[i] = {
            'vm': vm.name,
            'arm_id': vm.id,
            'id': vm.vm_id,
            'nic': nic,
            'pip': pip,
            'subnet': subnet,
            'nsg': nsg,
            'vnet': vnet,
            'os_disk': vm.storage_profile.os_disk.name,
        }
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
        blob_client, table_client, None, 'monitoring')
    # create async op holder
    async_ops = {}
    # delete vms
    async_ops['vms'] = {}
    for key in resources:
        vm_name = resources[key]['vm']
        async_ops['vms'][vm_name] = resource.AsyncOperation(functools.partial(
            resource.delete_virtual_machine, compute_client,
            ms.resource_group, vm_name), retry_conflict=True)
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
                ms.resource_group, nic_name),
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
            resource_group=ms.resource_group, wait=False,
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
            ms.resource_group, nsg_name), retry_conflict=True)
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
                ms.resource_group, pip_name),
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
                ms.virtual_network.resource_group, vnet_name, subnet_name),
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
                ms.virtual_network.resource_group, vnet_name),
            retry_conflict=True
        )
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
