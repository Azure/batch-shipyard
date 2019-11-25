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
import logging
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
# non-stdlib imports
import click
import ruamel.yaml
# local imports
import convoy.clients
import convoy.fleet
import convoy.settings
import convoy.util
import convoy.validator

# create logger
logger = logging.getLogger('shipyard')
# global defines
_CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


class CliContext(object):
    """CliContext class: holds context for CLI commands"""
    def __init__(self):
        """Ctor for CliContext"""
        self.cleanup = True
        self.show_config = False
        self.verbose = False
        self.yes = False
        self.raw = None
        self.config = None
        self.conf_config = None
        self.conf_pool = None
        self.conf_jobs = None
        self.conf_fs = None
        self.conf_monitor = None
        self.conf_federation = None
        self.conf_slurm = None
        # clients
        self.batch_mgmt_client = None
        self.batch_client = None
        self.blob_client = None
        self.table_client = None
        self.queue_client = None
        self.keyvault_client = None
        self.auth_client = None
        self.resource_client = None
        self.compute_client = None
        self.network_client = None
        self.storage_mgmt_client = None
        # aad/keyvault options
        self.keyvault_uri = None
        self.keyvault_credentials_secret_id = None
        self.aad_authority_url = None
        self.aad_directory_id = None
        self.aad_application_id = None
        self.aad_auth_key = None
        self.aad_user = None
        self.aad_password = None
        self.aad_cert_private_key = None
        self.aad_cert_thumbprint = None
        self.aad_endpoint = None
        # management options
        self.subscription_id = None

    @staticmethod
    def ensure_pathlib_conf(conf):
        # type: (Any) -> pathlib.Path
        """Ensure conf object is a pathlib object
        :param str or pathlib.Path or None conf: conf object
        :rtype: pathlib.Path or None
        :return: conf object as pathlib
        """
        if conf is not None and not isinstance(conf, pathlib.Path):
            conf = pathlib.Path(conf)
        return conf

    def _ensure_credentials_section(self, section):
        # type: (CliContext, str) -> None
        """Ensure a credentials section exists
        :param CliContext self: this
        :param str section: section name
        """
        fail = True
        # if credentials doesn't exist at all then section won't exist
        if 'credentials' not in self.config:
            # set section to credentials if empty (checking for base)
            if convoy.util.is_none_or_empty(section):
                section = 'credentials'
        elif (convoy.util.is_none_or_empty(section) or
              section in self.config['credentials']):
            # else the credentials section does exist, so the base
            # check is ok if section is not specified, else check if
            # the section exists
            fail = False
        if fail:
            raise RuntimeError(
                ('"{}" configuration is missing or keyvault client is '
                 'invalid. Are you missing your configuration files, '
                 'pointing to the wrong configdir location, or missing '
                 'keyvault configuration/arguments?').format(section))

    def _init_keyvault_client(self):
        # type: (CliContext) -> None
        """Initialize keyvault client and check for valid creds
        :param CliContext self: this
        """
        self.keyvault_client = convoy.clients.create_keyvault_client(self)
        if self.keyvault_client is None:
            self._ensure_credentials_section(None)

    def initialize_for_fs(self):
        # type: (CliContext) -> None
        """Initialize context for fs commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        if self.verbose:
            logger.debug('initializing for remote fs actions')
        self._init_keyvault_client()
        self._init_config(
            skip_global_config=False, skip_pool_config=True,
            skip_monitor_config=True, skip_federation_config=True,
            fs_storage=True)
        self._ensure_credentials_section('storage')
        _, self.resource_client, self.compute_client, self.network_client, \
            self.storage_mgmt_client, _, _ = \
            convoy.clients.create_all_clients(self)
        # inject storage account keys if via aad
        convoy.fleet.fetch_storage_account_keys_from_aad(
            self.storage_mgmt_client, self.config, fs_storage=True)
        self.blob_client, _, _ = convoy.clients.create_storage_clients()
        self._cleanup_after_initialize()

    def initialize_for_monitor(self):
        # type: (CliContext) -> None
        """Initialize context for monitor commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        if self.verbose:
            logger.debug('initializing for monitoring actions')
        self._init_keyvault_client()
        self._init_config(
            skip_global_config=False, skip_pool_config=True,
            skip_monitor_config=False, skip_federation_config=True,
            fs_storage=True)
        self._ensure_credentials_section('storage')
        self._ensure_credentials_section('monitoring')
        self.auth_client, self.resource_client, self.compute_client, \
            self.network_client, self.storage_mgmt_client, _, _ = \
            convoy.clients.create_all_clients(self)
        # inject storage account keys if via aad
        convoy.fleet.fetch_storage_account_keys_from_aad(
            self.storage_mgmt_client, self.config, fs_storage=True)
        self.blob_client, self.table_client, _ = \
            convoy.clients.create_storage_clients()
        self._cleanup_after_initialize()

    def initialize_for_federation(self, init_batch=False):
        # type: (CliContext, bool) -> None
        """Initialize context for fed commands
        :param CliContext self: this
        :param bool init_batch: initialize batch
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        if self.verbose:
            logger.debug('initializing for fed actions')
        self._init_keyvault_client()
        self._init_config(
            skip_global_config=False, skip_pool_config=not init_batch,
            skip_monitor_config=True, skip_federation_config=False,
            fs_storage=not init_batch)
        self._ensure_credentials_section('storage')
        self.auth_client, self.resource_client, self.compute_client, \
            self.network_client, self.storage_mgmt_client, _, \
            self.batch_client = convoy.clients.create_all_clients(
                self, batch_clients=init_batch)
        # inject storage account keys if via aad
        convoy.fleet.fetch_storage_account_keys_from_aad(
            self.storage_mgmt_client, self.config, fs_storage=not init_batch)
        # call populate global settings again to adjust for federation storage
        sc = convoy.settings.federation_credentials_storage(self.config)
        convoy.fleet.populate_global_settings(
            self.config, fs_storage=not init_batch, sc=sc)
        self.blob_client, self.table_client, self.queue_client = \
            convoy.clients.create_storage_clients()
        self._cleanup_after_initialize()

    def initialize_for_slurm(self, init_batch=False):
        # type: (CliContext, bool) -> None
        """Initialize context for slurm commands
        :param CliContext self: this
        :param bool init_batch: initialize batch
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        if self.verbose:
            logger.debug('initializing for slurm actions')
        self._init_keyvault_client()
        self._init_config(
            skip_global_config=False, skip_pool_config=not init_batch,
            skip_monitor_config=True, skip_federation_config=True,
            fs_storage=not init_batch)

        self.conf_slurm = self._form_conf_path(
            self.conf_slurm, 'slurm')
        if self.conf_slurm is None:
            raise ValueError('slurm conf file was not specified')
        self.conf_slurm = CliContext.ensure_pathlib_conf(
            self.conf_slurm)
        convoy.validator.validate_config(
            convoy.validator.ConfigType.Slurm, self.conf_slurm)
        self._read_config_file(self.conf_slurm)

        self._ensure_credentials_section('storage')
        self._ensure_credentials_section('slurm')
        self.auth_client, self.resource_client, self.compute_client, \
            self.network_client, self.storage_mgmt_client, \
            self.batch_mgmt_client, self.batch_client = \
            convoy.clients.create_all_clients(
                self, batch_clients=init_batch)
        # inject storage account keys if via aad
        convoy.fleet.fetch_storage_account_keys_from_aad(
            self.storage_mgmt_client, self.config, fs_storage=not init_batch)
        # call populate global settings again to adjust for slurm storage
        sc = convoy.settings.slurm_credentials_storage(self.config)
        convoy.fleet.populate_global_settings(
            self.config, fs_storage=not init_batch, sc=sc)
        self.blob_client, self.table_client, self.queue_client = \
            convoy.clients.create_storage_clients()
        self._cleanup_after_initialize()

    def initialize_for_keyvault(self):
        # type: (CliContext) -> None
        """Initialize context for keyvault commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        if self.verbose:
            logger.debug('initializing for keyvault actions')
        self._init_keyvault_client()
        self._init_config(
            skip_global_config=True, skip_pool_config=True,
            skip_monitor_config=True, skip_federation_config=True,
            fs_storage=False)
        # do not perform keyvault credentials section check as all
        # options can be specified off the cli, validity of the keyvault
        # client will be checked later
        self._cleanup_after_initialize()

    def initialize_for_batch(self):
        # type: (CliContext) -> None
        """Initialize context for batch commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        if self.verbose:
            logger.debug('initializing for batch actions')
        self._init_keyvault_client()
        self._init_config(
            skip_global_config=False, skip_pool_config=False,
            skip_monitor_config=True, skip_federation_config=True,
            fs_storage=False)
        self._ensure_credentials_section('storage')
        self._ensure_credentials_section('batch')
        _, self.resource_client, self.compute_client, self.network_client, \
            self.storage_mgmt_client, self.batch_mgmt_client, \
            self.batch_client = \
            convoy.clients.create_all_clients(self, batch_clients=True)
        # inject storage account keys if via aad
        convoy.fleet.fetch_storage_account_keys_from_aad(
            self.storage_mgmt_client, self.config, fs_storage=False)
        self.blob_client, self.table_client, _ = \
            convoy.clients.create_storage_clients()
        self._cleanup_after_initialize()

    def initialize_for_storage(self):
        # type: (CliContext) -> None
        """Initialize context for storage commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        if self.verbose:
            logger.debug('initializing for storage actions')
        self._init_keyvault_client()
        self._init_config(
            skip_global_config=False, skip_pool_config=False,
            skip_monitor_config=True, skip_federation_config=True,
            fs_storage=False)
        self._ensure_credentials_section('storage')
        # inject storage account keys if via aad
        _, _, _, _, self.storage_mgmt_client, _, _ = \
            convoy.clients.create_all_clients(self)
        convoy.fleet.fetch_storage_account_keys_from_aad(
            self.storage_mgmt_client, self.config, fs_storage=False)
        self.blob_client, self.table_client, _ = \
            convoy.clients.create_storage_clients()
        self._cleanup_after_initialize()

    def _set_global_cli_options(self):
        # type: (CliContext) -> None
        """Set global cli options
        :param CliContext self: this
        """
        if self.config is None:
            self.config = {}
        # set internal config kv pairs
        self.config['_verbose'] = self.verbose
        self.config['_auto_confirm'] = self.yes
        self.config['_raw'] = self.raw
        # increase detail in logger formatters
        if self.verbose:
            convoy.util.set_verbose_logger_handlers()

    def _cleanup_after_initialize(self):
        # type: (CliContext) -> None
        """Cleanup after initialize_for_* funcs
        :param CliContext self: this
        """
        if not self.cleanup:
            return
        # free conf objects
        del self.conf_credentials
        del self.conf_fs
        del self.conf_config
        del self.conf_pool
        del self.conf_jobs
        del self.conf_monitor
        del self.conf_federation
        del self.conf_slurm
        # free cli options
        del self.verbose
        del self.yes
        del self.raw
        del self.aad_authority_url
        del self.aad_directory_id
        del self.aad_application_id
        del self.aad_auth_key
        del self.aad_user
        del self.aad_password
        del self.aad_cert_private_key
        del self.aad_cert_thumbprint
        del self.aad_endpoint
        del self.keyvault_credentials_secret_id
        del self.subscription_id
        # free clients that won't be used
        del self.storage_mgmt_client

    def _read_config_file(self, config_file):
        # type: (CliContext, pathlib.Path) -> None
        """Read a yaml/json file into self.config
        :param CliContext self: this
        :param pathlib.Path config_file: config file to load
        """
        with config_file.open('r') as f:
            if self.config is None:
                self.config = ruamel.yaml.load(
                    f, Loader=ruamel.yaml.RoundTripLoader)
            else:
                self.config = convoy.util.merge_dict(
                    self.config,
                    ruamel.yaml.load(f, Loader=ruamel.yaml.RoundTripLoader))

    def _form_conf_path(self, conf_var, prefix):
        """Form configuration file path with configdir if applicable
        :param CliContext self: this
        :param any conf_var: conf var
        :param str prefix: configuration file prefix
        :rtype: pathlib.Path
        :return: new configuration file path
        """
        # use configdir if available
        if conf_var is None:
            cd = self.configdir or '.'
            pathyaml = pathlib.Path(cd, '{}.yaml'.format(prefix))
            if pathyaml.exists():
                return pathyaml
            path = pathlib.Path(cd, '{}.yml'.format(prefix))
            if path.exists():
                return path
            path = pathlib.Path(cd, '{}.json'.format(prefix))
            if path.exists():
                return path
            return pathyaml
        else:
            return conf_var

    def _read_credentials_config(self):
        # type: (CliContext) -> None
        """Read credentials config file only
        :param CliContext self: this
        """
        self.conf_credentials = self._form_conf_path(
            self.conf_credentials, 'credentials')
        if self.conf_credentials is not None:
            self.conf_credentials = CliContext.ensure_pathlib_conf(
                self.conf_credentials)
            if self.conf_credentials.exists():
                self._read_config_file(self.conf_credentials)

    def _init_config(
            self, skip_global_config=False, skip_pool_config=False,
            skip_monitor_config=True, skip_federation_config=True,
            fs_storage=False):
        # type: (CliContext, bool, bool, bool, bool, bool) -> None
        """Initializes configuration of the context
        :param CliContext self: this
        :param bool skip_global_config: skip global config
        :param bool skip_pool_config: skip pool config
        :param bool skip_monitor_config: skip monitoring config
        :param bool skip_federation_config: skip federation config
        :param bool fs_storage: adjust storage settings for fs
        """
        # reset config
        self.config = None
        self._set_global_cli_options()
        # set/validate credentials config
        self.conf_credentials = self._form_conf_path(
            self.conf_credentials, 'credentials')
        self.conf_credentials = CliContext.ensure_pathlib_conf(
            self.conf_credentials)
        convoy.validator.validate_config(
            convoy.validator.ConfigType.Credentials, self.conf_credentials)
        # set/validate global config
        if not skip_global_config:
            self.conf_config = self._form_conf_path(self.conf_config, 'config')
            if self.conf_config is None:
                raise ValueError('config conf file was not specified')
            self.conf_config = CliContext.ensure_pathlib_conf(self.conf_config)
            convoy.validator.validate_config(
                convoy.validator.ConfigType.Global, self.conf_config)
        # set/validate batch config
        if not skip_pool_config:
            # set/validate pool config
            self.conf_pool = self._form_conf_path(self.conf_pool, 'pool')
            if self.conf_pool is None:
                raise ValueError('pool conf file was not specified')
            self.conf_pool = CliContext.ensure_pathlib_conf(self.conf_pool)
            convoy.validator.validate_config(
                convoy.validator.ConfigType.Pool, self.conf_pool)
            # set/validate jobs config
            self.conf_jobs = self._form_conf_path(self.conf_jobs, 'jobs')
            self.conf_jobs = CliContext.ensure_pathlib_conf(self.conf_jobs)
            convoy.validator.validate_config(
                convoy.validator.ConfigType.Jobs, self.conf_jobs)
        # set/validate fs config
        self.conf_fs = self._form_conf_path(self.conf_fs, 'fs')
        self.conf_fs = CliContext.ensure_pathlib_conf(self.conf_fs)
        convoy.validator.validate_config(
            convoy.validator.ConfigType.RemoteFS, self.conf_fs)
        # set/validate monitoring config
        if not skip_monitor_config:
            self.conf_monitor = self._form_conf_path(
                self.conf_monitor, 'monitor')
            if self.conf_monitor is None:
                raise ValueError('monitor conf file was not specified')
            self.conf_monitor = CliContext.ensure_pathlib_conf(
                self.conf_monitor)
            convoy.validator.validate_config(
                convoy.validator.ConfigType.Monitor, self.conf_monitor)
        # set/validate federation config
        if not skip_federation_config:
            self.conf_federation = self._form_conf_path(
                self.conf_federation, 'federation')
            if self.conf_federation is None:
                raise ValueError('federation conf file was not specified')
            self.conf_federation = CliContext.ensure_pathlib_conf(
                self.conf_federation)
            convoy.validator.validate_config(
                convoy.validator.ConfigType.Federation, self.conf_federation)
        # fetch credentials from keyvault, if conf file is missing
        kvcreds = None
        if self.conf_credentials is None or not self.conf_credentials.exists():
            kvcreds = convoy.fleet.fetch_credentials_conf_from_keyvault(
                self.keyvault_client, self.keyvault_uri,
                self.keyvault_credentials_secret_id)
        # read credentials conf, perform special keyvault processing if
        # required sections are missing
        if kvcreds is None:
            self._read_config_file(self.conf_credentials)
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
                        convoy.fleet.fetch_credentials_conf_from_keyvault(
                            self.keyvault_client, self.keyvault_uri,
                            self.keyvault_credentials_secret_id)
        else:
            self.config = kvcreds
        del kvcreds
        # re-populate global cli options again
        self._set_global_cli_options()
        # parse any keyvault secret ids from credentials
        convoy.fleet.fetch_secrets_from_keyvault(
            self.keyvault_client, self.config)
        # read rest of config files
        if not skip_global_config:
            self._read_config_file(self.conf_config)
        # read fs config regardless of skip setting
        if self.conf_fs is not None and self.conf_fs.exists():
            self._read_config_file(self.conf_fs)
        if not skip_pool_config:
            self._read_config_file(self.conf_pool)
            if self.conf_jobs is not None:
                self.conf_jobs = CliContext.ensure_pathlib_conf(self.conf_jobs)
                if self.conf_jobs.exists():
                    self._read_config_file(self.conf_jobs)
        if not skip_monitor_config:
            self._read_config_file(self.conf_monitor)
        if not skip_federation_config:
            self._read_config_file(self.conf_federation)
        # adjust settings
        convoy.fleet.initialize_globals(convoy.settings.verbose(self.config))
        if not skip_global_config:
            convoy.fleet.populate_global_settings(self.config, fs_storage)
        # show config if specified
        if self.show_config:
            logger.debug('config:\n' + json.dumps(self.config, indent=4))
        # disable azure storage/cosmosdb logging: setting logger level
        # to CRITICAL effectively disables logging from azure storage/cosmosdb
        az_logger = logging.getLogger('azure.storage')
        az_logger.setLevel(logging.CRITICAL)
        az_logger = logging.getLogger('azure.cosmosdb')
        az_logger.setLevel(logging.CRITICAL)


# create a pass decorator for shared context between commands
pass_cli_context = click.make_pass_decorator(CliContext, ensure=True)


def _confirm_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.yes = value
        return value
    return click.option(
        '-y', '--yes',
        expose_value=False,
        is_flag=True,
        help='Assume yes for all confirmation prompts',
        callback=callback)(f)


def _log_file_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.logfile = value
        return value
    return click.option(
        '--log-file',
        expose_value=False,
        envvar='SHIPYARD_LOG_FILE',
        help='Log to file',
        callback=callback)(f)


def _show_config_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.show_config = value
        return value
    return click.option(
        '--show-config',
        expose_value=False,
        is_flag=True,
        help='Show configuration',
        callback=callback)(f)


def _verbose_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.verbose = value
        return value
    return click.option(
        '-v', '--verbose',
        expose_value=False,
        is_flag=True,
        help='Verbose output',
        callback=callback)(f)


def _raw_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.raw = value
        return value
    return click.option(
        '--raw',
        expose_value=False,
        is_flag=True,
        help='Output data as returned by the service for supported '
        'operations as raw json',
        callback=callback)(f)


def _azure_keyvault_uri_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.keyvault_uri = value
        return value
    return click.option(
        '--keyvault-uri',
        expose_value=False,
        envvar='SHIPYARD_KEYVAULT_URI',
        help='Azure KeyVault URI',
        callback=callback)(f)


def _azure_keyvault_credentials_secret_id_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.keyvault_credentials_secret_id = value
        return value
    return click.option(
        '--keyvault-credentials-secret-id',
        expose_value=False,
        envvar='SHIPYARD_KEYVAULT_CREDENTIALS_SECRET_ID',
        help='Azure KeyVault credentials secret id',
        callback=callback)(f)


def _aad_directory_id_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_directory_id = value
        return value
    return click.option(
        '--aad-directory-id',
        expose_value=False,
        envvar='SHIPYARD_AAD_DIRECTORY_ID',
        help='Azure Active Directory directory (tenant) id',
        callback=callback)(f)


def _aad_application_id_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_application_id = value
        return value
    return click.option(
        '--aad-application-id',
        expose_value=False,
        envvar='SHIPYARD_AAD_APPLICATION_ID',
        help='Azure Active Directory application (client) id',
        callback=callback)(f)


def _aad_auth_key_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_auth_key = value
        return value
    return click.option(
        '--aad-auth-key',
        expose_value=False,
        envvar='SHIPYARD_AAD_AUTH_KEY',
        help='Azure Active Directory authentication key',
        callback=callback)(f)


def _aad_authority_url_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_authority_url = value
        return value
    return click.option(
        '--aad-authority-url',
        expose_value=False,
        envvar='SHIPYARD_AAD_AUTHORITY_URL',
        help='Azure Active Directory authority URL',
        callback=callback)(f)


def _aad_user_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_user = value
        return value
    return click.option(
        '--aad-user',
        expose_value=False,
        envvar='SHIPYARD_AAD_USER',
        help='Azure Active Directory user',
        callback=callback)(f)


def _aad_password_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_password = value
        return value
    return click.option(
        '--aad-password',
        expose_value=False,
        envvar='SHIPYARD_AAD_PASSWORD',
        help='Azure Active Directory password',
        callback=callback)(f)


def _aad_cert_private_key_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_cert_private_key = value
        return value
    return click.option(
        '--aad-cert-private-key',
        expose_value=False,
        envvar='SHIPYARD_AAD_CERT_PRIVATE_KEY',
        help='Azure Active Directory private key for X.509 certificate',
        callback=callback)(f)


def _aad_cert_thumbprint_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_cert_thumbprint = value
        return value
    return click.option(
        '--aad-cert-thumbprint',
        expose_value=False,
        envvar='SHIPYARD_AAD_CERT_THUMBPRINT',
        help='Azure Active Directory certificate SHA1 thumbprint',
        callback=callback)(f)


def _aad_endpoint_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.aad_endpoint = value
        return value
    return click.option(
        '--aad-endpoint',
        expose_value=False,
        envvar='SHIPYARD_AAD_ENDPOINT',
        help='Azure Active Directory endpoint',
        callback=callback)(f)


def _azure_subscription_id_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.subscription_id = value
        return value
    return click.option(
        '--subscription-id',
        expose_value=False,
        envvar='SHIPYARD_SUBSCRIPTION_ID',
        help='Azure Subscription ID',
        callback=callback)(f)


def _configdir_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.configdir = value
        return value
    return click.option(
        '--configdir',
        expose_value=False,
        envvar='SHIPYARD_CONFIGDIR',
        help='Configuration directory where all configuration files can be '
        'found. Each config file must be named exactly the same as the '
        'regular switch option, e.g., pool.yaml for --pool. Individually '
        'specified config options take precedence over this option. This '
        'defaults to "." if no other configuration option is specified.',
        callback=callback)(f)


def _credentials_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_credentials = value
        return value
    return click.option(
        '--credentials',
        expose_value=False,
        envvar='SHIPYARD_CREDENTIALS_CONF',
        help='Credentials config file',
        callback=callback)(f)


def _config_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_config = value
        return value
    return click.option(
        '--config',
        expose_value=False,
        envvar='SHIPYARD_CONFIG_CONF',
        help='Global config file',
        callback=callback)(f)


def _pool_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_pool = value
        return value
    return click.option(
        '--pool',
        expose_value=False,
        envvar='SHIPYARD_POOL_CONF',
        help='Pool config file',
        callback=callback)(f)


def _jobs_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_jobs = value
        return value
    return click.option(
        '--jobs',
        expose_value=False,
        envvar='SHIPYARD_JOBS_CONF',
        help='Jobs config file',
        callback=callback)(f)


def federation_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_federation = value
        return value
    return click.option(
        '--federation',
        expose_value=False,
        envvar='SHIPYARD_FEDERATION_CONF',
        help='Federation config file',
        callback=callback)(f)


def fs_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_fs = value
        return value
    return click.option(
        '--fs',
        expose_value=False,
        envvar='SHIPYARD_FS_CONF',
        help='RemoteFS config file',
        callback=callback)(f)


def monitor_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_monitor = value
        return value
    return click.option(
        '--monitor',
        expose_value=False,
        envvar='SHIPYARD_MONITOR_CONF',
        help='Resource monitoring config file',
        callback=callback)(f)


def slurm_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.conf_slurm = value
        return value
    return click.option(
        '--slurm',
        expose_value=False,
        envvar='SHIPYARD_SLURM_CONF',
        help='Slurm config file',
        callback=callback)(f)


def _storage_cluster_id_argument(f):
    def callback(ctx, param, value):
        return value
    return click.argument(
        'storage-cluster-id',
        callback=callback)(f)


def common_options(f):
    f = _config_option(f)
    f = _credentials_option(f)
    f = _configdir_option(f)
    f = _verbose_option(f)
    f = _show_config_option(f)
    f = _raw_option(f)
    # f = _log_file_option(f)
    f = _confirm_option(f)
    return f


def aad_options(f):
    f = _aad_cert_thumbprint_option(f)
    f = _aad_cert_private_key_option(f)
    f = _aad_password_option(f)
    f = _aad_user_option(f)
    f = _aad_authority_url_option(f)
    f = _aad_auth_key_option(f)
    f = _aad_application_id_option(f)
    f = _aad_directory_id_option(f)
    f = _aad_endpoint_option(f)
    return f


def batch_options(f):
    f = _azure_subscription_id_option(f)
    f = _jobs_option(f)
    f = _pool_option(f)
    return f


def keyvault_options(f):
    f = _azure_keyvault_credentials_secret_id_option(f)
    f = _azure_keyvault_uri_option(f)
    return f


def fs_options(f):
    f = _azure_subscription_id_option(f)
    f = fs_option(f)
    return f


def fs_cluster_options(f):
    f = fs_options(f)
    f = _storage_cluster_id_argument(f)
    return f


def monitor_options(f):
    f = monitor_option(f)
    f = _azure_subscription_id_option(f)
    return f


def federation_options(f):
    f = federation_option(f)
    f = _azure_subscription_id_option(f)
    return f


def slurm_options(f):
    f = slurm_option(f)
    f = _azure_subscription_id_option(f)
    return f


@click.group(context_settings=_CONTEXT_SETTINGS)
@click.version_option(version=convoy.__version__)
@click.pass_context
def cli(ctx):
    """Batch Shipyard: Simplify HPC and Batch workloads on Azure"""
    pass


@cli.group()
@pass_cli_context
def account(ctx):
    """Batch account actions"""
    pass


@account.command('images')
@click.option(
    '--show-unrelated', is_flag=True, help='Include unrelated images')
@click.option(
    '--show-unverified', is_flag=True, help='Include unverified images')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def account_images(ctx, show_unrelated, show_unverified):
    """List available VM images available to the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_account_images(
        ctx.batch_client, ctx.config, show_unrelated, show_unverified)


