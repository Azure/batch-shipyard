#!/usr/bin/env python3

# stdlib imports
import argparse
import asyncio
import datetime
import hashlib
import logging
import logging.handlers
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
# non-stdlib imports
import azure.common
import azure.storage.blob as azureblob
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable
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
_TORRENT_STATE = [
    'queued', 'checking', 'downloading metadata', 'downloading', 'finished',
    'seeding', 'allocating', 'checking fastresume'
]
_TORRENT_SESSION = None
_BATCHACCOUNT = os.environ['AZ_BATCH_ACCOUNT_NAME']
_POOLID = os.environ['AZ_BATCH_POOL_ID']
_NODEID = os.environ['AZ_BATCH_NODE_ID']
_SHARED_DIR = os.environ['AZ_BATCH_NODE_SHARED_DIR']
_TORRENT_DIR = pathlib.Path(_SHARED_DIR, '.torrents')
_PARTITION_KEY = '{}${}'.format(_BATCHACCOUNT, _POOLID)
_LR_LOCK_ASYNC = asyncio.Lock()
_PT_LOCK = threading.Lock()
_DIRECTDL_LOCK = threading.Lock()
_ENABLE_P2P = True
_NON_P2P_CONCURRENT_DOWNLOADING = True
_COMPRESSION = True
_SEED_BIAS = 3
_ALLOW_PUBLIC_PULL_WITH_PRIVATE = False
_SAVELOAD_FILE_EXTENSION = 'tar.gz'
_REGISTRY = None
# mutable global state
_CBHANDLES = {}
_QUEUE_MESSAGES = {}
_DHT_ROUTERS = []
_PREFIX = None
_STORAGE_CONTAINERS = {
    'blob_torrents': None,
    'table_dht': None,
    'table_registry': None,
    'table_torrentinfo': None,
    'table_services': None,
    'table_globalresources': None,
    'queue_globalresources': None,
}
_TORRENTS = {}
_PENDING_TORRENTS = {}
_TORRENT_REVERSE_LOOKUP = {}
_DIRECTDL = []
_DIRECTDL_DOWNLOADING = []
_GR_DONE = False
_LAST_DHT_INFO_DUMP = None


def _setup_logger():
    """Set up logger"""
    logger.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(
        'cascade.log', maxBytes=10485760, backupCount=5)
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03dZ %(levelname)s %(filename)s::%(funcName)s:'
        '%(lineno)d %(process)d:%(threadName)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info('logger initialized')


def _setup_container_names(sep: str):
    """Set up storage container names
    :param str sep: storage container prefix
    """
    if sep is None:
        sep = ''
    _STORAGE_CONTAINERS['blob_torrents'] = '-'.join(
        (sep + 'torrents', _BATCHACCOUNT.lower(), _POOLID.lower()))
    _STORAGE_CONTAINERS['table_dht'] = sep + 'dht'
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    _STORAGE_CONTAINERS['table_services'] = sep + 'services'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'globalresources'
    _STORAGE_CONTAINERS['queue_globalresources'] = '-'.join(
        (sep + 'globalresources', _BATCHACCOUNT.lower(), _POOLID.lower()))
    global _PREFIX
    _PREFIX = sep


def _create_credentials() -> tuple:
    """Create storage credentials
    :rtype: tuple
    :return: (blob_client, queue_client, table_client)
    """
    sa, ep, sakey = os.environ['CASCADE_STORAGE_ENV'].split(':')
    blob_client = azureblob.BlockBlobService(
        account_name=sa,
        account_key=sakey,
        endpoint_suffix=ep)
    queue_client = azurequeue.QueueService(
        account_name=sa,
        account_key=sakey,
        endpoint_suffix=ep)
    table_client = azuretable.TableService(
        account_name=sa,
        account_key=sakey,
        endpoint_suffix=ep)
    return blob_client, queue_client, table_client


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


def add_dht_node(ip: str, port: int):
    """Add a node as a DHT router
    :param str ip: ip address of the dht node
    :param int port: port of the dht node
    """
    if ip not in _DHT_ROUTERS:
        _TORRENT_SESSION.add_dht_router(ip, port)
        logger.debug('added {}:{} as dht router'.format(ip, port))
        _DHT_ROUTERS.append(ip)


