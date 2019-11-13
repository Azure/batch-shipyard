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
import datetime
import json
import logging
import os
import pickle
import re
import tempfile
import time
import uuid
# non-stdlib imports
import azure.common
import azure.cosmosdb.table as azuretable
import azure.storage.blob as azureblob
import azure.storage.file as azurefile
# local imports
from . import settings
from . import util

# TODO refactor as class

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_MONITOR_BATCHPOOL_PK = 'BatchPool'
_MONITOR_REMOTEFS_PK = 'RemoteFS'
_ALL_FEDERATIONS_PK = '!!FEDERATIONS'
_FEDERATION_ACTIONS_PREFIX_PK = '!!ACTIONS'
_BLOCKED_FEDERATION_ACTIONS_PREFIX_PK = '!!ACTIONS.BLOCKED'
_MAX_SEQUENCE_ID_PROPERTIES = 15
_MAX_SEQUENCE_IDS_PER_PROPERTY = 975
_DEFAULT_SAS_EXPIRY_DAYS = 365 * 30
_STORAGEACCOUNT = None
_STORAGEACCOUNTKEY = None
_STORAGEACCOUNTEP = None
_STORAGE_CONTAINERS = {
    'blob_globalresources': None,
    'blob_resourcefiles': None,
    'blob_remotefs': None,
    'blob_monitoring': None,
    'blob_federation_global': None,
    'blob_federation': None,
    'table_globalresources': None,
    'table_perf': None,
    'table_monitoring': None,
    'table_federation_global': None,
    'table_federation_jobs': None,
    'table_slurm': None,
    'queue_federation': None,
    # TODO remove following in future release
    'blob_torrents': None,
    'table_dht': None,
    'table_images': None,
    'table_registry': None,
    'table_torrentinfo': None,
}
_CONTAINERS_CREATED = set()


def set_storage_configuration(sep, postfix, sa, sakey, saep, sasexpiry):
    # type: (str, str, str, str, str, int) -> None
    """Set storage configuration
    :param str sep: storage entity prefix
    :param str postfix: storage entity postfix
    :param str sa: storage account
    :param str sakey: storage account key
    :param str saep: storage account endpoint
    :param int sasexpiry: sas expiry default time in days
    """
    if util.is_none_or_empty(sep):
        raise ValueError('storage_entity_prefix is invalid')
    global _STORAGEACCOUNT, _STORAGEACCOUNTKEY, _STORAGEACCOUNTEP, \
        _DEFAULT_SAS_EXPIRY_DAYS
    _STORAGE_CONTAINERS['blob_globalresources'] = '-'.join(
        (sep + 'gr', postfix))
    _STORAGE_CONTAINERS['blob_resourcefiles'] = '-'.join(
        (sep + 'rf', postfix))
    _STORAGE_CONTAINERS['blob_remotefs'] = sep + 'remotefs'
    _STORAGE_CONTAINERS['blob_monitoring'] = sep + 'monitor'
    _STORAGE_CONTAINERS['blob_federation'] = sep + 'fed'
    _STORAGE_CONTAINERS['blob_federation_global'] = sep + 'fedglobal'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'gr'
    _STORAGE_CONTAINERS['table_perf'] = sep + 'perf'
    _STORAGE_CONTAINERS['table_monitoring'] = sep + 'monitor'
    _STORAGE_CONTAINERS['table_federation_jobs'] = sep + 'fedjobs'
    _STORAGE_CONTAINERS['table_federation_global'] = sep + 'fedglobal'
    _STORAGE_CONTAINERS['table_slurm'] = sep + 'slurm'
    _STORAGE_CONTAINERS['queue_federation'] = sep + 'fed'
    # TODO remove following containers in future release
    _STORAGE_CONTAINERS['blob_torrents'] = '-'.join(
        (sep + 'tor', postfix))
    _STORAGE_CONTAINERS['table_dht'] = sep + 'dht'
    _STORAGE_CONTAINERS['table_images'] = sep + 'images'
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    # ensure all storage containers are between 3 and 63 chars in length
    for key in _STORAGE_CONTAINERS:
        length = len(_STORAGE_CONTAINERS[key])
        if length < 3 or length > 63:
            raise RuntimeError(
                'Storage container {} name {} length {} does not fall in '
                'storage naming rules. Retry with a modified '
                'batch_shipyard:storage_entity_prefix and/or '
                'pool_specification:id.'.format(
                    key, _STORAGE_CONTAINERS[key], length))
    _STORAGEACCOUNT = sa
    _STORAGEACCOUNTKEY = sakey
    _STORAGEACCOUNTEP = saep
    if sasexpiry is not None:
        _DEFAULT_SAS_EXPIRY_DAYS = sasexpiry


def set_storage_remotefs_container(storage_cluster_id):
    # type: (str) -> None
    """Set storage properties for a remotefs storage cluster
    :param str storage_cluster_id: storage cluster id
    """
    if util.is_none_or_empty(storage_cluster_id):
        raise ValueError('storage_cluster_id is invalid')
    _STORAGE_CONTAINERS['blob_remotefs'] = '{}-{}'.format(
        _STORAGE_CONTAINERS['blob_remotefs'],
        storage_cluster_id)


def get_storageaccount():
    # type: (None) -> str
    """Get storage account
    :rtype: str
    :return: storage account
    """
    return _STORAGEACCOUNT


def get_storageaccount_key():
    # type: (None) -> str
    """Get storage account key
    :rtype: str
    :return: storage account key
    """
    return _STORAGEACCOUNTKEY


def get_storageaccount_endpoint():
    # type: (None) -> str
    """Get storage account endpoint
    :rtype: str
    :return: storage account endpoint
    """
    return _STORAGEACCOUNTEP


def get_storage_table_monitoring():
    # type: (None) -> str
    """Get the table associated with monitoring
    :rtype: str
    :return: table name for monitoring
    """
    return _STORAGE_CONTAINERS['table_monitoring']


def populate_storage_account_keys_from_aad(storage_mgmt_client, config):
    # type: (azure.mgmt.storage.StorageManagementClient, dict) -> None
    """Fetch secrets with secret ids in config from keyvault
    :param azure.mgmt.storage.StorageManagementClient storage_mgmt_client:
        storage client
    :param dict config: configuration dict
    """
    modified = False
    if storage_mgmt_client is None:
        return modified
    # get ref to main storage account
    main_sa = settings.batch_shipyard_settings(config).storage_account_settings
    # iterate all storage accounts, if storage account does not have
    # a storage account key, then lookup via aad
    for ssel in settings.iterate_storage_credentials(config):
        sc = settings.credentials_storage(config, ssel)
        if util.is_none_or_empty(sc.account_key):
            if util.is_none_or_empty(sc.resource_group):
                raise ValueError(
                    ('resource_group is invalid for storage account {} to '
                     'be retrieved by aad').format(sc.account))
            keys = storage_mgmt_client.storage_accounts.list_keys(
                sc.resource_group, sc.account)
            props = storage_mgmt_client.storage_accounts.get_properties(
                sc.resource_group, sc.account)
            if main_sa == ssel:
                ep = props.primary_endpoints.table
                if ep is None:
                    raise ValueError(
                        ('the specified '
                         'batch_shipyard:storage_account_settings storage '
                         'account (link={} account={}) is not a general '
                         'purpose type storage account').format(
                             ssel, sc.account))
            else:
                # get either blob or file endpoint
                ep = (
                    props.primary_endpoints.blob or
                    props.primary_endpoints.file
                )
            ep = '.'.join(ep.rstrip('/').split('.')[2:])
            settings.set_credentials_storage_account(
                config, ssel, keys.keys[0].value, ep)
            modified = True
    return modified


def generate_blob_container_uri(storage_settings, container):
    # type: (StorageCredentialsSettings, str) -> str
    """Create a uri to a blob container
    :param StorageCredentialsSettings storage_settings: storage settings
    :param str container: container
    :rtype: str
    :return: blob container uri
    """
    blob_client = azureblob.BlockBlobService(
        account_name=storage_settings.account,
        account_key=storage_settings.account_key,
        endpoint_suffix=storage_settings.endpoint)
    return '{}://{}/{}'.format(
        blob_client.protocol, blob_client.primary_endpoint, container)


def create_blob_container_saskey(
        storage_settings, container, kind, create_container=False):
    # type: (StorageCredentialsSettings, str, str, bool) -> str
    """Create a saskey for a blob container
    :param StorageCredentialsSettings storage_settings: storage settings
    :param str container: container
    :param str kind: ingress or egress
    :param bool create_container: create container
    :rtype: str
    :return: saskey
    """
    global _CONTAINERS_CREATED
    blob_client = azureblob.BlockBlobService(
        account_name=storage_settings.account,
        account_key=storage_settings.account_key,
        endpoint_suffix=storage_settings.endpoint)
    if create_container:
        key = 'blob:{}:{}:{}'.format(
            storage_settings.account, storage_settings.endpoint, container)
        if key not in _CONTAINERS_CREATED:
            blob_client.create_container(container, fail_on_exist=False)
            _CONTAINERS_CREATED.add(key)
    if kind == 'ingress':
        perm = azureblob.ContainerPermissions(read=True, list=True)
    elif kind == 'egress':
        perm = azureblob.ContainerPermissions(
            read=True, write=True, delete=True, list=True)
    else:
        raise ValueError('{} type of transfer not supported'.format(kind))
    return blob_client.generate_container_shared_access_signature(
        container, perm,
        expiry=datetime.datetime.utcnow() +
        datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS)
    )