@account.command('info')
@click.option('--name', help='Batch account name')
@click.option('--resource-group', help='Batch account resource group')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def account_info(ctx, name, resource_group):
    """Retrieve Batch account information and quotas"""
    ctx.initialize_for_batch()
    convoy.fleet.action_account_info(
        ctx.batch_mgmt_client, ctx.config, name, resource_group)


@account.command('list')
@click.option('--resource-group', help='Scope query to resource group')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def account_list(ctx, resource_group):
    """Retrieve a list of Batch accounts and associated quotas in
    subscription"""
    ctx.initialize_for_batch()
    convoy.fleet.action_account_list(
        ctx.batch_mgmt_client, ctx.config, resource_group)


@account.command('quota')
@click.argument('location')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def account_quota(ctx, location):
    """Retrieve Batch account quota at the subscription level for the
    specified location"""
    ctx.initialize_for_batch()
    convoy.fleet.action_account_quota(
        ctx.batch_mgmt_client, ctx.config, location)


@cli.group()
@pass_cli_context
def fs(ctx):
    """Filesystem in Azure actions"""
    pass


@fs.group()
@pass_cli_context
def cluster(ctx):
    """Filesystem storage cluster in Azure actions"""
    pass


@cluster.command('add')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_add(ctx, storage_cluster_id):
    """Create a filesystem storage cluster in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.config, storage_cluster_id)


@cluster.command('orchestrate')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_orchestrate(ctx, storage_cluster_id):
    """Orchestrate a filesystem storage cluster in Azure with the
    specified disks"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_disks_add(
        ctx.resource_client, ctx.compute_client, ctx.config)
    convoy.fleet.action_fs_cluster_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.config, storage_cluster_id)