def _renew_queue_message_lease(
        loop: asyncio.BaseEventLoop,
        queue_client: azure.storage.queue.QueueService,
        queue_key: str, cb_key: str, msg_id: str):
    """Renew a storage queue message lease
    :param asyncio.BaseEventLoop loop: event loop
    :param azure.storage.queue.QueueService queue_client: queue client
    :param str queue_key: queue name key index into _STORAGE_CONTAINERS
    :param str cb_key: callback handle key
    :param str msg_id: message id
    """
    msg = queue_client.update_message(
        _STORAGE_CONTAINERS[queue_key],
        message_id=msg_id,
        pop_receipt=_QUEUE_MESSAGES[msg_id],
        visibility_timeout=45)
    if msg.pop_receipt is None:
        raise RuntimeError(
            'update message failed for id={} pr={}'.format(
                msg_id, _QUEUE_MESSAGES[msg_id]))
    _QUEUE_MESSAGES[msg_id] = msg.pop_receipt
    _CBHANDLES[cb_key] = loop.call_later(
        15, _renew_queue_message_lease, loop, queue_client, queue_key, cb_key,
        msg_id)


def scantree(path):
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path)
        else:
            yield entry


async def _record_perf_async(loop, event, message):
    proc = await asyncio.subprocess.create_subprocess_shell(
        'perf.py cascade {ev} --prefix {pr} --message "{msg}"'.format(
            ev=event, pr=_PREFIX, msg=message), loop=loop)
    await proc.wait()
    if proc.returncode != 0:
        logger.error(
            'could not record perf to storage for event: {}'.format(event))


def _record_perf(event, message):
    subprocess.check_call(
        'perf.py cascade {ev} --prefix {pr} --message "{msg}"'.format(
            ev=event, pr=_PREFIX, msg=message), shell=True)


