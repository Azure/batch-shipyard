#!/usr/bin/env python3

# stdlib imports
import argparse
import asyncio
import base64
import hashlib
import os
import pathlib
import random
import subprocess
import sys
import time
from typing import List
# non-stdlib imports
import azure.common
import azure.storage.blob as azureblob
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable
import libtorrent

# global defines
_DEFAULT_PORT_BEGIN = 6881
_DEFAULT_PORT_END = 6891
_DEFAULT_PRIVATE_REGISTRY_PORT = 5000
_REGISTRY_ARCHIVE = 'docker-registry-v2.tar.gz'
_REGISTRY_IMAGE_ID = '8ff6a4aae657'
_DOCKER_TAG = 'docker:'
_TORRENT_STATE = [
    'queued', 'checking', 'downloading metadata', 'downloading', 'finished',
    'seeding', 'allocating', 'checking fastresume'
]
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
_STORAGE_CONTAINERS = {
    'table_registry': None,
    'table_torrentinfo': None,
    'table_service': None,
    'table_globalresources': None,
    'queue_registry': None,
    'queue_globalresources': None,
}
_REGISTRIES = {}
_TORRENTS = {}
_DIRECTDL = {}


def _setup_container_names(sep: str):
    """Set up storage container names
    :param str sep: storage container prefix
    """
    if sep is None:
        sep = ''
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    _STORAGE_CONTAINERS['table_services'] = sep + 'services'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'globalresources'
    _STORAGE_CONTAINERS['queue_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['queue_globalresources'] = sep + 'globalresources'


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
        torrent_file: str, save_path: str, seed_mode: bool,
        port_range: List[int]=
        [_DEFAULT_PORT_BEGIN, _DEFAULT_PORT_END]) -> tuple:
    """Create a torrent session given a torrent file
    :param str torrent_file: torrent file
    :param str save_path: path to save torrented files to
    :param bool seed_mode: seed mode
    :param list port_range: port range to listen on
    :rtype: tuple
    :return: return (torrent_handle, session)
    """
    session = libtorrent.session()
    session.listen_on(port_range[0], port_range[-1])
    torrent_handle = session.add_torrent({
        'ti': libtorrent.torrent_info(torrent_file),
        'save_path': save_path,
        'seed_mode': seed_mode
    })
    session.start_dht()
    return torrent_handle, session


def add_dht_node(session: libtorrent.session, ip: str, port: int):
    """Add a node to the DHT
    :param libtorrent.session session: libtorrent session
    :param str ip: ip address of the dht node
    :param int port: port of the dht node
    """
    session.add_dht_node((ip, port))
    if not session.is_dht_running():
        session.start_dht()


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
        visibility_timeout=0)
    if msg.pop_receipt is None:
        raise RuntimeError('update message failed')
    _QUEUE_MESSAGES[msg_id].pop_receipt = msg.pop_receipt
    print('queue message updated id={} pr={}'.format(
        msg_id, _QUEUE_MESSAGES[msg_id].pop_receipt))
    _CBHANDLES[queue_key] = loop.call_later(
        15, _renew_queue_message_lease, loop, queue_client, queue_key, msg_id)


async def _start_private_registry_instance_async(
        loop: asyncio.BaseEventLoop, container: str):
    """Start private docker registry instance
    :param asyncio.BaseEventLoop loop: event loop
    :param str container: storage container holding registry info
    """
    proc = await asyncio.subprocess.create_subprocess_shell(
        'docker images | grep -E \'^registry.*2\' | awk -e \'{print $3}\'',
        stdout=asyncio.subprocess.PIPE, loop=loop)
    stdout = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError('docker images non-zero rc: {}'.format(
            proc.returncode))
    if (stdout[0].strip() != _REGISTRY_IMAGE_ID and
            pathlib.Path(_REGISTRY_ARCHIVE).exists()):
        print('importing registry from local file: {}'.format(
            _REGISTRY_ARCHIVE))
        proc = await asyncio.subprocess.create_subprocess_shell(
            'gunzip -c {} | docker load'.format(
                _REGISTRY_ARCHIVE), loop=loop)
        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError('docker load non-zero rc: {}'.format(
                proc.returncode))
    sa = os.getenv('PRIVATE_REGISTRY_SA') or _STORAGEACCOUNT
    sakey = os.getenv('PRIVATE_REGISTRY_SAKEY') or _STORAGEACCOUNTKEY
    registry_cmd = [
        'docker', 'run', '-d', '-p',
        '{p}:{p}'.format(p=_DEFAULT_PRIVATE_REGISTRY_PORT),
        '-e', 'REGISTRY_STORAGE=azure',
        '-e', 'REGISTRY_STORAGE_AZURE_ACCOUNTNAME={}'.format(sa),
        '-e', 'REGISTRY_STORAGE_AZURE_ACCOUNTKEY={}'.format(sakey),
        '-e', 'REGISTRY_STORAGE_AZURE_CONTAINER={}'.format(container),
        '--restart=always', '--name=registry', 'registry:2',
    ]
    print('starting private registry on port {} -> {}:{}'.format(
        _DEFAULT_PRIVATE_REGISTRY_PORT, sa, container))
    proc = await asyncio.subprocess.create_subprocess_shell(
        ' '.join(registry_cmd), loop=loop)
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(
            'docker run for private registry non-zero rc: {}'.format(
                proc.returncode))


