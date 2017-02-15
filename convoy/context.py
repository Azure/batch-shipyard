#!/usr/bin/env python3

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
from __future__ import absolute_import, division, print_function
from builtins import (  # noqa
    bytes, dict, int, list, object, range, str, ascii, chr, hex, input,
    next, oct, open, pow, round, super, filter, map, zip)
# stdlib imports
import json
# local imports
import convoy.fleet
import convoy.settings
import convoy.util

class Context(object):
    """Context class: holds context for Shipyard"""
    def __init__(self):
        """Ctor for Context"""
        self.verbose = False
        self.yes = False
        self.config = None
        self.batch_client = None
        self.blob_client = None
        self.queue_client = None
        self.table_client = None
        self.keyvault_client = None
        # aad/keyvault options
        self.keyvault_uri = None
        self.keyvault_credentials_secret_id = None
        self.aad_directory_id = None
        self.aad_application_id = None
        self.aad_auth_key = None
        self.aad_user = None
        self.aad_password = None
        self.aad_cert_private_key = None
        self.add_cert_thumbprint = None

    def initialize(self, obj_credentials, obj_config=None, obj_pool=None, obj_jobs=None, creds_only=False, no_config=False):
        # type: (Context, bool, bool) -> None
        """Initialize context
        :param Context self: this
        :param bool creds_only: credentials only initialization
        :param bool no_config: do not configure context
        """

        self._update_config(obj_credentials)
        self.keyvault_client = convoy.fleet.create_keyvault_client(
            self, self.config)
        del self.aad_directory_id
        del self.aad_application_id
        del self.aad_auth_key
        del self.aad_user
        del self.aad_password
        del self.aad_cert_private_key
        del self.aad_cert_thumbprint
        self.config = None
        self._init_config(creds_only, obj_credentials, obj_config, obj_pool, obj_jobs)
        if no_config:
            return
        if not creds_only:
            clients = convoy.fleet.initialize(self.config)
            self._set_clients(*clients)

    def _update_config(self, config):
        if self.config is None:
            self.config = config
        elif config:
            self.config = convoy.util.merge_dict(
                self.config, config)

    def _init_config(self, creds_only, obj_credentials, obj_config, obj_pool, obj_jobs):
        # type: (Context, bool) -> None
        """Initializes configuration of the context
        :param Context self: this
        :param bool creds_only: credentials only initialization
        """
        # fetch credentials from keyvault, if json file is missing
        kvcreds = None
        if obj_credentials is None:
            kvcreds = convoy.fleet.fetch_credentials_json_from_keyvault(
                self.keyvault_client, self.keyvault_uri,
                self.keyvault_credentials_secret_id)
        # read credentials json, perform special keyvault processing if
        # required sections are missing
        if kvcreds is None:
            self._update_config(obj_credentials)
            kv = convoy.settings.credentials_keyvault(self.config)
            self.keyvault_uri = self.keyvault_uri or kv.keyvault_uri
            self.keyvault_credentials_secret_id = (
                self.keyvault_credentials_secret_id or
                kv.keyvault_credentials_secret_id
            )
            if self.keyvault_credentials_secret_id is not None:
                try:
                    convoy.settings.credentials_batch(self.config)
                    if len(list(convoy.settings.iterate_storage_credentials(
                            self.config))) == 0:
                        raise KeyError()
                except KeyError:
                    # fetch credentials from keyvault
                    self.config = \
                        convoy.fleet.fetch_credentials_json_from_keyvault(
                            self.keyvault_client, self.keyvault_uri,
                            self.keyvault_credentials_secret_id)
        else:
            self.config = kvcreds
        del kvcreds
        del self.keyvault_credentials_secret_id
        # parse any keyvault secret ids from credentials
        convoy.fleet.fetch_secrets_from_keyvault(
            self.keyvault_client, self.config)
        # read rest of config files
        if not creds_only:
            self._update_config(obj_config)
            self._update_config(obj_pool)
            if obj_jobs is not None:
                self._update_config(obj_jobs)
        # set internal config kv pairs
        self.config['_verbose'] = self.verbose
        self.config['_auto_confirm'] = self.yes
        if self.verbose:
            logger.debug('config:\n' + json.dumps(self.config, indent=4))
        # free mem
        del self.verbose
        del self.yes

    def _set_clients(
            self, batch_client, blob_client, queue_client, table_client):
        """Sets clients for the context"""
        self.batch_client = batch_client
        self.blob_client = blob_client
        self.queue_client = queue_client
        self.table_client = table_client
