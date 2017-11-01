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

# compat imports
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)
from builtins import (  # noqa
    bytes, dict, int, list, object, range, str, ascii, chr, hex, input,
    next, oct, open, pow, round, super, filter, map, zip)
# stdlib imports
import base64
import copy
import datetime
import hashlib
import logging
import logging.handlers
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
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


# global defines
_PY2 = sys.version_info.major == 2
_ON_WINDOWS = platform.system() == 'Windows'
_REGISTERED_LOGGER_HANDLERS = []


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


def setup_logger(logger, logfile=None):
    # type: (logger, str) -> None
    """Set up logger"""
    global _REGISTERED_LOGGER_HANDLERS
    logger.setLevel(logging.DEBUG)
    if is_none_or_empty(logfile):
        handler = logging.StreamHandler()
    else:
        handler = logging.FileHandler(logfile, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s %(levelname)s - %(message)s')
    formatter.default_msec_format = '%s.%03d'
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    _REGISTERED_LOGGER_HANDLERS.append(handler)


def set_verbose_logger_handlers():
    # type: (None) -> None
    """Set logger handler formatters to more detail"""
    global _REGISTERED_LOGGER_HANDLERS
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s:%(funcName)s:%(lineno)d '
        '%(message)s')
    formatter.default_msec_format = '%s.%03d'
    for handler in _REGISTERED_LOGGER_HANDLERS:
        handler.setFormatter(formatter)


def decode_string(string, encoding=None):
    # type: (str, str) -> str
    """Decode a string with specified encoding
    :type string: str or bytes
    :param string: string to decode
    :param str encoding: encoding of string to decode
    :rtype: str
    :return: decoded string
    """
    if isinstance(string, bytes):
        if encoding is None:
            encoding = 'utf8'
        return string.decode(encoding)
    if isinstance(string, str):
        return string
    raise ValueError('invalid string type: {}'.format(type(string)))


def encode_string(string, encoding=None):
    # type: (str, str) -> str
    """Encode a string with specified encoding
    :type string: str or bytes
    :param string: string to decode
    :param str encoding: encoding of string to decode
    :rtype: str
    :return: decoded string
    """
    if isinstance(string, bytes):
        return string
    if isinstance(string, str):
        if encoding is None:
            encoding = 'utf8'
        return string.encode(encoding)
    raise ValueError('invalid string type: {}'.format(type(string)))


def is_none_or_empty(obj):
    # type: (any) -> bool
    """Determine if object is None or empty
    :type any obj: object
    :rtype: bool
    :return: if object is None or empty
    """
    return obj is None or len(obj) == 0


def is_not_empty(obj):
    # type: (any) -> bool
    """Determine if object is not None and is length is > 0
    :type any obj: object
    :rtype: bool
    :return: if object is not None and length is > 0
    """
    return obj is not None and len(obj) > 0


def get_input(prompt):
    # type: (str) -> str
    """Get user input from keyboard
    :param str prompt: prompt text
    :rtype: str
    :return: user input
    """
    return raw_input(prompt)


def confirm_action(config, msg=None, allow_auto=True):
    # type: (dict, str, bool) -> bool
    """Confirm action with user before proceeding
    :param dict config: configuration dict
    :param msg str: confirmation message
    :param bool allow_auto: allow auto confirmation
    :rtype: bool
    :return: if user confirmed or not
    """
    if allow_auto and config['_auto_confirm']:
        return True
    if msg is None:
        msg = 'action'
    while True:
        user = get_input('Confirm {} [y/n]: '.format(msg)).lower()
        if user in ('y', 'yes', 'n', 'no'):
            break
    if user in ('y', 'yes'):
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


def singularity_image_name_on_disk(name):
    # type: (str) -> str
    """Convert a singularity URI to an on disk simg name
    :param str name: Singularity image name
    :rtype: str
    :return: singularity image name on disk
    """
    docker = False
    if name.startswith('shub://'):
        name = name[7:]
    elif name.startswith('docker://'):
        docker = True
        name = name[9:]
        # singularity only uses the final portion
        name = name.split('/')[-1]
    name = name.replace('/', '-')
    idx = name.find(':')
    if idx != -1:
        name = name.replace(':', '-')
    else:
        if not docker:
            name = '{}-master'.format(name)
    if docker:
        name = '{}.img'.format(name)
    else:
        name = '{}.simg'.format(name)
    return name


def wrap_commands_in_shell(commands, windows=False, wait=True):
    # type: (List[str], bool, bool) -> str
    """Wrap commands in a shell
    :param list commands: list of commands to wrap
    :param bool windows: linux or windows commands to wrap
    :param bool wait: add wait for background processes
    :rtype: str
    :return: wrapped commands
    """
    if windows:
        return 'cmd.exe /c "{}"'.format(' && '.join(commands))
    else:
        return '/bin/bash -c \'set -e; set -o pipefail; {}{}\''.format(
            '; '.join(commands), '; wait' if wait else '')


def wrap_local_commands_in_shell(commands, wait=True):
    # type: (List[str], bool) -> str
    """Wrap commands in a shell that will be executed locally on the client
    :param list commands: list of commands to wrap
    :param bool wait: add wait for background processes
    :rtype: str
    :return: wrapped commands
    """
    return wrap_commands_in_shell(commands, windows=_ON_WINDOWS, wait=wait)


def base64_encode_string(string):
    # type: (str or bytes) -> str
    """Base64 encode a string
    :param str or bytes string: string to encode
    :rtype: str
    :return: base64-encoded string
    """
    if on_python2():
        return base64.b64encode(string)
    else:
        return str(base64.b64encode(string), 'ascii')


