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
        self.show_config = False
        self.verbose = False
        self.yes = False
        self.config = None
        self.conf_jobs = None
        self.conf_fs = None
        # clients
        self.batch_mgmt_client = None
        self.batch_client = None
        self.blob_client = None
        self.table_client = None
        self.keyvault_client = None
        self.resource_client = None
        self.compute_client = None
        self.network_client = None
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

    def initialize_for_fs(self):
        # type: (CliContext) -> None
        """Initialize context for fs commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        try:
            self.keyvault_client = convoy.clients.create_keyvault_client(self)
        except KeyError:
            logger.error(
                'Are you missing your configuration files or pointing to '
                'the wrong location?')
            raise
        self._init_config(
            skip_global_config=False, skip_pool_config=True, fs_storage=True)
        self.resource_client, self.compute_client, self.network_client, \
            _, _ = convoy.clients.create_arm_clients(self)
        self.blob_client, _ = convoy.clients.create_storage_clients()
        self._cleanup_after_initialize(
            skip_global_config=False, skip_pool_config=True)

    def initialize_for_keyvault(self):
        # type: (CliContext) -> None
        """Initialize context for keyvault commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        try:
            self.keyvault_client = convoy.clients.create_keyvault_client(self)
        except KeyError:
            logger.error(
                'Are you missing your configuration files or pointing to '
                'the wrong location?')
            raise
        self._init_config(
            skip_global_config=True, skip_pool_config=True, fs_storage=False)
        self._cleanup_after_initialize(
            skip_global_config=True, skip_pool_config=True)

    def initialize_for_batch(self):
        # type: (CliContext) -> None
        """Initialize context for batch commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        try:
            self.keyvault_client = convoy.clients.create_keyvault_client(self)
        except KeyError:
            logger.error(
                'Are you missing your configuration files or pointing to '
                'the wrong location?')
            raise
        self._init_config(
            skip_global_config=False, skip_pool_config=False, fs_storage=False)
        self.resource_client, self.compute_client, self.network_client, \
            self.batch_mgmt_client, self.batch_client = \
            convoy.clients.create_arm_clients(self, batch_clients=True)
        self.blob_client, self.table_client = \
            convoy.clients.create_storage_clients()
        self._cleanup_after_initialize(
            skip_global_config=False, skip_pool_config=False)

    def initialize_for_storage(self):
        # type: (CliContext) -> None
        """Initialize context for storage commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self._set_global_cli_options()
        self.keyvault_client = convoy.clients.create_keyvault_client(self)
        self._init_config(
            skip_global_config=False, skip_pool_config=False, fs_storage=False)
        self.blob_client, self.table_client = \
            convoy.clients.create_storage_clients()
        self._cleanup_after_initialize(
            skip_global_config=False, skip_pool_config=False)

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
        # increase detail in logger formatters
        if self.verbose:
            convoy.util.set_verbose_logger_handlers()

    def _cleanup_after_initialize(
            self, skip_global_config, skip_pool_config):
        # type: (CliContext) -> None
        """Cleanup after initialize_for_* funcs
        :param CliContext self: this
        :param bool skip_global_config: skip global config
        :param bool skip_pool_config: skip pool config
        """
        # free conf objects
        del self.conf_credentials
        del self.conf_fs
        if not skip_global_config:
            del self.conf_config
        if not skip_pool_config:
            del self.conf_pool
            del self.conf_jobs
        # free cli options
        del self.verbose
        del self.yes
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
            fs_storage=False):
        # type: (CliContext, bool, bool, bool) -> None
        """Initializes configuration of the context
        :param CliContext self: this
        :param bool skip_global_config: skip global config
        :param bool skip_pool_config: skip pool config
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


@click.group(context_settings=_CONTEXT_SETTINGS)
@click.version_option(version=convoy.__version__)
@click.pass_context
def cli(ctx):
    """Batch Shipyard: Provision and execute container workloads on
    Azure Batch"""
    pass


@cli.group()
@pass_cli_context
def account(ctx):
    """Batch account actions"""
    pass


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
@aad_options
@pass_cli_context
def fs_cluster_add(ctx, storage_cluster_id):
    """Create a filesystem storage cluster in Azure"""
    ctx.initialize_for_fs()
    convoy.fleet.action_fs_cluster_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.config, storage_cluster_id)


@cluster.command('resize')
@common_options
@fs_cluster_options
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
    '--poolid', help='Delete storage containers for the specified pool')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def storage_del(ctx, clear_tables, poolid):
    """Delete Azure Storage containers used by Batch Shipyard"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_del(
        ctx.blob_client, ctx.table_client, ctx.config, clear_tables, poolid)


@storage.command('clear')
@click.option(
    '--poolid', help='Clear storage containers for the specified pool')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def storage_clear(ctx, poolid):
    """Clear Azure Storage containers used by Batch Shipyard"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_clear(
        ctx.blob_client, ctx.table_client, ctx.config, poolid)


@storage.group()
@pass_cli_context
def sas(ctx):
    """SAS key actions"""
    pass


@sas.command('create')
@click.option(
    '--create', is_flag=True, help='Create permission')
@click.option(
    '--delete', is_flag=True, help='Delete permission')
@click.option(
    '--file', is_flag=True, help='Create file SAS instead of blob SAS')
@click.option(
    '--read', is_flag=True, help='Read permission')
@click.option(
    '--write', is_flag=True, help='Write permission')
@click.argument('storage-account')
@click.argument('path')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def sas_create(ctx, create, delete, file, read, write, storage_account, path):
    """Create an object-level SAS key"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_sas_create(
        ctx.config, storage_account, path, file, create, read, write, delete)


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
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_create(ctx):
    """Create a certificate to use with a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_create(ctx.config)


@cert.command('add')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_add(ctx):
    """Add a certificate to a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_add(ctx.batch_client, ctx.config)


@cert.command('list')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_list(ctx):
    """List all certificates in a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_list(ctx.batch_client)


@cert.command('del')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def cert_del(ctx):
    """Delete a certificate from a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_del(ctx.batch_client, ctx.config)


@cli.group()
@pass_cli_context
def pool(ctx):
    """Pool actions"""
    pass


@pool.command('listskus')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_listskus(ctx):
    """List available VM configurations available to the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_listskus(ctx.batch_client)


@pool.command('add')
@common_options
@fs_option
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_add(ctx):
    """Add a pool to the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.batch_mgmt_client, ctx.batch_client, ctx.blob_client,
        ctx.table_client, ctx.config)


@pool.command('list')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def pool_list(ctx):
    """List all pools in the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_list(ctx.batch_client)


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
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_grls(ctx):
    """Get remote login settings for all nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_grls(ctx.batch_client, ctx.config)


@nodes.command('list')
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def nodes_list(ctx):
    """List nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_nodes_list(ctx.batch_client, ctx.config)


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
    """Delete a node from a pool"""
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
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def jobs_list(ctx):
    """List jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_list(ctx.batch_client, ctx.config)


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
@common_options
@batch_options
@keyvault_options
@aad_options
@pass_cli_context
def tasks_list(ctx, all, jobid, poll_until_tasks_complete):
    """List tasks within jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_tasks_list(
        ctx.batch_client, ctx.config, all, jobid,
        poll_until_tasks_complete)


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


if __name__ == '__main__':
    convoy.util.setup_logger(logger)
    cli()
