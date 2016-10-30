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

# stdlib imports
from __future__ import division, print_function
import click
import json
import logging
import logging.handlers
try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib
# non-stdlib imports
# local imports
import convoy.fleet
import convoy.util

# create logger
logger = logging.getLogger('shipyard')
# global defines
_CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


class CliContext(object):
    """CliContext class: holds context for CLI commands"""
    def __init__(self):
        """Ctor for CliContext"""
        self.verbose = False
        self.yes = False
        self.config = None
        self.batch_client = None
        self.blob_client = None
        self.queue_client = None
        self.table_client = None

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

    def init_config(self):
        """Initializes configuration of the context"""
        # use configdir if available
        if self.configdir is not None:
            if self.json_credentials is None:
                self.json_credentials = pathlib.Path(
                    self.configdir, 'credentials.json')
            if self.json_config is None:
                self.json_config = pathlib.Path(
                    self.configdir, 'config.json')
            if self.json_pool is None:
                self.json_pool = pathlib.Path(self.configdir, 'pool.json')
            if self.json_jobs is None:
                self.json_jobs = pathlib.Path(self.configdir, 'jobs.json')
        # check for required json files
        if self.json_credentials is None:
            raise ValueError('credentials json was not specified')
        elif not isinstance(self.json_credentials, pathlib.Path):
            self.json_credentials = pathlib.Path(self.json_credentials)
        if self.json_config is None:
            raise ValueError('config json was not specified')
        elif not isinstance(self.json_config, pathlib.Path):
            self.json_config = pathlib.Path(self.json_config)
        if self.json_pool is None:
            raise ValueError('pool json was not specified')
        elif not isinstance(self.json_pool, pathlib.Path):
            self.json_pool = pathlib.Path(self.json_pool)
        # load json files into memory
        self._read_json_file(self.json_credentials)
        self._read_json_file(self.json_config)
        self._read_json_file(self.json_pool)
        if self.json_jobs is not None:
            self._read_json_file(self.json_jobs)
        # set internal config kv pairs
        self.config['_verbose'] = self.verbose
        self.config['_auto_confirm'] = self.yes
        if self.verbose:
            logger.debug('config:\n' + json.dumps(self.config, indent=4))
        # free mem
        del self.json_credentials
        del self.json_config
        del self.json_pool
        del self.json_jobs
        del self.verbose
        del self.yes

    def init_clients(self):
        """Initializes clients for the context"""
        clients = convoy.fleet.create_clients(self.config)
        self.batch_client = clients[0]
        self.blob_client = clients[1]
        self.queue_client = clients[2]
        self.table_client = clients[3]


# create a pass decorator for shared context between commands
pass_cli_context = click.make_pass_decorator(CliContext, ensure=True)


def verbose_option(f):
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


def confirm_option(f):
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


def configdir_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.configdir = value
        return value
    return click.option(
        '--configdir',
        expose_value=False,
        help='Configuration directory where all configuration files can be '
        'found. Each json config file must be named exactly the same as the '
        'regular switch option, e.g., pool.json for --pool. Individually '
        'specified config options take precedence over this option.',
        callback=callback)(f)


def credentials_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_credentials = value
        return value
    return click.option(
        '--credentials',
        expose_value=False,
        help='Credentials json config file',
        callback=callback)(f)


def config_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_config = value
        return value
    return click.option(
        '--config',
        expose_value=False,
        help='Global json config file',
        callback=callback)(f)


def pool_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_pool = value
        return value
    return click.option(
        '--pool',
        expose_value=False,
        help='Pool json config file',
        callback=callback)(f)


def jobs_option(f):
    def callback(ctx, param, value):
        clictx = ctx.ensure_object(CliContext)
        clictx.json_jobs = value
        return value
    return click.option(
        '--jobs',
        expose_value=False,
        help='Jobs json config file',
        callback=callback)(f)


def common_options(f):
    f = jobs_option(f)
    f = pool_option(f)
    f = config_option(f)
    f = credentials_option(f)
    f = configdir_option(f)
    f = verbose_option(f)
    f = confirm_option(f)
    return f


def _setup_context(ctx, pool_add_action=False):
    ctx.init_config()
    convoy.fleet.populate_global_settings(ctx.config, pool_add_action)
    ctx.init_clients()
    convoy.fleet.adjust_general_settings(ctx.config)


@click.group(context_settings=_CONTEXT_SETTINGS)
@click.version_option(version=convoy.fleet.__version__)
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
    _setup_context(ctx)
    convoy.fleet.action_storage_del(
        ctx.blob_client, ctx.queue_client, ctx.table_client, ctx.config)


@storage.command('clear')
@common_options
@pass_cli_context
def storage_clear(ctx):
    """Clear Azure Storage containers used by Batch Shipyard"""
    _setup_context(ctx)
    convoy.fleet.action_storage_clear(
        ctx.blob_client, ctx.queue_client, ctx.table_client, ctx.config)


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
    _setup_context(ctx)
    convoy.fleet.action_cert_create(ctx.config)


@cert.command('add')
@common_options
@pass_cli_context
def cert_add(ctx):
    """Add a certificate to a Batch account"""
    _setup_context(ctx)
    convoy.fleet.action_cert_add(ctx.batch_client, ctx.config)


@cert.command('list')
@common_options
@pass_cli_context
def cert_list(ctx):
    """List all certificates in a Batch account"""
    _setup_context(ctx)
    convoy.fleet.action_cert_list(ctx.batch_client)


