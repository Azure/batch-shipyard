# Batch Shipyard Installation
There are multiple available options for installing Batch Shipyard. Please
pick an option that is most suitable for your work environment.

* [Azure Cloud Shell](#cloudshell)
* [Pre-built binary](#binary)
* [Installers](#installers)
* [Docker image](#docker-install)
* [Singularity image](#singularity-install)
* [Jupyter Notebooks](#jupyter)

If you wish to install Batch Shipyard into your Azure App Service (e.g.,
Azure Function App) environment, please see
[this guide](60-batch-shipyard-site-extension.md).

## <a name="cloudshell"></a>Azure Cloud Shell
Batch Shipyard is now integrated into
[Azure Cloud Shell](https://docs.microsoft.com/azure/cloud-shell/overview)
with no installation required. Simply request a Cloud Shell session and type
`shipyard` to invoke the CLI. Data stored in your home directory or
`clouddrive` will persist between Cloud Shell sessions.

Note that Azure Cloud Shell may not have the most recent release of
Batch Shipyard. You can see the version of Batch Shipyard installed with
the command `shipyard --version`.

If you wish to install Batch Shipyard on your machine, please proceed to the
Installation section.

## <a name="binary"></a>Pre-built Binary
Download an appropriate [Release](https://github.com/Azure/batch-shipyard/releases)
binary for your operating system. Pre-built binaries are not available
for all platforms and architectures at this time.

Note that for the Linux pre-built binary, it may not work on all
distributions. If this is the case, please pick an alternate installation
method. After downloading the binary, make sure that the executable bit is
set via `chmod +x` prior to attempting to execute the file.

## <a name="installers"></a>Installation via Script
Installation is an easy two-step process if using the installers: fetch the
code and run the install script to download and setup dependencies. This
is typically the most flexible and compatible installation outside of the
Docker image for the CLI.

### Step 1: Acquire Batch Shipyard
Clone the repository:
```shell
git clone https://github.com/Azure/batch-shipyard.git
```
or [download the latest release](https://github.com/Azure/batch-shipyard/releases)
and unpack the archive.

For the next step (if not using the Batch Shipyard CLI Docker image), refer
to your operating system specific installation instructions:

* [Linux](#linux-install)
* [Mac OS X](#mac-install)
* [Windows](#windows-install)
* [Windows Subsystem for Linux](#wsl-install)

Alternatively, you can install the Batch Shipyard CLI on your machine via
[Docker](#docker-install) or [Singularity](#singularity-install). If using
the Docker image, this is the only step needed and does not require any
futher installation steps.

### <a name="linux-install"></a>Step 2 [Linux]: Run the `install.sh` Script
Batch Shipyard includes an installation script to simplify installation on
a variety of recent Linux distributions. This installation script can be used
regardless of if you obtained Batch Shipyard through `git clone` or
downloading a release package.

Please ensure that your target Python distribution is 2.7 or 3.4+. It is
recommended to install Batch Shipyard on Python 3.4 or later. Although Python
3.4+ is recommended, if you cannot easily install Python 3.4+ on
your system but Python 2.7 is available, then please use that version of
Python to avoid installation hassles with a Python interpreter.

The `install.sh` script supports isolated installation through a virtual
environment so that other system-wide or user python dependencies are left
unmodified. To perform this style of installation, which is recommended
and the default, simply invoke the `install.sh` script without parameters.
If you would like to specify the virtual environment to use, use the
`-e` parameter. If you don't want to use a virtual environment and instead
would like to install into your user environment, specify the `-u` option.
Using this option will require modifying your shell rc file for advanced
data movement capability provided by Batch Shipyard. Note that the default
installation targets `python3`; you can use the `-2` argument to install
for `python` (Python 2.7).

The recommended installation method with a virtual environment:
```shell
# Ensure you are NOT root
# Obtain Batch Shipyard through git clone or downloading the archive and unpacking
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install for Python 3.4+ (recommended) in the virtual environment ".shipyard"
./install.sh
# Or install for Python 2.7 (not recommended) in the virtual environment ".shipyard"
./install.sh -2
```

A helper script named `shipyard` will be generated with a successful
installation. This helper script can be invoked in lieu of `shipyard.py`
which will invoke shipyard with the appropriate interpreter and virtual
environment, if created during installation.

Do not delete the virtual environment directory (in the above example, a
directory named `.shipyard` would be created), as this contains the
virtual environment required for execution.

Please note that although Anaconda environment installations are supported,
there is a larger startup delay for invoking `shipyard` with Anaconda
environments due to the delay in activating a conda environment.
Python from [python.org](https://www.python.org) (CPython) is recommended as
the execution environment.

Alternatively, install directly into your "user" environment:
```shell
# Ensure you are not root
# Obtain Batch Shipyard through git clone or downloading the archive and unpacking
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install for Python 3.4+
./install.sh -u
# Or install for Python 2.7
./install.sh -2 -u
# Add $HOME/.local/bin to your PATH in your shell rc file if it is not present.
# For example, the following line can be added to ~/.bashrc for bash shells:
export PATH=$PATH:$HOME/.local/bin
# Reload .bashrc for bash shells
. ~/.bashrc
```

Please ensure that you are not invoking the install script as root. `sudo`
will be invoked wherever root access is required for installing system-wide
packages in the `install.sh` script. Python packages required by Batch
Shipyard will be installed either in the virtual environment or user context.

Please see the Upgrading section below for information on upgrading to a new
release of Batch Shipyard.

#### Installation on CentOS 6.x / RHEL 6.x / Fedora 13 to 18
The default python interpreter distributed with 6.x series releases is
incompatible with Batch Shipyard. To install on these distributions, you must
install `epel-release` package first then the `python34` epel package. Once
these packages are installed, then invoke the installer in the following
manner:

```shell
DISTRIB_ID=centos DISTRIB_RELEASE=6.x ./install.sh
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

### <a name="mac-install"></a>Step 2 [Mac]: Run the `install.sh` Script
It is recommended to follow the steps outlined on
[this guide](http://docs.python-guide.org/en/latest/starting/install3/osx/#install3-osx)
to install Batch Shipyard on a Python3 installation rather than the default
Python 2.7 that is shipped with Mac OS X. However, if you prefer to use
the system defaulted Python 2.7, the installation will work with that
environment as well.

The `install.sh` script supports isolated installation through a virtual
environment so that other system-wide or user python dependencies are left
unmodified. To perform this style of installation, which is recommended,
specify the virtual environment to create with the `-e` parameter. This option
also does not require modifying your shell rc file for advanced data movement
capability provided by Batch Shipyard.

The recommended installation method with a virtual environment:
```shell
# Ensure you are not root
# Obtain Batch Shipyard through git clone or downloading the archive and unpacking
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install for Python 3.4+ (recommended) in the virtual environment ".shipyard"
./install.sh
# Or to install for Python 2.7 in the virtual environment ".shipyard"
./install.sh -2
```

A helper script named `shipyard` will be generated with a successful
installation. This helper script can be invoked in lieu of `shipyard.py`
which will invoke shipyard with the appropriate interpreter and virtual
environment, if created during installation.

Do not delete the virtual environment directory (in the above example, a
directory named `.shipyard` would be created), as this contains the
virtual environment required for execution.

Please note that although Anaconda environment installations are supported,
there is a larger startup delay for invoking `shipyard` with Anaconda
environments due to the delay in activating a conda environment.
Python from [python.org](https://www.python.org) (CPython) is recommended as
the execution environment which can be installed easily with the Homebrew
as noted in the aforementioned guide.

Please see the Upgrading section below for information on upgrading to a new
release of Batch Shipyard.

### <a name="windows-install"></a>Step 2 [Windows]: Run the `install.cmd` Script
Batch Shipyard includes a installation command file that simplifies
installing Batch Shipyard on [python.org (CPython)](https://www.python.org)
and Anaconda. It is highly recommended to use Python 3.5 or later (or an
Anaconda equivalent). The use of the `install.cmd` script installs Batch
Shipyard into a virtual environment. Please ensure that `python.exe` can be
found in your `%PATH%`. For example:

```shell
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install Batch Shipyard into the virtual environment named "shipyard.venv"
install.cmd shipyard.venv
```

A helper command file named `shipyard.cmd` will be generated with a successful
installation. This helper script can be invoked in lieu of `shipyard.py`
which will invoke shipyard with the appropriate interpreter and virtual
environment, if created during installation.

Do not delete the virtual environment directory (in the above example, a
directory named `shipyard.venv` would be created), as this contains the
virtual environment required for execution.

Please note that although Anaconda environment installations are supported,
there is a larger startup delay for invoking `shipyard.cmd` with Anaconda
environments due to the delay in activating a conda environment.
Python from [python.org](https://www.python.org) (CPython) is recommended as
the execution environment.

If you are installing on Python 3.4 on Windows, you will need a compiler
that matches the CRT of the CPython version you are using. For Python 2.7,
you can download the necessary development headers and compiler
[from Microsoft](http://aka.ms/vcpython27). If you are on Python 3.4
on Windows, it is recommended to upgrade to Python 3.5 or later so that you
do not need a compiler to install the dependencies.

Alternatively you can install Batch Shipyard using the `requirements.txt`
file:

```shell
# Install for Windows on Python 3.5+
pip3.exe install --upgrade -r requirements.txt
# Or invoke directly from wherever you installed python
C:\Python36\Scripts\pip3.exe install --upgrade -r requirements.txt
```

Note that installing directly using the `requirements.txt` file does not
create a `shipyard.cmd` file that wraps `shipyard.py` and points it to the
proper interpreter.

Please see the Upgrading section below for information on upgrading to a new
release of Batch Shipyard.

### <a name="wsl-install"></a>Step 2 [Windows Subsytem for Linux]: Run the `install.sh` Script
Windows Subsystem for Linux (using Ubuntu) now comes with Python3 installed
out of the box. This is the recommended Python interpreter to use with Batch
Shipyard. First, you must enable and install Windows Subsystem for Linux.
Please follow the
[installation guide from Microsoft](https://msdn.microsoft.com/commandline/wsl/install_guide),
if you have not enabled and installed it.

The `install.sh` script supports isolated installation through a virtual
environment so that other system-wide or user python dependencies are left
unmodified. To perform this style of installation, which is recommended,
specify the virtual environment to create with the `-e` parameter. This option
also does not require modifying your shell rc file for advanced data movement
capability provided by Batch Shipyard.

Once you have installed and activated the Windows Subsystem for Linux and
Bash, the recommended installation method with a virtual environment is as
follows:

```shell
# Obtain Batch Shipyard through git clone or downloading the archive and unpacking
# Change directory to where Batch Shipyard was cloned or unpacked to
cd batch-shipyard
# Install for Python3 in the virtual environment ".shipyard"
./install.sh
```

A helper script named `shipyard` will be generated with a successful
installation. This helper script can be invoked in lieu of `shipyard.py`
which will invoke shipyard with the appropriate interpreter and virtual
environment, if created during installation. For the purposes of usage
documentation as it refers to either Linux or Windows, Batch Shipyard
installations on Windows Subsystem for Linux should be considered as
Linux.

Do not delete the virtual environment directory (in the above example, a
directory named `.shipyard` would be created), as this contains the
virtual environment required for execution.

Please see the Upgrading section below for information on upgrading to a new
release of Batch Shipyard.

## <a name="docker-install"></a>Batch Shipyard CLI Installation via Docker
If using the [alfpark/batch-shipyard:latest-cli](https://hub.docker.com/r/alfpark/batch-shipyard)
Docker image, then all of the required software is bundled in the image
itself, however, you will need an installation of the Docker engine on
your machine. More information on installing Docker to your local machine
can be found [here](https://www.docker.com/products/overview).

To install:
```shell
docker pull alfpark/batch-shipyard:latest-cli
```
This will pull the CLI Docker image of Batch Shipyard to your local machine.
You are now ready to execute it with `docker run`. Please see the
[Batch Shipyard Usage](20-batch-shipyard-usage.md) guide for more information
on how to execute the Batch Shipyard CLI Docker image.

## <a name="singularity-install"></a>Batch Shipyard CLI Installation via Singularity
If using the [alfpark/batch-shipyard-singularity:cli](https://www.singularity-hub.org/collections/204)
Singularity image, then all of the required software is bundled in the image
itself, however, you will need an installation of Singularity on your
machine. More information on installing Singularity to your local machine
can be found [here](https://www.sylabs.io/singularity/).

To install:
```shell
singularity pull shub://alfpark/batch-shipyard-singularity:cli
```
This will pull the CLI Singularity image of Batch Shipyard to your local
machine (to the current working directory). You are now ready to execute
it with `singularity run` or simply just executing the image. Please see
the [Batch Shipyard Usage](20-batch-shipyard-usage.md) guide for more
information on how to execute the Batch Shipyard CLI Singularity image.

## <a name="jupyter"></a>Jupyter Notebooks
There are community contributed [Jupyter notebooks](../contrib/notebooks) to
help you quickly get started if you prefer that environment instead of a
commandline.

## Upgrading to New Releases
To upgrade to a new release, simply execute `git pull` or download a new
release archive and unpack. Next, upgrade the dependencies for your
respective platform below.

#### Linux, Mac, and Windows Subsystem for Linux
Rerun the `install.sh` script with the appropriate parameters for all
upgrades. Please ensure that if you specified `-2`, `-3` and/or the
`-e <env name>` parameter, then these parameters are issued again for
upgrades.

#### Windows
Rerun the `install.cmd` script with the same virtual environment parameter.

#### CLI Docker
If using the CLI Docker image, simply re-issue the `docker pull` command
above.

#### Pre-built Binary
Download a new version of the binary.

## Windows Support
Please note that while Batch Shipyard can run on Windows, some functionality
may not be supported in Windows out of the box such as SSH, scp, rsync, and
credential encryption functionality. To ensure support for these features
on Windows, please read the Data Movement and Optional Credential Encryption
Support sections below.

Alternatively, you can install Batch Shipyard on the
[Windows Subsystem for Linux](#wsl-install) with full support for all
functionality as if running on Linux natively.

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
with Python 2.7 or 3.4+, although 3.5+ is highly recommended. You will also
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

#### Ubuntu/Debian
```
apt-get update
apt-get install -y build-essential libssl-dev libffi-dev libpython-dev python-dev python-pip
pip install --upgrade pip
```

#### CentOS/RHEL/Fedora
```
yum install -y gcc openssl-devel libffi-devel python-devel
curl -fSsL https://bootstrap.pypa.io/get-pip.py | python
```

#### SLES/OpenSUSE
```
zypper ref
zypper -n in gcc libopenssl-devel libffi48-devel python-devel
curl -fSsL https://bootstrap.pypa.io/get-pip.py | python
```

#### Note about Python 3.4+
If installing for Python 3.4+, then simply use the Python3 equivalents for
the python dependencies. For example, on Ubuntu/Debian:
```
apt-get update
apt-get install -y build-essential libssl-dev libffi-dev libpython3-dev python3-dev python3-pip
pip3 install --upgrade pip
```
would install the proper dependencies for Python3.

### Data Movement Support
Batch Shipyard contains native support for moving files locally accessible
at the point of script execution. The `install.sh` script ensures that the
following programs are installed. The Docker CLI image contains all of the
necessary software as well. With a manual installation, the following
programs must be installed to take advantage of data movement features of
Batch Shipyard:

1. An SSH client that provides `ssh` and `scp` (or `ssh.exe` and `scp.exe`
on Windows). You can find
[OpenSSH binaries for Windows](https://github.com/PowerShell/Win32-OpenSSH/releases)
released by the PowerShell team. OpenSSH with
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

### Optional Credential Encryption Support
Batch Shipyard supports optionally
[encrypting credentials](75-batch-shipyard-credential-encryption.md)
that are used by backend components within your pool deployment (please
refer to the referenced guide on if your scenario requires this
functionality). In order to utilize this feature, you must have `openssl`
(or `openssl.exe` on Windows) installed. The `install.sh` script ensures that
OpenSSL is installed on Linux. The Docker CLI image also contains OpenSSL
binaries. You might be able to find
[OpenSSL binaries for Windows](https://wiki.openssl.org/index.php/Binaries)
on the OpenSSL wiki.

Note that all commandlines, environment variables and resource file URLs
which are stored by the Azure Batch Service are encrypted by the service.
This feature is to prevent credentials from being displayed in the clear when
using the Azure Portal, Batch Labs, or other tools to inspect the status
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
