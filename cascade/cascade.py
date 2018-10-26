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
import datetime
import hashlib
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
import shutil
import subprocess
import sys
import threading
import time
from typing import Tuple
# non-stdlib imports
import azure.common
import azure.cosmosdb.table as azuretable
import azure.storage.blob as azureblob
try:
    import libtorrent
    _LIBTORRENT_IMPORTED = True
except ImportError:
    _LIBTORRENT_IMPORTED = False

# create logger
logger = logging.getLogger('cascade')
# global defines
_ON_WINDOWS = sys.platform == 'win32'
_DEFAULT_PORT_BEGIN = 6881
_DEFAULT_PORT_END = 6891
_DOCKER_TAG = 'docker:'
_SINGULARITY_TAG = 'singularity:'
_TORRENT_STATE = [
    'queued', 'checking', 'downloading metadata', 'downloading', 'finished',
    'seeding', 'allocating', 'checking fastresume'
]
_TORRENT_SESSION = None
_NODEID = os.environ['AZ_BATCH_NODE_ID']
_NODE_ROOT_DIR = os.environ['AZ_BATCH_NODE_ROOT_DIR']
_TEMP_MOUNT_DIR = pathlib.Path(_NODE_ROOT_DIR, '..', '..').resolve()
try:
    _SINGULARITY_CACHE_DIR = pathlib.Path(os.environ['SINGULARITY_CACHEDIR'])
except KeyError:
    _SINGULARITY_CACHE_DIR = None
_TORRENT_DIR = pathlib.Path(_NODE_ROOT_DIR, 'torrents')
try:
    _AZBATCH_USER = pwd.getpwnam('_azbatch')
except NameError:
    _AZBATCH_USER = None
_PARTITION_KEY = None
_MAX_VMLIST_PROPERTIES = 13
_MAX_VMLIST_IDS_PER_PROPERTY = 800
_LR_LOCK_ASYNC = asyncio.Lock()
_PT_LOCK = threading.Lock()
_DIRECTDL_LOCK = threading.Lock()
_ENABLE_P2P = True
_CONCURRENT_DOWNLOADS_ALLOWED = 10
_COMPRESSION = True
_SEED_BIAS = 3
_SAVELOAD_FILE_EXTENSION = 'tar.gz'
_RECORD_PERF = int(os.getenv('SHIPYARD_TIMING', default='0'))
# mutable global state
_CBHANDLES = {}
_BLOB_LEASES = {}
_DHT_ROUTERS = []
_PREFIX = None
_STORAGE_CONTAINERS = {
    'blob_globalresources': None,
    'blob_torrents': None,
    'table_dht': None,
    'table_torrentinfo': None,
    'table_images': None,
    'table_globalresources': None,
}
_TORRENTS = {}
_PENDING_TORRENTS = {}
_TORRENT_REVERSE_LOOKUP = {}
_DIRECTDL_QUEUE = queue.Queue()
_DIRECTDL_DOWNLOADING = set()
_GR_DONE = False
_LAST_DHT_INFO_DUMP = None
_THREAD_EXCEPTIONS = []
_DOCKER_PULL_ERRORS = frozenset((
    'toomanyrequests',
    'connection reset by peer',
    'error pulling image configuration',
    'error parsing http 404 response body',
    'received unexpected http status',
    'tls handshake timeout',
))


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


