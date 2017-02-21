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
from convoy.context import Context
import convoy.fleet
import convoy.settings
import convoy.util

# create logger
logger = logging.getLogger('shipyard')
# global defines
_CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


class CliContext(Context):
    """CliContext class: holds context for CLI commands"""

    def initialize(self, creds_only=False, no_config=False):
        # type: (CliContext, bool, bool) -> None
        """Initialize context
        :param CliContext self: this
        :param bool creds_only: credentials only initialization
        :param bool no_config: do not configure context
        """

        obj_credentials = self._read_credentials_config()
        obj_config, obj_pool, obj_jobs = None, None, None
        if not creds_only:
            obj_config = self._read_config_config()
            obj_pool = self._read_pool_config()
            obj_jobs = self._read_obj_jobs()

        super(Context, self).initialize(obj_credentials, obj_config, obj_pool, obj_jobs, creds_only, no_config)

        # free mem
        del self.json_credentials
        del self.json_config
        del self.json_pool
        del self.json_jobs

    def _read_json_file(self, json_file):
        # type: (CliContext, pathlib.Path) -> None
        """Read a json file into self.config, while checking for invalid
        JSON and returning an error that makes sense if ValueError
        :param CliContext self: this
        :param pathlib.Path json_file: json file to load
        """
        try:
            with json_file.open('r') as f:
                return json.load(f)
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
            return self._read_json_file(self.json_credentials)

    def _read_config_confg(self):
        if self.configdir is not None:
            if self.json_config is None:
                self.json_config = pathlib.Path(
                    self.configdir, 'config.json')
        if self.json_config is None:
            raise ValueError('config json was not specified')
        elif not isinstance(self.json_config, pathlib.Path):
            self.json_config = pathlib.Path(self.json_config)
        return self._read_json_file(self.json_config)

    def _read_pool_config(self):
        if self.configdir is not None:
            if self.json_pool is None:
                self.json_pool = pathlib.Path(self.configdir, 'pool.json')
        if self.json_pool is None:
            raise ValueError('pool json was not specified')
        elif not isinstance(self.json_pool, pathlib.Path):
            self.json_pool = pathlib.Path(self.json_pool)
        return self._read_json_file(self.json_pool)

    def _read_jobs_confg(self):
        if self.configdir is not None:
            if self.json_jobs is None:
                self.json_jobs = pathlib.Path(self.configdir, 'jobs.json')
        if self.json_jobs is not None:
            if not isinstance(self.json_jobs, pathlib.Path):
                self.json_jobs = pathlib.Path(self.json_jobs)
            if self.json_jobs.exists():
                return self._read_json_file(self.json_jobs)


# create a pass decorator for shared context between commands
pass_cli_context = click.make_pass_decorator(CliContext, ensure=True)


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


def common_options(f):
    f = _aad_cert_thumbprint_option(f)
    f = _aad_cert_private_key_option(f)
    f = _aad_password_option(f)
    f = _aad_user_option(f)
    f = _aad_auth_key_option(f)
    f = _aad_application_id_option(f)
    f = _aad_directory_id_option(f)
    f = _azure_keyvault_credentials_secret_id_option(f)
    f = _azure_keyvault_uri_option(f)
    f = _jobs_option(f)
    f = _pool_option(f)
    f = _config_option(f)
    f = _credentials_option(f)
    f = _configdir_option(f)
    f = _verbose_option(f)
    f = _confirm_option(f)
    return f


@click.group(context_settings=_CONTEXT_SETTINGS)
@click.version_option(version=convoy.__version__)
@click.pass_context
def cli(ctx):
    """Batch Shipyard: Provision and Execute Docker Workloads on Azure Batch"""
    pass


@cli.group()
@pass_cli_context
def storage(ctx):
    """Storage actions"""
    pass


@storage.command('del')
@common_options
@pass_cli_context
def storage_del(ctx):
    """Delete Azure Storage containers used by Batch Shipyard"""
    ctx.initialize()
    convoy.fleet.action_storage_del(
        ctx.blob_client, ctx.queue_client, ctx.table_client, ctx.config)


@storage.command('clear')
@common_options
@pass_cli_context
def storage_clear(ctx):
    """Clear Azure Storage containers used by Batch Shipyard"""
    ctx.initialize()
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
@pass_cli_context
def keyvault_add(ctx, name):
    """Add a credentials json as a secret to Azure KeyVault"""
    ctx.initialize(creds_only=True)
    convoy.fleet.action_keyvault_add(
        ctx.keyvault_client, ctx.config, ctx.keyvault_uri, name)


@keyvault.command('del')
@click.argument('name')
@common_options
@pass_cli_context
def keyvault_del(ctx, name):
    """Delete a secret from Azure KeyVault"""
    ctx.initialize(creds_only=True, no_config=True)
    convoy.fleet.action_keyvault_del(
        ctx.keyvault_client, ctx.keyvault_uri, name)


