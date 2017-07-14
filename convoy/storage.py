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
import logging
# non-stdlib imports
import azure.common
import azure.storage.blob as azureblob
import azure.storage.file as azurefile
import azure.storage.table as azuretable
# local imports
from . import settings
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_DOCKER_HUB_REGISTRY = 'docker.io'
_DEFAULT_SAS_EXPIRY_DAYS = 180
_DEFAULT_RF_SAS_EXPIRY_DAYS = 365 * 30
_STORAGEACCOUNT = None
_STORAGEACCOUNTKEY = None
_STORAGEACCOUNTEP = None
_STORAGE_CONTAINERS = {
    'blob_globalresources': None,
    'blob_resourcefiles': None,
    'blob_torrents': None,
    'blob_remotefs': None,
    'table_dht': None,
    'table_registry': None,
    'table_torrentinfo': None,
    'table_images': None,
    'table_globalresources': None,
    'table_perf': None,
    'queue_globalresources': None,  # TODO remove in 3.0
}


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
    _STORAGE_CONTAINERS['table_dht'] = sep + 'dht'
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    _STORAGE_CONTAINERS['table_images'] = sep + 'images'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'gr'
    _STORAGE_CONTAINERS['table_perf'] = sep + 'perf'
    # TODO remove in 3.0
    _STORAGE_CONTAINERS['queue_globalresources'] = '-'.join(
        (sep + 'gr', postfix))
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


def _construct_partition_key_from_config(config):
    # type: (dict) -> str
    """Construct partition key from config
    :param dict config: configuration dict
    :rtype: str
    :return: partition key
    """
    return '{}${}'.format(
        settings.credentials_batch(config).account, settings.pool_id(config))