class DockerSaveThread(threading.Thread):
    def __init__(
            self, blob_client, queue_client, table_client, resource, msg_id,
            nglobalresources):
        threading.Thread.__init__(self)
        self.blob_client = blob_client
        self.queue_client = queue_client
        self.table_client = table_client
        self.resource = resource
        self.msg_id = msg_id
        self.nglobalresources = nglobalresources
        with _DIRECTDL_LOCK:
            _DIRECTDL_DOWNLOADING.append(self.resource)

    def run(self):
        success = False
        try:
            self._pull_and_load()
            success = True
        except Exception as ex:
            logger.exception(ex)
        finally:
            # cancel callback
            if _ENABLE_P2P or not _NON_P2P_CONCURRENT_DOWNLOADING:
                _CBHANDLES[self.resource].cancel()
                _CBHANDLES.pop(self.resource)
                # release queue message
                self.queue_client.update_message(
                    _STORAGE_CONTAINERS['queue_globalresources'],
                    message_id=self.msg_id,
                    pop_receipt=_QUEUE_MESSAGES[self.msg_id],
                    visibility_timeout=0)
                _QUEUE_MESSAGES.pop(self.msg_id)
                logger.debug(
                    'queue message released for {}'.format(self.resource))
            # remove from downloading list
            if success:
                with _DIRECTDL_LOCK:
                    _DIRECTDL_DOWNLOADING.remove(self.resource)
                    _DIRECTDL.remove(self.resource)

    def _pull_and_load(self):
        if _REGISTRY is None:
            raise RuntimeError(
                ('{} image specified for global resource, but there are '
                 'no registries available').format(self.resource))
        file = None
        resource_hash = hashlib.sha1(self.resource.encode('utf8')).hexdigest()
        image = self.resource[
            self.resource.find(_DOCKER_TAG) + len(_DOCKER_TAG):]
        _record_perf('pull-start', 'img={}'.format(image))
        start = datetime.datetime.now()
        logger.info('pulling image {} from {}'.format(image, _REGISTRY))
        if _REGISTRY == 'registry.hub.docker.com':
            subprocess.check_output(
                'docker pull {}'.format(image), shell=True)
        else:
            _pub = False
            try:
                subprocess.check_output(
                    'docker pull {}/{}'.format(_REGISTRY, image),
                    shell=True)
            except subprocess.CalledProcessError:
                if _ALLOW_PUBLIC_PULL_WITH_PRIVATE:
                    subprocess.check_output(
                        'docker pull {}'.format(image), shell=True)
                    _pub = True
                else:
                    raise
            # tag image to remove registry ip
            if not _pub:
                subprocess.check_call(
                    'docker tag {}/{} {}'.format(_REGISTRY, image, image),
                    shell=True)
            del _pub
        diff = (datetime.datetime.now() - start).total_seconds()
        logger.debug('took {} sec to pull docker image {} from {}'.format(
            diff, image, _REGISTRY))
        # register service
        _merge_service(
            self.table_client, self.resource, self.nglobalresources)
        # save docker image to seed to torrent
        if _ENABLE_P2P:
            _record_perf('pull-end', 'img={},diff={}'.format(
                image, diff))
            _record_perf('save-start', 'img={}'.format(image))
            start = datetime.datetime.now()
            if _COMPRESSION:
                # need to create reproducible compressed tarballs
                # 1. untar docker save file
                # 2. re-tar files sorted by name and set mtime/user/group
                #    to known values
                # 3. fast compress with parallel gzip ignoring certain file
                #    properties
                # 4. remove temporary directory
                tmpdir = _TORRENT_DIR / '{}-tmp'.format(resource_hash)
                tmpdir.mkdir(parents=True, exist_ok=True)
                file = _TORRENT_DIR / '{}.{}'.format(
                    resource_hash, _SAVELOAD_FILE_EXTENSION)
                logger.info('saving docker image {} to {} for seeding'.format(
                    image, file))
                subprocess.check_call(
                    ('(docker save {} | tar -xf -) '
                     '&& (tar --sort=name --mtime=\'1970-01-01\' '
                     '--owner=0 --group=0 -cf - . '
                     '| pigz --fast -n -T -c > {})').format(image, file),
                    cwd=str(tmpdir), shell=True)
                shutil.rmtree(str(tmpdir), ignore_errors=True)
                del tmpdir
                fsize = file.stat().st_size
            else:
                # tarball generated by docker save is not reproducible
                # we need to untar it and torrent the contents instead
                file = _TORRENT_DIR / '{}'.format(resource_hash)
                file.mkdir(parents=True, exist_ok=True)
                logger.info('saving docker image {} to {} for seeding'.format(
                    image, file))
                subprocess.check_call(
                    'docker save {} | tar -xf -'.format(image),
                    cwd=str(file), shell=True)
                fsize = 0
                for entry in scantree(str(file)):
                    if entry.is_file(follow_symlinks=False):
                        fsize += entry.stat().st_size
            diff = (datetime.datetime.now() - start).total_seconds()
            logger.debug('took {} sec to save docker image {} to {}'.format(
                diff, image, file))
            _record_perf('save-end', 'img={},size={},diff={}'.format(
                image, fsize, diff))
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
            # get docker image size
            output = subprocess.check_output(
                ('docker images --format \"{{{{.Repository}}}} '
                 '{{{{.Size}}}}\" | grep ^{}').format(image), shell=True)
            size = ' '.join(output.decode('utf-8').split()[1:])
            _record_perf('pull-end', 'img={},diff={},size={}'.format(
                image, diff, size))


