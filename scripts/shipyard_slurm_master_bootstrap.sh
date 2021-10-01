#!/usr/bin/env bash

# shellcheck disable=SC1039,SC1091,SC2129

set -e
set -o pipefail

# version consts
SLURM_VERSION=18.08.5-2
DOCKER_CE_VERSION_DEBIAN=18.09.2
GLUSTER_VERSION_DEBIAN=4.1
GLUSTER_VERSION_CENTOS=41

# consts
DOCKER_CE_PACKAGE_DEBIAN="docker-ce=5:${DOCKER_CE_VERSION_DEBIAN}~3-0~"
SLURM_CONF_DIR=/etc/slurm
AZFILE_MOUNT_DIR=/azfile-slurm
SHIPYARD_VAR_DIR=/var/batch-shipyard
SHIPYARD_SLURM_PY=${SHIPYARD_VAR_DIR}/slurm.py
SHIPYARD_CONF_FILE=${SHIPYARD_VAR_DIR}/slurm.json
HOSTNAME=$(hostname -s)
HOSTNAME=${HOSTNAME,,}
SHIPYARD_STORAGE_CLUSTER_FSTAB=$(<sdv.fstab)

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
    DISTRIB_LIKE=$ID_LIKE
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
DISTRIB_LIKE=${DISTRIB_LIKE,,}
DISTRIB_CODENAME=${DISTRIB_CODENAME,,}

# set distribution specific vars
PACKAGER=
USER_MOUNTPOINT=/mnt/resource
SYSTEMD_PATH=/lib/systemd/system
if [ "$DISTRIB_ID" == "ubuntu" ]; then
    PACKAGER=apt
    USER_MOUNTPOINT=/mnt
elif [ "$DISTRIB_ID" == "debian" ] || [ "$DISTRIB_LIKE" == "debian" ]; then
    PACKAGER=apt
elif [[ $DISTRIB_ID == centos* ]] || [ "$DISTRIB_ID" == "rhel" ]; then
    PACKAGER=yum
else
    PACKAGER=zypper
    SYSTEMD_PATH=/usr/lib/systemd/system
fi
if [ "$PACKAGER" == "apt" ]; then
    export DEBIAN_FRONTEND=noninteractive
fi

# globals
aad_cloud=
cluster_id=
cluster_name=
cluster_user=
controller_primary=
controller_secondary=
controller_tertiary=
is_primary=0
is_login_node=0
num_controllers=
sc_args=
slurm_state_path=
storage_account=
storage_prefix=
storage_rg=
shipyardversion=

# process command line options
while getopts "h?a:c:i:lm:p:s:u:v:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_slurm_master_bootstrap.sh parameters"
            echo ""
            echo "-a [aad cloud type] AAD cloud type for MSI"
            echo "-c [primary:secondary:tertiary] controller hosts"
            echo "-i [id] cluster id"
            echo "-l is login node"
            echo "-m [type:scid] mount storage cluster"
            echo "-p [path] state save path"
            echo "-s [storage account:resource group:prefix] storage config"
            echo "-u [user] cluster username"
            echo "-v [version] batch-shipyard version"
            echo ""
            exit 1
            ;;
        a)
            aad_cloud=${OPTARG,,}
            ;;
        c)
            IFS=':' read -ra cont <<< "${OPTARG,,}"
            controller_primary=${cont[0]}
            if [ "$controller_primary" == "$HOSTNAME" ]; then
                is_primary=1
            fi
            controller_secondary=${cont[1]}
            controller_tertiary=${cont[2]}
            num_controllers=${#cont[@]}
            ;;
        i)
            IFS='-' read -ra clus <<< "${OPTARG,,}"
            cluster_id=${OPTARG}
            cluster_name=${clus[0]}
            ;;
        l)
            is_login_node=1
            ;;
        m)
            IFS=',' read -ra sc_args <<< "${OPTARG,,}"
            ;;
        p)
            slurm_state_path=${OPTARG}
            ;;
        s)
            IFS=':' read -ra ss <<< "${OPTARG,,}"
            storage_account=${ss[0]}
            storage_rg=${ss[1]}
            storage_prefix=${ss[2]}
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

