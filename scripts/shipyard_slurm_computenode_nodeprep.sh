#!/usr/bin/env bash

# shellcheck disable=SC1091

set -e
set -o pipefail

# version consts
SLURM_VERSION=18.08.5-2

# consts
SLURM_PACKAGE_DEBIAN="slurm-${SLURM_VERSION}_1.0_amd64"
SLURM_PACKAGE_CENTOS="slurm-${SLURM_VERSION}-1.0-1.x86_64"
SLURM_CONF_DIR=/etc/slurm
AZFILE_MOUNT_DIR=/azfile-slurm
SHIPYARD_VAR_DIR=/var/batch-shipyard
SHIPYARD_CONF_FILE=${SHIPYARD_VAR_DIR}/slurm.json
SHIPYARD_HOST_FILE=${SHIPYARD_VAR_DIR}/slurm_host
SHIPYARD_COMPLETED_ASSIGNMENT_FILE=${SHIPYARD_VAR_DIR}/slurm_host.assigned
SHIPYARD_PROVISION_FAILED_FILE=${SHIPYARD_VAR_DIR}/slurm_host.failed
HOSTNAME=$(hostname -s)
HOSTNAME=${HOSTNAME,,}
IP_ADDRESS=$(ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1)

log() {
    local level=$1
    shift
    echo "$(date -u -Ins) - $level - $*"
}

# dump uname immediately
uname -ar

# try to get distrib vars
if [ -e /etc/os-release ]; then
    . /etc/os-release
    DISTRIB_ID=$ID
    DISTRIB_RELEASE=$VERSION_ID
    DISTRIB_CODENAME=$VERSION_CODENAME
    if [ -z "$DISTRIB_CODENAME" ]; then
        if [ "$DISTRIB_ID" == "debian" ] && [ "$DISTRIB_RELEASE" == "9" ]; then
            DISTRIB_CODENAME=stretch
        fi
    fi
else
    if [ -e /etc/lsb-release ]; then
        . /etc/lsb-release
    fi
fi
if [ -z "${DISTRIB_ID+x}" ] || [ -z "${DISTRIB_RELEASE+x}" ]; then
    log ERROR "Unknown DISTRIB_ID or DISTRIB_RELEASE."
    exit 1
fi
if [ -z "${DISTRIB_CODENAME}" ]; then
    log WARNING "Unknown DISTRIB_CODENAME."
fi
DISTRIB_ID=${DISTRIB_ID,,}
DISTRIB_RELEASE=${DISTRIB_RELEASE,,}
DISTRIB_CODENAME=${DISTRIB_CODENAME,,}

# set distribution specific vars
PACKAGER=
PACKAGE_SUFFIX=
SLURM_PACKAGE=
if [ "$DISTRIB_ID" == "ubuntu" ]; then
    PACKAGER=apt
    PACKAGE_SUFFIX=deb
    SLURM_PACKAGE="${SLURM_PACKAGE_DEBIAN}.${PACKAGE_SUFFIX}"
elif [ "$DISTRIB_ID" == "debian" ]; then
    PACKAGER=apt
    PACKAGE_SUFFIX=deb
    SLURM_PACKAGE="${SLURM_PACKAGE_DEBIAN}.${PACKAGE_SUFFIX}"
elif [[ $DISTRIB_ID == centos* ]] || [ "$DISTRIB_ID" == "rhel" ]; then
    PACKAGER=yum
    PACKAGE_SUFFIX=rpm
    SLURM_PACKAGE="${SLURM_PACKAGE_CENTOS}.${PACKAGE_SUFFIX}"
else
    PACKAGER=zypper
    PACKAGE_SUFFIX=rpm
    SLURM_PACKAGE="${SLURM_PACKAGE_CENTOS}.${PACKAGE_SUFFIX}"
fi
if [ "$PACKAGER" == "apt" ]; then
    export DEBIAN_FRONTEND=noninteractive
fi

# globals
aad_cloud=
cluster_id=
cluster_user=
queue_assign=
storage_account=
storage_key=
storage_ep=
storage_prefix=
shipyardversion=

