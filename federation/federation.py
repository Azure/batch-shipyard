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
import concurrent.futures
import datetime
import hashlib
import json
import logging
import logging.handlers
import multiprocessing
import pathlib
import pickle
import random
import subprocess
import threading
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
)
# non-stdlib imports
import azure.batch
import azure.batch.models as batchmodels
import azure.cosmosdb.table
import azure.mgmt.compute
import azure.mgmt.resource
import azure.mgmt.storage
import azure.storage.blob
import azure.storage.queue
import dateutil.tz
import msrestazure.azure_active_directory
import msrestazure.azure_cloud

# create logger
logger = logging.getLogger(__name__)
# global defines
_MEGABYTE = 1048576
_RDMA_INSTANCES = frozenset((
    'standard_a8', 'standard_a9',
))
_RDMA_INSTANCE_SUFFIXES = frozenset((
    'r', 'rs', 'rs_v2', 'rs_v3',
))
_GPU_INSTANCE_PREFIXES = frozenset((
    'standard_nc', 'standard_nd', 'standard_nv',
))
_POOL_NATIVE_METADATA_NAME = 'BATCH_SHIPYARD_NATIVE_CONTAINER_POOL'
# TODO allow these maximums to be configurable
_MAX_EXECUTOR_WORKERS = min((multiprocessing.cpu_count() * 4, 32))
_MAX_TIMESPAN_POOL_UPDATE = datetime.timedelta(seconds=60)
_MAX_TIMESPAN_NODE_COUNTS_UPDATE = datetime.timedelta(seconds=10)
_MAX_TIMESPAN_ACTIVE_TASKS_COUNT_UPDATE = datetime.timedelta(seconds=20)


def _setup_logger(log) -> None:
    """Set up logger"""
    log.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s:%(funcName)s:%(lineno)d '
        '%(message)s')
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


def datetime_utcnow(as_string: bool=False) -> datetime.datetime:
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


def hash_federation_id(federation_id: str) -> str:
    """Hash a federation id
    :param federation_id: federation id
    :return: hashed federation id
    """
    return hash_string(federation_id)


def is_rdma_pool(vm_size: str) -> bool:
    """Check if pool is IB/RDMA capable
    :param vm_size: vm size
    :return: if rdma is present
    """
    vsl = vm_size.lower()
    if vsl in _RDMA_INSTANCES:
        return True
    elif any(vsl.endswith(x) for x in _RDMA_INSTANCE_SUFFIXES):
        return True
    return False


def is_gpu_pool(vm_size: str) -> bool:
    """Check if pool is GPU capable
    :param vm_size: vm size
    :return: if gpus are present
    """
    vsl = vm_size.lower()
    return any(vsl.startswith(x) for x in _GPU_INSTANCE_PREFIXES)


def get_temp_disk_for_node_agent(node_agent: str) -> str:
    """Get temp disk location for node agent
    :param node_agent: node agent
    :return: temp disk location
    """
    if node_agent.startswith('batch.node.unbuntu'):
        return '/mnt'
    elif node_agent.startswith('batch.node.windows'):
        return 'D:\\batch'
    else:
        return '/mnt/resource'


class PoolConstraints():
    def __init__(self, constraints: Dict[str, Any]) -> None:
        autoscale = constraints.get('autoscale', {})
        self.autoscale_allow = autoscale.get('allow')
        self.autoscale_exclusive = autoscale.get('exclusive')
        self.custom_image_arm_id = constraints.get('custom_image_arm_id')
        self.location = constraints.get('location')
        lp = constraints.get('low_priority_nodes', {})
        self.low_priority_nodes_allow = lp.get('allow')
        self.low_priority_nodes_exclusive = lp.get('exclusive')
        matb = constraints.get('max_active_task_backlog', {})
        self.max_active_task_backlog_ratio = matb.get('ratio')
        self.max_active_task_backlog_autoscale_exempt = matb.get(
            'autoscale_exempt')
        self.native = constraints.get('native')
        self.virtual_network_arm_id = constraints.get('virtual_network_arm_id')
        self.windows = constraints.get('windows')
        self.registries = constraints.get('registries')


class ComputeNodeConstraints():
    def __init__(self, constraints: Dict[str, Any]) -> None:
        self.vm_size = constraints.get('vm_size')
        cores = constraints.get('cores', {})
        self.cores = cores.get('amount')
        if self.cores is not None:
            self.cores = int(self.cores)
        self.core_variance = cores.get('schedulable_variance')
        memory = constraints.get('memory', {})
        self.memory = memory.get('amount')
        if self.memory is not None:
            # normalize to MB
            suffix = self.memory[-1].lower()
            self.memory = int(self.memory[:-1])
            if suffix == 'b':
                self.memory /= _MEGABYTE
            elif suffix == 'k':
                self.memory /= 1024
            elif suffix == 'g':
                self.memory *= 1024
            elif suffix == 't':
                self.memory *= _MEGABYTE
            else:
                raise ValueError(
                    'invalid memory constraint suffix: {}'.format(suffix))
        self.memory_variance = memory.get('schedulable_variance')
        self.exclusive = constraints.get('exclusive')
        self.gpu = constraints.get('gpu')
        self.infiniband = constraints.get('infiniband')


class TaskConstraints():
    def __init__(self, constraints: Dict[str, Any]) -> None:
        self.auto_complete = constraints.get('auto_complete')
        self.has_multi_instance = constraints.get('has_multi_instance')
        self.has_task_dependencies = constraints.get('has_task_dependencies')
        instance_counts = constraints.get('instance_counts', {})
        self.instance_counts_max = instance_counts.get('max')
        self.instance_counts_total = instance_counts.get('total')
        self.merge_task_id = constraints.get('merge_task_id')
        self.tasks_per_recurrence = constraints.get('tasks_per_recurrence')


class Constraints():
    def __init__(self, constraints: Dict[str, Any]) -> None:
        self.pool = PoolConstraints(constraints['pool'])
        self.compute_node = ComputeNodeConstraints(constraints['compute_node'])
        self.task = TaskConstraints(constraints['task'])


class TaskNaming():
    def __init__(self, naming: Dict[str, Any]) -> None:
        self.prefix = naming.get('prefix')
        self.padding = naming.get('padding')


class Credentials():
    def __init__(self, config: Dict[str, Any]) -> None:
        """Ctor for Credentials
        :param config: configuration
        """
        # set attr from config
        self.storage_account = config['storage']['account']
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
            resource_id: str=None
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
        prefix = config['storage']['entity_prefix']
        self.queue_prefix = '{}fed'.format(prefix)
        self.table_name_global = '{}fedglobal'.format(prefix)
        self.table_name_jobs = '{}fedjobs'.format(prefix)
        self.blob_container_data_prefix = '{}fed'.format(prefix)
        self.blob_container_name_global = '{}fedglobal'.format(prefix)
        self.file_share_logging = '{}fedlogs'.format(prefix)
        self._batch_client_lock = threading.Lock()
        self.batch_clients = {}
        # create credentials
        self.creds = Credentials(config)
        # create clients
        self.compute_client = self._create_compute_client()
        self.blob_client = self._create_blob_client()
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
    def logger_level(self) -> str:
        return self._config['logging']['level']

    @property
    def logger_persist(self) -> bool:
        return self._config['logging']['persistence']

    @property
    def logger_filename(self) -> bool:
        return self._config['logging']['filename']

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

    def _create_blob_client(self) -> azure.storage.blob.BlockBlobService:
        """Create a blob client for the given storage account
        :return: block blob client
        """
        return azure.storage.blob.BlockBlobService(
            account_name=self.creds.storage_account,
            account_key=self.creds.storage_account_key,
            endpoint_suffix=self.creds.storage_account_ep,
        )

    def _create_compute_client(
            self
    ) -> azure.mgmt.compute.ComputeManagementClient:
        """Create a compute mgmt client
        :return: compute client
        """
        client = azure.mgmt.compute.ComputeManagementClient(
            self.creds.arm_creds, self.creds.sub_id,
            base_url=self.creds.cloud.endpoints.resource_manager)
        return client

    def batch_client(
            self,
            batch_account: str,
            service_url: str
    ) -> azure.batch.BatchServiceClient:
        """Get/create batch client
        :param batch_account: batch account name
        :param service_url: service url
        :return: batch client
        """
        with self._batch_client_lock:
            try:
                return self.batch_clients[batch_account]
            except KeyError:
                client = azure.batch.BatchServiceClient(
                    self.creds.batch_creds, base_url=service_url)
                self._modify_client_for_retry_and_user_agent(client)
                self.batch_clients[batch_account] = client
                logger.debug('batch client created for account: {}'.format(
                    batch_account))
                return client


class ComputeServiceHandler():
    def __init__(self, service_proxy: ServiceProxy) -> None:
        """Ctor for Compute Service handler
        :param service_proxy: ServiceProxy
        """
        self.service_proxy = service_proxy
        self._vm_sizes_lock = threading.Lock()
        self._queried_locations = set()
        self._vm_sizes = {}

    def populate_vm_sizes_from_location(self, location: str) -> None:
        """Populate VM sizes for a location
        :param location: location
        """
        location = location.lower()
        with self._vm_sizes_lock:
            if location in self._queried_locations:
                return
        vmsizes = list(
            self.service_proxy.compute_client.virtual_machine_sizes.list(
                location)
        )
        with self._vm_sizes_lock:
            for vmsize in vmsizes:
                name = vmsize.name.lower()
                if name in self._vm_sizes:
                    continue
                self._vm_sizes[name] = vmsize
            self._queried_locations.add(location)

    def get_vm_size(
            self,
            vm_size: str
    ) -> 'azure.mgmt.compute.models.VirtualMachineSize':
        """Get VM Size information
        :param vm_size: name of VM size
        """
        with self._vm_sizes_lock:
            return self._vm_sizes[vm_size.lower()]