def create_file_share_saskey(
        storage_settings, file_share, kind, create_share=False):
    # type: (StorageCredentialSettings, str, str, bool) -> str
    """Create a saskey for a file share
    :param StorageCredentialsSettings storage_settings: storage settings
    :param str file_share: file share
    :param str kind: ingress or egress
    :param bool create_share: create file share
    :rtype: str
    :return: saskey
    """
    file_client = azurefile.FileService(
        account_name=storage_settings.account,
        account_key=storage_settings.account_key,
        endpoint_suffix=storage_settings.endpoint)
    if create_share:
        key = 'file:{}:{}:{}'.format(
            storage_settings.account, storage_settings.endpoint, file_share)
        if key not in _CONTAINERS_CREATED:
            file_client.create_share(file_share, fail_on_exist=False)
            _CONTAINERS_CREATED.add(key)
    if kind == 'ingress':
        perm = azurefile.SharePermissions(read=True, list=True)
    elif kind == 'egress':
        perm = azurefile.SharePermissions(
            read=True, write=True, delete=True, list=True)
    else:
        raise ValueError('{} type of transfer not supported'.format(kind))
    return file_client.generate_share_shared_access_signature(
        file_share, perm,
        expiry=datetime.datetime.utcnow() +
        datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS)
    )


def create_saskey(
        storage_settings, path, file, create, list_perm, read, write, delete,
        expiry_days=None):
    # type: (settings.StorageCredentialsSettings, str, bool, bool, bool, bool,
    #        bool, bool, int) -> None
    """Create an object-level sas key
    :param settings.StorageCredentialsSetting storage_settings:
        storage settings
    :param str path: path
    :param bool file: file sas
    :param bool create: create perm
    :param bool list_perm: list perm
    :param bool read: read perm
    :param bool write: write perm
    :param bool delete: delete perm
    :param int expiry_days: expiry in days
    :rtype: str
    :return: sas token
    """
    if expiry_days is None:
        expiry_days = _DEFAULT_SAS_EXPIRY_DAYS
    if file:
        client = azurefile.FileService(
            account_name=storage_settings.account,
            account_key=storage_settings.account_key,
            endpoint_suffix=storage_settings.endpoint)
        tmp = path.split('/')
        if len(tmp) < 1:
            raise ValueError('path is invalid: {}'.format(path))
        share_name = tmp[0]
        if len(tmp) == 1:
            perm = azurefile.SharePermissions(
                read=read, write=write, delete=delete, list=list_perm)
            sas = client.generate_share_shared_access_signature(
                share_name=share_name, permission=perm,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=expiry_days)
            )
        else:
            if len(tmp) == 2:
                directory_name = ''
                file_name = tmp[1]
            else:
                directory_name = tmp[1]
                file_name = '/'.join(tmp[2:])
            perm = azurefile.FilePermissions(
                read=read, create=create, write=write, delete=delete)
            sas = client.generate_file_shared_access_signature(
                share_name=share_name, directory_name=directory_name,
                file_name=file_name, permission=perm,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=expiry_days)
            )
    else:
        client = azureblob.BlockBlobService(
            account_name=storage_settings.account,
            account_key=storage_settings.account_key,
            endpoint_suffix=storage_settings.endpoint)
        tmp = path.split('/')
        if len(tmp) < 1:
            raise ValueError('path is invalid: {}'.format(path))
        container_name = tmp[0]
        if len(tmp) == 1:
            perm = azureblob.ContainerPermissions(
                read=read, write=write, delete=delete, list=list_perm)
            sas = client.generate_container_shared_access_signature(
                container_name=container_name, permission=perm,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=expiry_days)
            )
        else:
            blob_name = '/'.join(tmp[1:])
            perm = azureblob.BlobPermissions(
                read=read, create=create, write=write, delete=delete)
            sas = client.generate_blob_shared_access_signature(
                container_name=container_name, blob_name=blob_name,
                permission=perm,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=expiry_days)
            )
    return sas


def _construct_partition_key_from_config(config, pool_id=None):
    # type: (dict, str) -> str
    """Construct partition key from config
    :param dict config: configuration dict
    :param str pool_id: use specified pool id instead
    :rtype: str
    :return: partition key
    """
    if util.is_none_or_empty(pool_id):
        pool_id = settings.pool_id(config, lower=True)
    return '{}${}'.format(
        settings.credentials_batch(config).account, pool_id)


def _add_global_resource(
        blob_client, table_client, config, pk, dr, grtype):
    # type: (azureblob.BlockBlobService, azuretable.TableService, dict, str,
    #        settings.DataReplicationSettings, str) -> None
    """Add global resources
    :param azure.storage.blob.BlockService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str pk: partition key
    :param settings.DataReplicationSettings dr: data replication settings
    :param str grtype: global resources type
    """
    try:
        if grtype == 'docker_images':
            prefix = 'docker'
            resources = settings.global_resources_docker_images(config)
        elif grtype == 'singularity_images':
            prefix = 'singularity'
            resources = settings.global_resources_singularity_images(config)
            key_fingerprint_dict = (
                settings.singularity_signed_images_key_fingerprint_dict(
                    config))
        else:
            raise NotImplementedError(
                'global resource type: {}'.format(grtype))
        for gr in resources:
            resource = '{}:{}'.format(prefix, gr)
            resource_sha1 = util.hash_string(resource)
            logger.info('adding global resource: {} hash={}'.format(
                resource, resource_sha1))
            key_fingerprint = None
            if prefix == 'singularity':
                key_fingerprint = key_fingerprint_dict.get(gr, None)
            table_client.insert_or_replace_entity(
                _STORAGE_CONTAINERS['table_globalresources'],
                {
                    'PartitionKey': pk,
                    'RowKey': resource_sha1,
                    'Resource': resource,
                    'KeyFingerprint': key_fingerprint,
                }
            )
            for i in range(0, dr.concurrent_source_downloads):
                blob_client.create_blob_from_bytes(
                    container_name=_STORAGE_CONTAINERS['blob_globalresources'],
                    blob_name='{}.{}'.format(resource_sha1, i),
                    blob=b'',
                )
    except KeyError:
        pass


def populate_global_resource_blobs(blob_client, table_client, config):
    # type: (azureblob.BlockBlobService, azuretable.TableService, dict) -> None
    """Populate global resource blobs
    :param azure.storage.blob.BlockService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    pk = _construct_partition_key_from_config(config)
    dr = settings.data_replication_settings(config)
    _add_global_resource(
        blob_client, table_client, config, pk, dr, 'docker_images')
    _add_global_resource(
        blob_client, table_client, config, pk, dr, 'singularity_images')


def add_resources_to_monitor(table_client, config, pools, fsmap):
    # type: (azuretable.TableService, dict, List[str], dict) -> None
    """Populate resources to monitor
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param list pools: pools to monitor
    :param dict fsmap: fs clusters to monitor
    """
    if util.is_not_empty(pools):
        bc = settings.credentials_batch(config)
        for poolid in pools:
            entity = {
                'PartitionKey': _MONITOR_BATCHPOOL_PK,
                'RowKey': '{}${}'.format(bc.account, poolid),
                'BatchServiceUrl': bc.account_service_url,
                'AadEndpoint': bc.aad.endpoint,
                'AadAuthorityUrl': bc.aad.authority_url,
            }
            if settings.verbose(config):
                logger.debug(
                    'inserting pool monitor resource entity: {}'.format(
                        entity))
            try:
                table_client.insert_entity(
                    _STORAGE_CONTAINERS['table_monitoring'], entity)
            except azure.common.AzureConflictHttpError:
                logger.error('monitoring for pool {} already exists'.format(
                    poolid))
            else:
                logger.debug('resource monitor added for pool {}'.format(
                    poolid))
    if util.is_not_empty(fsmap):
        for sc_id in fsmap:
            fs = fsmap[sc_id]
            entity = {
                'PartitionKey': _MONITOR_REMOTEFS_PK,
                'RowKey': sc_id,
                'Type': fs['type'],
                'ResourceGroup': fs['rg'],
                'NodeExporterPort': fs['ne_port'],
                'VMs': json.dumps(fs['vms'], ensure_ascii=False),
            }
            if fs['type'] == 'glusterfs':
                entity['AvailabilitySet'] = fs['as']
            if settings.verbose(config):
                logger.debug(
                    'inserting RemoteFS monitor resource entity: {}'.format(
                        entity))
            try:
                table_client.insert_entity(
                    _STORAGE_CONTAINERS['table_monitoring'], entity)
            except azure.common.AzureConflictHttpError:
                logger.error(
                    'monitoring for remotefs {} already exists'.format(sc_id))
            else:
                logger.debug('resource monitor added for remotefs {}'.format(
                    sc_id))


def list_monitored_resources(table_client, config):
    # type: (azuretable.TableService, dict) -> None
    """List monitored resources
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    # list batch pools monitored
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_monitoring'],
            filter='PartitionKey eq \'{}\''.format(_MONITOR_BATCHPOOL_PK))
    except azure.common.AzureMissingResourceHttpError:
        logger.error(
            'cannot list monitored Batch pools as monitoring table does '
            'not exist')
    else:
        pools = ['batch pools monitored:']
        for ent in entities:
            ba, poolid = ent['RowKey'].split('$')
            pools.append('* pool id: {} (account: {})'.format(
                poolid, ba))
        if len(pools) == 1:
            logger.info('no Batch pools monitored')
        else:
            logger.info('{}'.format('\n'.join(pools)))
        del pools
    # list remotefs monitored
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_monitoring'],
            filter='PartitionKey eq \'{}\''.format(_MONITOR_REMOTEFS_PK))
    except azure.common.AzureMissingResourceHttpError:
        logger.error(
            'cannot list monitored RemoteFS clusters as monitoring table does '
            'not exist')
    else:
        fs = ['RemoteFS clusters monitored:']
        for ent in entities:
            sc_id = ent['RowKey']
            fs.append('* storage cluster id: {}'.format(sc_id))
            fs.append('  * type: {}'.format(ent['Type']))
            fs.append('  * resource group: {}'.format(ent['ResourceGroup']))
        if len(fs) == 1:
            logger.info('no RemoteFS clusters monitored')
        else:
            logger.info('{}'.format('\n'.join(fs)))