def _setup_logger() -> None:
    """Set up logger"""
    logger.setLevel(logging.DEBUG)
    logloc = pathlib.Path(
        os.environ['AZ_BATCH_TASK_WORKING_DIR'],
        'cascade.log')
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
    _STORAGE_CONTAINERS['blob_torrents'] = '-'.join(
        (sep + 'tor', batchaccount, poolid))
    _STORAGE_CONTAINERS['table_dht'] = sep + 'dht'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
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
    proc = await asyncio.subprocess.create_subprocess_shell(
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


def generate_torrent(incl_file: pathlib.Path, resource_hash: str) -> dict:
    """Generate torrent file for a given file and write it to disk
    :param pathlib.Path incl_file: file to include in torrent
    :param str resource_hash: resource hash
    :rtype: tuple
    :return: (torrent file as pathlib, torrent file data sha1 hash)
    """
    fs = libtorrent.file_storage()
    libtorrent.add_files(fs, str(incl_file))
    tor = libtorrent.create_torrent(fs)
    tor.set_creator('libtorrent {}'.format(libtorrent.version))
    libtorrent.set_piece_hashes(tor, str(incl_file.parent))
    torrent = tor.generate()
    torrent_data = libtorrent.bencode(torrent)
    fp = _TORRENT_DIR / '{}.torrent'.format(resource_hash)
    with fp.open('wb') as f:
        f.write(torrent_data)
    return fp, hashlib.sha1(torrent_data).hexdigest()


def create_torrent_session(
        resource: str, save_path: pathlib.Path, seed_mode: bool):
    """Create a torrent session given a torrent file
    :param str resource: torrent resource
    :param pathlib.Path save_path: path to save torrented files to
    :param bool seed_mode: seed mode
    :param list port_range: port range to listen on
    :return: torrent_handle
    """
    torrent_handle = _TORRENT_SESSION.add_torrent({
        'ti': libtorrent.torrent_info(
            str(_TORRENTS[resource]['torrent_file'])),
        'save_path': str(save_path),
        'seed_mode': seed_mode
    })
    logger.info('created torrent session for {} is_seed={}'.format(
        resource, torrent_handle.is_seed()))
    return torrent_handle


def _remove_torrent_from_session(resource: str, torrent_handle) -> None:
    """Remove a torrent from the session
    :param str resource: torrent resource
    :param torrent_handle: torrent handle
    """
    _TORRENT_SESSION.remove_torrent(torrent_handle)
    # wait for removal alert
    retries = 5
    while True:
        alert = _TORRENT_SESSION.pop_alert()
        if not alert:
            retries -= 1
            if retries == 0:
                break
            else:
                time.sleep(1)
                continue
        if isinstance(alert, str):
            logger.warning('received alert: {}'.format(alert))
        else:
            logger.warning('received alert: {}'.format(alert.message()))
    logger.info('removed torrent for {}'.format(resource))


def add_dht_node(ip: str, port: int):
    """Add a node as a DHT router
    :param str ip: ip address of the dht node
    :param int port: port of the dht node
    """
    if ip not in _DHT_ROUTERS:
        _TORRENT_SESSION.add_dht_router(ip, port)
        logger.debug('added {}:{} as dht router'.format(ip, port))
        _DHT_ROUTERS.append(ip)


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
    """Convert a singularity URI to an on disk simg name
    :param str name: Singularity image name
    :rtype: str
    :return: singularity image name on disk
    """
    docker = False
    if name.startswith('shub://'):
        name = name[7:]
    elif name.startswith('docker://'):
        docker = True
        name = name[9:]
        # singularity only uses the final portion
        name = name.split('/')[-1]
    name = name.replace('/', '-')
    if docker:
        name = name.replace(':', '-')
        name = '{}.img'.format(name)
    else:
        idx = name.find(':')
        # for some reason, even tagged images in singularity result in -master?
        if idx != -1:
            name = name[:idx]
        name = '{}-master.simg'.format(name)
    return name


def singularity_image_path_on_disk(name: str) -> pathlib.Path:
    """Get a singularity image path on disk
    :param str name: Singularity image name
    :rtype: pathlib.Path
    :return: singularity image path on disk
    """
    return _SINGULARITY_CACHE_DIR / _singularity_image_name_on_disk(name)


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

    def _pull(self, grtype: str, image: str) -> tuple:
        """Container image pull
        :param str grtype: global resource type
        :param str image: image to pull
        :rtype: tuple
        :return: tuple or return code, stdout, stderr
        """
        if grtype == 'docker':
            proc = subprocess.Popen(
                'docker pull {}'.format(image),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                universal_newlines=True)
        elif grtype == 'singularity':
            proc = subprocess.Popen(
                'singularity pull {}'.format(image),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                universal_newlines=True)
        stdout, stderr = proc.communicate()
        return proc.returncode, stdout, stderr

    def _pull_and_save(self) -> None:
        """Thread main logic for pulling and saving a container image"""
        file = None
        resource_hash = compute_resource_hash(self.resource)
        grtype, image = get_container_image_name_from_resource(self.resource)
        _record_perf('pull-start', 'grtype={},img={}'.format(grtype, image))
        start = datetime.datetime.now()
        logger.info('pulling {} image {}'.format(grtype, image))
        backoff = random.randint(2, 5)
        while True:
            rc, stdout, stderr = self._pull(grtype, image)
            if rc == 0:
                if grtype == 'singularity':
                    # log stderr as return code can be misleading
                    logger.debug('{} image {} pull stderr: {}'.format(
                        grtype, image, stderr))
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
        # save image to seed to torrent
        if _ENABLE_P2P:
            _record_perf('pull-end', 'grtype={},img={},diff={}'.format(
                grtype, image, diff))
            _record_perf('save-start', 'grtype={},img={}'.format(
                grtype, image))
            start = datetime.datetime.now()
            if _COMPRESSION:
                # need to create reproducible compressed tarballs
                # 1. untar image save file
                # 2. re-tar files sorted by name and set mtime/user/group
                #    to known values
                # 3. fast compress with parallel gzip ignoring certain file
                #    properties
                # 4. remove temporary directory
                tmpdir = _TORRENT_DIR / '{}-tmp'.format(resource_hash)
                tmpdir.mkdir(parents=True, exist_ok=True)
                file = _TORRENT_DIR / '{}.{}'.format(
                    resource_hash, _SAVELOAD_FILE_EXTENSION)
                logger.info('saving {} image {} to {} for seeding'.format(
                    grtype, image, file))
                if grtype == 'docker':
                    subprocess.check_call(
                        ('(docker save {} | tar -xf -) '
                         '&& (tar --sort=name --mtime=\'1970-01-01\' '
                         '--owner=0 --group=0 -cf - . '
                         '| pigz --fast -n -T -c > {})').format(image, file),
                        cwd=str(tmpdir), shell=True)
                elif grtype == 'singularity':
                    subprocess.check_call(
                        ('(singularity image.export {} | tar -xf -) '
                         '&& (tar --sort=name --mtime=\'1970-01-01\' '
                         '--owner=0 --group=0 -cf - . '
                         '| pigz --fast -n -T -c > {})').format(image, file),
                        cwd=str(tmpdir), shell=True)
                shutil.rmtree(str(tmpdir), ignore_errors=True)
                del tmpdir
                fsize = file.stat().st_size
            else:
                # tarball generated by image save is not reproducible
                # we need to untar it and torrent the contents instead
                file = _TORRENT_DIR / '{}'.format(resource_hash)
                file.mkdir(parents=True, exist_ok=True)
                logger.info('saving {} image {} to {} for seeding'.format(
                    grtype, image, file))
                if grtype == 'docker':
                    subprocess.check_call(
                        'docker save {} | tar -xf -'.format(image),
                        cwd=str(file), shell=True)
                elif grtype == 'singularity':
                    subprocess.check_call(
                        'singularity image.export {} | tar -xf -'.format(
                            image),
                        cwd=str(file), shell=True)
                fsize = 0
                for entry in scantree(str(file)):
                    if entry.is_file(follow_symlinks=False):
                        fsize += entry.stat().st_size
            diff = (datetime.datetime.now() - start).total_seconds()
            logger.debug('took {} sec to save {} image {} to {}'.format(
                diff, grtype, image, file))
            _record_perf('save-end', 'grtype={},img={},size={},diff={}'.format(
                grtype, image, fsize, diff))
            # generate torrent file
            start = datetime.datetime.now()
            torrent_file, torrent_sha1 = generate_torrent(file, resource_hash)
            # check if blob exists and is non-zero length prior to uploading
            try:
                _bp = self.blob_client.get_blob_properties(
                    _STORAGE_CONTAINERS['blob_torrents'],
                    str(torrent_file.name))
                if _bp.properties.content_length == 0:
                    raise ValueError()
            except Exception:
                self.blob_client.create_blob_from_path(
                    _STORAGE_CONTAINERS['blob_torrents'],
                    str(torrent_file.name), str(torrent_file))
            diff = (datetime.datetime.now() - start).total_seconds()
            logger.debug(
                'took {} sec to generate and upload torrent file: {}'.format(
                    diff, torrent_file))
            start = datetime.datetime.now()
            # add to torrent dict (effectively enqueues for torrent start)
            entity = {
                'PartitionKey': _PARTITION_KEY,
                'RowKey': resource_hash,
                'Resource': self.resource,
                'TorrentFileLocator': '{},{}'.format(
                    _STORAGE_CONTAINERS['blob_torrents'],
                    str(torrent_file.name)),
                'TorrentFileSHA1': torrent_sha1,
                'TorrentIsDir': file.is_dir(),
                'TorrentContentSizeBytes': fsize,
            }
            with _PT_LOCK:
                _PENDING_TORRENTS[self.resource] = {
                    'entity': entity,
                    'torrent_file': torrent_file,
                    'started': False,
                    'seed': True,
                    'loaded': True,
                    'loading': False,
                    'registered': True,
                }
                _TORRENT_REVERSE_LOOKUP[resource_hash] = self.resource
            # wait until torrent has started
            logger.info(
                'waiting for torrent {} to start'.format(self.resource))
            while (self.resource not in _TORRENTS or
                   not _TORRENTS[self.resource]['started']):
                time.sleep(0.1)
            diff = (datetime.datetime.now() - start).total_seconds()
            logger.debug('took {} sec for {} torrent to start'.format(
                diff, self.resource))
        else:
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
        ipaddress: str, nglobalresources: int) -> None:
    """Direct download resource logic
    :param asyncio.BaseEventLoop loop: event loop
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    :param str ipaddress: ip address
    :param int nglobalresources: number of global resources
    """
    # ensure we are not downloading too many sources at once
    with _DIRECTDL_LOCK:
        if len(_DIRECTDL_DOWNLOADING) > _CONCURRENT_DOWNLOADS_ALLOWED:
            return
    # retrieve a resouorce from dl queue
    _start_torrent_list = []
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
        # check if torrent is available for resource
        with _DIRECTDL_LOCK:
            if resource not in _DIRECTDL_DOWNLOADING:
                if _ENABLE_P2P:
                    nseeds = _get_torrent_num_seeds(table_client, resource)
                    if nseeds >= _SEED_BIAS:
                        _start_torrent_list.append(resource)
                        resource = None
                        break
                else:
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
    # start any torrents
    for resource in _start_torrent_list:
        _start_torrent_via_storage(blob_client, table_client, resource)
    del _start_torrent_list
    if resource is None:
        return
    # pull and save container image in thread
    if is_container_resource(resource):
        thr = ContainerImageSaveThread(
            blob_client, table_client, resource, blob_name, nglobalresources)
        thr.start()
    else:
        # TODO download via blob, explode uri to get container/blob
        # use download to path into /tmp and move to _TORRENT_DIR
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
                if prop in entity and _NODEID in entity[prop]:
                    count += 1
        if count == nglobalresources:
            _record_perf(
                'gr-done',
                'nglobalresources={}'.format(nglobalresources))
            _GR_DONE = True
            logger.info('all {} global resources loaded'.format(
                nglobalresources))