class BatchServiceHandler():
    def __init__(self, service_proxy: ServiceProxy) -> None:
        """Ctor for Federation Batch handler
        :param service_proxy: ServiceProxy
        """
        self.service_proxy = service_proxy

    def get_pool_full_update(
            self,
            batch_account: str,
            service_url: str,
            pool_id: str,
    ) -> batchmodels.CloudPool:
        client = self.service_proxy.batch_client(batch_account, service_url)
        try:
            return client.pool.get(pool_id)
        except batchmodels.BatchErrorException as e:
            pass
        return None

    def get_node_state_counts(
            self,
            batch_account: str,
            service_url: str,
            pool_id: str,
    ) -> batchmodels.PoolNodeCounts:
        client = self.service_proxy.batch_client(batch_account, service_url)
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
                    'no node counts for pool {} (account={} '
                    'service_url={})'.format(
                        pool_id, batch_account, service_url))
            return nc[0]
        except batchmodels.BatchErrorException as e:
            logger.error(
                'could not retrieve pool {} node counts (account={} '
                'service_url={})'.format(pool_id, batch_account, service_url))

    def immediately_evaluate_autoscale(
            self,
            batch_account: str,
            service_url: str,
            pool_id: str,
    ) -> None:
        # retrieve current autoscale
        client = self.service_proxy.batch_client(batch_account, service_url)
        try:
            pool = client.pool.get(pool_id)
            if not pool.enable_auto_scale:
                logger.warning(
                    'cannot immediately evaluate autoscale on pool {} as '
                    'autoscale is not enabled (batch_account={} '
                    'service_url={})'.format(
                        pool_id, batch_account, service_url))
                return
            client.pool.enable_auto_scale(
                pool_id=pool.id,
                auto_scale_formula=pool.auto_scale_formula,
                auto_scale_evaluation_interval=pool.
                auto_scale_evaluation_interval,
            )
        except Exception as exc:
            logger.exception(str(exc))
        else:
            logger.debug(
                'autoscale enabled for pool {} interval={} (batch_account={} '
                'service_url={})'.format(
                    pool_id, pool.auto_scale_evaluation_interval,
                    batch_account, service_url))

    def add_job_schedule(
            self,
            batch_account: str,
            service_url: str,
            jobschedule: batchmodels.JobScheduleAddParameter,
    ) -> None:
        client = self.service_proxy.batch_client(batch_account, service_url)
        client.job_schedule.add(jobschedule)

    def get_job(
            self,
            batch_account: str,
            service_url: str,
            job_id: str,
    ) -> batchmodels.CloudJob:
        client = self.service_proxy.batch_client(batch_account, service_url)
        return client.job.get(job_id)

    def add_job(
            self,
            batch_account: str,
            service_url: str,
            job: batchmodels.JobAddParameter,
    ) -> None:
        client = self.service_proxy.batch_client(batch_account, service_url)
        client.job.add(job)

    async def delete_or_terminate_job(
            self,
            batch_account: str,
            service_url: str,
            job_id: str,
            delete: bool,
            is_job_schedule: bool,
            wait: bool=False,
    ) -> None:
        action = 'delete' if delete else 'terminate'
        cstate = (
            batchmodels.JobScheduleState.completed if is_job_schedule else
            batchmodels.JobState.completed
        )
        client = self.service_proxy.batch_client(batch_account, service_url)
        iface = client.job_schedule if is_job_schedule else client.job
        logger.debug('{} {} {} (account={} service_url={})'.format(
            action, 'job schedule' if is_job_schedule else 'job',
            job_id, batch_account, service_url))
        try:
            if delete:
                iface.delete(job_id)
            else:
                iface.terminate(job_id)
        except batchmodels.batch_error.BatchErrorException as exc:
            if delete:
                if ('does not exist' in exc.message.value or
                        (not wait and
                         'marked for deletion' in exc.message.value)):
                    return
            else:
                if ('completed state' in exc.message.value or
                        'marked for deletion' in exc.message.value):
                    return
        # wait for job to delete/terminate
        if wait:
            while True:
                try:
                    _job = iface.get(job_id)
                    if _job.state == cstate:
                        break
                except batchmodels.batch_error.BatchErrorException as exc:
                    if 'does not exist' in exc.message.value:
                        break
                    else:
                        raise
                await asyncio.sleep(1)

    def _format_generic_task_id(
            self, prefix: str, padding: int, tasknum: int) -> str:
        """Format a generic task id from a task number
        :param prefix: prefix
        :param padding: zfill task number
        :param tasknum: task number
        :return: generic task id
        """
        return '{}{}'.format(prefix, str(tasknum).zfill(padding))

    def regenerate_next_generic_task_id(
            self,
            batch_account: str,
            service_url: str,
            job_id: str,
            naming: TaskNaming,
            current_task_id: str,
            last_task_id: Optional[str]=None,
            tasklist: Optional[List[str]]=None,
            is_merge_task: Optional[bool]=False
    ) -> Tuple[List[str], str]:
        """Regenerate the next generic task id
        :param batch_account: batch account
        :param service_url: service url
        :param job_id: job id
        :param naming: naming convention
        :param current_task_id: current task id
        :param tasklist: list of committed and uncommitted tasks in job
        :param is_merge_task: is merge task
        :return: (list of task ids for job, next generic docker task id)
        """
        # get prefix and padding settings
        prefix = naming.prefix
        if is_merge_task:
            prefix = 'merge-{}'.format(prefix)
        if not current_task_id.startswith(prefix):
            return tasklist, current_task_id
        delimiter = prefix if is_not_empty(prefix) else ' '
        client = self.service_proxy.batch_client(batch_account, service_url)
        # get filtered, sorted list of generic docker task ids
        try:
            if tasklist is None:
                tasklist = client.task.list(
                    job_id,
                    task_list_options=batchmodels.TaskListOptions(
                        filter='startswith(id, \'{}\')'.format(prefix)
                        if is_not_empty(prefix) else None,
                        select='id'))
                tasklist = [x.id for x in tasklist]
            tasknum = sorted(
                [int(x.split(delimiter)[-1]) for x in tasklist])[-1] + 1
        except (batchmodels.batch_error.BatchErrorException, IndexError,
                TypeError):
            tasknum = 0
        id = self._format_generic_task_id(prefix, naming.padding, tasknum)
        while id in tasklist:
            try:
                if (last_task_id is not None and
                        last_task_id.startswith(prefix)):
                    tasknum = int(last_task_id.split(delimiter)[-1])
                    last_task_id = None
            except Exception:
                last_task_id = None
            tasknum += 1
            id = self._format_generic_task_id(prefix, naming.padding, tasknum)
        return tasklist, id

    def _submit_task_sub_collection(
            self,
            client: azure.batch.BatchServiceClient,
            job_id: str,
            start: int,
            end: int,
            slice: int,
            all_tasks: List[str],
            task_map: Dict[str, batchmodels.TaskAddParameter]
    ) -> bool:
        """Submits a sub-collection of tasks, do not call directly
        :param client: batch client
        :param job_id: job to add to
        :param start: start offset, includsive
        :param end: end offset, exclusive
        :param slice: slice width
        :param all_tasks: list of all task ids
        :param task_map: task collection map to add
        """
        ret = True
        initial_slice = slice
        while True:
            chunk_end = start + slice
            if chunk_end > end:
                chunk_end = end
            chunk = all_tasks[start:chunk_end]
            logger.debug('submitting {} tasks ({} -> {}) to job {}'.format(
                len(chunk), start, chunk_end - 1, job_id))
            try:
                results = client.task.add_collection(job_id, chunk)
            except batchmodels.BatchErrorException as e:
                if e.error.code == 'RequestBodyTooLarge':
                    # collection contents are too large, reduce and retry
                    if slice == 1:
                        raise
                    slice = slice >> 1
                    if slice < 1:
                        slice = 1
                    logger.error(
                        ('task collection slice was too big, retrying with '
                         'slice={}').format(slice))
                    continue
            else:
                # go through result and retry just failed tasks
                while True:
                    retry = []
                    for result in results.value:
                        if (result.status ==
                                batchmodels.TaskAddStatus.client_error):
                            de = None
                            if result.error.values is not None:
                                de = [
                                    '{}: {}'.format(x.key, x.value)
                                    for x in result.error.values
                                ]
                            logger.error(
                                ('skipping retry of adding task {} as it '
                                 'returned a client error (code={} '
                                 'message={} {}) for job {}').format(
                                     result.task_id, result.error.code,
                                     result.error.message,
                                     ' '.join(de) if de is not None else '',
                                     job_id))
                            ret = False
                        elif (result.status ==
                              batchmodels.TaskAddStatus.server_error):
                            retry.append(task_map[result.task_id])
                    if len(retry) > 0:
                        logger.debug(
                            'retrying adding {} tasks to job {}'.format(
                                len(retry), job_id))
                        results = client.task.add_collection(job_id, retry)
                    else:
                        break
            if chunk_end == end:
                break
            start = chunk_end
            slice = initial_slice
        return ret

    def add_task_collection(
            self,
            batch_account: str,
            service_url: str,
            job_id: str,
            task_map: Dict[str, batchmodels.TaskAddParameter]
    ) -> None:
        """Add a collection of tasks to a job
        :param batch_account: batch account
        :param service_url: service url
        :param job_id: job to add to
        :param task_map: task collection map to add
        """
        client = self.service_proxy.batch_client(batch_account, service_url)
        all_tasks = list(task_map.values())
        num_tasks = len(all_tasks)
        if num_tasks == 0:
            logger.debug(
                'no tasks detected in task_map for job {} for '
                '(batch_account={} service-url={})'.format(
                    job_id, batch_account, service_url))
            return
        slice = 100  # can only submit up to 100 tasks at a time
        task_futures = []
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=_MAX_EXECUTOR_WORKERS) as executor:
            for start in range(0, num_tasks, slice):
                end = start + slice
                if end > num_tasks:
                    end = num_tasks
                task_futures.append(executor.submit(
                    self._submit_task_sub_collection, client, job_id, start,
                    end, end - start, all_tasks, task_map))
        # throw exceptions from any failure
        try:
            errors = any(not x.result() for x in task_futures)
        except Exception as exc:
            logger.exception(str(exc))
            errors = True
        if errors:
            logger.error(
                'failures detected in task submission of {} tasks for '
                'job {} for (batch_account={} service_url={})'.format(
                    num_tasks, job_id, batch_account, service_url))
        else:
            logger.info(
                'submitted all {} tasks to job {} for (batch_account={} '
                'service_url={})'.format(
                    num_tasks, job_id, batch_account, service_url))

    def set_auto_complete_on_job(
            self,
            batch_account: str,
            service_url: str,
            job_id: str
    ) -> None:
        client = self.service_proxy.batch_client(batch_account, service_url)
        client.job.patch(
            job_id=job_id,
            job_patch_parameter=batchmodels.JobPatchParameter(
                on_all_tasks_complete=batchmodels.
                OnAllTasksComplete.terminate_job
            ),
        )
        logger.debug('set auto-completion for job {}'.format(job_id))

    def aggregate_active_task_count_on_pool(
            self,
            batch_account: str,
            service_url: str,
            pool_id: str,
    ) -> int:
        total_active = 0
        client = self.service_proxy.batch_client(batch_account, service_url)
        try:
            jobs = list(client.job.list(
                job_list_options=batchmodels.JobListOptions(
                    filter='(state eq \'active\') and (executionInfo/poolId '
                    'eq \'{}\')'.format(pool_id),
                    select='id',
                ),
            ))
        except batchmodels.batch_error.BatchErrorException as exc:
            logger.exception(str(exc))
        else:
            if len(jobs) == 0:
                return total_active
            tc_futures = []
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers_for_executor(jobs)) as executor:
                for job in jobs:
                    tc_futures.append(executor.submit(
                        client.job.get_task_counts, job.id))
            for tc in tc_futures:
                try:
                    total_active += tc.result().active
                except Exception as exc:
                    logger.exception(str(exc))
        return total_active