@cert.command('del')
@common_options
@pass_cli_context
def cert_del(ctx):
    """Delete a certificate from a Batch account"""
    _setup_context(ctx)
    convoy.fleet.action_cert_del(ctx.batch_client, ctx.config)


@cli.group()
@pass_cli_context
def pool(ctx):
    """Pool actions"""
    pass


@pool.command('add')
@common_options
@pass_cli_context
def pool_add(ctx):
    """Add a pool to the Batch account"""
    _setup_context(ctx, True)
    convoy.fleet.action_pool_add(
        ctx.batch_client, ctx.blob_client, ctx.queue_client,
        ctx.table_client, ctx.config)


@pool.command('list')
@common_options
@pass_cli_context
def pool_list(ctx):
    """List all pools in the Batch account"""
    _setup_context(ctx)
    convoy.fleet.action_pool_list(ctx.batch_client)


@pool.command('del')
@click.option(
    '--wait', is_flag=True, help='Wait for pool deletion to complete')
@common_options
@pass_cli_context
def pool_del(ctx, wait):
    """Delete a pool from the Batch account"""
    _setup_context(ctx)
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
    _setup_context(ctx)
    convoy.fleet.action_pool_resize(
        ctx.batch_client, ctx.blob_client, ctx.config, wait=wait)


@pool.command('grls')
@common_options
@pass_cli_context
def pool_grls(ctx):
    """Get remote login settings for all nodes in pool"""
    _setup_context(ctx)
    convoy.fleet.action_pool_grls(ctx.batch_client, ctx.config)


@pool.command('listnodes')
@common_options
@pass_cli_context
def pool_listnodes(ctx):
    """List nodes in pool"""
    _setup_context(ctx)
    convoy.fleet.action_pool_listnodes(ctx.batch_client, ctx.config)


@pool.command('asu')
@common_options
@pass_cli_context
def pool_asu(ctx):
    """Add an SSH user to all nodes in pool"""
    _setup_context(ctx)
    convoy.fleet.action_pool_asu(ctx.batch_client, ctx.config)


@pool.command('dsu')
@common_options
@pass_cli_context
def pool_dsu(ctx):
    """Delete an SSH user from all nodes in pool"""
    _setup_context(ctx)
    convoy.fleet.action_pool_dsu(ctx.batch_client, ctx.config)


@pool.command('delnode')
@click.option(
    '--nodeid', help='NodeId of compute node in pool to delete')
@common_options
@pass_cli_context
def pool_delnode(ctx, nodeid):
    """Delete a node from a pool"""
    _setup_context(ctx)
    convoy.fleet.action_pool_delnode(ctx.batch_client, ctx.config, nodeid)


@cli.group()
@pass_cli_context
def jobs(ctx):
    """Jobs actions"""
    pass


@jobs.command('add')
@common_options
@pass_cli_context
def jobs_add(ctx):
    """Add jobs"""
    _setup_context(ctx)
    convoy.fleet.action_jobs_add(
        ctx.batch_client, ctx.blob_client, ctx.config)


@jobs.command('list')
@common_options
@pass_cli_context
def jobs_list(ctx):
    """List jobs"""
    _setup_context(ctx)
    convoy.fleet.action_jobs_list(ctx.batch_client, ctx.config)


@jobs.command('listtasks')
@common_options
@pass_cli_context
def jobs_list_tasks(ctx):
    """List tasks within jobs"""
    _setup_context(ctx)
    convoy.fleet.action_jobs_listtasks(ctx.batch_client, ctx.config)


@jobs.command('termtasks')
@click.option(
    '--jobid', help='Terminate tasks in the specified job id')
@click.option(
    '--taskid', help='Terminate tasks in the specified task id')
@click.option(
    '--wait', is_flag=True, help='Wait for task termination to complete')
@common_options
@pass_cli_context
def jobs_termtasks(ctx, jobid, taskid, wait):
    """Terminate specified tasks in jobs"""
    _setup_context(ctx)
    convoy.fleet.action_jobs_termtasks(
        ctx.batch_client, ctx.config, jobid, taskid, wait)


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
    _setup_context(ctx)
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
    _setup_context(ctx)
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
    _setup_context(ctx)
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
    _setup_context(ctx)
    convoy.fleet.action_jobs_cmi(ctx.batch_client, ctx.config, delete)


@cli.group()
@pass_cli_context
def data(ctx):
    """Data actions"""
    pass


@data.command('listfiles')
@common_options
@pass_cli_context
def data_listfiles(ctx):
    """List files for all tasks in jobs"""
    _setup_context(ctx)
    convoy.fleet.action_data_listfiles(ctx.batch_client, ctx.config)


@data.command('stream')
@click.option(
    '--filespec', help='File specification as jobid,taskid,filename')
@common_options
@pass_cli_context
def data_stream(ctx, filespec):
    """Stream a text file to the local console"""
    _setup_context(ctx)
    convoy.fleet.action_data_stream(ctx.batch_client, filespec)


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
    _setup_context(ctx)
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
    _setup_context(ctx)
    convoy.fleet.action_data_getfilenode(
        ctx.batch_client, ctx.config, all, filespec)


@data.command('ingress')
@common_options
@pass_cli_context
def data_ingress(ctx):
    """Ingress data into Azure"""
    _setup_context(ctx)
    convoy.fleet.action_data_ingress(ctx.batch_client, ctx.config)

if __name__ == '__main__':
    convoy.util.setup_logger(logger)
    cli()