def _log_torrent_info(resource: str, th) -> None:
    """Log torrent info
    :param str resource: resource
    :param th: torrent handle
    """
    global _LAST_DHT_INFO_DUMP
    s = th.status()
    if (s.download_rate > 0 or s.upload_rate > 0 or s.num_peers > 0 or
            (1.0 - s.progress) > 1e-6):
        logger.debug(
            ('{name} {file} bytes={bytes} state={state} '
             'completion={completion:.2f}% peers={peers} '
             'down={down:.3f} kB/s up={up:.3f} kB/s'.format(
                 name=_TORRENT_REVERSE_LOOKUP[th.name().split('.')[0]],
                 file=th.name(), bytes=s.total_wanted,
                 state=_TORRENT_STATE[s.state], completion=s.progress * 100,
                 peers=s.num_peers, down=s.download_rate / 1000,
                 up=s.upload_rate / 1000)))
    now = datetime.datetime.utcnow()
    if (_LAST_DHT_INFO_DUMP is None or
            now > _LAST_DHT_INFO_DUMP + datetime.timedelta(minutes=1)):
        _LAST_DHT_INFO_DUMP = now
        ss = _TORRENT_SESSION.status()
        logger.debug(
            ('dht: running={} globalnodes={} nodes={} node_cache={} '
             'torrents={} incomingconn={} down={} up={}'.format(
                 _TORRENT_SESSION.is_dht_running(), ss.dht_global_nodes,
                 ss.dht_nodes, ss.dht_node_cache, ss.dht_torrents,
                 ss.has_incoming_connections, ss.total_dht_download,
                 ss.total_dht_upload)))


