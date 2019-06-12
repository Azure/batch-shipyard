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
import argparse
import asyncio
import base64
import datetime
import enum
import hashlib
import json
import logging
import logging.handlers
import os
import pathlib
try:
    import pwd
except ImportError:
    pass
import queue
import random
import subprocess
import sys
import threading
import time
from typing import Tuple
# non-stdlib imports
import azure.common
import azure.cosmosdb.table as azuretable
import azure.storage.blob as azureblob

logger = None
# global defines
_ON_WINDOWS = sys.platform == 'win32'
_CONTAINER_MODE = None
_DOCKER_CONFIG_FILE = '.docker/config.json'
_DOCKER_TAG = 'docker:'
_SINGULARITY_TAG = 'singularity:'
_NODEID = os.environ['AZ_BATCH_NODE_ID']
_NODE_ROOT_DIR = os.environ['AZ_BATCH_NODE_ROOT_DIR']
try:
    _SINGULARITY_CACHE_DIR = pathlib.Path(os.environ['SINGULARITY_CACHEDIR'])
except KeyError:
    _SINGULARITY_CACHE_DIR = None
try:
    _SINGULARITY_SYPGP_DIR = pathlib.Path(os.environ['SINGULARITY_SYPGPDIR'])
except KeyError:
    _SINGULARITY_SYPGP_DIR = None
try:
    _AZBATCH_USER = pwd.getpwnam('_azbatch')
except NameError:
    _AZBATCH_USER = None
_PARTITION_KEY = None
_MAX_VMLIST_PROPERTIES = 13
_MAX_VMLIST_IDS_PER_PROPERTY = 800
_DOCKER_AUHTS = None
_DOCKER_AUHTS_LOCK = threading.Lock()
_DIRECTDL_LOCK = threading.Lock()
_CONCURRENT_DOWNLOADS_ALLOWED = 10
_RECORD_PERF = int(os.getenv('SHIPYARD_TIMING', default='0'))
# mutable global state
_CBHANDLES = {}
_BLOB_LEASES = {}
_PREFIX = None
_STORAGE_CONTAINERS = {
    'blob_globalresources': None,
    'table_images': None,
    'table_globalresources': None,
}
_DIRECTDL_QUEUE = queue.Queue()
_DIRECTDL_KEY_FINGERPRINT_DICT = dict()
_DIRECTDL_DOWNLOADING = set()
_GR_DONE = False
_THREAD_EXCEPTIONS = []
_DOCKER_PULL_ERRORS = frozenset((
    'toomanyrequests',
    'connection reset by peer',
    'error pulling image configuration',
    'error parsing http 404 response body',
    'received unexpected http status',
    'tls handshake timeout',
))


class ContainerMode(enum.Enum):
    DOCKER = 1
    SINGULARITY = 2


class StandardStreamLogger:
    """Standard Stream Logger"""
    def __init__(self, level):
        """Standard Stream ctor"""
        self.level = level

    def write(self, message: str) -> None:
        """Write a message to the stream
        :param str message: message to write
        """
        if message != '\n':
            self.level(message)

    def flush(self) -> None:
        """Flush stream"""
        self.level(sys.stderr)


def _setup_logger(mode: str, log_dir: str) -> None:
    if not os.path.isdir(log_dir):
        invalid_log_dir = log_dir
        log_dir = os.environ['AZ_BATCH_TASK_WORKING_DIR']
        print('log directory "{}" '.format(invalid_log_dir) +
              'is not valid: using "{}"'.format(log_dir))
    logger_suffix = "" if mode is None else "-{}".format(mode)
    logger_name = 'cascade{}-{}'.format(
        logger_suffix, datetime.datetime.now().strftime('%Y%m%dT%H%M%S'))
    global logger
    logger = logging.getLogger(logger_name)
    """Set up logger"""
    logger.setLevel(logging.DEBUG)
    logloc = pathlib.Path(log_dir, '{}.log'.format(logger_name))
    handler = logging.handlers.RotatingFileHandler(
        str(logloc), maxBytes=10485760, backupCount=5)
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03dZ %(levelname)s %(filename)s::%(funcName)s:'
        '%(lineno)d %(process)d:%(threadName)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # redirect stderr to logger
    sys.stderr = StandardStreamLogger(logger.error)
    logger.info('logger initialized, log file: {}'.format(logloc))


