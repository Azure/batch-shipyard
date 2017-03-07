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
import json
import logging
import zlib
# non-stdlib imports
import azure.common.credentials
import azure.keyvault
# local imports
from . import aad
from . import settings
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_SECRET_ENCODED_FORMAT_KEY = 'format'
_SECRET_ENCODED_FORMAT_VALUE = 'zlib+base64'


def create_client(ctx, kv_aad):
    # type: (CliContext, settings.AADSettings) ->
    #       azure.keyvault.KeyVaultClient
    """Create KeyVault client
    :param CliContext ctx: Cli Context
    :param settings.AADSettings kv_aad: AAD settings
    :rtype: azure.keyvault.KeyVaultClient
    :return: keyvault client
    """
    return azure.keyvault.KeyVaultClient(
        aad.create_aad_credentials(ctx, kv_aad)
    )


def fetch_credentials_json(
        client, keyvault_uri, keyvault_credentials_secret_id):
    # type: (azure.keyvault.KeyVaultClient, str, str) -> dict
    """Fetch credentials json from KeyVault
    :param azure.keyvault.KeyVaultClient client: keyvault client
    :param str keyvault_uri: keyvault uri
    :param str keyvault_credentials_secret_id: secret id for creds json
    :rtype: dict
    :return: credentials dict
    """
    if client is None:
        raise RuntimeError(
            'KeyVault client not initialized, please ensure proper AAD '
            'credentials and KeyVault parameters have been provided')
    logger.debug('fetching credentials json from keyvault')
    if util.is_none_or_empty(keyvault_credentials_secret_id):
        raise RuntimeError(
            'cannot fetch credentials json from keyvault without a valid '
            'keyvault credentials secret id')
    cred = client.get_secret(keyvault_credentials_secret_id)
    if util.is_none_or_empty(cred.value):
        raise ValueError(
            'credential json from secret id {} is invalid'.format(
                keyvault_credentials_secret_id))
    # check for encoding and decode/decompress if necessary
    if cred.tags is not None:
        try:
            if (cred.tags[_SECRET_ENCODED_FORMAT_KEY] ==
                    _SECRET_ENCODED_FORMAT_VALUE):
                cred.value = util.decode_string(
                    zlib.decompress(util.base64_decode_string(cred.value)))
            else:
                raise RuntimeError(
                    '{} encoding format is invalid'.format(
                        cred.tags[_SECRET_ENCODED_FORMAT_KEY]))
        except KeyError:
            pass
    return json.loads(cred.value)


def store_credentials_json(client, config, keyvault_uri, secret_name):
    # type: (azure.keyvault.KeyVaultClient, dict, str, str) -> None
    """Store credentials json in KeyVault
    :param azure.keyvault.KeyVaultClient client: keyvault client
    :param dict config: configuration dict
    :param str keyvault_uri: keyvault uri
    :param str secret_name: secret name for creds json
    """
    if client is None:
        raise RuntimeError(
            'KeyVault client not initialized, please ensure proper AAD '
            'credentials and KeyVault parameters have been provided')
    creds = {
        'credentials': settings.raw_credentials(config, True)
    }
    creds = json.dumps(creds).encode('utf8')
    # first zlib compress and encode as base64
    encoded = util.base64_encode_string(zlib.compress(creds))
    # store secret
    logger.debug('storing secret in keyvault {} with name {}'.format(
        keyvault_uri, secret_name))
    bundle = client.set_secret(
        keyvault_uri, secret_name, encoded,
        tags={_SECRET_ENCODED_FORMAT_KEY: _SECRET_ENCODED_FORMAT_VALUE}
    )
    logger.info('keyvault secret id for name {}: {}'.format(
        secret_name,
        azure.keyvault.key_vault_id.parse_secret_id(bundle.id).base_id))


def delete_secret(client, keyvault_uri, secret_name):
    # type: (azure.keyvault.KeyVaultClient, str, str) -> None
    """Delete secret from KeyVault
    :param azure.keyvault.KeyVaultClient client: keyvault client
    :param str keyvault_uri: keyvault uri
    :param str secret_name: secret name for creds json
    """
    if client is None:
        raise RuntimeError(
            'KeyVault client not initialized, please ensure proper AAD '
            'credentials and KeyVault parameters have been provided')
    logger.info('deleting secret in keyvault {} with name {}'.format(
        keyvault_uri, secret_name))
    client.delete_secret(keyvault_uri, secret_name)


def list_secrets(client, keyvault_uri):
    # type: (azure.keyvault.KeyVaultClient, str) -> None
    """List all secret ids and metadata from KeyVault
    :param azure.keyvault.KeyVaultClient client: keyvault client
    :param str keyvault_uri: keyvault uri
    """
    if client is None:
        raise RuntimeError(
            'KeyVault client not initialized, please ensure proper AAD '
            'credentials and KeyVault parameters have been provided')
    logger.debug('listing secret ids in keyvault {}'.format(keyvault_uri))
    secrets = client.get_secrets(keyvault_uri)
    for secret in secrets:
        logger.info('id={} enabled={} tags={} content_type={}'.format(
            secret.id, secret.attributes.enabled, secret.tags,
            secret.content_type))


def get_secret(client, secret_id, value_is_json=False):
    # type: (azure.keyvault.KeyVaultClient, str, bool) -> str
    """Get secret from KeyVault
    :param azure.keyvault.KeyVaultClient client: keyvault client
    :param str secret_id: secret id to retrieve
    :param bool value_is_json: expected value is json
    :rtype: str
    :return: secret value
    """
    if client is None:
        raise RuntimeError(
            'cannot retrieve secret {} with invalid KeyVault client'.format(
                secret_id))
    value = client.get_secret(secret_id).value
    if value_is_json and util.is_not_empty(value):
        return json.loads(value)
    else:
        return value


def parse_secret_ids(client, config):
    # type: (azure.keyvault.KeyVaultClient, dict) -> None
    """Parse secret ids in credentials, fetch values from KeyVault, and add
    appropriate values to config
    :param azure.keyvault.KeyVaultClient client: keyvault client
    :param dict config: configuration dict
    """
    # batch account key
    secid = settings.credentials_batch_account_key_secret_id(config)
    if secid is not None:
        logger.debug('fetching batch account key from keyvault')
        bakey = get_secret(client, secid)
        if util.is_none_or_empty(bakey):
            raise ValueError(
                'batch account key retrieved for secret id {} is '
                'invalid'.format(secid))
        settings.set_credentials_batch_account_key(config, bakey)
    # storage account keys
    for ssel in settings.iterate_storage_credentials(config):
        secid = settings.credentials_storage_account_key_secret_id(
            config, ssel)
        if secid is None:
            continue
        logger.debug(
            'fetching storage account key for link {} from keyvault'.format(
                ssel))
        sakey = get_secret(client, secid)
        if util.is_none_or_empty(sakey):
            raise ValueError(
                'storage account key retrieved for secret id {} is '
                'invalid'.format(secid))
        settings.set_credentials_storage_account_key(config, ssel, sakey)
    # docker registry passwords
    for reg in settings.iterate_docker_registry_servers(config):
        secid = settings.credentials_docker_registry_password_secret_id(
            config, reg)
        if secid is None:
            continue
        logger.debug(
            ('fetching docker registry password for registry {} '
             'from keyvault').format(reg))
        password = get_secret(client, secid)
        if util.is_none_or_empty(password):
            raise ValueError(
                'docker registry password retrieved for secret id {} is '
                'invalid'.format(secid))
        settings.set_credentials_docker_registry_password(
            config, reg, password)
