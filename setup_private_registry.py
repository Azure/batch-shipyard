#!/usr/bin/env python3

# stdlib imports
import argparse
import asyncio
import os
import pathlib
import subprocess
# non-stdlib imports
import azure.common
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
_STORAGE_CONTAINERS = {
    'table_registry': None,
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
    :rtype: azure.storage.table.TableService
    :return: table client
    """
    ep = os.getenv('CASCADE_EP') or 'core.windows.net'
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=ep)
    return table_client


async def _start_private_registry_instance_async(
        loop: asyncio.BaseEventLoop, container: str,
        registry_archive: str, registry_image_id: str):
    """Start private docker registry instance
    :param asyncio.BaseEventLoop loop: event loop
    :param str container: storage container holding registry info
    :param str registry_archive: registry archive file
    :param str registry_image_id: registry image id
    """
    # check if registry is already running
    proc = await asyncio.subprocess.create_subprocess_shell(
        'docker ps -f status=running -f name=registry | grep registry',
        loop=loop)
    await proc.wait()
    if proc.returncode == 0:
        print('detected running registry instance, not starting a new one')
        return
    # check for registry image
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
        table_client: azure.storage.table.TableService,
        ipaddress: str, container: str, registry_archive: str,
        registry_image_id: str):
    """Set up a docker private registry if a ticket exists
    :param asyncio.BaseEventLoop loop: event loop
    :param azure.storage.table.TableService table_client: table client
    :param str ipaddress: ip address
    :param str container: container holding registry
    :param str registry_archive: registry archive file
    :param str registry_image_id: registry image id
    """
    # first check if we've registered before
    try:
        entity = table_client.get_entity(
            _STORAGE_CONTAINERS['table_registry'], _PARTITION_KEY, _NODEID)
        exists = True
        print('private registry row already exists: {}'.format(entity))
    except azure.common.AzureMissingResourceHttpError:
        exists = False
    # install/start docker registy container
    await _start_private_registry_instance_async(
        loop, container, registry_archive, registry_image_id)
    # register self into registry table
    if not exists:
        entity = {
            'PartitionKey': _PARTITION_KEY,
            'RowKey': _NODEID,
            'IpAddress': ipaddress,
            'Port': _DEFAULT_PRIVATE_REGISTRY_PORT,
            'StorageAccount': _STORAGEACCOUNT,
            'Container': container,
        }
        table_client.insert_or_replace_entity(
            _STORAGE_CONTAINERS['table_registry'], entity=entity)


def main():
    """Main function"""
    # get command-line args
    args = parseargs()
    container, regarchive, regimageid = args.settings.split(':')

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
    table_client = _create_credentials()

    # set up private registry
    loop.run_until_complete(setup_private_registry_async(
        loop, table_client, args.ipaddress, container, regarchive, regimageid))

    # create a private registry file to notify cascade
    pathlib.Path('.cascade_private_registry.txt').touch()

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
        'settings',
        help='private registry settings '
        '[container:archive:imageid]')
    parser.add_argument(
        'ipaddress', nargs='?', default=None, help='ip address')
    parser.add_argument(
        '--prefix', help='storage container prefix')
    return parser.parse_args()

if __name__ == '__main__':
    main()