def bootstrap_dht_nodes(
        loop: asyncio.BaseEventLoop,
        table_client: azuretable.TableService,
        ipaddress: str,
        num_attempts: int) -> None:
    """Bootstrap DHT router nodes
    :param asyncio.BaseEventLoop loop: event loop
    :param azuretable.TableService table_client: table client
    :param str ipaddress: ip address
    :param int num_attempts: number of attempts
    """
    found_self = False
    dht_nodes = []
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_dht'],
            filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
    except azure.common.AzureMissingResourceHttpError:
        pass
    else:
        for entity in entities:
            dht_nodes.append((entity['RowKey'], entity['Port']))
            if entity['RowKey'] == ipaddress:
                found_self = True
    if not found_self:
        entity = {
            'PartitionKey': _PARTITION_KEY,
            'RowKey': ipaddress,
            'Port': _DEFAULT_PORT_BEGIN,
        }
        table_client.insert_entity(_STORAGE_CONTAINERS['table_dht'], entity)
        dht_nodes.insert(0, (ipaddress, _DEFAULT_PORT_BEGIN))
    # TODO handle vm/ips no longer in pool
    for node in dht_nodes:
        if len(_DHT_ROUTERS) >= 3:
            break
        add_dht_node(node[0], node[1])
    # ensure at least 3 DHT router nodes if possible
    if len(dht_nodes) < 3:
        num_attempts += 1
        if num_attempts < 600:
            delay = 1
        elif num_attempts < 1200:
            delay = 10
        else:
            delay = 30
        loop.call_later(
            delay, bootstrap_dht_nodes, loop, table_client, ipaddress,
            num_attempts)


