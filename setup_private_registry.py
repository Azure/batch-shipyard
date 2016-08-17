#!/usr/bin/env python3

# stdlib imports
import argparse
import asyncio
import os
import pathlib
import subprocess
from typing import List
# non-stdlib imports
import azure.common
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable

# global defines
_DEFAULT_PRIVATE_REGISTRY_PORT = 5000
_STORAGEACCOUNT = os.environ['PRIVATE_REGISTRY_SA']
_STORAGEACCOUNTKEY = os.environ['PRIVATE_REGISTRY_SAKEY']
_BATCHACCOUNT = os.environ['AZ_BATCH_ACCOUNT_NAME']
_POOLID = os.environ['AZ_BATCH_POOL_ID']
_NODEID = os.environ['AZ_BATCH_NODE_ID']
_PARTITION_KEY = '{}${}'.format(_BATCHACCOUNT, _POOLID)
# mutable global state
_CBHANDLES = {}
_QUEUE_MESSAGES = {}
_STORAGE_CONTAINERS = {
    'table_registry': None,
    'queue_registry': None,
}


def _setup_container_names(sep: str):
    """Set up storage container names
    :param str sep: storage container prefix
    """
    if sep is None:
        sep = ''
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['queue_registry'] = '-'.join(
        (sep + 'registry', _BATCHACCOUNT.lower(), _POOLID.lower()))


def _create_credentials() -> tuple:
    """Create storage credentials
    :rtype: tuple
    :return: (queue_client, table_client)
    """
    ep = os.getenv('CASCADE_EP') or 'core.windows.net'
    queue_client = azurequeue.QueueService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=ep)
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=ep)
    return queue_client, table_client


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
        raise RuntimeError('update message failed')
    _QUEUE_MESSAGES[msg_id].pop_receipt = msg.pop_receipt
    print('queue message updated id={} pr={}'.format(
        msg_id, _QUEUE_MESSAGES[msg_id].pop_receipt))
    _CBHANDLES[queue_key] = loop.call_later(
        15, _renew_queue_message_lease, loop, queue_client, queue_key, msg_id)


async def _start_private_registry_instance_async(
        loop: asyncio.BaseEventLoop, container: str,
        registry_archive: str, registry_image_id: str):
    """Start private docker registry instance
    :param asyncio.BaseEventLoop loop: event loop
    :param str container: storage container holding registry info
    :param str registry_archive: registry archive file
    :param str registry_image_id: registry image id
    """
    proc = await asyncio.subprocess.create_subprocess_shell(
        'docker images | grep -E \'^registry.*2\' | awk -e \'{print $3}\'',
        stdout=asyncio.subprocess.PIPE, loop=loop)
    stdout = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError('docker images non-zero rc: {}'.format(
            proc.returncode))
    if (stdout[0].strip() != registry_image_id and
            pathlib.Path(registry_archive).exists()):
        print('importing registry from local file: {}'.format(
            registry_archive))
        proc = await asyncio.subprocess.create_subprocess_shell(
            'gunzip -c {} | docker load'.format(registry_archive), loop=loop)
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
        ipaddress: str, container: str,
        registry_archive: str, registry_image_id: str):
    """Set up a docker private registry if a ticket exists
    :param asyncio.BaseEventLoop loop: event loop
    :param azure.storage.queue.QueueService queue_client: queue client
    :param azure.storage.table.TableService table_client: table client
    :param str ipaddress: ip address
    :param str container: container holding registry
    :param str registry_archive: registry archive file
    :param str registry_image_id: registry image id
    """
    # first check if we've registered before
    try:
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_registry'], _PARTITION_KEY, ipaddress)
        print('private registry row already exists: {}'.format(entity))
        await _start_private_registry_instance_async(
            loop, container, registry_archive, registry_image_id)
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
            if len(list(entities)) == 0:
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
            await _start_private_registry_instance_async(
                loop, container, registry_archive, registry_image_id)
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


def get_private_registries(
        table_client: azure.storage.table.TableService) -> List[str]:
    """Get private registry list from table
    :param azure.storage.table.TableService table_client: table client
    :rtype: list
    :return: list of registries
    """
    registries = []
    print('refreshing docker private registry list')
    try:
        entities = table_client.query_entities(
            _STORAGE_CONTAINERS['table_registry'],
            filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
    except azure.common.AzureMissingResourceHttpError:
        pass
    else:
        for ent in entities:
            if ent['RowKey'] == 'registry.hub.docker.com':
                continue
            registries.append('{}:{}'.format(ent['RowKey'], ent['Port']))
    print(registries)
    return registries


def register_insecure_registries(offer: str, sku: str, registries: List[str]):
    """Register insecure registries with daemon
    :param str offer: vm offer
    :param str sku: vm sku
    :param list registries: list of registries
    """
    if offer == 'ubuntuserver':
        if sku.startswith('14.04') or sku.startswith('16.04'):
            # inject setting into docker opts
            with open('/etc/default/docker', 'r') as f:
                inf = f.readlines()
            for i in range(0, len(inf)):
                line = inf[i].strip()
                if line.startswith('DOCKER_OPTS='):
                    opts = line.split('DOCKER_OPTS=')[-1].strip('"')
                    tmp = opts.split('--insecure-registry')
                    buf = []
                    for registry in registries:
                        buf.append('--insecure-registry {}'.format(registry))
                    inf[i] = 'DOCKER_OPTS="{} {}"\n'.format(
                        tmp[0], ' '.join(buf))
                    break
                else:
                    continue
            with open('/etc/default/docker', 'w') as f:
                f.writelines(inf)
            # restart docker daemon
            print('restarting docker deaemon')
            if sku.startswith('14.04'):
                subprocess.check_call('service docker restart', shell=True)
            else:
                subprocess.check_call(
                    'systemctl restart docker.service', shell=True)
        else:
            raise RuntimeError('Unsupported sku {} for offer {}'.format(
                sku, offer))
    else:
        raise RuntimeError('Unsupported offer {} (sku {})'.format(offer, sku))


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
    queue_client, table_client = _create_credentials()

    # set up private registry
    loop.run_until_complete(setup_private_registry_async(
        loop, queue_client, table_client, args.ipaddress, args.container,
        args.regarchive, args.regimageid))

    # get private registries
    registries = get_private_registries(table_client)

    if len(registries) > 0:
        # modify init scripts with registry info
        register_insecure_registries(
            args.offer.lower(), args.sku.lower(), registries)
        # write registry file
        with open('.cascade_private_registries.txt', 'w') as f:
            for registry in registries:
                f.write('{}\n'.format(registry))

    # stop asyncio loop
    loop.stop()
    loop.close()


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Install Docker Private Registry')
    parser.add_argument(
        'offer', help='vm offer')
    parser.add_argument(
        'sku', help='vm sku')
    parser.add_argument(
        'ipaddress', nargs='?', default=None, help='ip address')
    parser.add_argument(
        '--regarchive', help='private registry archive')
    parser.add_argument(
        '--regimageid', help='private registry image id')
    parser.add_argument(
        '--prefix', help='storage container prefix')
    parser.add_argument(
        '--container', help='private registry container name')
    return parser.parse_args()

if __name__ == '__main__':
    main()