@cluster.command('resize')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_resize(ctx, storage_cluster_id):
    """Resize a filesystem storage cluster in Azure. Only increasing the
    storage cluster size is supported."""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_resize(
        ctx.compute_client, ctx.network_client, ctx.blob_client, ctx.config,
        storage_cluster_id)


@cluster.command('expand')
@click.option(
    '--no-rebalance', is_flag=True,
    help='Do not rebalance filesystem, if applicable')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_expand(ctx, storage_cluster_id, no_rebalance):
    """Expand a filesystem storage cluster in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_expand(
        ctx.compute_client, ctx.network_client, ctx.config,
        storage_cluster_id, not no_rebalance)


@cluster.command('del')
@click.option(
    '--delete-resource-group', is_flag=True,
    help='Delete all resources in the storage cluster resource group')
@click.option(
    '--delete-data-disks', is_flag=True,
    help='Delete all attached managed data disks')
@click.option(
    '--delete-virtual-network', is_flag=True, help='Delete virtual network')
@click.option(
    '--generate-from-prefix', is_flag=True,
    help='Generate resources to delete from storage cluster hostname prefix')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for deletion to complete')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_del(
        ctx, storage_cluster_id, delete_resource_group, delete_data_disks,
        delete_virtual_network, generate_from_prefix, no_wait):
    """Delete a filesystem storage cluster in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_del(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.config, storage_cluster_id,
        delete_resource_group, delete_data_disks, delete_virtual_network,
        generate_from_prefix, not no_wait)


