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
import logging
# non-stdlib imports
import azure.common
import azure.storage.table as azuretable
# local imports
import convoy.util

# create logger
logger = logging.getLogger(__name__)
convoy.util.setup_logger(logger)


def delete_storage_containers(
        blob_client, queue_client, table_client, config, sc):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict, dict) -> None
    """Delete storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param dict sc: storage containers
    """
    for key in sc:
        if key.startswith('blob_'):
            blob_client.delete_container(sc[key])
        elif key.startswith('table_'):
            table_client.delete_table(sc[key])
        elif key.startswith('queue_'):
            queue_client.delete_queue(sc[key])


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


def clear_storage_containers(
        blob_client, queue_client, table_client, config, sc):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict, dict) -> None
    """Clear storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param dict sc: storage containers
    """
    try:
        perf = config['batch_shipyard']['store_timing_metrics']
    except KeyError:
        perf = False
    for key in sc:
        if key.startswith('blob_'):
            # TODO this is temp to preserve registry upload
            if key != 'blob_resourcefiles':
                _clear_blobs(blob_client, sc[key])
            else:
                _clear_blob_task_resourcefiles(blob_client, sc[key], config)
        elif key.startswith('table_'):
            try:
                _clear_table(table_client, sc[key], config)
            except azure.common.AzureMissingResourceHttpError:
                if key != 'table_perf' or perf:
                    raise
        elif key.startswith('queue_'):
            logger.info('clearing queue: {}'.format(sc[key]))
            queue_client.clear_messages(sc[key])


def create_storage_containers(
        blob_client, queue_client, table_client, config, sc):
    # type: (azureblob.BlockBlobService, azurequeue.QueueService,
    #        azuretable.TableService, dict) -> None
    """Create storage containers
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param dict config: configuration dict
    :param dict sc: storage containers
    """
    try:
        perf = config['batch_shipyard']['store_timing_metrics']
    except KeyError:
        perf = False
    for key in sc:
        if key.startswith('blob_'):
            logger.info('creating container: {}'.format(sc[key]))
            blob_client.create_container(sc[key])
        elif key.startswith('table_'):
            if key == 'table_perf' and not perf:
                continue
            logger.info('creating table: {}'.format(sc[key]))
            table_client.create_table(sc[key])
        elif key.startswith('queue_'):
            logger.info('creating queue: {}'.format(sc[key]))
            queue_client.create_queue(sc[key])
