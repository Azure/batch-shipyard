#!/usr/bin/env bash

# shellcheck disable=SC1091

set -e
set -o pipefail

# version consts
DOCKER_CE_VERSION_DEBIAN=18.03.1

# consts
DOCKER_CE_PACKAGE_DEBIAN="docker-ce=${DOCKER_CE_VERSION_DEBIAN}~ce~3-0~"
SHIPYARD_VAR_DIR=/var/batch-shipyard
SHIPYARD_CONF_FILE=${SHIPYARD_VAR_DIR}/federation.json

log() {
    local level=$1
    shift
    echo "$(date -u -Ins) - $level - $*"
}

# dump uname immediately
uname -ar

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
    log ERROR "Unknown DISTRIB_ID or DISTRIB_RELEASE."
    exit 1
fi
DISTRIB_ID=${DISTRIB_ID,,}
DISTRIB_RELEASE=${DISTRIB_RELEASE,,}

# set distribution specific vars
PACKAGER=
if [ "$DISTRIB_ID" == "ubuntu" ]; then
    PACKAGER=apt
elif [ "$DISTRIB_ID" == "debian" ]; then
    PACKAGER=apt
elif [[ $DISTRIB_ID == centos* ]] || [ "$DISTRIB_ID" == "rhel" ]; then
    PACKAGER=yum
else
    PACKAGER=zypper
fi
if [ "$PACKAGER" == "apt" ]; then
    export DEBIAN_FRONTEND=noninteractive
fi

# globals
aad_cloud=
log_level=
log_persist=
log_filename=
post_success_blackout=
post_success_autoscale=
prefix=
refresh_interval_actions=5
refresh_interval_federation=30
storage_account=
storage_rg=
shipyardversion=

# process command line options
while getopts "h?a:l:p:r:s:v:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_federation_bootstrap.sh parameters"
            echo ""
            echo "-a [aad cloud type] AAD cloud type for MSI"
            echo "-l [persistence:level:filename] logging options"
            echo "-p [blackout interval:evaluate autoscale] post-success scheduling options"
            echo "-r [federation:actions] refresh intervals"
            echo "-s [storage account:resource group:prefix] storage config"
            echo "-v [version] batch-shipyard version"
            echo ""
            exit 1
            ;;
        a)
            aad_cloud=${OPTARG,,}
            ;;
        p)
            IFS=':' read -ra p <<< "${OPTARG}"
            post_success_blackout=${p[0]}
            post_success_autoscale=${p[1],,}
            ;;
        l)
            IFS=':' read -ra lo <<< "${OPTARG}"
            log_persist=${lo[0],,}
            log_level=${lo[1],,}
            log_filename=${lo[2]}
            ;;
        r)
            IFS=':' read -ra ri <<< "${OPTARG,,}"
            refresh_interval_federation=${ri[0]}
            refresh_interval_actions=${ri[1]}
            ;;
        s)
            IFS=':' read -ra ss <<< "${OPTARG,,}"
            storage_account=${ss[0]}
            storage_rg=${ss[1]}
            prefix=${ss[2]}
            ;;
        v)
            shipyardversion=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift
# check required params
if [ -z "$aad_cloud" ]; then
    log ERROR "AAD cloud type not specified"
    exit 1
fi

check_for_buggy_ntfs_mount() {
    # Check to ensure sdb1 mount is not mounted as ntfs
    set +e
    mount | grep /dev/sdb1 | grep fuseblk
    local rc=$?
    set -e
    if [ $rc -eq 0 ]; then
        log ERROR "/dev/sdb1 temp disk is mounted as fuseblk/ntfs"
        exit 1
    fi
}

download_file_as() {
    log INFO "Downloading: $1 as $2"
    local retries=10
    set +e
    while [ $retries -gt 0 ]; do
        if curl -fSsL "$1" -o "$2"; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not download: $1"
            exit 1
        fi
        sleep 1
    done
    set -e
}

add_repo() {
    local url=$1
    set +e
    local retries=120
    local rc
    while [ $retries -gt 0 ]; do
        if [ "$PACKAGER" == "apt" ]; then
            curl -fSsL "$url" | apt-key add -
            rc=$?
        elif [ "$PACKAGER" == "yum" ]; then
            yum-config-manager --add-repo "$url"
            rc=$?
        elif [ "$PACKAGER" == "zypper" ]; then
            zypper addrepo "$url"
            rc=$?
        fi
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not add repo: $url"
            exit 1
        fi
        sleep 1
    done
    set -e
}

refresh_package_index() {
    set +e
    local retries=120
    local rc
    while [ $retries -gt 0 ]; do
        if [ "$PACKAGER" == "apt" ]; then
            apt-get update
            rc=$?
        elif [ "$PACKAGER" == "yum" ]; then
            yum makecache -y fast
            rc=$?
        elif [ "$PACKAGER" == "zypper" ]; then
            zypper -n --gpg-auto-import-keys ref
            rc=$?
        fi
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not update package index"
            exit 1
        fi
        sleep 1
    done
    set -e
}

install_packages() {
    set +e
    local retries=120
    local rc
    while [ $retries -gt 0 ]; do
        if [ "$PACKAGER" == "apt" ]; then
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends "$@"
            rc=$?
        elif [ "$PACKAGER" == "yum" ]; then
            yum install -y "$@"
            rc=$?
        elif [ "$PACKAGER" == "zypper" ]; then
            zypper -n in "$@"
            rc=$?
        fi
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not install packages ($PACKAGER): $*"
            exit 1
        fi
        sleep 1
    done
    set -e
}

