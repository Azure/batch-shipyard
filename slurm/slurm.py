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
import collections
import concurrent.futures
import datetime
import enum
import hashlib
import json
import logging
import logging.handlers
import multiprocessing
import pathlib
import random
import re
import subprocess
import sys
import threading
import time
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
)
# non-stdlib imports
import azure.batch
import azure.batch.models as batchmodels
import azure.common
import azure.cosmosdb.table
import azure.mgmt.resource
import azure.mgmt.storage
import azure.storage.queue
import dateutil.tz
import msrestazure.azure_active_directory
import msrestazure.azure_cloud

# create logger
logger = logging.getLogger(__name__)
# global defines
# TODO allow these maximums to be configurable
_MAX_EXECUTOR_WORKERS = min((multiprocessing.cpu_count() * 4, 32))
_MAX_AUTH_FAILURE_RETRIES = 10
_MAX_RESUME_FAILURE_ATTEMPTS = 10


class Actions(enum.IntEnum):
    Suspend = 0,
    Resume = 1,
    ResumeFailed = 2,
    WaitForResume = 3,


class HostStates(enum.IntEnum):
    Up = 0,
    Resuming = 1,
    ProvisionInterrupt = 2,
    Provisioned = 3,
    Suspended = 4,


def setup_logger(log) -> None:
    """Set up logger"""
    log.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s %(process)d %(levelname)s '
        '%(name)s:%(funcName)s:%(lineno)d %(message)s'
    )
    formatter.default_msec_format = '%s.%03d'
    handler.setFormatter(formatter)
    log.addHandler(handler)


def max_workers_for_executor(iterable: Any) -> int:
    """Get max number of workers for executor given an iterable
    :param iterable: an iterable
    :return: number of workers for executor
    """
    return min((len(iterable), _MAX_EXECUTOR_WORKERS))


def is_none_or_empty(obj: Any) -> bool:
    """Determine if object is None or empty
    :param obj: object
    :return: if object is None or empty
    """
    return obj is None or len(obj) == 0


def is_not_empty(obj: Any) -> bool:
    """Determine if object is not None and is length is > 0
    :param obj: object
    :return: if object is not None and length is > 0
    """
    return obj is not None and len(obj) > 0


def datetime_utcnow(as_string: bool = False) -> datetime.datetime:
    """Returns a datetime now with UTC timezone
    :param as_string: return as ISO8601 extended string
    :return: datetime object representing now with UTC timezone
    """
    dt = datetime.datetime.now(dateutil.tz.tzutc())
    if as_string:
        return dt.strftime('%Y%m%dT%H%M%S.%f')[:-3] + 'Z'
    else:
        return dt


def hash_string(strdata: str) -> str:
    """Hash a string
    :param strdata: string data to hash
    :return: hexdigest
    """
    return hashlib.sha1(strdata.encode('utf8')).hexdigest()


def random_blocking_sleep(min: int, max: int) -> None:
    time.sleep(random.randint(min, max))


class Credentials():
    def __init__(self, config: Dict[str, Any]) -> None:
        """Ctor for Credentials
        :param config: configuration
        """
        # set attr from config
        self.storage_account = config['storage']['account']
        try:
            self.storage_account_key = config['storage']['account_key']
            self.storage_account_ep = config['storage']['endpoint']
            self.storage_account_rg = None
            self.cloud = None
            self.arm_creds = None
            self.batch_creds = None
            self.sub_id = None
            logger.debug('storage account {} ep: {}'.format(
                self.storage_account, self.storage_account_ep))
        except KeyError:
            self.storage_account_rg = config['storage']['resource_group']
            # get cloud object
            self.cloud = Credentials.convert_cloud_type(config['aad_cloud'])
            # get aad creds
            self.arm_creds = self.create_msi_credentials()
            self.batch_creds = self.create_msi_credentials(
                resource_id=self.cloud.endpoints.batch_resource_id)
            # get subscription id
            self.sub_id = self.get_subscription_id()
            logger.debug('created msi auth for sub id: {}'.format(self.sub_id))
            # get storage account key and endpoint
            self.storage_account_key, self.storage_account_ep = \
                self.get_storage_account_key()
            logger.debug('storage account {} -> rg: {} ep: {}'.format(
                self.storage_account, self.storage_account_rg,
                self.storage_account_ep))

    @staticmethod
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

    def get_subscription_id(self) -> str:
        """Get subscription id for ARM creds
        :param arm_creds: ARM creds
        :return: subscription id
        """
        client = azure.mgmt.resource.SubscriptionClient(self.arm_creds)
        return next(client.subscriptions.list()).subscription_id

    def create_msi_credentials(
            self,
            resource_id: str = None
    ) -> msrestazure.azure_active_directory.MSIAuthentication:
        """Create MSI credentials
        :param resource_id: resource id to auth against
        :return: MSI auth object
        """
        if is_not_empty(resource_id):
            creds = msrestazure.azure_active_directory.MSIAuthentication(
                cloud_environment=self.cloud,
                resource=resource_id,
            )
        else:
            creds = msrestazure.azure_active_directory.MSIAuthentication(
                cloud_environment=self.cloud,
            )
        return creds

    def get_storage_account_key(self) -> Tuple[str, str]:
        """Retrieve the storage account key and endpoint
        :return: tuple of key, endpoint
        """
        client = azure.mgmt.storage.StorageManagementClient(
            self.arm_creds, self.sub_id,
            base_url=self.cloud.endpoints.resource_manager)
        ep = None
        if is_not_empty(self.storage_account_rg):
            acct = client.storage_accounts.get_properties(
                self.storage_account_rg, self.storage_account)
            ep = '.'.join(
                acct.primary_endpoints.blob.rstrip('/').split('.')[2:]
            )
        else:
            for acct in client.storage_accounts.list():
                if acct.name == self.storage_account:
                    self.storage_account_rg = acct.id.split('/')[4]
                    ep = '.'.join(
                        acct.primary_endpoints.blob.rstrip('/').split('.')[2:]
                    )
                    break
        if is_none_or_empty(self.storage_account_rg) or is_none_or_empty(ep):
            raise RuntimeError(
                'storage account {} not found in subscription id {}'.format(
                    self.storage_account, self.sub_id))
        keys = client.storage_accounts.list_keys(
            self.storage_account_rg, self.storage_account)
        return (keys.keys[0].value, ep)


