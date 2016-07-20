#!/usr/bin/env python3

# stdlib imports
import argparse
import datetime
import json
import hashlib
import os
import pathlib
import pprint
import time
from typing import List
# non-stdlib imports
import azure.batch.batch_auth as batchauth
import azure.batch.batch_service_client as batch
import azure.batch.models as batchmodels
import azure.common
import azure.storage.blob as azureblob
import azure.storage.queue as azurequeue
import azure.storage.table as azuretable

# global defines
_STORAGEACCOUNT = os.getenv('STORAGEACCOUNT')
_STORAGEACCOUNTKEY = os.getenv('STORAGEACCOUNTKEY')
_BATCHACCOUNTKEY = os.getenv('BATCHACCOUNTKEY')
_STORAGE_CONTAINERS = {
    'blob_resourcefiles': None,
    'table_registry': None,
    'table_torrentinfo': None,
    'table_service': None,
    'table_globalresources': None,
    'queue_registry': None,
    'queue_globalresources': None,
}
_REGISTRY_FILENAME = 'docker-registry-v2.tar.gz'
_NODEPREP_FILE = ('nodeprep.sh', 'scripts/nodeprep.sh')
_CASCADE_FILE = ('cascade.py', 'cascade.py')
_SETUP_PR_FILE = ('setup_private_registry.py', 'setup_private_registry.py')
_REGISTRY_FILE = (
    _REGISTRY_FILENAME, 'resources/{}'.format(_REGISTRY_FILENAME)
)


def _populate_global_settings(config: dict):
    """Populate global settings from config
    :param dict config: configuration dict
    """
    global _STORAGEACCOUNT, _STORAGEACCOUNTKEY, _BATCHACCOUNTKEY
    global _STORAGE_ENTITY_PREFIX
    _STORAGEACCOUNT = config[
        'global_settings']['credentials']['storage_account']
    _STORAGEACCOUNTKEY = config[
        'global_settings']['credentials']['storage_account_key']
    _BATCHACCOUNTKEY = config[
        'global_settings']['credentials']['batch_account_key']
    try:
        sep = config['global_settings']['storage_entity_prefix']
    except KeyError:
        sep = None
    if sep is None:
        sep = ''
    _STORAGE_CONTAINERS['blob_resourcefiles'] = sep + 'resourcefiles'
    _STORAGE_CONTAINERS['table_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['table_torrentinfo'] = sep + 'torrentinfo'
    _STORAGE_CONTAINERS['table_services'] = sep + 'services'
    _STORAGE_CONTAINERS['table_globalresources'] = sep + 'globalresources'
    _STORAGE_CONTAINERS['queue_registry'] = sep + 'registry'
    _STORAGE_CONTAINERS['queue_globalresources'] = sep + 'globalresources'


def _wrap_commands_in_shell(commands: List[str], wait: bool=True) -> str:
    """Wrap commands in a shell
    :param list commands: list of commands to wrap
    :param bool wait: add wait for background processes
    :rtype: str
    :return: wrapped commands
    """
    return '/bin/bash -c "set -e; set -o pipefail; {}{}"'.format(
        ';'.join(commands), '; wait' if wait else '')


def _create_credentials(config: dict) -> tuple:
    """Create authenticated clients
    :param dict config: configuration dict
    :rtype: tuple
    :return: (batch client, blob client, queue client, table client)
    """
    credentials = batchauth.SharedKeyCredentials(
        config['global_settings']['credentials']['batch_account'],
        _BATCHACCOUNTKEY)
    batch_client = batch.BatchServiceClient(
        credentials,
        base_url='https://{}.{}.{}'.format(
            config['global_settings']['credentials']['batch_account'],
            config['global_settings']['credentials']['batch_account_region'],
            config['global_settings']['credentials']['batch_endpoint']))
    blob_client = azureblob.BlockBlobService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=config[
            'global_settings']['credentials']['storage_endpoint'])
    queue_client = azurequeue.QueueService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=config[
            'global_settings']['credentials']['storage_endpoint'])
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=config[
            'global_settings']['credentials']['storage_endpoint'])
    return batch_client, blob_client, queue_client, table_client