def remove_resources_from_monitoring(
        table_client, config, all, pools, fsclusters):
    # type: (azuretable.TableService, dict, bool, List[str], List[str]) -> None
    """Remove resources from monitoring
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool all: all resource monitors
    :param list pools: pools to remove from monitoring
    :param list fsclusters: fs clusters to remove from monitoring
    """
    if all:
        if util.confirm_action(
                config, 'remove all resources from monitoring'):
            _clear_table(
                table_client, _STORAGE_CONTAINERS['table_monitoring'], config,
                pool_id=None, pk=_MONITOR_BATCHPOOL_PK)
        return
    if util.is_not_empty(pools):
        bc = settings.credentials_batch(config)
        for poolid in pools:
            try:
                table_client.delete_entity(
                    _STORAGE_CONTAINERS['table_monitoring'],
                    partition_key=_MONITOR_BATCHPOOL_PK,
                    row_key='{}${}'.format(bc.account, poolid)
                )
            except azure.common.AzureMissingResourceHttpError:
                logger.error('pool {} is not monitored'.format(poolid))
            else:
                logger.debug('resource monitor removed for pool {}'.format(
                    poolid))
    if util.is_not_empty(fsclusters):
        for sc_id in fsclusters:
            try:
                table_client.delete_entity(
                    _STORAGE_CONTAINERS['table_monitoring'],
                    partition_key=_MONITOR_REMOTEFS_PK,
                    row_key=sc_id
                )
            except azure.common.AzureMissingResourceHttpError:
                logger.error('RemoteFS cluster {} is not monitored'.format(
                    sc_id))
            else:
                logger.debug(
                    'resource monitor removed for RemoteFS cluster {}'.format(
                        sc_id))


def hash_pool_and_service_url(pool_id, batch_service_url):
    """Hash a pool and service url
    :param str pool_id: pool id
    :param str batch_service_url: batch_service_url
    :rtype: str
    :return: hashed pool and service url
    """
    return util.hash_string('{}${}'.format(
        batch_service_url.rstrip('/'), pool_id))


def hash_federation_id(federation_id):
    """Hash a federation id
    :param str federation_id: federation id
    :rtype: str
    :return: hashed federation id
    """
    fedhash = util.hash_string(federation_id)
    logger.debug('federation id {} -> {}'.format(federation_id, fedhash))
    return fedhash


def generate_job_id_locator_partition_key(federation_id, job_id):
    """Hash a job id locator
    :param str federation_id: federation id
    :param str job_id: job id
    :rtype: str
    :return: hashed fedhash and job id
    """
    return '{}${}'.format(
        util.hash_string(federation_id), util.hash_string(job_id))


def create_federation_id(
        blob_client, table_client, queue_client, config, federation_id, force,
        unique_jobs):
    # type: (azure.storage.blob.BlockBlobService, azuretable.TableService,
    #        azure.queue.QueueService, dict, str, bool, bool) -> None
    """Create storage containers for federation id
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_service: queue client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param bool force: force creation
    :param bool unique_jobs: unique job ids required
    """
    fedhash = hash_federation_id(federation_id)
    # create table entry for federation id
    entity = {
        'PartitionKey': _ALL_FEDERATIONS_PK,
        'RowKey': fedhash,
        'FederationId': federation_id,
        'BatchShipyardFederationVersion': 1,
        'UniqueJobIds': unique_jobs,
    }
    logger.debug(
        'inserting federation {} entity to global table '
        '(unique_jobs={})'.format(federation_id, unique_jobs))
    try:
        table_client.insert_entity(
            _STORAGE_CONTAINERS['table_federation_global'], entity)
    except azure.common.AzureConflictHttpError:
        logger.error('federation id {} already exists'.format(
            federation_id))
        if force:
            if util.confirm_action(
                    config, 'overwrite existing federation {}; this can '
                    'result in undefined behavior'.format(federation_id)):
                table_client.insert_or_replace_entity(
                    _STORAGE_CONTAINERS['table_federation_global'], entity)
            else:
                return
        else:
            return
    # create blob container for federation id
    contname = '{}-{}'.format(_STORAGE_CONTAINERS['blob_federation'], fedhash)
    logger.debug('creating container: {}'.format(contname))
    blob_client.create_container(contname)
    # create job queue for federation id
    queuename = '{}-{}'.format(
        _STORAGE_CONTAINERS['queue_federation'], fedhash)
    logger.debug('creating queue: {}'.format(queuename))
    queue_client.create_queue(queuename)
    if settings.raw(config):
        rawout = {
            'federation': {
                'id': entity['FederationId'],
                'hash': entity['RowKey'],
                'batch_shipyard_federation_version':
                entity['BatchShipyardFederationVersion'],
                'unique_job_ids': entity['UniqueJobIds'],
                'storage': {
                    'account': get_storageaccount(),
                    'endpoint': get_storageaccount_endpoint(),
                    'containers': {
                        'queue': queuename,
                        'blob': contname,
                    },
                },
            }
        }
        print(json.dumps(rawout, sort_keys=True, indent=4))


def federation_requires_unique_job_ids(table_client, federation_id):
    fedhash = hash_federation_id(federation_id)
    try:
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_federation_global'],
            _ALL_FEDERATIONS_PK, fedhash)
    except azure.common.AzureMissingResourceHttpError:
        raise RuntimeError(
            'federation {} does not exist'.format(federation_id))
    return entity['UniqueJobIds']


def list_federations(table_client, config, federation_ids):
    # type: (azuretable.TableService, dict, List[str]) -> None
    """List all federations
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str federation_id: federation id
    """
    log = []
    if util.is_not_empty(federation_ids):
        log.append('listing federations: {}'.format(', '.join(federation_ids)))
        fedhashset = set()
        fedhashmap = {}
        for x in federation_ids:
            fid = x.lower()
            fhash = hash_federation_id(fid)
            fedhashmap[fhash] = fid
            fedhashset.add(fhash)
    else:
        log.append('listing all federations:')
        fedhashset = None
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_federation_global'],
            filter='PartitionKey eq \'{}\''.format(_ALL_FEDERATIONS_PK))
    except azure.common.AzureMissingResourceHttpError:
        logger.error('no federations exist')
        return
    if settings.raw(config):
        rawout = {}
    for ent in entities:
        fedhash = ent['RowKey']
        if fedhashset is not None and fedhash not in fedhashset:
            continue
        if settings.raw(config):
            rawout[ent['FederationId']] = {
                'hash': fedhash,
                'batch_shipyard_federation_version':
                ent['BatchShipyardFederationVersion'],
                'unique_job_ids': ent['UniqueJobIds'],
                'pools': {}
            }
        else:
            log.append('* federation id: {}'.format(ent['FederationId']))
            log.append('  * federation hash: {}'.format(fedhash))
            log.append('  * batch shipyard federation version: {}'.format(
                ent['BatchShipyardFederationVersion']))
            log.append('  * unique job ids: {}'.format(ent['UniqueJobIds']))
            log.append('  * pools:')
        # get list of pools associated with federation
        try:
            fedents = table_client.query_entities(
                _STORAGE_CONTAINERS['table_federation_global'],
                filter='PartitionKey eq \'{}\''.format(fedhash))
        except azure.common.AzureMissingResourceHttpError:
            continue
        numpools = 0
        for fe in fedents:
            numpools += 1
            if settings.raw(config):
                rawout[ent['FederationId']]['pools'][fe['PoolId']] = {
                    'batch_account': fe['BatchAccount'],
                    'location': fe['Location'],
                    'hash': fe['RowKey'],
                }
            else:
                log.append('    * pool id: {}'.format(fe['PoolId']))
                log.append('      * batch account: {}'.format(
                    fe['BatchAccount']))
                log.append('      * location: {}'.format(fe['Location']))
                log.append('      * pool hash: {}'.format(fe['RowKey']))
        if numpools == 0:
            log.append('    * no pools in federation')
        # get number of jobs/job schedules for federation
        _, fejobs = get_all_federation_jobs(table_client, fedhash)
        fejobs = list(fejobs)
        fejk = [x['Kind'] for x in fejobs]
        if settings.raw(config):
            rawout[ent['FederationId']]['num_jobs'] = fejk.count('job')
            rawout[ent['FederationId']]['num_job_schedules'] = fejk.count(
                'job_schedule')
        else:
            log.append('  * number of jobs: {}'.format(fejk.count('job')))
            log.append('  * number of job schedules: {}'.format(
                fejk.count('job_schedule')))
    if settings.raw(config):
        print(json.dumps(rawout, sort_keys=True, indent=4))
    else:
        if len(log) > 1:
            logger.info(os.linesep.join(log))
        else:
            logger.error('no federations exist')


def batch_delete_entities(table_client, table_name, pk, rks):
    if util.is_none_or_empty(rks):
        return
    i = 0
    tb = azuretable.TableBatch()
    for rk in rks:
        tb.delete_entity(pk, rk)
        i += 1
        if i == 100:
            table_client.commit_batch(table_name, tb)
            tb = azuretable.TableBatch()
            i = 0
    if i > 0:
        table_client.commit_batch(table_name, tb)


def collate_all_location_entities_for_job(table_client, fedhash, entity):
    loc_pk = '{}${}'.format(fedhash, entity['RowKey'])
    rks = []
    try:
        loc_entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_federation_jobs'],
            filter='PartitionKey eq \'{}\''.format(loc_pk))
    except azure.common.AzureMissingResourceHttpError:
        pass
    else:
        for loc_entity in loc_entities:
            rks.append(loc_entity['RowKey'])
    return loc_pk, rks


def get_all_federation_jobs(table_client, fedhash):
    pk = '{}${}'.format(_FEDERATION_ACTIONS_PREFIX_PK, fedhash)
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_federation_jobs'],
            filter='PartitionKey eq \'{}\''.format(pk))
    except azure.common.AzureMissingResourceHttpError:
        entities = []
    return pk, entities


