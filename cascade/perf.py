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
import datetime
import os
# non-stdlib imports
import azure.common
import azure.storage.table as azuretable

# global defines
_BATCHACCOUNT = os.environ['AZ_BATCH_ACCOUNT_NAME']
_POOLID = os.environ['AZ_BATCH_POOL_ID']
_NODEID = os.environ['AZ_BATCH_NODE_ID']
_PARTITION_KEY = '{}${}'.format(_BATCHACCOUNT, _POOLID)


def _create_credentials() -> azuretable.TableService:
    """Create storage credentials
    :rtype: azure.storage.table.TableService
    :return: azure storage table client
    """
    sa, ep, sakey = os.environ['SHIPYARD_STORAGE_ENV'].split(':')
    table_client = azuretable.TableService(
        account_name=sa,
        account_key=sakey,
        endpoint_suffix=ep)
    return table_client


def process_event(
        table_client: azure.storage.table.TableService,
        table_name: str, source: str, event: str, ts: float,
        message: str) -> None:
    """Process event
    :param azure.storage.table.TableService table_client: table client
    :param str table_name: table name
    :param str source: source
    :param str event: event
    :param float ts: time stamp
    :param str message: message
    """
    entity = {
        'PartitionKey': _PARTITION_KEY,
        'RowKey': str(ts),
        'Event': '{}:{}'.format(source, event),
        'NodeId': _NODEID,
        'Message': message,
    }
    while True:
        try:
            table_client.insert_entity(table_name, entity)
            break
        except azure.common.AzureConflictHttpError:
            if not isinstance(ts, float):
                ts = float(ts)
            ts += 0.000001
            entity['RowKey'] = str(ts)


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
