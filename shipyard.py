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
# local imports
import convoy.fleet
import convoy.settings
import convoy.util

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
        self.batch_client = None
        self.blob_client = None
        self.queue_client = None
        self.table_client = None
        self.keyvault_client = None
        self.resource_client = None
        self.compute_client = None
        self.network_client = None
        # aad/keyvault options
        self.keyvault_uri = None
        self.keyvault_credentials_secret_id = None
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

    def initialize_for_remotefs(self):
        # type: (CliContext) -> None
        """Initialize context for remotefs commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self.resource_client, self.compute_client, self.network_client = \
            convoy.fleet.create_remotefs_clients(self, self.config)
        self._cleanup_during_initialize()
        self._init_config(
            skip_global_config=False, skip_pool_config=True,
            skip_remotefs_config=False)
        clients = convoy.fleet.initialize(self.config, remotefs_context=True)
        self._set_clients(*clients)

    def initialize_for_storage(self):
        # type: (CliContext) -> None
        """Initialize context for storage commands
        :param CliContext self: this
        """
        # path is identical to batch
        self.initialize_for_batch()

    def initialize_for_keyvault(self):
        # type: (CliContext) -> None
        """Initialize context for keyvault commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self.keyvault_client = convoy.fleet.create_keyvault_client(
            self, self.config)
        self._cleanup_during_initialize()
        self._init_config(
            skip_global_config=True, skip_pool_config=True,
            skip_remotefs_config=True)

    def initialize_for_batch(self):
        # type: (CliContext) -> None
        """Initialize context for batch commands
        :param CliContext self: this
        """
        self._read_credentials_config()
        self.keyvault_client = convoy.fleet.create_keyvault_client(
            self, self.config)
        self._cleanup_during_initialize()
        self._init_config(
            skip_global_config=False, skip_pool_config=False,
            skip_remotefs_config=True)
        clients = convoy.fleet.initialize(self.config)
        self._set_clients(*clients)

    def _cleanup_during_initialize(self):
        # type: (CliContext) -> None
        """Cleanup and free memory during initialize_for_* funcs
        :param CliContext self: this
        """
        del self.aad_directory_id
        del self.aad_application_id
        del self.aad_auth_key
        del self.aad_user
        del self.aad_password
        del self.aad_cert_private_key
        del self.aad_cert_thumbprint
        del self.aad_endpoint
        del self.subscription_id
        self.config = None

    def _read_json_file(self, json_file):
        # type: (CliContext, pathlib.Path) -> None
        """Read a json file into self.config, while checking for invalid
        JSON and returning an error that makes sense if ValueError
        :param CliContext self: this
        :param pathlib.Path json_file: json file to load
        """
        try:
            with json_file.open('r') as f:
                if self.config is None:
                    self.config = json.load(f)
                else:
                    self.config = convoy.util.merge_dict(
                        self.config, json.load(f))
        except ValueError:
            raise ValueError(
                ('Detected invalid JSON in file: {}. Please ensure the JSON '
                 'is valid and is encoded UTF-8 without BOM.'.format(
                     json_file)))

    def _read_credentials_config(self):
        # type: (CliContext) -> None
        """Read credentials config file only
        :param CliContext self: this
        """
        # use configdir if available
        if self.configdir is not None and self.json_credentials is None:
            self.json_credentials = pathlib.Path(
                self.configdir, 'credentials.json')
        if (self.json_credentials is not None and
                not isinstance(self.json_credentials, pathlib.Path)):
            self.json_credentials = pathlib.Path(self.json_credentials)
        if self.json_credentials.exists():
            self._read_json_file(self.json_credentials)

    def _init_config(
            self, skip_global_config=False, skip_pool_config=False,
            skip_remotefs_config=False):
        # type: (CliContext, bool, bool, bool) -> None
        """Initializes configuration of the context
        :param CliContext self: this
        :param bool skip_global_config: skip global config
        :param bool skip_pool_config: skip pool config
        :param bool skip_remotefs_config: skip remote fs config
        """
        # use configdir if available
        if self.configdir is not None:
            if self.json_credentials is None:
                self.json_credentials = pathlib.Path(
                    self.configdir, 'credentials.json')
            if not skip_global_config and self.json_config is None:
                self.json_config = pathlib.Path(
                    self.configdir, 'config.json')
            if not skip_pool_config:
                if self.json_pool is None:
                    self.json_pool = pathlib.Path(self.configdir, 'pool.json')
                if self.json_jobs is None:
                    self.json_jobs = pathlib.Path(self.configdir, 'jobs.json')
            if not skip_remotefs_config:
                if self.json_remotefs is None:
                    self.json_remotefs = pathlib.Path(
                        self.configdir, 'remotefs.json')
        # check for required json files
        if (self.json_credentials is not None and
                not isinstance(self.json_credentials, pathlib.Path)):
            self.json_credentials = pathlib.Path(self.json_credentials)
        if not skip_global_config:
            if self.json_config is None:
                raise ValueError('config json was not specified')
            elif not isinstance(self.json_config, pathlib.Path):
                self.json_config = pathlib.Path(self.json_config)
        if not skip_pool_config:
            if self.json_pool is None:
                raise ValueError('pool json was not specified')
            elif not isinstance(self.json_pool, pathlib.Path):
                self.json_pool = pathlib.Path(self.json_pool)
        if not skip_remotefs_config:
            if self.json_remotefs is None:
                raise ValueError('remotefs json was not specified')
            elif not isinstance(self.json_remotefs, pathlib.Path):
                self.json_remotefs = pathlib.Path(self.json_remotefs)
        # fetch credentials from keyvault, if json file is missing
        kvcreds = None
        if self.json_credentials is None or not self.json_credentials.exists():
            kvcreds = convoy.fleet.fetch_credentials_json_from_keyvault(
                self.keyvault_client, self.keyvault_uri,
                self.keyvault_credentials_secret_id)
        # read credentials json, perform special keyvault processing if
        # required sections are missing
        if kvcreds is None:
            self._read_json_file(self.json_credentials)
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
        if not skip_global_config:
            self._read_json_file(self.json_config)
        if not skip_remotefs_config:
            self._read_json_file(self.json_remotefs)
        if not skip_pool_config:
            self._read_json_file(self.json_pool)
            if self.json_jobs is not None:
                if not isinstance(self.json_jobs, pathlib.Path):
                    self.json_jobs = pathlib.Path(self.json_jobs)
                if self.json_jobs.exists():
                    self._read_json_file(self.json_jobs)
        # set internal config kv pairs
        self.config['_verbose'] = self.verbose
        self.config['_auto_confirm'] = self.yes
        if self.show_config:
            logger.debug('config:\n' + json.dumps(self.config, indent=4))
        # free mem
        del self.json_credentials
        if not skip_global_config:
            del self.json_config
        if not skip_pool_config:
            del self.json_pool
            del self.json_jobs
        del self.verbose
        del self.yes

    def _set_clients(
            self, batch_client, blob_client, queue_client, table_client):
        """Sets clients for the context"""
        self.batch_client = batch_client
        self.blob_client = blob_client
        self.queue_client = queue_client
        self.table_client = table_client


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


