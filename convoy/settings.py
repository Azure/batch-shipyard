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
# non-stdlib imports
# local imports
from . import util


def batch_shipyard_encryption_enabled(config):
    # type: (dict) -> bool
    """Get credential encryption enabled setting
    :param dict config: configuration object
    :rtype: bool
    :return: if credential encryption is enabled
    """
    try:
        encrypt = config['batch_shipyard']['encryption']['enabled']
    except KeyError:
        encrypt = False
    return encrypt


def batch_shipyard_encryption_pfx_filename(config):
    # type: (dict) -> str
    """Get filename of pfx cert
    :param dict config: configuration object
    :rtype: str
    :return: pfx filename
    """
    try:
        pfxfile = config['batch_shipyard']['encryption']['pfx']['filename']
    except KeyError:
        pfxfile = None
    return pfxfile


def batch_shipyard_encryption_pfx_passphrase(config):
    # type: (dict) -> str
    """Get passphrase of pfx cert
    :param dict config: configuration object
    :rtype: str
    :return: pfx passphrase
    """
    try:
        passphrase = config['batch_shipyard']['encryption'][
            'pfx']['passphrase']
    except KeyError:
        passphrase = None
    return passphrase


def batch_shipyard_encryption_pfx_sha1_thumbprint(config):
    # type: (dict) -> str
    """Get sha1 tp of pfx cert
    :param dict config: configuration object
    :rtype: str
    :return: pfx sha1 thumbprint
    """
    try:
        tp = config['batch_shipyard']['encryption']['pfx']['sha1_thumbprint']
    except KeyError:
        tp = None
    return tp


def set_batch_shipyard_encryption_pfx_sha1_thumbprint(config, tp):
    # type: (dict, str) -> None
    """Set sha1 tp of pfx cert
    :param dict config: configuration object
    """
    config['batch_shipyard']['encryption']['pfx']['sha1_thumbprint'] = tp


def docker_registry_hub_login(config):
    # type: (dict) -> tuple
    """Get docker registry hub login settings
    :param dict config: configuration object
    :rtype: tuple
    :return: (user, pw)
    """
    try:
        user = config['credentials']['docker_registry']['hub']['username']
        pw = config['credentials']['docker_registry']['hub']['password']
        if util.is_none_or_empty(user) or util.is_none_or_empty(pw):
            raise KeyError()
    except KeyError:
        user = None
        pw = None
    return user, pw
