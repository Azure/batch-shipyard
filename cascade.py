#!/usr/bin/env python3

# stdlib imports
import argparse
import asyncio
import base64
import datetime
import hashlib
import os
import pathlib
import random
import sys
# non-stdlib imports
import azure.common
import azure.storage.blob as azureblob
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable
import libtorrent

# global defines
_ON_WINDOWS = sys.platform == 'win32'
_DEFAULT_PORT_BEGIN = 6881
_DEFAULT_PORT_END = 6891
_DOCKER_TAG = 'docker:'
_TORRENT_STATE = [
    'queued', 'checking', 'downloading metadata', 'downloading', 'finished',
    'seeding', 'allocating', 'checking fastresume'
]
_TORRENT_SESSION = libtorrent.session()
_STORAGEACCOUNT = os.environ['CASCADE_SA']
_STORAGEACCOUNTKEY = os.environ['CASCADE_SAKEY']
_BATCHACCOUNT = os.environ['AZ_BATCH_ACCOUNT_NAME']
_POOLID = os.environ['AZ_BATCH_POOL_ID']
_NODEID = os.environ['AZ_BATCH_NODE_ID']
_SHARED_DIR = os.environ['AZ_BATCH_NODE_SHARED_DIR']
_TORRENT_DIR = pathlib.Path(_SHARED_DIR, '.torrents')
_PARTITION_KEY = '{}${}'.format(_BATCHACCOUNT, _POOLID)
# mutable global state
_CBHANDLES = {}
_QUEUE_MESSAGES = {}
_PREFIX = None
_STORAGE_CONTAINERS = {
    'table_dht': None,
    'table_registry': None,
    'table_torrentinfo': None,
    'table_services': None,
    'table_globalresources': None,
    'queue_globalresources': None,
}
_SELF_REGISTRY_PTR = None
_REGISTRIES = {}
_TORRENTS = {}
_DIRECTDL = {}
_DHT_ROUTERS = []
_LR_LOCK_ASYNC = asyncio.Lock()
_GR_DONE = False


def _setup_container_names(sep: str):
    """Set up storage container names
    :param str sep: storage container prefix
    """
    if sep is None:
        sep = ''
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
    ep = os.getenv('CASCADE_EP') or 'core.windows.net'
    blob_client = azureblob.BlockBlobService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=ep)
    queue_client = azurequeue.QueueService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=ep)
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=ep)
    return blob_client, queue_client, table_client


def generate_torrent(incl_file: str) -> dict:
    """Generate torrent file for a given file and write it to disk
    :param str incl_file: file to include in torrent
    :rtype: tuple
    :return: (torrent file as pathlib, torrent file encoded as base64,
              torrent file data sha1 hash)
    """
    fs = libtorrent.file_storage()
    libtorrent.add_files(fs, incl_file)
    tor = libtorrent.create_torrent(fs)
    tor.set_creator('libtorrent {}'.format(libtorrent.version))
    path = pathlib.Path(incl_file)
    libtorrent.set_piece_hashes(tor, str(path.parent))
    torrent = tor.generate()
    torrent_data = libtorrent.bencode(torrent)
    torrent_b64 = base64.b64encode(torrent_data).decode('ascii')
    torrent_sha1 = hashlib.sha1(torrent_data).hexdigest()
    fp = _TORRENT_DIR / '{}.torrent'.format(torrent_sha1)
    with fp.open('wb') as f:
        f.write(torrent_data)
    return fp, torrent_b64, torrent_sha1


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
    print('created torrent session for {} is_seed={}'.format(
        resource, torrent_handle.is_seed()))
    return torrent_handle


def add_dht_node(ip: str, port: int):
    """Add a node as a DHT router
    :param str ip: ip address of the dht node
    :param int port: port of the dht node
    """
    if ip not in _DHT_ROUTERS:
        _TORRENT_SESSION.add_dht_router(ip, port)
        print('added {}:{} as dht router'.format(ip, port))
        _DHT_ROUTERS.append(ip)