def gc_federation_jobs(table_client, config, federation_id, fedhash):
    # retrieve all job sequence rows for federation
    pk, entities = get_all_federation_jobs(table_client, fedhash)
    gc_dict = {
        pk: []
    }
    # process all jobs
    for entity in entities:
        # if sequence exists, ask for confirmation
        if ('Sequence0' in entity and
                util.is_not_empty(entity['Sequence0']) and
                not util.confirm_action(
                    config,
                    msg=('destroying pending actions for job {} in '
                         'federation id {}').format(
                             entity['RowKey'], federation_id))):
            raise RuntimeError(
                'Not destroying federation job {} with pending actions '
                'in federation id {}'.format(
                    entity['RowKey'], federation_id))
        gc_dict[pk].append(entity['RowKey'])
        loc_pk, loc_rks = collate_all_location_entities_for_job(
            table_client, fedhash, entity)
        if util.is_not_empty(loc_rks) and not util.confirm_action(
                config,
                msg='orphan job {} in federation id {}'.format(
                    entity['RowKey'], federation_id)):
            raise RuntimeError(
                'Not orphaning active/completed federation job '
                '{} in federation id {}'.format(
                    entity['RowKey'], federation_id))
        gc_dict[loc_pk] = loc_rks
    # batch delete entities
    for gc_pk in gc_dict:
        batch_delete_entities(
            table_client, _STORAGE_CONTAINERS['table_federation_jobs'],
            gc_pk, gc_dict[gc_pk])


def destroy_federation_id(
        blob_client, table_client, queue_client, config, federation_id):
    # type: (azure.storage.blob.BlockBlobService, azuretable.TableService,
    #        azure.queue.QueueService, dict, str) -> None
    """Remove storage containers for federation id
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_service: queue client
    :param dict config: configuration dict
    :param str federation_id: federation id
    """
    fedhash = hash_federation_id(federation_id)
    # delete table entities for federation id
    logger.debug('deleting all federation {} job entities'.format(
        federation_id))
    gc_federation_jobs(table_client, config, federation_id, fedhash)
    # remove table entry for federation id
    logger.debug('deleting federation {} entities in global table'.format(
        federation_id))
    try:
        table_client.delete_entity(
            _STORAGE_CONTAINERS['table_federation_global'],
            _ALL_FEDERATIONS_PK, fedhash)
    except azure.common.AzureMissingResourceHttpError:
        pass
    try:
        fedentities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_federation_global'],
            filter='PartitionKey eq \'{}\''.format(fedhash))
    except azure.common.AzureMissingResourceHttpError:
        pass
    else:
        batch_delete_entities(
            table_client, _STORAGE_CONTAINERS['table_federation_global'],
            fedhash, [x['RowKey'] for x in fedentities])
    # delete job queue for federation id
    queuename = '{}-{}'.format(
        _STORAGE_CONTAINERS['queue_federation'], fedhash)
    logger.debug('deleting queue: {}'.format(queuename))
    queue_client.delete_queue(queuename)
    # delete blob container for federation id
    contname = '{}-{}'.format(_STORAGE_CONTAINERS['blob_federation'], fedhash)
    logger.debug('deleting container: {}'.format(contname))
    blob_client.delete_container(contname)
    if settings.raw(config):
        rawout = {
            'federation': {
                'id': federation_id,
                'hash': fedhash,
                'storage': {
                    'account': get_storageaccount(),
                    'endpoint': get_storageaccount_endpoint(),
                    'containers': {
                        'queue': queuename,
                        'blob': contname,
                    },
                },
            },
        }
        print(json.dumps(rawout, sort_keys=True, indent=4))


def _check_if_federation_exists(table_client, fedhash):
    try:
        table_client.get_entity(
            _STORAGE_CONTAINERS['table_federation_global'],
            _ALL_FEDERATIONS_PK, fedhash)
    except azure.common.AzureMissingResourceHttpError:
        return False
    return True


def add_pool_to_federation(
        table_client, config, federation_id, batch_service_url, pools):
    # type: (azuretable.TableService, dict, str, str, List[str]) -> None
    """Populate federation with pools
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param str batch_service_url: batch service url to associate
    :param list pools: pools to monitor
    """
    fedhash = hash_federation_id(federation_id)
    # check if federation exists
    if not _check_if_federation_exists(table_client, fedhash):
        logger.error('federation {} does not exist'.format(federation_id))
        return
    if util.is_not_empty(batch_service_url):
        batch_service_url = batch_service_url.rstrip('/')
        account, location = settings.parse_batch_service_url(
            batch_service_url)
    else:
        bc = settings.credentials_batch(config)
        batch_service_url = bc.account_service_url.rstrip('/')
        account, location = settings.parse_batch_service_url(
            batch_service_url)
    rawout = {
        'federation': {
            'id': federation_id,
            'hash': fedhash,
            'storage': {
                'account': get_storageaccount(),
                'endpoint': get_storageaccount_endpoint(),
            },
        },
        'pools_added': {}
    }
    for poolid in pools:
        rk = hash_pool_and_service_url(poolid, batch_service_url)
        entity = {
            'PartitionKey': fedhash,
            'RowKey': rk,
            'FederationId': federation_id,
            'BatchAccount': account,
            'PoolId': poolid,
            'Location': location,
            'BatchServiceUrl': batch_service_url,
        }
        if settings.verbose(config):
            logger.debug(
                'inserting pool federation entity: {}'.format(
                    entity))
        try:
            table_client.insert_entity(
                _STORAGE_CONTAINERS['table_federation_global'], entity)
        except azure.common.AzureConflictHttpError:
            logger.error(
                'federation {} entity for pool {} already exists'.format(
                    federation_id, poolid))
        else:
            logger.debug('federation {} entity added for pool {}'.format(
                federation_id, poolid))
            if settings.raw(config):
                rawout['pools_added'][entity['RowKey']] = {
                    'pool_id': entity['PoolId'],
                    'batch_account': entity['BatchAccount'],
                    'location': entity['Location'],
                    'batch_service_url': entity['BatchServiceUrl'],
                }
    if settings.raw(config) and util.is_not_empty(rawout['pools_added']):
        print(json.dumps(rawout, sort_keys=True, indent=4))


def remove_pool_from_federation(
        table_client, config, federation_id, all, batch_service_url, pools):
    # type: (azuretable.TableService, dict, str, bool, str, List[str]) -> None
    """Remove pools from federation
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param bool all: all pools
    :param str batch_service_url: batch service url to associate
    :param list pools: pools to monitor
    """
    fedhash = hash_federation_id(federation_id)
    # check if federation exists
    if not _check_if_federation_exists(table_client, fedhash):
        logger.error('federation {} does not exist'.format(federation_id))
        return
    rawout = {
        'federation': {
            'id': federation_id,
            'hash': fedhash,
            'storage': {
                'account': get_storageaccount(),
                'endpoint': get_storageaccount_endpoint(),
            },
        },
        'pools_removed': {}
    }
    logger.warning(
        '**WARNING** Removing active pools with jobs/job schedules in a '
        'federation can lead to orphaned data. It is recommended to delete '
        'all federation jobs/job schedules associated with the pools '
        'to be removed prior to removal from the federation!')
    if all:
        if util.confirm_action(
                config, 'remove all pools from federation {}'.format(
                    federation_id)):
            if settings.raw(config):
                try:
                    entities = table_client.query_entities(
                        _STORAGE_CONTAINERS['table_federation_global'],
                        filter='PartitionKey eq \'{}\''.format(fedhash))
                except azure.common.AzureMissingResourceHttpError:
                    pass
                else:
                    for entity in entities:
                        rawout['pools_removed'][entity['RowKey']] = {
                            'hash': entity['PoolId'],
                            'batch_account': entity['BatchAccount'],
                            'location': entity['Location'],
                            'batch_service_url': entity['BatchServiceUrl'],
                        }
            _clear_table(
                table_client, _STORAGE_CONTAINERS['table_federation_global'],
                config, pool_id=None, pk=fedhash)
            if (settings.raw(config) and
                    util.is_not_empty(rawout['pools_removed'])):
                print(json.dumps(rawout, sort_keys=True, indent=4))
        return
    if util.is_not_empty(batch_service_url):
        account, _ = settings.parse_batch_service_url(batch_service_url)
    else:
        bc = settings.credentials_batch(config)
        batch_service_url = bc.account_service_url
        account, _ = settings.parse_batch_service_url(batch_service_url)
    for poolid in pools:
        if not util.confirm_action(
                config, 'remove pool {} from federation {}'.format(
                    poolid, federation_id)):
            continue
        try:
            rk = hash_pool_and_service_url(poolid, batch_service_url)
            entity = None
            if settings.raw(config):
                entity = table_client.get_entity(
                    _STORAGE_CONTAINERS['table_federation_global'],
                    partition_key=fedhash,
                    row_key=rk,
                )
            table_client.delete_entity(
                _STORAGE_CONTAINERS['table_federation_global'],
                partition_key=fedhash,
                row_key=rk,
            )
        except azure.common.AzureMissingResourceHttpError:
            logger.error('pool {} is not in federation {}'.format(
                poolid, federation_id))
        else:
            logger.debug('pool {} removed from federation {}'.format(
                poolid, federation_id))
            if settings.raw(config):
                rawout['pools_removed'][entity['RowKey']] = {
                    'pool_id': entity['PoolId'],
                    'batch_account': entity['BatchAccount'],
                    'location': entity['Location'],
                    'batch_service_url': entity['BatchServiceUrl'],
                }
    if settings.raw(config) and util.is_not_empty(rawout['pools_removed']):
        print(json.dumps(rawout, sort_keys=True, indent=4))