def _add_global_resource(
        blob_client, table_client, config, pk, dr, grtype):
    # type: (azurequeue.QueueService, azuretable.TableService, dict, str,
    #        settings.DataReplicationSettings, str) -> None
    """Add global resources
    :param azure.storage.blob.BlockService blob_client: blob client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str pk: partition key
    :param settings.DataReplicationSettings dr: data replication settings
    :param str grtype: global resources type
    """
    try:
        if grtype == 'docker_images':
            prefix = 'docker'
            resources = settings.global_resources_docker_images(config)
        else:
            raise NotImplementedError(
                'global resource type: {}'.format(grtype))
        for gr in resources:
            resource = '{}:{}'.format(prefix, gr)
            resource_sha1 = hashlib.sha1(
                resource.encode('utf8')).hexdigest()
            logger.info('adding global resource: {} {}'.format(
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
    # type: (azureblob.BlockService, azuretable.TableService, dict) -> None
    """Populate global resource blobs
    :param azure.storage.blob.BlockService blob_client: blob client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    pk = _construct_partition_key_from_config(config)
    preg = settings.docker_registry_private_settings(config)
    # populate registry table now if not an azure storage backed registry
    if util.is_none_or_empty(preg.storage_account):
        if util.is_not_empty(preg.server):
            # populate registry table with private registry server
            rk = preg.server
            port = preg.port
        else:
            # populate registry table with public docker hub
            rk = _DOCKER_HUB_REGISTRY
            port = 80
        # add entity to table
        table_client.insert_or_replace_entity(
            _STORAGE_CONTAINERS['table_registry'],
            {
                'PartitionKey': pk,
                'RowKey': rk,
                'Port': port,
            }
        )
    # get p2pcsd setting
    dr = settings.data_replication_settings(config)
    # add global resources
    _add_global_resource(
        blob_client, table_client, config, pk, dr, 'docker_images')


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
                datetime.timedelta(days=_DEFAULT_RF_SAS_EXPIRY_DAYS)
            )
        )
    return sas_urls


def upload_for_remotefs(blob_client, files):
    # type: (azure.storage.blob.BlockBlobService, List[tuple]) -> List[str]
    """Upload files to blob storage for remote fs
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param list files: files to upload
    :rtype: list
    :return: list of file urls
    """
    ret = []
    for file in files:
        _check_file_and_upload(blob_client, file, 'blob_remotefs')
        ret.append('https://{}.blob.{}/{}/{}'.format(
            _STORAGEACCOUNT, _STORAGEACCOUNTEP,
            _STORAGE_CONTAINERS['blob_remotefs'], file[0]))
    return ret


def delete_storage_containers(
        blob_client, queue_client, table_client, config, skip_tables=False):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict, bool) -> None
    """Delete storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool skip_tables: skip deleting tables
    """
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            if key != 'blob_remotefs':
                logger.debug('deleting container: {}'.format(
                    _STORAGE_CONTAINERS[key]))
                blob_client.delete_container(_STORAGE_CONTAINERS[key])
        elif not skip_tables and key.startswith('table_'):
            logger.debug('deleting table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.delete_table(_STORAGE_CONTAINERS[key])
        elif key.startswith('queue_'):
            # TODO remove in 3.0
            logger.debug('deleting queue: {}'.format(_STORAGE_CONTAINERS[key]))
            queue_client.delete_queue(_STORAGE_CONTAINERS[key])


def _clear_blobs(blob_client, container):
    # type: (azureblob.BlockBlobService, str) -> None
    """Clear blobs in container
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param str container: container to clear blobs from
    """
    logger.info('deleting blobs: {}'.format(container))
    blobs = blob_client.list_blobs(container)
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
    blobs = blob_client.list_blobs(container, prefix=envfileloc)
    for blob in blobs:
        blob_client.delete_blob(container, blob.name)


def _clear_table(table_client, table_name, config):
    """Clear table entities
    :param azure.storage.table.TableService table_client: table client
    :param str table_name: table name
    :param dict config: configuration dict
    """
    # type: (azuretable.TableService, str, dict) -> None
    pk = _construct_partition_key_from_config(config)
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
        blob_client, table_client, config, tables_only=False):
    # type: (azureblob.BlockBlobService, azuretable.TableService, dict,
    #        bool) -> None
    """Clear storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param bool tables_only: clear only tables
    """
    bs = settings.batch_shipyard_settings(config)
    for key in _STORAGE_CONTAINERS:
        if not tables_only and key.startswith('blob_'):
            if key != 'blob_remotefs':
                _clear_blobs(blob_client, _STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            try:
                _clear_table(table_client, _STORAGE_CONTAINERS[key], config)
            except azure.common.AzureMissingResourceHttpError:
                if key != 'table_perf' or bs.store_timing_metrics:
                    raise


def create_storage_containers(blob_client, table_client, config):
    # type: (azureblob.BlockBlobService, azuretable.TableService, dict) -> None
    """Create storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    bs = settings.batch_shipyard_settings(config)
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            logger.info('creating container: {}'.format(
                _STORAGE_CONTAINERS[key]))
            blob_client.create_container(_STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            if key == 'table_perf' and not bs.store_timing_metrics:
                continue
            logger.info('creating table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.create_table(_STORAGE_CONTAINERS[key])


def create_storage_containers_remotefs(blob_client):
    # type: (azureblob.BlockBlobService) -> None
    """Create storage containers used for remotefs
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    """
    contname = _STORAGE_CONTAINERS['blob_remotefs']
    logger.info('creating container: {}'.format(contname))
    blob_client.create_container(contname)


def delete_storage_containers_remotefs(blob_client):
    # type: (azureblob.BlockBlobService) -> None
    """Delete storage containers used for remotefs
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    """
    contname = _STORAGE_CONTAINERS['blob_remotefs']
    logger.info('deleting container: {}'.format(contname))
    blob_client.delete_container(contname)


def cleanup_with_del_pool(
        blob_client, queue_client, table_client, config, pool_id=None):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict, str) -> None
    """Special cleanup routine in combination with delete pool
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
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
        blob_client, table_client, config, tables_only=True)
    delete_storage_containers(
        blob_client, queue_client, table_client, config, skip_tables=True)
