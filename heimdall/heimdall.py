#!/usr/bin/env python3

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

# stdlib imports
import argparse
import asyncio
import hashlib
import json
import logging
import logging.handlers
import pathlib
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Tuple,
)
# non-stdlib imports
import azure.batch
import azure.batch.models as batchmodels
import azure.cosmosdb.table
import azure.mgmt.compute
import azure.mgmt.network
import azure.mgmt.resource
import azure.mgmt.storage
import msrestazure.azure_active_directory
import msrestazure.azure_cloud

# create logger
logger = logging.getLogger(__name__)
# global defines
_BATCH_SHIPYARD_VERSION = None
_BATCH_CLIENTS = {}
_VALID_NODE_STATES = frozenset((
    batchmodels.ComputeNodeState.idle,
    batchmodels.ComputeNodeState.offline,
    batchmodels.ComputeNodeState.running,
    batchmodels.ComputeNodeState.starting,
    batchmodels.ComputeNodeState.start_task_failed,
    batchmodels.ComputeNodeState.waiting_for_start_task,
))
_MONITOR_BATCHPOOL_PK = 'BatchPool'
_MONITOR_REMOTEFS_PK = 'RemoteFS'


def _setup_logger() -> None:
    # type: (None) -> None
    """Set up logger"""
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)sZ %(levelname)s %(name)s:%(funcName)s:%(lineno)d '
        '%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def is_none_or_empty(obj):
    # type: (any) -> bool
    """Determine if object is None or empty
    :type any obj: object
    :rtype: bool
    :return: if object is None or empty
    """
    return obj is None or len(obj) == 0


def is_not_empty(obj):
    # type: (any) -> bool
    """Determine if object is not None and is length is > 0
    :type any obj: object
    :rtype: bool
    :return: if object is not None and length is > 0
    """
    return obj is not None and len(obj) > 0


def convert_cloud_type(cloud_type: str) -> msrestazure.azure_cloud.Cloud:
    """Convert clout type string to object
    :param cloud_type: cloud type to convert
    :return: cloud object
    """
    if cloud_type == 'public':
        cloud = msrestazure.azure_cloud.AZURE_PUBLIC_CLOUD
    elif cloud_type == 'china':
        cloud = msrestazure.azure_cloud.AZURE_CHINA_CLOUD
    elif cloud_type == 'germany':
        cloud = msrestazure.azure_cloud.AZURE_GERMAN_CLOUD
    elif cloud_type == 'usgov':
        cloud = msrestazure.azure_cloud.AZURE_US_GOV_CLOUD
    else:
        raise ValueError('unknown cloud_type: {}'.format(cloud_type))
    return cloud


def create_msi_credentials(
        cloud: msrestazure.azure_cloud.Cloud,
        resource_id: str=None
) -> msrestazure.azure_active_directory.MSIAuthentication:
    """Create MSI credentials
    :param cloud: cloud kind
    :param resource_id: resource id to auth against
    :return: MSI auth object
    """
    if is_not_empty(resource_id):
        creds = msrestazure.azure_active_directory.MSIAuthentication(
            cloud_environment=cloud,
            resource=resource_id,
        )
    else:
        creds = msrestazure.azure_active_directory.MSIAuthentication(
            cloud_environment=cloud,
        )
    return creds


def _modify_client_for_retry_and_user_agent(client: Any) -> None:
    """Extend retry policy of clients and add user agent string
    :param client: a client object
    """
    if client is None:
        return
    client.config.retry_policy.max_backoff = 8
    client.config.retry_policy.retries = 20
    client.config.add_user_agent('batch-shipyard/{}'.format(
        _BATCH_SHIPYARD_VERSION))


def get_subscription_id(
        arm_creds: msrestazure.azure_active_directory.MSIAuthentication
) -> str:
    """Get subscription id for ARM creds
    :param arm_creds: ARM creds
    :return: subscription id
    """
    client = azure.mgmt.resource.SubscriptionClient(arm_creds)
    return next(client.subscriptions.list()).subscription_id