# process command line options
while getopts "h?a:i:q:s:u:v:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_slurm_computenode_bootstrap.sh parameters"
            echo ""
            echo "-a [aad cloud type] AAD cloud type for MSI"
            echo "-i [id] cluster id"
            echo "-q [assign] queue names"
            echo "-s [storage account:storage key:storage ep:prefix] storage config"
            echo "-u [user] cluster username"
            echo "-v [version] batch-shipyard version"
            echo ""
            exit 1
            ;;
        a)
            aad_cloud=${OPTARG,,}
            ;;
        i)
            cluster_id=${OPTARG}
            ;;
        q)
            queue_assign=${OPTARG}
            ;;
        s)
            IFS=':' read -ra ss <<< "${OPTARG}"
            storage_account=${ss[0]}
            storage_key=${ss[1]}
            storage_ep=${ss[2]}
            storage_prefix=${ss[3]}
            ;;
        u)
            cluster_user=${OPTARG}
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
            yum makecache -y
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

install_local_packages() {
    set +e
    local retries=120
    local rc
    while [ $retries -gt 0 ]; do
        if [ "$PACKAGER" == "apt" ]; then
            dpkg -i "$@"
            rc=$?
        else
            rpm -Uvh --nodeps "$@"
            rc=$?
        fi
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not install local packages: $*"
            exit 1
        fi
        sleep 1
    done
    set -e
}

start_and_check_slurmd() {
    local retries=120
    local rc
    set +e
    systemctl start slurmd
    while [ $retries -gt 0 ]; do
        if systemctl --no-pager status slurmd; then
            break
        fi
        sleep 1
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "slurmd could not start properly"
            exit 1
        fi
        systemctl restart slurmd
    done
    set -e
}

create_batch_shipyard_slurm_config() {
    mkdir -p ${SHIPYARD_VAR_DIR}
    chmod 755 ${SHIPYARD_VAR_DIR}
cat > ${SHIPYARD_CONF_FILE} << EOF
{
    "aad_cloud": "$aad_cloud",
    "storage": {
        "account": "$storage_account",
        "account_key": "$storage_key",
        "endpoint": "$storage_ep",
        "entity_prefix": "$storage_prefix",
        "queues": {
            "assign": "$queue_assign"
        },
        "azfile_mount_dir": "$AZFILE_MOUNT_DIR"
    },
    "cluster_id": "$cluster_id",
    "cluster_user": "$cluster_user",
    "ip_address": "$IP_ADDRESS",
    "logging_id": "$AZ_BATCH_NODE_ID",
    "batch": {
        "account": "$AZ_BATCH_ACCOUNT_NAME",
        "pool_id": "$AZ_BATCH_POOL_ID",
        "node_id": "$AZ_BATCH_NODE_ID",
        "is_dedicated": "$AZ_BATCH_NODE_IS_DEDICATED"
    },
    "batch_shipyard": {
        "var_path": "$SHIPYARD_VAR_DIR",
        "version": "$shipyardversion"
    }
}
EOF
    chmod 600 "$SHIPYARD_CONF_FILE"
    log INFO "Batch Shipyard slurm config created"
}

check_provisioning_status() {
    local host=$1
    local reset_host=$2
    set +e
    docker run --rm -v "${SHIPYARD_VAR_DIR}:${SHIPYARD_VAR_DIR}:ro" \
        "mcr.microsoft.com/azure-batch/shipyard:${shipyardversion}-slurm" \
        check-provisioning-status --conf "${SHIPYARD_CONF_FILE}" \
        --host "$1"
    rc=$?
    set -e
    if [ $rc -ne 0 ]; then
        log ERROR "Provisioning interrupt detected for host $1"
        if [ "$reset_host" -eq 1 ] && [ ! -s "$SHIPYARD_PROVISION_FAILED_FILE" ]; then
            host="${host}-$RANDOM"
            log DEBUG "Resetting host name to avoid collision: $host"
            hostnamectl set-hostname "${host}"
            hostnamectl status
            log DEBUG "Rebooting for hostname propagation to DNS"
            touch "$SHIPYARD_PROVISION_FAILED_FILE"
            shutdown -r now
        fi
        exit $rc
    fi
}

log INFO "Bootstrap start"
echo "Configuration:"
echo "--------------"
echo "OS Distribution: $DISTRIB_ID $DISTRIB_RELEASE $DISTRIB_CODENAME"
echo "Hostname: $HOSTNAME"
echo "IP Address: $IP_ADDRESS"
echo "Batch Shipyard Version: $shipyardversion"
echo "AAD cloud: $aad_cloud"
echo "Storage: $storage_account:$storage_prefix"
echo "Cluster Id: $cluster_id"
echo "Cluster user: $cluster_user"
echo "Assign queue: $queue_assign"
echo ""

