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
import json
import logging
import logging.handlers
import pathlib
from typing import (
    Dict,
    Generator,
    List,
    Tuple,
)
# non-stdlib imports
import azure.batch
import azure.batch.models as batchmodels
import azure.cosmosdb.table
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
        client.config.add_user_agent('batch-shipyard/{}-picket'.format(
            _BATCH_SHIPYARD_VERSION))
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
    ipaddrlist = []
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
                ipaddrlist.append(node.ip_address)
    except batchmodels.BatchErrorException as e:
        logger.error(e.message)
        return None
    if is_none_or_empty(ipaddrlist):
        logger.info('no viable nodes found in pool: {}'.format(poolid))
        return None
    logger.info('monitoring ip address list for pool {}: {}'.format(
        poolid, ipaddrlist))
    # construct prometheus targets
    targets = []
    if ne_port is not None:
        targets.append(
            {
                'targets': ['{}:{}'.format(x, ne_port) for x in ipaddrlist],
                'labels': {
                    'env': 'BatchPool',
                    'collector': 'NodeExporter',
                    'job': '{}'.format(poolid)
                }
            }
        )
    if ca_port is not None:
        targets.append(
            {
                'targets': ['{}:{}'.format(x, ca_port) for x in ipaddrlist],
                'labels': {
                    'env': 'BatchPool',
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
        pool_targets_file: pathlib.Path
) -> None:
    """Read table for pool monitoring
    :param cloud: cloud object
    :param table_client: table client
    :param table_name: table name
    :param pool_targets_file: prom pool targets
    """
    targets = []
    entities = table_client.query_entities(
        table_name, filter='PartitionKey eq \'BatchPool\'')
    for entity in entities:
        batch_account, poolid = entity['RowKey'].split('$')
        logger.debug('BatchPool entity read for account={} poolid={}'.format(
            batch_account, poolid))
        client = _get_batch_credentials(
            cloud, entity['AadEndpoint'], batch_account,
            entity['BatchServiceUrl'])
        pt = _construct_batch_monitoring_list(client, poolid)
        if is_not_empty(pt):
            targets.extend(pt)
    if is_none_or_empty(targets):
        return
    logger.debug('prometheus targets for pools: {}'.format(targets))
    with pool_targets_file.open('w') as f:
        if is_not_empty(targets):
            json.dump(targets, f, indent=4, ensure_ascii=False)


async def poll_for_monitoring_changes(
    loop: asyncio.BaseEventLoop,
    config: Dict,
    cloud: msrestazure.azure_cloud.Cloud,
    table_client: azure.cosmosdb.table.TableService
) -> Generator[None, None, None]:
    """Poll for monitoring changes
    :param loop: asyncio loop
    :param config: configuration
    :param cloud: cloud object
    :param table_client: table client
    """
    table_name = config['storage']['table_name']
    prom_var_dir = config['prometheus_var_dir']
    pool_targets_file = pathlib.Path(prom_var_dir) / 'batch_pools.json'
    logger.debug('polling table: {}'.format(table_name))
    while True:
        _construct_pool_monitoring_targets(
            cloud, table_client, table_name, pool_targets_file)
        await asyncio.sleep(5)


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
    # create table client
    table_client = create_table_client(
        cloud, arm_creds, sub_id, config['storage']['account'],
        config['storage']['resource_group'])
    # run the poller
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        poll_for_monitoring_changes(loop, config, cloud, table_client)
    )


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='picket: Azure Batch Shipyard Dynamic Monitor')
    parser.add_argument('--conf', help='configuration file')
    return parser.parse_args()


if __name__ == '__main__':
    _setup_logger()
    main()