async def _direct_download_resources_async(
        loop,
        blob_client: azure.storage.blob.BlockBlobService,
        queue_client, table_client, ipaddress,
        nglobalresources):
    # iterate through downloads to see if there are any torrents available
    with _DIRECTDL_LOCK:
        if len(_DIRECTDL) == 0:
            return
    # go through queue and find resources we can download
    msgs = queue_client.get_messages(
        _STORAGE_CONTAINERS['queue_globalresources'], num_messages=1,
        visibility_timeout=45)
    if len(msgs) == 0:
        return
    msg = None
    _rmdl = []
    _release_list = []
    with _DIRECTDL_LOCK:
        for _msg in msgs:
            if (msg is None and _msg.content in _DIRECTDL and
                    _msg.content not in _DIRECTDL_DOWNLOADING):
                if _ENABLE_P2P:
                    nseeds = _get_torrent_num_seeds(
                        table_client, _msg.content)
                    if nseeds < _SEED_BIAS:
                        msg = _msg
                    else:
                        _start_torrent_via_storage(
                            blob_client, table_client, _msg.content)
                        _rmdl.append(_msg.content)
                        _release_list.append(_msg)
                else:
                    msg = _msg
            else:
                _release_list.append(_msg)
    # renew lease and create renew callback
    if msg is not None:
        if _ENABLE_P2P or not _NON_P2P_CONCURRENT_DOWNLOADING:
            _QUEUE_MESSAGES[msg.id] = msg.pop_receipt
            _CBHANDLES[msg.content] = loop.call_later(
                15, _renew_queue_message_lease, loop, queue_client,
                'queue_globalresources', msg.content, msg.id)
        else:
            _release_list.append(msg)
    # release all messages in release list
    for _msg in _release_list:
        queue_client.update_message(
            _STORAGE_CONTAINERS['queue_globalresources'],
            message_id=_msg.id,
            pop_receipt=_msg.pop_receipt,
            visibility_timeout=0)
    # remove messages out of rmdl
    if len(_rmdl) > 0:
        with _DIRECTDL_LOCK:
            for dl in _rmdl:
                try:
                    logger.info(
                        'removing resource {} from direct downloads'.format(
                            dl))
                    _DIRECTDL.remove(dl)
                except ValueError:
                    pass
    if msg is None:
        return
    del _release_list
    del _rmdl
    # pull and save docker image in thread
    if msg.content.startswith(_DOCKER_TAG):
        thr = DockerSaveThread(
            blob_client, queue_client, table_client, msg.content, msg.id,
            nglobalresources)
        thr.start()
    else:
        # TODO download via blob, explode uri to get container/blob
        # use download to path into /tmp and move to _TORRENT_DIR
        raise NotImplementedError()


def _merge_service(
        table_client: azure.storage.table.TableService,
        resource: str,
        nglobalresources: int):
    """Merge entity to services table
    :param azure.storage.table.TableService table_client: table client
    :param str resource: resource to add to services table
    """
    rk = hashlib.sha1(resource.encode('utf8')).hexdigest()
    entity = {
        'PartitionKey': _PARTITION_KEY,
        'RowKey': rk,
        'Resource': resource,
        'VmList': _NODEID,
    }
    logger.debug('merging entity {} to services table'.format(entity))
    try:
        table_client.insert_entity(
            _STORAGE_CONTAINERS['table_services'], entity=entity)
    except azure.common.AzureConflictHttpError:
        while True:
            existing = table_client.get_entity(
                _STORAGE_CONTAINERS['table_services'],
                entity['PartitionKey'], entity['RowKey'])
            # merge VmList into existing
            evms = set(existing['VmList'].split(','))
            nvms = set(entity['VmList'].split(','))
            evms.update(nvms)
            existing['VmList'] = ','.join(list(evms))
            etag = existing['etag']
            existing.pop('etag')
            try:
                table_client.merge_entity(
                    _STORAGE_CONTAINERS['table_services'], entity=existing,
                    if_match=etag)
                entity = existing
                break
            except azure.common.AzureConflictHttpError:
                pass
    logger.info('entity {} merged to services table'.format(entity))
    global _GR_DONE
    if not _GR_DONE:
        try:
            entities = table_client.query_entities(
                _STORAGE_CONTAINERS['table_services'],
                filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
        except azure.common.AzureMissingResourceHttpError:
            entities = []
        count = 0
        for entity in entities:
            vms = set(entity['VmList'].split(','))
            if _NODEID in vms:
                count += 1
        if count == nglobalresources:
            _record_perf(
                'gr-done',
                'nglobalresources={}'.format(nglobalresources))
            _GR_DONE = True


def _get_torrent_info(resource, th):
    global _LAST_DHT_INFO_DUMP
    s = th.status()
    if (s.download_rate > 0 or s.upload_rate > 0 or s.num_peers > 0 or
            (s.progress - 1.0) > 1e-6):
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
        table_client: azure.storage.table.TableService,
        ipaddress: str):
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
    # TODO handle if pool has less than 3 nodes total
    if len(dht_nodes) < 3:
        loop.call_later(1, bootstrap_dht_nodes, loop, table_client, ipaddress)