# check sdb1 mount
check_for_buggy_ntfs_mount

# set sudoers to not require tty
sed -i 's/^Defaults[ ]*requiretty/# Defaults requiretty/g' /etc/sudoers

# if provisioning failed previously, don't proceed further
if [ -s "$SHIPYARD_PROVISION_FAILED_FILE" ]; then
    log ERROR "Slurm host provisioning failed."
    exit 1
fi

# post-reboot token push steps
if [ -s "$SHIPYARD_HOST_FILE" ]; then
    log INFO "Host assignment file found. Assuming reboot was successful."
    hostnamectl status

    # slurmd is manually started since storage clusters are manually mounted
    # check slurmd in a loop, sometimes it can fail starting due to GPU not ready
    start_and_check_slurmd

    # update host entity with batch node id and ip address
    if [ ! -s "$SHIPYARD_COMPLETED_ASSIGNMENT_FILE" ]; then
        host=$(<${SHIPYARD_HOST_FILE})
        log DEBUG "Host from hostfile is: $host"
        check_provisioning_status "$host" 1

        docker run --rm -v "${SHIPYARD_CONF_FILE}:${SHIPYARD_CONF_FILE}:ro" \
            -v "${AZFILE_MOUNT_DIR}:${AZFILE_MOUNT_DIR}:rw" \
            "mcr.microsoft.com/azure-batch/shipyard:${shipyardversion}-slurm" \
            complete-node-assignment --conf "${SHIPYARD_CONF_FILE}" \
            --host "$host"
        touch "$SHIPYARD_COMPLETED_ASSIGNMENT_FILE"
    fi
    log INFO "Bootstrap completed"
    exit 0
fi

# write batch shipyard config
create_batch_shipyard_slurm_config

echo "Fetching host assignment"
docker run --rm -v "${SHIPYARD_VAR_DIR}:${SHIPYARD_VAR_DIR}:rw" \
    -v "${AZFILE_MOUNT_DIR}:${AZFILE_MOUNT_DIR}:rw" \
    "mcr.microsoft.com/azure-batch/shipyard:${shipyardversion}-slurm" \
    get-node-assignment --conf "${SHIPYARD_CONF_FILE}"
host=$(<${SHIPYARD_HOST_FILE})
echo "Hostname assignment retrieved: $host"

check_provisioning_status "$host" 0

# set cluster user and passwordless SSH for MPI jobs
echo "Setting up cluster user: ${cluster_user}"
useradd -o -u 2000 -N -g 1000 -p '!' -s /bin/bash -m -d "/home/${cluster_user}" "${cluster_user}"
ssh_dir="/home/${cluster_user}/.ssh"
mkdir -p "$ssh_dir"
chmod 700 "$ssh_dir"
echo "$SHIPYARD_SLURM_CLUSTER_USER_SSH_PUBLIC_KEY" > "${ssh_dir}/id_rsa.pub"
chmod 644 "${ssh_dir}/id_rsa.pub"
echo "$SHIPYARD_SLURM_CLUSTER_USER_SSH_PUBLIC_KEY" >> "${ssh_dir}/authorized_keys"
chmod 600 "${ssh_dir}/authorized_keys"
cat > "${ssh_dir}/config" << EOF
Host 10.*
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
EOF
chmod 600 "${ssh_dir}/config"
mv slurm_cluster_user_ssh_private_key "${ssh_dir}/id_rsa"
chmod 600 "${ssh_dir}/id_rsa"
chown -R "${cluster_user}:_azbatchgrp" "$ssh_dir"
echo "Cluster user setup complete"

# add slurm user
groupadd -g 64030 slurm
useradd -u 64030 -N -g 64030 -p '!' -s /bin/bash -m -d /home/slurm slurm
slurm_uid=$(id -u slurm)
slurm_gid=$(id -g slurm)

# install slurm packages
if [ "$DISTRIB_ID" == "centos" ]; then
    install_packages epel-release
fi
install_packages hwloc numactl munge
slurm_docker_image="alfpark/slurm:${SLURM_VERSION}-${DISTRIB_ID}-${DISTRIB_RELEASE}"
docker pull "$slurm_docker_image"
mkdir -p /tmp/slurm
docker run --rm -v /tmp/slurm:/tmp/slurm "$slurm_docker_image" \
    /bin/sh -c 'cp -r /root/* /tmp/slurm/'