@cluster.command('suspend')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for suspension to complete')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_suspend(ctx, storage_cluster_id, no_wait):
    """Suspend a filesystem storage cluster in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_suspend(
        ctx.compute_client, ctx.config, storage_cluster_id, not no_wait)


@cluster.command('start')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for restart to complete')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_start(ctx, storage_cluster_id, no_wait):
    """Starts a previously suspended filesystem storage cluster in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_start(
        ctx.compute_client, ctx.network_client, ctx.config,
        storage_cluster_id, not no_wait)


@cluster.command('status')
@click.option(
    '--detail', is_flag=True, help='Detailed storage cluster status')
@click.option(
    '--hosts', is_flag=True,
    help='Output /etc/hosts compatible name resolution for GlusterFS clusters')
@common_options
@fs_cluster_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_status(ctx, storage_cluster_id, detail, hosts):
    """Query status of a filesystem storage cluster in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_status(
        ctx.compute_client, ctx.network_client, ctx.config,
        storage_cluster_id, detail, hosts)


@cluster.command('ssh')
@click.option(
    '--cardinal',
    help='Zero-based cardinal number of remote fs vm to connect to',
    type=int)
@click.option(
    '--hostname', help='Hostname of remote fs vm to connect to')
@click.option(
    '--tty', is_flag=True, help='Allocate a pseudo-tty')
@common_options
@fs_cluster_options
@click.argument('command', nargs=-1)
@keyvault_options
@aad_options
@pass_cli_context
def fs_cluster_ssh(ctx, storage_cluster_id, cardinal, hostname, tty, command):
    """Interactively login via SSH to a filesystem storage cluster virtual
    machine in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_ssh(
        ctx.compute_client, ctx.network_client, ctx.config,
        storage_cluster_id, cardinal, hostname, tty, command)


@fs.group()
@pass_cli_context
def disks(ctx):
    """Managed disk actions"""
    pass


@disks.command('add')
@common_options
@fs_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_disks_add(ctx):
    """Create managed disks in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_disks_add(
        ctx.resource_client, ctx.compute_client, ctx.config)


@disks.command('del')
@click.option(
    '--all', is_flag=True, help='Delete all disks in resource group')
@click.option(
    '--delete-resource-group', is_flag=True,
    help='Delete specified resource group')
@click.option(
    '--name', help='Delete disk with specified name only')
@click.option(
    '--resource-group',
    help='Delete disks matching specified resource group only')
@click.option(
    '--no-wait', is_flag=True,
    help='Do not wait for disk deletion to complete')
@common_options
@fs_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_disks_del(
        ctx, all, delete_resource_group, name, resource_group, no_wait):
    """Delete managed disks in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_disks_del(
        ctx.resource_client, ctx.compute_client, ctx.config, name,
        resource_group, all, delete_resource_group, not no_wait)


@disks.command('list')
@click.option(
    '--resource-group',
    help='List disks matching specified resource group only')
@click.option(
    '--restrict-scope', is_flag=True,
    help='List disks present only in configuration if they exist')
@common_options
@fs_options
@keyvault_options
@aad_options
@pass_cli_context
def fs_disks_list(ctx, resource_group, restrict_scope):
    """List managed disks in resource group"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_disks_list(
        ctx.compute_client, ctx.config, resource_group, restrict_scope)


@cli.group()
@pass_cli_context
def storage(ctx):
    """Storage actions"""
    pass


@storage.command('del')
@click.option(
    '--clear-tables', is_flag=True, help='Clear tables instead of deleting')
@click.option(
    '--diagnostics-logs', is_flag=True,
    help='Delete container used for uploaded diagnostics logs')
@click.option(
    '--poolid', multiple=True,
    help='Delete storage containers for the specified pool')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def storage_del(ctx, clear_tables, diagnostics_logs, poolid):
    """Delete Azure Storage containers used by Batch Shipyard"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_del(
        ctx.blob_client, ctx.table_client, ctx.config, clear_tables,
        diagnostics_logs, poolid)


@storage.command('clear')
@click.option(
    '--diagnostics-logs', is_flag=True, help='Clear uploaded diagnostics logs')
@click.option(
    '--poolid', multiple=True,
    help='Clear storage containers for the specified pool')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def storage_clear(ctx, diagnostics_logs, poolid):
    """Clear Azure Storage containers used by Batch Shipyard"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_clear(
        ctx.blob_client, ctx.table_client, ctx.config, diagnostics_logs,
        poolid)


@storage.group()
@pass_cli_context
def sas(ctx):
    """SAS token actions"""
    pass


@sas.command('create')
@click.option(
    '--create', is_flag=True, help='Create permission')
@click.option(
    '--delete', is_flag=True, help='Delete permission')
@click.option(
    '--file', is_flag=True, help='Create file SAS instead of blob SAS')
@click.option(
    '--list', is_flag=True, help='List permission')
@click.option(
    '--read', is_flag=True, help='Read permission')
@click.option(
    '--write', is_flag=True, help='Write permission')
@click.argument('storage-account')
@click.argument('path')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def sas_create(
        ctx, create, delete, file, list, read, write, storage_account, path):
    """Create a container- or object-level SAS token"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_sas_create(
        ctx.config, storage_account, path, file, create, list, read, write,
        delete)


@cli.group()
@pass_cli_context
def keyvault(ctx):
    """KeyVault actions"""
    pass


@keyvault.command('add')
@click.argument('name')
@common_options
@keyvault_options
@aad_options
@pass_cli_context
def keyvault_add(ctx, name):
    """Add a credentials config file as a secret to Azure KeyVault"""
    ctx.initialize_for_keyvault()
    convoy.fleet.action_keyvault_add(
        ctx.keyvault_client, ctx.config, ctx.keyvault_uri, name)


@keyvault.command('del')
@click.argument('name')
@common_options
@keyvault_options
@aad_options
@pass_cli_context
def keyvault_del(ctx, name):
    """Delete a secret from Azure KeyVault"""
    ctx.initialize_for_keyvault()
    convoy.fleet.action_keyvault_del(
        ctx.keyvault_client, ctx.keyvault_uri, name)


@keyvault.command('list')
@common_options
@keyvault_options
@aad_options
@pass_cli_context
def keyvault_list(ctx):
    """List secret ids and metadata in an Azure KeyVault"""
    ctx.initialize_for_keyvault()
    convoy.fleet.action_keyvault_list(ctx.keyvault_client, ctx.keyvault_uri)


@cli.group()
@pass_cli_context
def cert(ctx):
    """Certificate actions"""
    pass


