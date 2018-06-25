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
import concurrent.futures
import logging
import logging.handlers
import multiprocessing
import os
import pickle
import time
# non-stdlib imports
import azure.batch.models as batchmodels
import azure.batch.batch_service_client as batch
import msrest.authentication

# create logger
logger = logging.getLogger(__name__)
# global defines
_AAD_TOKEN_TYPE = 'Bearer'
_TASKMAP_PICKLE_FILE = 'taskmap.pickle'
_MAX_EXECUTOR_WORKERS = min((multiprocessing.cpu_count() * 4, 32))


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


class TokenAuthentication(msrest.authentication.Authentication):
    """Token Authentication session handler"""
    def __init__(self, token):
        """Ctor for TokenAuthentication
        :param TokenAuthentication self: this
        :param str token: token
        """
        self._token = token

    @property
    def token(self):
        """Retrieve signed token
        :param TokenAuthentication self: this
        """
        return self._token

    @token.setter
    def token(self, value):
        """Set signed token
        :param TokenAuthentication self: this
        :param str value: token value
        """
        self._token = value

    def signed_session(self):
        """Get a signed session for requests.
        Usually called by the Azure SDKs for you to authenticate queries.
        :param TokenAuthentication self: this
        :rtype: requests.Session
        :return: request session with signed header
        """
        session = super(TokenAuthentication, self).signed_session()
        # set session authorization header
        session.headers['Authorization'] = '{} {}'.format(
            _AAD_TOKEN_TYPE, self._token)
        return session


def _create_credentials():
    # type: (None) -> azure.batch.batch_service_client.BatchServiceClient
    """Create authenticated client
    :rtype: `azure.batch.batch_service_client.BatchServiceClient`
    :return: batch_client
    """
    # get the AAD token provided to the job manager
    aad_token = os.environ['AZ_BATCH_AUTHENTICATION_TOKEN']
    account_service_url = os.environ['AZ_BATCH_ACCOUNT_URL']
    logger.debug('creating batch client for account url: {}'.format(
        account_service_url))
    credentials = TokenAuthentication(aad_token)
    batch_client = batch.BatchServiceClient(
        credentials, base_url=account_service_url)
    batch_client.config.add_user_agent('batch-shipyard/rjm')
    return batch_client


def _submit_task_sub_collection(
        batch_client, job_id, start, end, slice, all_tasks, task_map):
    # type: (batch.BatchServiceClient, str, int, int, int, list, dict) -> None
    """Submits a sub-collection of tasks, do not call directly
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job to add to
    :param int start: start offset, includsive
    :param int end: end offset, exclusive
    :param int slice: slice width
    :param list all_tasks: list of all task ids
    :param dict task_map: task collection map to add
    """
    initial_slice = slice
    while True:
        chunk_end = start + slice
        if chunk_end > end:
            chunk_end = end
        chunk = all_tasks[start:chunk_end]
        logger.debug('submitting {} tasks ({} -> {}) to job {}'.format(
            len(chunk), start, chunk_end - 1, job_id))
        try:
            results = batch_client.task.add_collection(job_id, chunk)
        except batchmodels.BatchErrorException as e:
            if e.error.code == 'RequestBodyTooLarge':
                # collection contents are too large, reduce and retry
                if slice == 1:
                    raise
                slice = slice >> 1
                if slice < 1:
                    slice = 1
                logger.error(
                    ('task collection slice was too big, retrying with '
                     'slice={}').format(slice))
                continue
        else:
            # go through result and retry just failed tasks
            while True:
                retry = []
                for result in results.value:
                    if result.status == batchmodels.TaskAddStatus.client_error:
                        de = None
                        if result.error.values is not None:
                            de = [
                                '{}: {}'.format(x.key, x.value)
                                for x in result.error.values
                            ]
                        logger.error(
                            ('skipping retry of adding task {} as it '
                             'returned a client error (code={} message={} {}) '
                             'for job {}').format(
                                 result.task_id, result.error.code,
                                 result.error.message,
                                 ' '.join(de) if de is not None else '',
                                 job_id))
                    elif (result.status ==
                          batchmodels.TaskAddStatus.server_error):
                        retry.append(task_map[result.task_id])
                if len(retry) > 0:
                    logger.debug('retrying adding {} tasks to job {}'.format(
                        len(retry), job_id))
                    results = batch_client.task.add_collection(job_id, retry)
                else:
                    break
        if chunk_end == end:
            break
        start = chunk_end
        slice = initial_slice


