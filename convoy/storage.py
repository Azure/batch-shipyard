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
import hashlib
import json
import logging
import re
# non-stdlib imports
import azure.common
import azure.cosmosdb.table as azuretable
import azure.storage.blob as azureblob
import azure.storage.file as azurefile
# local imports
from . import settings
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_DEFAULT_SAS_EXPIRY_DAYS = 365 * 30
_STORAGEACCOUNT = None
_STORAGEACCOUNTKEY = None
_STORAGEACCOUNTEP = None
_STORAGE_CONTAINERS = {
    'blob_globalresources': None,
    'blob_resourcefiles': None,
    'blob_torrents': None,
    'blob_remotefs': None,
    'blob_monitoring': None,
    'table_dht': None,
    'table_torrentinfo': None,
    'table_images': None,
    'table_globalresources': None,
    'table_monitoring': None,
    'table_perf': None,
    # TODO remove following in future release
    'table_registry': None,
}
_MONITOR_BATCHPOOL_PK = 'BatchPool'
_MONITOR_REMOTEFS_PK = 'RemoteFS'


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
    _STORAGE_CONTAINERS['blob_torrents'] = '-'.join(
        (sep + 'tor', postfix))
    _STORAGE_CONTAINERS['blob_remotefs'] = sep + 'remotefs'
    _STORAGE_CONTAINERS['blob_monitoring'] = sep + 'monitor'
    _STORAGE_CONTAINERS['table_dht'] = sep + 'dht'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    _STORAGE_CONTAINERS['table_images'] = sep + 'images'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'gr'
    _STORAGE_CONTAINERS['table_monitoring'] = sep + 'monitor'
    _STORAGE_CONTAINERS['table_perf'] = sep + 'perf'
    # TODO remove following containers in future release
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
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
            ep = '.'.join(
                props.primary_endpoints.blob.rstrip('/').split('.')[2:])
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
    blob_client = azureblob.BlockBlobService(
        account_name=storage_settings.account,
        account_key=storage_settings.account_key,
        endpoint_suffix=storage_settings.endpoint)
    if create_container:
        blob_client.create_container(container, fail_on_exist=False)
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
        file_client.create_share(file_share, fail_on_exist=False)
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