install_local_packages "/tmp/slurm/${SLURM_PACKAGE}"
cp /tmp/slurm/slurmd.service /etc/systemd/system/
rm -rf /tmp/slurm
docker rmi "$slurm_docker_image"
mkdir -p "$SLURM_CONF_DIR" /var/spool/slurm /var/log/slurm
chown -R slurm:slurm /var/spool/slurm /var/log/slurm
cat << EOF > "/etc/ld.so.conf.d/slurm.conf"
/usr/lib/slurm
EOF
ldconfig
ldconfig -p | grep libslurmfull
systemctl daemon-reload

# mount Azure file share
cat << EOF > "/root/.azfile_creds"
username=$storage_account
password=$storage_key
EOF
chmod 600 /root/.azfile_creds
mkdir -p "$AZFILE_MOUNT_DIR"
chmod 755 "$AZFILE_MOUNT_DIR"
share="${storage_prefix}slurm"
echo "//${storage_account}.file.${storage_ep}/${share} ${AZFILE_MOUNT_DIR} cifs vers=3.0,credentials=/root/.azfile_creds,uid=${slurm_uid},gid=${slurm_gid},_netdev,serverino 0 0" >> /etc/fstab
mount "$AZFILE_MOUNT_DIR"

azfile_cluster_path="${AZFILE_MOUNT_DIR}/${cluster_id}"

# configure munge
shared_munge_key_path="${azfile_cluster_path}/munge"
shared_munge_key="${shared_munge_key_path}/munge.key"
# export munge key to storage
# poll for munge key
echo "Waiting for munge key"
while [ ! -s "$shared_munge_key" ]; do
    sleep 1
done
echo "Munge key found."
cp -f "$shared_munge_key" /etc/munge/munge.key
chmod 400 /etc/munge/munge.key
chown munge:munge /etc/munge/munge.key
if [ "$DISTRIB_ID" == "centos" ]; then
    systemctl start munge
fi
munge -n | unmunge
systemctl enable munge
systemctl restart munge
systemctl --no-pager status munge

# configure slurm
mkdir -p /var/spool/slurmd
chown -R slurm:slurm /var/spool/slurmd
# construct cgroup conf files
cat << EOF > "${SLURM_CONF_DIR}/cgroup.conf"
CgroupAutomount=yes
ConstrainCores=yes
ConstrainDevices=yes
#ConstrainRAMSpace=yes
EOF

cat << EOF > "${SLURM_CONF_DIR}/cgroup_allowed_devices_file.conf"
/dev/null
/dev/urandom
/dev/zero
/dev/sda*
/dev/sdb*
/dev/cpu/*/*
/dev/pts/*
/dev/nvidia*
/dev/infiniband/*
EOF

# copy configuration file
slurm_conf_azfile_path="${azfile_cluster_path}/slurm/conf"
echo "Waiting for slurm configuration file in $slurm_conf_azfile_path"
while [ ! -s "${slurm_conf_azfile_path}/slurm.conf" ]; do
    sleep 1
done
echo "Slurm configuration file found."
cp -f "${slurm_conf_azfile_path}/slurm.conf" "${SLURM_CONF_DIR}/slurm.conf"
chmod 644 "${SLURM_CONF_DIR}/slurm.conf"

check_provisioning_status "$host" 0

# set hostname, reboot required
hostnamectl set-hostname "$host"
hostnamectl status

# construct gres.conf for GPUs
set +e
gpus=$(lspci | grep -i nvidia | awk '{print $1}' | cut -d : -f 1)
set -e
if [ -n "$gpus" ]; then
    gres_file="${SLURM_CONF_DIR}/gres.conf"
    count=0
    for i in $gpus; do
        CPUAFFINITY=$(cat /sys/class/pci_bus/"$i":00/cpulistaffinity)
        echo "NodeName=${host} Name=gpu File=/dev/nvidia${count} CPUs=${CPUAFFINITY}" >> "$gres_file"
        count=$((count+1))
    done
    chmod 644 "$gres_file"
    chown slurm:slurm "$gres_file"
fi

log INFO "Rebooting for hostname propagation to DNS"
shutdown -r now

# TODO add slum pam auth (prevent user from SSHing into a compute node without an allocation)
#install_packages libpam-slurm
#echo "" >> /etc/pam.d/sshd
#echo "account    required    pam_slurm.so" >> /etc/pam.d/sshd