def _add_task_collection(batch_client, job_id, task_map):
    # type: (batch.BatchServiceClient, str, dict) -> None
    """Add a collection of tasks to a job
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job to add to
    :param dict task_map: task collection map to add
    """
    all_tasks = list(task_map.values())
    slice = 100  # can only submit up to 100 tasks at a time
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_EXECUTOR_WORKERS) as executor:
        for start in range(0, len(all_tasks), slice):
            end = start + slice
            if end > len(all_tasks):
                end = len(all_tasks)
            executor.submit(
                _submit_task_sub_collection, batch_client, job_id, start, end,
                end - start, all_tasks, task_map)
    logger.info('submitted all {} tasks to job {}'.format(
        len(task_map), job_id))


def _monitor_tasks(batch_client, job_id, numtasks):
    # type: (batch.BatchServiceClient, str, int) -> None
    """Monitor tasks for completion
    :param batch_client: The batch client to use.
    :type batch_client: `azure.batch.batch_service_client.BatchServiceClient`
    :param str job_id: job to add to
    :param int numtasks: number of tasks
    """
    i = 0
    j = 0
    while True:
        try:
            task_counts = batch_client.job.get_task_counts(job_id=job_id)
        except batchmodels.batch_error.BatchErrorException as ex:
            logger.exception(ex)
        else:
            if (task_counts.validation_status ==
                    batchmodels.TaskCountValidationStatus.validated):
                j = 0
                if task_counts.completed == numtasks:
                    logger.info(task_counts)
                    logger.info('all {} tasks completed'.format(numtasks))
                    break
            else:
                # unvalidated, perform manual list tasks
                j += 1
                if j % 10 == 0:
                    j = 0
                    try:
                        tasks = batch_client.task.list(
                            job_id=job_id,
                            task_list_options=batchmodels.TaskListOptions(
                                select='id,state')
                        )
                        states = [task.state for task in tasks]
                    except batchmodels.batch_error.BatchErrorException as ex:
                        logger.exception(ex)
                    else:
                        if (states.count(batchmodels.TaskState.completed) ==
                                numtasks):
                            logger.info('all {} tasks completed'.format(
                                numtasks))
                            break
            i += 1
            if i % 15 == 0:
                i = 0
                logger.debug(task_counts)
        time.sleep(2)


def main():
    """Main function"""
    # get command-line args
    args = parseargs()
    # get job id
    job_id = os.environ['AZ_BATCH_JOB_ID']
    # create batch client
    batch_client = _create_credentials()
    # unpickle task map
    logger.debug('loading pickled task map')
    with open(_TASKMAP_PICKLE_FILE, 'rb') as f:
        task_map = pickle.load(f, fix_imports=True)
    # submit tasks to job
    _add_task_collection(batch_client, job_id, task_map)
    # monitor tasks for completion
    if not args.monitor:
        logger.info('not monitoring tasks for completion')
    else:
        logger.info('monitoring tasks for completion')
        _monitor_tasks(batch_client, job_id, len(task_map))


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='rjm: Azure Batch Shipyard recurrent job manager')
    parser.set_defaults(monitor=False)
    parser.add_argument(
        '--monitor', action='store_true', help='monitor tasks for completion')
    return parser.parse_args()


if __name__ == '__main__':
    _setup_logger()
    main()