@cert.command('create')
@click.option('--file-prefix', help='Certificate file prefix')
@click.option('--pfx-password', help='PFX password')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_create(ctx, file_prefix, pfx_password):
    """Create a certificate to use with a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_create(ctx.config, file_prefix, pfx_password)


@cert.command('add')
@click.option('--file', help='Certificate file to add')
@click.option(
    '--pem-no-certs', is_flag=True, help='Do not export certs from PEM file')
@click.option(
    '--pem-public-key', is_flag=True, help='Add public key only from PEM file')
@click.option('--pfx-password', help='PFX password')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_add(ctx, file, pem_no_certs, pem_public_key, pfx_password):
    """Add a certificate to a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_add(
        ctx.batch_client, ctx.config, file, pem_no_certs, pem_public_key,
        pfx_password)


@cert.command('list')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_list(ctx):
    """List all certificates in a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_list(ctx.batch_client, ctx.config)


@cert.command('del')
@click.option(
    '--sha1', multiple=True, help='SHA1 thumbprint of certificate to delete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_del(ctx, sha1):
    """Delete certificates from a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_del(ctx.batch_client, ctx.config, sha1)


@cli.group()
@pass_cli_context
def pool(ctx):
    """Pool actions"""
    pass


@pool.command('add')
@click.option(
    '--recreate', is_flag=True, help='Recreate pool if it exists')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for nodes to provision')
@common_options
@fs_option
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_add(ctx, recreate, no_wait):
    """Add a pool to the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.batch_mgmt_client, ctx.batch_client, ctx.blob_client,
        ctx.table_client, ctx.keyvault_client, ctx.config, recreate, no_wait)


@pool.command('exists')
@click.option(
    '--pool-id', help='Query specified pool')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_exists(ctx, pool_id):
    """Check if a pool exists"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_exists(
        ctx.batch_client, ctx.config, pool_id=pool_id)


@pool.command('list')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_list(ctx):
    """List all pools in the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_list(ctx.batch_client, ctx.config)


@pool.command('del')
@click.option(
    '--poolid', help='Delete the specified pool')
@click.option(
    '--wait', is_flag=True, help='Wait for pool deletion to complete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_del(ctx, poolid, wait):
    """Delete a pool from the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_delete(
        ctx.batch_client, ctx.blob_client, ctx.table_client, ctx.config,
        pool_id=poolid, wait=wait)


@pool.command('resize')
@click.option(
    '--wait', is_flag=True, help='Wait for pool resize to complete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_resize(ctx, wait):
    """Resize a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_resize(
        ctx.batch_client, ctx.blob_client, ctx.config, wait=wait)


@pool.command('ssh')
@click.option(
    '--cardinal',
    help='Zero-based cardinal number of compute node in pool to connect to',
    type=int)
@click.option(
    '--nodeid', help='NodeId of compute node in pool to connect to')
@click.option(
    '--tty', is_flag=True, help='Allocate a pseudo-tty')
@click.argument('command', nargs=-1)
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_ssh(ctx, cardinal, nodeid, tty, command):
    """Interactively login via SSH to a node in a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_ssh(
        ctx.batch_client, ctx.config, cardinal, nodeid, tty, command)


@pool.command('rdp')
@click.option(
    '--cardinal',
    help='Zero-based cardinal number of compute node in pool to connect to',
    type=int)
@click.option(
    '--no-auto', is_flag=True,
    help='Do not automatically login if RDP password is present')
@click.option(
    '--nodeid', help='NodeId of compute node in pool to connect to')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_rdp(ctx, cardinal, no_auto, nodeid):
    """Interactively login via RDP to a node in a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_rdp(
        ctx.batch_client, ctx.config, cardinal, nodeid, no_auto=no_auto)


@pool.command('stats')
@click.option('--poolid', help='Get stats on specified pool')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_stats(ctx, poolid):
    """Get statistics about a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_stats(
        ctx.batch_client, ctx.config, pool_id=poolid)


@pool.group()
@pass_cli_context
def autoscale(ctx):
    """Autoscale actions"""
    pass


@autoscale.command('disable')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def autoscale_disable(ctx):
    """Disable autoscale on a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_autoscale_disable(ctx.batch_client, ctx.config)


@autoscale.command('enable')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def autoscale_enable(ctx):
    """Enable autoscale on a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_autoscale_enable(ctx.batch_client, ctx.config)


@autoscale.command('evaluate')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def autoscale_evaluate(ctx):
    """Evaluate autoscale formula"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_autoscale_evaluate(ctx.batch_client, ctx.config)


@autoscale.command('lastexec')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def autoscale_lastexec(ctx):
    """Get the result of the last execution of the autoscale formula"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_autoscale_lastexec(ctx.batch_client, ctx.config)


@pool.group()
@pass_cli_context
def images(ctx):
    """Container images actions"""
    pass


@images.command('update')
@click.option(
    '--docker-image', help='Docker image[:tag] to update')
@click.option(
    '--docker-image-digest', help='Digest to update Docker image to')
@click.option(
    '--singularity-image', help='Singularity image[:tag] to update')
@click.option(
    '--ssh', is_flag=True, help='Update over SSH instead of using a Batch job')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def images_update(
        ctx, docker_image, docker_image_digest, singularity_image, ssh):
    """Update container images in a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_images_update(
        ctx.batch_client, ctx.config, docker_image, docker_image_digest,
        singularity_image, ssh)


@images.command('list')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def images_list(ctx):
    """List container images in a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_images_list(ctx.batch_client, ctx.config)


@pool.group()
@pass_cli_context
def user(ctx):
    """Remote user actions"""
    pass


@user.command('add')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def user_add(ctx):
    """Add a remote user to all nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_user_add(ctx.batch_client, ctx.config)


@user.command('del')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def user_del(ctx):
    """Delete a remote user from all nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_user_del(ctx.batch_client, ctx.config)


@pool.group()
@pass_cli_context
def nodes(ctx):
    """Compute node actions"""
    pass


@nodes.command('grls')
@click.option(
    '--no-generate-tunnel-script', is_flag=True,
    help='Disable generating an SSH tunnel script')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_grls(ctx, no_generate_tunnel_script):
    """Get remote login settings for all nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_grls(
        ctx.batch_client, ctx.config, no_generate_tunnel_script)


@nodes.command('count')
@click.option(
    '--poolid', help='Target specified pool id rather than from configuration')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_count(ctx, poolid):
    """Get node counts in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_count(ctx.batch_client, ctx.config, poolid)


@nodes.command('list')
@click.option(
    '--start-task-failed',
    is_flag=True,
    help='List nodes in start task failed state')
@click.option(
    '--unusable',
    is_flag=True,
    help='List nodes in unusable state')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_list(ctx, start_task_failed, unusable):
    """List nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_list(
        ctx.batch_client, ctx.config, start_task_failed, unusable)


@nodes.command('zap')
@click.option(
    '--no-remove', is_flag=True, help='Do not remove exited containers')
@click.option(
    '--stop', is_flag=True, help='Use docker stop instead of kill')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_zap(ctx, no_remove, stop):
    """Zap all container processes on nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_zap(
        ctx.batch_client, ctx.config, not no_remove, stop)


@nodes.command('prune')
@click.option(
    '--volumes', is_flag=True, help='Prune volumes as well')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_prune(ctx, volumes):
    """Prune container/image data on nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_prune(ctx.batch_client, ctx.config, volumes)


@nodes.command('ps')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_ps(ctx):
    """List running containers on nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_ps(ctx.batch_client, ctx.config)


@nodes.command('del')
@click.option(
    '--all-start-task-failed',
    is_flag=True,
    help='Delete all nodes in start task failed state')
@click.option(
    '--all-starting',
    is_flag=True,
    help='Delete all nodes in starting state')
@click.option(
    '--all-unusable',
    is_flag=True,
    help='Delete all nodes in unusable state')
@click.option(
    '--nodeid', multiple=True,
    help='NodeId of compute node in pool to delete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_del(
        ctx, all_start_task_failed, all_starting, all_unusable, nodeid):
    """Delete a node or nodes from a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_del(
        ctx.batch_client, ctx.config, all_start_task_failed, all_starting,
        all_unusable, nodeid)


@nodes.command('reboot')
@click.option(
    '--all-start-task-failed',
    is_flag=True,
    help='Reboot all nodes in start task failed state')
@click.option(
    '--nodeid', multiple=True,
    help='NodeId of compute node in pool to reboot')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_reboot(ctx, all_start_task_failed, nodeid):
    """Reboot a node or nodes in a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_reboot(
        ctx.batch_client, ctx.config, all_start_task_failed, nodeid)


@cli.group()
@pass_cli_context
def jobs(ctx):
    """Jobs actions"""
    pass


@jobs.command('add')
@click.option(
    '--recreate', is_flag=True,
    help='Recreate any completed jobs with the same id')
@click.option(
    '--tail',
    help='Tails the specified file of the last job and task added')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_add(ctx, recreate, tail):
    """Add jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.batch_mgmt_client, ctx.batch_client, ctx.blob_client,
        ctx.table_client, ctx.keyvault_client, ctx.config, recreate, tail)


@jobs.command('list')
@click.option(
    '--jobid', help='Get the specified job id')
@click.option(
    '--jobscheduleid', help='Terminate just the specified job schedule id')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_list(ctx, jobid, jobscheduleid):
    """List jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_list(
        ctx.batch_client, ctx.config, jobid, jobscheduleid)


@jobs.command('term')
@click.option(
    '--all-jobs', is_flag=True, help='Terminate all jobs in Batch account')
@click.option(
    '--all-jobschedules', is_flag=True,
    help='Terminate all job schedules in Batch account')
@click.option(
    '--jobid', help='Terminate just the specified job id')
@click.option(
    '--jobscheduleid', help='Terminate just the specified job schedule id')
@click.option(
    '--termtasks', is_flag=True, help='Terminate tasks running in job first')
@click.option(
    '--wait', is_flag=True, help='Wait for jobs termination to complete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_term(
        ctx, all_jobs, all_jobschedules, jobid, jobscheduleid, termtasks,
        wait):
    """Terminate jobs and job schedules"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_del_or_term(
        ctx.batch_client, ctx.blob_client, ctx.table_client, ctx.config,
        False, all_jobs, all_jobschedules, jobid, jobscheduleid, termtasks,
        wait)


@jobs.command('del')
@click.option(
    '--all-jobs', is_flag=True, help='Delete all jobs in Batch account')
@click.option(
    '--all-jobschedules', is_flag=True,
    help='Delete all job schedules in Batch account')
@click.option(
    '--jobid', help='Delete just the specified job id')
@click.option(
    '--jobscheduleid', help='Delete just the specified job schedule id')
@click.option(
    '--termtasks', is_flag=True, help='Terminate tasks running in job first')
@click.option(
    '--wait', is_flag=True, help='Wait for jobs deletion to complete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_del(
        ctx, all_jobs, all_jobschedules, jobid, jobscheduleid, termtasks,
        wait):
    """Delete jobs and job schedules"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_del_or_term(
        ctx.batch_client, ctx.blob_client, ctx.table_client, ctx.config,
        True, all_jobs, all_jobschedules, jobid, jobscheduleid, termtasks,
        wait)