def _azure_management_subscription_id_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.subscription_id = value
        return value
    return click.option(
        '--management-subscription-id',
        expose_value=False,
        envvar='SHIPYARD_MANAGEMENT_SUBSCRIPTION_ID',
        help='Azure Management Subscription Id',
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
        'found. Each json config file must be named exactly the same as the '
        'regular switch option, e.g., pool.json for --pool. Individually '
        'specified config options take precedence over this option.',
        callback=callback)(f)


def _credentials_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_credentials = value
        return value
    return click.option(
        '--credentials',
        expose_value=False,
        envvar='SHIPYARD_CREDENTIALS_JSON',
        help='Credentials json config file',
        callback=callback)(f)


def _config_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_config = value
        return value
    return click.option(
        '--config',
        expose_value=False,
        envvar='SHIPYARD_CONFIG_JSON',
        help='Global json config file',
        callback=callback)(f)


def _pool_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_pool = value
        return value
    return click.option(
        '--pool',
        expose_value=False,
        envvar='SHIPYARD_POOL_JSON',
        help='Pool json config file',
        callback=callback)(f)


def _jobs_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_jobs = value
        return value
    return click.option(
        '--jobs',
        expose_value=False,
        envvar='SHIPYARD_JOBS_JSON',
        help='Jobs json config file',
        callback=callback)(f)


