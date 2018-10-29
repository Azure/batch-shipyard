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
import io
import json
import logging
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import os
# non-stdlib imports
import adal
import azure.common.credentials
import dateutil.parser
import msrest.authentication
import msrestazure.azure_exceptions
# local imports
from . import settings
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_LOGIN_AUTH_URI = 'https://login.microsoftonline.com'
_CLIENT_ID = '04b07795-8ddb-461a-bbee-02f9e1bf7b46'  # xplat-cli


class DeviceCodeAuthentication(msrest.authentication.Authentication):
    """Device Code Authentication session handler"""
    def __init__(self, context, resource, client_id, token_cache_file):
        """Ctor for DeviceCodeAuthentication
        :param DeviceCodeAuthentication self: this
        :param object context: context
        :param str resource: resource
        :param str client_id: client id
        :param str token_Cache_file: token cache file
        """
        self._context = context
        self._resource = resource
        self._client_id = client_id
        self._token_cache_file = token_cache_file
        self._token = None

    @property
    def token(self):
        """Retrieve signed token
        :param DeviceCodeAuthentication self: this
        """
        return self._token

    @token.setter
    def token(self, value):
        """Set signed token
        :param DeviceCodeAuthentication self: this
        :param str value: token value
        """
        self._token = value

    def signed_session(self):
        """Get a signed session for requests.
        Usually called by the Azure SDKs for you to authenticate queries.
        :param DeviceCodeAuthentication self: this
        :rtype: requests.Session
        :return: request session with signed header
        """
        session = super(DeviceCodeAuthentication, self).signed_session()
        # try to get cached token
        if self._token is None and util.is_not_empty(self._token_cache_file):
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
            cache_token = True
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
                else:
                    cache_token = False
            # set session authorization header
            session.headers['Authorization'] = '{} {}'.format(
                self._token['tokenType'], self._token['accessToken'])
            # cache token
            if cache_token and util.is_not_empty(self._token_cache_file):
                logger.debug('storing token to local cache: {}'.format(
                    self._token_cache_file))
                if util.on_python2():
                    with io.open(
                            self._token_cache_file,
                            'w', encoding='utf8') as fd:
                        fd.write(json.dumps(
                            self._token, indent=4, sort_keys=True,
                            ensure_ascii=False))
                else:
                    with open(
                            self._token_cache_file,
                            'w', encoding='utf8') as fd:
                        json.dump(
                            self._token, fd, indent=4, sort_keys=True,
                            ensure_ascii=False)
                if not util.on_windows():
                    os.chmod(self._token_cache_file, 0o600)
        except adal.AdalError as err:
            if (hasattr(err, 'error_response') and
                    'error_description' in err.error_response and
                    'AADSTS70008:' in err.error_response['error_description']):
                logger.error(
                    'Credentials have expired due to inactivity. Please '
                    'retry your command.')
            # clear token cache file due to expiration
            if util.is_not_empty(self._token_cache_file):
                try:
                    pathlib.Path(self._token_cache_file).unlink()
                    logger.debug('invalidated local token cache: {}'.format(
                        self._token_cache_file))
                except OSError:
                    pass
            raise
        return session


