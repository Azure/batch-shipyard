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
from __future__ import division, print_function, unicode_literals
import datetime
import hashlib
import logging
try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib
# non-stdlib imports
import azure.common
import azure.storage.blob as azureblob
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable
# local imports
import convoy.util

# create logger
logger = logging.getLogger(__name__)
convoy.util.setup_logger(logger)
# global defines
_REGISTRY_FILE = None
_STORAGEACCOUNT = None
_STORAGEACCOUNTKEY = None
_STORAGEACCOUNTEP = None
_STORAGE_CONTAINERS = {
    'blob_resourcefiles': None,
    'blob_torrents': None,
    'table_dht': None,
    'table_registry': None,
    'table_torrentinfo': None,
    'table_images': None,
    'table_globalresources': None,
    'table_perf': None,
    'queue_globalresources': None,
}


def set_storage_configuration(sep, postfix, sa, sakey, saep):
    # type: (str, str, str, str, str) -> None
    """Set storage configuration
    :param str sep: storage entity prefix
    :param str postfix: storage entity postfix
    :param str sa: storage account
    :param str sakey: storage account key
    :param str saep: storage account endpoint
    """
    global _STORAGEACCOUNT, _STORAGEACCOUNTKEY, _STORAGEACCOUNTEP
    _STORAGE_CONTAINERS['blob_resourcefiles'] = '-'.join(
        (sep + 'resourcefiles', postfix))
    _STORAGE_CONTAINERS['blob_torrents'] = '-'.join(
        (sep + 'torrents', postfix))
    _STORAGE_CONTAINERS['table_dht'] = sep + 'dht'
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    _STORAGE_CONTAINERS['table_images'] = sep + 'images'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'globalresources'
    _STORAGE_CONTAINERS['table_perf'] = sep + 'perf'
    _STORAGE_CONTAINERS['queue_globalresources'] = '-'.join(
        (sep + 'globalresources', postfix))
    _STORAGEACCOUNT = sa
    _STORAGEACCOUNTKEY = sakey
    _STORAGEACCOUNTEP = saep


def set_registry_file(rf):
    # type: (tuple) -> None
    """Set registry file
    :param tuple rf: registry file
    """
    global _REGISTRY_FILE
    _REGISTRY_FILE = rf


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


def get_registry_file():
    # type: (None) -> str
    """Get registry file
    :rtype: tuple
    :return: registry file
    """
    return _REGISTRY_FILE


def create_clients():
    # type: (None) -> tuple
    """Create storage clients
    :rtype: tuple
    :return: blob_client, queue_client, table_client
    """
    blob_client = azureblob.BlockBlobService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=_STORAGEACCOUNTEP)
    queue_client = azurequeue.QueueService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=_STORAGEACCOUNTEP)
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=_STORAGEACCOUNTEP)
    return blob_client, queue_client, table_client


def _add_global_resource(
        queue_client, table_client, config, pk, p2pcsd, grtype):
    # type: (azurequeue.QueueService, azuretable.TableService, dict, str,
    #        bool, str) -> None
    """Add global resources
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param str pk: partition key
    :param int p2pcsd: peer-to-peer concurrent source downloads
    :param str grtype: global resources type
    """
    try:
        for gr in config['global_resources'][grtype]:
            if grtype == 'docker_images':
                prefix = 'docker'
            else:
                raise NotImplementedError()
            resource = '{}:{}'.format(prefix, gr)
            logger.info('adding global resource: {}'.format(resource))
            table_client.insert_or_replace_entity(
                _STORAGE_CONTAINERS['table_globalresources'],
                {
                    'PartitionKey': pk,
                    'RowKey': hashlib.sha1(
                        resource.encode('utf8')).hexdigest(),
                    'Resource': resource,
                }
            )
            for _ in range(0, p2pcsd):
                queue_client.put_message(
                    _STORAGE_CONTAINERS['queue_globalresources'], resource)
    except KeyError:
        pass