def upload_resource_files(
        blob_client: azure.storage.blob.BlockBlobService, config: dict,
        files: List[tuple]) -> dict:
    """Upload resource files to blob storage
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    :rtype: dict
    :return: sas url dict
    """
    sas_urls = {}
    for file in files:
        upload = True
        if file[0] == _REGISTRY_FILENAME:
            fp = pathlib.Path(file[1])
            if not fp.exists():
                print('skipping optional docker registry image: {}'.format(
                    _REGISTRY_FILENAME))
                continue
            else:
                # check if blob exists
                try:
                    prop = blob_client.get_blob_properties(
                        _STORAGE_CONTAINERS['blob_resourcefiles'], file[0])
                    # TODO use MD5 instead
                    if (prop.name == _REGISTRY_FILENAME and
                            prop.properties.content_length ==
                            fp.stat().st_size):
                        print(('remote file size is the same '
                               'for {}, skipping').format(_REGISTRY_FILENAME))
                        upload = False
                except azure.common.AzureMissingResourceHttpError:
                    pass
        if upload:
            print('uploading file: {}'.format(file[1]))
            blob_client.create_blob_from_path(
                _STORAGE_CONTAINERS['blob_resourcefiles'], file[0], file[1])
        sas_urls[file[0]] = 'https://{}.blob.{}/{}/{}?{}'.format(
            _STORAGEACCOUNT,
            config['global_settings']['credentials']['storage_endpoint'],
            _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
            blob_client.generate_blob_shared_access_signature(
                _STORAGE_CONTAINERS['blob_resourcefiles'], file[0],
                permission=azureblob.BlobPermissions.READ,
                expiry=datetime.datetime.utcnow() +
                datetime.timedelta(hours=2)
            )
        )
    return sas_urls


