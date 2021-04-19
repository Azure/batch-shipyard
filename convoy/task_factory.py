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
import collections
import copy
import datetime
import fnmatch
import functools
import importlib
import itertools
import random
from urllib.parse import quote as urlquote
# non-stdlib imports
import azure.storage.blob as azureblob
import azure.storage.file as azurefile
# local imports

# global defines
_DEFAULT_SAS_EXPIRY_DAYS = 365 * 30
# named tuples
FileInfo = collections.namedtuple(
    'FileInfo', [
        'is_blob',
        'url',
        'sas',
        'file_path',
        'file_path_with_container',
        'file_name',
        'file_name_no_extension',
        'task_filepath',
    ]
)


def _prepare_random_task_factory(task_factory):
    # type: (dict) -> func
    """Prepare the random task factory
    :param dict task_factory: task factory object
    :rtype: func
    :return: random function to invoke
    """
    try:
        seed = task_factory['random']['seed']
    except KeyError:
        pass
    else:
        random.seed(seed)
    if 'integer' in task_factory['random']:
        rfunc = functools.partial(
            random.randrange,
            task_factory['random']['integer']['start'],
            task_factory['random']['integer']['stop'],
            task_factory['random']['integer']['step'],
        )
    elif 'uniform' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.uniform,
            task_factory['random']['distribution']['uniform']['a'],
            task_factory['random']['distribution']['uniform']['b'],
        )
    elif 'triangular' in task_factory['random']['distribution']:
        try:
            mode = task_factory['random']['distribution']['triangular']['mode']
        except KeyError:
            mode = None
        rfunc = functools.partial(
            random.triangular,
            task_factory['random']['distribution']['triangular']['low'],
            task_factory['random']['distribution']['triangular']['high'],
            mode,
        )
    elif 'beta' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.betavariate,
            task_factory['random']['distribution']['beta']['alpha'],
            task_factory['random']['distribution']['beta']['beta'],
        )
    elif 'exponential' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.expovariate,
            task_factory['random']['distribution']['exponential']['lambda'],
        )
    elif 'gamma' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.gammavariate,
            task_factory['random']['distribution']['gamma']['alpha'],
            task_factory['random']['distribution']['gamma']['beta'],
        )
    elif 'gauss' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.gauss,
            task_factory['random']['distribution']['gauss']['mu'],
            task_factory['random']['distribution']['gauss']['sigma'],
        )
    elif 'lognormal' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.lognormvariate,
            task_factory['random']['distribution']['lognormal']['mu'],
            task_factory['random']['distribution']['lognormal']['sigma'],
        )
    elif 'pareto' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.paretovariate,
            task_factory['random']['distribution']['pareto']['alpha'],
        )
    elif 'weibull' in task_factory['random']['distribution']:
        rfunc = functools.partial(
            random.weibullvariate,
            task_factory['random']['distribution']['weibull']['alpha'],
            task_factory['random']['distribution']['weibull']['beta'],
        )
    return rfunc


def _inclusion_check(path, include, exclude):
    # type: (str, list, list) -> bool
    """Check file for inclusion against filters
    :param str path: path to checko
    :param list include: inclusion filters
    :param list exclude: exclusion filters
    :rtype: bool
    :return: if file should be included
    """
    inc = True
    if include is not None:
        inc = any([fnmatch.fnmatch(path, x) for x in include])
    if inc and exclude is not None:
        inc = not any([fnmatch.fnmatch(path, x) for x in exclude])
    return inc


def _list_all_files_in_fileshare(client, fileshare, prefix):
    # type: (azure.storage.file.FileService, str, str) -> str
    """List all files in share
    :param azure.storage.file.FileService client: file client
    :param str fileshare: file share
    :param str prefix: prefix directory
    :rtype: str
    :return: file name
    """
    dirs = [prefix]
    while len(dirs) > 0:
        dir = dirs.pop()
        files = client.list_directories_and_files(
            share_name=fileshare,
            directory_name=dir,
        )
        for file in files:
            if dir is not None:
                fspath = '{}/{}'.format(dir, file.name)
            else:
                fspath = file.name
            if type(file) == azurefile.models.File:
                yield fspath
            else:
                dirs.append(fspath)