def _remotefs_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_remotefs = value
        return value
    return click.option(
        '--remotefs',
        expose_value=False,
        envvar='SHIPYARD_REMOTEFS_JSON',
        help='RemoteFS json config file',
        callback=callback)(f)


def common_options(f):
    f = _config_option(f)
    f = _credentials_option(f)
    f = _configdir_option(f)
    f = _verbose_option(f)
    f = _show_config_option(f)
    f = _confirm_option(f)
    return f


def aad_options(f):
    f = _aad_cert_thumbprint_option(f)
    f = _aad_cert_private_key_option(f)
    f = _aad_password_option(f)
    f = _aad_user_option(f)
    f = _aad_auth_key_option(f)
    f = _aad_application_id_option(f)
    f = _aad_directory_id_option(f)
    f = _aad_endpoint_option(f)
    return f


def batch_options(f):
    f = _jobs_option(f)
    f = _pool_option(f)
    return f


def keyvault_options(f):
    f = aad_options(f)
    f = _azure_keyvault_credentials_secret_id_option(f)
    f = _azure_keyvault_uri_option(f)
    return f


def remotefs_options(f):
    f = aad_options(f)
    f = _azure_management_subscription_id_option(f)
    f = _remotefs_option(f)
    return f


@click.group(context_settings=_CONTEXT_SETTINGS)
@click.version_option(version=convoy.__version__)
@click.pass_context
def cli(ctx):
    """Batch Shipyard: Provision and Execute Docker Workloads on Azure Batch"""
    pass


@cli.group()
@pass_cli_context
def remotefs(ctx):
    """Remote Filesystem actions"""
    pass


@remotefs.group()
@pass_cli_context
def cluster(ctx):
    """Storage cluster actions"""
    pass


@cluster.command('add')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_add(ctx):
    """Create a storage cluster for a Remote Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_cluster_add(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.config)


@cluster.command('del')
@click.option(
    '--delete-all-resources', is_flag=True,
    help='Delete all resources used by storage cluster via resource group')
@click.option(
    '--delete-data-disks', is_flag=True,
    help='Delete all attached managed data disks')
@click.option(
    '--delete-virtual-network', is_flag=True, help='Delete virtual network')
@click.option(
    '--wait', is_flag=True, help='Wait for deletion to complete')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_del(
        ctx, delete_all_resources, delete_data_disks, delete_virtual_network,
        wait):
    """Delete a storage cluster used for a Remote Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_cluster_del(
        ctx.resource_client, ctx.compute_client, ctx.network_client,
        ctx.blob_client, ctx.config, delete_all_resources, delete_data_disks,
        delete_virtual_network, wait)


@cluster.command('expand')
@click.option(
    '--rebalance', is_flag=True, help='Rebalance filesystem, if applicable')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_expand(ctx, rebalance):
    """Expand a storage cluster used for a Remote Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_cluster_expand(
        ctx.compute_client, ctx.network_client, ctx.config, rebalance)


@cluster.command('suspend')
@click.option(
    '--wait', is_flag=True, help='Wait for suspension to complete')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_suspend(ctx, wait):
    """Suspend a storage cluster used for a Remote Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_cluster_suspend(
        ctx.compute_client, ctx.config, wait)