def add_pool(
        batch_client: azure.batch.batch_service_client.BatchServiceClient,
        blob_client: azure.storage.blob.BlockBlobService, config: dict):
    """Add a Batch pool to account
    :param azure.batch.batch_service_client.BatchServiceClient: batch client
    :param azure.storage.blob.BlockBlobService blob_client: blob client
    :param dict config: configuration dict
    """
    publisher = config['addpool']['poolspec']['publisher']
    offer = config['addpool']['poolspec']['offer']
    sku = config['addpool']['poolspec']['sku']
    try:
        p2p = config['addpool']['peer_to_peer']['enabled']
    except KeyError:
        p2p = True
    try:
        preg = 'private' in config['addpool']['docker_registry']
        pcont = config['addpool']['docker_registry']['private']['container']
    except KeyError:
        preg = False
    try:
        dockeruser = config['addpool']['docker_registry']['login']['username']
        dockerpw = config['addpool']['docker_registry']['login']['password']
    except KeyError:
        dockeruser = None
        dockerpw = None
    try:
        prefix = config['global_settings']['storage_entity_prefix']
        if len(prefix) == 0:
            prefix = None
    except KeyError:
        prefix = None
    # TODO for now, only support Ubuntu 16.04
    if (publisher != 'Canonical' or offer != 'UbuntuServer' or
            sku < '16.04.0-LTS'):
        raise ValueError('Unsupported Docker Host VM Config')
    # pick latest sku
    node_agent_skus = batch_client.account.list_node_agent_skus()
    skus_to_use = [
        (nas, image_ref) for nas in node_agent_skus for image_ref in sorted(
            nas.verified_image_references, key=lambda item: item.sku)
        if image_ref.publisher.lower() == publisher.lower() and
        image_ref.offer.lower() == offer.lower() and
        image_ref.sku.lower() == sku.lower()
    ]
    sku_to_use, image_ref_to_use = skus_to_use[-1]
    # upload resource files
    sas_urls = upload_resource_files(
        blob_client, config, [
            _NODEPREP_FILE, _CASCADE_FILE, _SETUP_PR_FILE, _REGISTRY_FILE
        ]
    )
    # create pool param
    pool = batchmodels.PoolAddParameter(
        id=config['addpool']['poolspec']['id'],
        virtual_machine_configuration=batchmodels.VirtualMachineConfiguration(
            image_reference=image_ref_to_use,
            node_agent_sku_id=sku_to_use.id),
        vm_size=config['addpool']['poolspec']['vm_size'],
        target_dedicated=config['addpool']['poolspec']['vm_count'],
        start_task=batchmodels.StartTask(
            command_line='nodeprep.sh -o {} -s {}{}{}{}'.format(
                offer, sku,
                ' -p {}'.format(prefix) if prefix else '',
                ' -r {}'.format(pcont) if preg else '',
                ' -t' if p2p else ''
            ),
            run_elevated=True,
            wait_for_success=True,
            environment_settings=[
                batchmodels.EnvironmentSetting('LC_ALL', 'en_US.UTF-8'),
                batchmodels.EnvironmentSetting('CASCADE_SA', _STORAGEACCOUNT),
                batchmodels.EnvironmentSetting(
                    'CASCADE_SAKEY', _STORAGEACCOUNTKEY),
            ],
            resource_files=[],
        ),
    )
    for rf in sas_urls:
        pool.start_task.resource_files.append(
            batchmodels.ResourceFile(
                file_path=rf,
                blob_source=sas_urls[rf])
        )
    if preg:
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'PRIVATE_REGISTRY_SA',
                config['addpool']['docker_registry'][
                    'private']['storage_account'])
        )
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting(
                'PRIVATE_REGISTRY_SAKEY',
                config['addpool']['docker_registry'][
                    'private']['storage_account_key'])
        )
    if (dockeruser is not None and len(dockeruser) > 0 and
            dockerpw is not None and len(dockerpw) > 0):
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('DOCKER_LOGIN_USERNAME', dockeruser)
        )
        pool.start_task.environment_settings.append(
            batchmodels.EnvironmentSetting('DOCKER_LOGIN_PASSWORD', dockerpw)
        )
    # create pool if not exists
    try:
        print('Attempting to create pool:', pool.id)
        batch_client.pool.add(pool)
        print('Created pool:', pool.id)
    except batchmodels.BatchErrorException as e:
        if e.error.code != 'PoolExists':
            raise
        else:
            print('Pool {!r} already exists'.format(pool.id))
    # wait for pool idle
    node_state = frozenset(
        (batchmodels.ComputeNodeState.starttaskfailed,
         batchmodels.ComputeNodeState.unusable,
         batchmodels.ComputeNodeState.idle)
    )
    print('waiting for all nodes in pool {} to reach one of: {!r}'.format(
        pool.id, node_state))
    i = 0
    while True:
        # refresh pool to ensure that there is no resize error
        pool = batch_client.pool.get(pool.id)
        if pool.resize_error is not None:
            raise RuntimeError(
                'resize error encountered for pool {}: {!r}'.format(
                    pool.id, pool.resize_error))
        nodes = list(batch_client.compute_node.list(pool.id))
        if (len(nodes) >= pool.target_dedicated and
                all(node.state in node_state for node in nodes)):
            break
        i += 1
        if i % 3 == 0:
            print('waiting for {} nodes to reach desired state...'.format(
                pool.target_dedicated))
        time.sleep(10)
    get_remote_login_settings(batch_client, pool.id, nodes)
    if any(node.state != batchmodels.ComputeNodeState.idle for node in nodes):
        raise RuntimeError('node(s) of pool {} not in idle state'.format(
            pool.id))


def resize_pool(batch_client, pool_id, vm_count):
    print('Resizing pool {} to {}'.format(pool_id, vm_count))
    prp = batchmodels.PoolResizeParameter(
        target_dedicated=vm_count,
        resize_timeout=datetime.timedelta(minutes=20),
    )
    batch_client.pool.resize(
        pool_id=pool_id,
        pool_resize_parameter=prp,
    )