def create_aad_credentials(ctx, aad_settings):
    # type: (CliContext, settings.AADSettings) ->
    #       azure.common.credentials.ServicePrincipalCredentials or
    #       azure.common.credentials.UserPassCredentials
    """Create Azure Active Directory credentials
    :param CliContext ctx: Cli Context
    :param settings.AADSettings aad_settings: AAD settings
    :rtype: azure.common.credentials.ServicePrincipalCredentials or
        azure.common.credentials.UserPassCredentials
    :return: aad credentials object
    """
    # from aad parameters
    aad_directory_id = ctx.aad_directory_id or aad_settings.directory_id
    aad_application_id = ctx.aad_application_id or aad_settings.application_id
    aad_auth_key = ctx.aad_auth_key or aad_settings.auth_key
    aad_user = ctx.aad_user or aad_settings.user
    aad_password = ctx.aad_password or aad_settings.password
    aad_cert_private_key = (
        ctx.aad_cert_private_key or aad_settings.rsa_private_key_pem
    )
    aad_cert_thumbprint = (
        ctx.aad_cert_thumbprint or aad_settings.x509_cert_sha1_thumbprint
    )
    aad_authority_url = ctx.aad_authority_url or aad_settings.authority_url
    if util.is_not_empty(aad_authority_url):
        aad_authority_url = aad_authority_url.rstrip('/')
    else:
        aad_authority_url = _LOGIN_AUTH_URI
    endpoint = ctx.aad_endpoint or aad_settings.endpoint
    token_cache_file = aad_settings.token_cache_file
    # check for aad parameter validity
    if ((aad_directory_id is None and aad_application_id is None and
         aad_auth_key is None and aad_user is None and
         aad_password is None and aad_cert_private_key is None and
         aad_cert_thumbprint is None) or endpoint is None):
        return None
    # create credential object
    if (util.is_not_empty(aad_application_id) and
            util.is_not_empty(aad_cert_private_key)):
        if util.is_not_empty(aad_auth_key):
            raise ValueError('cannot specify both cert auth and auth key')
        if util.is_not_empty(aad_password):
            raise ValueError('cannot specify both cert auth and password')
        if settings.verbose(ctx.config):
            logger.debug(
                ('using aad auth with certificate, auth={} endpoint={} '
                 'directoryid={} appid={} cert_thumbprint={}').format(
                     aad_authority_url, endpoint, aad_directory_id,
                     aad_application_id, aad_cert_thumbprint))
        context = adal.AuthenticationContext(
            '{}/{}'.format(aad_authority_url, aad_directory_id))
        return msrestazure.azure_active_directory.AdalAuthentication(
            lambda: context.acquire_token_with_client_certificate(
                endpoint,
                aad_application_id,
                util.decode_string(open(aad_cert_private_key, 'rb').read()),
                aad_cert_thumbprint
            )
        )
    elif util.is_not_empty(aad_auth_key):
        if util.is_not_empty(aad_password):
            raise ValueError(
                'Cannot specify both an AAD Service Principal and User')
        if settings.verbose(ctx.config):
            logger.debug(
                ('using aad auth with key, auth={} endpoint={} '
                 'directoryid={} appid={}').format(
                     aad_authority_url, endpoint, aad_directory_id,
                     aad_application_id))
        context = adal.AuthenticationContext(
            '{}/{}'.format(aad_authority_url, aad_directory_id))
        return msrestazure.azure_active_directory.AdalAuthentication(
            context.acquire_token_with_client_credentials,
            endpoint,
            aad_application_id,
            aad_auth_key,
        )
    elif util.is_not_empty(aad_password):
        if settings.verbose(ctx.config):
            logger.debug(
                ('using aad auth with username and password, auth={} '
                 'endpoint={} directoryid={} username={}').format(
                     aad_authority_url, endpoint, aad_directory_id, aad_user))
        try:
            return azure.common.credentials.UserPassCredentials(
                username=aad_user,
                password=aad_password,
                tenant=aad_directory_id,
                auth_uri=aad_authority_url,
                resource=endpoint,
            )
        except msrest.exceptions.AuthenticationError as e:
            if 'AADSTS50079' in e.args[0]:
                raise RuntimeError('{} {}'.format(
                    e.args[0][2:],
                    'Do not pass an AAD password and try again.'))
            else:
                raise
    else:
        if settings.verbose(ctx.config):
            logger.debug(
                ('using aad auth with device code, auth={} endpoint={} '
                 'directoryid={}').format(
                     aad_authority_url, endpoint, aad_directory_id))
        return DeviceCodeAuthentication(
            context=adal.AuthenticationContext(
                '{}/{}'.format(aad_authority_url, aad_directory_id)),
            resource=endpoint,
            client_id=_CLIENT_ID,
            token_cache_file=token_cache_file,
        )