@cluster.command('start')
@click.option(
    '--wait', is_flag=True, help='Wait for restart to complete')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_start(ctx, wait):
    """Starts a previously suspended storage cluster used for a Remote
    Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_cluster_start(
        ctx.compute_client, ctx.network_client, ctx.config, wait)


@cluster.command('status')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_status(ctx):
    """Query status of a storage cluster used for a Remote
    Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_cluster_status(
        ctx.compute_client, ctx.network_client, ctx.config)


@cluster.command('ssh')
@click.option(
    '--cardinal',
    help='Zero-based cardinal number of remote fs vm to connect to',
    type=int)
@click.option(
    '--hostname', help='Hostname of remote fs vm to connect to')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_ssh(ctx, cardinal, hostname):
    """Interactively login via SSH to a virtual machine in the Remote
    Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_cluster_ssh(
        ctx.compute_client, ctx.network_client, ctx.config, cardinal, hostname)


@remotefs.group()
@pass_cli_context
def disks(ctx):
    """Managed disk actions"""
    pass


@disks.command('add')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_disks_add(ctx):
    """Create managed disks for Remote Filesystem in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_disks_add(
        ctx.resource_client, ctx.compute_client, ctx.config)


@disks.command('del')
@click.option(
    '--name', help='Delete disk with specified name only')
@click.option(
    '--wait', is_flag=True, help='Wait for disk deletion to complete')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_disks_del(ctx, name, wait):
    """Delete managed disks in Azure"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_disks_del(
        ctx.compute_client, ctx.config, name, wait)


@disks.command('list')
@click.option(
    '--restrict-scope', is_flag=True,
    help='List disks present only in configuration if they exist')
@common_options
@remotefs_options
@pass_cli_context
def remotefs_disks_list(ctx, restrict_scope):
    """List managed disks in resource group"""
    ctx.initialize_for_remotefs()
    convoy.fleet.action_remotefs_disks_list(
        ctx.compute_client, ctx.config, restrict_scope)


@cli.group()
@pass_cli_context
def storage(ctx):
    """Storage actions"""
    pass


@storage.command('del')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def storage_del(ctx):
    """Delete Azure Storage containers used by Batch Shipyard"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_del(
        ctx.blob_client, ctx.queue_client, ctx.table_client, ctx.config)


@storage.command('clear')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def storage_clear(ctx):
    """Clear Azure Storage containers used by Batch Shipyard"""
    ctx.initialize_for_storage()
    convoy.fleet.action_storage_clear(
        ctx.blob_client, ctx.queue_client, ctx.table_client, ctx.config)


@cli.group()
@pass_cli_context
def keyvault(ctx):
    """KeyVault actions"""
    pass


@keyvault.command('add')
@click.argument('name')
@common_options
@keyvault_options
@pass_cli_context
def keyvault_add(ctx, name):
    """Add a credentials json as a secret to Azure KeyVault"""
    ctx.initialize_for_keyvault()
    convoy.fleet.action_keyvault_add(
        ctx.keyvault_client, ctx.config, ctx.keyvault_uri, name)


@keyvault.command('del')
@click.argument('name')
@common_options
@keyvault_options
@pass_cli_context
def keyvault_del(ctx, name):
    """Delete a secret from Azure KeyVault"""
    ctx.initialize_for_keyvault()
    convoy.fleet.action_keyvault_del(
        ctx.keyvault_client, ctx.keyvault_uri, name)


@keyvault.command('list')
@common_options
@keyvault_options
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
@pass_cli_context
def cert_create(ctx):
    """Create a certificate to use with a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_create(ctx.config)


@cert.command('add')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def cert_add(ctx):
    """Add a certificate to a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_add(ctx.batch_client, ctx.config)


