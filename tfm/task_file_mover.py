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
import fnmatch
import logging
import logging.handlers
import os
import pathlib
# non-stdlib imports
import azure.batch.batch_auth as batchauth
import azure.batch.batch_service_client as batch

# create logger
logger = logging.getLogger(__name__)


def _setup_logger() -> None:
    # type: (None) -> None
    """Set up logger"""
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)sZ %(levelname)s %(name)s:%(funcName)s:%(lineno)d '
        '%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _create_credentials():
    # type: (None) -> azure.batch.batch_service_client.BatchServiceClient
    """Create authenticated client
    :rtype: `azure.batch.batch_service_client.BatchServiceClient`
    :return: batch_client
    """
    ba, url, bakey = os.environ['SHIPYARD_BATCH_ENV'].split(';')
    batch_client = batch.BatchServiceClient(
        batchauth.SharedKeyCredentials(ba, bakey), base_url=url)
    batch_client.config.add_user_agent('batch-shipyard/tfm')
    return batch_client


def get_all_files_via_task(batch_client, job_id, task_id, incl, excl, dst):
    # type: (batch.BatchServiceClient, str, str, list, list, str) -> None
    """Get all files from a task
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    """
    # prepare incl/excl filters
    if incl is not None:
        incl = incl.split(';')
    if excl is not None:
        excl = excl.split(';')
    # iterate through all files in task and download them
    logger.debug('downloading files to {}'.format(dst))
    files = batch_client.file.list_from_task(job_id, task_id, recursive=True)
    i = 0
    dirs_created = set('.')
    for file in files:
        if file.is_directory:
            continue
        if excl is not None:
            inc = not any([fnmatch.fnmatch(file.name, x) for x in excl])
        else:
            inc = True
        if incl is not None:
            inc = any([fnmatch.fnmatch(file.name, x) for x in incl])
        if not inc:
            logger.debug('skipping file {} due to filters'.format(
                file.name))
            continue
        fp = pathlib.Path(dst, file.name)
        if str(fp.parent) not in dirs_created:
            fp.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            dirs_created.add(str(fp.parent))
        stream = batch_client.file.get_from_task(job_id, task_id, file.name)
        with fp.open('wb') as f:
            for data in stream:
                f.write(data)
        i += 1
    if i == 0:
        logger.error(
            'no files found for task {} job {} include={} exclude={}'.format(
                task_id, job_id, incl if incl is not None else '',
                excl if excl is not None else '', ))
    else:
        logger.info(
            'all task files retrieved from job={} task={} include={} '
            'exclude={}'.format(
                task_id, job_id, incl if incl is not None else '',
                excl if excl is not None else '', ))


def main():
    """Main function"""
    # get command-line args
    args = parseargs()

    batch_client = _create_credentials()

    get_all_files_via_task(
        batch_client, args.jobid, args.taskid, args.include,
        args.exclude, args.dst)


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='tfm: Azure Batch task file mover')
    parser.set_defaults(dst='.')
    parser.add_argument('jobid', help='job id')
    parser.add_argument('taskid', help='task id')
    parser.add_argument('--include', help='include filter')
    parser.add_argument('--exclude', help='exclude filter')
    parser.add_argument('--dst', help='local destination path')
    return parser.parse_args()

if __name__ == '__main__':
    _setup_logger()
    main()