def _pack_sequences(ent, unique_id):
    seq = []
    for i in range(0, _MAX_SEQUENCE_ID_PROPERTIES):
        prop = 'Sequence{}'.format(i)
        if prop in ent and util.is_not_empty(ent[prop]):
            seq.extend(ent[prop].split(','))
    seq.append(str(unique_id))
    if len(seq) > _MAX_SEQUENCE_IDS_PER_PROPERTY * _MAX_SEQUENCE_ID_PROPERTIES:
        raise RuntimeError(
            'maximum number of enqueued sequence ids reached, please allow '
            'job actions to drain')
    for i in range(0, _MAX_SEQUENCE_ID_PROPERTIES):
        prop = 'Sequence{}'.format(i)
        start = i * _MAX_SEQUENCE_IDS_PER_PROPERTY
        end = start + _MAX_SEQUENCE_IDS_PER_PROPERTY
        if end > len(seq):
            end = len(seq)
        if start < end:
            ent[prop] = ','.join(seq[start:end])
        else:
            ent[prop] = None


def _retrieve_and_merge_sequence(
        table_client, pk, unique_id, kind, target, entity_must_not_exist):
    rk = util.hash_string(target)
    try:
        ent = table_client.get_entity(
            _STORAGE_CONTAINERS['table_federation_jobs'], pk, rk)
        if entity_must_not_exist:
            raise RuntimeError(
                '{} {} action entity already exists: rolling back action '
                'due to unique job id requirement for federation.'.format(
                    kind, target))
    except azure.common.AzureMissingResourceHttpError:
        ent = {
            'PartitionKey': pk,
            'RowKey': rk,
            'Kind': kind,
            'Id': target,
        }
    _pack_sequences(ent, unique_id)
    return ent


def _insert_or_merge_entity_with_etag(table_client, table_name, entity):
    if 'etag' not in entity:
        try:
            table_client.insert_entity(table_name, entity=entity)
            return True
        except azure.common.AzureConflictHttpError:
            pass
    else:
        etag = entity['etag']
        entity.pop('etag')
        try:
            table_client.merge_entity(table_name, entity=entity, if_match=etag)
            return True
        except azure.common.AzureConflictHttpError:
            pass
        except azure.common.AzureHttpError as ex:
            if ex.status_code != 412:
                raise
    return False


def check_if_job_exists_in_federation(
        table_client, federation_id, job_id):
    pk = generate_job_id_locator_partition_key(federation_id, job_id)
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_federation_jobs'],
            filter='PartitionKey eq \'{}\''.format(pk))
        for ent in entities:
            return True
    except azure.common.AzureMissingResourceHttpError:
        pass
    return False


def check_if_job_is_terminated_in_federation(
        table_client, federation_id, job_id):
    pk = generate_job_id_locator_partition_key(federation_id, job_id)
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_federation_jobs'],
            filter='PartitionKey eq \'{}\''.format(pk))
    except azure.common.AzureMissingResourceHttpError:
        return False
    else:
        for ent in entities:
            if 'TerminateTimestamp' in ent:
                return True
    return False


def add_job_to_federation(
        table_client, queue_client, config, federation_id, unique_id, msg,
        kind):
    # type: (azure.cosmosdb.TableService, azure.queue.QueueService, str,
    #        uuid.UUID, dict, str) -> None
    """Add a job/job schedule to a federation
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_service: queue client
    :param str federation_id: federation id
    :param uuid.UUID unique_id: unique id
    :param dict msg: dict payload
    :param str kind: kind
    """
    requires_unique_job_ids = federation_requires_unique_job_ids(
        table_client, federation_id)
    fedhash = hash_federation_id(federation_id)
    pk = '{}${}'.format(_FEDERATION_ACTIONS_PREFIX_PK, fedhash)
    target = msg['target']
    # check if job is terminated first
    if check_if_job_is_terminated_in_federation(
            table_client, federation_id, target):
        if requires_unique_job_ids:
            raise RuntimeError(
                'cannot add {} {} as federation requires unique job '
                'ids'.format(kind, target))
        if not util.confirm_action(
                config,
                'adding {} although one or more {}s representing this {} '
                'in federation {} have been terminated'.format(
                    target, kind, kind, federation_id)):
            raise RuntimeError(
                'aborted adding {} {} to federation {}'.format(
                    kind, target, federation_id))
    # upsert unique id to sequence
    while True:
        entity = _retrieve_and_merge_sequence(
            table_client, pk, unique_id, kind, target, requires_unique_job_ids)
        if _insert_or_merge_entity_with_etag(
                table_client, _STORAGE_CONTAINERS['table_federation_jobs'],
                entity):
            logger.debug(
                'upserted {} {} sequence uid {} to federation {}'.format(
                    kind, target, unique_id, federation_id))
            break
        else:
            logger.debug(
                'conflict upserting {} {} sequence uid {} to '
                'federation {}'.format(kind, target, unique_id, federation_id))
    # add queue message
    msg_data = json.dumps(msg, ensure_ascii=True, sort_keys=True)
    contname = '{}-{}'.format(
        _STORAGE_CONTAINERS['queue_federation'], fedhash)
    queue_client.put_message(contname, msg_data, time_to_live=-1)


def list_blocked_actions_in_federation(
        table_client, config, federation_id, job_id, job_schedule_id):
    # type: (azure.cosmosdb.TableService, dict, str, str, str) -> None
    """List blocked actions in federation
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param str job_id: job id
    :param str job_schedule_id: job schedule id
    """
    fedhash = hash_federation_id(federation_id)
    pk = '{}${}'.format(_BLOCKED_FEDERATION_ACTIONS_PREFIX_PK, fedhash)
    if (util.is_none_or_empty(job_id) and
            util.is_none_or_empty(job_schedule_id)):
        logger.debug(
            'fetching all blocked jobs/job schedules for federation '
            'id {}'.format(federation_id))
        try:
            entities = table_client.query_entities(
                _STORAGE_CONTAINERS['table_federation_jobs'],
                filter='PartitionKey eq \'{}\''.format(pk))
        except azure.common.AzureMissingResourceHttpError:
            pass
    else:
        rk = util.hash_string(
            job_id if util.is_not_empty(job_id) else job_schedule_id)
        try:
            entities = [table_client.get_entity(
                _STORAGE_CONTAINERS['table_federation_jobs'], pk, rk)]
        except azure.common.AzureMissingResourceHttpError:
            pass
    if settings.raw(config):
        log = {}
    else:
        log = [
            'listing blocked jobs/job schedules for federation id {}:'.format(
                federation_id)
        ]
    for entity in entities:
        id = entity['Id']
        if settings.raw(config):
            log[id] = {
                'hash': entity['RowKey'],
                'unique_id': entity['UniqueId'],
                'task_group_size': entity['NumTasks'],
                'reason': entity['Reason'],
            }
        else:
            log.append('* id: {}'.format(id))
            log.append('  * hash: {}'.format(entity['RowKey']))
            log.append('  * unique id: {}'.format(entity['UniqueId']))
            log.append('  * task group size: {}'.format(entity['NumTasks']))
            log.append('  * reason: {}'.format(entity['Reason']))
    if settings.raw(config):
        print(json.dumps(log, sort_keys=True, indent=4))
    else:
        if len(log) > 1:
            logger.info(os.linesep.join(log))
        else:
            logger.debug(
                'no blocked jobs/job schedules exist in federation '
                'id {}'.format(federation_id))


def list_queued_actions_in_federation(
        table_client, config, federation_id, job_id, job_schedule_id):
    # type: (azure.cosmosdb.TableService, dict, str, str, str) -> None
    """List queued actions in federation
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param str job_id: job id
    :param str job_schedule_id: job schedule id
    """
    fedhash = hash_federation_id(federation_id)
    pk = '{}${}'.format(_FEDERATION_ACTIONS_PREFIX_PK, fedhash)
    if (util.is_none_or_empty(job_id) and
            util.is_none_or_empty(job_schedule_id)):
        logger.debug(
            'fetching all queued jobs/job schedules for federation '
            'id {}'.format(federation_id))
        try:
            entities = table_client.query_entities(
                _STORAGE_CONTAINERS['table_federation_jobs'],
                filter='PartitionKey eq \'{}\''.format(pk))
        except azure.common.AzureMissingResourceHttpError:
            pass
    else:
        rk = util.hash_string(
            job_id if util.is_not_empty(job_id) else job_schedule_id)
        try:
            entities = [table_client.get_entity(
                _STORAGE_CONTAINERS['table_federation_jobs'], pk, rk)]
        except azure.common.AzureMissingResourceHttpError:
            pass
    if settings.raw(config):
        log = {}
    else:
        log = [
            'listing queued jobs/job schedules for federation id {}:'.format(
                federation_id)
        ]
    for entity in entities:
        if ('Sequence0' not in entity or
                util.is_none_or_empty(entity['Sequence0'])):
            continue
        id = entity['Id']
        uids = entity['Sequence0'].split(',')[:10]
        if settings.raw(config):
            log[id] = {
                'kind': entity['Kind'],
                'hash': entity['RowKey'],
                'first_ten_unique_ids': uids,
            }
        else:
            log.append('* id: {}'.format(id))
            log.append('  * kind: {}'.format(entity['Kind']))
            log.append('  * hash: {}'.format(entity['RowKey']))
            log.append('  * first ten unique ids:')
            for uid in uids:
                log.append('    * {}'.format(uid))
    if settings.raw(config):
        print(json.dumps(log, sort_keys=True, indent=4))
    else:
        if len(log) > 1:
            logger.info(os.linesep.join(log))
        else:
            logger.debug(
                'no queued jobs/job schedules exist in federation '
                'id {}'.format(federation_id))