@keyvault.command('list')
@common_options
@pass_cli_context
def keyvault_list(ctx):
    """List secret ids and metadata in an Azure KeyVault"""
    ctx.initialize(creds_only=True, no_config=True)
    convoy.fleet.action_keyvault_list(ctx.keyvault_client, ctx.keyvault_uri)


@cli.group()
@pass_cli_context
def cert(ctx):
    """Certificate actions"""
    pass


@cert.command('create')
@common_options
@pass_cli_context
def cert_create(ctx):
    """Create a certificate to use with a Batch account"""
    ctx.initialize()
    convoy.fleet.action_cert_create(ctx.config)


@cert.command('add')
@common_options
@pass_cli_context
def cert_add(ctx):
    """Add a certificate to a Batch account"""
    ctx.initialize()
    convoy.fleet.action_cert_add(ctx.batch_client, ctx.config)


@cert.command('list')
@common_options
@pass_cli_context
def cert_list(ctx):
    """List all certificates in a Batch account"""
    ctx.initialize()
    convoy.fleet.action_cert_list(ctx.batch_client)


@cert.command('del')
@common_options
@pass_cli_context
def cert_del(ctx):
    """Delete a certificate from a Batch account"""
    ctx.initialize()
    convoy.fleet.action_cert_del(ctx.batch_client, ctx.config)


@cli.group()
@pass_cli_context
def pool(ctx):
    """Pool actions"""
    pass


@pool.command('listskus')
@common_options
@pass_cli_context
def pool_listskus(ctx):
    """List available VM configurations available to the Batch account"""
    ctx.initialize()
    convoy.fleet.action_pool_listskus(ctx.batch_client)


@pool.command('add')
@common_options
@pass_cli_context
def pool_add(ctx):
    """Add a pool to the Batch account"""
    ctx.initialize()
    convoy.fleet.action_pool_add(
        ctx.batch_client, ctx.blob_client, ctx.queue_client,
        ctx.table_client, ctx.config)


@pool.command('list')
@common_options
@pass_cli_context
def pool_list(ctx):
    """List all pools in the Batch account"""
    ctx.initialize()
    convoy.fleet.action_pool_list(ctx.batch_client)


@pool.command('del')
@click.option(
    '--wait', is_flag=True, help='Wait for pool deletion to complete')
@common_options
@pass_cli_context
def pool_del(ctx, wait):
    """Delete a pool from the Batch account"""
    ctx.initialize()
    convoy.fleet.action_pool_delete(
        ctx.batch_client, ctx.blob_client, ctx.queue_client,
        ctx.table_client, ctx.config, wait=wait)


@pool.command('resize')
@click.option(
    '--wait', is_flag=True, help='Wait for pool resize to complete')
@common_options
@pass_cli_context
def pool_resize(ctx, wait):
    """Resize a pool"""
    ctx.initialize()
    convoy.fleet.action_pool_resize(
        ctx.batch_client, ctx.blob_client, ctx.config, wait=wait)


@pool.command('grls')
@common_options
@pass_cli_context
def pool_grls(ctx):
    """Get remote login settings for all nodes in pool"""
    ctx.initialize()
    convoy.fleet.action_pool_grls(ctx.batch_client, ctx.config)


@pool.command('listnodes')
@common_options
@pass_cli_context
def pool_listnodes(ctx):
    """List nodes in pool"""
    ctx.initialize()
    convoy.fleet.action_pool_listnodes(ctx.batch_client, ctx.config)


@pool.command('asu')
@common_options
@pass_cli_context
def pool_asu(ctx):
    """Add an SSH user to all nodes in pool"""
    ctx.initialize()
    convoy.fleet.action_pool_asu(ctx.batch_client, ctx.config)


@pool.command('dsu')
@common_options
@pass_cli_context
def pool_dsu(ctx):
    """Delete an SSH user from all nodes in pool"""
    ctx.initialize()
    convoy.fleet.action_pool_dsu(ctx.batch_client, ctx.config)


@pool.command('ssh')
@click.option(
    '--cardinal',
    help='Zero-based cardinal number of compute node in pool to connect to',
    type=int)
@click.option(
    '--nodeid', help='NodeId of compute node in pool to connect to')
@common_options
@pass_cli_context
def pool_ssh(ctx, cardinal, nodeid):
    """Interactively login via SSH to a node in the pool"""
    ctx.initialize()
    convoy.fleet.action_pool_ssh(
        ctx.batch_client, ctx.config, cardinal, nodeid)


@pool.command('delnode')
@click.option(
    '--nodeid', help='NodeId of compute node in pool to delete')
@common_options
@pass_cli_context
def pool_delnode(ctx, nodeid):
    """Delete a node from a pool"""
    ctx.initialize()
    convoy.fleet.action_pool_delnode(ctx.batch_client, ctx.config, nodeid)