class ContainerImageLoadThread(threading.Thread):
    """Container Image Load Thread"""
    def __init__(self, resource):
        """ContainerImageLoadThread ctor
        :param str resource: resource
        """
        threading.Thread.__init__(self)
        self.resource = resource
        _TORRENTS[self.resource]['seed'] = True
        _TORRENTS[self.resource]['loading'] = True

    def run(self) -> None:
        """Main thread run logic"""
        try:
            self._load_image()
        except Exception as ex:
            logger.exception(ex)
            _THREAD_EXCEPTIONS.append(ex)

    def _load_image(self) -> None:
        """Load container image"""
        logger.debug('loading resource: {}'.format(self.resource))
        resource_hash = compute_resource_hash(self.resource)
        grtype, image = get_container_image_name_from_resource(self.resource)
        start = datetime.datetime.now()
        if _COMPRESSION:
            file = _TORRENT_DIR / '{}.{}'.format(
                resource_hash, _SAVELOAD_FILE_EXTENSION)
            logger.info('loading {} image {} from {}'.format(
                grtype, image, file))
            _record_perf('load-start', 'grtype={},img={},size={}'.format(
                grtype, image, file.stat().st_size))
            if grtype == 'docker':
                subprocess.check_call(
                    'pigz -cd {} | docker load'.format(file), shell=True)
            elif grtype == 'singularity':
                imgpath = singularity_image_path_on_disk(image)
                subprocess.check_call(
                    'pigz -cd {} | singularity image.import {}'.format(
                        file, imgpath), shell=True)
        else:
            file = _TORRENT_DIR / '{}'.format(resource_hash)
            logger.info('loading {} image {} from {}'.format(
                grtype, image, file))
            _record_perf('load-start', 'grtype={},img={}'.format(
                grtype, image))
            if grtype == 'docker':
                subprocess.check_call(
                    'tar -cO . | docker load', cwd=str(file), shell=True)
            elif grtype == 'singularity':
                imgpath = singularity_image_path_on_disk(image)
                subprocess.check_call(
                    'tar -cO . | singularity image.import {}', cwd=str(
                        file, imgpath), shell=True)
        diff = (datetime.datetime.now() - start).total_seconds()
        logger.debug(
            'took {} sec to load {} image from {}'.format(diff, grtype, file))
        _record_perf('load-end', 'grtype={},img={},diff={}'.format(
            grtype, image, diff))
        _TORRENTS[self.resource]['loading'] = False
        _TORRENTS[self.resource]['loaded'] = True