def _renew_queue_message_lease(
        loop: asyncio.BaseEventLoop,
        queue_client: azure.storage.queue.QueueService,
        queue_key: str, msg_id: str):
    """Renew a storage queue message lease
    :param asyncio.BaseEventLoop loop: event loop
    :param azure.storage.queue.QueueService queue_client: queue client
    :param str queue_key: queue name key index into _STORAGE_CONTAINERS
    :param str msg_id: message id
    """
    print('updating queue message id={} pr={}'.format(
        msg_id, _QUEUE_MESSAGES[msg_id].pop_receipt))
    msg = queue_client.update_message(
        _STORAGE_CONTAINERS[queue_key],
        message_id=msg_id,
        pop_receipt=_QUEUE_MESSAGES[msg_id].pop_receipt,
        visibility_timeout=45)
    if msg.pop_receipt is None:
        raise RuntimeError(
            'update message failed for id={} pr={}'.format(
                msg_id, _QUEUE_MESSAGES[msg_id].pop_receipt))
    _QUEUE_MESSAGES[msg_id].pop_receipt = msg.pop_receipt
    print('queue message updated id={} pr={}'.format(
        msg_id, _QUEUE_MESSAGES[msg_id].pop_receipt))
    _CBHANDLES[queue_key] = loop.call_later(
        15, _renew_queue_message_lease, loop, queue_client, queue_key, msg_id)


def _pick_random_registry_key():
    if _SELF_REGISTRY_PTR is not None:
        return _SELF_REGISTRY_PTR
    return random.randint(0, len(_REGISTRIES) - 1)


def compute_sha1_for_file(file, blocksize=65536):
    """Compute SHA1 hash for file
    :param pathlib.Path file: file to compute sha1
    :param int blocksize: block size in bytes
    :rtype: str
    :return: SHA1 for file
    """
    hasher = hashlib.sha1()
    with file.open('rb') as filedesc:
        while True:
            buf = filedesc.read(blocksize)
            if not buf:
                break
            hasher.update(buf)
        return hasher.hexdigest()


async def _record_perf_async(loop, event, message):
    proc = await asyncio.subprocess.create_subprocess_shell(
        'perf.py cascade {ev} --prefix {pr} --message "{msg}"'.format(
            ev=event, pr=_PREFIX, msg=message), loop=loop)
    await proc.wait()
    if proc.returncode != 0:
        print('could not record perf to storage for event: {}'.format(event))