class FederationDataHandler():
    _GLOBAL_LOCK_BLOB = 'global.lock'
    _ALL_FEDERATIONS_PK = '!!FEDERATIONS'
    _FEDERATION_ACTIONS_PREFIX_PK = '!!ACTIONS'
    _BLOCKED_FEDERATION_ACTIONS_PREFIX_PK = '!!ACTIONS.BLOCKED'
    _MAX_SEQUENCE_ID_PROPERTIES = 15
    _MAX_SEQUENCE_IDS_PER_PROPERTY = 975
    _MAX_STR_ENTITY_PROPERTY_LENGTH = 32174

    def __init__(self, service_proxy: ServiceProxy) -> None:
        """Ctor for Federation data handler
        :param service_proxy: ServiceProxy
        """
        self.service_proxy = service_proxy
        self.lease_id = None
        try:
            self.scheduling_blackout = int(
                self.service_proxy._config[
                    'scheduling']['after_success']['blackout_interval'])
        except KeyError:
            self.scheduling_blackout = 15
        try:
            self.scheduling_evaluate_autoscale = self.service_proxy._config[
                'scheduling']['after_success']['evaluate_autoscale']
        except KeyError:
            self.scheduling_evaluate_autoscale = True

    @property
    def has_global_lock(self) -> bool:
        return self.lease_id is not None

    def lease_global_lock(
        self,
        loop: asyncio.BaseEventLoop,
    ) -> None:
        try:
            if self.lease_id is None:
                logger.debug('acquiring blob lease on {}'.format(
                    self._GLOBAL_LOCK_BLOB))
                self.lease_id = \
                    self.service_proxy.blob_client.acquire_blob_lease(
                        self.service_proxy.blob_container_name_global,
                        self._GLOBAL_LOCK_BLOB, lease_duration=15)
                logger.debug('blob lease acquired on {}'.format(
                    self._GLOBAL_LOCK_BLOB))
            else:
                self.lease_id = \
                    self.service_proxy.blob_client.renew_blob_lease(
                        self.service_proxy.blob_container_name_global,
                        self._GLOBAL_LOCK_BLOB, self.lease_id)
        except Exception:
            self.lease_id = None
        if self.lease_id is None:
            logger.error('could not acquire/renew lease on {}'.format(
                self._GLOBAL_LOCK_BLOB))
        loop.call_later(5, self.lease_global_lock, loop)

    def release_global_lock(self) -> None:
        if self.lease_id is not None:
            try:
                self.service_proxy.blob_client.release_blob_lease(
                    self.service_proxy.blob_container_name_global,
                    self._GLOBAL_LOCK_BLOB, self.lease_id)
            except azure.common.AzureConflictHttpError:
                self.lease_id = None

    def mount_file_storage(self) -> Optional[pathlib.Path]:
        if not self.service_proxy.logger_persist:
            logger.warning('logging persistence is disabled')
            return None
        # create logs directory
        log_path = self.service_proxy.batch_shipyard_var_path / 'logs'
        log_path.mkdir(exist_ok=True)
        # mount
        cmd = (
            'mount -t cifs //{sa}.file.{ep}/{share} {hmp} -o '
            'vers=3.0,username={sa},password={sakey},_netdev,serverino'
        ).format(
            sa=self.service_proxy.creds.storage_account,
            ep=self.service_proxy.creds.storage_account_ep,
            share=self.service_proxy.file_share_logging,
            hmp=log_path,
            sakey=self.service_proxy.creds.storage_account_key,
        )
        logger.debug('attempting to mount file share for logging persistence')
        try:
            output = subprocess.check_output(
                cmd, shell=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            logger.error('subprocess run error: {} exited with {}'.format(
                exc.cmd, exc.returncode))
            logger.error('stderr: {}'.format(exc.stderr))
            logger.error('stdout: {}'.format(exc.stdout))
            raise
        else:
            logger.debug(output)
        return log_path

    def unmount_file_storage(self) -> None:
        if not self.service_proxy.logger_persist:
            return
        log_path = self.service_proxy.batch_shipyard_var_path / 'logs'
        cmd = 'umount {hmp}'.format(hmp=log_path)
        logger.debug(
            'attempting to unmount file share for logging persistence')
        output = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.PIPE)
        logger.debug(output)

    def set_log_configuration(self, log_path: pathlib.Path) -> None:
        global logger
        # remove existing handlers
        handlers = logger.handlers[:]
        for handler in handlers:
            handler.close()
            logger.removeHandler(handler)
        # set level
        if self.service_proxy.logger_level == 'info':
            logger.setLevel(logging.INFO)
        elif self.service_proxy.logger_level == 'warning':
            logger.setLevel(logging.WARNING)
        elif self.service_proxy.logger_level == 'error':
            logger.setLevel(logging.ERROR)
        elif self.service_proxy.logger_level == 'critical':
            logger.setLevel(logging.CRITICAL)
        else:
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
        # set log file
        if log_path is None:
            logger.warning('not setting logfile as persistence is disabled')
        else:
            # log to selected log level file
            logfname = pathlib.Path(self.service_proxy.logger_filename)
            logfile = log_path / '{}-{}{}'.format(
                logfname.stem, self.service_proxy.logger_level,
                logfname.suffix)
            logfile.parent.mkdir(exist_ok=True)
            handler_logfile = logging.handlers.RotatingFileHandler(
                str(logfile), maxBytes=33554432, backupCount=20000,
                encoding='utf-8')
            handler_logfile.setFormatter(formatter)
            logger.addHandler(handler_logfile)
            az_storage_logger.addHandler(handler_logfile)
            az_cosmosdb_logger.addHandler(handler_logfile)
            # always log to error file
            if self.service_proxy.logger_level != 'error':
                logfile_err = log_path / '{}-error{}'.format(
                    logfname.stem, logfname.suffix)
                logfile_err.parent.mkdir(exist_ok=True)
                handler_logfile_err = logging.handlers.RotatingFileHandler(
                    str(logfile_err), maxBytes=33554432, backupCount=10000,
                    encoding='utf-8')
                handler_logfile_err.setFormatter(formatter)
                handler_logfile_err.setLevel(logging.ERROR)
                logger.addHandler(handler_logfile_err)

    def get_all_federations(self) -> List[azure.cosmosdb.table.Entity]:
        """Get all federations"""
        return self.service_proxy.table_client.query_entities(
            self.service_proxy.table_name_global,
            filter='PartitionKey eq \'{}\''.format(self._ALL_FEDERATIONS_PK))

    def get_all_pools_for_federation(
            self,
            fedhash: str
    ) -> List[azure.cosmosdb.table.Entity]:
        """Get all pools for a federation
        :param fedhash: federation hash
        """
        return self.service_proxy.table_client.query_entities(
            self.service_proxy.table_name_global,
            filter='PartitionKey eq \'{}\''.format(fedhash))

    def get_pool_for_federation(
            self,
            fedhash: str,
            poolhash: str,
    ) -> Optional[azure.cosmosdb.table.Entity]:
        try:
            return self.service_proxy.table_client.get_entity(
                self.service_proxy.table_name_global, fedhash, poolhash)
        except azure.common.AzureMissingResourceHttpError:
            return None

    def generate_pk_rk_for_job_location_entity(
            self,
            fedhash: str,
            job_id: str,
            pool: 'FederationPool',
    ) -> Tuple[str, str]:
        pk = '{}${}'.format(fedhash, hash_string(job_id))
        rk = hash_string('{}${}'.format(pool.service_url, pool.pool_id))
        return pk, rk

    def get_location_entity_for_job(
            self,
            fedhash: str,
            job_id: str,
            pool: 'FederationPool',
    ) -> Optional[azure.cosmosdb.table.Entity]:
        pk, rk = self.generate_pk_rk_for_job_location_entity(
            fedhash, job_id, pool)
        try:
            return self.service_proxy.table_client.get_entity(
                self.service_proxy.table_name_jobs, pk, rk)
        except azure.common.AzureMissingResourceHttpError:
            return None

    def location_entities_exist_for_job(
            self,
            fedhash: str,
            job_id: str,
    ) -> bool:
        try:
            entities = self.service_proxy.table_client.query_entities(
                self.service_proxy.table_name_jobs,
                filter='PartitionKey eq \'{}${}\''.format(
                    fedhash, hash_string(job_id))
            )
            for ent in entities:
                return True
        except azure.common.AzureMissingResourceHttpError:
            pass
        return False

    def insert_or_update_entity_with_etag_for_job(
            self,
            entity: Dict[str, Any],
    ) -> bool:
        if 'etag' not in entity:
            try:
                self.service_proxy.table_client.insert_entity(
                    self.service_proxy.table_name_jobs, entity=entity)
                return True
            except azure.common.AzureConflictHttpError:
                pass
        else:
            etag = entity['etag']
            entity.pop('etag')
            try:
                self.service_proxy.table_client.update_entity(
                    self.service_proxy.table_name_jobs, entity=entity,
                    if_match=etag)
                return True
            except azure.common.AzureConflictHttpError:
                pass
            except azure.common.AzureHttpError as ex:
                if ex.status_code != 412:
                    raise
        return False

    def delete_location_entity_for_job(
            self,
            entity: Dict[str, Any],
    ) -> None:
        try:
            self.service_proxy.table_client.delete_entity(
                self.service_proxy.table_name_jobs, entity['PartitionKey'],
                entity['RowKey'])
        except azure.common.AzureMissingResourceHttpError:
            pass

    def get_all_location_entities_for_job(
            self,
            fedhash: str,
            job_id: str,
    ) -> Optional[List[azure.cosmosdb.table.Entity]]:
        try:
            return self.service_proxy.table_client.query_entities(
                self.service_proxy.table_name_jobs,
                filter='PartitionKey eq \'{}${}\''.format(
                    fedhash, hash_string(job_id))
            )
        except azure.common.AzureMissingResourceHttpError:
            return None

    def delete_action_entity_for_job(
            self,
            entity: Dict[str, Any],
    ) -> None:
        try:
            self.service_proxy.table_client.delete_entity(
                self.service_proxy.table_name_jobs, entity['PartitionKey'],
                entity['RowKey'], if_match=entity['etag'])
        except azure.common.AzureMissingResourceHttpError:
            pass

    def get_messages_from_federation_queue(
            self,
            fedhash: str
    ) -> List[azure.storage.queue.models.QueueMessage]:
        queue_name = '{}-{}'.format(
            self.service_proxy.queue_prefix, fedhash)
        return self.service_proxy.queue_client.get_messages(
            queue_name, num_messages=32, visibility_timeout=1)

    def _get_sequence_entity_for_job(
            self,
            fedhash: str,
            job_id: str
    ) -> azure.cosmosdb.table.Entity:
        return self.service_proxy.table_client.get_entity(
            self.service_proxy.table_name_jobs,
            '{}${}'.format(self._FEDERATION_ACTIONS_PREFIX_PK, fedhash),
            hash_string(job_id))

    def get_first_sequence_id_for_job(
            self,
            fedhash: str,
            job_id: str
    ) -> str:
        try:
            entity = self._get_sequence_entity_for_job(fedhash, job_id)
        except azure.common.AzureMissingResourceHttpError:
            return None
        else:
            try:
                return entity['Sequence0'].split(',')[0]
            except Exception:
                return None

    def pop_and_pack_sequence_ids_for_job(
            self,
            fedhash: str,
            job_id: str,
    ) -> azure.cosmosdb.table.Entity:
        entity = self._get_sequence_entity_for_job(fedhash, job_id)
        seq = []
        for i in range(0, self._MAX_SEQUENCE_ID_PROPERTIES):
            prop = 'Sequence{}'.format(i)
            if prop in entity and is_not_empty(entity[prop]):
                seq.extend(entity[prop].split(','))
        seq.pop(0)
        for i in range(0, self._MAX_SEQUENCE_ID_PROPERTIES):
            prop = 'Sequence{}'.format(i)
            start = i * self._MAX_SEQUENCE_IDS_PER_PROPERTY
            end = start + self._MAX_SEQUENCE_IDS_PER_PROPERTY
            if end > len(seq):
                end = len(seq)
            if start < end:
                entity[prop] = ','.join(seq[start:end])
            else:
                entity[prop] = None
        return entity, len(seq) == 0

    def dequeue_sequence_id_from_federation_sequence(
            self,
            delete_message: bool,
            fedhash: str,
            msg_id: str,
            pop_receipt: str,
            target: str,
    ) -> None:
        # pop first item off table sequence
        if is_not_empty(target):
            while True:
                entity, empty_seq = self.pop_and_pack_sequence_ids_for_job(
                    fedhash, target)
                # see if there are no job location entities
                if (empty_seq and not self.location_entities_exist_for_job(
                        fedhash, target)):
                    # delete entity
                    self.delete_action_entity_for_job(entity)
                    logger.debug(
                        'deleted target {} action entity from '
                        'federation {}'.format(target, fedhash))
                    break
                else:
                    # merge update
                    if self.insert_or_update_entity_with_etag_for_job(
                            entity):
                        logger.debug(
                            'upserted target {} sequence to '
                            'federation {}'.format(target, fedhash))
                        break
                    else:
                        logger.debug(
                            'conflict upserting target {} sequence to '
                            'federation {}'.format(target, fedhash))
        # dequeue message
        if delete_message:
            queue_name = '{}-{}'.format(
                self.service_proxy.queue_prefix, fedhash)
            self.service_proxy.queue_client.delete_message(
                queue_name, msg_id, pop_receipt)

    def add_blocked_action_for_job(
            self,
            fedhash: str,
            target: str,
            unique_id: str,
            num_tasks: int,
            reason: str,
    ) -> None:
        entity = {
            'PartitionKey': '{}${}'.format(
                self._BLOCKED_FEDERATION_ACTIONS_PREFIX_PK, fedhash),
            'RowKey': hash_string(target),
            'UniqueId': unique_id,
            'Id': target,
            'NumTasks': num_tasks,
            'Reason': reason,
        }
        self.service_proxy.table_client.insert_or_replace_entity(
            self.service_proxy.table_name_jobs, entity)

    def remove_blocked_action_for_job(
            self,
            fedhash: str,
            target: str
    ) -> None:
        pk = '{}${}'.format(
            self._BLOCKED_FEDERATION_ACTIONS_PREFIX_PK, fedhash)
        rk = hash_string(target)
        try:
            self.service_proxy.table_client.delete_entity(
                self.service_proxy.table_name_jobs, pk, rk)
        except azure.common.AzureMissingResourceHttpError:
            pass

    def _create_blob_client(self, sa, ep, sas):
        return azure.storage.blob.BlockBlobService(
            account_name=sa,
            sas_token=sas,
            endpoint_suffix=ep
        )

    def construct_blob_url(
            self,
            fedhash: str,
            unique_id: str
    ) -> str:
        return (
            'https://{sa}.blob.{ep}/{prefix}-{fedhash}/messages/{uid}.pickle'
        ).format(
            sa=self.service_proxy.creds.storage_account,
            ep=self.service_proxy.creds.storage_account_ep,
            prefix=self.service_proxy.blob_container_data_prefix,
            fedhash=fedhash,
            uid=unique_id
        )

    def retrieve_blob_data(
            self,
            url: str
    ) -> Tuple[azure.storage.blob.BlockBlobService, str, str, bytes]:
        """Retrieve a blob URL
        :param url: Azure Storage url to retrieve
        :return: blob client, container, blob name, data
        """
        # explode url into parts
        tmp = url.split('/')
        host = tmp[2].split('.')
        sa = host[0]
        ep = '.'.join(host[2:])
        del host
        tmp = '/'.join(tmp[3:]).split('?')
        if len(tmp) > 1:
            sas = tmp[1]
        else:
            sas = None
        tmp = tmp[0].split('/')
        container = tmp[0]
        blob_name = '/'.join(tmp[1:])
        del tmp
        if sas is not None:
            blob_client = self._create_blob_client(sa, ep, sas)
        else:
            blob_client = self.service_proxy.blob_client
        data = blob_client.get_blob_to_bytes(container, blob_name)
        return blob_client, container, blob_name, data.content

    def delete_blob(
            self,
            blob_client: azure.storage.blob.BlockBlobService,
            container: str,
            blob_name: str
    ) -> None:
        blob_client.delete_blob(container, blob_name)