def populate_queues(queue_client, table_client, config):
    # type: (azurequeue.QueueService, azuretable.TableService, dict) -> None
    """Populate queues
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    try:
        preg = config['docker_registry']['private']['enabled']
    except KeyError:
        preg = False
    pk = '{}${}'.format(
        config['credentials']['batch']['account'],
        config['pool_specification']['id'])
    # if using docker public hub, then populate registry table with hub
    if not preg:
        table_client.insert_or_replace_entity(
            _STORAGE_CONTAINERS['table_registry'],
            {
                'PartitionKey': pk,
                'RowKey': 'registry.hub.docker.com',
                'Port': 80,
            }
        )
    # get p2pcsd setting
    try:
        p2p = config['data_replication']['peer_to_peer']['enabled']
    except KeyError:
        p2p = False
    if p2p:
        try:
            p2pcsd = config['data_replication']['peer_to_peer'][
                'concurrent_source_downloads']
            if p2pcsd is None or p2pcsd < 1:
                raise KeyError()
        except KeyError:
            p2pcsd = config['pool_specification']['vm_count'] // 6
            if p2pcsd < 1:
                p2pcsd = 1
    else:
        p2pcsd = 1
    # add global resources
    _add_global_resource(
        queue_client, table_client, config, pk, p2pcsd, 'docker_images')


def upload_resource_files(blob_client, config, files):
    # type: (azure.storage.blob.BlockBlobService, dict, List[tuple], tuple,
    #        str, str) -> dict
    """Upload resource files to blob storage
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :param list files: files to upload
    :rtype: dict
    :return: sas url dict
    """
    sas_urls = {}
    for file in files:
        # skip if no file is specified
        if file[0] is None:
            continue
        upload = True
        fp = pathlib.Path(file[1])
        if (_REGISTRY_FILE is not None and fp.name == _REGISTRY_FILE[0] and
                not fp.exists()):
            logger.debug('skipping optional docker registry image: {}'.format(
                _REGISTRY_FILE[0]))
            continue
        else:
            # check if blob exists
            try:
                prop = blob_client.get_blob_properties(
                    _STORAGE_CONTAINERS['blob_resourcefiles'], file[0])
                if (prop.properties.content_settings.content_md5 ==
                        convoy.util.compute_md5_for_file(fp, True)):
                    logger.debug(
                        'remote file is the same for {}, skipping'.format(
                            file[0]))
                    upload = False
            except azure.common.AzureMissingResourceHttpError:
                pass
        if upload:
            logger.info('uploading file: {}'.format(file[1]))
            blob_client.create_blob_from_path(
                _STORAGE_CONTAINERS['blob_resourcefiles'], file[0], file[1])
        sas_urls[file[0]] = 'https://{}.blob.{}/{}/{}?{}'.format(
            _STORAGEACCOUNT, _STORAGEACCOUNTEP,
            _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
            blob_client.generate_blob_shared_access_signature(
                _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
                permission=azureblob.BlobPermissions.READ,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=3)
            )
        )
    return sas_urls


def delete_storage_containers(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Delete storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            blob_client.delete_container(_STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            table_client.delete_table(_STORAGE_CONTAINERS[key])
        elif key.startswith('queue_'):
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
    envfileloc = '{}taskrf-'.format(
        config['batch_shipyard']['storage_entity_prefix'])
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
    logger.info('clearing table: {}'.format(table_name))
    ents = table_client.query_entities(
        table_name, filter='PartitionKey eq \'{}${}\''.format(
            config['credentials']['batch']['account'],
            config['pool_specification']['id'])
    )
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


def clear_storage_containers(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Clear storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    try:
        perf = config['batch_shipyard']['store_timing_metrics']
    except KeyError:
        perf = False
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            # TODO this is temp to preserve registry upload
            if key != 'blob_resourcefiles':
                _clear_blobs(blob_client, _STORAGE_CONTAINERS[key])
            else:
                _clear_blob_task_resourcefiles(
                    blob_client, _STORAGE_CONTAINERS[key], config)
        elif key.startswith('table_'):
            try:
                _clear_table(table_client, _STORAGE_CONTAINERS[key], config)
            except azure.common.AzureMissingResourceHttpError:
                if key != 'table_perf' or perf:
                    raise
        elif key.startswith('queue_'):
            logger.info('clearing queue: {}'.format(_STORAGE_CONTAINERS[key]))
            queue_client.clear_messages(_STORAGE_CONTAINERS[key])


def create_storage_containers(blob_client, queue_client, table_client, config):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Create storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    """
    try:
        perf = config['batch_shipyard']['store_timing_metrics']
    except KeyError:
        perf = False
    for key in _STORAGE_CONTAINERS:
        if key.startswith('blob_'):
            logger.info('creating container: {}'.format(
                _STORAGE_CONTAINERS[key]))
            blob_client.create_container(_STORAGE_CONTAINERS[key])
        elif key.startswith('table_'):
            if key == 'table_perf' and not perf:
                continue
            logger.info('creating table: {}'.format(_STORAGE_CONTAINERS[key]))
            table_client.create_table(_STORAGE_CONTAINERS[key])
        elif key.startswith('queue_'):
            logger.info('creating queue: {}'.format(_STORAGE_CONTAINERS[key]))
            queue_client.create_queue(_STORAGE_CONTAINERS[key])