@pool.command('udi')
@click.option(
    '--image', help='Docker image[:tag] to update')
@click.option(
    '--digest', help='Digest to update image to')
@common_options
@pass_cli_context
def pool_udi(ctx, image, digest):
    """Update Docker images in a pool"""
    ctx.initialize()
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
@pass_cli_context
def jobs_add(ctx, recreate, tail):
    """Add jobs"""
    ctx.initialize()
    convoy.fleet.action_jobs_add(
        ctx.batch_client, ctx.blob_client, ctx.keyvault_client, ctx.config,
        recreate, tail)


@jobs.command('list')
@common_options
@pass_cli_context
def jobs_list(ctx):
    """List jobs"""
    ctx.initialize()
    convoy.fleet.action_jobs_list(ctx.batch_client, ctx.config)


@jobs.command('listtasks')
@click.option(
    '--jobid', help='List tasks in the specified job id')
@common_options
@pass_cli_context
def jobs_list_tasks(ctx, jobid):
    """List tasks within jobs"""
    ctx.initialize()
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
@pass_cli_context
def jobs_termtasks(ctx, force, jobid, taskid, wait):
    """Terminate specified tasks in jobs"""
    ctx.initialize()
    convoy.fleet.action_jobs_termtasks(
        ctx.batch_client, ctx.config, jobid, taskid, wait, force)


@jobs.command('term')
@click.option(
    '--all', is_flag=True, help='Terminate all jobs in Batch account')
@click.option(
    '--jobid', help='Terminate just the specified job id')
@click.option(
    '--wait', is_flag=True, help='Wait for jobs termination to complete')
@common_options
@pass_cli_context
def jobs_term(ctx, all, jobid, wait):
    """Terminate jobs"""
    ctx.initialize()
    convoy.fleet.action_jobs_term(
        ctx.batch_client, ctx.config, all, jobid, wait)


@jobs.command('del')
@click.option(
    '--all', is_flag=True, help='Delete all jobs in Batch account')
@click.option(
    '--jobid', help='Delete just the specified job id')
@click.option(
    '--wait', is_flag=True, help='Wait for jobs deletion to complete')
@common_options
@pass_cli_context
def jobs_del(ctx, all, jobid, wait):
    """Delete jobs"""
    ctx.initialize()
    convoy.fleet.action_jobs_del(
        ctx.batch_client, ctx.config, all, jobid, wait)


@jobs.command('deltasks')
@click.option(
    '--jobid', help='Delete tasks in the specified job id')
@click.option(
    '--taskid', help='Delete tasks in the specified task id')
@click.option(
    '--wait', is_flag=True, help='Wait for task deletion to complete')
@common_options
@pass_cli_context
def jobs_deltasks(ctx, jobid, taskid, wait):
    """Delete specified tasks in jobs"""
    ctx.initialize()
    convoy.fleet.action_jobs_deltasks(
        ctx.batch_client, ctx.config, jobid, taskid, wait)


@jobs.command('cmi')
@click.option(
    '--delete', is_flag=True,
    help='Delete all cleanup multi-instance jobs in Batch account')
@common_options
@pass_cli_context
def jobs_cmi(ctx, delete):
    """Cleanup multi-instance jobs"""
    ctx.initialize()
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
@pass_cli_context
def data_listfiles(ctx, jobid, taskid):
    """List files for tasks in jobs"""
    ctx.initialize()
    convoy.fleet.action_data_listfiles(
        ctx.batch_client, ctx.config, jobid, taskid)


@data.command('stream')
@click.option(
    '--disk', is_flag=True,
    help='Write streamed data to disk and suppress console output')
@click.option(
    '--filespec', help='File specification as jobid,taskid,filename')
@common_options
@pass_cli_context
def data_stream(ctx, disk, filespec):
    """Stream a file as text to the local console or as binary to disk"""
    ctx.initialize()
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
@pass_cli_context
def data_getfile(ctx, all, filespec):
    """Retrieve file(s) from a job/task"""
    ctx.initialize()
    convoy.fleet.action_data_getfile(
        ctx.batch_client, ctx.config, all, filespec)


@data.command('getfilenode')
@click.option(
    '--all', is_flag=True, help='Retrieve all files for given compute node')
@click.option(
    '--filespec', help='File specification as nodeid,filename or '
    'nodeid,include_pattern if invoked with --all')
@common_options
@pass_cli_context
def data_getfilenode(ctx, all, filespec):
    """Retrieve file(s) from a compute node"""
    ctx.initialize()
    convoy.fleet.action_data_getfilenode(
        ctx.batch_client, ctx.config, all, filespec)


@data.command('ingress')
@common_options
@pass_cli_context
def data_ingress(ctx):
    """Ingress data into Azure"""
    ctx.initialize()
    convoy.fleet.action_data_ingress(ctx.batch_client, ctx.config)


if __name__ == '__main__':
    convoy.util.setup_logger(logger)
    cli()
