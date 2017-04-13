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
import collections
import getpass
import logging
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import tempfile
import subprocess
# local imports
from . import settings
from . import util

# create logger
logger = logging.getLogger(__name__)
util.setup_logger(logger)
# global defines
_SSH_KEY_PREFIX = 'id_rsa_shipyard'
_REMOTEFS_SSH_KEY_PREFIX = '{}_remotefs'.format(_SSH_KEY_PREFIX)
# named tuples
PfxSettings = collections.namedtuple(
    'PfxSettings', ['filename', 'passphrase', 'sha1'])


def get_ssh_key_prefix():
    # type: (None) -> str
    """Get SSH key prefix
    :rtype: str
    :return: ssh key prefix
    """
    return _SSH_KEY_PREFIX


def get_remotefs_ssh_key_prefix():
    # type: (None) -> str
    """Get remote fs SSH key prefix
    :rtype: str
    :return: ssh key prefix for remote fs
    """
    return _REMOTEFS_SSH_KEY_PREFIX


def generate_ssh_keypair(export_path, prefix=None):
    # type: (str, str) -> tuple
    """Generate an ssh keypair for use with user logins
    :param str export_path: keypair export path
    :param str prefix: key prefix
    :rtype: tuple
    :return: (private key filename, public key filename)
    """
    if util.is_none_or_empty(prefix):
        prefix = _SSH_KEY_PREFIX
    privkey = pathlib.Path(export_path, prefix)
    pubkey = pathlib.Path(export_path, prefix + '.pub')
    if privkey.exists():
        old = pathlib.Path(export_path, prefix + '.old')
        if old.exists():
            old.unlink()
        privkey.rename(old)
    if pubkey.exists():
        old = pathlib.Path(export_path, prefix + '.pub.old')
        if old.exists():
            old.unlink()
        pubkey.rename(old)
    logger.info('generating ssh key pair to path: {}'.format(export_path))
    subprocess.check_call(
        ['ssh-keygen', '-f', str(privkey), '-t', 'rsa', '-N', ''''''])
    return (privkey, pubkey)


def derive_private_key_pem_from_pfx(pfxfile, passphrase=None, pemfile=None):
    # type: (str, str, str) -> str
    """Derive a private key pem file from a pfx
    :param str pfxfile: pfx file
    :param str passphrase: passphrase for pfx
    :param str pemfile: path of pem file to write to
    :rtype: str
    :return: path of pem file
    """
    if pfxfile is None:
        raise ValueError('pfx file is invalid')
    if passphrase is None:
        passphrase = getpass.getpass('Enter password for PFX: ')
    # convert pfx to pem
    if pemfile is None:
        f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        f.close()
        pemfile = f.name
    try:
        # create pem from pfx
        subprocess.check_call(
            ['openssl', 'pkcs12', '-nodes', '-in', pfxfile, '-out',
             pemfile, '-password', 'pass:' + passphrase]
        )
    except Exception:
        fp = pathlib.Path(pemfile)
        if fp.exists():
            fp.unlink()
        pemfile = None
    return pemfile


def derive_public_key_pem_from_pfx(pfxfile, passphrase=None, pemfile=None):
    # type: (str, str, str) -> str
    """Derive a public key pem file from a pfx
    :param str pfxfile: pfx file
    :param str passphrase: passphrase for pfx
    :param str pemfile: path of pem file to write to
    :rtype: str
    :return: path of pem file
    """
    if pfxfile is None:
        raise ValueError('pfx file is invalid')
    if passphrase is None:
        passphrase = getpass.getpass('Enter password for PFX: ')
    # convert pfx to pem
    if pemfile is None:
        f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        f.close()
        pemfile = f.name
    try:
        # create pem from pfx
        subprocess.check_call(
            ['openssl', 'pkcs12', '-nodes', '-in', pfxfile, '-out',
             pemfile, '-password', 'pass:' + passphrase]
        )
        # extract public key from private key
        subprocess.check_call(
            ['openssl', 'rsa', '-in', pemfile, '-pubout', '-outform',
             'PEM', '-out', pemfile]
        )
    except Exception:
        fp = pathlib.Path(pemfile)
        if fp.exists():
            fp.unlink()
        pemfile = None
    return pemfile