def list_active_jobs_in_federation(
        table_client, config, federation_id, job_id, job_schedule_id):
    # type: (azure.cosmosdb.TableService, dict, str, str, str) -> None
    """List active jobs in federation
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param str job_id: job id
    :param str job_schedule_id: job schedule id
    """
    fedhash = hash_federation_id(federation_id)
    if (util.is_none_or_empty(job_id) and
            util.is_none_or_empty(job_schedule_id)):
        targets = []
        logger.debug(
            'fetching all active jobs/job schedules for federation '
            'id {}'.format(federation_id))
        _, entities = get_all_federation_jobs(table_client, fedhash)
        for entity in entities:
            targets.append(entity['RowKey'])
    else:
        targets = [job_id if util.is_not_empty(job_id) else job_schedule_id]
    if len(targets) == 0:
        logger.error(
            'no active jobs/job schedules in federation id {}'.format(
                federation_id))
        return
    if settings.raw(config):
        log = {}
    else:
        log = [
            'listing active jobs/job schedules for federation id {}:'.format(
                federation_id)
        ]
    for targethash in targets:
        try:
            entities = table_client.query_entities(
                _STORAGE_CONTAINERS['table_federation_jobs'],
                filter='PartitionKey eq \'{}${}\''.format(fedhash, targethash))
        except azure.common.AzureMissingResourceHttpError:
            pass
        kind = None
        for ent in entities:
            id = ent['Id']
            if kind is None:
                kind = ent['Kind']
                if settings.raw(config):
                    log[id] = {
                        'type': kind,
                        'hash': targethash,
                    }
                else:
                    log.append('* id: {}'.format(id))
                    log.append('  * type: {}'.format(kind))
                    log.append('  * hash: {}'.format(targethash))
            if 'AdditionTimestamps' in ent:
                ats = ent['AdditionTimestamps'].split(',')[-10:]
            else:
                ats = None
            if 'UniqueIds' in ent:
                uids = ent['UniqueIds'].split(',')[-10:]
            else:
                uids = None
            if settings.raw(config):
                poolid = ent['PoolId']
                log[id][poolid] = {
                    'batch_account': ent['BatchAccount'],
                    'service_url': ent['ServiceUrl'],
                }
                log[id][poolid]['ten_most_recent_task_additions'] = ats
                log[id][poolid]['ten_most_recent_unique_ids_serviced'] = uids
                log[id][poolid]['terminate_timestamp'] = (
                    ent['TerminateTimestamp'] if 'TerminateTimestamp' in ent
                    else None
                )
            else:
                log.append('  * pool id: {}'.format(ent['PoolId']))
                log.append('    * batch account: {}'.format(
                    ent['BatchAccount']))
                log.append('    * service url: {}'.format(ent['ServiceUrl']))
                log.append('    * ten most recent task addition times:')
                if util.is_not_empty(ats):
                    for at in ats:
                        log.append('      * {}'.format(at))
                else:
                    log.append('      * n/a')
                log.append('    * ten most recent unique ids serviced:')
                if util.is_not_empty(uids):
                    for uid in uids:
                        log.append('      * {}'.format(uid))
                else:
                    log.append('      * n/a')
                log.append('    * termination time: {}'.format(
                    ent['TerminateTimestamp'] if 'TerminateTimestamp' in ent
                    else 'n/a'))
    if settings.raw(config):
        print(json.dumps(log, sort_keys=True, indent=4))
    else:
        if len(log) > 1:
            logger.info(os.linesep.join(log))
        else:
            logger.error(
                'no active jobs/job schedules exist in federation '
                'id {}'.format(federation_id))


def pickle_and_upload(blob_client, data, rpath, federation_id=None):
    # type: (azureblob.BlockBlobService, dict, str, str) -> str
    """Pickle and upload data to a given remote path
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict data: data to pickle
    :param str rpath: remote path
    :param str federation_id: federation id
    :rtype: str
    :return: sas url of uploaded pickle
    """
    f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
    fname = f.name
    try:
        with open(fname, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.close()
        if util.is_none_or_empty(federation_id):
            sas_urls = upload_resource_files(blob_client, [(rpath, fname)])
        else:
            sas_urls = upload_job_for_federation(
                blob_client, federation_id, [(rpath, fname)])
        if len(sas_urls) != 1:
            raise RuntimeError(
                'unexpected number of sas urls for pickled upload')
        return next(iter(sas_urls.values()))
    finally:
        try:
            os.unlink(fname)
        except OSError:
            pass
        del f
        del fname


def delete_or_terminate_job_from_federation(
        blob_client, table_client, queue_client, config, delete, federation_id,
        job_id, job_schedule_id, all_jobs, all_jobschedules, force):
    # type: (azure.storage.blob.BlockBlobService, azure.cosmosdb.TableService,
    #        azure.queue.QueueService, bool, str, str, str, bool,
    #        bool, bool) -> None
    """Delete or terminate a job from a federation
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_service: queue client
    :param bool delete: delete instead of terminate
    :param str federation_id: federation id
    :param str job_id: job id
    :param str job_schedule_id: job schedule id
    :param bool all_jobs: all jobs
    :param bool all_jobschedules: all jobschedules
    :param bool force: force
    """
    fedhash = hash_federation_id(federation_id)
    if all_jobs or all_jobschedules:
        if all_jobs:
            kind = 'job'
        elif all_jobschedules:
            kind = 'job_schedule'
        targets = []
        logger.debug('fetching all {}s for federation id {}'.format(
            kind, federation_id))
        pk, entities = get_all_federation_jobs(table_client, fedhash)
        for entity in entities:
            if entity['Kind'] == kind:
                targets.append(entity['RowKey'])
    else:
        pk = '{}${}'.format(_FEDERATION_ACTIONS_PREFIX_PK, fedhash)
        kind = 'job' if util.is_not_empty(job_id) else 'job_schedule'
        targets = job_id if util.is_not_empty(job_id) else job_schedule_id
    method = 'delete' if delete else 'terminate'
    if len(targets) == 0:
        logger.error(
            'no {}s to {} in federation id {}'.format(
                kind, method, federation_id))
        return
    raw_output = {}
    for target in targets:
        # if terminate, check if job exists
        if not force and method == 'terminate':
            if not check_if_job_exists_in_federation(
                    table_client, federation_id, target):
                logger.warning(
                    'skipping termination of non-existent job {} in '
                    'federation {}'.format(target, federation_id))
                continue
        if not util.confirm_action(
                config,
                msg='{} {} id {} in federation {}'.format(
                    method, kind, target, federation_id)):
            return
        unique_id = uuid.uuid4()
        rpath = 'messages/{}.pickle'.format(unique_id)
        # upload message data to blob
        info = {
            'version': '1',
            'action': {
                'method': method,
                'kind': kind,
            },
            kind: {
                'id': target,
            },
        }
        sas_url = pickle_and_upload(
            blob_client, info, rpath, federation_id=federation_id)
        # upsert unique id to sequence
        while True:
            entity = _retrieve_and_merge_sequence(
                table_client, pk, unique_id, kind, target, False)
            if _insert_or_merge_entity_with_etag(
                    table_client, _STORAGE_CONTAINERS['table_federation_jobs'],
                    entity):
                logger.debug(
                    'upserted {} {} sequence uid {} to federation {}'.format(
                        kind, target, unique_id, federation_id))
                break
            else:
                logger.debug(
                    'conflict upserting {} {} sequence uid {} to '
                    'federation {}'.format(
                        kind, target, unique_id, federation_id))
        # add queue message
        msg = {
            'version': '1',
            'federation_id': federation_id,
            'target': target,
            'blob_data': sas_url,
            'uuid': str(unique_id),
        }
        msg_data = json.dumps(msg, ensure_ascii=True, sort_keys=True)
        contname = '{}-{}'.format(
            _STORAGE_CONTAINERS['queue_federation'], fedhash)
        queue_client.put_message(contname, msg_data, time_to_live=-1)
        logger.debug('enqueued {} of {} {} for federation {}'.format(
            method, kind, target, federation_id))
        if settings.raw(config):
            raw_output[target] = {
                'federation': {
                    'id': federation_id,
                    'storage': {
                        'account': get_storageaccount(),
                        'endpoint': get_storageaccount_endpoint(),
                    },
                },
                'kind': kind,
                'action': method,
                'unique_id': str(unique_id),
            }
    if util.is_not_empty(raw_output):
        print(json.dumps(raw_output, indent=4, sort_keys=True))


def zap_unique_id_from_federation(
        blob_client, config, federation_id, unique_id):
    # type: (azure.storage.blob.BlockBlobService, dict, str, str) -> None
    """Zap a unique id from a federation
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param str federation_id: federation id
    :param str unique_id: unique id
    """
    jloc = 'messages/{}.pickle'.format(unique_id)
    deleted = delete_resource_file(
        blob_client, jloc, federation_id=federation_id)
    if deleted and settings.raw(config):
        rawout = {
            'federation': {
                'id': federation_id,
                'storage': {
                    'account': get_storageaccount(),
                    'endpoint': get_storageaccount_endpoint(),
                },
            },
            'unique_id': unique_id,
        }
        print(json.dumps(rawout, sort_keys=True, indent=4))


def create_slurm_partition(
        table_client, queue_client, config, cluster_id, partition_name,
        batch_service_url, pool_id, compute_node_type, max_compute_nodes,
        hostlist):
    partpool_hash = util.hash_string('{}-{}'.format(
        partition_name, batch_service_url, pool_id))
    # insert partition entity
    entity = {
        'PartitionKey': 'PARTITIONS${}'.format(cluster_id),
        'RowKey': '{}${}'.format(partition_name, partpool_hash),
        'BatchServiceUrl': batch_service_url,
        'BatchPoolId': pool_id,
        'ComputeNodeType': compute_node_type,
        'HostList': hostlist,
        'BatchShipyardSlurmVersion': 1,
    }
    logger.debug(
        'inserting slurm partition {}:{} entity to table for '
        'cluster {}'.format(partition_name, pool_id, cluster_id))
    try:
        table_client.insert_entity(_STORAGE_CONTAINERS['table_slurm'], entity)
    except azure.common.AzureConflictHttpError:
        logger.error('partition {}:{} cluster id {} already exists'.format(
            partition_name, pool_id, cluster_id))
        if util.confirm_action(
                config, 'overwrite existing partition {}:{} for '
                'cluster {}; this can result in undefined behavior'.format(
                    partition_name, pool_id, cluster_id)):
            table_client.insert_or_replace_entity(
                _STORAGE_CONTAINERS['table_slurm'], entity)
        else:
            raise
    # create queue
    qname = '{}-{}'.format(cluster_id, partpool_hash)
    logger.debug('creating queue: {}'.format(qname))
    queue_client.create_queue(qname)


def get_slurm_host_node_id(table_client, cluster_id, host):
    node_id = None
    try:
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_slurm'],
            '{}${}'.format('HOSTS', cluster_id), host)
        node_id = entity['BatchNodeId']
    except (azure.common.AzureMissingResourceHttpError, KeyError):
        pass
    return node_id


