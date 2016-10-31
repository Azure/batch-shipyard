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
from builtins import str
# stdlib imports
import base64
import getpass
import logging
import os
try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib
import tempfile
import subprocess
# local imports
import convoy.util

# create logger
logger = logging.getLogger(__name__)
convoy.util.setup_logger(logger)
# global defines
_SSH_KEY_PREFIX = 'id_rsa_shipyard'


def get_ssh_key_prefix():
    # type: (None) -> str
    """Get SSH key prefix
    :rtype: str
    :return: ssh key prefix
    """
    return _SSH_KEY_PREFIX


def generate_ssh_keypair(export_path):
    # type: (str) -> tuple
    """Generate an ssh keypair for use with user logins
    :param str export_path: keypair export path
    :rtype: tuple
    :return: (private key filename, public key filename)
    """
    privkey = str(pathlib.Path(export_path, _SSH_KEY_PREFIX))
    pubkey = str(pathlib.Path(export_path, _SSH_KEY_PREFIX + '.pub'))
    try:
        if os.path.exists(privkey):
            old = privkey + '.old'
            if os.path.exists(old):
                os.unlink(old)
            os.rename(privkey, old)
    except OSError:
        pass
    try:
        if os.path.exists(pubkey):
            old = pubkey + '.old'
            if os.path.exists(old):
                os.unlink(old)
            os.rename(pubkey, old)
    except OSError:
        pass
    logger.info('generating ssh key pair to path: {}'.format(export_path))
    subprocess.check_call(
        ['ssh-keygen', '-f', privkey, '-t', 'rsa', '-N', ''''''])
    return (privkey, pubkey)


def derive_pem_from_pfx(pfxfile, passphrase=None, pemfile=None):
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
        subprocess.check_call(
            ['openssl', 'pkcs12', '-nodes', '-in', pfxfile, '-out',
             pemfile, '-password', 'pass:' + passphrase]
        )
    except Exception:
        os.unlink(pemfile)
        pemfile = None
    return pemfile


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
    sha1_cert_tp = proc.communicate(input=pfxdump)[0]
    # return just thumbprint (without colons) from the above openssl command
    # in lowercase. Expected openssl output is in the form:
    # SHA1 Fingerprint=<thumbprint>
    return ''.join(convoy.util.decode_string(
        sha1_cert_tp).strip().split('=')[1].split(':')).lower()


def generate_pem_pfx_certificates(config):
    # type: (dict) -> str
    """Generate a pem and a derived pfx file
    :param dict config: configuration dict
    :rtype: str
    :return: sha1 thumbprint of pfx
    """
    # gather input
    try:
        pemfile = config['batch_shipyard']['encryption']['public_key_pem']
    except KeyError:
        pemfile = None
    try:
        pfxfile = config['batch_shipyard']['encryption']['pfx']['filename']
    except KeyError:
        pfxfile = None
    try:
        passphrase = config['batch_shipyard']['encryption']['pfx'][
            'passphrase']
    except KeyError:
        passphrase = None
    if pemfile is None:
        pemfile = convoy.util.get_input(
            'Enter public key PEM filename to create: ')
    if pfxfile is None:
        pfxfile = convoy.util.get_input('Enter PFX filename to create: ')
    if passphrase is None:
        while passphrase is None or len(passphrase) == 0:
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
        try:
            os.unlink(privatekey)
        except OSError:
            pass
        # remove temp cert pem
        os.unlink(f.name)
    # get sha1 thumbprint of pfx
    return get_sha1_thumbprint_pfx(pfxfile, passphrase)


def _rsa_encrypt_string(data, config):
    # type: (str, dict) -> str
    """RSA encrypt a string
    :param str data: clear text data to encrypt
    :param dict config: configuration dict
    :rtype: str
    :return: base64-encoded cipher text
    """
    if data is None or len(data) == 0:
        raise ValueError('invalid data to encrypt')
    try:
        inkey = config['batch_shipyard']['encryption']['public_key_pem']
    except KeyError:
        pass
    proc = subprocess.Popen(
        ['openssl', 'rsautl', '-encrypt', '-pubin', '-inkey', inkey],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    ciphertext = convoy.util.base64_encode_string(
        proc.communicate(input=convoy.util.encode_string(data))[0])
    return ciphertext


def _rsa_decrypt_string_with_pfx(ciphertext, config):
    # type: (str, dict) -> str
    """RSA decrypt a string
    :param str ciphertext: cipher text in base64
    :param dict config: configuration dict
    :rtype: str
    :return: decrypted cipher text
    """
    if ciphertext is None or len(ciphertext) == 0:
        raise ValueError('invalid ciphertext to decrypt')
    pfxfile = config['batch_shipyard']['encryption']['pfx']['filename']
    try:
        pfx_passphrase = config['batch_shipyard']['encryption']['pfx'][
            'passphrase']
    except KeyError:
        pfx_passphrase = None
    pemfile = derive_pem_from_pfx(pfxfile, pfx_passphrase, None)
    if pemfile is None:
        raise RuntimeError('cannot decrypt without valid private key')
    cleartext = None
    try:
        data = base64.b64decode(ciphertext)
        proc = subprocess.Popen(
            ['openssl', 'rsautl', '-decrypt', '-inkey', pemfile],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        cleartext = proc.communicate(input=data)[0]
    finally:
        os.unlink(pemfile)
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