class ServiceProxy():
    def __init__(self, config: Dict[str, Any]) -> None:
        """Ctor for ServiceProxy
        :param config: configuration
        """
        self._config = config
        self._resume_timeout = None
        self._suspend_timeout = None
        prefix = config['storage']['entity_prefix']
        self.cluster_id = config['cluster_id']
        self.logging_id = config['logging_id']
        self.table_name = '{}slurm'.format(prefix)
        try:
            self.queue_assign = config['storage']['queues']['assign']
        except KeyError:
            self.queue_assign = None
        try:
            self.queue_action = config['storage']['queues']['action']
        except KeyError:
            self.queue_action = None
        try:
            self.node_id = config['batch']['node_id']
            self.pool_id = config['batch']['pool_id']
            self.ip_address = config['ip_address']
        except KeyError:
            self.node_id = None
            self.pool_id = None
            self.ip_address = None
        self.file_share_hmp = pathlib.Path(
            config['storage']['azfile_mount_dir']) / config['cluster_id']
        self._batch_client_lock = threading.Lock()
        self.batch_clients = {}
        # create credentials
        self.creds = Credentials(config)
        # create clients
        self.table_client = self._create_table_client()
        self.queue_client = self._create_queue_client()
        logger.debug('created storage clients for storage account {}'.format(
            self.creds.storage_account))

    @property
    def batch_shipyard_version(self) -> str:
        return self._config['batch_shipyard']['version']

    @property
    def batch_shipyard_var_path(self) -> pathlib.Path:
        return pathlib.Path(self._config['batch_shipyard']['var_path'])

    @property
    def storage_entity_prefix(self) -> str:
        return self._config['storage']['entity_prefix']

    @property
    def resume_timeout(self) -> int:
        if self._resume_timeout is None:
            # subtract off 5 seconds for fudge
            val = self._config['timeouts']['resume'] - 5
            if val < 5:
                val = 5
            self._resume_timeout = val
        return self._resume_timeout

    @property
    def suspend_timeout(self) -> int:
        if self._suspend_timeout is None:
            # subtract off 5 seconds for fudge
            val = self._config['timeouts']['suspend'] - 5
            if val < 5:
                val = 5
            self._suspend_timeout = val
        return self._suspend_timeout

    def log_configuration(self) -> None:
        logger.debug('configuration: {}'.format(
            json.dumps(self._config, sort_keys=True, indent=4)))

    def _modify_client_for_retry_and_user_agent(self, client: Any) -> None:
        """Extend retry policy of clients and add user agent string
        :param client: a client object
        """
        if client is None:
            return
        client.config.retry_policy.max_backoff = 8
        client.config.retry_policy.retries = 100
        client.config.add_user_agent('batch-shipyard/{}'.format(
            self.batch_shipyard_version))

    def _create_table_client(self) -> azure.cosmosdb.table.TableService:
        """Create a table client for the given storage account
        :return: table client
        """
        client = azure.cosmosdb.table.TableService(
            account_name=self.creds.storage_account,
            account_key=self.creds.storage_account_key,
            endpoint_suffix=self.creds.storage_account_ep,
        )
        return client

    def _create_queue_client(self) -> azure.storage.queue.QueueService:
        """Create a queue client for the given storage account
        :return: queue client
        """
        client = azure.storage.queue.QueueService(
            account_name=self.creds.storage_account,
            account_key=self.creds.storage_account_key,
            endpoint_suffix=self.creds.storage_account_ep,
        )
        return client

    def batch_client(
            self,
            service_url: str
    ) -> azure.batch.BatchServiceClient:
        """Get/create batch client
        :param service_url: service url
        :return: batch client
        """
        with self._batch_client_lock:
            try:
                return self.batch_clients[service_url]
            except KeyError:
                client = azure.batch.BatchServiceClient(
                    self.creds.batch_creds, batch_url=service_url)
                self._modify_client_for_retry_and_user_agent(client)
                self.batch_clients[service_url] = client
                logger.debug('batch client created for account: {}'.format(
                    service_url))
                return client

    def reset_batch_creds_and_client(
            self,
            service_url: str
    ) -> None:
        logger.warning('resetting batch creds and client for {}'.format(
            service_url))
        with self._batch_client_lock:
            self.creds.batch_creds = self.create_msi_credentials(
                resource_id=self.cloud.endpoints.batch_resource_id)
            self.batch_clients.pop(service_url, None)