class FederationPool():
    def __init__(
            self,
            batch_account: str,
            service_url: str,
            location: str,
            pool_id: str,
            cloud_pool: batchmodels.CloudPool,
            vm_size: 'azure.mgmt.compute.models.VirtualMachineSize'
    ) -> None:
        self._vm_size = None  # type: str
        self._native = None  # type: bool
        self._cloud_pool = None  # type: batchmodels.CloudPool
        self._pool_last_update = None  # type: datetime.datetime
        self._node_counts = None  # type: batchmodels.PoolNodeCounts
        self._node_counts_last_update = None  # type: datetime.datetime
        self._blackout_end_time = datetime_utcnow(as_string=False)
        self._active_tasks_count = None  # type: int
        self._active_tasks_count_last_update = None  # type: datetime.datetime
        self.batch_account = batch_account
        self.service_url = service_url
        self.location = location.lower()
        self.pool_id = pool_id
        self.cloud_pool = cloud_pool
        self.vm_props = vm_size
        if self.is_valid:
            self._vm_size = self.cloud_pool.vm_size.lower()

    @property
    def cloud_pool(self) -> batchmodels.CloudPool:
        return self._cloud_pool

    @cloud_pool.setter
    def cloud_pool(self, value: batchmodels.CloudPool) -> None:
        self._cloud_pool = value
        if (self._cloud_pool is not None and
                is_not_empty(self._cloud_pool.metadata)):
            for md in self._cloud_pool.metadata:
                if md.name == _POOL_NATIVE_METADATA_NAME:
                    self.native = md.value == '1'
        self._last_update = datetime_utcnow(as_string=False)

    @property
    def native(self) -> bool:
        return self._native

    @native.setter
    def native(self, value: bool) -> None:
        self._native = value

    @property
    def node_counts(self) -> batchmodels.PoolNodeCounts:
        return self._node_counts

    @node_counts.setter
    def node_counts(self, value: batchmodels.PoolNodeCounts) -> None:
        self._node_counts = value
        self._node_counts_last_update = datetime_utcnow(as_string=False)

    @property
    def active_tasks_count(self) -> int:
        return self._active_tasks_count

    @active_tasks_count.setter
    def active_tasks_count(self, value: int) -> None:
        self._active_tasks_count = value
        self._active_tasks_count_last_update = datetime_utcnow(as_string=False)

    @property
    def is_valid(self) -> bool:
        if (self.cloud_pool is not None and self.vm_props is not None and
                datetime_utcnow(as_string=False) > self._blackout_end_time):
            return self.cloud_pool.state == batchmodels.PoolState.active
        return False

    @property
    def pool_requires_update(self) -> bool:
        return (
            not self.is_valid or self._pool_last_update is None or
            (datetime_utcnow() - self._pool_last_update) >
            _MAX_TIMESPAN_POOL_UPDATE
        )

    @property
    def node_counts_requires_update(self) -> bool:
        if not self.is_valid:
            return False
        return (
            self._node_counts_last_update is None or
            (datetime_utcnow() - self._node_counts_last_update) >
            _MAX_TIMESPAN_NODE_COUNTS_UPDATE
        )

    @property
    def active_tasks_count_requires_update(self) -> bool:
        if not self.is_valid:
            return False
        return (
            self._active_tasks_count_last_update is None or
            (datetime_utcnow() - self._active_tasks_count_last_update) >
            _MAX_TIMESPAN_ACTIVE_TASKS_COUNT_UPDATE
        )

    @property
    def schedulable_low_priority_nodes(self) -> Optional[int]:
        if not self.is_valid or self.node_counts is None:
            return None
        return (self.node_counts.low_priority.idle +
                self.node_counts.low_priority.running)

    @property
    def schedulable_dedicated_nodes(self) -> Optional[int]:
        if not self.is_valid or self.node_counts is None:
            return None
        return (self.node_counts.dedicated.idle +
                self.node_counts.dedicated.running)

    @property
    def vm_size(self) -> Optional[str]:
        return self._vm_size

    def has_registry_login(self, registry: str) -> bool:
        if not self.is_valid:
            return None
        if self.native:
            cc = self._cloud_pool.virtual_machine_configuration.\
                container_configuration
            if cc.container_registries is None:
                return None
            for cr in cc.container_registries:
                if is_none_or_empty(cr.registry_server):
                    cmpr = 'dockerhub-{}'.format(cr.user_name)
                else:
                    cmpr = '{}-{}'.format(cr.registry_server, cr.user_name)
                if cmpr == registry:
                    return True
        else:
            if self._cloud_pool.start_task is None:
                return None
            creds = {}
            for ev in self._cloud_pool.start_task.environment_settings:
                if (ev.name.startswith('DOCKER_LOGIN_') and
                        ev.name != 'DOCKER_LOGIN_PASSWORD'):
                    creds[ev.name] = ev.value.split(',')
                    if len(creds) == 2:
                        break
            logins = set()
            print(creds)
            if len(creds) > 0:
                for i in range(0, len(creds['DOCKER_LOGIN_USERNAME'])):
                    srv = creds['DOCKER_LOGIN_SERVER'][i]
                    if is_none_or_empty(srv):
                        srv = 'dockerhub'
                    logins.add('{}-{}'.format(
                        srv, creds['DOCKER_LOGIN_USERNAME'][i]))
                if registry in logins:
                    return True
        return False

    def on_new_tasks_scheduled(
            self,
            bsh: BatchServiceHandler,
            blackout: int,
            evaluate_as: bool
    ) -> None:
        # invalidate count caches
        self._node_counts_last_update = None
        self._active_tasks_count_last_update = None
        # set scheduling blackout time
        if blackout > 0:
            self._blackout_end_time = datetime_utcnow(
                as_string=False) + datetime.timedelta(seconds=blackout)
            logger.debug(
                'blackout time for pool {} updated to {} (batch_account={} '
                'service_url={})'.format(
                    self.pool_id, self._blackout_end_time, self.batch_account,
                    self.service_url))
        # evaluate autoscale now
        if (evaluate_as and self.cloud_pool is not None and
                self.cloud_pool.enable_auto_scale):
            bsh.immediately_evaluate_autoscale(
                self.batch_account, self.service_url, self.pool_id)


