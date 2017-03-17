#!/usr/bin/env bash

set -e
set -o pipefail

# vars
PYTHON=python
PIP=pip
VENV_NAME=

# process options
while getopts "h?3e:" opt; do
    case "$opt" in
        h|\?)
            echo "install.sh parameters"
            echo ""
            echo "-3 install for Python 3.3+"
            echo "-e [environment name] install to a virtual environment"
            echo ""
            exit 1
            ;;
        3)
            PYTHON=python3
            PIP=pip3
            ;;
        e)
            VENV_NAME=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

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

# check for python
if hash $PYTHON 2> /dev/null; then
    echo "Installing for $PYTHON."
else
    echo "$PYTHON not found, please install $PYTHON first with your system software installer."
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
    if [ $PYTHON == "python" ]; then
        PYTHON_PKGS="libpython-dev python-dev python-pip"
    else
        PYTHON_PKGS="libpython3-dev python3-dev python3-pip"
    fi
    sudo apt-get install -y --no-install-recommends \
        build-essential libssl-dev libffi-dev openssl \
        openssh-client rsync $PYTHON_PKGS
elif [ $DISTRIB_ID == "centos" ] || [ $DISTRIB_ID == "rhel" ]; then
    if [ $PYTHON == "python" ]; then
        PYTHON_PKGS="python-devel"
    else
        if [ $(yum list installed epel-release) -ne 0 ]; then
            echo "epel-release package not installed."
            echo "Please install the epel-release package or refer to the Installation documentation for manual installation steps".
            exit 1
        fi
        if [ $(yum list installed python34) -ne 0 ]; then
            echo "python34 epel package not installed."
            echo "Please install the python34 epel package or refer to the Installation documentation for manual installation steps."
            exit 1
        fi
        PYTHON_PKGS="python34-devel"
    fi
    sudo yum install -y gcc openssl-devel libffi-devel openssl \
        openssh-clients rsync $PYTHON_PKGS
    curl -fSsL https://bootstrap.pypa.io/get-pip.py | sudo $PYTHON
elif [ $DISTRIB_ID == "opensuse" ] || [ $DISTRIB_ID == "sles" ]; then
    sudo zypper ref
    if [ $PYTHON == "python" ]; then
        PYTHON_PKGS="python-devel"
    else
        PYTHON_PKGS="python3-devel"
    fi
    sudo zypper -n in gcc libopenssl-devel libffi48-devel openssl \
        openssh rsync $PYTHON_PKGS
    curl -fSsL https://bootstrap.pypa.io/get-pip.py | sudo $PYTHON
else
    echo "Unsupported distribution."
    echo "Please refer to the Installation documentation for manual installation steps."
    exit 1
fi

# create virtual env if required and install required python packages
if [ ! -z $VENV_NAME ]; then
    # create venv
    mkdir -p $VENV_NAME
    virtualenv -p $PYTHON $VENV_NAME
    source $VENV_NAME/bin/activate
    $PIP install --upgrade pip setuptools
    $PIP install --upgrade -r requirements.txt
    deactivate
else
    sudo $PIP install --upgrade pip setuptools
    $PIP install --upgrade --user -r requirements.txt
fi

# create shipyard script
cat > shipyard << EOF
#!/usr/bin/env bash

set -e
set -f

BATCH_SHIPYARD_ROOT_DIR=$PWD
VENV_NAME=$VENV_NAME

EOF
cat >> shipyard << 'EOF'
if [ -z $BATCH_SHIPYARD_ROOT_DIR ]; then
    echo Batch Shipyard root directory not set.
    echo Please rerun the install.sh script.
    exit 1
fi

EOF

if [ ! -z $VENV_NAME ]; then
cat >> shipyard << 'EOF'
source $BATCH_SHIPYARD_ROOT_DIR/$VENV_NAME/bin/activate
EOF
fi

if [ $PYTHON == "python" ]; then
cat >> shipyard << 'EOF'
python $BATCH_SHIPYARD_ROOT_DIR/shipyard.py $*
EOF
else
cat >> shipyard << 'EOF'
python3 $BATCH_SHIPYARD_ROOT_DIR/shipyard.py $*
EOF
fi

if [ ! -z $VENV_NAME ]; then
cat >> shipyard << 'EOF'
deactivate
EOF
fi

chmod 755 shipyard

echo ""
if [ -z $VENV_NAME ]; then
    echo '>> Please add $HOME/.local/bin to your $PATH. You can do this '
    echo '>> permanently in your shell rc script, e.g., .bashrc for bash shells.'
    echo ""
fi
echo ">> Install completed for $PYTHON. Please run Batch Shipyard as: $PWD/shipyard"
