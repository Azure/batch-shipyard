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
    bytes, dict, int, list, object, range, ascii, chr, hex, input,
    next, oct, open, pow, round, super, filter, map, zip)
# stdlib imports
import logging
# non-stdlib imports
import azure.batch.batch_auth as batchauth
import azure.batch.batch_service_client as batchsc
import azure.keyvault
import azure.mgmt.batch
import azure.mgmt.compute
import azure.mgmt.network
import azure.mgmt.resource
import azure.storage.blob as azureblob
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable
# local imports
from . import aad
from . import settings
from . import storage
from . import util
from .version import __version__

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)


def _create_resource_client(ctx, credentials=None, subscription_id=None):
    # type: (CliContext, object, str) ->
    #        azure.mgmt.resource.resources.ResourceManagementClient
    """Create resource management client
    :param CliContext ctx: Cli Context
    :param object credentials: credentials object
    :param str subscription_id: subscription id
    :rtype: azure.mgmt.resource.resources.ResourceManagementClient
    :return: resource management client
    """
    mgmt_aad = None
    if credentials is None:
        mgmt_aad = settings.credentials_management(ctx.config).aad
        credentials = aad.create_aad_credentials(ctx, mgmt_aad)
    if util.is_none_or_empty(subscription_id):
        if mgmt_aad is None:
            mgmt_aad = settings.credentials_management(ctx.config).aad
        subscription_id = ctx.subscription_id or mgmt_aad.subscription_id
    return azure.mgmt.resource.resources.ResourceManagementClient(
        credentials, subscription_id)


def _create_compute_client(ctx, credentials=None, subscription_id=None):
    # type: (CliContext, object, str) ->
    #        azure.mgmt.compute.ComputeManagementClient
    """Create compute management client
    :param CliContext ctx: Cli Context
    :param object credentials: credentials object
    :param str subscription_id: subscription id
    :rtype: azure.mgmt.compute.ComputeManagementClient
    :return: compute management client
    """
    mgmt_aad = None
    if credentials is None:
        mgmt_aad = settings.credentials_management(ctx.config).aad
        credentials = aad.create_aad_credentials(ctx, mgmt_aad)
    if util.is_none_or_empty(subscription_id):
        if mgmt_aad is None:
            mgmt_aad = settings.credentials_management(ctx.config).aad
        subscription_id = ctx.subscription_id or mgmt_aad.subscription_id
    return azure.mgmt.compute.ComputeManagementClient(
        credentials, subscription_id)


def _create_network_client(ctx, credentials=None, subscription_id=None):
    # type: (CliContext, object, str) ->
    #        azure.mgmt.network.NetworkManagementClient
    """Create network management client
    :param CliContext ctx: Cli Context
    :rtype: azure.mgmt.network.NetworkManagementClient
    :return: network management client
    """
    mgmt_aad = None
    if credentials is None:
        mgmt_aad = settings.credentials_management(ctx.config).aad
        credentials = aad.create_aad_credentials(ctx, mgmt_aad)
    if util.is_none_or_empty(subscription_id):
        if mgmt_aad is None:
            mgmt_aad = settings.credentials_management(ctx.config).aad
        subscription_id = ctx.subscription_id or mgmt_aad.subscription_id
    return azure.mgmt.network.NetworkManagementClient(
        credentials, subscription_id)


def _create_batch_mgmt_client(ctx, credentials=None, subscription_id=None):
    # type: (CliContext, object, str) ->
    #        azure.mgmt.batch.BatchManagementClient
    """Create batch management client
    :param CliContext ctx: Cli Context
    :param object credentials: credentials object
    :param str subscription_id: subscription id
    :rtype: azure.mgmt.batch.BatchManagementClient
    :return: batch management client
    """
    mgmt_aad = None
    if credentials is None:
        mgmt_aad = settings.credentials_management(ctx.config).aad
        credentials = aad.create_aad_credentials(ctx, mgmt_aad)
    if util.is_none_or_empty(subscription_id):
        if mgmt_aad is None:
            mgmt_aad = settings.credentials_management(ctx.config).aad
        subscription_id = ctx.subscription_id or mgmt_aad.subscription_id
    batch_mgmt_client = azure.mgmt.batch.BatchManagementClient(
        credentials, subscription_id)
    batch_mgmt_client.config.add_user_agent(
        'batch-shipyard/{}'.format(__version__))
    return batch_mgmt_client