async def _load_and_register_async(
        loop: asyncio.BaseEventLoop,
        table_client: azuretable.TableService,
        nglobalresources: int) -> None:
    """Load and register image
    :param asyncio.BaseEventLoop loop: event loop
    :param azuretable.TableService table_client: table client
    :param int nglobalresource: number of global resources
    """
    global _LR_LOCK_ASYNC
    async with _LR_LOCK_ASYNC:
        for resource in _TORRENTS:
            # if torrent is seeding, load container/file and register
            if (_TORRENTS[resource]['started'] and
                    _TORRENTS[resource]['handle'].is_seed()):
                if (not _TORRENTS[resource]['loaded'] and
                        not _TORRENTS[resource]['loading']):
                    # container load image
                    if is_container_resource(resource):
                        thr = ContainerImageLoadThread(resource)
                        thr.start()
                    else:
                        # TODO "load blob" - move to appropriate path
                        raise NotImplementedError()
                # register to services table
                if (not _TORRENTS[resource]['registered'] and
                        _TORRENTS[resource]['loaded'] and
                        not _TORRENTS[resource]['loading']):
                    _merge_service(
                        table_client, resource, nglobalresources)
                    _TORRENTS[resource]['registered'] = True


async def manage_torrents_async(
        loop: asyncio.BaseEventLoop,
        table_client: azuretable.TableService,
        ipaddress: str, nglobalresources: int) -> None:
    """Manage torrents
    :param asyncio.BaseEventLoop loop: event loop
    :param azuretable.TableService table_client: table client
    :param str ipaddress: ip address
    :param int nglobalresource: number of global resources
    """
    global _LR_LOCK_ASYNC, _GR_DONE
    while True:
        # async schedule load and register
        if not _GR_DONE and not _LR_LOCK_ASYNC.locked():
            asyncio.ensure_future(_load_and_register_async(
                loop, table_client, nglobalresources))
        # move pending torrents into torrents
        with _PT_LOCK:
            for pt in _PENDING_TORRENTS:
                _TORRENTS[pt] = _PENDING_TORRENTS[pt]
            _PENDING_TORRENTS.clear()
        # start applicable torrent sessions
        for resource in _TORRENTS:
            if _TORRENTS[resource]['started']:
                # log torrent info
                _log_torrent_info(resource, _TORRENTS[resource]['handle'])
                continue
            seed = _TORRENTS[resource]['seed']
            logger.info(
                ('creating torrent session for {} ipaddress={} '
                 'seed={}').format(resource, ipaddress, seed))
            grtype, image = get_container_image_name_from_resource(resource)
            _TORRENTS[resource]['handle'] = create_torrent_session(
                resource, _TORRENT_DIR, seed)
            await _record_perf_async(
                loop, 'torrent-start', 'grtype={},img={}'.format(
                    grtype, image))
            del image
            # insert torrent into torrentinfo table
            try:
                table_client.insert_entity(
                    _STORAGE_CONTAINERS['table_torrentinfo'],
                    entity=_TORRENTS[resource]['entity'])
            except azure.common.AzureConflictHttpError:
                pass
            # mark torrent as started
            if not _TORRENTS[resource]['started']:
                _TORRENTS[resource]['started'] = True
        # sleep to avoid pinning cpu
        await asyncio.sleep(1)


