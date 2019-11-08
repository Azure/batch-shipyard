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
import collections
import datetime
import getpass
import logging
import os
try:
    import pathlib2 as pathlib
except ImportError:
    import pathlib
import tempfile
import stat
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
_MONITORING_SSH_KEY_PREFIX = '{}_monitoring'.format(_SSH_KEY_PREFIX)
_FEDERATION_SSH_KEY_PREFIX = '{}_federation'.format(_SSH_KEY_PREFIX)
_SLURM_CONTROLLER_SSH_KEY_PREFIX = '{}_slurm_controller'.format(
    _SSH_KEY_PREFIX)
_SLURM_LOGIN_SSH_KEY_PREFIX = '{}_slurm_login'.format(_SSH_KEY_PREFIX)
# named tuples
PfxSettings = collections.namedtuple(
    'PfxSettings', [
        'filename', 'passphrase', 'sha1',
    ]
)


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


def get_monitoring_ssh_key_prefix():
    # type: (None) -> str
    """Get monitoring SSH key prefix
    :rtype: str
    :return: ssh key prefix for monitoring
    """
    return _MONITORING_SSH_KEY_PREFIX


def get_federation_ssh_key_prefix():
    # type: (None) -> str
    """Get federation SSH key prefix
    :rtype: str
    :return: ssh key prefix for federation proxy
    """
    return _FEDERATION_SSH_KEY_PREFIX


def get_slurm_ssh_key_prefix(kind):
    # type: (str) -> str
    """Get slurm SSH key prefix
    :param str kind: kind
    :rtype: str
    :return: ssh key prefix for slurm
    """
    if kind == 'controller':
        return _SLURM_CONTROLLER_SSH_KEY_PREFIX
    else:
        return _SLURM_LOGIN_SSH_KEY_PREFIX


def generate_rdp_password():
    # type: (None) -> str
    """Generate an RDP password
    :rtype: str
    :return: rdp password
    """
    return base64.b64encode(os.urandom(8))


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


def check_ssh_private_key_filemode(ssh_private_key):
    # type: (pathlib.Path) -> bool
    """Check SSH private key filemode
    :param pathlib.Path ssh_private_key: SSH private key
    :rtype: bool
    :return: private key filemode is ok
    """
    def _mode_check(fstat, flag):
        return bool(fstat & flag)
    if util.on_windows():
        return True
    fstat = ssh_private_key.stat().st_mode
    modes = frozenset((stat.S_IRWXG, stat.S_IRWXO))
    return not any([_mode_check(fstat, x) for x in modes])


def connect_or_exec_ssh_command(
        remote_ip, remote_port, ssh_private_key, username, sync=True,
        shell=False, tty=False, ssh_args=None, command=None):
    # type: (str, int, pathlib.Path, str, bool, bool, tuple, tuple) -> bool
    """Connect to node via SSH or execute SSH command
    :param str remote_ip: remote ip address
    :param int remote_port: remote port
    :param pathlib.Path ssh_private_key: SSH private key
    :param str username: username
    :param bool sync: synchronous execution
    :param bool shell: execute with shell
    :param bool tty: allocate pseudo-tty
    :param tuple ssh_args: ssh args
    :param tuple command: command
    :rtype: int or subprocess.Process
    :return: return code or subprocess handle
    """
    if not ssh_private_key.exists():
        raise RuntimeError('SSH private key file not found at: {}'.format(
            ssh_private_key))
    # ensure file mode is set properly for the private key
    if not check_ssh_private_key_filemode(ssh_private_key):
        logger.warning(
            'SSH private key filemode is too permissive: {}'.format(
                ssh_private_key))
    # execute SSH command
    ssh_cmd = [
        'ssh', '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile={}'.format(os.devnull),
        '-i', str(ssh_private_key), '-p', str(remote_port),
    ]
    if tty:
        ssh_cmd.append('-t')
    if util.is_not_empty(ssh_args):
        ssh_cmd.extend(ssh_args)
    ssh_cmd.append('{}@{}'.format(username, remote_ip))
    if util.is_not_empty(command):
        ssh_cmd.extend(command)
    logger.info('{} node {}:{} with key {}'.format(
        'connecting to' if util.is_none_or_empty(command)
        else 'executing command on', remote_ip, remote_port, ssh_private_key))
    if sync:
        return util.subprocess_with_output(ssh_cmd, shell=shell)
    else:
        return util.subprocess_nowait_pipe_stdout(
            ssh_cmd, shell=shell, pipe_stderr=True)


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