class DockerLoadThread(threading.Thread):
    def __init__(self, resource):
        threading.Thread.__init__(self)
        self.resource = resource
        _TORRENTS[self.resource]['seed'] = True
        _TORRENTS[self.resource]['loading'] = True

    def run(self):
        logger.debug('loading resource: {}'.format(self.resource))
        resource_hash = hashlib.sha1(self.resource.encode('utf8')).hexdigest()
        image = self.resource[
            self.resource.find(_DOCKER_TAG) + len(_DOCKER_TAG):]
        start = datetime.datetime.now()
        if _COMPRESSION:
            file = _TORRENT_DIR / '{}.{}'.format(
                resource_hash, _SAVELOAD_FILE_EXTENSION)
            logger.info('loading docker image {} from {}'.format(image, file))
            _record_perf('load-start', 'img={},size={}'.format(
                image, file.stat().st_size))
            subprocess.check_call(
                'pigz -cd {} | docker load'.format(file), shell=True)
        else:
            file = _TORRENT_DIR / '{}'.format(resource_hash)
            logger.info('loading docker image {} from {}'.format(image, file))
            _record_perf('load-start', 'img={}'.format(image))
            subprocess.check_call(
                'tar -cO . | docker load', cwd=str(file), shell=True)
        diff = (datetime.datetime.now() - start).total_seconds()
        logger.debug(
            'took {} sec to load docker image from {}'.format(diff, file))
        _record_perf('load-end', 'img={},diff={}'.format(image, diff))
        _TORRENTS[self.resource]['loading'] = False
        _TORRENTS[self.resource]['loaded'] = True


async def _load_and_register_async(
        loop: asyncio.BaseEventLoop,
        table_client: azure.storage.table.TableService,
        nglobalresources: int):
    global _LR_LOCK_ASYNC
    async with _LR_LOCK_ASYNC:
        for resource in _TORRENTS:
            # if torrent is seeding, load container/file and register
            if (_TORRENTS[resource]['started'] and
                    _TORRENTS[resource]['handle'].is_seed()):
                if (not _TORRENTS[resource]['loaded'] and
                        not _TORRENTS[resource]['loading']):
                    # docker load image
                    if resource.startswith(_DOCKER_TAG):
                        thr = DockerLoadThread(resource)
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
        table_client: azure.storage.table.TableService,
        ipaddress: str,
        nglobalresources: int):
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
                _get_torrent_info(resource, _TORRENTS[resource]['handle'])
                continue
            seed = _TORRENTS[resource]['seed']
            logger.info(
                ('creating torrent session for {} ipaddress={} '
                 'seed={}').format(resource, ipaddress, seed))
            image = resource[resource.find(_DOCKER_TAG) + len(_DOCKER_TAG):]
            _TORRENTS[resource]['handle'] = create_torrent_session(
                resource, _TORRENT_DIR, seed)
            await _record_perf_async(loop, 'torrent-start', 'img={}'.format(
                image))
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
        blob_client: azure.storage.blob.BlockBlobService,
        queue_client: azure.storage.queue.QueueService,
        table_client: azure.storage.table.TableService,
        ipaddress: str,
        nglobalresources: int):
    # begin async manage torrent sessions
    if _ENABLE_P2P:
        asyncio.ensure_future(
            manage_torrents_async(
                loop, table_client, ipaddress, nglobalresources)
        )
    while True:
        # check if there are any direct downloads
        if len(_DIRECTDL) > 0:
            await _direct_download_resources_async(
                loop, blob_client, queue_client, table_client, ipaddress,
                nglobalresources)
        # if not in peer-to-peer mode, allow exit
        if not _ENABLE_P2P and _GR_DONE:
            break
        # sleep to avoid pinning cpu
        await asyncio.sleep(1)


def _get_torrent_num_seeds(
        table_client: azure.storage.table.TableService,
        resource: str) -> int:
    try:
        rk = hashlib.sha1(resource.encode('utf8')).hexdigest()
        se = table_client.get_entity(
            _STORAGE_CONTAINERS['table_services'],
            _PARTITION_KEY, rk)
        numseeds = len(se['VmList'].split(','))
    except azure.common.AzureMissingResourceHttpError:
        numseeds = 0
    return numseeds