def _get_storage_account_key(
        cloud: msrestazure.azure_cloud.Cloud,
        arm_creds: msrestazure.azure_active_directory.MSIAuthentication,
        sub_id: str,
        storage_account: str,
        resource_group: str
) -> Tuple[str, str]:
    """Retrieve the storage account key and endpoint
    :param cloud: cloud object
    :param arm_creds: ARM creds
    :param sub_id: subscription id
    :param storage_account: storage account name
    :param resource_group: resource group
    :return: tuple of key, endpoint
    """
    client = azure.mgmt.storage.StorageManagementClient(
        arm_creds, sub_id, base_url=cloud.endpoints.resource_manager)
    ep = None
    if is_not_empty(resource_group):
        acct = client.storage_accounts.get_properties(
            resource_group, storage_account)
        ep = '.'.join(
            acct.primary_endpoints.blob.rstrip('/').split('.')[2:]
        )
    else:
        for acct in client.storage_accounts.list():
            if acct.name == storage_account:
                resource_group = acct.id.split('/')[4]
                ep = '.'.join(
                    acct.primary_endpoints.blob.rstrip('/').split('.')[2:]
                )
                break
    if is_none_or_empty(resource_group) or is_none_or_empty(ep):
        raise RuntimeError(
            'storage account {} not found in subscription id {}'.format(
                storage_account, sub_id))
    keys = client.storage_accounts.list_keys(resource_group, storage_account)
    return (keys.keys[0].value, ep)


def create_table_client(
        cloud: msrestazure.azure_cloud.Cloud,
        arm_creds: msrestazure.azure_active_directory.MSIAuthentication,
        sub_id: str,
        storage_account: str,
        resource_group: str
) -> azure.cosmosdb.table.TableService:
    """Create a table client for the given storage account
    :param cloud: cloud object
    :param arm_creds: ARM creds
    :param sub_id: subscription id
    :param storage_account: storage account name
    :param resource_group: resource group
    :return: table client
    """
    key, ep = _get_storage_account_key(
        cloud, arm_creds, sub_id, storage_account, resource_group)
    return azure.cosmosdb.table.TableService(
        account_name=storage_account,
        account_key=key,
        endpoint_suffix=ep,
    )


def create_compute_client(
        cloud: msrestazure.azure_cloud.Cloud,
        arm_creds: msrestazure.azure_active_directory.MSIAuthentication,
        sub_id: str,
        resource_group: str
) -> azure.mgmt.compute.ComputeManagementClient:
    """Create a compute mgmt client
    :param cloud: cloud object
    :param arm_creds: ARM creds
    :param sub_id: subscription id
    :param resource_group: resource group
    :return: compute client
    """
    client = azure.mgmt.compute.ComputeManagementClient(
        arm_creds, sub_id, base_url=cloud.endpoints.resource_manager)
    _modify_client_for_retry_and_user_agent(client)
    return client


def create_network_client(
        cloud: msrestazure.azure_cloud.Cloud,
        arm_creds: msrestazure.azure_active_directory.MSIAuthentication,
        sub_id: str,
        resource_group: str
) -> azure.mgmt.network.NetworkManagementClient:
    """Create a network mgmt client
    :param cloud: cloud object
    :param arm_creds: ARM creds
    :param sub_id: subscription id
    :param resource_group: resource group
    :return: network client
    """
    client = azure.mgmt.network.NetworkManagementClient(
        arm_creds, sub_id, base_url=cloud.endpoints.resource_manager)
    _modify_client_for_retry_and_user_agent(client)
    return client


def _get_batch_credentials(
        cloud: msrestazure.azure_cloud.Cloud,
        resource_id: str,
        batch_account: str,
        service_url: str
) -> azure.batch.BatchServiceClient:
    """Get/create batch creds
    :param cloud: cloud object
    :param resource_id: resource id
    :param batch_account: batch account name
    :param service_url: service url
    :return: batch client
    """
    global _BATCH_CLIENTS
    try:
        return _BATCH_CLIENTS[batch_account]
    except KeyError:
        creds = create_msi_credentials(cloud, resource_id=resource_id)
        client = azure.batch.BatchServiceClient(creds, base_url=service_url)
        _modify_client_for_retry_and_user_agent(client)
        _BATCH_CLIENTS[batch_account] = client
        logger.debug('batch client created for account: {}'.format(
            batch_account))
        return client