def del_pool(batch_client, pool_id):
    print('Deleting pool: {}'.format(pool_id))
    batch_client.pool.delete(pool_id)


def add_job(batch_client, pool_id, job_id, numtasks):
    # add job
    job = batchmodels.JobAddParameter(
        id=job_id,
        pool_info=batchmodels.PoolInformation(pool_id=pool_id),
        common_environment_settings=[
            batchmodels.EnvironmentSetting('LC_ALL', 'en_US.UTF-8'),
            batchmodels.EnvironmentSetting(
                'STORAGEACCOUNT', _STORAGEACCOUNT),
            batchmodels.EnvironmentSetting(
                'STORAGEACCOUNTKEY', _STORAGEACCOUNTKEY),
        ],
    )
    batch_client.job.add(job)
    for i in range(0, numtasks):
        add_task(batch_client, pool_id, job.id, i)


def add_task(batch_client, pool_id, job_id, tasknum=None):
    if tasknum is None:
        tasknum = int(sorted(
            batch_client.task.list(job_id), key=lambda x: x.id
        )[-1].split('-')[-1]) + 1
    print('creating task number {}'.format(tasknum))
    task_commands = [
        '',
    ]
    task = batchmodels.TaskAddParameter(
        id='demotask-{}'.format(tasknum),
        command_line=_wrap_commands_in_shell(task_commands),
    )
    print(task.command_line)
    batch_client.task.add(job_id=job_id, task=task)


def del_job(batch_client, job_id):
    print('Deleting job: {}'.format(job_id))
    batch_client.job.delete(job_id)


def del_all_jobs(batch_client):
    print('Listing jobs...')
    jobs = batch_client.job.list()
    for job in jobs:
        del_job(batch_client, job.id)


def get_remote_login_settings(batch_client, pool_id, nodes=None):
    if nodes is None:
        nodes = batch_client.compute_node.list(pool_id)
    for node in nodes:
        rls = batch_client.compute_node.get_remote_login_settings(
            pool_id, node.id)
        print('node {}: {}'.format(node.id, rls))


def delete_storage_containers(blob_client, queue_client, table_client, config):
    blob_client.delete_container(_STORAGE_CONTAINERS['blob_resourcefiles'])
    table_client.delete_table(_STORAGE_CONTAINERS['table_registry'])
    table_client.delete_table(_STORAGE_CONTAINERS['table_torrentinfo'])
    table_client.delete_table(_STORAGE_CONTAINERS['table_services'])
    table_client.delete_table(_STORAGE_CONTAINERS['table_globalresources'])
    queue_client.delete_queue(_STORAGE_CONTAINERS['queue_registry'])
    queue_client.delete_queue(_STORAGE_CONTAINERS['queue_globalresources'])


def _clear_blobs(blob_client, container):
    print('deleting blobs: {}'.format(container))
    blobs = blob_client.list_blobs(container)
    for blob in blobs:
        blob_client.delete_blob(container, blob.name)


def _clear_table(table_client, table_name):
    print('clearing table: {}'.format(table_name))
    ents = table_client.query_entities(table_name)
    for ent in ents:
        table_client.delete_entity(
            table_name, ent['PartitionKey'], ent['RowKey'])


def clear_storage_containers(blob_client, queue_client, table_client, config):
    # _clear_blobs(blob_client, _STORAGE_CONTAINERS['blob_resourcefiles'])
    _clear_table(table_client, _STORAGE_CONTAINERS['table_registry'])
    _clear_table(table_client, _STORAGE_CONTAINERS['table_torrentinfo'])
    _clear_table(table_client, _STORAGE_CONTAINERS['table_services'])
    _clear_table(table_client, _STORAGE_CONTAINERS['table_globalresources'])
    print('clearing queue: {}'.format(_STORAGE_CONTAINERS['queue_registry']))
    queue_client.clear_messages(_STORAGE_CONTAINERS['queue_registry'])
    print('clearing queue: {}'.format(
        _STORAGE_CONTAINERS['queue_globalresources']))
    queue_client.clear_messages(_STORAGE_CONTAINERS['queue_globalresources'])