async def _direct_download_resources_async(
        loop, blob_client, queue_client, table_client, ipaddress):
    # iterate through downloads to see if there are any torrents available
    rmdl = []
    for dl in _DIRECTDL:
        if _check_resource_has_torrent(loop, table_client, dl, False):
            rmdl.append(dl)
    if len(rmdl) > 0:
        for dl in rmdl:
            _DIRECTDL.pop(dl, None)
    if len(_DIRECTDL) == 0:
        return
    # go through queue and find resources we can download
    msg = None
    _release_list = []
    while True:
        msgs = queue_client.get_messages(
            _STORAGE_CONTAINERS['queue_globalresources'], num_messages=32,
            visibility_timeout=45)
        if len(msgs) == 0:
            break
        for _msg in msgs:
            if _msg.content in _DIRECTDL and msg is None:
                msg = _msg
            else:
                _release_list.append(_msg)
        if msg is not None:
            break
    # renew lease and create renew callback
    if msg is not None:
        _QUEUE_MESSAGES[msg.id] = msg
        _CBHANDLES['queue_globalresources'] = loop.call_later(
            15, _renew_queue_message_lease, loop, queue_client,
            'queue_globalresources', msg.id)
    # release all messages in release list
    for _msg in _release_list:
        queue_client.update_message(
            _STORAGE_CONTAINERS['queue_globalresources'],
            message_id=_msg.id,
            pop_receipt=_msg.pop_receipt,
            visibility_timeout=0)
    del _release_list
    if msg is None:
        return
    file = None
    # download data
    resource = msg.content
    if resource.startswith(_DOCKER_TAG):
        if len(_REGISTRIES) < 1:
            raise RuntimeError(
                ('{} image specified for global resource, but there are '
                 'no registries available').format(resource))
        image = resource[resource.find(_DOCKER_TAG) + len(_DOCKER_TAG):]
        registry = None
        await _record_perf_async(loop, 'pull-start', 'img={}'.format(image))
        start = datetime.datetime.now()
        while True:
            # pick random registry to download from
            registry = _REGISTRIES[_pick_random_registry_key()]
            print('pulling image {} from {}'.format(image, registry))
            if registry == 'registry.hub.docker.com':
                proc = await asyncio.subprocess.create_subprocess_shell(
                    'docker pull {}'.format(image), loop=loop)
            else:
                proc = await asyncio.subprocess.create_subprocess_shell(
                    'docker pull {}/{}'.format(registry, image), loop=loop)
            await proc.wait()
            if proc.returncode == 0:
                break
            else:
                print('docker pull non-zero rc: {}'.format(
                    proc.returncode))
                await asyncio.sleep(1)
        # tag image to remove registry ip
        if registry != 'registry.hub.docker.com':
            proc = await asyncio.subprocess.create_subprocess_shell(
                'docker tag {}/{} {}'.format(registry, image, image),
                loop=loop)
            await proc.wait()
            if proc.returncode != 0:
                raise RuntimeError('docker tag non-zero rc: {}'.format(
                    proc.returncode))
        diff = (datetime.datetime.now() - start).total_seconds()
        print('took {} sec to pull docker image {} from {}'.format(
            diff, image, registry))
        await _record_perf_async(loop, 'pull-end', 'img={},diff={}'.format(
            image, diff))
        # save docker image to seed to torrent
        await _record_perf_async(loop, 'save-start', 'img={}'.format(
            image))
        start = datetime.datetime.now()
        file = _TORRENT_DIR / '{}.tar.gz'.format(image)
        print('creating path to store torrent: {}'.format(file.parent))
        file.parent.mkdir(parents=True, exist_ok=True)
        print('saving docker image {} to {} for seeding'.format(
            image, file))
        proc = await asyncio.subprocess.create_subprocess_shell(
            'docker save {} | gzip -c > {}'.format(image, file), loop=loop)
        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError('docker save non-zero rc: {}'.format(
                proc.returncode))
        else:
            print('docker image {} saved for seeding'.format(image))
        diff = (datetime.datetime.now() - start).total_seconds()
        print('took {} sec to save docker image {} to {}'.format(
            diff, image, file.parent))
        await _record_perf_async(loop, 'save-end', 'img={},diff={}'.format(
            image, diff))
    else:
        # TODO download via blob, explode uri to get container/blob
        # use download to path into /tmp and move to _TORRENT_DIR
        raise NotImplementedError()
    # generate torrent file
    start = datetime.datetime.now()
    future = loop.run_in_executor(None, generate_torrent, str(file))
    torrent_file, torrent_b64, torrent_sha1 = await future
    diff = (datetime.datetime.now() - start).total_seconds()
    print('took {} sec to generate torrent file: {}'.format(
        diff, torrent_file))
    start = datetime.datetime.now()
    # add to torrent dict (effectively enqueues for torrent start)
    entity = {
        'PartitionKey': _PARTITION_KEY,
        'RowKey': hashlib.sha1(resource.encode('utf8')).hexdigest(),
        'Resource': resource,
        'TorrentFileBase64': torrent_b64,
        'TorrentFileSHA1': torrent_sha1,
        'FileSizeBytes': file.stat().st_size,
        # 'FileSHA1': compute_sha1_for_file(file),
    }
    _TORRENTS[resource] = {
        'entity': entity,
        'torrent_file': torrent_file,
        'started': False,
        'seed': True,
        'loaded': True,
        'registered': False,
    }
    # wait until torrent has started
    print('waiting for torrent {} to start'.format(resource))
    while not _TORRENTS[resource]['started']:
        await asyncio.sleep(0.1)
    diff = (datetime.datetime.now() - start).total_seconds()
    print('took {} sec for {} torrent to start'.format(diff, resource))
    # cancel callback
    _CBHANDLES['queue_globalresources'].cancel()
    _CBHANDLES.pop('queue_globalresources')
    # release queue message
    queue_client.update_message(
        _STORAGE_CONTAINERS['queue_globalresources'],
        message_id=msg.id,
        pop_receipt=_QUEUE_MESSAGES[msg.id].pop_receipt,
        visibility_timeout=0)
    _QUEUE_MESSAGES.pop(msg.id)
    print('queue message released for {}'.format(resource))
    # remove resources from download list
    _DIRECTDL.pop(resource)


