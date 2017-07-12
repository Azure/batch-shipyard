#!/usr/bin/env bash

set -e
set -o pipefail

# vars
PYTHON=python
PIP=pip
SUDO=sudo
VENV_NAME=

# process options
while getopts "h?23ce:" opt; do
    case "$opt" in
        h|\?)
            echo "install.sh parameters"
            echo ""
            echo "-2 install for Python 2.7"
            echo "-3 install for Python 3.3+"
            echo "-c install for Cloud Shell"
            echo "-e [environment name] install to a virtual environment"
            echo ""
            exit 1
            ;;
        2)
            PYTHON=python
            PIP=pip
            ;;
        3)
            PYTHON=python3
            PIP=pip3
            ;;
        c)
            PYTHON=python3
            PIP=pip3
            VENV_NAME=cloudshell
            SUDO=
            ;;
        e)
            VENV_NAME=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

# non-cloud shell environment checks
if [ ! -z $SUDO ]; then
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

# check for anaconda
set +e
ANACONDA=0
$PYTHON -c "from __future__ import print_function; import sys; print(sys.version)" | grep -Ei 'anaconda|continuum|conda-forge'
if [ $? -eq 0 ]; then
    # check for conda
    if hash conda 2> /dev/null; then
        echo "Anaconda environment detected."
    else
        echo "Anaconda environment detected, but conda command not found."
        exit 1
    fi
    if [ -z $VENV_NAME ]; then
        echo "Virtual environment name must be supplied for Anaconda installations."
        exit 1
    fi
    ANACONDA=1
    PIP=pip
fi
set -e

# perform some virtual env parameter checks
INSTALL_VENV_BIN=0
if [ ! -z $VENV_NAME ]; then
    # check if virtual env, env is not named shipyard
    if [ "$VENV_NAME" == "shipyard" ]; then
        echo "Virtual environment name cannot be shipyard. Please use a different virtual environment name."
        exit 1
    fi
    # check for virtualenv executable
    if [ $ANACONDA -eq 0 ]; then
        if hash virtualenv 2> /dev/null; then
            echo "virtualenv found."
        else
            echo "virtualenv not found."
            INSTALL_VENV_BIN=1
        fi
    fi
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
    # check for OS X
    if [ -z ${DISTRIB_ID+x} ] && [ "$(uname)" == "Darwin" ]; then
        DISTRIB_ID=$(uname)
        DISTRIB_RELEASE=$(uname -a | cut -d' ' -f3)
    fi
fi

if [ -z ${DISTRIB_ID+x} ] || [ -z ${DISTRIB_RELEASE+x} ]; then
    echo "Unknown DISTRIB_ID or DISTRIB_RELEASE."
    echo "Please refer to the Installation documentation for manual installation steps."
    exit 1
fi

# lowercase vars
if [ $DISTRIB_ID != "Darwin" ]; then
    DISTRIB_ID=${DISTRIB_ID,,}
    DISTRIB_RELEASE=${DISTRIB_RELEASE,,}
fi

# install requisite packages from distro repo
if [ ! -z $SUDO ] || [ $(id -u) -eq 0 ]; then
    if [ $DISTRIB_ID == "ubuntu" ] || [ $DISTRIB_ID == "debian" ]; then
        $SUDO apt-get update
        if [ $PYTHON == "python" ]; then
            PYTHON_PKGS="libpython-dev python-dev"
            if [ $ANACONDA -eq 0 ]; then
                PYTHON_PKGS="$PYTHON_PKGS python-pip"
            fi
        else
            PYTHON_PKGS="libpython3-dev python3-dev"
            if [ $ANACONDA -eq 0 ]; then
                PYTHON_PKGS="$PYTHON_PKGS python3-pip"
            fi
        fi
        $SUDO apt-get install -y --no-install-recommends \
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
        $SUDO yum install -y gcc openssl-devel libffi-devel openssl \
            openssh-clients rsync $PYTHON_PKGS
        if [ $ANACONDA -eq 0 ]; then
            curl -fSsL https://bootstrap.pypa.io/get-pip.py | $SUDO $PYTHON
        fi
    elif [ $DISTRIB_ID == "opensuse" ] || [ $DISTRIB_ID == "sles" ]; then
        $SUDO zypper ref
        if [ $PYTHON == "python" ]; then
            PYTHON_PKGS="python-devel"
        else
            PYTHON_PKGS="python3-devel"
        fi
        $SUDO zypper -n in gcc libopenssl-devel libffi48-devel openssl \
            openssh rsync $PYTHON_PKGS
        if [ $ANACONDA -eq 0 ]; then
            curl -fSsL https://bootstrap.pypa.io/get-pip.py | $SUDO $PYTHON
        fi
    elif [ $DISTRIB_ID == "Darwin" ]; then
        # check for pip, otherwise install it
        if hash $PIP 2> /dev/null; then
            echo "$PIP detected."
        else
            echo "$PIP not found, installing for Python"
            $SUDO $PYTHON -m ensurepip
        fi
    else
        echo "Unsupported distribution."
        echo "Please refer to the Installation documentation for manual installation steps."
        exit 1
    fi
fi

# create virtual env if required and install required python packages
if [ ! -z $VENV_NAME ]; then
    # install virtual env if required
    if [ $INSTALL_VENV_BIN -eq 1 ]; then
        if [ ! -z $SUDO ] || [ $(id -u) -eq 0 ]; then
            $SUDO $PIP install virtualenv
        else
            $PIP install --user virtualenv
        fi
    fi
    if [ $ANACONDA -eq 0 ]; then
        # create venv if it doesn't exist
        if [ ! -z $SUDO ] || [ $(id -u) -eq 0 ]; then
            virtualenv -p $PYTHON $VENV_NAME
        else
            $HOME/.local/bin/virtualenv -p $PYTHON $VENV_NAME
        fi
        source $VENV_NAME/bin/activate
        $PIP install --upgrade pip setuptools
        $PIP install --upgrade -r requirements.txt
        deactivate
    else
        # create conda env
        set +e
        conda create --yes --name $VENV_NAME
        set -e
        source activate $VENV_NAME
        conda install --yes pip
        # temporary workaround with pip requirements upgrading setuptools and
        # conda pip failing to reference the old setuptools version
        set +e
        $PIP install --upgrade setuptools
        set -e
        $PIP install --upgrade -r requirements.txt
        source deactivate $VENV_NAME
    fi
else
    $SUDO $PIP install --upgrade pip setuptools
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
    if [ $ANACONDA -eq 0 ]; then
cat >> shipyard << 'EOF'
source $BATCH_SHIPYARD_ROOT_DIR/$VENV_NAME/bin/activate
EOF
    else
cat >> shipyard << 'EOF'
source activate $VENV_NAME
EOF
    fi
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
    if [ $ANACONDA -eq 0 ]; then
cat >> shipyard << 'EOF'
deactivate
EOF
    else
cat >> shipyard << 'EOF'
source deactivate $VENV_NAME
EOF
    fi
fi

chmod 755 shipyard

echo ""
if [ -z $VENV_NAME ]; then
    echo '>> Please add $HOME/.local/bin to your $PATH. You can do this '
    echo '>> permanently in your shell rc script, e.g., .bashrc for bash shells.'
    echo ""
fi
echo ">> Install complete for $PYTHON. Please run Batch Shipyard as: $PWD/shipyard"