@jobs.command('cmi')
@click.option(
    '--delete', is_flag=True,
    help='Delete all cleanup multi-instance jobs in Batch account')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_cmi(ctx, delete):
    """Cleanup non-native multi-instance jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_cmi(ctx.batch_client, ctx.config, delete)


@jobs.command('migrate')
@click.option(
    '--jobid', help='Migrate only the specified job id')
@click.option(
    '--jobscheduleid', help='Migrate only the specified job schedule id')
@click.option(
    '--poolid', help='Target specified pool id rather than from configuration')
@click.option(
    '--requeue', is_flag=True, help='Requeue running tasks in job')
@click.option(
    '--terminate', is_flag=True, help='Terminate running tasks in job')
@click.option(
    '--wait', is_flag=True, help='Wait for running tasks to complete in job')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_migrate(ctx, jobid, jobscheduleid, poolid, requeue, terminate, wait):
    """Migrate jobs or job schedules to another pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_migrate(
        ctx.batch_client, ctx.config, jobid, jobscheduleid, poolid, requeue,
        terminate, wait)


@jobs.command('disable')
@click.option(
    '--jobid', help='Disable only the specified job id')
@click.option(
    '--jobscheduleid', help='Disable only the specified job schedule id')
@click.option(
    '--requeue', is_flag=True, help='Requeue running tasks in job')
@click.option(
    '--terminate', is_flag=True, help='Terminate running tasks in job')
@click.option(
    '--wait', is_flag=True, help='Wait for running tasks to complete in job')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_disable(ctx, jobid, jobscheduleid, requeue, terminate, wait):
    """Disable jobs and job schedules"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_disable(
        ctx.batch_client, ctx.config, jobid, jobscheduleid, requeue,
        terminate, wait)


@jobs.command('enable')
@click.option(
    '--jobid', help='Enable only the specified job id')
@click.option(
    '--jobscheduleid', help='Enable only the specified job schedule id')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_enable(ctx, jobid, jobscheduleid):
    """Enable jobs and job schedules"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_enable(
        ctx.batch_client, ctx.config, jobid, jobscheduleid)


@jobs.command('stats')
@click.option('--jobid', help='Get stats only on the specified job id')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_stats(ctx, jobid):
    """Get statistics about jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_stats(ctx.batch_client, ctx.config, job_id=jobid)


@jobs.group()
@pass_cli_context
def tasks(ctx):
    """Tasks actions"""
    pass


@tasks.command('list')
@click.option(
    '--all', is_flag=True, help='List tasks in all jobs in account')
@click.option(
    '--jobid', help='List tasks in the specified job id')
@click.option(
    '--poll-until-tasks-complete', is_flag=True,
    help='Poll until all tasks are in completed state')
@click.option(
    '--taskid', help='Get specified task within the specified job id')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def tasks_list(ctx, all, jobid, poll_until_tasks_complete, taskid):
    """List tasks within jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_tasks_list(
        ctx.batch_client, ctx.config, all, jobid,
        poll_until_tasks_complete, taskid)


@tasks.command('count')
@click.option(
    '--jobid', help='List tasks in the specified job id')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def tasks_count(ctx, jobid):
    """Get task counts for a job"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_tasks_count(ctx.batch_client, ctx.config, jobid)


@tasks.command('term')
@click.option(
    '--force', is_flag=True,
    help='Force docker kill signal to task regardless of state')
@click.option(
    '--jobid', help='Terminate tasks in the specified job id')
@click.option(
    '--taskid', help='Terminate tasks in the specified task id')
@click.option(
    '--wait', is_flag=True, help='Wait for task termination to complete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def tasks_term(ctx, force, jobid, taskid, wait):
    """Terminate specified tasks in jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_tasks_term(
        ctx.batch_client, ctx.config, jobid, taskid, wait, force)


@tasks.command('del')
@click.option(
    '--jobid', help='Delete tasks in the specified job id')
@click.option(
    '--taskid', help='Delete tasks in the specified task id')
@click.option(
    '--wait', is_flag=True, help='Wait for task deletion to complete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def tasks_del(ctx, jobid, taskid, wait):
    """Delete specified tasks in jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_tasks_del(
        ctx.batch_client, ctx.config, jobid, taskid, wait)


@cli.group()
@pass_cli_context
def data(ctx):
    """Data actions"""
    pass


@data.command('ingress')
@click.option(
    '--to-fs', help='Ingress data to specified remote filesystem')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def data_ingress(ctx, to_fs):
    """Ingress data into Azure"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_ingress(
        ctx.batch_client, ctx.compute_client, ctx.network_client, ctx.config,
        to_fs)


@data.group()
@pass_cli_context
def files(ctx):
    """Compute node file actions"""
    pass


@files.command('list')
@click.option(
    '--jobid', help='List files from the specified job id')
@click.option(
    '--taskid', help='List files from the specified task id')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def files_list(ctx, jobid, taskid):
    """List files for tasks in jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_files_list(
        ctx.batch_client, ctx.config, jobid, taskid)


@files.command('stream')
@click.option(
    '--disk', is_flag=True,
    help='Write streamed data to disk and suppress console output')
@click.option(
    '--filespec', help='File specification as jobid,taskid,filename')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def files_stream(ctx, disk, filespec):
    """Stream a file as text to the local console or as binary to disk"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_files_stream(
        ctx.batch_client, ctx.config, filespec, disk)


@files.command('task')
@click.option(
    '--all', is_flag=True, help='Retrieve all files for given job/task')
@click.option(
    '--filespec',
    help='File specification as jobid,taskid,filename or '
    'jobid,taskid,include_pattern if invoked with --all')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def files_task(ctx, all, filespec):
    """Retrieve file(s) from a job/task"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_files_task(
        ctx.batch_client, ctx.config, all, filespec)


@files.command('node')
@click.option(
    '--all', is_flag=True, help='Retrieve all files for given compute node')
@click.option(
    '--filespec', help='File specification as nodeid,filename or '
    'nodeid,include_pattern if invoked with --all')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def files_node(ctx, all, filespec):
    """Retrieve file(s) from a compute node"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_files_node(
        ctx.batch_client, ctx.config, all, filespec)


@cli.group()
@pass_cli_context
def diag(ctx):
    """Diagnostics actions"""
    pass


@diag.group()
@pass_cli_context
def logs(ctx):
    """Diagnostic log actions"""
    pass


@logs.command('upload')
@click.option(
    '--cardinal',
    help='Zero-based cardinal number of compute node in pool to egress '
    'service logs from',
    type=int)
@click.option(
    '--generate-sas', is_flag=True,
    help='Generate a read/list SAS token for container')
@click.option(
    '--nodeid', help='NodeId of compute node in to egress service logs from')
@click.option(
    '--wait', is_flag=True, help='Wait for log upload to complete')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def diag_logs_upload(ctx, cardinal, generate_sas, nodeid, wait):
    """Upload Batch Service Logs from compute node"""
    ctx.initialize_for_batch()
    convoy.fleet.action_diag_logs_upload(
        ctx.batch_client, ctx.blob_client, ctx.config, cardinal, nodeid,
        generate_sas, wait)


@cli.group()
@pass_cli_context
def misc(ctx):
    """Miscellaneous actions"""
    pass


@misc.command('tensorboard')
@click.option(
    '--jobid', help='Tensorboard to the specified job id')
@click.option(
    '--taskid', help='Tensorboard to the specified task id')
@click.option(
    '--logdir', help='logdir for Tensorboard')
@click.option(
    '--image',
    help='Use specified TensorFlow Docker image instead. tensorboard.py '
    'must be in the expected location in the Docker image.')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def misc_tensorboard(ctx, jobid, taskid, logdir, image):
    """Create a tunnel to a Tensorboard instance for a specific task"""
    ctx.initialize_for_batch()
    convoy.fleet.action_misc_tensorboard(
        ctx.batch_client, ctx.config, jobid, taskid, logdir, image)