def create_arm_clients(ctx, batch_clients=False):
    # type: (CliContext, bool) ->
    #        Tuple[azure.mgmt.resource.resources.ResourceManagementClient,
    #              azure.mgmt.compute.ComputeManagementClient,
    #              azure.mgmt.network.NetworkManagementClient,
    #              azure.mgmt.batch.BatchManagementClient,
    #              azure.batch.batch_service_client.BatchServiceClient]
    """Create resource, compute and network clients
    :param CliContext ctx: Cli Context
    :param bool batch_clients: create batch clients
    :rtype: tuple
    :return: (
        azure.mgmt.resource.resources.ResourceManagementClient,
        azure.mgmt.compute.ComputeManagementClient,
        azure.mgmt.network.NetworkManagementClient,
        azure.mgmt.batch.BatchManagementClient,
        azure.batch.batch_service_client.BatchServiceClient)
    """
    mgmt = settings.credentials_management(ctx.config)
    subscription_id = ctx.subscription_id or mgmt.subscription_id
    if util.is_none_or_empty(subscription_id):
        credentials = None
        resource_client = None
        compute_client = None
        network_client = None
    else:
        # subscription_id must be of type 'str' due to python management
        # library type checking, but can be read as 'unicode' from json
        subscription_id = str(subscription_id)
        # create add credential object
        credentials = aad.create_aad_credentials(ctx, mgmt.aad)
        # create clients
        resource_client = _create_resource_client(
            ctx, credentials=credentials, subscription_id=subscription_id)
        compute_client = _create_compute_client(
            ctx, credentials=credentials, subscription_id=subscription_id)
        network_client = _create_network_client(
            ctx, credentials=credentials, subscription_id=subscription_id)
    if batch_clients:
        try:
            if credentials is None:
                credentials = aad.create_aad_credentials(ctx, mgmt.aad)
            batch_mgmt_client = _create_batch_mgmt_client(
                ctx, credentials=credentials, subscription_id=subscription_id)
        except Exception:
            if settings.verbose(ctx.config):
                logger.warning('could not create batch management client')
            batch_mgmt_client = None
        # create batch service client
        batch_client = _create_batch_service_client(ctx)
    else:
        batch_mgmt_client = None
        batch_client = None
    return (
        resource_client, compute_client, network_client, batch_mgmt_client,
        batch_client
    )


def create_keyvault_client(ctx):
    # type: (CliContext) -> azure.keyvault.KeyVaultClient
    """Create KeyVault client
    :param CliContext ctx: Cli Context
    :rtype: azure.keyvault.KeyVaultClient
    :return: keyvault client
    """
    kv = settings.credentials_keyvault(ctx.config)
    if util.is_none_or_empty(ctx.keyvault_uri or kv.keyvault_uri):
        return None
    return azure.keyvault.KeyVaultClient(
        aad.create_aad_credentials(ctx, kv.aad)
    )


def _create_batch_service_client(ctx):
    # type: (CliContext) -> azure.batch.batch_service_client.BatchServiceClient
    """Create batch service client
    :param CliContext ctx: Cli Context
    :rtype: azure.batch.batch_service_client.BatchServiceClient
    :return: batch service client
    """
    bc = settings.credentials_batch(ctx.config)
    if util.is_none_or_empty(bc.account_key):
        logger.debug('batch account key not specified, using aad auth')
        batch_aad = settings.credentials_batch(ctx.config).aad
        credentials = aad.create_aad_credentials(ctx, batch_aad)
    else:
        credentials = batchauth.SharedKeyCredentials(
            bc.account, bc.account_key)
    batch_client = batchsc.BatchServiceClient(
        credentials, base_url=bc.account_service_url)
    batch_client.config.add_user_agent('batch-shipyard/{}'.format(__version__))
    return batch_client


def create_storage_clients():
    # type: (None) -> tuple
    """Create storage clients
    :rtype: tuple
    :return: blob_client, queue_client, table_client
    """
    account_name = storage.get_storageaccount()
    account_key = storage.get_storageaccount_key()
    endpoint_suffix = storage.get_storageaccount_endpoint()
    blob_client = azureblob.BlockBlobService(
        account_name=account_name,
        account_key=account_key,
        endpoint_suffix=endpoint_suffix,
    )
    queue_client = azurequeue.QueueService(
        account_name=account_name,
        account_key=account_key,
        endpoint_suffix=endpoint_suffix,
    )
    table_client = azuretable.TableService(
        account_name=account_name,
        account_key=account_key,
        endpoint_suffix=endpoint_suffix,
    )
    return blob_client, queue_client, table_client
