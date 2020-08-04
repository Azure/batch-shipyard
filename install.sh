#!/usr/bin/env bash

# shellcheck disable=SC1090
# shellcheck disable=SC1091

set -e
set -o pipefail

# vars
PYTHON=python3
PIP=pip3
SUDO=sudo
VENV_NAME=.shipyard

# process options
while getopts "h?23ce:u" opt; do
    case "$opt" in
        h|\?)
            echo "install.sh parameters"
            echo ""
            echo "-2 install for Python 2.7"
            echo "-3 install for Python 3.4+ [default]"
            echo "-c install for Cloud Shell (via Dockerfile)"
            echo "-e [environment name] install to a virtual environment"
            echo "-u force install into user python environment instead of a virtual enviornment"
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
        u)
            VENV_NAME=
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

# non-cloud shell environment checks
if [ -n "$SUDO" ]; then
    # check to ensure this is not being run directly as root
    if [ "$(id -u)" -eq 0 ]; then
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
if [ ! -f "${PWD}"/shipyard.py ]; then
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
if $PYTHON -c "from __future__ import print_function; import sys; print(sys.version)" | grep -Ei 'anaconda|continuum|conda-forge'; then
    # check for conda
    if hash conda 2> /dev/null; then
        echo "Anaconda environment detected."
    else
        echo "Anaconda environment detected, but conda command not found."
        exit 1
    fi
    if [ -z "$VENV_NAME" ]; then
        echo "Virtual environment name must be supplied for Anaconda installations."
        exit 1
    fi
    ANACONDA=1
    PIP=pip
fi
set -e

# perform some virtual env parameter checks
INSTALL_VENV_BIN=0
if [ -n "$VENV_NAME" ]; then
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
    echo "Installing into virtualenv: $VENV_NAME"
else
    echo "Installing into user environment instead of virtualenv"
fi

# try to get /etc/lsb-release
if [ -e /etc/lsb-release ]; then
    . /etc/lsb-release
else
    if [ -e /etc/os-release ]; then
        . /etc/os-release
        DISTRIB_ID=$ID
        DISTRIB_RELEASE=$VERSION_ID
        DISTRIB_LIKE=$ID_LIKE
    fi
    # check for OS X
    if [ -z "${DISTRIB_ID+x}" ] && [ "$(uname)" == "Darwin" ]; then
        DISTRIB_ID=$(uname)
        DISTRIB_RELEASE=$(uname -a | cut -d' ' -f3)
    fi
fi

if [ -z "${DISTRIB_ID+x}" ] || [ -z "${DISTRIB_RELEASE+x}" ]; then
    echo "Unknown DISTRIB_ID or DISTRIB_RELEASE."
    echo "Please refer to the Installation documentation for manual installation steps."
    exit 1
fi

# lowercase vars
if [ "$DISTRIB_ID" != "Darwin" ]; then
    DISTRIB_ID=${DISTRIB_ID,,}
    DISTRIB_RELEASE=${DISTRIB_RELEASE,,}
fi

echo "Detected OS: $DISTRIB_ID $DISTRIB_RELEASE"

