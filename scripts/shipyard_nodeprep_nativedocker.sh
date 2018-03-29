#!/usr/bin/env bash

set -e
set -o pipefail

log() {
    local level=$1
    shift
    echo "$(date -u -Ins) - $level - $*"
}

# consts
MOUNTS_PATH=$AZ_BATCH_NODE_ROOT_DIR/mounts

# globals
azurefile=0
azureblob=0
blobxferversion=latest
custom_image=0
encrypted=
gluster_on_compute=0
networkopt=0
sc_args=
version=

# process command line options
while getopts "h?acef:m:nuv:x:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_nodeprep_nativedocker.sh parameters"
            echo ""
            echo "-a mount azurefile shares"
            echo "-c mount azureblob containers"
            echo "-e [thumbprint] encrypted credentials with cert"
            echo "-f set up glusterfs on compute"
            echo "-m [type:scid] mount storage cluster"
            echo "-n optimize network TCP settings"
            echo "-u custom image"
            echo "-v [version] batch-shipyard version"
            echo "-x [blobxfer version] blobxfer version"
            echo ""
            exit 1
            ;;
        a)
            azurefile=1
            ;;
        c)
            azureblob=1
            ;;
        e)
            encrypted=${OPTARG,,}
            ;;
        f)
            gluster_on_compute=1
            ;;
        m)
            IFS=',' read -ra sc_args <<< "${OPTARG,,}"
            ;;
        n)
            networkopt=1
            ;;
        u)
            custom_image=1
            ;;
        v)
            version=$OPTARG
            ;;
        x)
            blobxferversion=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

check_for_buggy_ntfs_mount() {
    # Check to ensure sdb1 mount is not mounted as ntfs
    set +e
    mount | grep /dev/sdb1 | grep fuseblk
    if [ $? -eq 0 ]; then
        log ERROR "/dev/sdb1 temp disk is mounted as fuseblk/ntfs"
        exit 1
    fi
    set -e
}

save_startup_to_volatile() {
    set +e
    touch $AZ_BATCH_NODE_ROOT_DIR/volatile/startup/.save
    set -e
}

optimize_tcp_network_settings() {
    local sysctlfile=/etc/sysctl.d/60-azure-batch-shipyard.conf
    if [ ! -e $sysctlfile ] || [ ! -s $sysctlfile ]; then
cat > $sysctlfile << EOF
net.core.rmem_default=16777216
net.core.wmem_default=16777216
net.core.rmem_max=16777216
net.core.wmem_max=16777216
net.core.netdev_max_backlog=30000
net.ipv4.tcp_max_syn_backlog=80960
net.ipv4.tcp_mem=16777216 16777216 16777216
net.ipv4.tcp_rmem=4096 87380 16777216
net.ipv4.tcp_wmem=4096 65536 16777216
net.ipv4.tcp_slow_start_after_idle=0
net.ipv4.tcp_tw_reuse=1
net.ipv4.tcp_abort_on_overflow=1
net.ipv4.route.flush=1
EOF
    fi
    if [ "$1" == "ubuntu" ] && [ "$2" == 14.04* ]; then
        service procps start
    else
        service procps reload
    fi
}

blacklist_kernel_upgrade() {
    local offer=$1
    shift
    local sku=$1
    shift
    if [ $offer != "ubuntu" ]; then
        log DEBUG "No kernel upgrade blacklist required on $offer $sku"
        return
    fi
    set +e
    grep linux-azure /etc/apt/apt.conf.d/50unattended-upgrades
    local rc=$?
    set -e
    if [ $rc -ne 0 ]; then
        sed -i "/^Unattended-Upgrade::Package-Blacklist {/alinux-azure\nlinux-cloud-tools-azure\nlinux-headers-azure\nlinux-image-azure\nlinux-tools-azure" /etc/apt/apt.conf.d/50unattended-upgrades
        log INFO "Added linux-azure to package blacklist for unattended upgrades"
    fi
}

check_for_nvidia_docker() {
    set +e
    nvidia-docker version
    if [ $? -ne 0 ]; then
        log ERROR "nvidia-docker2 not installed"
        exit 1
    fi
    set -e
}