def _get_storage_entities(task_factory, storage_settings):
    # type: (dict, settings.TaskFactoryStorageSettings) -> TaskSettings
    """Generate a task given a config
    :param dict task_factory: task factory object
    :param settings.TaskFactoryStorageSettings storage_settings:
        storage settings
    :rtype: FileInfo
    :return: file info
    """
    if not storage_settings.is_file_share:
        # create blob client
        blob_client = azureblob.BlockBlobService(
            account_name=storage_settings.storage_settings.account,
            account_key=storage_settings.storage_settings.account_key,
            endpoint_suffix=storage_settings.storage_settings.endpoint)
        # list blobs in container with filters
        if storage_settings.container != storage_settings.remote_path:
            prefix = '/'.join(storage_settings.remote_path.split('/')[1:])
        else:
            prefix = None
        blobs = blob_client.list_blobs(
            container_name=storage_settings.container, prefix=prefix)
        for blob in blobs:
            if not _inclusion_check(
                    blob.name, storage_settings.include,
                    storage_settings.exclude):
                continue
            file_path_with_container = '{}/{}'.format(
                storage_settings.container, blob.name)
            file_name = blob.name.split('/')[-1]
            file_name_no_extension = file_name.split('.')[0]
            if task_factory['file']['task_filepath'] == 'file_path':
                task_filepath = blob.name
            elif (task_factory['file']['task_filepath'] ==
                  'file_path_with_container'):
                task_filepath = file_path_with_container
            elif task_factory['file']['task_filepath'] == 'file_name':
                task_filepath = file_name
            elif (task_factory['file']['task_filepath'] ==
                  'file_name_no_extension'):
                task_filepath = file_name_no_extension
            else:
                raise ValueError(
                    'invalid task_filepath specification: {}'.format(
                        task_factory['file']['task_filepath']))
            # create blob url
            url = 'https://{}.blob.{}/{}/{}'.format(
                storage_settings.storage_settings.account,
                storage_settings.storage_settings.endpoint,
                storage_settings.container,
                urlquote(blob.name))
            # create blob sas
            sas = blob_client.generate_blob_shared_access_signature(
                storage_settings.container, blob.name,
                permission=azureblob.BlobPermissions.READ,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(days=_DEFAULT_SAS_EXPIRY_DAYS))
            yield FileInfo(
                is_blob=True,
                url=url,
                sas=sas,
                file_path=blob.name,
                file_path_with_container=file_path_with_container,
                file_name=file_name,
                file_name_no_extension=file_name_no_extension,
                task_filepath=task_filepath,
            )
    else:
        # create file share client
        file_client = azurefile.FileService(
            account_name=storage_settings.storage_settings.account,
            account_key=storage_settings.storage_settings.account_key,
            endpoint_suffix=storage_settings.storage_settings.endpoint)
        # list files in share with include/exclude
        if storage_settings.container != storage_settings.remote_path:
            prefix = '/'.join(storage_settings.remote_path.split('/')[1:])
        else:
            prefix = None
        for file in _list_all_files_in_fileshare(
                file_client, storage_settings.container, prefix):
            if not _inclusion_check(
                    file, storage_settings.include,
                    storage_settings.exclude):
                continue
            file_path_with_container = '{}/{}'.format(
                storage_settings.container, file)
            file_name = file.split('/')[-1]
            file_name_no_extension = file_name.split('.')[0]
            if task_factory['file']['task_filepath'] == 'file_path':
                task_filepath = file
            elif (task_factory['file']['task_filepath'] ==
                  'file_path_with_container'):
                task_filepath = file_path_with_container
            elif task_factory['file']['task_filepath'] == 'file_name':
                task_filepath = file_name
            elif (task_factory['file']['task_filepath'] ==
                  'file_name_no_extension'):
                task_filepath = file_name_no_extension
            else:
                raise ValueError(
                    'invalid task_filepath specification: {}'.format(
                        task_factory['file']['task_filepath']))
            yield FileInfo(
                is_blob=False,
                url=None,
                sas=None,
                file_path=file,
                file_path_with_container=file_path_with_container,
                file_name=file_name,
                file_name_no_extension=file_name_no_extension,
                task_filepath=task_filepath,
            )


