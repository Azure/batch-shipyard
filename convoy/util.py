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
from __future__ import division, print_function, unicode_literals
import base64
import copy
import hashlib
import logging
import logging.handlers
import os
import subprocess
try:
    from os import scandir as scandir
except ImportError:
    from scandir import scandir as scandir
import platform
import sys
import time
# function remaps
try:
    raw_input
except NameError:
    raw_input = input


# create logger
logger = logging.getLogger(__name__)
# global defines
_PY2 = sys.version_info.major == 2
_ON_WINDOWS = platform.system() == 'Windows'
_SSH_KEY_PREFIX = 'id_rsa_shipyard'


def on_python2():
    # type: (None) -> bool
    """Execution on python2
    :rtype: bool
    :return: if on Python2
    """
    return _PY2


def on_windows():
    # type: (None) -> bool
    """Execution on Windows
    :rtype: bool
    :return: if on Windows
    """
    return _ON_WINDOWS


def setup_logger(logger):
    # type: (logger) -> None
    """Set up logger"""
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)sZ %(levelname)s %(name)s:%(funcName)s:%(lineno)d '
        '%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# set up util logger
setup_logger(logger)


def get_ssh_key_prefix():
    # type: (None) -> str
    """Get SSH key prefix
    :rtype: str
    :return: ssh key prefix
    """
    return _SSH_KEY_PREFIX


def get_input(prompt):
    # type: (str) -> str
    """Get user input from keyboard
    :param str prompt: prompt text
    :rtype: str
    :return: user input
    """
    return raw_input(prompt)


def confirm_action(config, msg=None):
    # type: (dict) -> bool
    """Confirm action with user before proceeding
    :param dict config: configuration dict
    :rtype: bool
    :return: if user confirmed or not
    """
    if config['_auto_confirm']:
        return True
    if msg is None:
        msg = 'action'
    user = get_input('Confirm {} [y/n]: '.format(msg))
    if user.lower() in ['y', 'yes']:
        return True
    return False