class StorageServiceHandler():
    _PARTITIONS_PREFIX = 'PARTITIONS'
    _HOSTS_PREFIX = 'HOSTS'

    def __init__(self, service_proxy: ServiceProxy) -> None:
        """Ctor for Storage handler
        :param service_proxy: ServiceProxy
        """
        self.service_proxy = service_proxy

    def get_storage_account_key(self) -> Tuple[str, str]:
        return (self.service_proxy.creds.storage_account_key,
                self.service_proxy.creds.storage_account_ep)

    def list_partitions(self) -> List[azure.cosmosdb.table.Entity]:
        return self.service_proxy.table_client.query_entities(
            self.service_proxy.table_name,
            filter='PartitionKey eq \'{}${}\''.format(
                self._PARTITIONS_PREFIX, self.service_proxy.cluster_id))

    def get_host_assignment_entity(
            self,
            host: str,
    ) -> azure.cosmosdb.table.Entity:
        return self.service_proxy.table_client.get_entity(
            self.service_proxy.table_name,
            '{}${}'.format(self._HOSTS_PREFIX, self.service_proxy.cluster_id),
            host)

    def delete_node_assignment_entity(
            self,
            entity: azure.cosmosdb.table.Entity,
    ) -> None:
        try:
            self.service_proxy.table_client.delete_entity(
                self.service_proxy.table_name,
                entity['PartitionKey'],
                entity['RowKey'])
        except azure.common.AzureMissingResourceHttpError:
            pass

    def insert_queue_assignment_msg(self, rowkey: str, host: str) -> None:
        rkparts = rowkey.split('$')
        qname = '{}-{}'.format(self.service_proxy.cluster_id, rkparts[1])
        logger.debug('inserting host {} assignment token to queue {}'.format(
            host, qname))
        msg = {
            'cluster_id': self.service_proxy.cluster_id,
            'host': host,
        }
        msg_data = json.dumps(msg, ensure_ascii=True, sort_keys=True)
        self.service_proxy.queue_client.put_message(
            qname, msg_data, time_to_live=-1)

    def get_queue_assignment_msg(self) -> None:
        logger.debug('getting queue assignment from {}'.format(
            self.service_proxy.queue_assign))
        host = None
        while host is None:
            msgs = self.service_proxy.queue_client.get_messages(
                self.service_proxy.queue_assign, num_messages=1,
                visibility_timeout=150)
            for msg in msgs:
                msg_data = json.loads(msg.content, encoding='utf8')
                logger.debug(
                    'got message {}: {}'.format(msg.id, msg_data))
                host = msg_data['host']
                outfile = pathlib.Path(
                    self.service_proxy.batch_shipyard_var_path) / 'slurm_host'
                with outfile.open('wt') as f:
                    f.write(host)
                self.service_proxy.queue_client.delete_message(
                    self.service_proxy.queue_assign, msg.id,
                    msg.pop_receipt)
                break
            random_blocking_sleep(1, 3)
        logger.info('got host assignment: {}'.format(host))

    def insert_queue_action_msg(
            self,
            action: Actions,
            hosts: List[str],
            retry_count: Optional[int] = None,
            visibility_timeout: Optional[int] = None,
    ) -> None:
        msg = {
            'cluster_id': self.service_proxy.cluster_id,
            'action': action.value,
            'hosts': hosts,
        }
        if retry_count is not None:
            msg['retry_count'] = retry_count
        logger.debug('inserting queue {} message (vt={}): {}'.format(
            self.service_proxy.queue_action, visibility_timeout, msg))
        msg_data = json.dumps(msg, ensure_ascii=True, sort_keys=True)
        self.service_proxy.queue_client.put_message(
            self.service_proxy.queue_action, msg_data,
            visibility_timeout=visibility_timeout, time_to_live=-1)

    def get_queue_action_msg(
            self
    ) -> Optional[Tuple[Dict[str, Any], str, str]]:
        msgs = self.service_proxy.queue_client.get_messages(
            self.service_proxy.queue_action, num_messages=1,
            visibility_timeout=self.service_proxy.resume_timeout)
        for msg in msgs:
            msg_data = json.loads(msg.content, encoding='utf8')
            logger.debug(
                'got message {} from queue {}: {}'.format(
                    msg.id, self.service_proxy.queue_action, msg_data))
            return (msg_data, msg.id, msg.pop_receipt)
        return None

    def update_queue_action_msg(
            self,
            id: str,
            pop_receipt: str,
    ) -> None:
        logger.debug(
            'updating queue {} message id {} pop receipt {}'.format(
                self.service_proxy.queue_action, id, pop_receipt))
        self.service_proxy.queue_client.update_message(
            self.service_proxy.queue_action, id, pop_receipt, 20)

    def delete_queue_action_msg(
            self,
            id: str,
            pop_receipt: str,
    ) -> None:
        logger.debug(
            'deleting queue {} message id {} pop receipt {}'.format(
                self.service_proxy.queue_action, id, pop_receipt))
        self.service_proxy.queue_client.delete_message(
            self.service_proxy.queue_action, id, pop_receipt)

    def insert_host_assignment_entity(
            self,
            host: str,
            partition_name: str,
            service_url: str,
            pool_id: str
    ) -> None:
        entity = {
            'PartitionKey': '{}${}'.format(
                self._HOSTS_PREFIX, self.service_proxy.cluster_id),
            'RowKey': host,
            'Partition': partition_name,
            'State': HostStates.Resuming.value,
            'BatchServiceUrl': service_url,
            'BatchPoolId': pool_id,
            'BatchShipyardSlurmVersion': 1,
        }
        self.service_proxy.table_client.insert_or_replace_entity(
            self.service_proxy.table_name, entity)

    def merge_host_assignment_entity_for_compute_node(
            self,
            host: str,
            state: HostStates,
            state_only: bool,
            retry_on_conflict: Optional[bool] = None,
    ) -> None:
        entity = {
            'PartitionKey': '{}${}'.format(
                self._HOSTS_PREFIX, self.service_proxy.cluster_id),
            'RowKey': host,
            'State': state.value,
        }
        if not state_only:
            entity['BatchNodeId'] = self.service_proxy.node_id
        logger.debug(
            'merging host {} ip={} assignment entity in table {}: {}'.format(
                host, self.service_proxy.ip_address,
                self.service_proxy.table_name, entity))
        if retry_on_conflict is None:
            retry_on_conflict = True
        while True:
            try:
                self.service_proxy.table_client.merge_entity(
                    self.service_proxy.table_name, entity)
                break
            except azure.common.AzureConflictHttpError:
                if retry_on_conflict:
                    random_blocking_sleep(1, 3)
                else:
                    raise

    def update_host_assignment_entity_as_provisioned(
            self,
            host: str,
            entity: azure.cosmosdb.table.Entity,
    ) -> None:
        entity['State'] = HostStates.Provisioned.value
        entity['IpAddress'] = self.service_proxy.ip_address
        entity['BatchNodeId'] = self.service_proxy.node_id
        logger.debug(
            'updating host {} ip={} assignment entity in table {}: {}'.format(
                host, self.service_proxy.ip_address,
                self.service_proxy.table_name, entity))
        # this must process sucessfully with no etag collision
        self.service_proxy.table_client.update_entity(
            self.service_proxy.table_name, entity)

    def wait_for_host_assignment_entities(
            self,
            start_time: datetime.datetime,
            hosts: List[str],
            timeout: Optional[int] = None,
            set_idle_state: Optional[bool] = None,
    ) -> None:
        if timeout is None:
            timeout = self.service_proxy.resume_timeout
        logger.info('waiting for {} hosts to spin up in {} sec'.format(
            len(hosts), timeout))
        host_queue = collections.deque(hosts)
        i = 0
        while len(host_queue) > 0:
            host = host_queue.popleft()
            try:
                entity = self.get_host_assignment_entity(host)
                ip = entity['IpAddress']
                state = HostStates(entity['State'])
                if state != HostStates.Provisioned:
                    logger.error('unexpected state for host {}: {}'.format(
                        host, state))
                    raise KeyError()
            except (azure.common.AzureMissingResourceHttpError, KeyError):
                host_queue.append(host)
            else:
                logger.debug(
                    'updating host {} with ip {} node id {} pool id {}'.format(
                        host, ip, entity['BatchNodeId'],
                        entity['BatchPoolId']))
                cmd = ['scontrol', 'update', 'NodeName={}'.format(host),
                       'NodeAddr={}'.format(ip),
                       'NodeHostname={}'.format(host)]
                if set_idle_state:
                    cmd.append('State=Idle')
                logger.debug('command: {}'.format(' '.join(cmd)))
                subprocess.check_call(cmd)
                # update entity state
                m_entity = {
                    'PartitionKey': entity['PartitionKey'],
                    'RowKey': entity['RowKey'],
                    'State': HostStates.Up.value,
                }
                self.service_proxy.table_client.merge_entity(
                    self.service_proxy.table_name, m_entity)
                continue
            i += 1
            if i % 6 == 0:
                i = 0
                logger.debug('still waiting for {} hosts'.format(
                    len(host_queue)))
            diff = datetime_utcnow() - start_time
            if diff.total_seconds() > timeout:
                return host_queue
            random_blocking_sleep(5, 10)
        logger.info('{} host spin up completed'.format(len(hosts)))
        return None