@cert.command('list')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def cert_list(ctx):
    """List all certificates in a Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_cert_list(ctx.batch_client)


@cert.command('del')
@common_options
@batch_options
@keyvault_options
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
@pass_cli_context
def pool_listskus(ctx):
    """List available VM configurations available to the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_listskus(ctx.batch_client)


@pool.command('add')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_add(ctx):
    """Add a pool to the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_add(
        ctx.batch_client, ctx.blob_client, ctx.queue_client,
        ctx.table_client, ctx.config)


@pool.command('list')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_list(ctx):
    """List all pools in the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_list(ctx.batch_client)


@pool.command('del')
@click.option(
    '--wait', is_flag=True, help='Wait for pool deletion to complete')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_del(ctx, wait):
    """Delete a pool from the Batch account"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_delete(
        ctx.batch_client, ctx.blob_client, ctx.queue_client,
        ctx.table_client, ctx.config, wait=wait)


@pool.command('resize')
@click.option(
    '--wait', is_flag=True, help='Wait for pool resize to complete')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_resize(ctx, wait):
    """Resize a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_resize(
        ctx.batch_client, ctx.blob_client, ctx.config, wait=wait)


@pool.command('grls')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_grls(ctx):
    """Get remote login settings for all nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_grls(ctx.batch_client, ctx.config)


@pool.command('listnodes')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_listnodes(ctx):
    """List nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_listnodes(ctx.batch_client, ctx.config)


@pool.command('asu')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_asu(ctx):
    """Add an SSH user to all nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_asu(ctx.batch_client, ctx.config)


@pool.command('dsu')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_dsu(ctx):
    """Delete an SSH user from all nodes in pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_dsu(ctx.batch_client, ctx.config)


@pool.command('ssh')
@click.option(
    '--cardinal',
    help='Zero-based cardinal number of compute node in pool to connect to',
    type=int)
@click.option(
    '--nodeid', help='NodeId of compute node in pool to connect to')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_ssh(ctx, cardinal, nodeid):
    """Interactively login via SSH to a node in the pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_ssh(
        ctx.batch_client, ctx.config, cardinal, nodeid)


@pool.command('delnode')
@click.option(
    '--nodeid', help='NodeId of compute node in pool to delete')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_delnode(ctx, nodeid):
    """Delete a node from a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_delnode(ctx.batch_client, ctx.config, nodeid)


@pool.command('rebootnode')
@click.option(
    '--all-start-task-failed',
    is_flag=True,
    help='Reboot all nodes with start task failed state')
@click.option(
    '--nodeid', help='NodeId of compute node in pool to reboot')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_rebootnode(ctx, all_start_task_failed, nodeid):
    """Reboot a node or nodes in a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_rebootnode(
        ctx.batch_client, ctx.config, all_start_task_failed, nodeid)


@pool.command('udi')
@click.option(
    '--image', help='Docker image[:tag] to update')
@click.option(
    '--digest', help='Digest to update image to')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def pool_udi(ctx, image, digest):
    """Update Docker images in a pool"""
    ctx.initialize_for_batch()
    convoy.fleet.action_pool_udi(ctx.batch_client, ctx.config, image, digest)


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
@pass_cli_context
def jobs_add(ctx, recreate, tail):
    """Add jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_add(
        ctx.batch_client, ctx.blob_client, ctx.keyvault_client, ctx.config,
        recreate, tail)


@jobs.command('list')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def jobs_list(ctx):
    """List jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_list(ctx.batch_client, ctx.config)


@jobs.command('listtasks')
@click.option(
    '--jobid', help='List tasks in the specified job id')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def jobs_list_tasks(ctx, jobid):
    """List tasks within jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_listtasks(ctx.batch_client, ctx.config, jobid)