def _merge_service(
        table_client: azure.storage.table.TableService,
        resource: str):
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
    print('merging entity {} to services table'.format(entity))
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
    print('entity {} merged to services table'.format(entity))


def _get_torrent_info(resource, th):
    s = th.status()
    print(('%s wanted: %d %.2f%% complete (down: %.1f kB/s up: %.1f kB/s '
           'peers: %d) %s') %
          (th.name(), s.total_wanted, s.progress * 100, s.download_rate / 1000,
           s.upload_rate / 1000, s.num_peers, _TORRENT_STATE[s.state]))
#     ss = _TORRENT_SESSION.status()
#     print(_TORRENT_SESSION.is_dht_running(), ss.dht_global_nodes,
#           ss.dht_nodes, ss.dht_node_cache, ss.dht_torrents,
#           ss.total_dht_upload, ss.total_dht_download,
#           ss.has_incoming_connections)
#     p = th.get_peer_info()
#     for i in p:
#         print(i.ip)


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
    if not found_self and len(dht_nodes) < 3:
        entity = {
            'PartitionKey': _PARTITION_KEY,
            'RowKey': ipaddress,
            'Port': _DEFAULT_PORT_BEGIN,
        }
        table_client.insert_entity(_STORAGE_CONTAINERS['table_dht'], entity)
        dht_nodes.insert(0, (ipaddress, _DEFAULT_PORT_BEGIN))
    for node in dht_nodes:
        if len(_DHT_ROUTERS) >= 3:
            break
        add_dht_node(node[0], node[1])
    # TODO handle if pool has less than 3 nodes total
    if len(dht_nodes) < 3:
        loop.call_later(1, bootstrap_dht_nodes, loop, table_client, ipaddress)


async def _load_and_register_async(
        loop: asyncio.BaseEventLoop,
        table_client: azure.storage.table.TableService,
        nglobalresources: int):
    global _LR_LOCK_ASYNC
    async with _LR_LOCK_ASYNC:
        nfinished = 0
        for resource in _TORRENTS:
            # if torrent is seeding, load into docker registry and register
            if _TORRENTS[resource]['started']:
                if _TORRENTS[resource]['handle'].is_seed():
                    # docker load image
                    if not _TORRENTS[resource]['loaded']:
                        image = resource[
                            resource.find(_DOCKER_TAG) + len(_DOCKER_TAG):]
                        await _record_perf_async(
                            loop, 'load-start', 'img={}'.format(image))
                        start = datetime.datetime.now()
                        file = _TORRENT_DIR / '{}.tar.gz'.format(image)
                        print('loading docker image {} from {}'.format(
                            image, file))
                        proc = await \
                            asyncio.subprocess.create_subprocess_shell(
                                'gunzip -c {} | docker load'.format(file),
                                loop=loop)
                        await proc.wait()
                        if proc.returncode != 0:
                            raise RuntimeError(
                                'docker load non-zero rc: {}'.format(
                                    proc.returncode))
                        _TORRENTS[resource]['loaded'] = True
                        diff = (datetime.datetime.now() -
                                start).total_seconds()
                        print(('took {} sec to load docker image '
                               'from {}').format(diff, file))
                        await _record_perf_async(
                            loop, 'load-end', 'img={},diff={}'.format(
                                image, diff))
                    # register to services table
                    if not _TORRENTS[resource]['registered']:
                        _merge_service(table_client, resource)
                        _TORRENTS[resource]['registered'] = True
                    else:
                        nfinished += 1
        if not _GR_DONE and nfinished == nglobalresources:
            await _record_perf_async(
                loop, 'gr-done',
                'nglobalresources={}'.format(nglobalresources))
            global _GR_DONE
            _GR_DONE = True