class BatchServiceHandler():
    def __init__(self, service_proxy: ServiceProxy) -> None:
        """Ctor for Batch handler
        :param service_proxy: ServiceProxy
        """
        self.service_proxy = service_proxy

    def get_node_state_counts(
            self,
            service_url: str,
            pool_id: str,
    ) -> batchmodels.PoolNodeCounts:
        client = self.service_proxy.batch_client(service_url)
        try:
            node_counts = client.account.list_pool_node_counts(
                account_list_pool_node_counts_options=batchmodels.
                AccountListPoolNodeCountsOptions(
                    filter='poolId eq \'{}\''.format(pool_id)
                )
            )
            nc = list(node_counts)
            if len(nc) == 0:
                logger.error(
                    'no node counts for pool {} (service_url={})'.format(
                        pool_id, service_url))
            return nc[0]
        except batchmodels.BatchErrorException:
            logger.error(
                'could not retrieve pool {} node counts '
                '(service_url={})'.format(pool_id, service_url))

    def get_node_info(
            self,
            service_url: str,
            pool_id: str,
            node_id: str,
    ) -> batchmodels.ComputeNode:
        auth_attempts = 0
        client = self.service_proxy.batch_client(service_url)
        # get pool and add delta to current target counts
        while True:
            try:
                return client.compute_node.get(pool_id, node_id)
            except batchmodels.BatchErrorException as ex:
                if 'failed to authorize the request' in ex.message.value:
                    if auth_attempts > _MAX_AUTH_FAILURE_RETRIES:
                        raise
                    logger.warning(
                        'authorization failed for {}, retrying'.format(
                            service_url))
                    self.service_proxy.reset_batch_creds_and_client(
                        service_url)
                    random_blocking_sleep(1, 3)
                    auth_attempts += 1
                    client = self.service_proxy.batch_client(service_url)
                else:
                    return None

    def add_nodes_to_pool(
            self,
            service_url: str,
            pool_id: str,
            compute_node_type: str,
            num_hosts: int,
    ) -> None:
        auth_attempts = 0
        client = self.service_proxy.batch_client(service_url)
        # get pool and add delta to current target counts
        while True:
            try:
                pool = client.pool.get(pool_id)
                if (pool.allocation_state ==
                        batchmodels.AllocationState.resizing):
                    logger.debug(
                        'cannot add nodes to pool {} as it is resizing, '
                        'will retry'.format(pool_id))
                    random_blocking_sleep(5, 10)
                    continue
                if compute_node_type == 'dedicated':
                    target_dedicated = pool.target_dedicated_nodes + num_hosts
                    target_low_priority = 0
                    logger.debug(
                        'adding dedicated nodes to pool {}: {} -> {} '
                        '(service_url={})'.format(
                            pool_id, pool.target_dedicated_nodes,
                            target_dedicated, service_url))
                else:
                    target_dedicated = 0
                    target_low_priority = (
                        pool.target_low_priority_nodes + num_hosts
                    )
                    logger.debug(
                        'adding low priority nodes to pool {}: {} -> {} '
                        '(service_url={})'.format(
                            pool_id, pool.target_low_priority_nodes,
                            target_low_priority, service_url))
                client.pool.resize(
                    pool_id,
                    pool_resize_parameter=batchmodels.PoolResizeParameter(
                        target_dedicated_nodes=target_dedicated,
                        target_low_priority_nodes=target_low_priority,
                    ),
                )
                logger.info('added nodes to pool {}'.format(pool_id))
                break
            except batchmodels.BatchErrorException as ex:
                if 'ongoing resize operation' in ex.message.value:
                    logger.debug('pool {} is resizing, will retry'.format(
                        pool_id))
                    random_blocking_sleep(5, 10)
                elif 'failed to authorize the request' in ex.message.value:
                    if auth_attempts > _MAX_AUTH_FAILURE_RETRIES:
                        raise
                    logger.warning(
                        'authorization failed for {}, retrying'.format(
                            service_url))
                    self.service_proxy.reset_batch_creds_and_client(
                        service_url)
                    random_blocking_sleep(1, 3)
                    auth_attempts += 1
                    client = self.service_proxy.batch_client(service_url)
                else:
                    logger.exception(
                        'could not add nodes to pool {} '
                        '(service_url={})'.format(pool_id, service_url))
                    raise

    def remove_nodes_from_pool(
            self,
            service_url: str,
            pool_id: str,
            nodes: List[str],
    ) -> None:
        auth_attempts = 0
        client = self.service_proxy.batch_client(service_url)
        while True:
            try:
                pool = client.pool.get(pool_id)
                if (pool.allocation_state ==
                        batchmodels.AllocationState.resizing):
                    logger.debug(
                        'cannot remove nodes to pool {} as it is resizing, '
                        'will retry'.format(pool_id))
                    random_blocking_sleep(5, 10)
                    continue
                client.pool.remove_nodes(
                    pool_id,
                    node_remove_parameter=batchmodels.NodeRemoveParameter(
                        node_list=nodes,
                    ),
                )
                logger.info('removed {} nodes from pool {}'.format(
                    len(nodes), pool_id))
                break
            except batchmodels.BatchErrorException as ex:
                if 'ongoing resize operation' in ex.message.value:
                    logger.debug('pool {} has ongoing resize operation'.format(
                        pool_id))
                    random_blocking_sleep(5, 10)
                elif 'failed to authorize the request' in ex.message.value:
                    if auth_attempts > _MAX_AUTH_FAILURE_RETRIES:
                        # TODO need better recovery - requeue suspend action?
                        raise
                    logger.warning(
                        'authorization failed for {}, retrying'.format(
                            service_url))
                    self.service_proxy.reset_batch_creds_and_client(
                        service_url)
                    random_blocking_sleep(1, 3)
                    auth_attempts += 1
                    client = self.service_proxy.batch_client(service_url)
                else:
                    logger.error(
                        'could not remove nodes from pool {} '
                        '(service_url={})'.format(pool_id, service_url))
                    # TODO need better recovery - requeue suspend action?
                    break
        # delete log files
        for node in nodes:
            file = pathlib.Path(
                self.service_proxy.file_share_hmp
            ) / 'slurm' / 'logs' / 'slurm-helper-debug-{}.log'.format(node)
            try:
                file.unlink()
            except OSError:
                pass

    def clean_pool(
            self,
            service_url: str,
            pool_id: str,
    ) -> None:
        auth_attempts = 0
        node_filter = [
            '(state eq \'starttaskfailed\')',
            '(state eq \'unusable\')',
            '(state eq \'preempted\')',
        ]
        client = self.service_proxy.batch_client(service_url)
        while True:
            try:
                nodes = client.compute_node.list(
                    pool_id=pool_id,
                    compute_node_list_options=batchmodels.
                    ComputeNodeListOptions(filter=' or '.join(node_filter)),
                )
                node_ids = [node.id for node in nodes]
                if is_none_or_empty(node_ids):
                    logger.debug('no nodes to clean from pool: {}'.format(
                        pool_id))
                    return
                logger.info('removing nodes {} from pool {}'.format(
                    node_ids, pool_id))
                client.pool.remove_nodes(
                    pool_id=pool_id,
                    node_remove_parameter=batchmodels.NodeRemoveParameter(
                        node_list=node_ids,
                    )
                )
                break
            except batchmodels.BatchErrorException as ex:
                if 'ongoing resize operation' in ex.message.value:
                    logger.debug('pool {} has ongoing resize operation'.format(
                        pool_id))
                    random_blocking_sleep(5, 10)
                elif 'failed to authorize the request' in ex.message.value:
                    if auth_attempts > _MAX_AUTH_FAILURE_RETRIES:
                        # TODO need better recovery - requeue suspend action?
                        raise
                    logger.warning(
                        'authorization failed for {}, retrying'.format(
                            service_url))
                    self.service_proxy.reset_batch_creds_and_client(
                        service_url)
                    random_blocking_sleep(1, 3)
                    auth_attempts += 1
                    client = self.service_proxy.batch_client(service_url)
                else:
                    logger.error(
                        'could not clean pool {} (service_url={})'.format(
                            pool_id, service_url))
                    # TODO need better recovery - requeue resume fail action?
                    break