@jobs.command('termtasks')
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
@pass_cli_context
def jobs_termtasks(ctx, force, jobid, taskid, wait):
    """Terminate specified tasks in jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_termtasks(
        ctx.batch_client, ctx.config, jobid, taskid, wait, force)


@jobs.command('term')
@click.option(
    '--all', is_flag=True, help='Terminate all jobs in Batch account')
@click.option(
    '--jobid', help='Terminate just the specified job id')
@click.option(
    '--termtasks', is_flag=True, help='Terminate tasks running in job first')
@click.option(
    '--wait', is_flag=True, help='Wait for jobs termination to complete')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def jobs_term(ctx, all, jobid, termtasks, wait):
    """Terminate jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_term(
        ctx.batch_client, ctx.config, all, jobid, termtasks, wait)


@jobs.command('del')
@click.option(
    '--all', is_flag=True, help='Delete all jobs in Batch account')
@click.option(
    '--jobid', help='Delete just the specified job id')
@click.option(
    '--termtasks', is_flag=True, help='Terminate tasks running in job first')
@click.option(
    '--wait', is_flag=True, help='Wait for jobs deletion to complete')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def jobs_del(ctx, all, jobid, termtasks, wait):
    """Delete jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_del(
        ctx.batch_client, ctx.config, all, jobid, termtasks, wait)


@jobs.command('deltasks')
@click.option(
    '--jobid', help='Delete tasks in the specified job id')
@click.option(
    '--taskid', help='Delete tasks in the specified task id')
@click.option(
    '--wait', is_flag=True, help='Wait for task deletion to complete')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def jobs_deltasks(ctx, jobid, taskid, wait):
    """Delete specified tasks in jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_deltasks(
        ctx.batch_client, ctx.config, jobid, taskid, wait)


@jobs.command('cmi')
@click.option(
    '--delete', is_flag=True,
    help='Delete all cleanup multi-instance jobs in Batch account')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def jobs_cmi(ctx, delete):
    """Cleanup multi-instance jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_jobs_cmi(ctx.batch_client, ctx.config, delete)


@cli.group()
@pass_cli_context
def data(ctx):
    """Data actions"""
    pass


@data.command('listfiles')
@click.option(
    '--jobid', help='List files from the specified job id')
@click.option(
    '--taskid', help='List files from the specified task id')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def data_listfiles(ctx, jobid, taskid):
    """List files for tasks in jobs"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_listfiles(
        ctx.batch_client, ctx.config, jobid, taskid)


@data.command('stream')
@click.option(
    '--disk', is_flag=True,
    help='Write streamed data to disk and suppress console output')
@click.option(
    '--filespec', help='File specification as jobid,taskid,filename')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def data_stream(ctx, disk, filespec):
    """Stream a file as text to the local console or as binary to disk"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_stream(
        ctx.batch_client, ctx.config, filespec, disk)


@data.command('getfile')
@click.option(
    '--all', is_flag=True, help='Retrieve all files for given job/task')
@click.option(
    '--filespec',
    help='File specification as jobid,taskid,filename or '
    'jobid,taskid,include_pattern if invoked with --all')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def data_getfile(ctx, all, filespec):
    """Retrieve file(s) from a job/task"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_getfile(
        ctx.batch_client, ctx.config, all, filespec)


@data.command('getfilenode')
@click.option(
    '--all', is_flag=True, help='Retrieve all files for given compute node')
@click.option(
    '--filespec', help='File specification as nodeid,filename or '
    'nodeid,include_pattern if invoked with --all')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def data_getfilenode(ctx, all, filespec):
    """Retrieve file(s) from a compute node"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_getfilenode(
        ctx.batch_client, ctx.config, all, filespec)


@data.command('ingress')
@common_options
@batch_options
@keyvault_options
@pass_cli_context
def data_ingress(ctx):
    """Ingress data into Azure"""
    ctx.initialize_for_batch()
    convoy.fleet.action_data_ingress(ctx.batch_client, ctx.config)


if __name__ == '__main__':
    convoy.util.setup_logger(logger)
    cli()