def merge_dict(dict1, dict2):
    # type: (dict, dict) -> dict
    """Recursively merge dictionaries: dict2 on to dict1. This differs
    from dict.update() in that values that are dicts are recursively merged.
    Note that only dict value types are merged, not lists, etc.

    :param dict dict1: dictionary to merge to
    :param dict dict2: dictionary to merge with
    :rtype: dict
    :return: merged dictionary
    """
    if not isinstance(dict1, dict) or not isinstance(dict2, dict):
        raise ValueError('dict1 or dict2 is not a dictionary')
    result = copy.deepcopy(dict1)
    for k, v in dict2.items():
        if k in result and isinstance(result[k], dict):
            result[k] = merge_dict(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def scantree(path):
    # type: (str) -> os.DirEntry
    """Recursively scan a directory tree
    :param str path: path to scan
    :rtype: DirEntry
    :return: DirEntry via generator
    """
    for entry in scandir(path):
        if entry.is_dir(follow_symlinks=True):
            # due to python2 compat, cannot use yield from here
            for t in scantree(entry.path):
                yield t
        else:
            yield entry


def wrap_commands_in_shell(commands, wait=True):
    # type: (List[str], bool) -> str
    """Wrap commands in a shell
    :param list commands: list of commands to wrap
    :param bool wait: add wait for background processes
    :rtype: str
    :return: wrapped commands
    """
    return '/bin/bash -c \'set -e; set -o pipefail; {}{}\''.format(
        '; '.join(commands), '; wait' if wait else '')


def compute_md5_for_file(file, as_base64, blocksize=65536):
    # type: (pathlib.Path, bool, int) -> str
    """Compute MD5 hash for file
    :param pathlib.Path file: file to compute md5 for
    :param bool as_base64: return as base64 encoded string
    :param int blocksize: block size in bytes
    :rtype: str
    :return: md5 for file
    """
    hasher = hashlib.md5()
    with file.open('rb') as filedesc:
        while True:
            buf = filedesc.read(blocksize)
            if not buf:
                break
            hasher.update(buf)
        if as_base64:
            if on_python2():
                return base64.b64encode(hasher.digest())
            else:
                return str(base64.b64encode(hasher.digest()), 'ascii')
        else:
            return hasher.hexdigest()


def generate_ssh_keypair():
    # type: (str) -> tuple
    """Generate an ssh keypair for use with user logins
    :param str key_fileprefix: key file prefix
    :rtype: tuple
    :return: (private key filename, public key filename)
    """
    pubkey = _SSH_KEY_PREFIX + '.pub'
    try:
        if os.path.exists(_SSH_KEY_PREFIX):
            old = _SSH_KEY_PREFIX + '.old'
            if os.path.exists(old):
                os.remove(old)
            os.rename(_SSH_KEY_PREFIX, old)
    except OSError:
        pass
    try:
        if os.path.exists(pubkey):
            old = pubkey + '.old'
            if os.path.exists(old):
                os.remove(old)
            os.rename(pubkey, old)
    except OSError:
        pass
    logger.info('generating ssh key pair')
    subprocess.check_call(
        ['ssh-keygen', '-f', _SSH_KEY_PREFIX, '-t', 'rsa', '-N', ''''''])
    return (_SSH_KEY_PREFIX, pubkey)


def subprocess_with_output(cmd, shell=False, suppress_output=False):
    # type: (str, bool, bool) -> int
    """Subprocess command and print output
    :param str cmd: command line to execute
    :param bool shell: use shell in Popen
    :param bool suppress_output: suppress output
    :rtype: int
    :return: return code of process
    """
    _devnull = open(os.devnull, 'w')
    if suppress_output:
        proc = subprocess.Popen(
            cmd, shell=shell, stdout=_devnull, stderr=subprocess.STDOUT)
    else:
        proc = subprocess.Popen(cmd, shell=shell)
    proc.wait()
    _devnull.close()
    return proc.returncode


def subprocess_nowait(cmd, shell=False, suppress_output=False):
    # type: (str, bool, bool) -> subprocess.Process
    """Subprocess command and do not wait for subprocess
    :param str cmd: command line to execute
    :param bool shell: use shell in Popen
    :param bool suppress_output: suppress output
    :rtype: subprocess.Process
    :return: subprocess process handle
    """
    _devnull = open(os.devnull, 'w')
    if suppress_output:
        proc = subprocess.Popen(
            cmd, shell=shell, stdout=_devnull, stderr=subprocess.STDOUT)
    else:
        proc = subprocess.Popen(cmd, shell=shell)
    return proc


def subprocess_attach_stdin(cmd, shell=False):
    # type: (str, bool) -> subprocess.Process
    """Subprocess command and attach stdin
    :param str cmd: command line to execute
    :param bool shell: use shell in Popen
    :rtype: subprocess.Process
    :return: subprocess process handle
    """
    return subprocess.Popen(cmd, shell=shell, stdin=subprocess.PIPE)


def subprocess_wait_all(procs):
    # type: (list) -> list
    """Wait for all processes in given list
    :param list procs: list of processes to wait on
    :rtype: list
    :return: list of return codes
    """
    if procs is None or len(procs) == 0:
        raise ValueError('procs is invalid')
    rcodes = [None] * len(procs)
    while True:
        for i in range(0, len(procs)):
            if rcodes[i] is None and procs[i].poll() == 0:
                rcodes[i] = procs[i].returncode
        if all(x is not None for x in rcodes):
            break
        time.sleep(0.03)
    return rcodes


def subprocess_wait_any(procs):
    # type: (list) -> list
    """Wait for any process in given list
    :param list procs: list of processes to wait on
    :rtype: tuple
    :return: (integral position in procs list, return code)
    """
    if procs is None or len(procs) == 0:
        raise ValueError('procs is invalid')
    while True:
        for i in range(0, len(procs)):
            if procs[i].poll() == 0:
                return i, procs[i].returncode
        time.sleep(0.03)


def subprocess_wait_multi(procs1, procs2):
    # type: (list) -> list
    """Wait for any process in given list
    :param list procs: list of processes to wait on
    :rtype: tuple
    :return: (integral position in procs list, return code)
    """
    if ((procs1 is None or len(procs1) == 0) and
            (procs2 is None or len(procs2) == 0)):
        raise ValueError('both procs1 and procs2 are invalid')
    while True:
        if procs1 is not None and len(procs1) > 0:
            for i in range(0, len(procs1)):
                if procs1[i].poll() == 0:
                    return procs1, i, procs1[i].returncode
        if procs2 is not None and len(procs2) > 0:
            for i in range(0, len(procs2)):
                if procs2[i].poll() == 0:
                    return procs2, i, procs2[i].returncode
        time.sleep(0.03)