def _setup_storage_names(sep: str) -> None:
    """Set up storage names
    :param str sep: storage container prefix
    """
    global _PARTITION_KEY, _PREFIX
    # transform pool id if necessary
    poolid = os.environ['AZ_BATCH_POOL_ID'].lower()
    autopool = os.environ.get('SHIPYARD_AUTOPOOL', default=None)
    # remove guid portion of pool id if autopool
    if autopool is not None:
        poolid = poolid[:-37]
    # set partition key
    batchaccount = os.environ['AZ_BATCH_ACCOUNT_NAME'].lower()
    _PARTITION_KEY = '{}${}'.format(batchaccount, poolid)
    # set container names
    if sep is None or len(sep) == 0:
        raise ValueError('storage_entity_prefix is invalid')
    _STORAGE_CONTAINERS['blob_globalresources'] = '-'.join(
        (sep + 'gr', batchaccount, poolid))
    _STORAGE_CONTAINERS['table_images'] = sep + 'images'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'gr'
    _PREFIX = sep


def _create_credentials() -> tuple:
    """Create storage credentials
    :rtype: tuple
    :return: (blob_client, table_client)
    """
    sa, ep, sakey = os.environ['SHIPYARD_STORAGE_ENV'].split(':')
    blob_client = azureblob.BlockBlobService(
        account_name=sa,
        account_key=sakey,
        endpoint_suffix=ep)
    table_client = azuretable.TableService(
        account_name=sa,
        account_key=sakey,
        endpoint_suffix=ep)
    return blob_client, table_client


async def _record_perf_async(
        loop: asyncio.BaseEventLoop, event: str, message: str) -> None:
    """Record timing metric async
    :param asyncio.BaseEventLoop loop: event loop
    :param str event: event
    :param str message: message
    """
    if not _RECORD_PERF:
        return
    proc = await asyncio.create_subprocess_shell(
        './perf.py cascade {ev} --prefix {pr} --message "{msg}"'.format(
            ev=event, pr=_PREFIX, msg=message), loop=loop)
    await proc.wait()
    if proc.returncode != 0:
        logger.error(
            'could not record perf to storage for event: {}'.format(event))


def _record_perf(event: str, message: str) -> None:
    """Record timing metric
    :param str event: event
    :param str message: message
    """
    if not _RECORD_PERF:
        return
    subprocess.check_call(
        './perf.py cascade {ev} --prefix {pr} --message "{msg}"'.format(
            ev=event, pr=_PREFIX, msg=message), shell=True)


def _renew_blob_lease(
        loop: asyncio.BaseEventLoop,
        blob_client: azureblob.BlockBlobService,
        container_key: str, resource: str, blob_name: str):
    """Renew a storage blob lease
    :param asyncio.BaseEventLoop loop: event loop
    :param azureblob.BlockBlobService blob_client: blob client
    :param str container_key: blob container index into _STORAGE_CONTAINERS
    :param str resource: resource
    :param str blob_name: blob name
    """
    try:
        lease_id = blob_client.renew_blob_lease(
            container_name=_STORAGE_CONTAINERS[container_key],
            blob_name=blob_name,
            lease_id=_BLOB_LEASES[resource],
        )
    except azure.common.AzureException as e:
        logger.exception(e)
        _BLOB_LEASES.pop(resource)
        _CBHANDLES.pop(resource)
    else:
        _BLOB_LEASES[resource] = lease_id
        _CBHANDLES[resource] = loop.call_later(
            15, _renew_blob_lease, loop, blob_client, container_key, resource,
            blob_name)


def scantree(path):
    """Recursively scan a directory tree
    :param str path: path to scan
    :rtype: os.DirEntry
    :return: DirEntry via generator
    """
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path)
        else:
            yield entry


def get_container_image_name_from_resource(resource: str) -> Tuple[str, str]:
    """Get container image from resource id
    :param str resource: resource
    :rtype: tuple
    :return: (type, image name)
    """
    if resource.startswith(_DOCKER_TAG):
        return (
            'docker',
            resource[len(_DOCKER_TAG):]
        )
    elif resource.startswith(_SINGULARITY_TAG):
        return (
            'singularity',
            resource[len(_SINGULARITY_TAG):]
        )
    else:
        raise ValueError('invalid resource: {}'.format(resource))