@misc.command('mirror-images')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def misc_mirror(ctx):
    """Mirror Batch Shipyard system images to the specified fallback
    registry"""
    ctx.initialize_for_batch()
    convoy.fleet.action_misc_mirror_images(ctx.batch_client, ctx.config)


@cli.group()
@pass_cli_context
def monitor(ctx):
    """Monitoring actions"""
    pass


@monitor.command('create')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_create(ctx):
    """Create a monitoring resource"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_create(
        ctx.auth_client, ctx.resource_client, ctx.compute_client,
        ctx.network_client, ctx.blob_client, ctx.table_client, ctx.config)


@monitor.command('add')
@click.option(
    '--poolid', multiple=True, help='Add pool to monitor')
@click.option(
    '--remote-fs', multiple=True, help='Add RemoteFS cluster to monitor')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_add(ctx, poolid, remote_fs):
    """Add a resource to monitor"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_add(
        ctx.table_client, ctx.config, poolid, remote_fs)


@monitor.command('list')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_list(ctx):
    """List all monitored resources"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_list(ctx.table_client, ctx.config)


@monitor.command('remove')
@click.option(
    '--all', is_flag=True, help='Remove all resources from monitoring')
@click.option(
    '--poolid', multiple=True, help='Remove a pool from monitoring')
@click.option(
    '--remote-fs', multiple=True,
    help='Remove RemoteFS cluster from monitoring')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_remove(ctx, all, poolid, remote_fs):
    """Remove a resource from monitoring"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_remove(
        ctx.table_client, ctx.config, all, poolid, remote_fs)


@monitor.command('ssh')
@click.option(
    '--tty', is_flag=True, help='Allocate a pseudo-tty')
@common_options
@monitor_options
@click.argument('command', nargs=-1)
@keyvault_options
@aad_options
@pass_cli_context
def monitor_ssh(ctx, tty, command):
    """Interactively login via SSH to monitoring resource virtual
    machine in Azure"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_ssh(
        ctx.compute_client, ctx.network_client, ctx.config, tty, command)


@monitor.command('suspend')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for suspension to complete')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_suspend(ctx, no_wait):
    """Suspend a monitoring resource"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_suspend(
        ctx.compute_client, ctx.config, not no_wait)


@monitor.command('start')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for restart to complete')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_start(ctx, no_wait):
    """Starts a previously suspended monitoring resource"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_start(
        ctx.compute_client, ctx.config, not no_wait)


@monitor.command('status')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_status(ctx):
    """Query status of a monitoring resource"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_status(
        ctx.compute_client, ctx.network_client, ctx.config)


@monitor.command('destroy')
@click.option(
    '--delete-resource-group', is_flag=True,
    help='Delete all resources in the monitoring resource group')
@click.option(
    '--delete-virtual-network', is_flag=True, help='Delete virtual network')
@click.option(
    '--generate-from-prefix', is_flag=True,
    help='Generate resources to delete from monitoring hostname prefix')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for deletion to complete')
@common_options
@monitor_options
@keyvault_options
@aad_options
@pass_cli_context
def monitor_destroy(
        ctx, delete_resource_group, delete_virtual_network,
        generate_from_prefix, no_wait):
    """Destroy a monitoring resource"""
    ctx.initialize_for_monitor()
    convoy.fleet.action_monitor_destroy(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.table_client, ctx.config, delete_resource_group,
        delete_virtual_network, generate_from_prefix, not no_wait)


@cli.group()
@pass_cli_context
def fed(ctx):
    """Federation actions"""
    pass


@fed.group()
@pass_cli_context
def proxy(ctx):
    """Federation proxy actions"""
    pass


@proxy.command('create')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_proxy_create(ctx):
    """Create a federation proxy"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_proxy_create(
        ctx.auth_client, ctx.resource_client, ctx.compute_client,
        ctx.network_client, ctx.blob_client, ctx.table_client,
        ctx.queue_client, ctx.config)


@proxy.command('ssh')
@click.option(
    '--tty', is_flag=True, help='Allocate a pseudo-tty')
@common_options
@federation_options
@click.argument('command', nargs=-1)
@keyvault_options
@aad_options
@pass_cli_context
def fed_proxy_ssh(ctx, tty, command):
    """Interactively login via SSH to federation proxy virtual
    machine in Azure"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_proxy_ssh(
        ctx.compute_client, ctx.network_client, ctx.config, tty, command)


@proxy.command('suspend')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for suspension to complete')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_proxy_suspend(ctx, no_wait):
    """Suspend a federation proxy"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_proxy_suspend(
        ctx.compute_client, ctx.config, not no_wait)


@proxy.command('start')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for restart to complete')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_proxy_start(ctx, no_wait):
    """Starts a previously suspended federation proxy"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_proxy_start(
        ctx.compute_client, ctx.config, not no_wait)


@proxy.command('status')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_proxy_status(ctx):
    """Query status of a federation proxy"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_proxy_status(
        ctx.compute_client, ctx.network_client, ctx.config)


@proxy.command('destroy')
@click.option(
    '--delete-resource-group', is_flag=True,
    help='Delete all resources in the federation resource group')
@click.option(
    '--delete-virtual-network', is_flag=True, help='Delete virtual network')
@click.option(
    '--generate-from-prefix', is_flag=True,
    help='Generate resources to delete from federation hostname prefix')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for deletion to complete')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_proxy_destroy(
        ctx, delete_resource_group, delete_virtual_network,
        generate_from_prefix, no_wait):
    """Destroy a federation proxy"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_proxy_destroy(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.table_client, ctx.queue_client, ctx.config,
        delete_resource_group, delete_virtual_network, generate_from_prefix,
        not no_wait)


@fed.command('create')
@click.argument('federation-id')
@click.option(
    '--force', is_flag=True,
    help='Force creation of the federation even if it exists')
@click.option(
    '--no-unique-job-ids', is_flag=True,
    help='Allow non-unique job ids to be submitted')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_create(ctx, federation_id, force, no_unique_job_ids):
    """Create a federation"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_create(
        ctx.blob_client, ctx.table_client, ctx.queue_client, ctx.config,
        federation_id, force, not no_unique_job_ids)


@fed.command('list')
@click.option(
    '--federation-id', multiple=True, help='Limit to specified federation id')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_list(ctx, federation_id):
    """List all federations"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_list(
        ctx.table_client, ctx.config, federation_id)


@fed.command('destroy')
@click.argument('federation-id')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_destroy(ctx, federation_id):
    """Destroy a federation"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_destroy(
        ctx.blob_client, ctx.table_client, ctx.queue_client, ctx.config,
        federation_id)


@fed.group()
@pass_cli_context
def pool(ctx):
    """Federation pool actions"""
    pass


@pool.command('add')
@click.argument('federation-id')
@click.option(
    '--batch-service-url',
    help='Associate specified pools with batch service url')
@click.option(
    '--pool-id', multiple=True, help='Add pool to federation')
@common_options
@batch_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_pool_add(ctx, federation_id, batch_service_url, pool_id):
    """Add a pool to a federation"""
    init_batch = convoy.util.is_none_or_empty(batch_service_url)
    ctx.initialize_for_federation(init_batch=init_batch)
    convoy.fleet.action_fed_pool_add(
        ctx.batch_client, ctx.table_client, ctx.config, federation_id,
        batch_service_url, pool_id)


@pool.command('remove')
@click.argument('federation-id')
@click.option(
    '--all', is_flag=True, help='Remove all pools from federation')
@click.option(
    '--batch-service-url',
    help='Associate specified pools with batch service url')
@click.option(
    '--pool-id', multiple=True, help='Remove pool from federation')
@common_options
@batch_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_pool_remove(ctx, federation_id, all, batch_service_url, pool_id):
    """Remove a pool from a federation"""
    init_batch = convoy.util.is_none_or_empty(batch_service_url)
    ctx.initialize_for_federation(init_batch=init_batch)
    convoy.fleet.action_fed_pool_remove(
        ctx.batch_client, ctx.table_client, ctx.config, federation_id, all,
        batch_service_url, pool_id)


@fed.group()
@pass_cli_context
def jobs(ctx):
    """Federation jobs actions"""
    pass


@jobs.command('add')
@click.argument('federation-id')
@common_options
@batch_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_jobs_add(ctx, federation_id):
    """Add jobs or job schedules to a federation"""
    ctx.initialize_for_federation(init_batch=True)
    convoy.fleet.action_fed_jobs_add(
        ctx.batch_client, ctx.keyvault_client, ctx.blob_client,
        ctx.table_client, ctx.queue_client, ctx.config, federation_id)


@jobs.command('list')
@click.argument('federation-id')
@click.option(
    '--blocked', is_flag=True, help='List blocked actions')
@click.option(
    '--job-id', help='List the specified job id')
@click.option(
    '--jobschedule-id', help='List the specified job schedule id')
@click.option(
    '--queued', is_flag=True, help='List queued actions')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_jobs_list(ctx, blocked, federation_id, job_id, jobschedule_id, queued):
    """List jobs or job schedules in a federation"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_jobs_list(
        ctx.table_client, ctx.config, federation_id, job_id, jobschedule_id,
        blocked, queued)


@jobs.command('term')
@click.argument('federation-id')
@click.option(
    '--all-jobs', is_flag=True, help='Terminate all jobs in federation')