def _start_torrent_via_storage(
        blob_client: azure.storage.blob.BlockBlobService,
        table_client: azure.storage.table.TableService,
        resource: str, entity: dict=None):
    if not _ENABLE_P2P:
        return
    if entity is None:
        rk = hashlib.sha1(resource.encode('utf8')).hexdigest()
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_torrentinfo'],
            _PARTITION_KEY, rk)
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
        blob_client: azure.storage.blob.BlockBlobService,
        table_client: azure.storage.table.TableService,
        resource: str) -> bool:
    if not _ENABLE_P2P:
        return False
    add_to_dict = False
    try:
        rk = hashlib.sha1(resource.encode('utf8')).hexdigest()
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_torrentinfo'],
            _PARTITION_KEY, rk)
        numseeds = _get_torrent_num_seeds(table_client, resource)
        if numseeds < _SEED_BIAS:
            add_to_dict = True
    except azure.common.AzureMissingResourceHttpError:
        add_to_dict = True
    if add_to_dict:
        logger.info('adding {} as resource to download'.format(resource))
        with _DIRECTDL_LOCK:
            _DIRECTDL.append(resource)
        return False
    else:
        logger.info('found torrent for resource {}'.format(resource))
        _start_torrent_via_storage(
            blob_client, table_client, resource, entity)
    return True


def distribute_global_resources(
        loop: asyncio.BaseEventLoop,
        blob_client: azure.storage.blob.BlockBlobService,
        queue_client: azure.storage.queue.QueueService,
        table_client: azure.storage.table.TableService,
        ipaddress: str):
    """Distribute global services/resources
    :param asyncio.BaseEventLoop loop: event loop
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
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
        bootstrap_dht_nodes(loop, table_client, ipaddress)
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
                with _DIRECTDL_LOCK:
                    _DIRECTDL.append(ent['Resource'])
    # run async func in loop
    loop.run_until_complete(download_monitor_async(
        loop, blob_client, queue_client, table_client, ipaddress, nentities))


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
    global _ENABLE_P2P, _NON_P2P_CONCURRENT_DOWNLOADING
    # get command-line args
    args = parseargs()
    p2popts = args.p2popts.split(':')
    _ENABLE_P2P = p2popts[0] == 'true'
    _NON_P2P_CONCURRENT_DOWNLOADING = p2popts[1]
    # set p2p options
    if _ENABLE_P2P:
        if not _LIBTORRENT_IMPORTED:
            raise ImportError('No module named \'libtorrent\'')
        global _COMPRESSION, _SEED_BIAS, _ALLOW_PUBLIC_PULL_WITH_PRIVATE, \
            _SAVELOAD_FILE_EXTENSION
        _COMPRESSION = p2popts[3] == 'true'
        _SEED_BIAS = int(p2popts[2])
        _ALLOW_PUBLIC_PULL_WITH_PRIVATE = p2popts[4] == 'true'
        if not _COMPRESSION:
            _SAVELOAD_FILE_EXTENSION = 'tar'
        logger.info('peer-to-peer options: compression={} seedbias={}'.format(
            _COMPRESSION, _SEED_BIAS))
        # create torrent directory
        logger.debug('creating torrent dir: {}'.format(_TORRENT_DIR))
        _TORRENT_DIR.mkdir(parents=True, exist_ok=True)
    else:
        logger.info('non-p2p concurrent downloading: {}'.format(
            _NON_P2P_CONCURRENT_DOWNLOADING))
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

    # set up container names
    _setup_container_names(args.prefix)

    # create storage credentials
    blob_client, queue_client, table_client = _create_credentials()

    # set registry
    global _REGISTRY
    if pathlib.Path('.cascade_private_registry.txt').exists():
        _REGISTRY = 'localhost:5000'
    else:
        _REGISTRY = 'registry.hub.docker.com'
    logger.info('docker registry: {}'.format(_REGISTRY))

    del args

    # distribute global resources
    distribute_global_resources(
        loop, blob_client, queue_client, table_client, ipaddress)


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Cascade: Azure Batch P2P File/Image Replicator')
    parser.set_defaults(ipaddress=None)
    parser.add_argument(
        'p2popts',
        help='peer to peer options [enabled:non-p2p concurrent '
        'downloading:seed bias:compression:public pull passthrough]')
    parser.add_argument(
        '--ipaddress', help='ip address')
    parser.add_argument(
        '--prefix', help='storage container prefix')
    parser.add_argument(
        '--privateregcount', help='private registry count')
    parser.add_argument(
        '--no-torrent', action='store_false', dest='torrent',
        help='disable peer-to-peer transfer')
    parser.add_argument(
        '--nonp2pcd', action='store_true',
        help='non-p2p concurrent downloading')
    return parser.parse_args()

if __name__ == '__main__':
    _setup_logger()
    main()