def is_container_resource(resource: str) -> bool:
    """Check if resource is a container resource
    :param str resource: resource
    :rtype: bool
    :return: is a supported resource
    """
    if (resource.startswith(_DOCKER_TAG) or
            resource.startswith(_SINGULARITY_TAG)):
        return True
    return False


def compute_resource_hash(resource: str) -> str:
    """Calculate compute resource hash
    :param str resource: resource
    :rtype: str
    :return: hash of resource
    """
    return hashlib.sha1(resource.encode('utf8')).hexdigest()


def _singularity_image_name_on_disk(name: str) -> str:
    """Convert a singularity URI to an on disk sif name
    :param str name: Singularity image name
    :rtype: str
    :return: singularity image name on disk
    """
    docker = False
    if name.startswith('shub://'):
        name = name[7:]
    elif name.startswith('library://'):
        name = name[10:]
    elif name.startswith('oras://'):
        name = name[7:]
    elif name.startswith('docker://'):
        docker = True
        name = name[9:]
        # singularity only uses the final portion
        name = name.split('/')[-1]
    name = name.replace('/', '-')
    if docker:
        name = name.replace(':', '-')
        name = '{}.sif'.format(name)
    else:
        tmp = name.split(':')
        if len(tmp) > 1:
            name = '{}_{}.sif'.format(tmp[0], tmp[1])
        else:
            name = '{}_latest.sif'.format(name)
    return name


def singularity_image_path_on_disk(name: str) -> pathlib.Path:
    """Get a singularity image path on disk
    :param str name: Singularity image name
    :rtype: pathlib.Path
    :return: singularity image path on disk
    """
    return _SINGULARITY_CACHE_DIR / _singularity_image_name_on_disk(name)


def singularity_image_name_to_key_file_name(name: str) -> str:
    """Convert a singularity image to its key file name
    :param str name: Singularity image name
    :rtype: str
    :return: key file name of the singularity image
    """
    hash_image_name = compute_resource_hash(name)
    key_file_name = 'public-{}.asc'.format(hash_image_name)
    return key_file_name


