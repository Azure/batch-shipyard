#!/usr/bin/env bash

set -e
set -o pipefail

# globals
azurefile=0
blobxferversion=latest
encrypted=
gluster_on_compute=0
networkopt=0
sc_args=
version=

# process command line options
while getopts "h?aef:m:nv:x:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_nodeprep_nativedocker.sh parameters"
            echo ""
            echo "-a install azurefile docker volume driver"
            echo "-e [thumbprint] encrypted credentials with cert"
            echo "-f set up glusterfs on compute"
            echo "-m [type:scid] mount storage cluster"
            echo "-n optimize network TCP settings"
            echo "-v [version] batch-shipyard version"
            echo "-x [blobxfer version] blobxfer version"
            echo ""
            exit 1
            ;;
        a)
            azurefile=1
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

contains() {
    string="$1"
    substring="$2"
    if test "${string#*$substring}" != "$string"; then
        return 0
    else
        return 1
    fi
}

check_for_buggy_ntfs_mount() {
    # Check to ensure sdb1 mount is not mounted as ntfs
    set +e
    mount | grep /dev/sdb1 | grep fuseblk
    if [ $? -eq 0 ]; then
        echo "ERROR: /dev/sdb1 temp disk is mounted as fuseblk/ntfs"
        exit 1
    fi
    set -e
}