async def download_monitor_async(
        loop: asyncio.BaseEventLoop,
        blob_client: azureblob.BlockBlobService,
        table_client: azuretable.TableService,
        ipaddress: str, nglobalresources: int) -> None:
    """Download monitor
    :param asyncio.BaseEventLoop loop: event loop
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    :param str ipaddress: ip address
    :param int nglobalresource: number of global resources
    """
    # begin async manage torrent sessions
    if _ENABLE_P2P:
        asyncio.ensure_future(
            manage_torrents_async(
                loop, table_client, ipaddress, nglobalresources)
        )
    while True:
        # check if there are any direct downloads
        if _DIRECTDL_QUEUE.qsize() > 0:
            await _direct_download_resources_async(
                loop, blob_client, table_client, ipaddress, nglobalresources)
        # check for any thread exceptions
        if len(_THREAD_EXCEPTIONS) > 0:
            logger.critical('Thread exceptions encountered, terminating')
            # raise first exception
            raise _THREAD_EXCEPTIONS[0]
        # fixup filemodes/ownership for singularity images
        if (_GR_DONE and _SINGULARITY_CACHE_DIR is not None and
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
        # if not in peer-to-peer mode, allow exit
        if not _ENABLE_P2P and _GR_DONE:
            break
        # sleep to avoid pinning cpu
        await asyncio.sleep(1)


def _get_torrent_num_seeds(
        table_client: azuretable.TableService,
        resource: str) -> int:
    """Get number of torrent seeders via table (for first VmList prop)
    :param azuretable.TableService table_client: table client
    :param int nglobalresource: number of global resources
    :rtype: int
    :return: number of seeds
    """
    numseeds = 0
    try:
        se = table_client.get_entity(
            _STORAGE_CONTAINERS['table_images'],
            _PARTITION_KEY, compute_resource_hash(resource))
    except azure.common.AzureMissingResourceHttpError:
        pass
    else:
        try:
            numseeds = len(se['VmList0'].split(','))
        except KeyError:
            pass
    return numseeds


def _start_torrent_via_storage(
        blob_client: azureblob.BlockBlobService,
        table_client: azuretable.TableService,
        resource: str, entity: dict = None) -> None:
    """Start a torrent via storage entity
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    :param str resource: resource
    :param dict entity: entity
    """
    if not _ENABLE_P2P:
        return
    if entity is None:
        rk = compute_resource_hash(resource)
        # entity may not be populated yet, keep trying until ready
        while True:
            try:
                entity = table_client.get_entity(
                    _STORAGE_CONTAINERS['table_torrentinfo'],
                    _PARTITION_KEY, rk)
                break
            except azure.common.AzureMissingResourceHttpError:
                time.sleep(1)
    # retrive torrent file
    torrent_file = _TORRENT_DIR / '{}.torrent'.format(entity['RowKey'])
    tc, tp = entity['TorrentFileLocator'].split(',')
    blob_client.get_blob_to_path(tc, tp, str(torrent_file))
    # add to pending torrents
    with _PT_LOCK:
        _PENDING_TORRENTS[resource] = {
            'entity': entity,
            'torrent_file': torrent_file,
            'started': False,
            'seed': False,
            'loaded': False,
            'loading': False,
            'registered': False,
        }
        _TORRENT_REVERSE_LOOKUP[entity['RowKey']] = resource


def _check_resource_has_torrent(
        blob_client: azureblob.BlockBlobService,
        table_client: azuretable.TableService,
        resource: str) -> bool:
    """Check if a resource has an associated torrent
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    :param str resource: resource
    :rtype: bool
    :return: if resource has torrent
    """
    if not _ENABLE_P2P:
        return False
    add_to_dict = False
    try:
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_torrentinfo'],
            _PARTITION_KEY, compute_resource_hash(resource))
        numseeds = _get_torrent_num_seeds(table_client, resource)
        if numseeds < _SEED_BIAS:
            add_to_dict = True
    except azure.common.AzureMissingResourceHttpError:
        add_to_dict = True
    if add_to_dict:
        logger.info('adding {} as resource to download'.format(resource))
        _DIRECTDL_QUEUE.put(resource)
        return False
    else:
        logger.info('found torrent for resource {}'.format(resource))
        _start_torrent_via_storage(
            blob_client, table_client, resource, entity)
    return True