class CommandProcessor():
    def __init__(self, config: Dict[str, Any]) -> None:
        """Ctor for CommandProcessor
        :param config: configuration
        """
        self._service_proxy = ServiceProxy(config)
        self._partitions = None
        self.ssh = StorageServiceHandler(self._service_proxy)
        self.bsh = BatchServiceHandler(self._service_proxy)

    @property
    def slurm_partitions(self) -> List[azure.cosmosdb.table.Entity]:
        if self._partitions is None:
            self._partitions = list(self.ssh.list_partitions())
            for entity in self._partitions:
                entity['HostList'] = re.compile(entity['HostList'])
        return self._partitions

    def set_log_configuration(self) -> None:
        global logger
        # remove existing handlers
        handlers = logger.handlers[:]
        for handler in handlers:
            handler.close()
            logger.removeHandler(handler)
        # set level
        logger.setLevel(logging.DEBUG)
        # set formatter
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s:%(funcName)s:%(lineno)d '
            '%(message)s')
        formatter.default_msec_format = '%s.%03d'
        # set handlers
        handler_stream = logging.StreamHandler()
        handler_stream.setFormatter(formatter)
        logger.addHandler(handler_stream)
        az_storage_logger = logging.getLogger('azure.storage')
        az_storage_logger.setLevel(logging.WARNING)
        az_storage_logger.addHandler(handler_stream)
        az_cosmosdb_logger = logging.getLogger('azure.cosmosdb')
        az_cosmosdb_logger.setLevel(logging.WARNING)
        az_cosmosdb_logger.addHandler(handler_stream)
        # log to selected log level file
        logfname = pathlib.Path('slurm-helper.log')
        logfile = (
            self._service_proxy.file_share_hmp / 'slurm' / 'logs' /
            ('{}-{}-{}{}').format(
                logfname.stem, 'debug', self._service_proxy.logging_id,
                logfname.suffix)
        )
        logfile.parent.mkdir(exist_ok=True)
        handler_logfile = logging.handlers.RotatingFileHandler(
            str(logfile), maxBytes=33554432, backupCount=20000,
            encoding='utf-8')
        handler_logfile.setFormatter(formatter)
        logger.addHandler(handler_logfile)
        az_storage_logger.addHandler(handler_logfile)
        az_cosmosdb_logger.addHandler(handler_logfile)
        # dump configuration
        self._service_proxy.log_configuration()

    def process_resume_action(self, hosts: List[str]) -> None:
        if len(hosts) == 0:
            logger.error('host list is empty for resume')
            return
        logger.debug(
            'pulled action resume for hosts: {}'.format(', '.join(hosts)))
        # first check if hosts have already resumed as this action can
        # be called multiple times for the same set of hosts due to
        # controller failover
        hosts_modified = []
        for he in hosts:
            host, partname = he.split()
            try:
                entity = self.ssh.get_host_assignment_entity(host)
                state = HostStates(entity['State'])
            except azure.common.AzureMissingResourceHttpError:
                hosts_modified.append(he)
            else:
                logger.debug(
                    'host entry {} found for partition {} but state '
                    'is {}'.format(host, partname, state))
                if state != HostStates.Resuming and state != HostStates.Up:
                    hosts_modified.append(he)
        hosts = hosts_modified
        del hosts_modified
        logger.debug('resuming hosts: {}'.format(', '.join(hosts)))
        if len(hosts) == 0:
            logger.error('modified host list is empty for resume')
            return
        # collate hosts into a map of batch pools -> host config
        pool_map = {}
        partitions = self.slurm_partitions
        for entity in partitions:
            key = '{}${}'.format(
                entity['BatchServiceUrl'], entity['BatchPoolId'])
            pool_map[key] = {
                'num_hosts': 0,
                'compute_node_type': entity['ComputeNodeType'],
            }
        # insert host assignment entity and message
        total_hosts = 0
        for he in hosts:
            host, partname = he.split()
            for entity in partitions:
                if not entity['RowKey'].startswith(partname):
                    continue
                if entity['HostList'].fullmatch(host):
                    key = '{}${}'.format(
                        entity['BatchServiceUrl'], entity['BatchPoolId'])
                    pool_map[key]['num_hosts'] += 1
                    self.ssh.insert_host_assignment_entity(
                        host, partname, entity['BatchServiceUrl'],
                        entity['BatchPoolId'])
                    self.ssh.insert_queue_assignment_msg(
                        entity['RowKey'], host)
                    total_hosts += 1
                    break
        if total_hosts != len(hosts):
            logger.error(
                'total host {} to number of hosts to resume '
                '{} mismatch'.format(total_hosts, len(hosts)))
        del total_hosts
        # resize batch pools to specified number of hosts
        resize_futures = {}
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers_for_executor(pool_map)) as executor:
            for key in pool_map:
                service_url, pool_id = key.split('$')
                resize_futures[key] = executor.submit(
                    self.bsh.add_nodes_to_pool(
                        service_url, pool_id,
                        pool_map[key]['compute_node_type'],
                        pool_map[key]['num_hosts'])
                )

    def process_suspend_action(self, hosts: List[str]) -> bool:
        if len(hosts) == 0:
            logger.error('host list is empty for suspend')
            return True
        logger.debug('suspending hosts: {}'.format(', '.join(hosts)))
        # find pool/account mapping for node
        suspend_retry = set()
        suspended = []
        pool_map = {}
        entities = []
        for host in hosts:
            try:
                entity = self.ssh.get_host_assignment_entity(host)
            except azure.common.AzureMissingResourceHttpError:
                logger.error('host {} entity not found'.format(host))
                continue
            logger.debug('found host {} mapping: {}'.format(host, entity))
            if HostStates(entity['State']) == HostStates.Suspended:
                logger.error('host {} is already suspended'.format(host))
                continue
            try:
                node_id = entity['BatchNodeId']
            except KeyError:
                logger.error(
                    'host {} does not have a batch node id assigned'.format(
                        host))
                suspend_retry.add(host)
                continue
            key = '{}${}'.format(
                entity['BatchServiceUrl'], entity['BatchPoolId'])
            if key not in pool_map:
                pool_map[key] = []
            pool_map[key].append(node_id)
            suspended.append(host)
            entities.append(entity)
        # resize batch pools down, deleting specified hosts
        if len(entities) == 0:
            logger.info('no hosts to suspend after analyzing host entities')
        else:
            # remove nodes
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers_for_executor(
                        pool_map)) as executor:
                for key in pool_map:
                    service_url, pool_id = key.split('$')
                    executor.submit(
                        self.bsh.remove_nodes_from_pool(
                            service_url, pool_id, pool_map[key])
                    )
            # mark entities suspended
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers_for_executor(
                        suspended)) as executor:
                for host in suspended:
                    executor.submit(
                        self.ssh.
                        merge_host_assignment_entity_for_compute_node(
                            host, HostStates.Suspended, True,
                            retry_on_conflict=True)
                    )
        # delete log files
        for host in suspended:
            file = pathlib.Path(
                self._service_proxy.file_share_hmp
            ) / 'slurm' / 'logs' / 'slurmd-{}.log'.format(host)
            try:
                file.unlink()
            except OSError:
                pass
        # re-enqueue suspend retry entries
        if len(suspend_retry) > 0:
            if set(hosts) == suspend_retry:
                logger.debug('host suspend list in is the same as retry')
                return False
            logger.debug('adding suspend action for {} hosts to retry'.format(
                len(suspend_retry)))
            self.ssh.insert_queue_action_msg(
                Actions.Suspend, list(suspend_retry))
        return True

    def _query_node_state(self, host, entity):
        service_url = entity['BatchServiceUrl']
        pool_id = entity['BatchPoolId']
        node_id = None
        try:
            node_id = entity['BatchNodeId']
        except KeyError:
            logger.debug('batch node id not present for host {}'.format(
                host))
            return node_id, None
        node = self.bsh.get_node_info(service_url, pool_id, node_id)
        if node is None:
            logger.error(
                'host {} compute node {} on pool {} (service_url={}) '
                'does not exist'.format(
                    host, node_id, pool_id, service_url))
            return node_id, None
        logger.debug(
            'host node {} on pool {} is {} (service_url={})'.format(
                host, node_id, pool_id, node.state, service_url))
        return node_id, node.state

    def process_resume_failed_action(
            self,
            hosts: List[str],
            retry_count: int,
    ) -> bool:
        if len(hosts) == 0:
            logger.error('host list is empty for resume failed')
            return True
        hosts_retry = set()
        hosts_update = set()
        hosts_check = {}
        clean_pools = set()
        # create pool map from partitions
        pool_map = {}
        partitions = self.slurm_partitions
        for entity in partitions:
            key = '{}${}'.format(
                entity['BatchServiceUrl'], entity['BatchPoolId'])
            pool_map[key] = {
                'compute_node_type': entity['ComputeNodeType'],
                'hosts_recover': set(),
                'nodes_recover': set(),
            }
        # check host state
        for he in hosts:
            host, partname = he.split()
            try:
                entity = self.ssh.get_host_assignment_entity(host)
                host_state = HostStates(entity['State'])
            except azure.common.AzureMissingResourceHttpError:
                # TODO what else can we do here?
                logger.error('host {} entity not found'.format(host))
                continue
            logger.debug('host {} state is {}'.format(host, host_state))
            if host_state == HostStates.Up:
                # TODO if up, verify sinfo state
                # sinfo -h -n host -o "%t"
                hosts_update.add(host)
            else:
                hosts_check[he] = entity
        # check pool for each host to mark cleanup
        for he in hosts:
            host, partname = he.split()
            entity = hosts_check[he]
            service_url = entity['BatchServiceUrl']
            pool_id = entity['BatchPoolId']
            node_counts = self.bsh.get_node_state_counts(service_url, pool_id)
            num_bad_nodes = (
                node_counts.dedicated.unusable +
                node_counts.dedicated.start_task_failed +
                node_counts.low_priority.unusable +
                node_counts.low_priority.start_task_failed
            )
            # mark pool for cleanup for any unusable/start task failed
            if num_bad_nodes > 0:
                key = '{}${}'.format(service_url, pool_id)
                logger.debug('{} bad nodes found on {}'.format(
                    num_bad_nodes, key))
                clean_pools.add(key)
        # check each host on the Batch service
        for he in hosts:
            host, partname = he.split()
            entity = hosts_check[he]
            service_url = entity['BatchServiceUrl']
            pool_id = entity['BatchPoolId']
            key = '{}${}'.format(service_url, pool_id)
            node_id, node_state = self._query_node_state(host, entity)
            if (node_state == batchmodels.ComputeNodeState.idle or
                    node_state == batchmodels.ComputeNodeState.offline or
                    node_state == batchmodels.ComputeNodeState.running):
                hosts_update.add(host)
            elif (node_state ==
                  batchmodels.ComputeNodeState.start_task_failed or
                  node_state == batchmodels.ComputeNodeState.unusable or
                  node_state == batchmodels.ComputeNodeState.preempted or
                  node_state == batchmodels.ComputeNodeState.leaving_pool):
                clean_pools.add(key)
                pool_map[key]['nodes_recover'].add(node_id)
                pool_map[key]['hosts_recover'].add(he)
            else:
                if retry_count >= _MAX_RESUME_FAILURE_ATTEMPTS:
                    logger.debug(
                        '{} on partition {} exceeded max resume failure retry '
                        'attempts, recovering instead'.format(host, partname))
                    if node_id is not None:
                        pool_map[key]['nodes_recover'].add(node_id)
                    pool_map[key]['hosts_recover'].add(he)
                else:
                    hosts_retry.add(he)
        del hosts_check
        # update hosts
        if len(hosts_update) > 0:
            self.ssh.insert_queue_action_msg(
                Actions.WaitForResume, list(hosts_update), retry_count=0)
        del hosts_update
        # clean pools
        for key in clean_pools:
            service_url, pool_id = key.split('$')
            self.bsh.clean_pool(service_url, pool_id)
        del clean_pools
        # recover hosts
        for key in pool_map:
            hosts_recover = pool_map[key]['hosts_recover']
            hrlen = len(hosts_recover)
            if hrlen == 0:
                continue
            for he in hosts_recover:
                host, partname = he.split()
                self.ssh.merge_host_assignment_entity_for_compute_node(
                    host, HostStates.ProvisionInterrupt, True,
                    retry_on_conflict=True)
            nodes_recover = pool_map[key]['nodes_recover']
            if len(nodes_recover) > 0:
                service_url, pool_id = key.split('$')
                self.bsh.remove_nodes_from_pool(
                    service_url, pool_id, list(nodes_recover))
            host_list = list(hosts_recover)
            self.ssh.insert_queue_action_msg(Actions.Resume, host_list)
            self.ssh.insert_queue_action_msg(
                Actions.WaitForResume, host_list, retry_count=0,
                visibility_timeout=60)
        # re-enqueue failed resume hosts
        if len(hosts_retry) > 0:
            logger.debug(
                'adding resume failed action for {} hosts to retry'.format(
                    len(hosts_retry)))
            self.ssh.insert_queue_action_msg(
                Actions.ResumeFailed, list(hosts_retry),
                retry_count=retry_count + 1, visibility_timeout=60)
        return True

    def process_wait_for_resume_action(
            self,
            hosts: List[str],
            retry_count: int,
    ) -> bool:
        if len(hosts) == 0:
            logger.error('host list is empty for resume failed')
            return True
        start_time = datetime_utcnow()
        remain_hosts = self.ssh.wait_for_host_assignment_entities(
            start_time, hosts, timeout=10, set_idle_state=True)
        if remain_hosts is not None:
            if retry_count > self._service_proxy.resume_timeout / 30:
                logger.error(
                    'not retrying host spin up completion for: {}'.format(
                        remain_hosts))
                self.ssh.insert_queue_action_msg(
                    Actions.ResumeFailed, list(remain_hosts), retry_count=0,
                    visibility_timeout=5)
            else:
                logger.warning(
                    'host spin up not completed: {}'.format(remain_hosts))
                self.ssh.insert_queue_action_msg(
                    Actions.WaitForResume, list(remain_hosts),
                    retry_count=retry_count + 1, visibility_timeout=30)
        return True

    def resume_hosts(self, hosts: List[str]) -> None:
        # insert into action queue
        start_time = datetime_utcnow()
        logger.debug('received resume hosts: {}'.format(', '.join(hosts)))
        self.ssh.insert_queue_action_msg(Actions.Resume, hosts)
        # process resume completions and translate into scontrol
        bare_hosts = [he.split()[0] for he in hosts]
        remain_hosts = self.ssh.wait_for_host_assignment_entities(
            start_time, bare_hosts)
        if remain_hosts is not None:
            raise RuntimeError(
                'exceeded resume timeout waiting for hosts to '
                'spin up: {}'.format(remain_hosts))

    def resume_hosts_failed(self, hosts: List[str]) -> None:
        # insert into action queue
        logger.info('received resume failed hosts: {}'.format(
            ', '.join(hosts)))
        self.ssh.insert_queue_action_msg(
            Actions.ResumeFailed, hosts, retry_count=0, visibility_timeout=5)

    def suspend_hosts(self, hosts: List[str]) -> None:
        # insert into action queue
        logger.debug('received suspend hosts: {}'.format(', '.join(hosts)))
        self.ssh.insert_queue_action_msg(Actions.Suspend, hosts)

    def check_provisioning_status(self, host: str) -> None:
        logger.debug(
            'checking for provisioning status for host {}'.format(host))
        try:
            entity = self.ssh.get_host_assignment_entity(host)
            state = HostStates(entity['State'])
        except (azure.common.AzureMissingResourceHttpError, KeyError):
            # this should not happen, but fail in case it does
            logger.error('host assignment entity does not exist for {}'.format(
                host))
            sys.exit(1)
        logger.info('host {} state property is {}'.format(host, state))
        if state != HostStates.Resuming:
            logger.error(
                'unexpected state, state is not {} for host {}'.format(
                    HostStates.Resuming, host))
            # update host entity assignment
            self.ssh.merge_host_assignment_entity_for_compute_node(
                host, HostStates.ProvisionInterrupt, False,
                retry_on_conflict=False)
            sys.exit(1)
        return entity

    def daemon_processor(self) -> None:
        # set logging config for daemon processor
        self.set_log_configuration()
        logger.info('daemon processor starting')
        while True:
            msg = self.ssh.get_queue_action_msg()
            if msg is None:
                random_blocking_sleep(1, 3)
            else:
                del_msg = True
                action = msg[0]['action']
                hosts = msg[0]['hosts']
                msg_id = msg[1]
                pop_receipt = msg[2]
                if action == Actions.Suspend:
                    del_msg = self.process_suspend_action(hosts)
                elif action == Actions.Resume:
                    self.process_resume_action(hosts)
                elif action == Actions.ResumeFailed:
                    del_msg = self.process_resume_failed_action(
                        hosts, msg[0]['retry_count'])
                elif action == Actions.WaitForResume:
                    del_msg = self.process_wait_for_resume_action(
                        hosts, msg[0]['retry_count'])
                else:
                    logger.error('unknown action {} for hosts {}'.format(
                        action, ', '.join(hosts)))
                if del_msg:
                    self.ssh.delete_queue_action_msg(msg_id, pop_receipt)
                else:
                    self.ssh.update_queue_action_msg(msg_id, pop_receipt)

    def execute(
            self,
            action: str,
            hosts: Optional[List[str]],
            host: Optional[str],
    ) -> None:
        """Execute action
        :param action: action to execute
        """
        # process actions
        if action == 'daemon':
            self.daemon_processor()
        elif action == 'sakey':
            sakey = self.ssh.get_storage_account_key()
            print(sakey[0], sakey[1])
        elif action == 'resume':
            self.resume_hosts(hosts)
        elif action == 'resume-fail':
            self.resume_hosts_failed(hosts)
        elif action == 'suspend':
            self.suspend_hosts(hosts)
        elif action == 'check-provisioning-status':
            self.check_provisioning_status(host)
        elif action == 'get-node-assignment':
            self.ssh.get_queue_assignment_msg()
        elif action == 'complete-node-assignment':
            entity = self.check_provisioning_status(host)
            self.ssh.update_host_assignment_entity_as_provisioned(host, entity)
        else:
            raise ValueError('unknown action to execute: {}'.format(action))