execute_command_with_retry() {
    local retries=30
    set +e
    while [ $retries -gt 0 ]; do
        "$@"
        rc=$?
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Command failed: $*"
            exit $rc
        fi
        sleep 1
    done
    set -e
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

install_docker_host_engine() {
    log DEBUG "Installing Docker Host Engine"
    # set vars
    local srvstart="systemctl start docker.service"
    local srvstop="systemctl stop docker.service"
    local srvdisable="systemctl disable docker.service"
    local srvstatus="systemctl --no-pager status docker.service"
    if [ "$PACKAGER" == "apt" ]; then
        local repo=https://download.docker.com/linux/"${DISTRIB_ID}"
        local gpgkey="${repo}"/gpg
        local dockerversion="${DOCKER_CE_PACKAGE_DEBIAN}${DISTRIB_ID}-${DISTRIB_CODENAME}"
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
    # disable docker from auto-start due to temp disk issues
    $srvstop
    $srvdisable
    # ensure docker daemon modifications are idempotent
    rm -rf /var/lib/docker
    mkdir -p /etc/docker
    echo "{ \"data-root\": \"$USER_MOUNTPOINT/docker\", \"hosts\": [ \"unix:///var/run/docker.sock\", \"tcp://127.0.0.1:2375\" ] }" > /etc/docker/daemon.json
    # ensure no options are specified after dockerd
    sed -i 's|^ExecStart=/usr/bin/dockerd.*|ExecStart=/usr/bin/dockerd|' "${SYSTEMD_PATH}"/docker.service
    systemctl daemon-reload
    $srvstart
    $srvstatus
    docker info
    log INFO "Docker Host Engine installed"
}

install_storage_cluster_dependencies() {
    if [ -z "${sc_args[0]}" ]; then
        return
    fi
    log DEBUG "Installing storage cluster dependencies"
    if [ "$PACKAGER" == "zypper" ]; then
        if [[ "$DISTRIB_RELEASE" == 12-sp3* ]]; then
            local repodir=SLE_12_SP3
        fi
        local repo="http://download.opensuse.org/repositories/filesystems/${repodir}/filesystems.repo"
    fi
    for sc_arg in "${sc_args[@]}"; do
        IFS=':' read -ra sc <<< "$sc_arg"
        server_type=${sc[0]}
        if [ "$server_type" == "nfs" ]; then
            if [ "$PACKAGER" == "apt" ]; then
                install_packages nfs-common nfs4-acl-tools
            elif [ "$PACKAGER" == "yum" ] ; then
                install_packages nfs-utils nfs4-acl-tools
                systemctl enable rpcbind
                systemctl start rpcbind
            elif [ "$PACKAGER" == "zypper" ]; then
                install_packages nfs-client nfs4-acl-tools
                systemctl enable rpcbind
                systemctl start rpcbind
            fi
        elif [ "$server_type" == "glusterfs" ]; then
            if [ "$PACKAGER" == "apt" ]; then
                if [ "$DISTRIB_ID" == "debian" ]; then
                    add_repo "http://download.gluster.org/pub/gluster/glusterfs/${GLUSTER_VERSION_DEBIAN}/rsa.pub"
                else
                    add-apt-repository ppa:gluster/glusterfs-${GLUSTER_VERSION_DEBIAN}
                fi
                install_packages glusterfs-client acl
            elif [ "$PACKAGER" == "yum" ] ; then
                install_packages centos-release-gluster${GLUSTER_VERSION_CENTOS}
                install_packages glusterfs-server acl
            elif [ "$PACKAGER" == "zypper" ]; then
                add_repo "$repo"
                "$PACKAGER" -n --gpg-auto-import-keys ref
                install_packages glusterfs acl
            fi
        else
            log ERROR "Unknown file server type ${sc[0]} for ${sc[1]}"
            exit 1
        fi
    done
    log INFO "Storage cluster dependencies installed"
}

process_fstab_entry() {
    local desc=$1
    local fstab_entry=$2
    IFS=' ' read -ra fs <<< "$fstab_entry"
    local mountpoint="${fs[1]}"
    log INFO "Creating host directory for $desc at $mountpoint"
    mkdir -p "$mountpoint"
    chmod 777 "$mountpoint"
    echo "INFO: Adding $mountpoint to fstab"
    echo "$fstab_entry" >> /etc/fstab
    tail -n1 /etc/fstab
    echo "INFO: Mounting $mountpoint"
    local START
    START=$(date -u +"%s")
    set +e
    while :
    do
        if mount "$mountpoint"; then
            break
        else
            local NOW
            NOW=$(date -u +"%s")
            local DIFF=$(((NOW-START)/60))
            # fail after 5 minutes of attempts
            if [ $DIFF -ge 5 ]; then
                echo "ERROR: Could not mount $desc on $mountpoint"
                exit 1
            fi
            sleep 1
        fi
    done
    set -e
    log INFO "$mountpoint mounted."
}

process_storage_clusters() {
    if [ -n "${sc_args[0]}" ]; then
        log DEBUG "Processing storage clusters"
        IFS='#' read -ra fstabs <<< "$SHIPYARD_STORAGE_CLUSTER_FSTAB"
        i=0
        for sc_arg in "${sc_args[@]}"; do
            IFS=':' read -ra sc <<< "$sc_arg"
            fstab_entry="${fstabs[$i]//,noauto/,auto}"
            process_fstab_entry "$sc_arg" "$fstab_entry"
            i=$((i + 1))
        done
        log INFO "Storage clusters processed"
    fi
}

install_systemd_unit_file() {
cat << EOF > /etc/systemd/system/batch-shipyard-slurm.service
[Unit]
Description=Batch Shipyard Slurm Helper
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
TimeoutStartSec=0
Restart=always
LimitNOFILE=65536
LimitCORE=infinity
OOMScoreAdjust=-100
IOSchedulingClass=best-effort
IOSchedulingPriority=0
Environment=LC_CTYPE=en_US.UTF-8 PYTHONIOENCODING=utf-8
WorkingDirectory=/var/batch-shipyard
ExecStart=${SHIPYARD_SLURM_PY} daemon --conf ${SHIPYARD_CONF_FILE}
StandardOutput=null

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    log INFO "systemd unit file installed"
}

create_batch_shipyard_slurm_config() {
    mkdir -p ${SHIPYARD_VAR_DIR}
    chmod 755 ${SHIPYARD_VAR_DIR}
    # get timeouts
    local resume_timeout
    local suspend_timeout
    resume_timeout=$(grep '^ResumeTimeout=' slurm.conf | cut -d '=' -f 2)
    suspend_timeout=$(grep '^SuspendTimeout=' slurm.conf | cut -d '=' -f 2)
cat > ${SHIPYARD_CONF_FILE} << EOF
{
    "aad_cloud": "$aad_cloud",
    "storage": {
        "account": "$storage_account",
        "resource_group": "$storage_rg",
        "entity_prefix": "$storage_prefix",
        "queues": {
            "action": "$cluster_id"
        },
        "azfile_mount_dir": "$AZFILE_MOUNT_DIR"
    },
    "cluster_id": "$cluster_id",
    "cluster_name": "$cluster_name",
    "logging_id": "$HOSTNAME",
    "is_primary": "$is_primary",
    "timeouts": {
        "resume": $resume_timeout,
        "suspend": $suspend_timeout
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

log INFO "Bootstrap start"
echo "Configuration:"
echo "--------------"
echo "OS Distribution: $DISTRIB_ID $DISTRIB_RELEASE $DISTRIB_CODENAME"
echo "Hostname: $HOSTNAME"
echo "Batch Shipyard Version: $shipyardversion"
echo "AAD cloud: $aad_cloud"
echo "Storage: $storage_account:$storage_rg:$storage_prefix"
echo "Storage cluster mounts (${#sc_args[@]}): ${sc_args[*]}"
echo "Cluster Id: $cluster_id"
echo "Cluster Name: $cluster_name"
echo "Cluster user: $cluster_user"
echo "Controllers: $controller_primary backups($controller_secondary,$controller_tertiary)"
echo "Number of controllers: $num_controllers"
echo "Is Primary Controller: $is_primary"
echo "Is Login node: $is_login_node"
echo ""

if [ "$is_primary" -eq 1 ] && [ "$is_login_node" -eq 1 ]; then
    log ERROR "Cannot be designated as primary and login simultaneously"
    exit 1
fi

# check sdb1 mount
check_for_buggy_ntfs_mount

# set sudoers to not require tty
sed -i 's/^Defaults[ ]*requiretty/# Defaults requiretty/g' /etc/sudoers

# install docker
install_docker_host_engine

# install required base software
install_packages build-essential libffi-dev libssl-dev python3-dev
curl -fSsL https://bootstrap.pypa.io/get-pip.py | python3

# check or install dependencies for storage cluster mount
if [ -n "${sc_args[0]}" ]; then
    install_storage_cluster_dependencies
fi
# process and mount storage clusters
process_storage_clusters

# write batch shipyard config
create_batch_shipyard_slurm_config

# align uid/gid/permissions to batch pool
usermod -u 2000 "$cluster_user"
groupmod -n _azbatchgrp "$cluster_user"
chown -R "${cluster_user}:_azbatchgrp" "/home/${cluster_user}"
useradd -o -u 1000 -N -g 1000 -p '!' -s /bin/bash -m -d /home/_azbatch _azbatch

# install program deps and copy main program
pip3 install -r requirements.txt
chmod 755 slurm.py
cp -f slurm.py "$SHIPYARD_SLURM_PY"

# add slurm user
groupadd -g 64030 slurm
useradd -u 64030 -N -g 64030 -p '!' -s /bin/bash -m -d /home/slurm slurm
slurm_uid=$(id -u slurm)
slurm_gid=$(id -g slurm)

# install all slurm-related packages
if [ "$is_login_node" -eq 1 ]; then
    install_packages munge
else
    install_packages munge
    if [ "$is_primary" -eq 1 ]; then
        install_packages mariadb-server libmysqlclient20 libmariadb3
    fi
fi
slurm_docker_image="alfpark/slurm:${SLURM_VERSION}-${DISTRIB_ID}-${DISTRIB_RELEASE}"
docker pull "$slurm_docker_image"
mkdir -p /tmp/slurm
docker run --rm -v /tmp/slurm:/tmp/slurm "$slurm_docker_image" \
    /bin/sh -c 'cp -r /root/* /tmp/slurm/'
dpkg -i "/tmp/slurm/slurm-${SLURM_VERSION}_1.0_amd64.deb"
if [ "$is_login_node" -eq 0 ]; then
    cp /tmp/slurm/slurmctld.service /etc/systemd/system/
    if [ "$is_primary" -eq 1 ]; then
        cp /tmp/slurm/slurmdbd.service /etc/systemd/system/
    fi
fi
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

# retrieve storage account key and endpoint
echo "Retrieving storage account credentials for fileshare"
sa=$(${SHIPYARD_SLURM_PY} sakey --conf "${SHIPYARD_CONF_FILE}")
IFS=' ' read -ra ss <<< "${sa}"
storage_key=${ss[0]}
storage_ep=${ss[1]}
storage_ep="${storage_ep%"${storage_ep##*[![:space:]]}"}"

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
mkdir -p "$azfile_cluster_path"

slurm_log_path="${azfile_cluster_path}/slurm/logs"
mkdir -p "$slurm_log_path"

# create resume/suspend scripts
if [ "$is_login_node" -eq 0 ]; then
    resume_script="${SHIPYARD_VAR_DIR}/resume.sh"
    resume_fail_script="${SHIPYARD_VAR_DIR}/resume-fail.sh"
    suspend_script="${SHIPYARD_VAR_DIR}/suspend.sh"
cat > ${resume_script} << 'EOF'
#!/usr/bin/env bash

hostfile="$(mktemp /tmp/slurm_resume.XXXXXX)"

hosts=$(scontrol show hostnames $1)
touch $hostfile
for host in $hosts; do
    part=$(sinfo -h -n $host -N -o "%R")
    echo "$host $part" >> $hostfile
done

EOF

cat >> ${resume_script} << EOF
${SHIPYARD_SLURM_PY} resume --conf ${SHIPYARD_CONF_FILE} \\
EOF

cat >> ${resume_script} << 'EOF'
    --hostfile $hostfile \
EOF

cat >> ${resume_script} << EOF
    >> ${slurm_log_path}/power-save.log 2>&1
EOF

cat >> ${resume_script} << 'EOF'
ec=$?
rm -f $hostfile
exit $ec
EOF

cat > ${resume_fail_script} << 'EOF'
#!/usr/bin/env bash

hostfile="$(mktemp /tmp/slurm_resume_fail.XXXXXX)"

hosts=$(scontrol show hostnames $1)
touch $hostfile
for host in $hosts; do
    part=$(sinfo -h -n $host -N -o "%R")
    echo "$host $part" >> $hostfile
done

EOF

cat >> ${resume_fail_script} << EOF
${SHIPYARD_SLURM_PY} resume-fail --conf ${SHIPYARD_CONF_FILE} \\
EOF

cat >> ${resume_fail_script} << 'EOF'
    --hostfile $hostfile \
EOF

cat >> ${resume_fail_script} << EOF
    >> ${slurm_log_path}/power-save.log 2>&1
EOF

cat >> ${resume_fail_script} << 'EOF'
ec=$?
rm -f $hostfile
exit $ec
EOF


cat > ${suspend_script} << 'EOF'
#!/usr/bin/env bash

hostfile="$(mktemp /tmp/slurm_resume.XXXXXX)"

scontrol show hostnames $1 > $hostfile
EOF

cat >> ${suspend_script} << EOF
${SHIPYARD_SLURM_PY} suspend --conf ${SHIPYARD_CONF_FILE} \\
EOF

cat >> ${suspend_script} << 'EOF'
    --hostfile $hostfile \
EOF

cat >> ${suspend_script} << EOF
    >> ${slurm_log_path}/power-save.log 2>&1
EOF

cat >> ${suspend_script} << 'EOF'
ec=$?
rm -f $hostfile
exit $ec
EOF

chmod 755 "${resume_script}" "${resume_fail_script}" "${suspend_script}"
fi

chown -R slurm:slurm "${SHIPYARD_VAR_DIR}"

# configure munge
shared_munge_key_path="${azfile_cluster_path}/munge"
shared_munge_key="${shared_munge_key_path}/munge.key"
# export munge key to storage
if [ "$is_primary" -eq 1 ]; then
    munge -n | unmunge
    mkdir -p "$shared_munge_key_path"
    cp -f /etc/munge/munge.key "$shared_munge_key"
    # ensure munge key is "marked" read/write to prevent read-only deletion failures
    chmod 660 "$shared_munge_key"
else
    # poll for munge key
    echo "Waiting for primary munge key"
    while [ ! -s "$shared_munge_key" ]; do
        sleep 1
    done
    cp -f "$shared_munge_key" /etc/munge/munge.key
    chmod 400 /etc/munge/munge.key
    chown munge:munge /etc/munge/munge.key
    munge -n | unmunge
fi
systemctl enable munge
systemctl restart munge
systemctl --no-pager status munge

# start mariadb and prepare database
if [ "$is_primary" -eq 1 ]; then
    systemctl enable mariadb
    systemctl start mariadb
    systemctl --no-pager status mariadb

    # create db table
    chmod 600 slurmdb.sql
    cp slurmdb.sql "${SLURM_CONF_DIR}/"
    # shellcheck disable=SC2002
    cat "${SLURM_CONF_DIR}/slurmdb.sql" | mysql -u root
fi

# copy and modify configuration files
if [ "$is_primary" -eq 1 ]; then
    # create state save location
    mkdir -p "${slurm_state_path}"
    chown -R slurm:slurm "${slurm_state_path}"
    chmod 750 "${slurm_state_path}"

    cp slurm.conf "${SLURM_CONF_DIR}/"
    sed -i "s|{SHIPYARD_VAR_DIR}|${SHIPYARD_VAR_DIR}|g" "${SLURM_CONF_DIR}/slurm.conf"
    sed -i "s|{SLURM_LOG_PATH}|${slurm_log_path}|g" "${SLURM_CONF_DIR}/slurm.conf"
    sed -i "s|{HOSTNAME}|${HOSTNAME}|g" "${SLURM_CONF_DIR}/slurm.conf"
    sed -i "s|{SLURMCTLD_STATE_SAVE_PATH}|${slurm_state_path}|g" "${SLURM_CONF_DIR}/slurm.conf"
    sed -i "s|{SLURMCTLD_HOST_PRIMARY}|${controller_primary}|g" "${SLURM_CONF_DIR}/slurm.conf"
    if [ -n "$controller_secondary" ]; then
        sed -i "s|^#{SLURMCTLD_HOST_SECONDARY}|SlurmctldHost=${controller_secondary}|g" "${SLURM_CONF_DIR}/slurm.conf"
    fi
    if [ -n "$controller_tertiary" ]; then
        sed -i "s|^#{SLURMCTLD_HOST_TERTIARY}|SlurmctldHost=${controller_tertiary}|g" "${SLURM_CONF_DIR}/slurm.conf"
    fi

    cp slurmdbd.conf "${SLURM_CONF_DIR}/"
    sed -i "s|{SLURM_LOG_PATH}|${slurm_log_path}|g" "${SLURM_CONF_DIR}/slurmdbd.conf"
    sed -i "s|{HOSTNAME}|${HOSTNAME}|g" "${SLURM_CONF_DIR}/slurmdbd.conf"

    chown slurm:slurm "${SLURM_CONF_DIR}/slurm.conf"
    chmod 644 "${SLURM_CONF_DIR}/slurm.conf"
    chmod 600 "${SLURM_CONF_DIR}/slurmdbd.conf"
fi

# start slurm db service
if [ "$is_primary" -eq 1 ]; then
    systemctl enable slurmdbd
    systemctl start slurmdbd
    systemctl --no-pager status slurmdbd

    # delay before executing as dbd may not be fully up
    sleep 5

    # initialize account in db
    execute_command_with_retry sacctmgr -i add cluster "$cluster_name"
    execute_command_with_retry sacctmgr -i add account compute-account description="Compute accounts" Organization="$cluster_name"
    execute_command_with_retry sacctmgr -i create user "$cluster_user" account=compute-account adminlevel=None
fi

# copy config and block for secondary/tertiary
# start slurm controller service
slurm_conf_azfile_path="${azfile_cluster_path}/slurm/conf"
if [ "$is_primary" -eq 1 ]; then
    systemctl enable slurmctld
    systemctl start slurmctld
    systemctl --no-pager status slurmctld
    mkdir -p "$slurm_conf_azfile_path"
    cp "${SLURM_CONF_DIR}/slurm.conf" "${slurm_conf_azfile_path}/"
    # ensure slurm conf is "marked" read/write to prevent read-only deletion failures
    chmod 660 "${slurm_conf_azfile_path}/slurm.conf"
else
    echo "Waiting for primary Slurm configuration file"
    while [ ! -s "${slurm_conf_azfile_path}/slurm.conf" ]; do
        sleep 1
    done
    echo "Slurm configuration file found."
    cp -f "${slurm_conf_azfile_path}/slurm.conf" "${SLURM_CONF_DIR}/slurm.conf"
    chown slurm:slurm "${SLURM_CONF_DIR}/slurm.conf"
    chmod 644 "${SLURM_CONF_DIR}/slurm.conf"
    if [ "$is_login_node" -eq 0 ]; then
        systemctl enable slurmctld
        systemctl start slurmctld
        systemctl --no-pager status slurmctld
    fi
fi

# start daemon
if [ "$is_login_node" -eq 0 ]; then
    # setup systemd unit file
    install_systemd_unit_file

    # start batch shipyard slurm daemon mode
    systemctl enable batch-shipyard-slurm
    systemctl start batch-shipyard-slurm
    systemctl --no-pager status batch-shipyard-slurm
fi

log INFO "Bootstrap completed"