def _construct_batch_monitoring_list(
        batch_client: azure.batch.BatchServiceClient,
        poolid: str
) -> List[Dict]:
    """Construct the batch pool monitoring list
    :param batch_client: batch client
    :param poolid: pool id
    """
    logger.debug('querying batch pool: {}'.format(poolid))
    # first retrieve node exporter and cadvisor ports
    try:
        pool = batch_client.pool.get(
            poolid,
            pool_get_options=batchmodels.PoolGetOptions(
                select='id,state,startTask',
            ),
        )
    except batchmodels.BatchErrorException as e:
        logger.error(e.message)
        return None
    if pool.state == batchmodels.PoolState.deleting:
        logger.debug('pool {} is being deleted, ignoring'.format(pool.id))
        return None
    ne_port = None
    ca_port = None
    for es in pool.start_task.environment_settings:
        if es.name == 'PROM_NODE_EXPORTER_PORT':
            ne_port = int(es.value)
        elif es.name == 'PROM_CADVISOR_PORT':
            ca_port = int(es.value)
        if ne_port is not None and ca_port is not None:
            break
    logger.debug('pool {} state={} ne_port={} ca_port={}'.format(
        pool.id, pool.state, ne_port, ca_port))
    # get node list
    nodelist = []
    try:
        nodes = batch_client.compute_node.list(
            poolid,
            compute_node_list_options=batchmodels.ComputeNodeListOptions(
                select='id,state,ipAddress',
            ),
        )
        for node in nodes:
            logger.debug('compute node {} state={} ipaddress={}'.format(
                node.id, node.state.value, node.ip_address))
            if node.state in _VALID_NODE_STATES:
                nodelist.append(node)
    except batchmodels.BatchErrorException as e:
        logger.error(e.message)
        return None
    if is_none_or_empty(nodelist):
        logger.info('no viable nodes found in pool: {}'.format(poolid))
        return None
    logger.info('monitoring {} nodes for pool: {}'.format(
        len(nodelist), poolid))
    # construct prometheus targets
    targets = []
    if ne_port is not None:
        targets.append(
            {
                'targets': [
                    '{}:{}'.format(x.ip_address, ne_port) for x in nodelist
                ],
                'labels': {
                    'env': _MONITOR_BATCHPOOL_PK,
                    'collector': 'NodeExporter',
                    'job': '{}'.format(poolid)
                }
            }
        )
    if ca_port is not None:
        targets.append(
            {
                'targets': [
                    '{}:{}'.format(x.ip_address, ca_port) for x in nodelist
                ],
                'labels': {
                    'env': _MONITOR_BATCHPOOL_PK,
                    'collector': 'cAdvisor',
                    'job': '{}'.format(poolid)
                }
            }
        )
    return targets


def _construct_pool_monitoring_targets(
        cloud: msrestazure.azure_cloud.Cloud,
        table_client: azure.cosmosdb.table.TableService,
        table_name: str,
        pool_targets_file: pathlib.Path,
        last_hash: bytes
) -> bytes:
    """Read table for pool monitoring
    :param cloud: cloud object
    :param table_client: table client
    :param table_name: table name
    :param pool_targets_file: prom pool targets
    :param last_hash: last SHA256 digest of pool targets
    :returned: hashed target dict
    """
    targets = []
    entities = table_client.query_entities(
        table_name,
        filter='PartitionKey eq \'{}\''.format(_MONITOR_BATCHPOOL_PK))
    for entity in entities:
        batch_account, poolid = entity['RowKey'].split('$')
        logger.debug('{} entity read for account={} poolid={}'.format(
            _MONITOR_BATCHPOOL_PK, batch_account, poolid))
        client = _get_batch_credentials(
            cloud, entity['AadEndpoint'], batch_account,
            entity['BatchServiceUrl'])
        pt = _construct_batch_monitoring_list(client, poolid)
        if is_not_empty(pt):
            targets.extend(pt)
    ret = None
    if is_none_or_empty(targets):
        logger.debug('no prometheus targets for pools found')
        try:
            pool_targets_file.unlink()
        except OSError:
            pass
    else:
        output = json.dumps(
            targets, ensure_ascii=False, sort_keys=True).encode('utf8')
        sha = hashlib.sha256()
        sha.update(output)
        ret = sha.digest()
        if ret != last_hash:
            logger.debug('prometheus targets for pools: {}'.format(targets))
            with pool_targets_file.open('wb') as f:
                f.write(output)
        else:
            logger.debug('prometheus targets for pools unchanged')
    return ret