class Federation():
    def __init__(self, fedhash: str, fedid: str) -> None:
        self.lock = threading.Lock()
        self.hash = fedhash
        self.id = fedid
        self.pools = {}  # type: Dict[str, FederationPool]

    def update_pool(
            self,
            csh: ComputeServiceHandler,
            bsh: BatchServiceHandler,
            entity: azure.cosmosdb.table.Entity,
            poolset: set,
    ) -> str:
        rk = entity['RowKey']
        exists = False
        with self.lock:
            if rk in self.pools:
                exists = True
                if self.pools[rk].is_valid:
                    poolset.add(rk)
                    return rk
        batch_account = entity['BatchAccount']
        poolid = entity['PoolId']
        service_url = entity['BatchServiceUrl']
        pool = bsh.get_pool_full_update(
            batch_account, service_url, poolid)
        if exists and pool is not None:
            with self.lock:
                self.pools[rk].cloud_pool = pool
                poolset.add(rk)
                return rk
        location = entity['Location']
        csh.populate_vm_sizes_from_location(location)
        vm_size = None
        if pool is not None:
            vm_size = csh.get_vm_size(pool.vm_size)
        fedpool = FederationPool(
            batch_account, service_url, location, poolid, pool, vm_size
        )
        with self.lock:
            poolset.add(rk)
            self.pools[rk] = fedpool
            if self.pools[rk].is_valid:
                logger.info(
                    'valid pool {} id={} to federation {} id={} for '
                    'account {} at location {} size={} ppn={} mem={}'.format(
                        rk, poolid, self.hash, self.id, batch_account,
                        location, fedpool.vm_size,
                        fedpool.vm_props.number_of_cores,
                        fedpool.vm_props.memory_in_mb))
            elif not exists:
                logger.warning(
                    'invalid pool {} id={} to federation {} '
                    'id={} (batch_account={} service_url={})'.format(
                        rk, poolid, self.hash, self.id, fedpool.batch_account,
                        fedpool.service_url))
            return rk

    def trim_orphaned_pools(self, fedpools: set) -> None:
        with self.lock:
            # do not get symmetric difference
            diff = [x for x in self.pools.keys() if x not in fedpools]
            removed = False
            for rk in diff:
                logger.debug(
                    'removing pool {} id={} from federation {} id={}'.format(
                        rk, self.pools[rk].pool_id, self.hash, self.id))
                self.pools.pop(rk)
                removed = True
            if removed:
                pool_ids = [self.pools[x].pool_id for x in self.pools]
                logger.info('active pools in federation {} id={}: {}'.format(
                    self.hash, self.id, ' '.join(pool_ids)))

    def check_pool_in_federation(
            self,
            fdh: FederationDataHandler,
            poolhash: str
    ) -> bool:
        entity = fdh.get_pool_for_federation(self.hash, poolhash)
        return entity is not None

    def _log_constraint_failure(
            self,
            unique_id: str,
            pool_id: str,
            constraint_name: str,
            required_value: Any,
            actual_value: Any,
    ) -> None:
        logger.debug(
            'constraint failure for uid {} on pool {} for fed id {} '
            'fed hash {}: {} requires {} actual {}'.format(
                unique_id, pool_id, self.id, self.hash, constraint_name,
                required_value, actual_value)
        )

    def _filter_pool_with_hard_constraints(
            self,
            pool: FederationPool,
            constraints: Constraints,
            unique_id: str,
    ) -> bool:
        # constraint order matching
        # 0. pool validity
        # 1. location
        # 2. virtual network arm id
        # 3. custom image arm id
        # 4. windows (implies native)
        # 5. native
        # 6. autoscale disallow
        # 7. autoscale exclusive
        # 8. low priority disallow
        # 9. low priority exclusive
        # 10. exclusive
        # 11. vm_size
        # 12. gpu
        # 13. infiniband
        # 14. cores
        # 15. memory
        # 16. multi instance -> inter node
        # 17. registries

        cp = pool.cloud_pool
        # pool validity (this function shouldn't be called with invalid
        # pools, but check anyways)
        if not pool.is_valid:
            logger.debug(
                'pool {} is not valid for filtering of uid {} for fed id {} '
                'fed hash {}'.format(cp.id, unique_id, self.id, self.hash))
            return True
        # location
        if (is_not_empty(constraints.pool.location) and
                constraints.pool.location != pool.location):
            self._log_constraint_failure(
                unique_id, cp.id, 'location', constraints.pool.location,
                pool.location)
            return True
        # virtual network
        if (is_not_empty(constraints.pool.virtual_network_arm_id) and
                (cp.network_configuration is None or
                 constraints.pool.virtual_network_arm_id !=
                 cp.network_configuration.subnet_id.lower())):
            self._log_constraint_failure(
                unique_id, cp.id, 'virtual_network_arm_id',
                constraints.pool.virtual_network_arm_id,
                cp.network_configuration.subnet_id
                if cp.network_configuration is not None else 'none')
            return True
        # custom image
        if (is_not_empty(constraints.pool.custom_image_arm_id) and
                (cp.virtual_machine_configuration is None or
                 constraints.pool.custom_image_arm_id !=
                 cp.virtual_machine_configuration.image_reference.
                 virtual_machine_image_id.lower())):
            self._log_constraint_failure(
                unique_id, cp.id, 'custom_image_arm_id',
                constraints.pool.custom_image_arm_id,
                cp.virtual_machine_configuration.image_reference.
                virtual_machine_image_id
                if cp.virtual_machine_configuration is not None else 'none')
            return True
        # windows
        if (constraints.pool.windows and
                (cp.virtual_machine_configuration is None or
                 not cp.virtual_machine_configuration.
                 node_agent_sku_id.lower().startswith('batch.node.windows'))):
            self._log_constraint_failure(
                unique_id, cp.id, 'windows',
                constraints.pool.windows,
                cp.virtual_machine_configuration.node_agent_sku_id)
            return True
        # native
        if (constraints.pool.native is not None and
                constraints.pool.native != pool.native):
            self._log_constraint_failure(
                unique_id, cp.id, 'native',
                constraints.pool.native, pool.native)
            return True
        # autoscale disallow
        if (constraints.pool.autoscale_allow is not None and
                not constraints.pool.autoscale_allow and
                cp.enable_auto_scale):
            self._log_constraint_failure(
                unique_id, cp.id, 'autoscale_allow',
                constraints.pool.autoscale_allow,
                cp.enable_auto_scale)
            return True
        # autoscale exclusive
        if (constraints.pool.autoscale_exclusive and
                not cp.enable_auto_scale):
            self._log_constraint_failure(
                unique_id, cp.id, 'autoscale_exclusive',
                constraints.pool.autoscale_exclusive,
                cp.enable_auto_scale)
            return True
        # low priority disallow
        if (constraints.pool.low_priority_nodes_allow is not None and
                not constraints.pool.low_priority_nodes_allow and
                cp.target_low_priority_nodes > 0):
            self._log_constraint_failure(
                unique_id, cp.id, 'low_priority_nodes_allow',
                constraints.pool.low_priority_nodes_allow,
                cp.target_low_priority_nodes)
            return True
        # low priority exclusive
        if (constraints.pool.low_priority_nodes_exclusive and
                cp.target_low_priority_nodes == 0 and
                not cp.enable_auto_scale):
            self._log_constraint_failure(
                unique_id, cp.id, 'low_priority_nodes_exclusive',
                constraints.pool.low_priority_nodes_exclusive,
                cp.target_low_priority_nodes)
            return True
        # exclusive
        if constraints.compute_node.exclusive and cp.max_tasks_per_node > 1:
            self._log_constraint_failure(
                unique_id, cp.id, 'exclusive',
                constraints.compute_node.exclusive,
                cp.max_tasks_per_node)
            return True
        # vm size
        if (is_not_empty(constraints.compute_node.vm_size) and
                constraints.compute_node.vm_size != pool.vm_size):
            self._log_constraint_failure(
                unique_id, cp.id, 'vm_size',
                constraints.compute_node.vm_size,
                pool.vm_size)
            return True
        # gpu
        if (constraints.compute_node.gpu is not None and
                constraints.compute_node.gpu != is_gpu_pool(pool.vm_size)):
            self._log_constraint_failure(
                unique_id, cp.id, 'gpu',
                constraints.compute_node.gpu, is_gpu_pool(pool.vm_size))
            return True
        # infiniband
        if (constraints.compute_node.infiniband is not None and
                constraints.compute_node.infiniband != is_rdma_pool(
                    pool.vm_size)):
            self._log_constraint_failure(
                unique_id, cp.id, 'infiniband',
                constraints.compute_node.infiniband,
                is_rdma_pool(pool.vm_size))
            return True
        # cores
        if (constraints.compute_node.cores is not None and
                pool.vm_props is not None):
            # absolute core filtering
            if constraints.compute_node.cores > pool.vm_props.number_of_cores:
                self._log_constraint_failure(
                    unique_id, cp.id, 'cores',
                    constraints.compute_node.cores,
                    pool.vm_props.number_of_cores)
                return True
            # core variance of zero must match the number of cores exactly
            if constraints.compute_node.core_variance == 0:
                if (constraints.compute_node.cores !=
                        pool.vm_props.number_of_cores):
                    self._log_constraint_failure(
                        unique_id, cp.id, 'zero core_variance',
                        constraints.compute_node.cores,
                        pool.vm_props.number_of_cores)
                    return True
            # core variance of None corresponds to no restrictions
            # positive core variance infers maximum core matching
            if (constraints.compute_node.core_variance is not None and
                    constraints.compute_node.core_variance > 0):
                max_cc = constraints.compute_node.cores * (
                    1 + constraints.compute_node.core_variance)
                if pool.vm_props.number_of_cores > max_cc:
                    self._log_constraint_failure(
                        unique_id, cp.id, 'max core_variance',
                        max_cc,
                        pool.vm_props.number_of_cores)
                    return True
        # memory
        if (constraints.compute_node.memory is not None and
                pool.vm_props is not None):
            vm_mem = pool.vm_props.memory_in_mb
            # absolute memory filtering
            if constraints.compute_node.memory > vm_mem:
                self._log_constraint_failure(
                    unique_id, cp.id, 'memory',
                    constraints.compute_node.memory,
                    vm_mem)
                return True
            # memory variance of zero must match the memory amount exactly
            if constraints.compute_node.memory_variance == 0:
                if constraints.compute_node.memory != vm_mem:
                    self._log_constraint_failure(
                        unique_id, cp.id, 'zero memory_variance',
                        constraints.compute_node.memory,
                        vm_mem)
                    return True
            # memory variance of None corresponds to no restrictions
            # positive memory variance infers maximum memory matching
            if (constraints.compute_node.memory_variance is not None and
                    constraints.compute_node.memory_variance > 0):
                max_mem = constraints.compute_node.memory * (
                    1 + constraints.compute_node.memory_variance)
                if vm_mem > max_mem:
                    self._log_constraint_failure(
                        unique_id, cp.id, 'max memory_variance',
                        max_mem,
                        vm_mem)
                    return True
        # multi-instance
        if (constraints.task.has_multi_instance and
                not cp.enable_inter_node_communication):
            self._log_constraint_failure(
                unique_id, cp.id, 'has_multi_instance',
                constraints.task.has_multi_instance,
                cp.enable_inter_node_communication)
            return True
        # registries
        if is_not_empty(constraints.pool.registries):
            for cr in constraints.pool.registries:
                if not pool.has_registry_login(cr):
                    self._log_constraint_failure(
                        unique_id, cp.id, 'registries',
                        cr if is_not_empty(cr) else 'dockerhub',
                        False)
                    return True
        # hard constraint filtering passed
        return False

    def _filter_pool_nodes_with_constraints(
            self,
            pool: FederationPool,
            constraints: Constraints,
            unique_id: str,
    ) -> bool:
        cp = pool.cloud_pool
        # check for dedicated only execution
        if (constraints.pool.low_priority_nodes_allow is not None and
                not constraints.pool.low_priority_nodes_allow):
            # if there are no schedulable dedicated nodes and
            # if no autoscale is allowed or no autoscale formula exists
            if (pool.schedulable_dedicated_nodes == 0 and
                    (not (constraints.pool.autoscale_allow and
                          cp.enable_auto_scale))):
                self._log_constraint_failure(
                    unique_id, cp.id, 'low_priority_nodes_allow',
                    constraints.pool.low_priority_nodes_allow,
                    pool.schedulable_dedicated_nodes)
                return True
        # check for low priority only execution
        if constraints.pool.low_priority_nodes_exclusive:
            # if there are no schedulable low pri nodes and
            # if no autoscale is allowed or no autoscale formula exists
            if (pool.schedulable_low_priority_nodes == 0 and
                    (not (constraints.pool.autoscale_allow and
                          cp.enable_auto_scale))):
                self._log_constraint_failure(
                    unique_id, cp.id, 'low_priority_nodes_allow',
                    constraints.pool.low_priority_nodes_allow,
                    pool.schedulable_dedicated_nodes)
                return True
        # max active task backlog ratio
        if constraints.pool.max_active_task_backlog_ratio is not None:
            schedulable_slots = (
                pool.schedulable_dedicated_nodes +
                pool.schedulable_low_priority_nodes
            ) * cp.max_tasks_per_node
            if schedulable_slots > 0:
                ratio = pool.active_tasks_count / schedulable_slots
            else:
                if (cp.enable_auto_scale and
                        cp.allocation_state ==
                        batchmodels.AllocationState.steady and
                        constraints.pool.
                        max_active_task_backlog_autoscale_exempt):
                    ratio = 0
                else:
                    ratio = None
            if (ratio is None or
                    ratio > constraints.pool.max_active_task_backlog_ratio):
                self._log_constraint_failure(
                    unique_id, cp.id, 'max_active_task_backlog_ratio',
                    constraints.pool.max_active_task_backlog_ratio,
                    ratio)
                return True
        # node constraint filtering passed
        return False

    def _pre_constraint_filter_pool_update(
            self,
            bsh: BatchServiceHandler,
            fdh: FederationDataHandler,
            rk: str,
            active_tasks_count_update: bool,
    ) -> bool:
        pool = self.pools[rk]
        # ensure pool is in federation (pools can be removed between
        # federation updates)
        if self.check_pool_in_federation(fdh, rk):
            # refresh pool
            if pool.pool_requires_update:
                pool.cloud_pool = bsh.get_pool_full_update(
                    pool.batch_account, pool.service_url, pool.pool_id)
            # refresh node state counts
            if pool.node_counts_requires_update:
                pool.node_counts = bsh.get_node_state_counts(
                    pool.batch_account, pool.service_url, pool.pool_id)
            # refresh active task counts
            if (active_tasks_count_update and
                    pool.active_tasks_count_requires_update):
                pool.active_tasks_count = \
                    bsh.aggregate_active_task_count_on_pool(
                        pool.batch_account, pool.service_url, pool.pool_id)
        else:
            logger.warning(
                'pool id {} hash={} not in fed id {} fed hash {}'.format(
                    pool.pool_id, rk, self.id, self.hash))
            return False
        return True

    def _select_pool_for_target_required(
            self,
            unique_id: str,
            using_slots: bool,
            target_required: int,
            allow_autoscale: bool,
            num_pools: Dict[str, int],
            binned: List[str],
            pool_map: Dict[str, Dict[str, int]],
    ) -> Optional[str]:
        logger.debug(
            'pool selection attempt for uid={} using_slots={} '
            'target_required={} allow_autoscale={} num_pools={} '
            'binned={}'.format(
                unique_id, using_slots, target_required, allow_autoscale,
                num_pools, binned))
        # try to match against largest idle pool with sufficient capacity
        if num_pools['idle'] > 0:
            for rk in binned['idle']:
                if pool_map['idle'][rk] >= target_required:
                    return rk
        # try to match against largest avail pool with sufficient capacity
        if num_pools['avail'] > 0:
            for rk in binned['avail']:
                if pool_map['avail'][rk] >= target_required:
                    return rk
        # try to match against any autoscale-enabled pool that is steady
        if allow_autoscale:
            for rk in binned['idle']:
                pool = self.pools[rk]
                if (pool.cloud_pool.enable_auto_scale and
                        pool.cloud_pool.allocation_state ==
                        batchmodels.AllocationState.steady):
                    return rk
            for rk in binned['avail']:
                pool = self.pools[rk]
                if (pool.cloud_pool.enable_auto_scale and
                        pool.cloud_pool.allocation_state ==
                        batchmodels.AllocationState.steady):
                    return rk
        # if using slot scheduling, then attempt to schedule with backlog
        if using_slots:
            # try to match against largest idle pool
            if num_pools['idle'] > 0:
                for rk in binned['idle']:
                    if pool_map['idle'][rk] >= 1:
                        return rk
            # try to match against largest avail pool
            if num_pools['avail'] > 0:
                for rk in binned['avail']:
                    if pool_map['avail'][rk] >= 1:
                        return rk
        return None

    def _greedy_best_fit_match_for_job(
            self,
            num_tasks: int,
            constraints: Constraints,
            unique_id: str,
            dedicated_vms: Dict[str, Dict[str, int]],
            dedicated_slots: Dict[str, Dict[str, int]],
            low_priority_vms: Dict[str, Dict[str, int]],
            low_priority_slots: Dict[str, Dict[str, int]],
    ) -> Optional[str]:
        # calculate pools of each
        num_pools = {
            'vms': {
                'dedicated': {
                    'idle': len(dedicated_vms['idle']),
                    'avail': len(dedicated_vms['avail']),
                },
                'low_priority': {
                    'idle': len(low_priority_vms['idle']),
                    'avail': len(low_priority_vms['avail']),
                }
            },
            'slots': {
                'dedicated': {
                    'idle': len(dedicated_slots['idle']),
                    'avail': len(dedicated_slots['avail']),
                },
                'low_priority': {
                    'idle': len(low_priority_slots['idle']),
                    'avail': len(low_priority_slots['avail']),
                }
            }
        }
        # bin all maps
        binned = {
            'vms': {
                'dedicated': {
                    'idle': sorted(
                        dedicated_vms['idle'],
                        key=dedicated_vms['idle'].get,
                        reverse=True),
                    'avail': sorted(
                        dedicated_vms['avail'],
                        key=dedicated_vms['avail'].get,
                        reverse=True),
                },
                'low_priority': {
                    'idle': sorted(
                        low_priority_vms['idle'],
                        key=low_priority_vms['idle'].get,
                        reverse=True),
                    'avail': sorted(
                        low_priority_vms['avail'],
                        key=low_priority_vms['avail'].get,
                        reverse=True),
                }
            },
            'slots': {
                'dedicated': {
                    'idle': sorted(
                        dedicated_slots['idle'],
                        key=dedicated_slots['idle'].get,
                        reverse=True),
                    'avail': sorted(
                        dedicated_slots['avail'],
                        key=dedicated_slots['avail'].get,
                        reverse=True),
                },
                'low_priority': {
                    'idle': sorted(
                        low_priority_slots['idle'],
                        key=low_priority_slots['idle'].get,
                        reverse=True),
                    'avail': sorted(
                        low_priority_slots['avail'],
                        key=low_priority_slots['avail'].get,
                        reverse=True),
                }
            }
        }
        # scheduling is done by slots (regular tasks) or vms (multi-instance)
        if constraints.task.has_multi_instance:
            total_slots_required = None
            vms_required_per_task = constraints.task.instance_counts_max
        else:
            total_slots_required = constraints.task.instance_counts_total
            vms_required_per_task = None
        # greedy smallest-fit (by vms or slots) matching
        selected = None
        # constraint: dedicated only pools
        if (constraints.pool.low_priority_nodes_allow is not None and
                not constraints.pool.low_priority_nodes_allow):
            if total_slots_required is not None:
                selected = self._select_pool_for_target_required(
                    unique_id, True, total_slots_required,
                    constraints.pool.autoscale_allow,
                    num_pools['slots']['dedicated'],
                    binned['slots']['dedicated'], dedicated_slots)
            else:
                selected = self._select_pool_for_target_required(
                    unique_id, False, vms_required_per_task,
                    constraints.pool.autoscale_allow,
                    num_pools['vms']['dedicated'],
                    binned['vms']['dedicated'], dedicated_vms)
        elif constraints.pool.low_priority_nodes_exclusive:
            # constraint: low priority only pools
            if total_slots_required is not None:
                selected = self._select_pool_for_target_required(
                    unique_id, True, total_slots_required,
                    constraints.pool.autoscale_allow,
                    num_pools['slots']['low_priority'],
                    binned['slots']['low_priority'], low_priority_slots)
            else:
                selected = self._select_pool_for_target_required(
                    unique_id, False, vms_required_per_task,
                    constraints.pool.autoscale_allow,
                    num_pools['vms']['low_priority'],
                    binned['vms']['low_priority'], low_priority_vms)
        else:
            # no constraints, try scheduling on dedicated first, then low pri
            if total_slots_required is not None:
                selected = self._select_pool_for_target_required(
                    unique_id, True, total_slots_required,
                    constraints.pool.autoscale_allow,
                    num_pools['slots']['dedicated'],
                    binned['slots']['dedicated'], dedicated_slots)
                if selected is None:
                    selected = self._select_pool_for_target_required(
                        unique_id, True, total_slots_required,
                        constraints.pool.autoscale_allow,
                        num_pools['slots']['low_priority'],
                        binned['slots']['low_priority'], low_priority_slots)
            else:
                selected = self._select_pool_for_target_required(
                    unique_id, False, vms_required_per_task,
                    constraints.pool.autoscale_allow,
                    num_pools['vms']['dedicated'],
                    binned['vms']['dedicated'], dedicated_vms)
                if selected is None:
                    selected = self._select_pool_for_target_required(
                        unique_id, False, vms_required_per_task,
                        constraints.pool.autoscale_allow,
                        num_pools['vms']['low_priority'],
                        binned['vms']['low_priority'], low_priority_vms)
        return selected

    def find_target_pool_for_job(
            self,
            bsh: BatchServiceHandler,
            fdh: FederationDataHandler,
            num_tasks: int,
            constraints: Constraints,
            blacklist: Set[str],
            unique_id: str,
            target: str,
    ) -> Optional[str]:
        """
        This function should be called with lock already held!
        """
        dedicated_vms = {
            'idle': {},
            'avail': {},
        }
        dedicated_slots = {
            'idle': {},
            'avail': {},
        }
        low_priority_vms = {
            'idle': {},
            'avail': {},
        }
        low_priority_slots = {
            'idle': {},
            'avail': {},
        }
        # check and update pools in parallel
        update_futures = {}
        if len(self.pools) > 0:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers_for_executor(
                        self.pools)) as executor:
                for rk in self.pools:
                    if rk in blacklist:
                        continue
                    update_futures[rk] = executor.submit(
                        self._pre_constraint_filter_pool_update, bsh, fdh, rk,
                        constraints.pool.max_active_task_backlog_ratio
                        is not None
                    )
        # perform constraint filtering
        # TODO optimization -> fast match against last schedule?
        for rk in self.pools:
            pool = self.pools[rk]
            if rk in blacklist:
                continue
            # check if update was successful for pool
            if not update_futures[rk].result():
                continue
            # ensure pool is valid and node counts exist
            if not pool.is_valid or pool.node_counts is None:
                logger.warning(
                    'skipping invalid pool id {} hash={} node counts '
                    'valid={} in fed id {} fed hash {} uid={} '
                    'target={}'.format(
                        pool.pool_id, rk, pool.node_counts is not None,
                        self.id, self.hash, unique_id, target))
                continue
            # hard constraint filtering
            if self._filter_pool_with_hard_constraints(
                    pool, constraints, unique_id):
                blacklist.add(rk)
                continue
            # further constraint matching for nodes
            if self._filter_pool_nodes_with_constraints(
                    pool, constraints, unique_id):
                continue
            # add counts for pre-sort
            if pool.node_counts.dedicated.idle > 0:
                dedicated_vms['idle'][rk] = pool.node_counts.dedicated.idle
                dedicated_slots['idle'][rk] = (
                    pool.node_counts.dedicated.idle *
                    pool.cloud_pool.max_tasks_per_node
                )
            if pool.node_counts.low_priority.idle > 0:
                low_priority_vms['idle'][rk] = (
                    pool.node_counts.low_priority.idle
                )
                low_priority_slots['idle'][rk] = (
                    pool.node_counts.low_priority.idle *
                    pool.cloud_pool.max_tasks_per_node
                )
            # for availbility counts, allow pools to be added to map even
            # with zero nodes if they can autoscale
            if (pool.schedulable_dedicated_nodes > 0 or
                    pool.cloud_pool.enable_auto_scale):
                dedicated_vms['avail'][rk] = pool.schedulable_dedicated_nodes
                dedicated_slots['avail'][rk] = (
                    pool.schedulable_dedicated_nodes *
                    pool.cloud_pool.max_tasks_per_node
                )
            if (pool.schedulable_low_priority_nodes > 0 or
                    pool.cloud_pool.enable_auto_scale):
                low_priority_vms['avail'][rk] = (
                    pool.schedulable_low_priority_nodes
                )
                low_priority_slots['avail'][rk] = (
                    pool.schedulable_low_priority_nodes *
                    pool.cloud_pool.max_tasks_per_node
                )
        del update_futures
        # check for non-availability
        if (len(dedicated_vms['avail']) == 0 and
                len(low_priority_vms['avail']) == 0 and
                not constraints.pool.autoscale_allow):
            logger.error(
                'no available nodes to schedule uid {} target={} in fed {} '
                'fed hash {}'.format(unique_id, target, self.id, self.hash))
            if len(blacklist) == len(self.pools):
                fdh.add_blocked_action_for_job(
                    self.hash, target, unique_id, num_tasks,
                    'Constraint filtering: all pools blacklisted')
            else:
                fdh.add_blocked_action_for_job(
                    self.hash, target, unique_id, num_tasks,
                    'Constraint filtering: no available pools')
            return None
        # perform greedy matching
        schedule = self._greedy_best_fit_match_for_job(
            num_tasks, constraints, unique_id, dedicated_vms, dedicated_slots,
            low_priority_vms, low_priority_slots)
        if schedule is None:
            logger.warning(
                'could not match uid {} target={} in fed {} fed hash {} to '
                'any pool'.format(unique_id, target, self.id, self.hash))
            fdh.add_blocked_action_for_job(
                self.hash, target, unique_id, num_tasks,
                'Pool matching: no available pools or nodes')
        else:
            logger.info(
                'selected pool id {} hash {} for uid {} target={} in fed {} '
                'fed hash {}'.format(
                    self.pools[schedule].pool_id, schedule, unique_id,
                    target, self.id, self.hash))
        return schedule

    async def create_job_schedule(
            self,
            bsh: BatchServiceHandler,
            target_pool: str,
            jobschedule: batchmodels.JobScheduleAddParameter,
            constraints: Constraints,
    ) -> bool:
        """
        This function should be called with lock already held!
        """
        # get pool ref
        pool = self.pools[target_pool]
        # overwrite pool id in job schedule
        jobschedule.job_specification.pool_info.pool_id = pool.pool_id
        # add job schedule
        try:
            logger.info(
                'adding job schedule {} to pool {} (batch_account={} '
                'service_url={})'.format(
                    jobschedule.id, pool.pool_id, pool.batch_account,
                    pool.service_url))
            bsh.add_job_schedule(
                pool.batch_account, pool.service_url, jobschedule)
            success = True
        except batchmodels.batch_error.BatchErrorException as exc:
            if 'marked for deletion' in exc.message.value:
                logger.error(
                    'cannot reuse job shcedule {} being deleted on '
                    'pool {}'.format(jobschedule.id, pool.pool_id))
            elif 'already exists' in exc.message.value:
                logger.error(
                    'cannot reuse existing job shcedule {} on '
                    'pool {}'.format(jobschedule.id, pool.pool_id))
            else:
                logger.exception(str(exc))
                await bsh.delete_or_terminate_job(
                    pool.batch_account, pool.service_url, jobschedule.id,
                    True, True, wait=True)
            success = False
        return success

    async def create_job(
            self,
            bsh: BatchServiceHandler,
            target_pool: str,
            job: batchmodels.JobAddParameter,
            constraints: Constraints,
    ) -> bool:
        """
        This function should be called with lock already held!
        """
        # get pool ref
        pool = self.pools[target_pool]
        # overwrite pool id in job
        job.pool_info.pool_id = pool.pool_id
        # fixup jp env vars
        if (job.job_preparation_task is not None and
                job.job_preparation_task.environment_settings is not None):
            replace_ev = []
            for ev in job.job_preparation_task.environment_settings:
                if ev.name == 'SINGULARITY_CACHEDIR':
                    replace_ev.append(batchmodels.EnvironmentSetting(
                        ev.name,
                        '{}/singularity/cache'.format(
                            get_temp_disk_for_node_agent(
                                pool.cloud_pool.
                                virtual_machine_configuration.
                                node_agent_sku_id.lower()))
                    ))
                else:
                    replace_ev.append(ev)
            job.job_preparation_task.environment_settings = replace_ev
        # add job
        success = False
        del_job = True
        try:
            logger.info(
                'adding job {} to pool {} (batch_account={} '
                'service_url={})'.format(
                    job.id, pool.pool_id, pool.batch_account,
                    pool.service_url))
            bsh.add_job(pool.batch_account, pool.service_url, job)
            success = True
            del_job = False
        except batchmodels.batch_error.BatchErrorException as exc:
            if 'marked for deletion' in exc.message.value:
                del_job = False
                logger.error(
                    'cannot reuse job {} being deleted on pool {}'.format(
                        job.id, pool.pool_id))
            elif 'already in a completed state' in exc.message.value:
                del_job = False
                logger.error(
                    'cannot reuse completed job {} on pool {}'.format(
                        job.id, pool.pool_id))
            elif 'job already exists' in exc.message.value:
                del_job = False
                success = True
                # cannot re-use an existing job if multi-instance due to
                # job release requirement
                if (constraints.task.has_multi_instance and
                        constraints.task.auto_complete):
                    logger.error(
                        'cannot reuse job {} on pool {} with multi_instance '
                        'and auto_complete'.format(job.id, pool.pool_id))
                    success = False
                else:
                    # retrieve job and check for constraints
                    ej = bsh.get_job(
                        pool.batch_account, pool.service_url, job.id)
                    # ensure the job's pool info matches
                    if ej.pool_info.pool_id != pool.pool_id:
                        logger.error(
                            'existing job {} on pool {} is already assigned '
                            'to a different pool {}'.format(
                                job.id, pool.pool_id, ej.pool_info.pool_id))
                        success = False
                    else:
                        # ensure job prep command line is the same (this will
                        # prevent jobs with mismatched data ingress)
                        ejp = None
                        njp = None
                        if ej.job_preparation_task is not None:
                            ejp = ej.job_preparation_task.command_line
                            if job.job_preparation_task is not None:
                                njp = job.job_preparation_task.command_line
                                if ejp != njp:
                                    success = False
                            else:
                                success = False
                        else:
                            if job.job_preparation_task is not None:
                                njp = job.job_preparation_task.command_line
                                success = False
                        if not success:
                            logger.error(
                                'existing job {} on pool {} has an '
                                'incompatible job prep task: existing={} '
                                'desired={}'.format(
                                    job.id, pool.pool_id, ejp, njp))
                        elif (job.uses_task_dependencies and
                                not ej.uses_task_dependencies):
                            # check for task dependencies
                            logger.error(
                                ('existing job {} on pool {} has an '
                                 'incompatible task dependency setting: '
                                 'existing={} desired={}').format(
                                     job.id, pool.pool_id,
                                     ej.uses_task_dependencies,
                                     job.uses_task_dependencies))
                            success = False
                        elif (ej.on_task_failure != job.on_task_failure):
                            # check for job actions
                            logger.error(
                                ('existing job {} on pool {} has an '
                                 'incompatible on_task_failure setting: '
                                 'existing={} desired={}').format(
                                     job.id, pool.pool_id,
                                     ej.on_task_failure.value,
                                     job.on_task_failure.value))
                            success = False
            else:
                logger.exception(str(exc))
        if del_job:
            await bsh.delete_or_terminate_job(
                pool.batch_account, pool.service_url, job.id, True, False,
                wait=True)
        return success

    def track_job(
            self,
            fdh: FederationDataHandler,
            target_pool: str,
            job_id: str,
            is_job_schedule: bool,
            unique_id: Optional[str],
    ) -> None:
        # get pool ref
        pool = self.pools[target_pool]
        # add to jobs table
        while True:
            entity = fdh.get_location_entity_for_job(self.hash, job_id, pool)
            if entity is None:
                pk, rk = fdh.generate_pk_rk_for_job_location_entity(
                    self.hash, job_id, pool)
                entity = {
                    'PartitionKey': pk,
                    'RowKey': rk,
                    'Kind': 'job_schedule' if is_job_schedule else 'job',
                    'Id': job_id,
                    'PoolId': pool.pool_id,
                    'BatchAccount': pool.batch_account,
                    'ServiceUrl': pool.service_url,
                }
                if is_not_empty(unique_id):
                    entity['UniqueIds'] = unique_id
                    entity['AdditionTimestamps'] = datetime_utcnow(
                        as_string=True)
            else:
                if is_not_empty(unique_id):
                    try:
                        entity['AdditionTimestamps'] = '{},{}'.format(
                            entity['AdditionTimestamps'], datetime_utcnow(
                                as_string=True))
                    except KeyError:
                        entity['AdditionTimestamps'] = datetime_utcnow(
                            as_string=True)
                    if (len(entity['AdditionTimestamps']) >
                            fdh._MAX_STR_ENTITY_PROPERTY_LENGTH):
                        tmp = entity['AdditionTimestamps'].split(',')
                        entity['AdditionTimestamps'] = ','.join(tmp[-32:])
                        del tmp
                    try:
                        entity['UniqueIds'] = '{},{}'.format(
                            entity['UniqueIds'], unique_id)
                    except KeyError:
                        entity['UniqueIds'] = unique_id
                    if (len(entity['UniqueIds']) >
                            fdh._MAX_STR_ENTITY_PROPERTY_LENGTH):
                        tmp = entity['UniqueIds'].split(',')
                        entity['UniqueIds'] = ','.join(tmp[-32:])
                        del tmp
            if fdh.insert_or_update_entity_with_etag_for_job(entity):
                logger.debug(
                    'upserted location entity for job {} on pool {} uid={} '
                    '(batch_account={} service_url={})'.format(
                        job_id, pool.pool_id, unique_id, pool.batch_account,
                        pool.service_url))
                break
            else:
                logger.debug(
                    'conflict upserting location entity for job {} on '
                    'pool {} uid={}(batch_account={} service_url={})'.format(
                        job_id, pool.pool_id, unique_id, pool.batch_account,
                        pool.service_url))

    def fixup_task_for_mismatch(
            self,
            node_agent: str,
            ib_mismatch: bool,
            task: batchmodels.TaskAddParameter,
            constraints: Constraints,
    ) -> batchmodels.TaskAddParameter:
        # fix up env vars for gpu and/or non-native
        if ((constraints.compute_node.gpu or not constraints.pool.native) and
                task.environment_settings is not None):
            replace_ev = []
            for ev in task.environment_settings:
                if ev.name == 'CUDA_CACHE_PATH':
                    replace_ev.append(batchmodels.EnvironmentSetting(
                        ev.name,
                        '{}/batch/tasks/.nv/ComputeCache'.format(
                            get_temp_disk_for_node_agent(node_agent))
                    ))
                elif ev.name == 'SINGULARITY_CACHEDIR':
                    replace_ev.append(batchmodels.EnvironmentSetting(
                        ev.name,
                        '{}/singularity/cache'.format(
                            get_temp_disk_for_node_agent(node_agent))
                    ))
                else:
                    replace_ev.append(ev)
            task.environment_settings = replace_ev
        # fix up ib rdma mapping in command line
        if ib_mismatch:
            if node_agent.startswith('batch.node.sles'):
                final = (
                    '/etc/dat.conf:/etc/rdma/dat.conf:ro '
                    '--device=/dev/hvnd_rdma'
                )
            else:
                final = '/etc/dat.conf:/etc/rdma/dat.conf:ro'
            if constraints.task.has_multi_instance:
                # fixup coordination command line
                cc = task.multi_instance_settings.coordination_command_line
                cc = cc.replace(
                    '/etc/rdma:/etc/rdma:ro',
                    '/etc/dat.conf:/etc/dat.conf:ro').replace(
                        '/etc/rdma/dat.conf:/etc/dat.conf:ro', final)
                task.multi_instance_settings.coordination_command_line = cc
            # fixup command line
            task.command_line = task.command_line.replace(
                '/etc/rdma:/etc/rdma:ro',
                '/etc/dat.conf:/etc/dat.conf:ro').replace(
                    '/etc/rdma/dat.conf:/etc/dat.conf:ro', final)
        return task

    def schedule_tasks(
            self,
            bsh: BatchServiceHandler,
            fdh: FederationDataHandler,
            target_pool: str,
            job_id: str,
            constraints: Constraints,
            naming: TaskNaming,
            task_map: Dict[str, batchmodels.TaskAddParameter],
    ) -> None:
        """
        This function should be called with lock already held!
        """
        # get pool ref
        pool = self.pools[target_pool]
        na = pool.cloud_pool.virtual_machine_configuration.\
            node_agent_sku_id.lower()
        # check if there is an ib mismatch
        ib_mismatch = (
            is_rdma_pool(pool.vm_size) and
            not na.startswith('batch.node.centos')
        )
        task_ids = sorted(task_map.keys())
        # fixup tasks directly if task dependencies are present
        if constraints.task.has_task_dependencies:
            for tid in task_ids:
                task_map[tid] = self.fixup_task_for_mismatch(
                    na, ib_mismatch, task_map[tid], constraints)
        else:
            # re-assign task ids to current job if no task dependencies
            # 1. sort task map keys
            # 2. re-map task ids to current job
            # 3. re-gather merge task dependencies (shouldn't happen)
            last_tid = None
            tasklist = None
            merge_task_id = None
            for tid in task_ids:
                is_merge_task = tid == constraints.task.merge_task_id
                tasklist, new_tid = bsh.regenerate_next_generic_task_id(
                    pool.batch_account, pool.service_url, job_id, naming, tid,
                    last_task_id=last_tid, tasklist=tasklist,
                    is_merge_task=is_merge_task)
                task = task_map.pop(tid)
                task = self.fixup_task_for_mismatch(
                    na, ib_mismatch, task, constraints)
                task.id = new_tid
                task_map[new_tid] = task
                if is_merge_task:
                    merge_task_id = new_tid
                tasklist.append(new_tid)
                last_tid = new_tid
            if merge_task_id is not None:
                merge_task = task_map.pop(merge_task_id)
                merge_task = self.fixup_task_for_mismatch(
                    na, ib_mismatch, merge_task, constraints)
                merge_task.depends_on = batchmodels.TaskDependencies(
                    task_ids=list(task_map.keys()),
                )
                task_map[merge_task_id] = merge_task
        # submit task collection
        bsh.add_task_collection(
            pool.batch_account, pool.service_url, job_id, task_map)
        # set auto complete
        if constraints.task.auto_complete:
            bsh.set_auto_complete_on_job(
                pool.batch_account, pool.service_url, job_id)
        # post scheduling actions
        pool.on_new_tasks_scheduled(
            bsh, fdh.scheduling_blackout, fdh.scheduling_evaluate_autoscale)


