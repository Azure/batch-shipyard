# Batch Shipyard Installation

## Requirements
The Batch Shipyard tool is written in Python. The client script is compatible
with Python 2.7 or 3.3+. You will also need to install the
[Azure Batch](https://pypi.python.org/pypi/azure-batch) and
[Azure Storage](https://pypi.python.org/pypi/azure-storage) python packages.
Installation can be performed using the [requirements.txt](../requirements.txt)
file via the command `pip install --user -r requirements.txt` (or via `pip3`
for python3).

Please note that the Python dependencies require a valid compiler, ssl, ffi,
and python development libraries to be installed due to the
[cryptography](https://pypi.python.org/pypi/cryptography) dependency on Linux.
For Windows, binary wheels will be installed for dependencies, thus no
development environment is needed. The following are example commands to
execute (as root or with `sudo`) to install the required dependencies on Linux:

####Ubuntu/Debian
```
apt-get update && apt-get install -y build-essential libssl-dev libffi-dev libpython-dev python-dev
```

####CentOS/RHEL/Fedora
```
yum update && yum install -y gcc openssl-dev libffi-devel python-devel
```

####SLES/OpenSUSE
```
zypper ref && zypper -n in libopenssl-dev libffi48-devel python-devel
```

####Note about Python 3.3+
If installing for Python 3.3+, then simply use the python3 equivalents for
the python dependencies. For example, on Ubuntu/Debian:

```
apt-get update && apt-get install -y build-essential libssl-dev libffi-dev libpython3-dev python3-dev
```

would install the proper dependencies for python3.

####Data Movement Support
Batch Shipyard contains native support for moving files locally accessible
at the point of script execution. In order to take advantage of this
functionality, the following programs must be installed:

1. An SSH client that provides `scp`. OpenSSH with
[HPN patches](http://www.psc.edu/index.php/hpn-ssh) can be used on the client
side to further accelerate `scp` to Azure Batch compute nodes where
`hpn_server_swap` has been set to `true` in the `pool_specification`.
2. `rsync` if `rsync` functionality is needed.
3. [blobxfer](https://github.com/Azure/blobxfer) if transfering to Azure
storage. This is automatically installed if `pip install` is used with
`requirements.txt` as per above.

Note that data movement is not supported if invoked from Windows.

## Installation
Simply clone the repository:

```
git clone https://github.com/Azure/batch-shipyard.git
```

or [download the latest release](https://github.com/Azure/batch-shipyard/releases).

**Note:** if cloning the repository on Windows, please ensure that git does
not modify the Unix line-endings (LF) for any file in the `scripts` directory.
If these files are modified with Windows line-endings (CRLF) then compute nodes
will fail to start properly.

## Next Steps
Either continue on to
[Batch Shipyard Configuration](10-batch-shipyard-configuration.md) for a full
explanation of all of the Batch Shipyard configuration options within the
config files or continue to the
[Batch Shipyard Quickstart](02-batch-shipyard-quickstart.md) guide.
