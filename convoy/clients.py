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


def create_resource_client(ctx, credentials=None, subscription_id=None):
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


def create_compute_client(ctx, credentials=None, subscription_id=None):
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


def create_network_client(ctx, credentials=None, subscription_id=None):
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
    mgmt_aad = settings.credentials_management(ctx.config).aad
    subscription_id = ctx.subscription_id or mgmt_aad.subscription_id
    if util.is_none_or_empty(subscription_id):
        return (None, None, None, None, None)
    credentials = aad.create_aad_credentials(ctx, mgmt_aad)
    resource_client = create_resource_client(
        ctx, credentials=credentials, subscription_id=subscription_id)
    compute_client = create_compute_client(
        ctx, credentials=credentials, subscription_id=subscription_id)
    network_client = create_network_client(
        ctx, credentials=credentials, subscription_id=subscription_id)
    if batch_clients:
        batch_mgmt_client, batch_client = create_batch_clients(ctx)
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
    kv_aad = settings.credentials_keyvault(ctx.config).aad
    return azure.keyvault.KeyVaultClient(
        aad.create_aad_credentials(ctx, kv_aad)
    )


def create_batch_mgmt_client(ctx, credentials=None, subscription_id=None):
    # type: (CliContext, object, str) ->
    #        azure.mgmt.batch.BatchManagementClient
    """Create batch management client
    :param CliContext ctx: Cli Context
    :param object credentials: credentials object
    :param str subscription_id: subscription id
    :rtype: azure.mgmt.batch.BatchManagementClient
    :return: batch management client
    """
    batch_aad = None
    if credentials is None:
        batch_aad = settings.credentials_batch(ctx.config).aad
        credentials = aad.create_aad_credentials(ctx, batch_aad)
    if util.is_none_or_empty(subscription_id):
        if batch_aad is None:
            batch_aad = settings.credentials_batch(ctx.config).aad
        subscription_id = ctx.subscription_id or batch_aad.subscription_id
        if util.is_none_or_empty(subscription_id):
            return None
    batch_mgmt_client = azure.mgmt.batch.BatchManagementClient(
        credentials, subscription_id)
    batch_mgmt_client.config.add_user_agent(
        'batch-shipyard/{}'.format(__version__))
    return batch_mgmt_client


def create_batch_clients(ctx):
    # type: (CliContext) ->
    #        Tuple[azure.mgmt.batch.BatchManagementClient,
    #              azure.batch.batch_service_client.BatchServiceClient]
    """Create batch client
    :param CliContext ctx: Cli Context
    :rtype: tuple
    :return: (
        azure.mgmt.batch.BatchManagementClient,
        azure.batch.batch_service_client.BatchServiceClient)
    """
    bc = settings.credentials_batch(ctx.config)
    use_aad = bc.user_subscription or util.is_none_or_empty(bc.account_key)
    batch_mgmt_client = None
    if use_aad:
        subscription_id = ctx.subscription_id or bc.subscription_id
        batch_aad = settings.credentials_batch(ctx.config).aad
        credentials = aad.create_aad_credentials(ctx, batch_aad)
        batch_mgmt_client = create_batch_mgmt_client(
            ctx, credentials=credentials, subscription_id=subscription_id)
    else:
        credentials = batchauth.SharedKeyCredentials(
            bc.account, bc.account_key)
    batch_client = batchsc.BatchServiceClient(
        credentials, base_url=bc.account_service_url)
    batch_client.config.add_user_agent('batch-shipyard/{}'.format(__version__))
    return (batch_mgmt_client, batch_client)


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
