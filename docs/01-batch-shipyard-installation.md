# Batch Shipyard Installation
Installation is an easy two-step process: fetch the code and run the
install script to download and setup dependencies.

## Installation
### Step 1: Acquire Batch Shipyard
Clone the repository:
```shell
git clone https://github.com/Azure/batch-shipyard.git
```
or [download the latest release](https://github.com/Azure/batch-shipyard/releases)
and unpack the archive.

### Step 2a: [Linux] Run the install.sh Script
Batch Shipyard includes an installation script to simplify installation on
a variety of recent Linux distributions. This installation script can be used
regardless of if you obtained Batch Shipyard through `git clone` or
downloading a release package.

Please ensure that your target Python distribution is 2.7 or 3.3+. It is
recommended to install Batch Shipyard on Python 3.5 or later. Although Python
3.5 or later is recommended, if you cannot easily install Python 3.5+ on
your system but Python 2.7 is available, then please use that version of
Python to avoid installation hassles with a Python interpreter.

Install required software as follows:
```shell
# Ensure you are not root
# Obtain Batch Shipyard through git clone or downloading the archive and unpacking
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install for Python 2.7
./install.sh
# Or to install for Python 3.5+ (recommended)
./install.sh -3
# Add $HOME/.local/bin to your PATH in your shell rc file
# For example, the following line can be added to ~/.bashrc for bash shells:
export PATH=$PATH:$HOME/.local/bin
# Reload .bashrc for bash shells
. ~/.bashrc
```
Please ensure that you are not invoking the install script as root. `sudo`
will be invoked wherever root access is required for installing system-wide
packages in the `install.sh` script. Python packages required by Batch
Shipyard will be installed in the user context.

A helper script named `shipyard` will be generated with a successful
installation. This helper script can be invoked in lieu of `shipyard.py`
which will invoke the python script with the appropriate version of
the interpreter.

Please see the Upgrading section below for information on upgrading to a new
release of Batch Shipyard.

#### Installation on CentOS 6.x / RHEL 6.x / Fedora 13 to 18
The default python interpreter distributed with 6.x series releases is
incompatible with Batch Shipyard. To install on these distributions, you must
install `epel-release` package first then the `python34` epel package. Once
these packages are installed, then invoke the installer in the following
manner:

```shell
DISTRIB_ID=centos DISTRIB_RELEASE=6.x ./install.sh -3
```

#### Unsupported Linux Distributions
The following distributions will not work with the `install.sh` script:
* CentOS < 6.0
* Debian < 8
* Fedora < 13
* OpenSUSE < 13.1
* RHEL < 6.0
* SLES < 12
* Ubuntu < 14.04

Please follow the manual installation instructions found later in this
document for these distributions.

### Step 2b: [Windows] Pip Install Dependencies
Invoke `pip.exe` (or `pip3.exe`) and install using the `requirements.txt`
file. For example:
```shell
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install for Windows on Python 3.5+
pip3.exe install --upgrade -r requirements.txt
# Or invoke directly from the installation directory
C:\Python36\Scripts\pip3.exe install --upgrade -r requirements.txt
```
If you are installing on Python < 3.5 on Windows, you will need a compiler
that matches the CRT of the CPython version you are using. For Python 2.7,
you can download the necessary development headers and compiler
[from Microsoft](http://aka.ms/vcpython27). If you are on Python 3.3 or 3.4
on Windows, it is recommended to upgrade to Python 3.5 or later so that you
do not need a compiler to install the dependencies.

Although it is recommended to use the Python distribution from
[python.org](https://www.python.org) for use with Batch Shipyard, if you are
using the Anaconda distribution, you can use the `install_conda_windows.cmd`
file to aid in installing dependencies to your conda environment:
```shell
# Create environment if you haven't done so yet such that you don't install
# to the root environment, unless you really want to
conda create --name batchshipyard
# Activate the environment
activate batchshipyard
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Run installer script
install_conda_windows.cmd
```

Please see the Upgrading section below for information on upgrading to a new
release of Batch Shipyard.

### Step 2c: [Mac] Pip Install Dependencies
Please follow the steps outlined on
[this guide](http://docs.python-guide.org/en/latest/starting/install/osx/)
to ensure that you have a recent version of Python, a compiler and pip. It
is recommended to use Python 3.5 or later for use with Batch Shipyard.

Invoke `pip` and install using the `requirements.txt` file. For example:
```shell
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Reference correct location of pip below if not found on path
pip install --upgrade --user -r requirements.txt
```
Please see the Upgrading section below for information on upgrading to a new
release of Batch Shipyard.

## CLI Installation With Docker
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
release archive and unpack. Next, upgrade the dependencies for your
respective platform below.

#### Linux
Rerun the `install.sh` script for all upgrades.

#### Windows
Reissue the `pip.exe install --upgrade -r requirements.txt` command.

If using Anaconda, you can rerun the `install_conda_windows.cmd` script
within the environment that hosts Batch Shipyard.

#### Mac
Reissue the `pip install --upgrade --user -r requirements.txt` command.

#### CLI Docker
If using the CLI Docker image, simply re-issue the `docker pull` command
above.

## Windows and Mac Support
Please note that while Batch Shipyard can run on Windows or Mac, these
platforms are not the primary test environments and are not officially
supported. Additionally, some functionality is not supported in Windows.
For the best experience, please run Batch Shipyard from Linux.

Note that if you are cloning the repository on Windows, please ensure that
git or any text editor does not modify the Unix line-endings (LF) for any
file in the `scripts` or `resources` directory. The repository's
`.gitattributes` designates line endings for all text files, but can be
overridden by your local git configuration. If these files are modified
with Windows line-endings (CRLF) then compute nodes will fail to start
properly.

## Manual Installation
### Requirements
The Batch Shipyard tool is written in Python. The client script is compatible
with Python 2.7 or 3.3+, although 3.5+ is highly recommended. You will also
need to install dependent Python packages that Batch Shipyard requires.
Installation can be performed using the [requirements.txt](../requirements.txt)
file via the command `pip install --upgrade --user -r requirements.txt` (or
via `pip3` for Python3). Note that this `pip` command should be run for every
Batch Shipyard upgrade if not using `install.sh`. The use of `install.sh` is
highly recommended instead of these manual steps below on Linux platforms.

Batch Shipyard has some Python dependencies which require a valid compiler,
ssl, ffi, and Python development libraries to be installed due to the
[cryptography](https://pypi.python.org/pypi/cryptography) dependency on Linux.
For Windows, binary wheels will be installed for most dependencies. If
installing on Python 3.5 or later for Windows, no development environment
is needed. The following are example commands to execute (as root or with
`sudo`) to install the required dependencies on Linux:

####Ubuntu/Debian
```
apt-get update
apt-get install -y build-essential libssl-dev libffi-dev libpython-dev python-dev python-pip
pip install --upgrade pip
```

####CentOS/RHEL/Fedora
```
yum install -y gcc openssl-dev libffi-devel python-devel
curl -fSsL https://bootstrap.pypa.io/get-pip.py | python
```

####SLES/OpenSUSE
```
zypper ref
zypper -n in gcc libopenssl-devel libffi48-devel python-devel
curl -fSsL https://bootstrap.pypa.io/get-pip.py | python
```

####Note about Python 3.3+
If installing for Python 3.3+, then simply use the Python3 equivalents for
the python dependencies. For example, on Ubuntu/Debian:
```
apt-get update
apt-get install -y build-essential libssl-dev libffi-dev libpython3-dev python3-dev python3-pip
pip3 install --upgrade pip
```
would install the proper dependencies for Python3.

###Data Movement Support
Batch Shipyard contains native support for moving files locally accessible
at the point of script execution. The `install.sh` script ensures that the
following programs are installed. The Docker CLI image contains all of the
necessary software as well. With a manual installation, the following
programs must be installed to take advantage of data movement features of
Batch Shipyard:

1. An SSH client that provides `ssh` and `scp` (or `ssh.exe` and `scp.exe`
on Windows). OpenSSH with
[HPN patches](https://www.psc.edu/index.php/using-joomla/extensions/templates/atomic/636-hpn-ssh)
can be used on the client side to further accelerate `scp` to Azure Batch
compute nodes where `hpn_server_swap` has been set to `true` in the
`pool_specification`.
2. `rsync` if `rsync` functionality is needed. This is not supported on
Windows.
3. [blobxfer](https://github.com/Azure/blobxfer) if transfering to Azure
storage. This is automatically installed if `pip install` is used with
`requirements.txt` as per above. If installed with `--user` flag, this is
typically placed in `~/.local/bin`. This path will need to be added to your
`PATH` environment variable.

###Encryption Support
Batch Shipyard supports encrypting credentials that are used by backend
components within your pool deployment. In order to utilize this feature,
you must have `openssl` installed. The `install.sh` script ensures that
OpenSSL is installed. The Docker CLI image also contains OpenSSL.

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
