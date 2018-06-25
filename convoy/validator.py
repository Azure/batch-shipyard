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

# compat imports
from __future__ import absolute_import, division, print_function
from builtins import (  # noqa
    bytes, dict, int, list, object, range, str, ascii, chr, hex, input,
    next, oct, open, pow, round, super, filter, map, zip)
# stdlib imports
import enum
import logging
import sys
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import warnings
# non-stdlib imports
import pykwalify.core
import pykwalify.errors
import ruamel.yaml
# local imports
import convoy.util


# create logger
logger = logging.getLogger(__name__)


# enums
class ConfigType(enum.Enum):
    Credentials = 1,
    Global = 2,
    Pool = 3,
    Jobs = 4,
    RemoteFS = 5,
    Monitor = 6,
    Federation = 7,


# global defines
_ROOT_PATH = pathlib.Path(__file__).resolve().parent.parent
_SCHEMAS = {
    ConfigType.Credentials: {
        'name': 'Credentials',
        'schema': pathlib.Path(_ROOT_PATH, 'schemas/credentials.yaml'),
    },
    ConfigType.Global: {
        'name': 'Global',
        'schema': pathlib.Path(_ROOT_PATH, 'schemas/config.yaml'),
    },
    ConfigType.Pool: {
        'name': 'Pool',
        'schema': pathlib.Path(_ROOT_PATH, 'schemas/pool.yaml'),
    },
    ConfigType.Jobs: {
        'name': 'Jobs',
        'schema': pathlib.Path(_ROOT_PATH, 'schemas/jobs.yaml'),
    },
    ConfigType.RemoteFS: {
        'name': 'RemoteFS',
        'schema': pathlib.Path(_ROOT_PATH, 'schemas/fs.yaml'),
    },
    ConfigType.Monitor: {
        'name': 'Monitor',
        'schema': pathlib.Path(_ROOT_PATH, 'schemas/monitor.yaml'),
    },
    ConfigType.Federation: {
        'name': 'Federation',
        'schema': pathlib.Path(_ROOT_PATH, 'schemas/federation.yaml'),
    },
}

# configure loggers
_PYKWALIFY_LOGGER = logging.getLogger('pykwalify')
convoy.util.setup_logger(_PYKWALIFY_LOGGER)
_PYKWALIFY_LOGGER.setLevel(logging.CRITICAL)
convoy.util.setup_logger(logger)

# ignore ruamel.yaml warning
warnings.simplefilter('ignore', ruamel.yaml.error.UnsafeLoaderWarning)


def validate_config(config_type, config_file):
    if config_file is None or not config_file.exists():
        return
    schema = _SCHEMAS[config_type]
    validator = pykwalify.core.Core(
        source_file=str(config_file),
        schema_files=[str(schema['schema'])]
    )
    validator.strict_rule_validation = True
    try:
        validator.validate(raise_exception=True)
    except pykwalify.errors.SchemaError as e:
        logger.error('{} Configuration {}'.format(schema['name'], e.msg))
        sys.exit(1)