async def manage_torrents_async(
        loop: asyncio.BaseEventLoop,
        table_client: azure.storage.table.TableService,
        ipaddress: str,
        nglobalresources: int):
    global _LR_LOCK_ASYNC
    while True:
        # async schedule load and register
        if not _LR_LOCK_ASYNC.locked():
            asyncio.ensure_future(_load_and_register_async(
                loop, table_client, nglobalresources))
        # start applicable torrent sessions
        for resource in _TORRENTS:
            if _TORRENTS[resource]['started']:
                # print out torrent info
                _get_torrent_info(resource, _TORRENTS[resource]['handle'])
                continue
            seed = _TORRENTS[resource]['seed']
            print(('creating torrent session for {} ipaddress={} '
                   'seed={}').format(resource, ipaddress, seed))
            image = resource[resource.find(_DOCKER_TAG) + len(_DOCKER_TAG):]
            parent = (_TORRENT_DIR / image).parent
            print('creating torrent download directory: {}'.format(parent))
            parent.mkdir(parents=True, exist_ok=True)
            _TORRENTS[resource]['handle'] = create_torrent_session(
                resource, parent, seed)
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
    asyncio.ensure_future(
        manage_torrents_async(loop, table_client, ipaddress, nglobalresources))
    while True:
        # check if there are any direct downloads
        if len(_DIRECTDL) > 0:
            await _direct_download_resources_async(
                loop, blob_client, queue_client, table_client, ipaddress)
        # sleep to avoid pinning cpu
        await asyncio.sleep(1)


def _check_resource_has_torrent(
        loop: asyncio.BaseEventLoop,
        table_client: azure.storage.table.TableService,
        resource: str,
        add_to_dict: bool=False) -> bool:
    try:
        rk = hashlib.sha1(resource.encode('utf8')).hexdigest()
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_torrentinfo'],
            _PARTITION_KEY, rk)
    except azure.common.AzureMissingResourceHttpError:
        if add_to_dict:
            _DIRECTDL[resource] = None
        return False
    else:
        # write torrent file to disk
        torrent = base64.b64decode(entity['TorrentFileBase64'])
        torrent_file = _TORRENT_DIR / '{}.torrent'.format(
            entity['TorrentFileSHA1'])
        with open(str(torrent_file), 'wb') as f:
            f.write(torrent)
        _TORRENTS[resource] = {
            'entity': entity,
            'torrent_file': torrent_file,
            'started': False,
            'seed': False,
            'loaded': False,
            'registered': False,
        }
        print('found torrent for resource {}'.format(resource))
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
    print('creating torrent session on {}:{}'.format(
        ipaddress, _DEFAULT_PORT_BEGIN))
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
            _check_resource_has_torrent(
                loop, table_client, ent['Resource'], True)
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
    # get command-line args
    args = parseargs()

    # get event loop
    if _ON_WINDOWS:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    loop.set_debug(True)

    # get ip address if not specified, for local testing only
    if args.ipaddress is None:
        args.ipaddress = loop.run_until_complete(_get_ipaddress_async(loop))

    print('ip address: {}'.format(args.ipaddress))

    # set up container names
    _setup_container_names(args.prefix)

    # create storage credentials
    blob_client, queue_client, table_client = _create_credentials()

    # create torrent directory
    print('creating torrent dir: {}'.format(_TORRENT_DIR))
    _TORRENT_DIR.mkdir(parents=True, exist_ok=True)

    # get registry list
    global _REGISTRIES, _SELF_REGISTRY_PTR
    _REGISTRIES = [line.rstrip('\n') for line in open(
        '.cascade_private_registries.txt', 'r')]
    if len(_REGISTRIES) == 0:
        _REGISTRIES.append('registry.hub.docker.com')
    for i in range(0, len(_REGISTRIES)):
        if _REGISTRIES[i].split(':')[0] == args.ipaddress:
            _SELF_REGISTRY_PTR = i
            break
    print('docker registries: {} self={}'.format(
        _REGISTRIES, _SELF_REGISTRY_PTR))

    # distribute global resources
    distribute_global_resources(
        loop, blob_client, queue_client, table_client, args.ipaddress)


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Cascade: Azure Batch P2P File/Image Replicator')
    parser.add_argument(
        'ipaddress', nargs='?', default=None, help='ip address')
    parser.add_argument(
        '--prefix', help='storage container prefix')
    return parser.parse_args()

if __name__ == '__main__':
    main()