class FederationProcessor():
    def __init__(self, config: Dict[str, Any]) -> None:
        """Ctor for FederationProcessor
        :param config: configuration
        """
        self._service_proxy = ServiceProxy(config)
        try:
            self.fed_refresh_interval = int(config['refresh_intervals'].get(
                'federations', 30))
        except KeyError:
            self.fed_refresh_interval = 30
        try:
            self.action_refresh_interval = int(config['refresh_intervals'].get(
                'actions', 5))
        except KeyError:
            self.action_refresh_interval = 5
        self.csh = ComputeServiceHandler(self._service_proxy)
        self.bsh = BatchServiceHandler(self._service_proxy)
        self.fdh = FederationDataHandler(self._service_proxy)
        # data structs
        self._federation_lock = threading.Lock()
        self.federations = {}  # type: Dict[str, Federation]

    @property
    def federations_available(self) -> bool:
        with self._federation_lock:
            return len(self.federations) > 0

    def _update_federation(self, entity) -> None:
        fedhash = entity['RowKey']
        fedid = entity['FederationId']
        if fedhash not in self.federations:
            logger.debug('adding federation hash {} id: {}'.format(
                fedhash, fedid))
            self.federations[fedhash] = Federation(fedhash, fedid)
        pools = list(self.fdh.get_all_pools_for_federation(fedhash))
        if len(pools) == 0:
            return
        poolset = set()
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers_for_executor(pools)) as executor:
            for pool in pools:
                executor.submit(
                    self.federations[fedhash].update_pool,
                    self.csh, self.bsh, pool, poolset)
        self.federations[fedhash].trim_orphaned_pools(poolset)

    def update_federations(self) -> None:
        """Update federations"""
        entities = list(self.fdh.get_all_federations())
        if len(entities) == 0:
            return
        with self._federation_lock:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers_for_executor(
                        entities)) as executor:
                for entity in entities:
                    executor.submit(self._update_federation, entity)

    async def add_job_v1(
        self,
        fedhash: str,
        job: batchmodels.JobAddParameter,
        constraints: Constraints,
        naming: TaskNaming,
        task_map: Dict[str, batchmodels.TaskAddParameter],
        unique_id: str
    ) -> bool:
        # get the number of tasks in job
        # try to match the appropriate pool for the tasks in job
        # add job to pool
        # if job exists, ensure settings match
        # add tasks to job
        # record mapping in fedjobs table
        num_tasks = len(task_map)
        logger.debug(
            'attempting to match job {} with {} tasks in fed {} uid={}'.format(
                job.id, num_tasks, fedhash, unique_id))
        blacklist = set()
        while True:
            poolrk = self.federations[fedhash].find_target_pool_for_job(
                self.bsh, self.fdh, num_tasks, constraints, blacklist,
                unique_id, job.id)
            if poolrk is not None:
                cj = await self.federations[fedhash].create_job(
                    self.bsh, poolrk, job, constraints)
                if cj:
                    # remove blocked action if any
                    self.fdh.remove_blocked_action_for_job(fedhash, job.id)
                    # track job prior to adding tasks in case task
                    # addition fails
                    self.federations[fedhash].track_job(
                        self.fdh, poolrk, job.id, False, None)
                    # schedule tasks
                    self.federations[fedhash].schedule_tasks(
                        self.bsh, self.fdh, poolrk, job.id, constraints,
                        naming, task_map)
                    # update job tracking
                    self.federations[fedhash].track_job(
                        self.fdh, poolrk, job.id, False, unique_id)
                    break
                else:
                    logger.debug(
                        'blacklisting pool hash={} in fed hash {} '
                        'uid={} for job {}'.format(
                            poolrk, fedhash, unique_id, job.id))
                    blacklist.add(poolrk)
            else:
                return False
        return True

    async def add_job_schedule_v1(
        self,
        fedhash: str,
        job_schedule: batchmodels.JobScheduleAddParameter,
        constraints: Constraints,
        unique_id: str
    ) -> bool:
        # ensure there is no existing job schedule. although this is checked
        # at submission time, a similarly named job schedule can be enqueued
        # multiple times before the action is dequeued
        if self.fdh.location_entities_exist_for_job(fedhash, job_schedule.id):
            logger.error(
                'job schedule {} already exists for fed {} uid={}'.format(
                    job_schedule.id, fedhash, unique_id))
            return True
        num_tasks = constraints.task.tasks_per_recurrence
        logger.debug(
            'attempting to match job schedule {} with {} tasks in fed {} '
            'uid={}'.format(job_schedule.id, num_tasks, fedhash, unique_id))
        blacklist = set()
        while True:
            poolrk = self.federations[fedhash].find_target_pool_for_job(
                self.bsh, self.fdh, num_tasks, constraints, blacklist,
                unique_id, job_schedule.id)
            if poolrk is not None:
                cj = await self.federations[fedhash].create_job_schedule(
                    self.bsh, poolrk, job_schedule, constraints)
                if cj:
                    # remove blocked action if any
                    self.fdh.remove_blocked_action_for_job(
                        fedhash, job_schedule.id)
                    # track job schedule
                    self.federations[fedhash].track_job(
                        self.fdh, poolrk, job_schedule.id, True, unique_id)
                    break
                else:
                    logger.debug(
                        'blacklisting pool hash={} in fed hash {} '
                        'uid={} for job schedule {}'.format(
                            poolrk, fedhash, unique_id, job_schedule.id))
                    blacklist.add(poolrk)
            else:
                return False
        return True

    async def _terminate_job(
        self,
        fedhash: str,
        job_id: str,
        is_job_schedule: bool,
        entity: azure.cosmosdb.table.models.Entity,
    ) -> None:
        if 'TerminateTimestamp' in entity:
            logger.debug(
                '{} {} for fed {} has already been terminated '
                'at {}'.format(
                    'job schedule' if is_job_schedule else 'job',
                    job_id, fedhash, entity['TerminateTimestamp']))
            return
        await self.bsh.delete_or_terminate_job(
            entity['BatchAccount'], entity['ServiceUrl'], job_id, False,
            is_job_schedule, wait=False)
        logger.info(
            'terminated {} {} on pool {} for fed {} (batch_account={} '
            'service_url={}'.format(
                'job schedule' if is_job_schedule else 'job',
                job_id, entity['PoolId'], fedhash, entity['BatchAccount'],
                entity['ServiceUrl']))
        while True:
            entity['TerminateTimestamp'] = datetime_utcnow(as_string=False)
            if self.fdh.insert_or_update_entity_with_etag_for_job(entity):
                break
            else:
                # force update
                entity['etag'] = '*'

    async def _delete_job(
        self,
        fedhash: str,
        job_id: str,
        is_job_schedule: bool,
        entity: azure.cosmosdb.table.models.Entity,
    ) -> None:
        await self.bsh.delete_or_terminate_job(
            entity['BatchAccount'], entity['ServiceUrl'], job_id, True,
            is_job_schedule, wait=False)
        logger.info(
            'deleted {} {} on pool {} for fed {} (batch_account={} '
            'service_url={}'.format(
                'job schedule' if is_job_schedule else 'job',
                job_id, entity['PoolId'], fedhash, entity['BatchAccount'],
                entity['ServiceUrl']))
        self.fdh.delete_location_entity_for_job(entity)

    async def delete_or_terminate_job_v1(
        self,
        delete: bool,
        fedhash: str,
        job_id: str,
        is_job_schedule: bool,
        unique_id: str
    ) -> None:
        # find all jobs across federation mathching the id
        entities = self.fdh.get_all_location_entities_for_job(fedhash, job_id)
        # terminate each pool-level job representing federation job
        tasks = []
        coro = self._delete_job if delete else self._terminate_job
        for entity in entities:
            tasks.append(
                asyncio.ensure_future(
                    coro(fedhash, job_id, is_job_schedule, entity)))
        if len(tasks) > 0:
            await asyncio.wait(tasks)
        else:
            logger.error(
                'cannot {} {} {} for fed {}, no location entities '
                'exist (uid={})'.format(
                    'delete' if delete else 'terminate',
                    'job schedule' if is_job_schedule else 'job',
                    job_id, fedhash, unique_id))

    async def process_message_action_v1(
        self,
        fedhash: str,
        data: Dict[str, Any],
        unique_id: str
    ) -> bool:
        result = True
        # check proper version
        if is_not_empty(data) and data['version'] != '1':
            logger.error('cannot process job data version {} for {}'.format(
                data['version'], unique_id))
            return result
        # extract data from message
        action = data['action']['method']
        target_type = data['action']['kind']
        target = data[target_type]['id']
        logger.debug(
            'uid {} for fed {} message action={} target_type={} '
            'target={}'.format(
                unique_id, fedhash, action, target_type, target))
        # take action depending upon kind and method
        if target_type == 'job_schedule':
            if action == 'add':
                job_schedule = data[target_type]['data']
                logger.debug(
                    'uid {} for fed {} target_type={} target={} '
                    'constraints={}'.format(
                        unique_id, fedhash, target_type, target,
                        data[target_type]['constraints']))
                constraints = Constraints(data[target_type]['constraints'])
                result = await self.add_job_schedule_v1(
                    fedhash, job_schedule, constraints, unique_id)
            elif action == 'terminate':
                await self.delete_or_terminate_job_v1(
                    False, fedhash, target, True, unique_id)
            elif action == 'delete':
                await self.delete_or_terminate_job_v1(
                    True, fedhash, target, True, unique_id)
            else:
                raise NotImplementedError()
        elif target_type == 'job':
            if action == 'add':
                job = data[target_type]['data']
                logger.debug(
                    'uid {} for fed {} target_type={} target={} '
                    'constraints={}'.format(
                        unique_id, fedhash, target_type, target,
                        data[target_type]['constraints']))
                constraints = Constraints(data[target_type]['constraints'])
                logger.debug(
                    'uid {} for fed {} target_type={} target={} '
                    'naming={}'.format(
                        unique_id, fedhash, target_type, target,
                        data[target_type]['task_naming']))
                naming = TaskNaming(data[target_type]['task_naming'])
                task_map = data['task_map']
                result = await self.add_job_v1(
                    fedhash, job, constraints, naming, task_map, unique_id)
            elif action == 'terminate':
                await self.delete_or_terminate_job_v1(
                    False, fedhash, target, False, unique_id)
            elif action == 'delete':
                await self.delete_or_terminate_job_v1(
                    True, fedhash, target, False, unique_id)
            else:
                raise NotImplementedError()
        else:
            logger.error('unknown target type: {}'.format(target_type))
        return result

    async def process_queue_message_v1(
            self,
            fedhash: str,
            msg: Dict[str, Any]
    ) -> Tuple[bool, str]:
        result = True
        target_fedid = msg['federation_id']
        calc_fedhash = hash_federation_id(target_fedid)
        if calc_fedhash != fedhash:
            logger.error(
                'federation hash mismatch, expected={} actual={} id={}'.format(
                    fedhash, calc_fedhash, target_fedid))
            return result, None
        target = msg['target']
        unique_id = msg['uuid']
        # get sequence from table
        seq_id = self.fdh.get_first_sequence_id_for_job(fedhash, target)
        if seq_id is None:
            logger.error(
                'sequence length is missing or non-positive for uid={} for '
                'target {} on federation {}'.format(
                    unique_id, target, fedhash))
            # remove blocked action if any
            self.fdh.remove_blocked_action_for_job(fedhash, target)
            return result, None
        # if there is a sequence mismatch, then queue is no longer FIFO
        # get the appropriate next sequence id and construct the blob url
        # for the message data
        if seq_id != unique_id:
            logger.warning(
                'queue message for fed {} does not match first '
                'sequence q:{} != t:{} for target {}'.format(
                    fedhash, unique_id, seq_id, target))
            unique_id = seq_id
            blob_url = self.fdh.construct_blob_url(fedhash, unique_id)
        else:
            blob_url = msg['blob_data']
        del seq_id
        # retrieve message data from blob
        job_data = None
        try:
            blob_client, container, blob_name, data = \
                self.fdh.retrieve_blob_data(blob_url)
        except Exception as exc:
            logger.exception(str(exc))
            logger.error(
                'cannot process queue message for sequence id {} for '
                'fed {}'.format(unique_id, fedhash))
            # remove blocked action if any
            self.fdh.remove_blocked_action_for_job(fedhash, target)
            return False, target
        else:
            job_data = pickle.loads(data, fix_imports=True)
            del data
        del blob_url
        # process message
        if job_data is not None:
            result = await self.process_message_action_v1(
                fedhash, job_data, unique_id)
            # cleanup
            if result:
                self.fdh.delete_blob(blob_client, container, blob_name)
            else:
                target = None
        return result, target

    async def process_federation_queue(self, fedhash: str) -> None:
        acquired = self.federations[fedhash].lock.acquire(blocking=False)
        if not acquired:
            logger.debug('could not acquire lock on federation {}'.format(
                fedhash))
            return
        try:
            msgs = self.fdh.get_messages_from_federation_queue(fedhash)
            for msg in msgs:
                if not await self.check_global_lock(backoff=False):
                    logger.error(
                        'global lock lease lost while processing queue for '
                        'fed {}'.format(fedhash))
                    return
                msg_data = json.loads(msg.content, encoding='utf8')
                if msg_data['version'] == '1':
                    del_msg, target = await self.process_queue_message_v1(
                        fedhash, msg_data)
                else:
                    logger.error(
                        'cannot process message version {} for fed {}'.format(
                            msg_data['version'], fedhash))
                    del_msg = True
                    target = None
                # delete message
                self.fdh.dequeue_sequence_id_from_federation_sequence(
                    del_msg, fedhash, msg.id, msg.pop_receipt, target)
        finally:
            self.federations[fedhash].lock.release()

    async def check_global_lock(
        self,
        backoff: bool=True
    ) -> Generator[None, None, None]:
        if not self.fdh.has_global_lock:
            if backoff:
                await asyncio.sleep(5 + random.randint(0, 5))
            return False
        return True

    async def iterate_and_process_federation_queues(
        self
    ) -> Generator[None, None, None]:
        while True:
            if not await self.check_global_lock():
                continue
            if self.federations_available:
                # TODO process in parallel
                for fedhash in self.federations:
                    try:
                        await self.process_federation_queue(fedhash)
                    except Exception as exc:
                        logger.exception(str(exc))
                    if not await self.check_global_lock(backoff=False):
                        break
            await asyncio.sleep(self.action_refresh_interval)

    async def poll_for_federations(
        self,
        loop: asyncio.BaseEventLoop,
    ) -> Generator[None, None, None]:
        """Poll federations
        :param loop: asyncio loop
        """
        # lease global lock blob
        self.fdh.lease_global_lock(loop)
        # block until global lock acquired
        while not await self.check_global_lock():
            pass
        # mount log storage
        log_path = self.fdh.mount_file_storage()
        # set logging configuration
        self.fdh.set_log_configuration(log_path)
        self._service_proxy.log_configuration()
        logger.debug('polling federation table {} every {} sec'.format(
            self._service_proxy.table_name_global, self.fed_refresh_interval))
        logger.debug('polling action queues {} every {} sec'.format(
            self._service_proxy.table_name_jobs, self.action_refresh_interval))
        # begin message processing
        asyncio.ensure_future(
            self.iterate_and_process_federation_queues(), loop=loop)
        # continuously update federations
        while True:
            if not await self.check_global_lock():
                continue
            try:
                self.update_federations()
            except Exception as exc:
                logger.exception(str(exc))
            await asyncio.sleep(self.fed_refresh_interval)