def base64_decode_string(string):
    # type: (str) -> str
    """Base64 decode a string
    :param str string: string to decode
    :rtype: str
    :return: decoded string
    """
    return base64.b64decode(string)


def convert_timedelta_to_string(td):
    # type: (datetime.timedelta) -> str
    """Convert a time delta to string
    :param datetime.timedelta td: time delta to convert
    :rtype: str
    :return: string representation
    """
    days = td.days
    hours = td.seconds // 3600
    minutes = (td.seconds - (hours * 3600)) // 60
    seconds = (td.seconds - (hours * 3600) - (minutes * 60))
    return '{0}.{1:02d}:{2:02d}:{3:02d}'.format(days, hours, minutes, seconds)


def convert_string_to_timedelta(string):
    # type: (str) -> datetime.timedelta
    """Convert string to time delta. strptime() does not support time deltas
    greater than 24 hours.
    :param str string: string representation of time delta
    :rtype: datetime.timedelta
    :return: time delta
    """
    if is_none_or_empty(string):
        raise ValueError('{} is not a valid timedelta string'.format(string))
    # get days
    tmp = string.split('.')
    if len(tmp) == 2:
        days = int(tmp[0])
        tmp = tmp[1]
    elif len(tmp) == 1:
        days = 0
        tmp = tmp[0]
    else:
        raise ValueError('{} is not a valid timedelta string'.format(string))
    # get total seconds
    tmp = tmp.split(':')
    if len(tmp) != 3:
        raise ValueError('{} is not a valid timedelta string'.format(string))
    totsec = int(tmp[2]) + int(tmp[1]) * 60 + int(tmp[0]) * 3600
    return datetime.timedelta(days, totsec)


def compute_sha256_for_file(file, as_base64, blocksize=65536):
    # type: (pathlib.Path, bool, int) -> str
    """Compute SHA256 hash for file
    :param pathlib.Path file: file to compute md5 for
    :param bool as_base64: return as base64 encoded string
    :param int blocksize: block size in bytes
    :rtype: str
    :return: SHA256 for file
    """
    hasher = hashlib.sha256()
    if isinstance(file, pathlib.Path):
        file = str(file)
    with open(file, 'rb') as filedesc:
        while True:
            buf = filedesc.read(blocksize)
            if not buf:
                break
            hasher.update(buf)
        if as_base64:
            return base64_encode_string(hasher.digest())
        else:
            return hasher.hexdigest()


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
    if isinstance(file, pathlib.Path):
        file = str(file)
    with open(file, 'rb') as filedesc:
        while True:
            buf = filedesc.read(blocksize)
            if not buf:
                break
            hasher.update(buf)
        if as_base64:
            return base64_encode_string(hasher.digest())
        else:
            return hasher.hexdigest()


def subprocess_with_output(cmd, shell=False, cwd=None, suppress_output=False):
    # type: (str, bool, str, bool) -> int
    """Subprocess command and print output
    :param str cmd: command line to execute
    :param bool shell: use shell in Popen
    :param str cwd: current working directory
    :param bool suppress_output: suppress output
    :rtype: int
    :return: return code of process
    """
    _devnull = None
    try:
        if suppress_output:
            _devnull = open(os.devnull, 'w')
            proc = subprocess.Popen(
                cmd, shell=shell, cwd=cwd, stdout=_devnull,
                stderr=subprocess.STDOUT)
        else:
            proc = subprocess.Popen(cmd, shell=shell, cwd=cwd)
        proc.wait()
    finally:
        if _devnull is not None:
            _devnull.close()
    return proc.returncode


def subprocess_nowait(cmd, shell=False, cwd=None, env=None):
    # type: (str, bool, str, dict) -> subprocess.Process
    """Subprocess command and do not wait for subprocess
    :param str cmd: command line to execute
    :param bool shell: use shell in Popen
    :param str cwd: current working directory
    :param dict env: env vars to use
    :rtype: subprocess.Process
    :return: subprocess process handle
    """
    return subprocess.Popen(cmd, shell=shell, cwd=cwd, env=env)


def subprocess_nowait_pipe_stdout(
        cmd, shell=False, cwd=None, env=None, pipe_stderr=False):
    # type: (str, bool, str, dict) -> subprocess.Process
    """Subprocess command and do not wait for subprocess
    :param str cmd: command line to execute
    :param bool shell: use shell in Popen
    :param str cwd: current working directory
    :param dict env: env vars to use
    :param bool pipe_stderr: redirect stderr to pipe as well
    :rtype: subprocess.Process
    :return: subprocess process handle
    """
    if pipe_stderr:
        return subprocess.Popen(
            cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, env=env)
    else:
        return subprocess.Popen(
            cmd, shell=shell, stdout=subprocess.PIPE, cwd=cwd, env=env)


def subprocess_attach_stdin(cmd, shell=False):
    # type: (str, bool) -> subprocess.Process
    """Subprocess command and attach stdin
    :param str cmd: command line to execute
    :param bool shell: use shell in Popen
    :rtype: subprocess.Process
    :return: subprocess process handle
    """
    return subprocess.Popen(cmd, shell=shell, stdin=subprocess.PIPE)


def subprocess_wait_all(procs, poll=True):
    # type: (list, bool) -> list
    """Wait for all processes in given list
    :param list procs: list of processes to wait on
    :param bool poll: use poll(), otherwise communicate() if using PIPEs
    :rtype: list
    :return: list of return codes
    """
    if procs is None or len(procs) == 0:
        raise ValueError('procs is invalid')
    rcodes = [None] * len(procs)
    while True:
        for i in range(0, len(procs)):
            if rcodes[i] is None:
                if poll and procs[i].poll() == 0:
                    rcodes[i] = procs[i].returncode
                else:
                    procs[i].communicate()
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