def distribute_global_resources(
        loop: asyncio.BaseEventLoop,
        blob_client: azureblob.BlockBlobService,
        table_client: azuretable.TableService,
        ipaddress: str) -> None:
    """Distribute global services/resources
    :param asyncio.BaseEventLoop loop: event loop
    :param azureblob.BlockBlobService blob_client: blob client
    :param azuretable.TableService table_client: table client
    :param str ipaddress: ip address
    """
    # set torrent session port listen
    if _ENABLE_P2P:
        global _TORRENT_SESSION
        # create torrent session
        logger.info('creating torrent session on {}:{}'.format(
            ipaddress, _DEFAULT_PORT_BEGIN))
        _TORRENT_SESSION = libtorrent.session()
        _TORRENT_SESSION.listen_on(_DEFAULT_PORT_BEGIN, _DEFAULT_PORT_END)
        _TORRENT_SESSION.stop_lsd()
        _TORRENT_SESSION.stop_upnp()
        _TORRENT_SESSION.stop_natpmp()
        # bootstrap dht nodes
        bootstrap_dht_nodes(loop, table_client, ipaddress, 0)
        _TORRENT_SESSION.start_dht()
    # get globalresources from table
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_globalresources'],
            filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
    except azure.common.AzureMissingResourceHttpError:
        entities = None
    nentities = 0
    # check torrent info table for resource
    if entities is not None:
        for ent in entities:
            nentities += 1
            if _ENABLE_P2P:
                _check_resource_has_torrent(
                    blob_client, table_client, ent['Resource'])
            else:
                _DIRECTDL_QUEUE.put(ent['Resource'])
    if nentities == 0:
        logger.info('no global resources specified')
        return
    # run async func in loop
    loop.run_until_complete(download_monitor_async(
        loop, blob_client, table_client, ipaddress, nentities))


async def _get_ipaddress_async(loop: asyncio.BaseEventLoop) -> str:
    """Get IP address
    :param asyncio.BaseEventLoop loop: event loop
    :rtype: str
    :return: ip address
    """
    if _ON_WINDOWS:
        raise NotImplementedError()
    else:
        proc = await asyncio.subprocess.create_subprocess_shell(
            'ip addr list eth0 | grep "inet " | cut -d\' \' -f6 | cut -d/ -f1',
            stdout=asyncio.subprocess.PIPE, loop=loop)
        output = await proc.communicate()
        return output[0].decode('ascii').strip()


def main():
    """Main function"""
    global _ENABLE_P2P, _CONCURRENT_DOWNLOADS_ALLOWED, _POOL_ID
    # get command-line args
    args = parseargs()
    p2popts = args.p2popts.split(':')
    _ENABLE_P2P = p2popts[0] == 'true'
    _CONCURRENT_DOWNLOADS_ALLOWED = int(p2popts[1])
    logger.info('max concurrent downloads: {}'.format(
        _CONCURRENT_DOWNLOADS_ALLOWED))
    # set p2p options
    if _ENABLE_P2P:
        if not _LIBTORRENT_IMPORTED:
            raise ImportError('No module named \'libtorrent\'')
        global _COMPRESSION, _SEED_BIAS, _SAVELOAD_FILE_EXTENSION
        _COMPRESSION = p2popts[3] == 'true'
        _SEED_BIAS = int(p2popts[2])
        if not _COMPRESSION:
            _SAVELOAD_FILE_EXTENSION = 'tar'
        logger.info('peer-to-peer options: compression={} seedbias={}'.format(
            _COMPRESSION, _SEED_BIAS))
        # create torrent directory
        logger.debug('creating torrent dir: {}'.format(_TORRENT_DIR))
        _TORRENT_DIR.mkdir(parents=True, exist_ok=True)
    del p2popts

    # get event loop
    if _ON_WINDOWS:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    loop.set_debug(True)

    # get ip address if not specified, for local testing only
    if args.ipaddress is None:
        ipaddress = loop.run_until_complete(_get_ipaddress_async(loop))
    else:
        ipaddress = args.ipaddress
    logger.debug('ip address: {}'.format(ipaddress))

    # set up storage names
    _setup_storage_names(args.prefix)
    del args

    # create storage credentials
    blob_client, table_client = _create_credentials()

    # distribute global resources
    distribute_global_resources(loop, blob_client, table_client, ipaddress)


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Cascade: Batch Shipyard P2P File/Image Replicator')
    parser.set_defaults(ipaddress=None)
    parser.add_argument(
        'p2popts',
        help='peer to peer options [enabled:non-p2p concurrent '
        'downloading:seed bias:compression]')
    parser.add_argument(
        '--ipaddress', help='ip address')
    parser.add_argument(
        '--prefix', help='storage container prefix')
    return parser.parse_args()


if __name__ == '__main__':
    _setup_logger()
    main()