async def setup_private_registry_async(
        loop: asyncio.BaseEventLoop,
        queue_client: azure.storage.queue.QueueService,
        table_client: azure.storage.table.TableService,
        ipaddress: str, container: str):
    """Set up a docker private registry if a ticket exists
    :param asyncio.BaseEventLoop loop: event loop
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param str ipaddress: ip address
    :param str container: container holding registry
    """
    # first check if we've registered before
    try:
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_registry'], _PARTITION_KEY, ipaddress)
        print('private registry row already exists: {}'.format(entity))
        await _start_private_registry_instance_async(loop, container)
        return
    except azure.common.AzureMissingResourceHttpError:
        pass
    while True:
        # check for a ticket
        msgs = queue_client.get_messages(
            _STORAGE_CONTAINERS['queue_registry'], num_messages=1,
            visibility_timeout=45)
        # if there are no messages, then check the table to make sure at
        # least 1 entry exists
        if len(msgs) == 0:
            entities = table_client.query_entities(
                _STORAGE_CONTAINERS['table_registry'],
                filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY)
            )
            if len(entities) == 0:
                print('no registry entries found, will try again for ticket')
                await asyncio.sleep(1)
            else:
                break
        else:
            msg = msgs[0]
            print('got queue message id={} pr={}'.format(
                msg.id, msg.pop_receipt))
            _QUEUE_MESSAGES[msg.id] = msg
            # create renew callback
            _CBHANDLES['queue_registry'] = loop.call_later(
                15, _renew_queue_message_lease, loop, queue_client,
                'queue_registry', msg.id)
            # install docker registy container
            await _start_private_registry_instance_async(loop, container)
            entity = {
                'PartitionKey': _PARTITION_KEY,
                'RowKey': ipaddress,
                'Port': _DEFAULT_PRIVATE_REGISTRY_PORT,
                'NodeId': _NODEID,
                'StorageAccount': _STORAGEACCOUNT,
                'Container': container,
            }
            # register self into registry table
            table_client.insert_or_replace_entity(
                _STORAGE_CONTAINERS['table_registry'], entity=entity)
            # insert self into local registry cache
            _REGISTRIES[ipaddress] = entity
            # cancel callback
            _CBHANDLES['queue_registry'].cancel()
            _CBHANDLES.pop('queue_registry')
            # release queue message
            print('releasing queue message id={} pr={}'.format(
                msg.id, _QUEUE_MESSAGES[msg.id].pop_receipt))
            queue_client.update_message(
                _STORAGE_CONTAINERS['queue_registry'],
                message_id=msg.id,
                pop_receipt=_QUEUE_MESSAGES[msg.id].pop_receipt,
                visibility_timeout=0)
            _QUEUE_MESSAGES.pop(msg.id)
            break


def _pick_random_registry_key():
    return list(_REGISTRIES.keys())[random.randint(0, len(_REGISTRIES) - 1)]


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