def clear_slurm_table_entities(table_client, cluster_id):
    logger.debug('deleting slurm cluster {} entities in table'.format(
        cluster_id))
    tablename = _STORAGE_CONTAINERS['table_slurm']
    keys = ['HOSTS', 'PARTITIONS']
    for key in keys:
        try:
            pk = '{}${}'.format(key, cluster_id)
            entities = table_client.query_entities(
                tablename,
                filter='PartitionKey eq \'{}\''.format(pk))
        except azure.common.AzureMissingResourceHttpError:
            pass
        else:
            batch_delete_entities(
                table_client, tablename, pk, [x['RowKey'] for x in entities]
            )


def _check_file_and_upload(blob_client, file, key, container=None):
    # type: (azure.storage.blob.BlockBlobService, tuple, str, str) -> None
    """Upload file to blob storage if necessary
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param tuple file: file to upload
    :param str key: blob container key
    :param str container: absolute container override
    """
    if file[0] is None:
        return
    contname = container or _STORAGE_CONTAINERS[key]
    upload = True
    # check if blob exists
    try:
        prop = blob_client.get_blob_properties(contname, file[0])
        if (prop.properties.content_settings.content_md5 ==
                util.compute_md5_for_file(file[1], True)):
            logger.debug(
                'remote file is the same for {}, skipping'.format(file[0]))
            upload = False
    except azure.common.AzureMissingResourceHttpError:
        pass
    if upload:
        logger.info('uploading file {} as {!r}'.format(file[1], file[0]))
        blob_client.create_blob_from_path(contname, file[0], str(file[1]))


def delete_resource_file(blob_client, blob_name, federation_id=None):
    # type: (azure.storage.blob.BlockBlobService, str) -> bool
    """Delete a resource file from blob storage
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str blob_name: blob name
    :param str federation_id: federation id
    """
    if util.is_not_empty(federation_id):
        fedhash = hash_federation_id(federation_id)
        container = '{}-{}'.format(
            _STORAGE_CONTAINERS['blob_federation'], fedhash)
    else:
        container = _STORAGE_CONTAINERS['blob_resourcefiles']
    try:
        blob_client.delete_blob(container, blob_name)
        logger.debug('blob {} deleted from container {}'.format(
            blob_name, container))
    except azure.common.AzureMissingResourceHttpError:
        logger.warning('blob {} does not exist in container {}'.format(
            blob_name, container))
        return False
    return True


def upload_resource_files(blob_client, files):
    # type: (azure.storage.blob.BlockBlobService, List[tuple]) -> dict
    """Upload resource files to blob storage
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param list files: files to upload
    :rtype: dict
    :return: sas url dict
    """
    sas_urls = {}
    for file in files:
        _check_file_and_upload(blob_client, file, 'blob_resourcefiles')
        sas_urls[file[0]] = 'https://{}.blob.{}/{}/{}?{}'.format(
            _STORAGEACCOUNT, _STORAGEACCOUNTEP,
            _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
            blob_client.generate_blob_shared_access_signature(
                _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
                permission=azureblob.BlobPermissions.READ,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS)
            )
        )
    return sas_urls


def upload_for_nonbatch(blob_client, files, kind):
    # type: (azure.storage.blob.BlockBlobService, List[tuple],
    #        str) -> List[str]
    """Upload files to blob storage for non-batch
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param list files: files to upload
    :param str kind: "remotefs", "monitoring" or "federation"
    :rtype: list
    :return: list of file urls
    """
    if kind == 'federation':
        kind = '{}_global'.format(kind.lower())
    key = 'blob_{}'.format(kind.lower())
    ret = []
    for file in files:
        _check_file_and_upload(blob_client, file, key)
        ret.append('https://{}.blob.{}/{}/{}'.format(
            _STORAGEACCOUNT, _STORAGEACCOUNTEP,
            _STORAGE_CONTAINERS[key], file[0]))
    return ret


def upload_to_container(blob_client, sa, files, container, gen_sas=True):
    # type: (azure.storage.blob.BlockBlobService,
    #        settings.StorageCredentialsSettings, List[tuple],
    #        str, bool) -> dict
    """Upload files to a specific blob storage container
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param settings.StorageCredentialsSettings sa: storage account
    :param list files: files to upload
    :param str container: container
    :param bool gen_sas: generate a SAS URL for blob
    :rtype: dict
    :return: sas url dict
    """
    sas_urls = {}
    for file in files:
        _check_file_and_upload(blob_client, file, None, container=container)
        sas_urls[file[0]] = 'https://{}.blob.{}/{}/{}'.format(
            sa.account, sa.endpoint, container, file[0],
        )
        if gen_sas:
            sas_urls[file[0]] = '{}?{}'.format(
                sas_urls[file[0]],
                blob_client.generate_blob_shared_access_signature(
                    container, file[0],
                    permission=azureblob.BlobPermissions.READ,
                    expiry=datetime.datetime.utcnow() +
                    datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS)
                )
            )
    return sas_urls


def create_global_lock_blob(blob_client, kind):
    # type: (azure.storage.blob.BlockBlobService, str) -> None
    """Create a global lock blob
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str kind: "remotefs", "monitoring" or "federation"
    """
    if kind == 'federation':
        kind = '{}_global'.format(kind.lower())
    key = 'blob_{}'.format(kind.lower())
    blob_client.create_blob_from_bytes(
        _STORAGE_CONTAINERS[key], 'global.lock', b'')


def upload_job_for_federation(blob_client, federation_id, files):
    # type: (azure.storage.blob.BlockBlobService, str,
    #        List[tuple]) -> List[str]
    """Upload files to blob storage for federation jobs
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str federation_id: federation id
    :param list files: files to upload
    :rtype: list
    :return: list of file urls
    """
    fedhash = hash_federation_id(federation_id)
    contname = '{}-{}'.format(_STORAGE_CONTAINERS['blob_federation'], fedhash)
    sas_urls = {}
    for file in files:
        _check_file_and_upload(blob_client, file, None, container=contname)
        sas_urls[file[0]] = 'https://{}.blob.{}/{}/{}?{}'.format(
            _STORAGEACCOUNT, _STORAGEACCOUNTEP,
            contname, file[0],
            blob_client.generate_blob_shared_access_signature(
                contname, file[0],
                permission=azureblob.BlobPermissions(read=True, delete=True),
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS)
            )
        )
    return sas_urls