def convert_pem_to_pfx(pemfile, no_certs, passphrase):
    # type: (str, bool, str) -> str
    """Convert pem to password-protected pfx
    :param str pemfile: path of pem file to convert from
    :param bool no_certs: don't export certs
    :param str passphrase: passphrase for pfx
    :rtype: tuple
    :return: path of pfx file, passphrase
    """
    if pemfile is None:
        raise ValueError('pem file is invalid')
    if passphrase is None:
        passphrase = getpass.getpass('Enter password for PFX: ')
    # convert pem to pfx
    f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
    f.close()
    pfxfile = f.name
    try:
        if no_certs:
            subprocess.check_call(
                ['openssl', 'pkcs12', '-export', '-nocerts', '-inkey', pemfile,
                 '-out', pfxfile, '-password', 'pass:' + passphrase]
            )
        else:
            subprocess.check_call(
                ['openssl', 'pkcs12', '-export', '-in', pemfile, '-out',
                 pfxfile, '-password', 'pass:' + passphrase]
            )
    except Exception:
        fp = pathlib.Path(pfxfile)
        if fp.exists():
            fp.unlink()
        pfxfile = None
    return pfxfile, passphrase


def convert_pem_to_cer(pemfile, no_certs):
    # type: (str) -> str
    """Convert pem to cer containing public key only
    :param str pemfile: path of pem file to convert from
    :param bool no_certs: don't export certs
    :rtype: str
    :return: path of cer file
    """
    if pemfile is None:
        raise ValueError('pem file is invalid')
    # convert pem to cer
    f = tempfile.NamedTemporaryFile(mode='wb', delete=False)
    f.close()
    cerfile = f.name
    try:
        if no_certs:
            subprocess.check_call(
                ['openssl', 'req', '-new', '-x509', '-key', pemfile,
                 '-outform', 'DER', '-out', cerfile,
                 '-subj', _autofill_subject()]
            )
        else:
            pf = None
            try:
                pf = tempfile.NamedTemporaryFile(mode='wb', delete=False)
                pf.close()
                subprocess.check_call(
                    ['openssl', 'req', '-new', '-x509', '-in', pemfile,
                     '-outform', 'DER', '-nodes', '-keyout', pf.name,
                     '-out', cerfile, '-subj', _autofill_subject()]
                )
            finally:
                if pf is not None:
                    fp = pathlib.Path(pf.name)
                    if fp.exists():
                        fp.unlink()
    except Exception:
        fp = pathlib.Path(cerfile)
        if fp.exists():
            fp.unlink()
        cerfile = None
    return cerfile


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
    :param str pfxfile: name of the pfx file
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
    :param str pfxfile: name of the pfx file
    :rtype: str
    :return: sha1 thumbprint of pem
    """
    proc = subprocess.Popen(
        ['openssl', 'x509', '-noout', '-fingerprint', '-in', pemfile],
        stdout=subprocess.PIPE
    )
    return _parse_sha1_thumbprint_openssl(proc.communicate()[0])


def get_sha1_thumbprint_cer(cerfile):
    # type: (str) -> str
    """Get SHA1 thumbprint of CER
    :param str cerfile: name of the cer file
    :rtype: str
    :return: sha1 thumbprint of cer
    """
    proc = subprocess.Popen(
        ['openssl', 'x509', '-noout', '-fingerprint', '-inform', 'DER',
         '-in', cerfile],
        stdout=subprocess.PIPE
    )
    return _parse_sha1_thumbprint_openssl(proc.communicate()[0])


def _autofill_subject():
    # type: (None) -> str
    """Generate an autofill subject for openssl
    :rtype: str
    :return: generated autofill subject
    """
    return '/O=BatchShipyard/CN=GenCert{}'.format(
        datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S'))


def generate_pem_pfx_certificates(config, file_prefix=None, pfx_password=None):
    # type: (dict, str, str) -> str
    """Generate a pem and a derived pfx file
    :param dict config: configuration dict
    :param str file_prefix: prefix of file to create
    :param str pfx_password: pfx password
    :rtype: str
    :return: sha1 thumbprint of pfx
    """
    # gather input
    if util.is_not_empty(file_prefix):
        pemfile = file_prefix + '.pem'
    else:
        pemfile = (
            settings.batch_shipyard_encryption_public_key_pem(config) or
            util.get_input('Enter public key PEM filename to create: ')
        )
    if util.is_not_empty(file_prefix):
        pfxfile = file_prefix + '.pfx'
    else:
        pfxfile = (
            settings.batch_shipyard_encryption_pfx_filename(config) or
            util.get_input('Enter PFX filename to create: ')
        )
    passphrase = (
        pfx_password or
        settings.batch_shipyard_encryption_pfx_passphrase(config)
    )
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
             'rsa:4096', '-keyout', privatekey, '-out', f.name,
             '-days', '3650', '-subj', _autofill_subject()]
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