check_for_nvidia_driver() {
    set +e
    local out=$(lsmod)
    echo "$out" | grep -i nvidia > /dev/null
    local rc=$?
    set -e
    echo "$out"
    if [ $rc -ne 0 ]; then
        log ERROR "No Nvidia drivers detected!"
        exit 1
    else
        check_for_nvidia_docker
    fi
}

check_for_nvidia() {
    log INFO "Checking for Nvidia Hardware"
    # first check for card
    set +e
    local out=$(lspci)
    echo "$out" | grep -i nvidia > /dev/null
    local rc=$?
    set -e
    echo "$out"
    if [ $rc -ne 0 ]; then
        log INFO "No Nvidia card(s) detected!"
    else
        blacklist_kernel_upgrade $1 $2
        check_for_nvidia_driver
        # enable persistence mode
        nvidia-smi -pm 1
        nvidia-smi
    fi
}

check_docker_root_dir() {
    set +e
    local rootdir=$(docker info | grep "Docker Root Dir" | cut -d' ' -f 4)
    set -e
    log DEBUG "Graph root: $rootdir"
    if [ -z "$rootdir" ]; then
        log ERROR "could not determine docker graph root"
    elif [[  "$rootdir" == /mnt/* && "$1" == "ubuntu" ]] || [[ "$rootdir" == /mnt/resource/* && "$1" != "ubuntu" ]]; then
        log INFO "docker root is within ephemeral temp disk"
    else
        log WARNING "docker graph root is on the OS disk. Performance may be impacted."
    fi
}

check_for_docker_host_engine() {
    set +e
    # enable and start docker service if custom image
    if [ $custom_image -eq 1 ]; then
        docker version --format '{{.Server.Version}}'
        if [ $? -ne 0 ]; then
            systemctl start docker.service
        fi
    fi
    systemctl status docker.service
    docker version --format '{{.Server.Version}}'
    if [ $? -ne 0 ]; then
        log ERROR "Docker not installed"
        exit 1
    fi
    set -e
    docker info
}

mount_azurefile_share() {
    log INFO "Mounting Azure File Shares"
    chmod +x azurefile-mount.sh
    ./azurefile-mount.sh
    chmod 700 azurefile-mount.sh
    chown root:root azurefile-mount.sh
}

docker_pull_image() {
    local image=$1
    log DEBUG "Pulling Docker Image: $1"
    set +e
    local retries=60
    while [ $retries -gt 0 ]; do
        local pull_out=$(docker pull $image 2>&1)
        local rc=$?
        if [ $rc -eq 0 ]; then
            echo "$pull_out"
            break
        fi
        # non-zero exit code: check if pull output has toomanyrequests,
        # connection resets, or image config error
        if [[ ! -z "$(grep 'toomanyrequests' <<<$pull_out)" ]] || [[ ! -z "$(grep 'connection reset by peer' <<<$pull_out)" ]] || [[ ! -z "$(grep 'error pulling image configuration' <<<$pull_out)" ]]; then
            log WARNING "will retry: $pull_out"
        else
            log ERROR "$pull_out"
            exit $rc
        fi
        retries=retries-1
        if [ $retries -le 0 ]; then
            log ERROR "Could not pull docker image: $image"
            exit $rc
        fi
        sleep $[($RANDOM % 5) + 1]s
    done
    set -e
}

install_local_packages() {
    local distrib=$1
    shift
    set +e
    local retries=120
    while [ $retries -gt 0 ]; do
        if [[ $distrib == "ubuntu" ]]; then
            dpkg -i $*
        else
            rpm -Uvh --nodeps $*
        fi
        if [ $? -eq 0 ]; then
            break
        fi
        retries=retries-1
        if [ $retries -eq 0 ]; then
            log ERROR "Could not install local packages: $*"
            exit 1
        fi
        sleep 1
    done
    set -e
}

install_packages() {
    local distrib=$1
    shift
    set +e
    local retries=30
    while [ $retries -gt 0 ]; do
        if [[ $distrib == "ubuntu" ]]; then
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends $*
        elif [[ $distrib == centos* ]]; then
            yum install -y $*
        fi
        if [ $? -eq 0 ]; then
            break
        fi
        retries=retries-1
        if [ $retries -eq 0 ]; then
            log ERROR "Could not install packages: $*"
            exit 1
        fi
        sleep 1
    done
    set -e
}

refresh_package_index() {
    local distrib=$1
    set +e
    local retries=120
    while [ $retries -gt 0 ]; do
        if [[ $distrib == "ubuntu" ]]; then
            apt-get update
        elif [[ $distrib == centos* ]]; then
            yum makecache -y fast
        else
            log ERROR "Unknown distribution for refresh: $distrib"
            exit 1
        fi
        if [ $? -eq 0 ]; then
            break
        fi
        retries=retries-1
        if [ $retries -eq 0 ]; then
            log ERROR "Could not update package index"
            exit 1
        fi
        sleep 1
    done
    set -e
}

mount_azureblob_container() {
    log INFO "Mounting Azure Blob Containers"
    local distrib=$1
    local release=$2
    if [ $distrib == "ubuntu" ]; then
        local debfile=packages-microsoft-prod.deb
        if [ ! -f ${debfile} ]; then
            download_file https://packages.microsoft.com/config/ubuntu/16.04/${debfile}
            install_local_packages $distrib ${debfile}
            refresh_package_index $distrib
            install_packages $distrib blobfuse
        fi
    elif [[ $distrib == centos* ]]; then
        local rpmfile=packages-microsoft-prod.rpm
        if [ ! -f ${rpmfile} ]; then
            download_file https://packages.microsoft.com/config/rhel/7/${rpmfile}
            install_local_packages $distrib ${rpmfile}
            refresh_package_index $distrib
            install_packages $distrib blobfuse
        fi
    else
        log ERROR "unsupported distribution for Azure blob: $distrib $release"
        exit 1
    fi
    chmod +x azureblob-mount.sh
    ./azureblob-mount.sh
    chmod 700 azureblob-mount.sh
    chown root:root azureblob-mount.sh
    chmod 600 *.cfg
    chown root:root *.cfg
}

download_file() {
    log INFO "Downloading: $1"
    local retries=10
    set +e
    while [ $retries -gt 0 ]; do
        curl -fSsLO $1
        if [ $? -eq 0 ]; then
            break
        fi
        retries=retries-1
        if [ $retries -eq 0 ]; then
            log ERROR "Could not download: $1"
            exit 1
        fi
        sleep 1
    done
    set -e
}

process_fstab_entry() {
    local desc=$1
    local mountpoint=$2
    local fstab_entry=$3
    log INFO "Creating host directory for $desc at $mountpoint"
    mkdir -p $mountpoint
    chmod 777 $mountpoint
    log INFO "Adding $mountpoint to fstab"
    echo $fstab_entry >> /etc/fstab
    tail -n1 /etc/fstab
    log INFO "Mounting $mountpoint"
    local START=$(date -u +"%s")
    set +e
    while :
    do
        mount $mountpoint
        if [ $? -eq 0 ]; then
            break
        else
            local NOW=$(date -u +"%s")
            local DIFF=$((($NOW-$START)/60))
            # fail after 5 minutes of attempts
            if [ $DIFF -ge 5 ]; then
                log ERROR "Could not mount $desc on $mountpoint"
                exit 1
            fi
            sleep 1
        fi
    done
    set -e
    log INFO "$mountpoint mounted."
}

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

# lowercase vars
DISTRIB_ID=${DISTRIB_ID,,}
DISTRIB_RELEASE=${DISTRIB_RELEASE,,}

echo "Configuration [Native Docker]:"
echo "------------------------------"
echo "Batch Shipyard version: $version"
echo "Blobxfer version: $blobxferversion"
echo "Distrib ID/Release: $DISTRIB_ID $DISTRIB_RELEASE"
echo "Custom image: $custom_image"
echo "Network optimization: $networkopt"
echo "Encrypted: $encrypted"
echo "Storage cluster mount: ${sc_args[*]}"
echo "Custom mount: $SHIPYARD_CUSTOM_MOUNTS_FSTAB"
echo "Azure File: $azurefile"
echo "Azure Blob: $azureblob"
echo "GlusterFS on compute: $gluster_on_compute"
echo ""
log INFO "Prep start"

# check sdb1 mount
check_for_buggy_ntfs_mount

# save startup stderr/stdout
save_startup_to_volatile

# set python env vars
LC_ALL=en_US.UTF-8
PYTHONASYNCIODEBUG=1

# store node prep start
if command -v python3 > /dev/null 2>&1; then
    npstart=`python3 -c 'import datetime;print(datetime.datetime.utcnow().timestamp())'`
else
    npstart=`python -c 'import datetime;import time;print(time.mktime(datetime.datetime.utcnow().timetuple()))'`
fi

# set node prep status files
nodeprepfinished=$AZ_BATCH_NODE_SHARED_DIR/.node_prep_finished

# create shared mount points
mkdir -p $MOUNTS_PATH

# decrypt encrypted creds
if [ ! -z $encrypted ]; then
    # convert pfx to pem
    pfxfile=$AZ_BATCH_CERTIFICATES_DIR/sha1-$encrypted.pfx
    privatekey=$AZ_BATCH_CERTIFICATES_DIR/key.pem
    openssl pkcs12 -in $pfxfile -out $privatekey -nodes -password file:$pfxfile.pw
    # remove pfx-related files
    rm -f $pfxfile $pfxfile.pw
    # decrypt creds
    if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
        DOCKER_LOGIN_PASSWORD=`echo $DOCKER_LOGIN_PASSWORD | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
    fi
fi

# check for docker host engine
check_for_docker_host_engine
check_docker_root_dir $DISTRIB_ID

# check for nvidia card/driver/docker
check_for_nvidia $DISTRIB_ID $DISTRIB_RELEASE

# mount azure resources (this must be done every boot)
if [ $azurefile -eq 1 ]; then
    mount_azurefile_share $DISTRIB_ID $DISTRIB_RELEASE
fi
if [ $azureblob -eq 1 ]; then
    mount_azureblob_container $DISTRIB_ID $DISTRIB_RELEASE
fi

# check if we're coming up from a reboot
if [ -f $nodeprepfinished ]; then
    # mount any storage clusters
    if [ ! -z $sc_args ]; then
        # eval and split fstab var to expand vars (this is ok since it is set by shipyard)
        fstab_mounts=$(eval echo "$SHIPYARD_STORAGE_CLUSTER_FSTAB")
        IFS='#' read -ra fstabs <<< "$fstab_mounts"
        i=0
        for sc_arg in ${sc_args[@]}; do
            IFS=':' read -ra sc <<< "$sc_arg"
            mount $MOUNTS_PATH/${sc[1]}
        done
    fi
    # mount any custom mounts
    if [ ! -z "$SHIPYARD_CUSTOM_MOUNTS_FSTAB" ]; then
        IFS='#' read -ra fstab_mounts <<< "$SHIPYARD_CUSTOM_MOUNTS_FSTAB"
        for fstab in "${fstab_mounts[@]}"; do
            # eval and split fstab var to expand vars
            fstab_entry=$(eval echo "$fstab")
            IFS=' ' read -ra parts <<< "$fstab_entry"
            mount ${parts[1]}
        done
    fi
    log INFO "$nodeprepfinished file exists, assuming successful completion of node prep"
    exit 0
fi

# one-time setup
if [ $networkopt -eq 1 ]; then
    # do not fail script if this function fails
    set +e
    optimize_tcp_network_settings $DISTRIB_ID $DISTRIB_RELEASE
    set -e
    # set sudoers to not require tty
    sed -i 's/^Defaults[ ]*requiretty/# Defaults requiretty/g' /etc/sudoers
fi

# install gluster on compute software
if [ $custom_image -eq 0 ]; then
    if [ $gluster_on_compute -eq 1 ]; then
        if [ $DISTRIB_ID == "ubuntu" ]; then
            install_packages $DISTRIB_ID glusterfs-server
            systemctl enable glusterfs-server
            systemctl start glusterfs-server
            # create brick directory
            mkdir -p /mnt/gluster
        elif [[ $DISTRIB_ID == centos* ]]; then
            install_packages $DISTRIB_ID epel-release centos-release-gluster38
            sed -i -e "s/enabled=1/enabled=0/g" /etc/yum.repos.d/CentOS-Gluster-3.8.repo
            install_packages $DISTRIB_ID --enablerepo=centos-gluster38,epel glusterfs-server
            systemctl daemon-reload
            chkconfig glusterd on
            systemctl start glusterd
            # create brick directory
            mkdir -p /mnt/resource/gluster
        fi
    fi
fi

# install storage cluster software
if [ $custom_image -eq 0 ]; then
    if [ ! -z $sc_args ]; then
        if [ $DISTRIB_ID == "ubuntu" ]; then
            for sc_arg in ${sc_args[@]}; do
                IFS=':' read -ra sc <<< "$sc_arg"
                server_type=${sc[0]}
                if [ $server_type == "nfs" ]; then
                    install_packages $DISTRIB_ID nfs-common nfs4-acl-tools
                elif [ $server_type == "glusterfs" ]; then
                    install_packages $DISTRIB_ID glusterfs-client acl
                else
                    log ERROR "Unknown file server type ${sc[0]} for ${sc[1]}"
                    exit 1
                fi
            done
        elif [[ $DISTRIB_ID == centos* ]]; then
            for sc_arg in ${sc_args[@]}; do
                IFS=':' read -ra sc <<< "$sc_arg"
                server_type=${sc[0]}
                if [ $server_type == "nfs" ]; then
                    install_packages $DISTRIB_ID nfs-utils nfs4-acl-tools
                    systemctl daemon-reload
                    systemctl enable rpcbind
                    systemctl start rpcbind
                elif [ $server_type == "glusterfs" ]; then
                    install_packages $DISTRIB_ID epel-release centos-release-gluster38
                    sed -i -e "s/enabled=1/enabled=0/g" /etc/yum.repos.d/CentOS-Gluster-3.8.repo
                    install_packages $DISTRIB_ID --enablerepo=centos-gluster38,epel glusterfs-server acl
                else
                    log ERROR "Unknown file server type ${sc[0]} for ${sc[1]}"
                    exit 1
                fi
            done
        fi
    fi
fi

# mount any storage clusters
if [ ! -z $sc_args ]; then
    # eval and split fstab var to expand vars (this is ok since it is set by shipyard)
    fstab_mounts=$(eval echo "$SHIPYARD_STORAGE_CLUSTER_FSTAB")
    IFS='#' read -ra fstabs <<< "$fstab_mounts"
    i=0
    for sc_arg in ${sc_args[@]}; do
        IFS=':' read -ra sc <<< "$sc_arg"
        fstab_entry="${fstabs[$i]}"
        process_fstab_entry "$sc_arg" "$MOUNTS_PATH/${sc[1]}" "$fstab_entry"
        i=$(($i + 1))
    done
fi

# mount any custom mounts
if [ ! -z "$SHIPYARD_CUSTOM_MOUNTS_FSTAB" ]; then
    IFS='#' read -ra fstab_mounts <<< "$SHIPYARD_CUSTOM_MOUNTS_FSTAB"
    for fstab in "${fstab_mounts[@]}"; do
        # eval and split fstab var to expand vars
        fstab_entry=$(eval echo "$fstab")
        IFS=' ' read -ra parts <<< "$fstab_entry"
        process_fstab_entry "${parts[2]}" "${parts[1]}" "$fstab_entry"
    done
fi

# retrieve docker images related to data movement
docker_pull_image alfpark/blobxfer:$blobxferversion
docker_pull_image alfpark/batch-shipyard:${version}-cargo

# login to registry servers (do not specify -e as creds have been decrypted)
./registry_login.sh
# delete singularity login info as it's not compatible
if [ -f singularity-registry-login ]; then
    rm -f singularity-registry-login
fi

# touch node prep finished file to preserve idempotency
touch $nodeprepfinished
