# Batch Shipyard Installation
Installation is an easy two-step process: fetch the code and run the
`install.sh` script.

## Installation
Simply clone the repository:
```shell
git clone https://github.com/Azure/batch-shipyard.git
```
or [download the latest release](https://github.com/Azure/batch-shipyard/releases).

Batch Shipyard includes an installation script to simplify installation on
a variety of recent platforms. This installation script can be used
regardless of if you obtained Batch Shipyard through `git clone` or
downloading a release package.

To install required software:
```shell
# Ensure you are not root
# Obtain Batch Shipyard through git clone or downloading the archive and unpacking
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install for Python2
./install.sh
# Or if you prefer Python3
./install.sh -3
```
Please ensure that you are not invoking the install script as root. `sudo`
will be invoked wherever root access is required for installing system-wide
packages in the `install.sh` script. Python packages required by Batch
Shipyard will be installed in the user context.

## Installation With Docker
If using the [alfpark/batch-shipyard:cli-latest](https://hub.docker.com/r/alfpark/batch-shipyard)
Docker image, then all of the required software is bundled in the image
itself, however, you will need an installation of the Docker engine on
your machine. More information on installing Docker to your local machine
can be found [here](https://www.docker.com/products/overview).

To install:
```shell
docker pull alfpark/batch-shipyard:cli-latest
```
This will pull the cli Docker image of batch-shipyard to your local machine.
You are now ready to execute it with `docker run`. Please see the
[Batch Shipyard Usage](20-batch-shipyard-usage.md) guide for more information
on how to execute the cli Docker image.

## Upgrading to New Releases
To upgrade to a new release, simply execute `git pull` or download a new
release archive and unpack. Rerun the `install.sh` script for all upgrades
as dependencies may have changed between versions.

If using the cli Docker image, simply re-issue the `docker pull` command
above.

## Windows and Mac
Please note that while Batch Shipyard can run on Windows or Mac, these
platforms are not the primary test environments and are not officially
supported. Additionally, some functionality is not supported in Windows.
For the best experience, please run Batch Shipyard from Linux.

Note that if you are cloning the repository on Windows, please ensure that
git or any text editor does not modify the Unix line-endings (LF) for any
file in the `scripts` directory. The repostiory's `.gitattributes` attempts
to force the line endings for all text files, but could be overridden by
your local git configuration. If these files are modified with Windows
line-endings (CRLF) then compute nodes will fail to start properly.

## Manual Installation
### Requirements
The Batch Shipyard tool is written in Python. The client script is compatible
with Python 2.7 or 3.3+. You will also need to install the
[Azure Batch](https://pypi.python.org/pypi/azure-batch) and
[Azure Storage](https://pypi.python.org/pypi/azure-storage) python packages.
Installation can be performed using the [requirements.txt](../requirements.txt)
file via the command `pip install --upgrade --user -r requirements.txt`
(or via `pip3` for python3). If `pip` is not installed on your system,
please continue reading below. Note that this `pip` command should be run
for every Batch Shipyard upgrade if not using `install.sh`.

Batch Shipyard has some Python dependencies which require a valid compiler,
ssl, ffi, and python development libraries to be installed due to the
[cryptography](https://pypi.python.org/pypi/cryptography) dependency on Linux.
For Windows, binary wheels will be installed for dependencies, thus no
development environment is needed. The following are example commands to
execute (as root or with `sudo`) to install the required dependencies on Linux:

####Ubuntu/Debian
```
apt-get update
apt-get install -y build-essential libssl-dev libffi-dev libpython-dev python-dev python-pip
pip install --upgrade pip
```

####CentOS/RHEL/Fedora
```
yum install -y gcc openssl-dev libffi-devel python-devel
curl https://bootstrap.pypa.io/get-pip.py | python
```

####SLES/OpenSUSE
```
zypper ref
zypper -n in gcc libopenssl-devel libffi48-devel python-devel python-pip
pip install --upgrade pip
```

####Note about Python 3.3+
If installing for Python 3.3+, then simply use the Python3 equivalents for
the python dependencies. For example, on Ubuntu/Debian:

```
apt-get update
apt-get install -y build-essential libssl-dev libffi-dev libpython3-dev python3-dev python3-pip
pip install --upgrade pip
```

would install the proper dependencies for Python3.

###Data Movement Support
Batch Shipyard contains native support for moving files locally accessible
at the point of script execution. The `install.sh` script ensures that the
following programs are installed. With a manual installation, the following
programs must be installed to take advantage of data movement features of
Batch Shipyard:

1. An SSH client that provides `scp`. OpenSSH with
[HPN patches](http://www.psc.edu/index.php/hpn-ssh) can be used on the client
side to further accelerate `scp` to Azure Batch compute nodes where
`hpn_server_swap` has been set to `true` in the `pool_specification`.
2. `rsync` if `rsync` functionality is needed.
3. [blobxfer](https://github.com/Azure/blobxfer) if transfering to Azure
storage. This is automatically installed if `pip install` is used with
`requirements.txt` as per above.

Note that data movement which involves programs required in from 1 or 2 above
are not supported if invoked from Windows.

###Encryption Support
Batch Shipyard supports encrypting credentials that are used by backend
components within your pool deployment. In order to utilize this feature,
you must have `openssl` installed. The `install.sh` script ensures that
OpenSSL is installed. Encryption support is not available on Windows.

Note that all commandlines, environment variables and resource file URLs
which are stored by the Azure Batch Service are encrypted by the service.
This feature is to prevent credentials from being displayed in the clear when
using the Azure Portal, Batch Explorer, or other tools to inspect the status
of pools, jobs and tasks. If this is not an issue for your scenario, then
encrypting credentials is unnecessary. Please review the
[credential encryption guide](75-batch-shipyard-credential-encryption.md)
for more information.

## Next Steps
Either continue on to
[Batch Shipyard Configuration](10-batch-shipyard-configuration.md) for a full
explanation of all of the Batch Shipyard configuration options within the
config files or continue to the
[Batch Shipyard Quickstart](02-batch-shipyard-quickstart.md) guide.
