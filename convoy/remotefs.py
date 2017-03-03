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
import dateutil.parser
import json
import logging
import os
# non-stdlib imports
import adal
import azure.common.credentials
import azure.mgmt.compute
import azure.mgmt.compute.models
import azure.mgmt.network
import azure.mgmt.resource
import msrest.authentication
# local imports
from . import settings
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_CLIENT_ID = '04b07795-8ddb-461a-bbee-02f9e1bf7b46'  # xplat-cli


class DeviceCodeAuthentication(msrest.authentication.Authentication):
    def __init__(self, context, resource, client_id, token_cache_file):
        self._context = context
        self._resource = resource
        self._client_id = client_id
        self._token_cache_file = token_cache_file
        self._token = None

    @property
    def token(self):
        return self._token

    @token.setter
    def token(self, value):
        self._token = value

    def signed_session(self):
        """Get a signed session for requests.
        Usually called by the Azure SDKs for you to authenticate queries.
        :rtype: requests.Session
        """
        session = super(DeviceCodeAuthentication, self).signed_session()
        # try to get cached token
        if self._token is None:
            try:
                with open(self._token_cache_file, 'r') as fd:
                    self._token = json.load(fd)
            except OSError:
                pass
            except Exception:
                logger.error(
                    'Error attempting read of token cache: {}'.format(
                        self._token_cache_file))
        # get token
        try:
            if self._token is None:
                # get token through selected method
                code = self._context.acquire_user_code(
                    resource=self._resource,
                    client_id=self._client_id,
                )
                logger.info(
                    'Please follow the instructions below. The requesting '
                    'application will be: Microsoft Azure Cross-platform '
                    'Command Line Interface')
                logger.info(code['message'])
                self._token = self._context.acquire_token_with_device_code(
                    resource=self._resource,
                    user_code_info=code,
                    client_id=self._client_id,
                )
            else:
                # check for expiry time
                expiry = dateutil.parser.parse(self._token['expiresOn'])
                if (datetime.datetime.now() +
                        datetime.timedelta(minutes=5) >= expiry):
                    # attempt token refresh
                    logger.debug('Refreshing token expiring on: {}'.format(
                        expiry))
                    self._token = self._context.\
                        acquire_token_with_refresh_token(
                            refresh_token=self._token['refreshToken'],
                            client_id=self._client_id,
                            resource=self._resource,
                        )
            # set session authorization header
            session.headers['Authorization'] = '{} {}'.format(
                self._token['tokenType'], self._token['accessToken'])
            # cache token
            logger.debug('storing token to local cache: {}'.format(
                self._token_cache_file))
            with open(self._token_cache_file, 'w') as fd:
                json.dump(self._token, fd, indent=4, sort_keys=False)
        except adal.AdalError as err:
            if (hasattr(err, 'error_response') and
                    'error_description' in err.error_response and
                    'AADSTS70008:' in err.error_response['error_description']):
                logger.error('Credentials have expired due to inactivity.')
            try:
                logger.debug('invalidating local token cache: {}'.format(
                    self._token_cache_file))
                os.unlink(self._token_cache_file)
            except OSError:
                pass
            raise
        return session


def _create_aad_credentials(
        aad_directory_id, aad_user, aad_password, endpoint, token_cache_file):
    # type: (str, str, str, str,
    #        str) -> azure.common.credentials.UserPassCredentials
    """Create Azure Active Directory credentials
    :param str aad_directory_id: aad directory/tenant id
    :param str aad_user: aad user
    :param str aad_password: aad password
    :param str endpoint: management endpoint
    :param str token_cache_file: token cache file
    :rtype: azure.common.credentials.UserPassCredentials
    :return: aad credentials object
    """
    if util.is_not_empty(aad_password):
        try:
            return azure.common.credentials.UserPassCredentials(
                username=aad_user,
                password=aad_password,
                resource=endpoint,
            )
        except msrest.exceptions.AuthenticationError as e:
            if 'AADSTS50079' in e.args[0]:
                raise RuntimeError('{} {}'.format(
                    e.args[0][2:],
                    'Do not pass an AAD password to shipyard and try again.'))
    else:
        return DeviceCodeAuthentication(
            context=adal.AuthenticationContext(
                'https://login.microsoftonline.com/{}'.format(aad_directory_id)
            ),
            resource=endpoint,
            client_id=_CLIENT_ID,
            token_cache_file=token_cache_file,
        )


def create_clients(
        subscription_id, aad_directory_id, aad_user, aad_password, endpoint,
        token_cache_file):
    # type: (str, str, str, str, str, str) ->
    #        Tuple[azure.mgmt.resource.resources.ResourceManagementClient,
    #              azure.mgmt.compute.ComputeManagementClient,
    #              azure.mgmt.network.NetworkManagementClient]
    """Create compute and network clients
    :param str subscription_id: subscription id
    :param str aad_directory_id: aad directory/tenant id
    :param str aad_user: aad user
    :param str aad_password: aad_password
    :param str endpoint: management endpoint
    :param str token_cache_file: token cache file
    :rtype: tuple
    :return: (
        azure.mgmt.resource.resources.ResourceManagementClient,
        azure.mgmt.compute.ComputeManagementClient,
        azure.mgmt.network.NetworkManagementClient)
    """
    credentials = _create_aad_credentials(
        aad_directory_id, aad_user, aad_password, endpoint, token_cache_file)
    resource_client = azure.mgmt.resource.resources.ResourceManagementClient(
        credentials, subscription_id)
    compute_client = azure.mgmt.compute.ComputeManagementClient(
        credentials, subscription_id)
    network_client = azure.mgmt.network.NetworkManagementClient(
        credentials, subscription_id)
    return (resource_client, compute_client, network_client)


def create_disks(resource_client, compute_client, config):
    # type: (azure.mgmt.resource.resources.ResourceManagementClient,
    #        azure.mgmt.compute.ComputeManagementClient, dict) -> None
    """Create managed disks
    :param azure.mgmt.resource.resources.ResourceManagementClient
        resource_client: resource client
    :param azure.mgmt.compute.ComputeManagementClient compute_client:
        compute client
    :param dict config: configuration dict
    """
    # TODO
    # retrieve remotefs settings
    # check if resource group exists
    # create resource group if it doesn't exist
    # create managed disks
    pass


def create_storage_cluster(
        resource_client, compute_client, network_client, config):
    raise NotImplementedError()