def _get_private_ip_from_vm_name(
        compute_client: azure.mgmt.compute.ComputeManagementClient,
        network_client: azure.mgmt.network.NetworkManagementClient,
        vm_rg: str,
        vm_name: str) -> str:
    """Get private ip address from vm name
    :param compute_client: compute client
    :param network_client: network client
    :param str vm_rg: resource group name
    :param str vm_name: vm name
    :return: private ip
    """
    vm = compute_client.virtual_machines.get(
        resource_group_name=vm_rg,
        vm_name=vm_name,
        expand=compute_client.virtual_machines.models.
        InstanceViewTypes.instance_view,
    )
    nic_id = vm.network_profile.network_interfaces[0].id
    tmp = nic_id.split('/')
    if tmp[-2] != 'networkInterfaces':
        logger.error('could not parse network interface id')
        return None
    nic_name = tmp[-1]
    nic = network_client.network_interfaces.get(
        resource_group_name=vm_rg,
        network_interface_name=nic_name,
    )
    return nic.ip_configurations[0].private_ip_address


def _construct_remotefs_monitoring_list(
        compute_client: azure.mgmt.compute.ComputeManagementClient,
        network_client: azure.mgmt.network.NetworkManagementClient,
        sc_id: str,
        entity: Dict
) -> List[Dict]:
    """Construct the remotefs monitoring list
    :param compute_client: compute client
    :param network_client: network client
    :param sc_id: storage cluster id
    :param entity: entity
    """
    nodelist = []
    ne_port = int(entity['NodeExporterPort'])
    fstype = entity['Type']
    vms = json.loads(entity['VMs'])
    logger.debug('remotefs {} type={} ne_port={} num_vms={}'.format(
        sc_id, fstype, ne_port, len(vms)))
    if fstype == 'nfs':
        vm_rg = entity['ResourceGroup']
        vm_name = vms[0]
        pip = _get_private_ip_from_vm_name(
            compute_client, network_client, vm_rg, vm_name)
        if pip is not None:
            nodelist.append(pip)
    elif fstype == 'glusterfs':
        rg = entity['ResourceGroup']
        avset = compute_client.availability_sets.get(
            rg, entity['AvailabilitySet'])
        for sr in avset.virtual_machines:
            tmp = sr.id.split('/')
            vm_rg = tmp[4].lower()
            vm_name = tmp[8].lower()
            pip = _get_private_ip_from_vm_name(
                compute_client, network_client, vm_rg, vm_name)
            if pip is not None:
                nodelist.append(pip)
    else:
        logger.error('unknown fstype {}'.format(fstype))
    if is_none_or_empty(nodelist):
        logger.info('no viable nodes found in remotefs: {}'.format(sc_id))
        return None
    logger.info('monitoring {} nodes for remotefs: {}'.format(
        len(nodelist), sc_id))
    # construct prometheus targets
    targets = []
    if ne_port is not None:
        targets.append(
            {
                'targets': [
                    '{}:{}'.format(x, ne_port) for x in nodelist
                ],
                'labels': {
                    'env': _MONITOR_REMOTEFS_PK,
                    'collector': 'NodeExporter',
                    'job': '{}'.format(sc_id)
                }
            }
        )
    return targets