class ContainerImageSaveThread(threading.Thread):
    """Container Image Save Thread"""
    def __init__(
            self, blob_client: azureblob.BlockBlobService,
            table_client: azuretable.TableService,
            resource: str, blob_name: str, nglobalresources: int):
        """ContainerImageSaveThread ctor
        :param azureblob.BlockBlobService blob_client: blob client
        :param azuretable.TableService table_client: table client
        :param str resource: resource
        :param str blob_name: resource blob name
        :param int nglobalresources: number of global resources
        """
        threading.Thread.__init__(self)
        self.blob_client = blob_client
        self.table_client = table_client
        self.resource = resource
        self.blob_name = blob_name
        self.nglobalresources = nglobalresources
        # add to downloading set
        with _DIRECTDL_LOCK:
            _DIRECTDL_DOWNLOADING.add(self.resource)

    def run(self) -> None:
        """Thread main run function"""
        try:
            self._pull_and_save()
        except Exception as ex:
            logger.exception(ex)
            _THREAD_EXCEPTIONS.append(ex)
        finally:
            # cancel callback
            try:
                _CBHANDLES[self.resource].cancel()
            except KeyError as e:
                logger.exception(e)
            _CBHANDLES.pop(self.resource)
            # release blob lease
            try:
                self.blob_client.release_blob_lease(
                    container_name=_STORAGE_CONTAINERS['blob_globalresources'],
                    blob_name=self.blob_name,
                    lease_id=_BLOB_LEASES[self.resource],
                )
            except azure.common.AzureException as e:
                logger.exception(e)
            _BLOB_LEASES.pop(self.resource)
            logger.debug(
                'blob lease released for {}'.format(self.resource))
            # remove from downloading set
            with _DIRECTDL_LOCK:
                _DIRECTDL_DOWNLOADING.remove(self.resource)

    def _check_pull_output_overload(self, stderr: str) -> bool:
        """Check output for registry overload errors
        :param str stderr: stderr
        :rtype: bool
        :return: if error appears to be overload from registry
        """
        return any([x in stderr for x in _DOCKER_PULL_ERRORS])

    def _get_singularity_credentials(self, image: str) -> tuple:
        """Get the username and the password of the registry of a given
        Singularity image
        :param str image: image for which we want the username and the
        password
        :rtype: tuple
        :return: username and password
        """
        global _DOCKER_AUHTS
        registry_type, _, image_name = image.partition('://')
        if registry_type != 'docker' and registry_type != 'oras':
            return None, None
        docker_config_data = {}
        with _DOCKER_AUHTS_LOCK:
            if _DOCKER_AUHTS is None:
                with open(_DOCKER_CONFIG_FILE) as docker_config_file:
                    docker_config_data = json.load(docker_config_file)
                try:
                    _DOCKER_AUHTS = docker_config_data['auths']
                except KeyError:
                    _DOCKER_AUHTS = {}
        registry = image_name.partition('/')[0]
        try:
            b64auth = _DOCKER_AUHTS[registry]['auth']
        except KeyError:
            return None, None
        auth = base64.b64decode(b64auth).decode('utf-8')
        username, _, password = auth.partition(':')
        return username, password

    def _get_singularity_pull_cmd(self, image: str) -> str:
        """Get singularity pull command
        :param str image: image to pull
        :rtype: str
        :return: pull command for the singularity image
        """
        # if we have a key_fingerprint we need to pull
        # the key to our keyring
        image_out_path = singularity_image_path_on_disk(image)
        key_file_path = pathlib.Path(
            singularity_image_name_to_key_file_name(image))
        username, password = self._get_singularity_credentials(image)
        if username is not None and password is not None:
            credentials_command_argument = (
                '--docker-username {} --docker-password {} '.format(
                    username, password))
        else:
            credentials_command_argument = ''
        if image in _DIRECTDL_KEY_FINGERPRINT_DICT:
            singularity_pull_cmd = (
                'singularity pull -F ' +
                credentials_command_argument +
                '{} {}'.format(image_out_path, image))
            key_fingerprint = _DIRECTDL_KEY_FINGERPRINT_DICT[image]
            if key_file_path.is_file():
                key_import_cmd = ('singularity key import {}'
                                  .format(key_file_path))
                fingerprint_check_cmd = (
                    'key_fingerprint=$({} | '.format(key_import_cmd) +
                    'grep -o "fingerprint \\(\\S*\\)" | ' +
                    'grep -o "\\S*$" | sed -e "s/\\(.*\\)/\\U\\1/"); ' +
                    'if [ ${key_fingerprint} != ' +
                    '"{}" ]; '.format(key_fingerprint.upper()) +
                    'then (>&2 echo "aborting: fingerprint of ' +
                    'key file $key_fingerprint does not match ' +
                    'fingerprint provided {}")'.format(key_fingerprint) +
                    ' && exit 1; fi')
                cmd = (key_import_cmd + ' && ' + fingerprint_check_cmd +
                       ' && ' + singularity_pull_cmd)
            else:
                key_pull_cmd = ('singularity key pull {}'
                                .format(key_fingerprint))
                cmd = key_pull_cmd + ' && ' + singularity_pull_cmd
            # if the image pulled from oras we need to manually
            # verify the image
            if image.startswith('oras://'):
                singularity_verify_cmd = ('singularity verify {}'
                                          .format(image_out_path))
                cmd = cmd + ' && ' + singularity_verify_cmd
        else:
            cmd = ('singularity pull -U -F ' +
                   credentials_command_argument +
                   '{} {}'.format(image_out_path, image))
        return cmd

    def _pull(self, grtype: str, image: str) -> tuple:
        """Container image pull
        :param str grtype: global resource type
        :param str image: image to pull
        :rtype: tuple
        :return: tuple or return code, stdout, stderr
        """
        if grtype == 'docker':
            cmd = 'docker pull {}'.format(image)
        elif grtype == 'singularity':
            cmd = self._get_singularity_pull_cmd(image)
        logger.debug('pulling command: {}'.format(cmd))
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True)
        stdout, stderr = proc.communicate()
        return proc.returncode, stdout, stderr

    def _pull_and_save(self) -> None:
        """Thread main logic for pulling and saving a container image"""
        grtype, image = get_container_image_name_from_resource(self.resource)
        _record_perf('pull-start', 'grtype={},img={}'.format(grtype, image))
        start = datetime.datetime.now()
        logger.info('pulling {} image {}'.format(grtype, image))
        backoff = random.randint(2, 5)
        while True:
            rc, stdout, stderr = self._pull(grtype, image)
            if rc == 0:
                break
            elif self._check_pull_output_overload(stderr.lower()):
                logger.error(
                    'Too many requests issued to registry server, '
                    'retrying...')
                backoff = backoff << 1
                endbackoff = backoff << 1
                if endbackoff >= 300:
                    endbackoff = 300
                    if backoff > endbackoff:
                        backoff = endbackoff
                time.sleep(random.randint(backoff, endbackoff))
                # reset if backoff reaches 5 min
                if backoff >= 300:
                    backoff = random.randint(2, 5)
            else:
                raise RuntimeError(
                    '{} pull failed: stdout={} stderr={}'.format(
                        grtype, stdout, stderr))
        diff = (datetime.datetime.now() - start).total_seconds()
        logger.debug('took {} sec to pull {} image {}'.format(
            diff, grtype, image))
        # register service
        _merge_service(
            self.table_client, self.resource, self.nglobalresources)
        # get image size
        try:
            if grtype == 'docker':
                output = subprocess.check_output(
                    'docker images {}'.format(image), shell=True)
                size = ' '.join(output.decode('utf-8').split()[-2:])
            elif grtype == 'singularity':
                imgpath = singularity_image_path_on_disk(image)
                size = imgpath.stat().st_size
            _record_perf(
                'pull-end', 'grtype={},img={},diff={},size={}'.format(
                    grtype, image, diff, size))
        except subprocess.CalledProcessError as ex:
            logger.exception(ex)
            _record_perf('pull-end', 'grtype={},img={},diff={}'.format(
                grtype, image, diff))


