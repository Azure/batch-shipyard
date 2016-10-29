#!/usr/bin/env bash

set -e
set -o pipefail

PY3=
if [ "$1" == "-3" ]; then
    PY3=1
    echo "Installing for Python3."
else
    PY3=0
    echo "Installing for Python2."
fi

# check to ensure this is not being run directly as root
if [ $(id -u) -eq 0 ]; then
    echo "Installation cannot be performed as root or via sudo."
    echo "Please install as a regular user."
    exit 1
fi

# check for sudo
if hash sudo 2> /dev/null; then
    echo "sudo found."
else
    echo "sudo not found. Please install sudo first before proceeding."
    exit 1
fi

# check that shipyard.py is in cwd
if [ ! -f $PWD/shipyard.py ]; then
    echo "shipyard.py not found in $PWD."
    echo "Please run install.sh from the same directory as shipyard.py."
    exit 1
fi

# try to get /etc/lsb-release
if [ -e /etc/lsb-release ]; then
    . /etc/lsb-release
else
    if [ -e /etc/os-release ]; then
        . /etc/os-release
        DISTRIB_ID=$ID
        DISTRIB_RELEASE=$VERSION_ID
    fi
fi

if [ -z ${DISTRIB_ID+x} ] || [ -z ${DISTRIB_RELEASE+x} ]; then
    echo "Unknown DISTRIB_ID or DISTRIB_RELEASE."
    echo "Please refer to the Installation documentation for manual installation steps."
    exit 1
fi

# lowercase vars
DISTRIB_ID=${DISTRIB_ID,,}
DISTRIB_RELEASE=${DISTRIB_RELEASE,,}

# install requisite packages from distro repo
if [ $DISTRIB_ID == "ubuntu" ] || [ $DISTRIB_ID == "debian" ]; then
    sudo apt-get update
    if [ $PY3 -eq 0 ]; then
        PYTHON_PKGS="libpython-dev python-dev python-pip"
    else
        PYTHON_PKGS="libpython3-dev python3-dev python3-pip"
    fi
    sudo apt-get install -y --no-install-recommends \
        build-essential libssl-dev libffi-dev openssl \
        openssh-client rsync $PYTHON_PKGS
elif [ $DISTRIB_ID == "centos" ] || [ $DISTRIB_ID == "rhel" ]; then
    if [ $PY3 -eq 0 ]; then
        PYTHON_PKGS="python-devel"
        curl https://bootstrap.pypa.io/get-pip.py | sudo python
    else
        PYTHON_PKGS="python3-devel"
        curl https://bootstrap.pypa.io/get-pip.py | sudo python3
    fi
    sudo yum install -y gcc openssl-devel libffi-devel openssl \
        openssh-clients rsync $PYTHON_PKGS
elif [ $DISTRIB_ID == "opensuse" ] || [ $DISTRIB_ID == "sles" ]; then
    sudo zypper ref
    if [ $PY3 -eq 0 ]; then
        PYTHON_PKGS="python-devel python-pip"
    else
        PYTHON_PKGS="python3-devel python3-pip"
    fi
    sudo zypper -n in gcc libopenssl-devel libffi48-devel openssl \
        openssh rsync $PYTHON_PKGS
else
    echo "Unsupported distribution."
    echo "Please refer to the Installation documentation for manual installation steps."
    exit 1
fi

# create shipyard script
cat > shipyard << EOF
#!/usr/bin/env bash

set -e
set -f

BATCH_SHIPYARD_ROOT_DIR=$PWD

EOF
cat >> shipyard << 'EOF'
if [ -z $BATCH_SHIPYARD_ROOT_DIR ]; then
    echo Batch Shipyard root directory not set.
    echo Please rerun the install.sh script.
    exit 1
fi

if hash python3 2> /dev/null; then
    python3 $BATCH_SHIPYARD_ROOT_DIR/shipyard.py $*
else
    python $BATCH_SHIPYARD_ROOT_DIR/shipyard.py $*
fi
EOF
chmod 755 shipyard

# install required python packages
if [ $PY3 -eq 0 ]; then
    sudo pip install --upgrade pip setuptools
    pip install --upgrade --user -r requirements.txt
    echo "Install completed for Python2. Please run Batch Shipyard as: $PWD/shipyard"

else
    sudo pip3 install --upgrade pip setuptools
    pip3 install --upgrade --user -r requirements.txt
    echo "Install completed for Python3. Please run Batch Shipyard as: $PWD/shipyard"
fi