async def _direct_download_resources_async(
        loop, blob_client, queue_client, table_client, ipaddress):
    # iterate through downloads to see if there are any torrents available
    for dl in _DIRECTDL:
        exists = _check_resource_has_torrent(loop, table_client, dl, False)
        if exists:
            _DIRECTDL.pop(dl, None)
    if len(_DIRECTDL) == 0:
        print('no resources to direct download')
        return
    while True:
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
                if _msg.content in _DIRECTDL:
                    msg = _msg
                else:
                    _release_list.append(_msg)
            if msg is not None:
                break
        # renew lease
        _QUEUE_MESSAGES[msg.id] = msg
        # create renew callback
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
        file = None
        # download data
        resource = msg.content
        if resource.startswith(_DOCKER_TAG):
            if len(_REGISTRIES) < 1:
                raise RuntimeError(
                    ('{} image specified for global resource, but there are '
                     'no registries available').format(resource))
            image = resource[resource.find(_DOCKER_TAG) + len(_DOCKER_TAG):]
            while True:
                # pick random registry to download from
                registry_ip = _pick_random_registry_key()
                print('pulling image {} from {}'.format(image, registry_ip))
                if registry_ip == 'registry.hub.docker.com':
                    proc = await asyncio.subprocess.create_subprocess_shell(
                        'docker pull {}'.format(image), loop=loop
                    )
                else:
                    registry_port = _REGISTRIES[registry_ip]['Port']
                    proc = await asyncio.subprocess.create_subprocess_shell(
                        'docker pull {}:{}/{}'.format(
                            registry_ip, registry_port, image), loop=loop
                    )
                await proc.wait()
                if proc.returncode == 0:
                    break
                else:
                    print('docker pull non-zero rc: {}'.format(
                        proc.returncode))
                    await asyncio.sleep(1)
            # save docker image to seed to torrent
            print('saving docker image for seeding')
            file = _TORRENT_DIR / '{}.tar.gz'.format(image)
            proc = await asyncio.subprocess.create_subprocess_shell(
                'docker save {} | gzip -c > {}'.format(
                    image, file), loop=loop)
            await proc.wait()
            if proc.returncode != 0:
                raise RuntimeError('docker save non-zero rc: {}'.format(
                    proc.returncode))
        else:
            # TODO download via blob, explode uri to get container/blob
            # use download to path into /tmp and move to _TORRENT_DIR
            raise NotImplemented()
        # generate torrent file
        torrent_file, torrent_b64, torrent_sha1 = generate_torrent(str(file))
        # add to torrent dict (effectively enqueues for torrent start)
        entity = {
            'PartitionKey': _PARTITION_KEY,
            'RowKey': resource,
            'TorrentFileBase64': torrent_b64,
            'TorrentFileSHA1': torrent_sha1,
            'FileSizeBytes': file.stat().st_size,
            # 'FileSHA1': compute_sha1_for_file(file),
            'DHTNodes': ipaddress,
        }
        _TORRENTS[resource] = {
            'entity': entity,
            'etag': None,
            'torrent_file': torrent_file,
            'started': False
        }
        # wait until torrent has started
        while not _TORRENTS[resource]['started']:
            await asyncio.sleep(1)
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
        # remove resources from download list
        _DIRECTDL.pop(resource)
        if len(_DIRECTDL) == 0:
            break


def _merge_torrentinfo(
        table_client: azure.storage.table.TableService,
        key: str):
    """Merge info into torrentinfo table
    :param azure.storage.table.TableService table_client: table client
    :param str key: torrent dict key
    """
    entity = _TORRENTS[key]
    print('merging entity for {} to torrentinfo table: {}'.format(key, entity))
    try:
        if entity['etag'] is None:
            entity['etag'] = table_client.insert_entity(
                _STORAGE_CONTAINERS['table_torrentinfo'],
                entity=entity)
    except azure.common.AzureConflictHttpError:
        while True:
            existing = table_client.get_entity(
                _STORAGE_CONTAINERS['table_torrentinfo'],
                entity['PartitionKey'], entity['RowKey'])
            # ensure we're talking about the same file
            if existing['TorrentFileSHA1'] != entity['TorrentFileSHA1']:
                raise RuntimeError(
                    ('torrent file SHA1 mismatch. '
                     'existing: {} entity: {})'.format(existing, entity)))
            # merge dht_node into existing
            edht = set(existing['DHTNodes'].split(','))
            ndht = set(entity['DHTNodes'].split(','))
            edht.update(ndht)
            existing['DHTNodes'] = ','.join(list(edht))
            etag = existing['etag']
            existing.pop('etag')
            try:
                existing['etag'] = table_client.merge_entity(
                    _STORAGE_CONTAINERS['table_torrentinfo'], entity=existing,
                    if_match=etag)
                _TORRENTS[key] = existing
                break
            except azure.common.AzureConflictHttpError:
                pass
    print('entity for {} merged to torrentinfo table: {}'.format(
        key, _TORRENTS[key]))


async def download_monitor_async(
        loop: asyncio.BaseEventLoop,
        blob_client: azure.storage.blob.BlockBlobService,
        queue_client: azure.storage.queue.QueueService,
        table_client: azure.storage.table.TableService,
        ipaddress: str):
    while True:
        # start applicable torrent sessions
        for resource in _TORRENTS:
            if _TORRENTS[resource]['started']:
                continue
            # start torrent session
            try:
                dht_nodes = _TORRENTS[
                    resource]['entity']['DHTNodes'].split(',')
            except KeyError:
                dht_nodes = []
            seed = ipaddress in dht_nodes
            th, session = create_torrent_session(
                _TORRENTS[resource]['torrent_file'], str(_TORRENT_DIR),
                seed)
            _TORRENTS[resource]['handle'] = th
            _TORRENTS[resource]['session'] = session
            print('created torrent session for: {} seed={}'.format(
                resource, seed))
            # if we're seeding add self to dht_nodes
            if th.is_seed():
                if ipaddress not in dht_nodes:
                    # add to torrentinfo table
                    dht_nodes.append(ipaddress)
                    entity = _TORRENTS[resource]['entity']
                    entity['DHTNodes'] = ','.join(dht_nodes)
                    _merge_torrentinfo(table_client, resource)
                    # TODO register to services table
            # mark torrent as started
            _TORRENTS[resource]['started'] = True
        # check if there are any direct downloads
        await _direct_download_resources_async(
            loop, blob_client, queue_client, table_client, ipaddress)
        # sleep to avoid pinning cpu
        await asyncio.sleep(1)