def create_saskey(storage_settings, path, file, create, read, write, delete):
    # type: (settings.StorageCredentialsSettings, str, bool, bool, bool,
    #        bool, bool) -> None
    """Create an object-level sas key
    :param settings.StorageCredentialsSetting storage_settings:
        storage settings
    :param str path: path
    :param bool file: file sas
    :param bool create: create perm
    :param bool read: read perm
    :param bool write: write perm
    :param bool delete: delete perm
    :rtype: str
    :return: sas token
    """
    if file:
        client = azurefile.FileService(
            account_name=storage_settings.account,
            account_key=storage_settings.account_key,
            endpoint_suffix=storage_settings.endpoint)
        perm = azurefile.FilePermissions(
            read=read, create=create, write=write, delete=delete)
        tmp = path.split('/')
        if len(tmp) < 2:
            raise ValueError('path is invalid: {}'.format(path))
        share_name = tmp[0]
        if len(tmp) == 2:
            directory_name = ''
            file_name = tmp[1]
        else:
            directory_name = tmp[1]
            file_name = '/'.join(tmp[2:])
        sas = client.generate_file_shared_access_signature(
            share_name=share_name, directory_name=directory_name,
            file_name=file_name, permission=perm,
            expiry=datetime.datetime.utcnow() +
            datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS)
        )
    else:
        client = azureblob.BlockBlobService(
            account_name=storage_settings.account,
            account_key=storage_settings.account_key,
            endpoint_suffix=storage_settings.endpoint)
        perm = azureblob.BlobPermissions(
            read=read, create=create, write=write, delete=delete)
        tmp = path.split('/')
        if len(tmp) < 1:
            raise ValueError('path is invalid: {}'.format(path))
        container_name = tmp[0]
        blob_name = '/'.join(tmp[1:])
        sas = client.generate_blob_shared_access_signature(
            container_name=container_name, blob_name=blob_name,
            permission=perm,
            expiry=datetime.datetime.utcnow() +
            datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS)
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
        else:
            raise NotImplementedError(
                'global resource type: {}'.format(grtype))
        for gr in resources:
            resource = '{}:{}'.format(prefix, gr)
            resource_sha1 = hashlib.sha1(
                resource.encode('utf8')).hexdigest()
            logger.info('adding global resource: {} hash={}'.format(
                resource, resource_sha1))
            table_client.insert_or_replace_entity(
                _STORAGE_CONTAINERS['table_globalresources'],
                {
                    'PartitionKey': pk,
                    'RowKey': resource_sha1,
                    'Resource': resource,
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
        _clear_table(
            table_client, _STORAGE_CONTAINERS['table_monitoring'], config,
            pool_id=None, pk=_MONITOR_BATCHPOOL_PK)
        return
    if len(pools) > 0:
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
    if len(fsclusters) > 0:
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


def _check_file_and_upload(blob_client, file, container):
    # type: (azure.storage.blob.BlockBlobService, tuple, str) -> None
    """Upload file to blob storage if necessary
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param tuple file: file to upload
    :param str container: blob container ref
    """
    if file[0] is None:
        return
    upload = True
    # check if blob exists
    try:
        prop = blob_client.get_blob_properties(
            _STORAGE_CONTAINERS[container], file[0])
        if (prop.properties.content_settings.content_md5 ==
                util.compute_md5_for_file(file[1], True)):
            logger.debug(
                'remote file is the same for {}, skipping'.format(
                    file[0]))
            upload = False
    except azure.common.AzureMissingResourceHttpError:
        pass
    if upload:
        logger.info('uploading file {} as {!r}'.format(file[1], file[0]))
        blob_client.create_blob_from_path(
            _STORAGE_CONTAINERS[container], file[0], str(file[1]))


def upload_resource_files(blob_client, config, files):
    # type: (azure.storage.blob.BlockBlobService, dict, List[tuple]) -> dict
    """Upload resource files to blob storage
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
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
    """Upload files to blob storage for monitoring
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param list files: files to upload
    :param str kind: kind, "remotefs" or "monitoring"
    :rtype: list
    :return: list of file urls
    """
    kind = 'blob_{}'.format(kind.lower())
    ret = []
    for file in files:
        _check_file_and_upload(blob_client, file, kind)
        ret.append('https://{}.blob.{}/{}/{}'.format(
            _STORAGEACCOUNT, _STORAGEACCOUNTEP,
            _STORAGE_CONTAINERS[kind], file[0]))
    return ret


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
        if key == 'table_registry':
            # TODO remove in future release: unused table
            logger.debug('deleting table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.delete_table(_STORAGE_CONTAINERS[key])
        elif key.startswith('blob_'):
            if (key != 'blob_remotefs' and key != 'blob_monitoring'):
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
        if not tables_only and key.startswith('blob_'):
            if (key != 'blob_remotefs' and key != 'blob_monitoring'):
                _clear_blobs(blob_client, _STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            # TODO remove in a future release: unused registry table
            if key == 'table_registry':
                continue
            if key == 'table_monitoring':
                continue
            try:
                _clear_table(
                    table_client, _STORAGE_CONTAINERS[key], config,
                    pool_id=pool_id)
            except azure.common.AzureMissingResourceHttpError:
                if key != 'table_perf' or bs.store_timing_metrics:
                    raise


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
            if key == 'blob_remotefs' or key == 'blob_monitoring':
                continue
            logger.info('creating container: {}'.format(
                _STORAGE_CONTAINERS[key]))
            blob_client.create_container(_STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            # TODO remove in a future release: unused registry table
            if key == 'table_registry':
                continue
            if key == 'table_monitoring':
                continue
            if key == 'table_perf' and not bs.store_timing_metrics:
                continue
            logger.info('creating table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.create_table(_STORAGE_CONTAINERS[key])


def create_storage_containers_nonbatch(blob_client, table_client, kind):
    # type: (azureblob.BlockBlobService, str) -> None
    """Create storage containers used for monitoring
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param str kind: kind, "remotefs" or "monitoring"
    """
    key = 'blob_{}'.format(kind.lower())
    contname = _STORAGE_CONTAINERS[key]
    logger.info('creating container: {}'.format(contname))
    blob_client.create_container(contname)
    try:
        key = 'table_{}'.format(kind.lower())
        contname = _STORAGE_CONTAINERS[key]
    except KeyError:
        pass
    else:
        logger.info('creating table: {}'.format(contname))
        table_client.create_table(contname)


def delete_storage_containers_nonbatch(blob_client, table_client, kind):
    # type: (azureblob.BlockBlobService, str) -> None
    """Delete storage containers used for monitoring
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.cosmosdb.table.TableService table_client: table client
    :param str kind: kind, "remotefs" or "monitoring"
    """
    key = 'blob_{}'.format(kind.lower())
    contname = _STORAGE_CONTAINERS[key]
    logger.info('deleting container: {}'.format(contname))
    try:
        blob_client.delete_container(contname)
    except azure.common.AzureMissingResourceHttpError:
        logger.warning('container not found: {}'.format(contname))
    try:
        key = 'table_{}'.format(kind.lower())
        contname = _STORAGE_CONTAINERS[key]
    except KeyError:
        pass
    else:
        logger.debug('deleting table: {}'.format(contname))
        table_client.delete_table(contname)


def delete_storage_containers_boot_diagnostics(
        blob_client, vm_name, vm_id):
    # type: (azureblob.BlockBlobService, str, str) -> None
    """Delete storage containers used for remotefs bootdiagnostics
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str vm_name: vm name
    :param str vm_id: vm id
    """
    name = re.sub('[\W_]+', '', vm_name)
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