# install requisite packages from distro repo
if [ -n "$SUDO" ] || [ "$(id -u)" -eq 0 ]; then
    if [ "$DISTRIB_ID" == "debian" || "$DISTRIB_LIKE" == "debian" ]; then
        $SUDO apt-get update
        if [ $ANACONDA -eq 1 ]; then
            PYTHON_PKGS=
        else
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
        fi
        # shellcheck disable=SC2086
        $SUDO apt-get install -y --no-install-recommends \
            build-essential libssl-dev libffi-dev openssl \
            openssh-client rsync $PYTHON_PKGS
    elif [ "$DISTRIB_ID" == "centos" ] || [ "$DISTRIB_ID" == "rhel" ]; then
        $SUDO yum makecache fast
        if [ $ANACONDA -eq 1 ]; then
            PYTHON_PKGS=
        else
            if [ $PYTHON == "python" ]; then
                PYTHON_PKGS="python-devel"
            else
                if ! yum list installed epel-release; then
                    echo "epel-release package not installed."
                    echo "Please install the epel-release package or refer to the Installation documentation for manual installation steps".
                    exit 1
                fi
                if ! yum list installed python34; then
                    echo "python34 epel package not installed."
                    echo "Please install the python34 epel package or refer to the Installation documentation for manual installation steps."
                    exit 1
                fi
                PYTHON_PKGS="python34-devel"
            fi
        fi
        # shellcheck disable=SC2086
        $SUDO yum install -y gcc openssl-devel libffi-devel openssl \
            openssh-clients rsync $PYTHON_PKGS
        if [ $ANACONDA -eq 0 ]; then
            curl -fSsL --tlsv1 https://bootstrap.pypa.io/get-pip.py | $SUDO $PYTHON
        fi
    elif [ "$DISTRIB_ID" == "opensuse" ] || [ "$DISTRIB_ID" == "sles" ]; then
        $SUDO zypper ref
        if [ $ANACONDA -eq 1 ]; then
            PYTHON_PKGS=
        else
            if [ $PYTHON == "python" ]; then
                PYTHON_PKGS="python-devel"
            else
                PYTHON_PKGS="python3-devel"
            fi
        fi
        # shellcheck disable=SC2086
        $SUDO zypper -n in gcc libopenssl-devel libffi48-devel openssl \
            openssh rsync $PYTHON_PKGS
        if [ $ANACONDA -eq 0 ]; then
            curl -fSsL --tlsv1 https://bootstrap.pypa.io/get-pip.py | $SUDO $PYTHON
        fi
    elif [ "$DISTRIB_ID" == "Darwin" ]; then
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
if [ -n "$VENV_NAME" ]; then
    # install virtual env if required
    if [ $INSTALL_VENV_BIN -eq 1 ]; then
        if [ -n "$SUDO" ] || [ "$(id -u)" -eq 0 ]; then
            $SUDO $PIP install virtualenv
        else
            $PIP install --user virtualenv
        fi
    fi
    if [ $ANACONDA -eq 0 ]; then
        # create venv if it doesn't exist
        if [ -n "$SUDO" ] || [ "$(id -u)" -eq 0 ]; then
            virtualenv -p $PYTHON "$VENV_NAME"
        else
            "${HOME}"/.local/bin/virtualenv -p $PYTHON "$VENV_NAME"
        fi
        source "${VENV_NAME}"/bin/activate
        $PYTHON -m pip install --upgrade pip
        $PIP install --upgrade setuptools
        set +e
        $PIP uninstall -y azure-storage
        set -e
        $PIP install --upgrade -r requirements.txt
        $PIP install --upgrade --no-deps -r req_nodeps.txt
        deactivate
    else
        # set python version
        pyver=$($PYTHON -c "import sys;a=sys.version_info;print('{}.{}'.format(a[0],a[1]));")
        echo "Creating conda env for Python $pyver"
        # create conda env
        set +e
        conda create --yes --name "$VENV_NAME" python="${pyver}"
        set -e
        source activate "$VENV_NAME"
        conda install --yes pip
        # temporary workaround with pip requirements upgrading setuptools and
        # conda pip failing to reference the old setuptools version
        set +e
        $PIP install --upgrade setuptools
        $PIP uninstall -y azure-storage
        set -e
        $PIP install --upgrade -r requirements.txt
        $PIP install --upgrade --no-deps -r req_nodeps.txt
        source deactivate "$VENV_NAME"
    fi
else
    $PYTHON -m pip install --upgrade --user pip
    $PIP install --upgrade --user setuptools
    set +e
    $PIP uninstall -y azure-storage
    set -e
    $PIP install --upgrade --user -r requirements.txt
    $PIP install --upgrade --no-deps --user -r req_nodeps.txt
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

if [ -n "$VENV_NAME" ]; then
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

if [ -n "$VENV_NAME" ]; then
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
if [ -z "$VENV_NAME" ]; then
    # shellcheck disable=SC2016
    echo '>> Please add $HOME/.local/bin to your $PATH. You can do this '
    echo '>> permanently in your shell rc script, e.g., .bashrc for bash shells.'
    echo ""
fi
echo ">> Install complete for $PYTHON. Please run Batch Shipyard as: $PWD/shipyard"