def _update_registries(
        table_client: azure.storage.table.TableService, ipaddress: str):
    # check if we exist in the list, do not update if so
    if ipaddress in _REGISTRIES:
        return
    print('refreshing docker private registry list...')
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_registry'],
            filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
    except azure.common.AzureMissingResourceHttpError:
        pass
    else:
        _REGISTRIES.clear()
        for ent in entities:
            _REGISTRIES[ent['RowKey']] = ent


def _check_resource_has_torrent(
        loop: asyncio.BaseEventLoop,
        table_client: azure.storage.table.TableService,
        resource: str,
        add_to_dict: bool=False) -> bool:
    try:
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_torrentinfo'],
            _PARTITION_KEY, resource)
    except azure.common.AzureMissingResourceHttpError:
        if add_to_dict:
            _DIRECTDL[resource] = None
        return False
    else:
        # write torrent file to disk
        torrent = base64.b64decode(entity['TorrentFileBase64'])
        torrent_file = _TORRENT_DIR / '{}.torrent'.format(
            entity['TorrentFileSHA1'])
        with open(torrent_file, 'wb') as f:
            f.write(torrent)
        try:
            etag = entity['etag']
            entity.pop('etag')
        except KeyError:
            etag = None
        _TORRENTS[resource] = {
            'entity': entity,
            'etag': etag,
            'torrent_file': torrent_file,
            'started': False,
        }
    return True


def distribute_global_resources(
        loop: asyncio.BaseEventLoop,
        blob_client: azure.storage.blob.BlockBlobService,
        queue_client: azure.storage.queue.QueueService,
        table_client: azure.storage.table.TableService,
        ipaddress: str, container: str):
    """Distribute global services/resources
    :param asyncio.BaseEventLoop loop: event loop
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param str ipaddress: ip address
    :param str container: container holding registry
    """
    # get private registry list
    _update_registries(table_client, ipaddress)
    # get globalresources from table
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_globalresources'],
            filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
    except azure.common.AzureMissingResourceHttpError:
        entities = []
    # check torrent info table for resource
    for ent in entities:
        _check_resource_has_torrent(loop, table_client, ent['RowKey'], True)
    # run async func in loop
    loop.run_until_complete(download_monitor_async(
        loop, blob_client, queue_client, table_client, ipaddress))


def test_torrent():
    file = '/tmp/test/test2.bin'
    torrent_name = 'test.torrent'
    generate_torrent(torrent_name, file)
    h, session = create_torrent_session(
        torrent_name, str(pathlib.Path(file).parent), True)

    print('Name: {} Total size: {}'.format(h.name(), h.status().total_wanted))
    while True:
        s = h.status()

        print(
            '\r%.2f%% complete (down: %.1f kb/s up: %.1f kB/s peers: %d) %s' %
            (s.progress * 100, s.download_rate / 1000, s.upload_rate / 1000,
             s.num_peers, _TORRENT_STATE[s.state]))
        sys.stdout.flush()
        p = h.get_peer_info()
        for i in p:
            print(i)
            print(i.ip)
        # print(h.is_seed())
        # print(session.is_dht_running())

        time.sleep(1)


def main():
    """Main function"""
    # get command-line args
    args = parseargs()

    # for local testing
    if args.ipaddress is None:
        args.ipaddress = subprocess.check_output(
            'ip addr list eth0 | grep "inet " | cut -d\' \' -f6 | cut -d/ -f1',
            shell=True).decode('ascii').strip()

    # get event loop
    loop = asyncio.get_event_loop()

    # set up container names
    _setup_container_names(args.prefix)

    # create storage credentials
    blob_client, queue_client, table_client = _create_credentials()

    # create torrent directory
    _TORRENT_DIR.mkdir(parents=True, exist_ok=True)

    # set up private registry
    if args.privateregistry:
        loop.run_until_complete(setup_private_registry_async(
            loop, queue_client, table_client, args.ipaddress,
            args.privateregistry))

    # distribute global resources
    distribute_global_resources(
        loop, blob_client, queue_client, table_client, args.ipaddress,
        args.privateregistry)


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
    parser.add_argument(
        '--privateregistry',
        help='enable private registry and container name')
    return parser.parse_args()

if __name__ == '__main__':
    main()