@click.option(
    '--all-jobschedules', is_flag=True,
    help='Terminate all job schedules in federation')
@click.option(
    '--force', is_flag=True,
    help='Force termination even if jobs do not exist')
@click.option(
    '--job-id', multiple=True, help='Terminate the specified job id')
@click.option(
    '--jobschedule-id', multiple=True,
    help='Terminate the specified job schedule id')
@common_options
@batch_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_jobs_term(
        ctx, federation_id, all_jobs, all_jobschedules, force, job_id,
        jobschedule_id):
    """Terminate a job or job schedule in a federation"""
    ctx.initialize_for_federation(init_batch=True)
    convoy.fleet.action_fed_jobs_del_or_term(
        ctx.blob_client, ctx.table_client, ctx.queue_client, ctx.config,
        False, federation_id, job_id, jobschedule_id, all_jobs,
        all_jobschedules, force)


@jobs.command('del')
@click.argument('federation-id')
@click.option(
    '--all-jobs', is_flag=True, help='Delete all jobs in federation')
@click.option(
    '--all-jobschedules', is_flag=True,
    help='Delete all job schedules in federation')
@click.option(
    '--job-id', multiple=True, help='Delete the specified job id')
@click.option(
    '--jobschedule-id', multiple=True,
    help='Delete the specified job schedule id')
@common_options
@batch_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_jobs_del(
        ctx, federation_id, all_jobs, all_jobschedules, job_id,
        jobschedule_id):
    """Delete a job or job schedule in a federation"""
    ctx.initialize_for_federation(init_batch=True)
    convoy.fleet.action_fed_jobs_del_or_term(
        ctx.blob_client, ctx.table_client, ctx.queue_client, ctx.config,
        True, federation_id, job_id, jobschedule_id, all_jobs,
        all_jobschedules, False)


@jobs.command('zap')
@click.argument('federation-id')
@click.option(
    '--unique-id', help='Zap the specified queued unique id')
@common_options
@federation_options
@keyvault_options
@aad_options
@pass_cli_context
def fed_jobs_zap(
        ctx, federation_id, unique_id):
    """Zap a queued unique id from a federation"""
    ctx.initialize_for_federation()
    convoy.fleet.action_fed_jobs_zap(
        ctx.blob_client, ctx.config, federation_id, unique_id)


@cli.group()
@pass_cli_context
def slurm(ctx):
    """Slurm on Batch actions"""
    pass


@slurm.group()
@pass_cli_context
def ssh(ctx):
    """Slurm SSH actions"""
    pass


@ssh.command('controller')
@click.option(
    '--offset', help='Controller VM offset')
@click.option(
    '--tty', is_flag=True, help='Allocate a pseudo-tty')
@common_options
@slurm_options
@click.argument('command', nargs=-1)
@keyvault_options
@aad_options
@pass_cli_context
def slurm_ssh_controller(ctx, offset, tty, command):
    """Interactively login via SSH to a Slurm controller virtual
    machine in Azure"""
    ctx.initialize_for_slurm()
    convoy.fleet.action_slurm_ssh(
        ctx.compute_client, ctx.network_client, None, None, ctx.config,
        tty, command, 'controller', offset, None)


@ssh.command('login')
@click.option(
    '--offset', help='Controller VM offset')
@click.option(
    '--tty', is_flag=True, help='Allocate a pseudo-tty')
@common_options
@slurm_options
@click.argument('command', nargs=-1)
@keyvault_options
@aad_options
@pass_cli_context
def slurm_ssh_login(ctx, offset, tty, command):
    """Interactively login via SSH to a Slurm login/gateway virtual
    machine in Azure"""
    ctx.initialize_for_slurm()
    convoy.fleet.action_slurm_ssh(
        ctx.compute_client, ctx.network_client, None, None, ctx.config,
        tty, command, 'login', offset, None)


@ssh.command('node')
@click.option(
    '--node-name', help='Slurm node name')
@click.option(
    '--tty', is_flag=True, help='Allocate a pseudo-tty')
@common_options
@slurm_options
@click.argument('command', nargs=-1)
@keyvault_options
@aad_options
@pass_cli_context
def slurm_ssh_node(ctx, node_name, tty, command):
    """Interactively login via SSH to a Slurm compute node virtual
    machine in Azure"""
    ctx.initialize_for_slurm(init_batch=True)
    if convoy.util.is_none_or_empty(node_name):
        raise ValueError('node name must be specified')
    convoy.fleet.action_slurm_ssh(
        ctx.compute_client, ctx.network_client, ctx.table_client,
        ctx.batch_client, ctx.config, tty, command, 'node', None, node_name)


@slurm.group()
@pass_cli_context
def cluster(ctx):
    """Slurm cluster actions"""
    pass


@cluster.command('create')
@common_options
@slurm_options
@keyvault_options
@aad_options
@pass_cli_context
def slurm_cluster_create(ctx):
    """Create a Slurm cluster with controllers and login nodes"""
    ctx.initialize_for_slurm(init_batch=True)
    convoy.fleet.action_slurm_cluster_create(
        ctx.auth_client, ctx.resource_client, ctx.compute_client,
        ctx.network_client, ctx.blob_client, ctx.table_client,
        ctx.queue_client, ctx.batch_client, ctx.config)


@cluster.command('orchestrate')
@click.option(
    '--storage-cluster-id', help='Storage cluster id to create')
@common_options
@slurm_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def slurm_cluster_orchestrate(ctx, storage_cluster_id):
    """Orchestrate a Slurm cluster with shared file system and Batch pool"""
    if convoy.util.is_not_empty(storage_cluster_id):
        ctx.cleanup = False
        ctx.initialize_for_fs()
        convoy.fleet.action_fs_disks_add(
            ctx.resource_client, ctx.compute_client, ctx.config)
        convoy.fleet.action_fs_cluster_add(
            ctx.resource_client, ctx.compute_client, ctx.network_client,
            ctx.blob_client, ctx.config, storage_cluster_id)
        ctx.cleanup = True
    else:
        logger.warning(
            'skipping fs cluster orchestration as no storage cluster id '
            'was specified')
    ctx.initialize_for_slurm(init_batch=True)
    convoy.fleet.action_pool_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.batch_mgmt_client, ctx.batch_client, ctx.blob_client,
        ctx.table_client, ctx.keyvault_client, ctx.config, False, False)
    convoy.fleet.action_slurm_cluster_create(
        ctx.auth_client, ctx.resource_client, ctx.compute_client,
        ctx.network_client, ctx.blob_client, ctx.table_client,
        ctx.queue_client, ctx.batch_client, ctx.config)


@cluster.command('suspend')
@click.option(
    '--no-controller-nodes', is_flag=True,
    help='Do not suspend controller nodes')
@click.option(
    '--no-login-nodes', is_flag=True, help='Do not suspend login nodes')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for suspension to complete')
@common_options
@slurm_options
@keyvault_options
@aad_options
@pass_cli_context
def slurm_cluster_suspend(ctx, no_controller_nodes, no_login_nodes, no_wait):
    """Suspend a Slurm cluster contoller and/or login nodes"""
    ctx.initialize_for_slurm()
    convoy.fleet.action_slurm_cluster_suspend(
        ctx.compute_client, ctx.config, not no_controller_nodes,
        not no_login_nodes, not no_wait)


@cluster.command('start')
@click.option(
    '--no-controller-nodes', is_flag=True,
    help='Do not start controller nodes')
@click.option(
    '--no-login-nodes', is_flag=True, help='Do not start login nodes')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for restart to complete')
@common_options
@slurm_options
@keyvault_options
@aad_options
@pass_cli_context
def slurm_cluster_start(ctx, no_controller_nodes, no_login_nodes, no_wait):
    """Starts a previously suspended Slurm cluster"""
    ctx.initialize_for_slurm()
    convoy.fleet.action_slurm_cluster_start(
        ctx.compute_client, ctx.config, not no_controller_nodes,
        not no_login_nodes, not no_wait)


@cluster.command('status')
@common_options
@slurm_options
@keyvault_options
@aad_options
@pass_cli_context
def slurm_cluster_status(ctx):
    """Query status of a Slurm controllers and login nodes"""
    ctx.initialize_for_slurm()
    convoy.fleet.action_slurm_cluster_status(
        ctx.compute_client, ctx.network_client, ctx.config)


@cluster.command('destroy')
@click.option(
    '--delete-resource-group', is_flag=True,
    help='Delete all resources in the Slurm controller resource group')
@click.option(
    '--delete-virtual-network', is_flag=True, help='Delete virtual network')
@click.option(
    '--generate-from-prefix', is_flag=True,
    help='Generate resources to delete from Slurm controller hostname prefix')
@click.option(
    '--no-wait', is_flag=True, help='Do not wait for deletion to complete')
@common_options
@slurm_options
@keyvault_options
@aad_options
@pass_cli_context
def slurm_cluster_destroy(
        ctx, delete_resource_group, delete_virtual_network,
        generate_from_prefix, no_wait):
    """Destroy a Slurm controller"""
    ctx.initialize_for_slurm(init_batch=True)
    convoy.fleet.action_slurm_cluster_destroy(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.table_client, ctx.queue_client, ctx.config,
        delete_resource_group, delete_virtual_network, generate_from_prefix,
        not no_wait)


if __name__ == '__main__':
    convoy.util.setup_logger(logger)
    cli()