optimize_tcp_network_settings() {
    sysctlfile=/etc/sysctl.d/60-azure-batch-shipyard.conf
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

check_for_nvidia_docker() {
    set +e
    nvidia-docker --version
    if [ $? -ne 0 ]; then
        echo "ERROR: nvidia-docker not installed"
        exit 1
    fi
    set -e
}

check_for_nvidia_driver() {
    set +e
    out=$(lsmod)
    echo "$out" | grep -i nvidia > /dev/null
    rc=$?
    set -e
    echo "$out"
    if [ $rc -ne 0 ]; then
        echo "ERROR: No Nvidia drivers detected!"
        exit 1
    else
        check_for_nvidia_docker
    fi
}

check_for_nvidia() {
    # first check for card
    set +e
    out=$(lspci)
    echo "$out" | grep -i nvidia > /dev/null
    rc=$?
    set -e
    echo "$out"
    if [ $rc -ne 0 ]; then
        echo "INFO: No Nvidia card(s) detected!"
    else
        check_for_nvidia_driver
    fi
}

check_docker_root_dir() {
    set +e
    rootdir=$(docker info | grep "Docker Root Dir" | cut -d' ' -f 4)
    set -e
    echo "$rootdir"
    if [ -z "$rootdir" ]; then
        echo "ERROR: could not determine docker graph root"
    elif [[  "$rootdir" == /mnt/* && "$1" == "ubuntu" ]] || [[ "$rootdir" == /mnt/resource/* && "$1" != "ubuntu" ]]; then
        echo "INFO: docker root is within ephemeral temp disk"
    else
        echo "WARNING: docker graph root is on the OS disk. Performance may be impacted."
    fi
}

check_for_docker_host_engine() {
    set +e
    docker --version
    if [ $? -ne 0 ]; then
        echo "ERROR: Docker not installed"
        exit 1
    fi
    set -e
}

install_azurefile_docker_volume_driver() {
    chown root:root azurefile-dockervolumedriver*
    chmod 755 azurefile-dockervolumedriver
    chmod 640 azurefile-dockervolumedriver.env
    mv azurefile-dockervolumedriver /usr/bin
    mv azurefile-dockervolumedriver.env /etc/default/azurefile-dockervolumedriver
    if [[ "$1" == "ubuntu" ]] && [[ "$2" == 14.04* ]]; then
        mv azurefile-dockervolumedriver.conf /etc/init
        initctl reload-configuration
        initctl start azurefile-dockervolumedriver
    else
        if [[ "$1" == "opensuse" ]] || [[ "$1" == "sles" ]]; then
            systemdloc=/usr/lib/systemd/system
        else
            systemdloc=/lib/systemd/system
        fi
        mv azurefile-dockervolumedriver.service $systemdloc
        systemctl daemon-reload
        systemctl enable azurefile-dockervolumedriver
        systemctl start azurefile-dockervolumedriver
    fi
    # create docker volumes
    chmod +x azurefile-dockervolume-create.sh
    ./azurefile-dockervolume-create.sh
}

docker_pull_image() {
    image=$1
    set +e
    retries=60
    while [ $retries -gt 0 ]; do
        pull_out=$(docker pull $image 2>&1)
        rc=$?
        if [ $rc -eq 0 ]; then
            echo "$pull_out"
            break
        fi
        # non-zero exit code: check if pull output has toomanyrequests or
        # connection resets
        if [ contains "$pull_out" "toomanyrequests" ] || [ contains "$pull_out" "connection reset by peer" ]; then
            echo "WARNING: will retry:\n$pull_out"
        else
            echo "ERROR:\n$pull_out"
            exit $rc
        fi
        let retries=retries-1
        if [ $retries -le 0 ]; then
            echo "ERROR: Could not pull docker image: $image"
            exit $rc
        fi
        sleep $[($RANDOM % 5) + 1]s
    done
    set -e
}

install_packages() {
    distrib=$1
    shift
    set +e
    retries=30
    while [ $retries -gt 0 ]; do
        if [[ $distrib == "ubuntu" ]]; then
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends $*
        elif [[ $distrib == centos* ]]; then
            yum install -y $*
        fi
        if [ $? -eq 0 ]; then
            break
        fi
        let retries=retries-1
        if [ $retries -eq 0 ]; then
            echo "ERROR: Could not install packages: $*"
            exit 1
        fi
        sleep 1
    done
    set -e
}

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
echo "Network optimization: $networkopt"
echo "Encrypted: $encrypted"
echo "Storage cluster mount: ${sc_args[*]}"
echo "Azure File: $azurefile"
echo "GlusterFS on compute: $gluster_on_compute"

# check sdb1 mount
check_for_buggy_ntfs_mount

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
cascadefailed=$AZ_BATCH_NODE_SHARED_DIR/.cascade_failed

# get ip address of eth0
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

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

# check if we're coming up from a reboot
if [ -f $nodeprepfinished ]; then
    echo "$nodeprepfinished file exists, assuming successful completion of node prep"
    exit 0
fi

# one-time setup
if [ ! -f $nodeprepfinished ] && [ $networkopt -eq 1 ]; then
    # do not fail script if this function fails
    set +e
    optimize_tcp_network_settings $DISTRIB_ID $DISTRIB_RELEASE
    set -e
fi

# check for docker host engine
check_for_docker_host_engine
check_docker_root_dir $DISTRIB_ID

# check for nvidia card/driver/docker
check_for_nvidia

# install azurefile docker volume driver
if [ $azurefile -eq 1 ]; then
    install_azurefile_docker_volume_driver $DISTRIB_ID $DISTRIB_RELEASE
fi

# install gluster on compute
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

# install storage cluster software
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
                echo "ERROR: Unknown file server type ${sc[0]} for ${sc[1]}"
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
                echo "ERROR: Unknown file server type ${sc[0]} for ${sc[1]}"
                exit 1
            fi
        done
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
        mountpoint=$AZ_BATCH_NODE_SHARED_DIR/${sc[1]}
        echo "Creating host directory for storage cluster $sc_arg at $mountpoint"
        mkdir -p $mountpoint
        chmod 777 $mountpoint
        echo "Adding $mountpoint to fstab"
        # eval fstab var to expand vars (this is ok since it is set by shipyard)
        fstab_entry="${fstabs[$i]}"
        echo $fstab_entry >> /etc/fstab
        tail -n1 /etc/fstab
        echo "Mounting $mountpoint"
        START=$(date -u +"%s")
        set +e
        while :
        do
            mount $mountpoint
            if [ $? -eq 0 ]; then
                break
            else
                NOW=$(date -u +"%s")
                DIFF=$((($NOW-$START)/60))
                # fail after 5 minutes of attempts
                if [ $DIFF -ge 5 ]; then
                    echo "Could not mount storage cluster $sc_arg on: $mountpoint"
                    exit 1
                fi
                sleep 1
            fi
        done
        set -e
        echo "$mountpoint mounted."
        i=$(($i + 1))
    done
fi

# retrieve docker images related to data movement
docker_pull_image alfpark/blobxfer:$blobxferversion
docker_pull_image alfpark/batch-shipyard:tfm-$version
docker_pull_image alfpark/batch-shipyard:rjm-$version

# login to registry servers (do not specify -e as creds have been decrypted)
./registry_login.sh

# touch node prep finished file to preserve idempotency
touch $nodeprepfinished