def main() -> None:
    """Main function"""
    # get command-line args
    args = parseargs()
    # load configuration
    if is_none_or_empty(args.conf):
        raise ValueError('config file not specified')
    with open(args.conf, 'rb') as f:
        config = json.load(f)
    logger.debug('loaded config from {}: {}'.format(args.conf, config))
    del args
    # create federation processor
    fed_processor = FederationProcessor(config)
    # run the poller
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            fed_processor.poll_for_federations(loop)
        )
    except Exception as exc:
        logger.exception(str(exc))
    finally:
        handlers = logger.handlers[:]
        for handler in handlers:
            handler.close()
            logger.removeHandler(handler)
        try:
            fed_processor.fdh.unmount_file_storage()
        except Exception as exc:
            logger.exception(str(exc))


def parseargs() -> argparse.Namespace:
    """Parse program arguments
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='federation: Azure Batch Shipyard Federation Controller')
    parser.add_argument('--conf', help='configuration file')
    return parser.parse_args()


if __name__ == '__main__':
    _setup_logger(logger)
    az_logger = logging.getLogger('azure.storage')
    _setup_logger(az_logger)
    az_logger.setLevel(logging.WARNING)
    az_logger = logging.getLogger('azure.cosmosdb')
    _setup_logger(az_logger)
    az_logger.setLevel(logging.WARNING)
    main()