def _construct_remotefs_monitoring_targets(
        cloud: msrestazure.azure_cloud.Cloud,
        table_client: azure.cosmosdb.table.TableService,
        compute_client: azure.mgmt.compute.ComputeManagementClient,
        network_client: azure.mgmt.network.NetworkManagementClient,
        table_name: str,
        remotefs_targets_file: pathlib.Path,
        last_hash: bytes
) -> bytes:
    """Read table for remotefs monitoring
    :param cloud: cloud object
    :param table_client: table client
    :param compute_client: compute client
    :param network_client: network client
    :param table_name: table name
    :param remotefs_targets_file: prom remotefs targets
    :param last_hash: last SHA256 digest of remotefs targets
    :returned: hashed target dict
    """
    targets = []
    entities = table_client.query_entities(
        table_name,
        filter='PartitionKey eq \'{}\''.format(_MONITOR_REMOTEFS_PK))
    for entity in entities:
        sc_id = entity['RowKey']
        logger.debug('{} entity read for sc_id={}'.format(
            _MONITOR_REMOTEFS_PK, sc_id))
        rfst = _construct_remotefs_monitoring_list(
            compute_client, network_client, sc_id, entity)
        if is_not_empty(rfst):
            targets.extend(rfst)
    ret = None
    if is_none_or_empty(targets):
        logger.debug('no prometheus targets for remotefs found')
        try:
            remotefs_targets_file.unlink()
        except OSError:
            pass
    else:
        output = json.dumps(
            targets, ensure_ascii=False, sort_keys=True).encode('utf8')
        sha = hashlib.sha256()
        sha.update(output)
        ret = sha.digest()
        if ret != last_hash:
            logger.debug('prometheus targets for remotefs: {}'.format(targets))
            with remotefs_targets_file.open('wb') as f:
                f.write(output)
        else:
            logger.debug('prometheus targets for remotefs unchanged')
    return ret


async def poll_for_monitoring_changes(
    loop: asyncio.BaseEventLoop,
    config: Dict,
    cloud: msrestazure.azure_cloud.Cloud,
    table_client: azure.cosmosdb.table.TableService,
    compute_client: azure.mgmt.compute.ComputeManagementClient,
    network_client: azure.mgmt.network.NetworkManagementClient
) -> Generator[None, None, None]:
    """Poll for monitoring changes
    :param loop: asyncio loop
    :param config: configuration
    :param cloud: cloud object
    :param table_client: table client
    :param compute_client: compute client
    :param network_client: network client
    """
    polling_interval = config.get('polling_interval', 10)
    table_name = config['storage']['table_name']
    prom_var_dir = config['prometheus_var_dir']
    pool_targets_file = pathlib.Path(prom_var_dir) / 'batch_pools.json'
    remotefs_targets_file = pathlib.Path(prom_var_dir) / 'remotefs.json'
    logger.debug('polling table {} every {} sec'.format(
        table_name, polling_interval))
    last_pool_hash = None
    last_remotefs_hash = None
    while True:
        last_pool_hash = _construct_pool_monitoring_targets(
            cloud, table_client, table_name, pool_targets_file, last_pool_hash)
        last_remotefs_hash = _construct_remotefs_monitoring_targets(
            cloud, table_client, compute_client, network_client, table_name,
            remotefs_targets_file, last_remotefs_hash)
        await asyncio.sleep(polling_interval)


def main() -> None:
    """Main function"""
    global _BATCH_SHIPYARD_VERSION
    # get command-line args
    args = parseargs()
    # load configuration
    if is_none_or_empty(args.conf):
        raise ValueError('config file not specified')
    with open(args.conf, 'rb') as f:
        config = json.load(f)
    logger.debug('loaded config: {}'.format(config))
    _BATCH_SHIPYARD_VERSION = config['batch_shipyard_version']
    # convert cloud type
    cloud = convert_cloud_type(config['aad_cloud'])
    # get resource manager aad creds
    arm_creds = create_msi_credentials(cloud)
    # get subscription id
    sub_id = get_subscription_id(arm_creds)
    logger.debug('created msi auth for sub id: {}'.format(sub_id))
    # create clients
    table_client = create_table_client(
        cloud, arm_creds, sub_id, config['storage']['account'],
        config['storage']['resource_group'])
    compute_client = create_compute_client(
        cloud, arm_creds, sub_id, config['storage']['resource_group'])
    network_client = create_network_client(
        cloud, arm_creds, sub_id, config['storage']['resource_group'])
    # run the poller
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        poll_for_monitoring_changes(
            loop, config, cloud, table_client, compute_client, network_client
        )
    )


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='heimdall: Azure Batch Shipyard Dynamic Monitor')
    parser.add_argument('--conf', help='configuration file')
    return parser.parse_args()


if __name__ == '__main__':
    _setup_logger()
    main()