def main() -> None:
    """Main function"""
    # get command-line args
    args = parseargs()
    if is_none_or_empty(args.action):
        raise ValueError('action is invalid')
    # load configuration
    if is_none_or_empty(args.conf):
        raise ValueError('config file not specified')
    with open(args.conf, 'rb') as f:
        config = json.load(f)
    logger.debug('loaded config from {}: {}'.format(args.conf, config))
    # parse hostfile
    if args.hostfile is not None:
        with open(args.hostfile, 'r') as f:
            hosts = [line.rstrip() for line in f]
    else:
        hosts = None
    try:
        # create command processor
        cmd_processor = CommandProcessor(config)
        # execute action
        cmd_processor.execute(args.action, hosts, args.host)
    except Exception:
        logger.exception('error executing {}'.format(args.action))
    finally:
        handlers = logger.handlers[:]
        for handler in handlers:
            handler.close()
            logger.removeHandler(handler)


def parseargs() -> argparse.Namespace:
    """Parse program arguments
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='slurm: Azure Batch Shipyard Slurm Helper')
    parser.add_argument(
        'action',
        choices=[
            'daemon', 'sakey', 'resume', 'resume-fail', 'suspend',
            'check-provisioning-status', 'get-node-assignment',
            'complete-node-assignment',
        ]
    )
    parser.add_argument('--conf', help='configuration file')
    parser.add_argument('--hostfile', help='host file')
    parser.add_argument('--host', help='host')
    return parser.parse_args()


if __name__ == '__main__':
    # set up log formatting and default handlers
    setup_logger(logger)
    main()
