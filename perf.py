#!/usr/bin/env python3

# stdlib imports
import argparse
import datetime
import os
# non-stdlib imports
import azure.storage.table as azuretable

# global defines
_STORAGEACCOUNT = os.environ['CASCADE_SA']
_STORAGEACCOUNTKEY = os.environ['CASCADE_SAKEY']
_BATCHACCOUNT = os.environ['AZ_BATCH_ACCOUNT_NAME']
_POOLID = os.environ['AZ_BATCH_POOL_ID']
_NODEID = os.environ['AZ_BATCH_NODE_ID']
_PARTITION_KEY = '{}${}'.format(_BATCHACCOUNT, _POOLID)


def _create_credentials():
    """Create storage credentials
    :rtype: azure.storage.table.TableService
    :return: azure storage table client
    """
    ep = os.getenv('CASCADE_EP') or 'core.windows.net'
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=ep)
    return table_client


def process_event(table_client, table_name, source, event, ts, message):
    entity = {
        'PartitionKey': _PARTITION_KEY,
        'RowKey': str(ts),
        'Event': '{}:{}'.format(source, event),
        'NodeId': _NODEID,
        'Message': message,
    }
    table_client.insert_entity(table_name, entity)


def main():
    """Main function"""
    # get command-line args
    args = parseargs()
    if args.ts is None:
        args.ts = datetime.datetime.utcnow().timestamp()
    args.source = args.source.lower()
    args.event = args.event.lower()

    # set up container name
    table_name = args.prefix + 'perf'
    # create storage credentials
    table_client = _create_credentials()
    # insert perf event into table
    process_event(
        table_client, table_name, args.source, args.event, args.ts,
        args.message)


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Shipyard perf recorder')
    parser.add_argument('source', help='event source')
    parser.add_argument('event', help='event')
    parser.add_argument('--ts', help='timestamp (posix)')
    parser.add_argument('--message', help='message')
    parser.add_argument('--prefix', help='storage container prefix')
    return parser.parse_args()

if __name__ == '__main__':
    main()