async def _direct_download_resources_async(
        loop: asyncio.BaseEventLoop,
        blob_client: azureblob.BlockBlobService,
        table_client: azuretable.TableService,
        nglobalresources: int) -> None:
    """Direct download resource logic
    :param asyncio.BaseEventLoop loop: event loop
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    :param int nglobalresources: number of global resources
    """
    # ensure we are not downloading too many sources at once
    with _DIRECTDL_LOCK:
        if len(_DIRECTDL_DOWNLOADING) > _CONCURRENT_DOWNLOADS_ALLOWED:
            return
    # retrieve a resource from dl queue
    _seen = set()
    while True:
        try:
            resource = _DIRECTDL_QUEUE.get()
        except queue.Empty:
            break
        else:
            if resource in _seen:
                _DIRECTDL_QUEUE.put(resource)
                resource = None
                break
            _seen.add(resource)
        with _DIRECTDL_LOCK:
            if resource not in _DIRECTDL_DOWNLOADING:
                break
            else:
                _DIRECTDL_QUEUE.put(resource)
                resource = None
    del _seen
    # attempt to get a blob lease
    if resource is not None:
        lease_id = None
        blob_name = None
        for i in range(0, _CONCURRENT_DOWNLOADS_ALLOWED):
            blob_name = '{}.{}'.format(compute_resource_hash(resource), i)
            try:
                lease_id = blob_client.acquire_blob_lease(
                    container_name=_STORAGE_CONTAINERS['blob_globalresources'],
                    blob_name=blob_name,
                    lease_duration=60,
                )
                break
            except azure.common.AzureConflictHttpError:
                blob_name = None
                pass
        if lease_id is None:
            logger.debug(
                'no available blobs to lease for resource: {}'.format(
                    resource))
            _DIRECTDL_QUEUE.put(resource)
            return
        # create lease renew callback
        logger.debug('blob lease {} acquired for resource {}'.format(
            lease_id, resource))
        _BLOB_LEASES[resource] = lease_id
        _CBHANDLES[resource] = loop.call_later(
            15, _renew_blob_lease, loop, blob_client, 'blob_globalresources',
            resource, blob_name)
    if resource is None:
        return
    # pull and save container image in thread
    if is_container_resource(resource):
        thr = ContainerImageSaveThread(
            blob_client, table_client, resource, blob_name, nglobalresources)
        thr.start()
    else:
        # TODO download via blob, explode uri to get container/blob
        # use download to path into /tmp and move to directory
        raise NotImplementedError()