create_batch_shipyard_federation_config() {
    mkdir -p ${SHIPYARD_VAR_DIR}
    chmod 755 ${SHIPYARD_VAR_DIR}
cat > ${SHIPYARD_CONF_FILE} << EOF
{
    "aad_cloud": "$aad_cloud",
    "storage": {
        "account": "$storage_account",
        "resource_group": "$storage_rg",
        "entity_prefix": "$prefix"
    },
    "batch_shipyard": {
        "var_path": "$SHIPYARD_VAR_DIR",
        "version": "$shipyardversion"
    },
    "logging": {
        "persistence": $log_persist,
        "level": "$log_level",
        "filename": "$log_filename"
    },
    "refresh_intervals": {
        "federations": $refresh_interval_federation,
        "actions": $refresh_interval_actions
    },
    "scheduling": {
        "after_success": {
            "blackout_interval": $post_success_blackout,
            "evaluate_autoscale": $post_success_autoscale
        }
    }
}
EOF
    log INFO "Batch Shipyard federation config created"
}

install_docker_host_engine() {
    log DEBUG "Installing Docker Host Engine"
    # set vars
    if [ "$PACKAGER" == "apt" ]; then
        local repo=https://download.docker.com/linux/"${DISTRIB_ID}"
        local gpgkey="${repo}"/gpg
        local dockerversion="${DOCKER_CE_PACKAGE_DEBIAN}${DISTRIB_ID}"
        local prereq_pkgs="apt-transport-https ca-certificates curl gnupg2 software-properties-common"
    elif [ "$PACKAGER" == "yum" ]; then
        local repo=https://download.docker.com/linux/centos/docker-ce.repo
        local dockerversion="${DOCKER_CE_PACKAGE_CENTOS}"
        local prereq_pkgs="yum-utils device-mapper-persistent-data lvm2"
    elif [ "$PACKAGER" == "zypper" ]; then
        if [[ "$DISTRIB_RELEASE" == 12-sp3* ]]; then
            local repodir=SLE_12_SP3
        fi
        local repo="http://download.opensuse.org/repositories/Virtualization:containers/${repodir}/Virtualization:containers.repo"
        local dockerversion="${DOCKER_CE_PACKAGE_SLES}"
    fi
    # refresh package index
    refresh_package_index
    # install required software first
    # shellcheck disable=SC2086
    install_packages $prereq_pkgs
    if [ "$PACKAGER" == "apt" ]; then
        # add gpgkey for repo
        add_repo "$gpgkey"
        # add repo
        add-apt-repository "deb [arch=amd64] $repo $(lsb_release -cs) stable"
    else
        add_repo "$repo"
    fi
    # refresh index
    refresh_package_index
    # install docker engine
    install_packages "$dockerversion"
    systemctl start docker.service
    systemctl enable docker.service
    systemctl --no-pager status docker.service
    docker info
    log INFO "Docker Host Engine installed"
    # install docker-compose
    install_packages python3-pip python3-distutils apache2-utils
    pip3 install --upgrade setuptools wheel
    pip3 install docker-compose
    log INFO "Docker-compose installed"
}

setup_docker_compose_systemd() {
    # create systemd area for docker compose
    mkdir -p /etc/docker/compose/batch-shipyard-federation
    chmod 644 docker-compose.yml
    cp docker-compose.yml /etc/docker/compose/batch-shipyard-federation/
    # substitute batch shipyard version
    sed -i "s/{BATCH_SHIPYARD_VERSION}/$shipyardversion/g" /etc/docker/compose/batch-shipyard-federation/docker-compose.yml
    # create systemd unit file
cat << EOF > /etc/systemd/system/docker-compose@.service
[Unit]
Description=%i service with docker compose
Requires=docker.service
After=docker.service

[Service]
Restart=always

WorkingDirectory=/etc/docker/compose/%i

# Remove old containers, images and volumes
ExecStartPre=/usr/local/bin/docker-compose down -v
ExecStartPre=/usr/local/bin/docker-compose rm -fv
ExecStartPre=-/bin/bash -c 'docker volume ls -qf "name=%i_" | xargs -r docker volume rm'
ExecStartPre=-/bin/bash -c 'docker network ls -qf "name=%i_" | xargs -r docker network rm'
ExecStartPre=-/bin/bash -c 'docker ps -aqf "name=%i_*" | xargs -r docker rm'

# Compose up
ExecStart=/usr/local/bin/docker-compose up

# Compose down, remove containers and volumes
ExecStop=/usr/local/bin/docker-compose down -v

[Install]
WantedBy=multi-user.target
EOF
    log INFO "systemd unit files for docker compose installed"
}

log INFO "Bootstrap start"
echo "Configuration:"
echo "--------------"
echo "OS Distribution: $DISTRIB_ID $DISTRIB_RELEASE"
echo "Batch Shipyard version: $shipyardversion"
echo "AAD cloud: $aad_cloud"
echo "Storage: $storage_account:$storage_rg:$prefix"
echo "Refresh intervals: feds=$refresh_interval_federation actions=$refresh_interval_actions"
echo "Logging: persist=$log_persist level=$log_level filename=$log_filename"
echo ""

# check sdb1 mount
check_for_buggy_ntfs_mount

# set sudoers to not require tty
sed -i 's/^Defaults[ ]*requiretty/# Defaults requiretty/g' /etc/sudoers

# write batch shipyard config
create_batch_shipyard_federation_config

# install docker host engine and docker compose
install_docker_host_engine

# setup docker compose on startup
setup_docker_compose_systemd

# start and enable services
systemctl daemon-reload
systemctl start docker-compose@batch-shipyard-federation
systemctl enable docker-compose@batch-shipyard-federation
systemctl --no-pager status docker-compose@batch-shipyard-federation

log INFO "Bootstrap completed"