def create_storage_containers(blob_client, queue_client, table_client, config):
    blob_client.create_container(_STORAGE_CONTAINERS['blob_resourcefiles'])
    table_client.create_table(_STORAGE_CONTAINERS['table_registry'])
    table_client.create_table(_STORAGE_CONTAINERS['table_torrentinfo'])
    table_client.create_table(_STORAGE_CONTAINERS['table_services'])
    table_client.create_table(_STORAGE_CONTAINERS['table_globalresources'])
    queue_client.create_queue(_STORAGE_CONTAINERS['queue_registry'])
    queue_client.create_queue(_STORAGE_CONTAINERS['queue_globalresources'])


def populate_queues(queue_client, table_client, config):
    try:
        use_hub = 'private' not in config['addpool']['docker_registry']
    except KeyError:
        use_hub = True
    pk = '{}${}'.format(
        config['global_settings']['credentials']['batch_account'],
        config['addpool']['poolspec']['id'])
    # if using docker public hub, then populate registry table with hub
    if use_hub:
        table_client.insert_or_replace_entity(
            _STORAGE_CONTAINERS['table_registry'],
            {
                'PartitionKey': pk,
                'RowKey': 'registry.hub.docker.com',
                'Port': 80,
            }
        )
    else:
        # populate registry queue
        for i in range(0, 3):
            queue_client.put_message(
                _STORAGE_CONTAINERS['queue_registry'], 'create-{}'.format(i))
    # populate global resources
    try:
        for gr in config['addpool']['global_resources']:
            table_client.insert_or_replace_entity(
                _STORAGE_CONTAINERS['table_globalresources'],
                {
                    'PartitionKey': pk,
                    'RowKey': hashlib.sha1(gr.encode('utf8')).hexdigest(),
                    'Resource': gr,
                }
            )
            queue_client.put_message(
                _STORAGE_CONTAINERS['queue_globalresources'], gr)
    except KeyError:
        pass


def main():
    """Main function"""
    # get command-line args
    args = parseargs()
    args.action = args.action.lower()

    if args.json is not None:
        with open(args.json, 'r') as f:
            config = json.load(f)
        print('config:')
        pprint.pprint(config)
        _populate_global_settings(config)

    batch_client, blob_client, queue_client, table_client = \
        _create_credentials(config)

    if args.action == 'addpool':
        create_storage_containers(
            blob_client, queue_client, table_client, config)
        populate_queues(queue_client, table_client, config)
        add_pool(batch_client, blob_client, config)
    elif args.action == 'resizepool':
        resize_pool(batch_client, args.poolid, args.numvms)
    elif args.action == 'delpool':
        del_pool(batch_client, args.poolid)
    elif args.action == 'addjob':
        add_job(batch_client, args.poolid, args.jobid, args.numtasks)
    elif args.action == 'addtask':
        add_task(batch_client, args.poolid, args.jobid, args.tasknum)
    elif args.action == 'deljob':
        del_job(batch_client, args.jobid)
    elif args.action == 'delalljobs':
        del_all_jobs(batch_client)
    elif args.action == 'grl':
        get_remote_login_settings(batch_client, args.poolid)
    elif args.action == 'delstorage':
        delete_storage_containers(
            blob_client, queue_client, table_client, config)
    elif args.action == 'clearstorage':
        clear_storage_containers(
            blob_client, queue_client, table_client, config)
    else:
        raise ValueError('Unknown action: {}'.format(args.action))


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Shipyard: Azure Batch to Docker Bridge')
    parser.add_argument(
        'action', help='action: addpool, addjob, addtask, delpool, deljob, '
        'delalljobs, grl, delstorage, clearstorage')
    parser.add_argument(
        '--json',
        help='json file config for option. required for all add actions')
    parser.add_argument('--poolid', help='pool id')
    parser.add_argument('--jobid', help='job id')
    return parser.parse_args()

if __name__ == '__main__':
    main()