def generate_task(task, storage_settings):
    # type: (dict, settings.TaskFactoryStorageSettings) -> TaskSettings
    """Generate a task given a config
    :param dict config: configuration object
    :param settings.TaskFactoryStorageSettings storage_settings:
        storage settings
    :rtype: TaskSettings
    :return: generated task
    """
    # create a copy of the base task without task_factory
    base_task_copy = copy.deepcopy(task)
    base_task_copy.pop('task_factory')
    # retrieve type of task factory
    task_factory = task['task_factory']
    if 'custom' in task_factory:
        try:
            pkg = task_factory['custom']['package']
        except KeyError:
            pkg = None
        module = importlib.import_module(
            task_factory['custom']['module'], package=pkg)
        try:
            input_args = task_factory['custom']['input_args']
        except KeyError:
            input_args = None
        try:
            input_kwargs = task_factory['custom']['input_kwargs']
        except KeyError:
            input_kwargs = None
        if input_args is not None:
            if input_kwargs is not None:
                args = module.generate(*input_args, **input_kwargs)
            else:
                args = module.generate(*input_args)
        else:
            if input_kwargs is not None:
                args = module.generate(**input_kwargs)
            else:
                args = module.generate()
        for arg in args:
            taskcopy = copy.copy(base_task_copy)
            taskcopy['command'] = taskcopy['command'].format(*arg)
            yield taskcopy
    elif 'file' in task_factory:
        for file in _get_storage_entities(task_factory, storage_settings):
            taskcopy = copy.copy(base_task_copy)
            if file.is_blob:
                # generate a resource file
                if 'resource_files' not in taskcopy:
                    taskcopy['resource_files'] = []
                else:
                    taskcopy['resource_files'] = copy.deepcopy(
                        base_task_copy['resource_files'])
                taskcopy['resource_files'].append(
                    {
                        'file_path': file.task_filepath,
                        'blob_source': '{}?{}'.format(file.url, file.sas),
                    }
                )
            else:
                # generate an azure_storage data ingress
                if 'input_data' not in taskcopy:
                    taskcopy['input_data'] = {}
                if 'azure_storage' not in taskcopy['input_data']:
                    taskcopy['input_data']['azure_storage'] = []
                else:
                    taskcopy['input_data']['azure_storage'] = copy.deepcopy(
                        base_task_copy['input_data']['azure_storage'])
                taskcopy['input_data']['azure_storage'].append(
                    {
                        'storage_account_settings':
                        storage_settings.storage_link_name,
                        'remote_path': file.file_path_with_container,
                        'local_path': '$AZ_BATCH_TASK_WORKING_DIR/{}'.format(
                            file.task_filepath),
                        'is_file_share': True,
                        'blobxfer_extra_options': '--rename',
                    }
                )
            # transform command
            taskcopy['command'] = taskcopy['command'].format(
                url=file.url,
                file_path_with_container=file.file_path_with_container,
                file_path=file.file_path,
                file_name=file.file_name,
                file_name_no_extension=file.file_name_no_extension,
            )
            yield taskcopy
    elif 'repeat' in task_factory:
        for _ in range(0, task_factory['repeat']):
            taskcopy = copy.copy(base_task_copy)
            yield taskcopy
    elif 'random' in task_factory:
        try:
            numgen = task_factory['random']['generate']
        except KeyError:
            raise ValueError(
                'must specify a "generate" property for a random task_factory')
        rfunc = _prepare_random_task_factory(task_factory)
        # generate tasks using rfunc
        for _ in range(0, numgen):
            taskcopy = copy.copy(base_task_copy)
            taskcopy['command'] = taskcopy['command'].format(rfunc())
            yield taskcopy
    elif 'parametric_sweep' in task_factory:
        sweep = task['task_factory']['parametric_sweep']
        if 'product' in sweep:
            product = []
            for chain in sweep['product']:
                product.append(
                    range(
                        chain['start'],
                        chain['stop'],
                        chain['step']
                    )
                )
            for arg in itertools.product(*product):
                taskcopy = copy.copy(base_task_copy)
                taskcopy['command'] = taskcopy['command'].format(*arg)
                yield taskcopy
        elif 'product_iterables' in sweep:
            product = []
            for chain in sweep['product_iterables']:
                product.append(chain)
            for arg in itertools.product(*product):
                taskcopy = copy.copy(base_task_copy)
                taskcopy['command'] = taskcopy['command'].format(*arg)
                yield taskcopy
        elif 'combinations' in sweep:
            iterable = sweep['combinations']['iterable']
            try:
                if sweep['combinations']['replacement']:
                    func = itertools.combinations_with_replacement
                else:
                    func = itertools.combinations
            except KeyError:
                func = itertools.combinations
            for arg in func(iterable, sweep['combinations']['length']):
                taskcopy = copy.copy(base_task_copy)
                taskcopy['command'] = taskcopy['command'].format(*arg)
                yield taskcopy
        elif 'permutations' in sweep:
            iterable = sweep['permutations']['iterable']
            for arg in itertools.permutations(
                    iterable, sweep['permutations']['length']):
                taskcopy = copy.copy(base_task_copy)
                taskcopy['command'] = taskcopy['command'].format(*arg)
                yield taskcopy
        elif 'zip' in sweep:
            iterables = sweep['zip']
            for arg in zip(*iterables):
                taskcopy = copy.copy(base_task_copy)
                taskcopy['command'] = taskcopy['command'].format(*arg)
                yield taskcopy
        else:
            raise ValueError('unknown parametric sweep type: {}'.format(sweep))
    elif 'autogenerated_task_id' in task_factory:
        pass
    else:
        raise ValueError('unknown task factory type: {}'.format(task_factory))