def delete_storage_containers(
        blob_client, table_client, config, skip_tables=False):
    # type: (azureblob.BlockBlobService, azuretable.TableService,
    #        dict, bool) -> None
    """Delete storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool skip_tables: skip deleting tables
    """
    for key in _STORAGE_CONTAINERS:
        # TODO add table_images to below on next release
        if (key == 'table_dht' or key == 'table_registry' or
                key == 'table_torrentinfo'):
            # TODO remove in future release: unused table
            logger.debug('deleting table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.delete_table(_STORAGE_CONTAINERS[key])
        elif key == 'blob_torrents':
            # TODO remove in future release: unused container
            logger.debug(
                'deleting container: {}'.format(_STORAGE_CONTAINERS[key]))
            blob_client.delete_container(_STORAGE_CONTAINERS[key])
        elif key.startswith('blob_'):
            if (key == 'blob_remotefs' or key == 'blob_monitoring' or
                    key == 'blob_federation' or
                    key == 'blob_federation_global'):
                continue
            logger.debug('deleting container: {}'.format(
                _STORAGE_CONTAINERS[key]))
            blob_client.delete_container(_STORAGE_CONTAINERS[key])
        elif not skip_tables and key.startswith('table_'):
            logger.debug('deleting table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.delete_table(_STORAGE_CONTAINERS[key])


def _clear_blobs(blob_client, container):
    # type: (azureblob.BlockBlobService, str) -> None
    """Clear blobs in container
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str container: container to clear blobs from
    """
    logger.info('deleting blobs: {}'.format(container))
    try:
        blobs = blob_client.list_blobs(container)
    except azure.common.AzureMissingResourceHttpError:
        logger.warning('container not found: {}'.format(container))
    else:
        for blob in blobs:
            blob_client.delete_blob(container, blob.name)


def _clear_blob_task_resourcefiles(blob_client, container, config):
    # type: (azureblob.BlockBlobService, str, dict) -> None
    """Clear task resource file blobs in container
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str container: container to clear blobs from
    :param dict config: configuration dict
    """
    bs = settings.batch_shipyard_settings(config)
    envfileloc = '{}taskrf-'.format(bs.storage_entity_prefix)
    logger.info('deleting blobs with prefix: {}'.format(envfileloc))
    try:
        blobs = blob_client.list_blobs(container, prefix=envfileloc)
    except azure.common.AzureMissingResourceHttpError:
        logger.warning('container not found: {}'.format(container))
    else:
        for blob in blobs:
            blob_client.delete_blob(container, blob.name)


def _clear_table(table_client, table_name, config, pool_id=None, pk=None):
    # type: (azuretable.TableService, str, dict, str, str) -> None
    """Clear table entities
    :param azure.cosmosdb.table.TableService table_client: table client
    :param str table_name: table name
    :param dict config: configuration dict
    :param str pool_id: use specified pool id instead
    :param str pk: partition key
    """
    if pk is None:
        pk = _construct_partition_key_from_config(config, pool_id=pool_id)
    logger.debug('clearing table (pk={}): {}'.format(pk, table_name))
    ents = table_client.query_entities(
        table_name, filter='PartitionKey eq \'{}\''.format(pk))
    # batch delete entities
    i = 0
    bet = azuretable.TableBatch()
    for ent in ents:
        bet.delete_entity(ent['PartitionKey'], ent['RowKey'])
        i += 1
        if i == 100:
            table_client.commit_batch(table_name, bet)
            bet = azuretable.TableBatch()
            i = 0
    if i > 0:
        table_client.commit_batch(table_name, bet)


def clear_storage_containers(
        blob_client, table_client, config, tables_only=False, pool_id=None):
    # type: (azureblob.BlockBlobService, azuretable.TableService, dict,
    #        bool, str) -> None
    """Clear storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool tables_only: clear only tables
    :param str pool_id: use specified pool id instead
    """
    bs = settings.batch_shipyard_settings(config)
    for key in _STORAGE_CONTAINERS:
        # TODO remove in a future release: unused container
        if key == 'blob_torrents':
            continue
        if not tables_only and key.startswith('blob_'):
            if (key == 'blob_remotefs' or key == 'blob_monitoring' or
                    key == 'blob_federation' or
                    key == 'blob_federation_global'):
                continue
            _clear_blobs(blob_client, _STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            # TODO remove in a future release: unused table
            if (key == 'table_dht' or key == 'table_images' or
                    key == 'table_registry' or key == 'table_torrentinfo'):
                continue
            if (key == 'table_monitoring' or
                    key == 'table_federation_global' or
                    key == 'table_federation_jobs' or
                    key == 'table_slurm'):
                continue
            try:
                _clear_table(
                    table_client, _STORAGE_CONTAINERS[key], config,
                    pool_id=pool_id)
            except azure.common.AzureMissingResourceHttpError:
                if key != 'table_perf' or bs.store_timing_metrics:
                    raise


def delete_or_clear_diagnostics_logs(blob_client, config, delete):
    # type: (azureblob.BlockBlobService, dict, bool) -> None
    """Clear diagnostics logs container
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param bool delete: delete instead of clear
    """
    bs = settings.batch_shipyard_settings(config)
    cont = bs.storage_entity_prefix + '-diaglogs'
    if not util.confirm_action(
            config, '{} diagnostics logs'.format(
                'delete' if delete else 'clear')):
        return
    if delete:
        logger.debug('deleting container: {}'.format(cont))
        blob_client.delete_container(cont)
    else:
        _clear_blobs(blob_client, cont)


def create_storage_containers(blob_client, table_client, config):
    # type: (azureblob.BlockBlobService, azuretable.TableService, dict) -> None
    """Create storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    bs = settings.batch_shipyard_settings(config)
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            # TODO remove in a future release: unused container
            if key == 'blob_torrents':
                continue
            if (key == 'blob_remotefs' or key == 'blob_monitoring' or
                    key == 'blob_federation' or
                    key == 'blob_federation_global'):
                continue
            logger.info('creating container: {}'.format(
                _STORAGE_CONTAINERS[key]))
            while True:
                blob_client.create_container(_STORAGE_CONTAINERS[key])
                if blob_client.exists(_STORAGE_CONTAINERS[key]):
                    break
                time.sleep(1)
        elif key.startswith('table_'):
            # TODO remove in a future release: unused table
            if (key == 'table_dht' or key == 'table_images' or
                    key == 'table_registry' or key == 'table_torrentinfo'):
                continue
            if (key == 'table_monitoring' or
                    key == 'table_federation_global' or
                    key == 'table_federation_jobs' or
                    key == 'table_slurm'):
                continue
            if key == 'table_perf' and not bs.store_timing_metrics:
                continue
            logger.info('creating table: {}'.format(_STORAGE_CONTAINERS[key]))
            while True:
                table_client.create_table(_STORAGE_CONTAINERS[key])
                if table_client.exists(_STORAGE_CONTAINERS[key]):
                    break
                time.sleep(1)


def create_storage_containers_nonbatch(
        blob_client, table_client, queue_client, kind):
    # type: (azureblob.BlockBlobService, azuretable.TableService,
    #        azurequeue.QueueService, str) -> None
    """Create storage containers used for non-batch actions
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_service: queue client
    :param str kind: kind, "remotefs", "monitoring", "federation", or "slurm"
    """
    if kind == 'federation':
        create_storage_containers_nonbatch(
            blob_client, table_client, None, 'federation_global')
        create_storage_containers_nonbatch(
            None, table_client, None, 'federation_jobs')
    else:
        if blob_client is not None:
            try:
                key = 'blob_{}'.format(kind.lower())
                contname = _STORAGE_CONTAINERS[key]
            except KeyError:
                pass
            else:
                logger.info('creating container: {}'.format(contname))
                while True:
                    blob_client.create_container(contname)
                    if blob_client.exists(contname):
                        break
                    time.sleep(1)
        if table_client is not None:
            try:
                key = 'table_{}'.format(kind.lower())
                contname = _STORAGE_CONTAINERS[key]
            except KeyError:
                pass
            else:
                logger.info('creating table: {}'.format(contname))
                while True:
                    table_client.create_table(contname)
                    if table_client.exists(contname):
                        break
                    time.sleep(1)
        if queue_client is not None:
            try:
                key = 'queue_{}'.format(kind.lower())
                contname = _STORAGE_CONTAINERS[key]
            except KeyError:
                pass
            else:
                logger.info('creating queue: {}'.format(contname))
                while True:
                    queue_client.create_queue(contname)
                    if queue_client.exists(contname):
                        break
                    time.sleep(1)


def delete_storage_containers_nonbatch(
        blob_client, table_client, queue_client, kind):
    # type: (azureblob.BlockBlobService, azuretable.TableService,
    #        azurequeue.QueueService, str) -> None
    """Delete storage containers used for non-batch actions
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param azure.storage.queue.QueueService queue_service: queue client
    :param str kind: kind, "remotefs", "monitoring" or "federation"
    """
    if kind == 'federation':
        delete_storage_containers_nonbatch(
            blob_client, table_client, queue_client, 'federation_global')
        delete_storage_containers_nonbatch(
            None, table_client, None, 'federation_jobs')
    else:
        if blob_client is not None:
            try:
                key = 'blob_{}'.format(kind.lower())
                contname = _STORAGE_CONTAINERS[key]
            except KeyError:
                pass
            else:
                logger.info('deleting container: {}'.format(contname))
                try:
                    blob_client.delete_container(contname)
                except azure.common.AzureMissingResourceHttpError:
                    logger.warning('container not found: {}'.format(contname))
        if table_client is not None:
            try:
                key = 'table_{}'.format(kind.lower())
                contname = _STORAGE_CONTAINERS[key]
            except KeyError:
                pass
            else:
                logger.debug('deleting table: {}'.format(contname))
                try:
                    table_client.delete_table(contname)
                except azure.common.AzureMissingResourceHttpError:
                    logger.warning('table not found: {}'.format(contname))
        if queue_client is not None:
            try:
                key = 'queue_{}'.format(kind.lower())
                contname = _STORAGE_CONTAINERS[key]
            except KeyError:
                pass
            else:
                logger.debug('deleting queue: {}'.format(contname))
                try:
                    queue_client.delete_queue(contname)
                except azure.common.AzureMissingResourceHttpError:
                    logger.warning('queue not found: {}'.format(contname))


def delete_file_share_directory(storage_settings, share, directory):
    # type: (StorageCredentialsSettings, str, str) -> None
    """Delete file share directory recursively
    :param StorageCredentialsSettings storage_settings: storage settings
    :param str share: share
    :param str directory: directory to delete
    """
    file_client = azurefile.FileService(
        account_name=storage_settings.account,
        account_key=storage_settings.account_key,
        endpoint_suffix=storage_settings.endpoint)
    logger.info(
        'recursively deleting files and directories in share {} at '
        'directory {}'.format(share, directory))
    del_dirs = []
    dirs = [directory]
    while len(dirs) > 0:
        dir = dirs.pop()
        try:
            objects = file_client.list_directories_and_files(
                share, directory_name=dir)
        except azure.common.AzureMissingResourceHttpError:
            logger.warning('directory {} does not exist on share {}'.format(
                directory, share))
            continue
        del_dirs.append(dir)
        for obj in objects:
            path = '{}/{}'.format(dir or '', obj.name)
            if type(obj) == azurefile.models.File:
                logger.debug('deleting file {} on share {}'.format(
                    path, share))
                file_client.delete_file(share, '', path)
            else:
                dirs.append(path)
                del_dirs.append(path)
    for dir in del_dirs[::-1]:
        logger.debug('deleting directory {} on share {}'.format(dir, share))
        file_client.delete_directory(share, dir)


def delete_storage_containers_boot_diagnostics(
        blob_client, vm_name, vm_id):
    # type: (azureblob.BlockBlobService, str, str) -> None
    """Delete storage containers used for remotefs bootdiagnostics
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str vm_name: vm name
    :param str vm_id: vm id
    """
    name = re.sub('[\W_]+', '', vm_name)  # noqa
    contname = 'bootdiagnostics-{}-{}'.format(
        name[0:min((9, len(name)))], vm_id)
    logger.info('deleting container: {}'.format(contname))
    try:
        blob_client.delete_container(contname)
    except azure.common.AzureMissingResourceHttpError:
        logger.warning('container not found: {}'.format(contname))


def cleanup_with_del_pool(blob_client, table_client, config, pool_id=None):
    # type: (azureblob.BlockBlobService, azuretable.TableService,
    #        dict, str) -> None
    """Special cleanup routine in combination with delete pool
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str pool_id: pool id
    """
    if util.is_none_or_empty(pool_id):
        pool_id = settings.pool_id(config)
    if not util.confirm_action(
            config, 'delete/cleanup of Batch Shipyard metadata in storage '
            'containers associated with {} pool'.format(pool_id)):
        return
    clear_storage_containers(
        blob_client, table_client, config, tables_only=True, pool_id=pool_id)
    delete_storage_containers(
        blob_client, table_client, config, skip_tables=True)