def _merge_service(
        table_client: azuretable.TableService,
        resource: str, nglobalresources: int) -> None:
    """Merge entity to services table
    :param azuretable.TableService table_client: table client
    :param str resource: resource to add to services table
    :param int nglobalresources: number of global resources
    """
    # merge service into services table
    entity = {
        'PartitionKey': _PARTITION_KEY,
        'RowKey': compute_resource_hash(resource),
        'Resource': resource,
        'VmList0': _NODEID,
    }
    logger.debug('merging entity {} to services table'.format(entity))
    try:
        table_client.insert_entity(
            _STORAGE_CONTAINERS['table_images'], entity=entity)
    except azure.common.AzureConflictHttpError:
        while True:
            entity = table_client.get_entity(
                _STORAGE_CONTAINERS['table_images'],
                entity['PartitionKey'], entity['RowKey'])
            # merge VmList into entity
            evms = []
            for i in range(0, _MAX_VMLIST_PROPERTIES):
                prop = 'VmList{}'.format(i)
                if prop in entity:
                    evms.extend(entity[prop].split(','))
            if _NODEID in evms:
                break
            evms.append(_NODEID)
            for i in range(0, _MAX_VMLIST_PROPERTIES):
                prop = 'VmList{}'.format(i)
                start = i * _MAX_VMLIST_IDS_PER_PROPERTY
                end = start + _MAX_VMLIST_IDS_PER_PROPERTY
                if end > len(evms):
                    end = len(evms)
                if start < end:
                    entity[prop] = ','.join(evms[start:end])
                else:
                    entity[prop] = None
            etag = entity['etag']
            entity.pop('etag')
            try:
                table_client.merge_entity(
                    _STORAGE_CONTAINERS['table_images'], entity=entity,
                    if_match=etag)
                break
            except azure.common.AzureHttpError as ex:
                if ex.status_code != 412:
                    raise
    logger.info('entity {} merged to services table'.format(entity))
    global _GR_DONE
    if not _GR_DONE:
        try:
            entities = table_client.query_entities(
                _STORAGE_CONTAINERS['table_images'],
                filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
        except azure.common.AzureMissingResourceHttpError:
            entities = []
        count = 0
        for entity in entities:
            for i in range(0, _MAX_VMLIST_PROPERTIES):
                prop = 'VmList{}'.format(i)
                mode_prefix = _CONTAINER_MODE.name.lower() + ':'
                if (prop in entity and _NODEID in entity[prop] and
                   entity['Resource'].startswith(mode_prefix)):
                    count += 1
        if count == nglobalresources:
            _record_perf(
                'gr-done',
                'nglobalresources={}'.format(nglobalresources))
            _GR_DONE = True
            logger.info('all {} global resources of container mode "{}" loaded'
                        .format(nglobalresources,
                                _CONTAINER_MODE.name.lower()))
        else:
            logger.info('{}/{} global resources of container mode "{}" loaded'
                        .format(count, nglobalresources,
                                _CONTAINER_MODE.name.lower()))


async def download_monitor_async(
        loop: asyncio.BaseEventLoop,
        blob_client: azureblob.BlockBlobService,
        table_client: azuretable.TableService,
        nglobalresources: int) -> None:
    """Download monitor
    :param asyncio.BaseEventLoop loop: event loop
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    :param int nglobalresource: number of global resources
    """
    while not _GR_DONE:
        # check if there are any direct downloads
        if _DIRECTDL_QUEUE.qsize() > 0:
            await _direct_download_resources_async(
                loop, blob_client, table_client, nglobalresources)
        # check for any thread exceptions
        if len(_THREAD_EXCEPTIONS) > 0:
            logger.critical('Thread exceptions encountered, terminating')
            # raise first exception
            raise _THREAD_EXCEPTIONS[0]
        # sleep to avoid pinning cpu
        await asyncio.sleep(1)
    # fixup filemodes/ownership for singularity images
    if (_SINGULARITY_CACHE_DIR is not None and
            _AZBATCH_USER is not None):
        if _SINGULARITY_CACHE_DIR.exists():
            logger.info('chown all files in {}'.format(
                _SINGULARITY_CACHE_DIR))
            for file in scantree(str(_SINGULARITY_CACHE_DIR)):
                os.chown(
                    str(file.path),
                    _AZBATCH_USER[2],
                    _AZBATCH_USER[3]
                )
        else:
            logger.warning(
                'singularity cache dir {} does not exist'.format(
                    _SINGULARITY_CACHE_DIR))
    # fixup filemodes/ownership for singularity keys
    if (_SINGULARITY_SYPGP_DIR is not None and
            _AZBATCH_USER is not None):
        if _SINGULARITY_SYPGP_DIR.exists():
            logger.info('chown all files in {}'.format(
                _SINGULARITY_SYPGP_DIR))
            for file in scantree(str(_SINGULARITY_SYPGP_DIR)):
                os.chown(
                    str(file.path),
                    _AZBATCH_USER[2],
                    _AZBATCH_USER[3]
                )
        else:
            logger.warning(
                'singularity sypgp dir {} does not exist'.format(
                    _SINGULARITY_SYPGP_DIR))


def distribute_global_resources(
        loop: asyncio.BaseEventLoop,
        blob_client: azureblob.BlockBlobService,
        table_client: azuretable.TableService) -> None:
    """Distribute global services/resources
    :param asyncio.BaseEventLoop loop: event loop
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    """
    # get globalresources from table
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_globalresources'],
            filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
    except azure.common.AzureMissingResourceHttpError:
        entities = []
    nentities = 0
    for ent in entities:
        resource = ent['Resource']
        grtype, image = get_container_image_name_from_resource(resource)
        if grtype == _CONTAINER_MODE.name.lower():
            nentities += 1
            _DIRECTDL_QUEUE.put(resource)
            key_fingerprint = ent.get('KeyFingerprint', None)
            if key_fingerprint is not None:
                _DIRECTDL_KEY_FINGERPRINT_DICT[image] = key_fingerprint
        else:
            logger.info('skipping resource {}:'.format(resource) +
                        'not matching container mode "{}"'
                        .format(_CONTAINER_MODE.name.lower()))
    if nentities == 0:
        logger.info('no global resources specified')
        return
    logger.info('{} global resources matching container mode "{}"'
                .format(nentities, _CONTAINER_MODE.name.lower()))
    # run async func in loop
    loop.run_until_complete(download_monitor_async(
        loop, blob_client, table_client, nentities))


def main():
    """Main function"""
    # get command-line args
    args = parseargs()

    _setup_logger(args.mode, args.log_directory)

    global _CONCURRENT_DOWNLOADS_ALLOWED, _CONTAINER_MODE

    # set up concurrent source downloads
    if args.concurrent is None:
        raise ValueError('concurrent source downloads is not specified')
    try:
        _CONCURRENT_DOWNLOADS_ALLOWED = int(args.concurrent)
    except ValueError:
        _CONCURRENT_DOWNLOADS_ALLOWED = None
    if (_CONCURRENT_DOWNLOADS_ALLOWED is None or
            _CONCURRENT_DOWNLOADS_ALLOWED <= 0):
        raise ValueError('concurrent source downloads is invalid: {}'
                         .format(args.concurrent))
    logger.info('max concurrent downloads: {}'.format(
        _CONCURRENT_DOWNLOADS_ALLOWED))

    # get event loop
    if _ON_WINDOWS:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    loop.set_debug(True)

    # set up container mode
    if args.mode is None:
        raise ValueError('container mode is not specified')
    if args.mode == 'docker':
        _CONTAINER_MODE = ContainerMode.DOCKER
    elif args.mode == 'singularity':
        _CONTAINER_MODE = ContainerMode.SINGULARITY
    else:
        raise ValueError('container mode is invalid: {}'.format(args.mode))
    logger.info('container mode: {}'.format(_CONTAINER_MODE.name))

    # set up storage names
    _setup_storage_names(args.prefix)
    del args

    # create storage credentials
    blob_client, table_client = _create_credentials()

    # distribute global resources
    distribute_global_resources(loop, blob_client, table_client)


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Cascade: Batch Shipyard File/Image Replicator')
    parser.set_defaults(concurrent=None, mode=None)
    parser.add_argument(
        '--concurrent',
        help='concurrent source downloads')
    parser.add_argument(
        '--mode', help='container mode (docker/singularity)')
    parser.add_argument(
        '--prefix', help='storage container prefix')
    parser.add_argument(
        '--log-directory', help='directory to store log files')
    return parser.parse_args()


if __name__ == '__main__':
    main()
