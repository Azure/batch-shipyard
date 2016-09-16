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
and python development libraries to be installed due to `cryptography`.

####Ubuntu
```
apt-get update && apt-get install -y build-essential libssl-dev libffi-dev libpython-dev python-dev
```

####CentOS
```
yum update && yum install -y gcc openssl-dev libffi-devel python-devel
```

####SLES/OpenSUSE
```
zypper ref && zypper -n in libopenssl-dev libffi48-devel python-devel
```

####Note about Python 3.3+
If installing for Python 3.3+, then simply use the python3 equivalents for
the python dependencies. For example, on Ubuntu:

```
apt-get update && apt-get install -y build-essential libssl-dev libffi-dev libpython3-dev python3-dev
```

would install the proper dependencies.

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