def _parse_sha1_thumbprint_openssl(output):
    # type: (str) -> str
    """Get SHA1 thumbprint from buffer
    :param str buffer: buffer to parse
    :rtype: str
    :return: sha1 thumbprint of buffer
    """
    # return just thumbprint (without colons) from the above openssl command
    # in lowercase. Expected openssl output is in the form:
    # SHA1 Fingerprint=<thumbprint>
    return ''.join(util.decode_string(
        output).strip().split('=')[1].split(':')).lower()


def get_sha1_thumbprint_pfx(pfxfile, passphrase):
    # type: (str, str) -> str
    """Get SHA1 thumbprint of PFX
    :param str pfxfile: name of the pfx file to export
    :param str passphrase: passphrase for pfx
    :rtype: str
    :return: sha1 thumbprint of pfx
    """
    if pfxfile is None:
        raise ValueError('pfxfile is invalid')
    if passphrase is None:
        passphrase = getpass.getpass('Enter password for PFX: ')
    # compute sha1 thumbprint of pfx
    pfxdump = subprocess.check_output(
        ['openssl', 'pkcs12', '-in', pfxfile, '-nodes', '-passin',
         'pass:' + passphrase]
    )
    proc = subprocess.Popen(
        ['openssl', 'x509', '-noout', '-fingerprint'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    return _parse_sha1_thumbprint_openssl(proc.communicate(input=pfxdump)[0])


def get_sha1_thumbprint_pem(pemfile):
    # type: (str) -> str
    """Get SHA1 thumbprint of PEM
    :param str pfxfile: name of the pfx file to export
    :rtype: str
    :return: sha1 thumbprint of pem
    """
    proc = subprocess.Popen(
        ['openssl', 'x509', '-noout', '-fingerprint', '-in', pemfile],
        stdout=subprocess.PIPE
    )
    return _parse_sha1_thumbprint_openssl(proc.communicate()[0])


def generate_pem_pfx_certificates(config):
    # type: (dict) -> str
    """Generate a pem and a derived pfx file
    :param dict config: configuration dict
    :rtype: str
    :return: sha1 thumbprint of pfx
    """
    # gather input
    pemfile = settings.batch_shipyard_encryption_public_key_pem(config)
    pfxfile = settings.batch_shipyard_encryption_pfx_filename(config)
    passphrase = settings.batch_shipyard_encryption_pfx_passphrase(config)
    if pemfile is None:
        pemfile = util.get_input('Enter public key PEM filename to create: ')
    if pfxfile is None:
        pfxfile = util.get_input('Enter PFX filename to create: ')
    if passphrase is None:
        while util.is_none_or_empty(passphrase):
            passphrase = getpass.getpass('Enter password for PFX: ')
            if len(passphrase) == 0:
                print('passphrase cannot be empty')
    privatekey = pemfile + '.key'
    # generate pem file with private key and no password
    f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
    f.close()
    try:
        subprocess.check_call(
            ['openssl', 'req', '-new', '-nodes', '-x509', '-newkey',
             'rsa:2048', '-keyout', privatekey, '-out', f.name, '-days', '730',
             '-subj', '/C=US/ST=None/L=None/O=None/CN=BatchShipyard']
        )
        # extract public key from private key
        subprocess.check_call(
            ['openssl', 'rsa', '-in', privatekey, '-pubout', '-outform',
             'PEM', '-out', pemfile]
        )
        logger.debug('created public key PEM file: {}'.format(pemfile))
        # convert pem to pfx for Azure Batch service
        subprocess.check_call(
            ['openssl', 'pkcs12', '-export', '-out', pfxfile, '-inkey',
             privatekey, '-in', f.name, '-certfile', f.name,
             '-passin', 'pass:', '-passout', 'pass:' + passphrase]
        )
        logger.debug('created PFX file: {}'.format(pfxfile))
    finally:
        # remove rsa private key file
        fp = pathlib.Path(privatekey)
        if fp.exists():
            fp.unlink()
        # remove temp cert pem
        fp = pathlib.Path(f.name)
        if fp.exists():
            fp.unlink()
    # get sha1 thumbprint of pfx
    return get_sha1_thumbprint_pfx(pfxfile, passphrase)


def get_encryption_pfx_settings(config):
    # type: (dict) -> tuple
    """Get PFX encryption settings from configuration
    :param dict config: configuration settings
    :rtype: tuple
    :return: pfxfile, passphrase, sha1 tp
    """
    pfxfile = settings.batch_shipyard_encryption_pfx_filename(config)
    pfx_passphrase = settings.batch_shipyard_encryption_pfx_passphrase(config)
    sha1_cert_tp = settings.batch_shipyard_encryption_pfx_sha1_thumbprint(
        config)
    # manually get thumbprint of pfx if not exists in config
    if util.is_none_or_empty(sha1_cert_tp):
        if pfx_passphrase is None:
            pfx_passphrase = getpass.getpass('Enter password for PFX: ')
        sha1_cert_tp = get_sha1_thumbprint_pfx(pfxfile, pfx_passphrase)
        settings.set_batch_shipyard_encryption_pfx_sha1_thumbprint(
            config, sha1_cert_tp)
    return PfxSettings(
        filename=pfxfile, passphrase=pfx_passphrase, sha1=sha1_cert_tp)


def _rsa_encrypt_string(data, config):
    # type: (str, dict) -> str
    """RSA encrypt a string
    :param str data: clear text data to encrypt
    :param dict config: configuration dict
    :rtype: str
    :return: base64-encoded cipher text
    """
    if util.is_none_or_empty(data):
        raise ValueError('invalid data to encrypt')
    inkey = settings.batch_shipyard_encryption_public_key_pem(config)
    derived = False
    if inkey is None:
        # derive pem from pfx
        derived = True
        pfxfile = settings.batch_shipyard_encryption_pfx_filename(config)
        pfx_passphrase = settings.batch_shipyard_encryption_pfx_passphrase(
            config)
        inkey = derive_public_key_pem_from_pfx(pfxfile, pfx_passphrase, None)
    try:
        if inkey is None:
            raise RuntimeError('public encryption key is invalid')
        proc = subprocess.Popen(
            ['openssl', 'rsautl', '-encrypt', '-pubin', '-inkey', inkey],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        ciphertext = util.base64_encode_string(
            proc.communicate(input=util.encode_string(data))[0])
        if proc.returncode != 0:
            raise RuntimeError(
                'openssl encryption failed with returncode: {}'.format(
                    proc.returncode))
        return ciphertext
    finally:
        if derived:
            fp = pathlib.Path(inkey)
            if fp.exists():
                fp.unlink()


def _rsa_decrypt_string_with_pfx(ciphertext, config):
    # type: (str, dict) -> str
    """RSA decrypt a string
    :param str ciphertext: cipher text in base64
    :param dict config: configuration dict
    :rtype: str
    :return: decrypted cipher text
    """
    if util.is_none_or_empty(ciphertext):
        raise ValueError('invalid ciphertext to decrypt')
    pfxfile = settings.batch_shipyard_encryption_pfx_filename(config)
    pfx_passphrase = settings.batch_shipyard_encryption_pfx_passphrase(config)
    pemfile = derive_private_key_pem_from_pfx(pfxfile, pfx_passphrase, None)
    if pemfile is None:
        raise RuntimeError('cannot decrypt without valid private key')
    cleartext = None
    try:
        data = util.base64_decode_string(ciphertext)
        proc = subprocess.Popen(
            ['openssl', 'rsautl', '-decrypt', '-inkey', pemfile],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        cleartext = proc.communicate(input=data)[0]
    finally:
        fp = pathlib.Path(pemfile)
        if fp.exists():
            fp.unlink()
    return cleartext


def encrypt_string(enabled, string, config):
    # type: (bool, str, dict) -> str
    """Encrypt a string
    :param bool enabled: if encryption is enabled
    :param str string: string to encrypt
    :param dict config: configuration dict
    :rtype: str
    :return: encrypted string if enabled
    """
    if enabled:
        return _rsa_encrypt_string(string, config)
    else:
        return string
