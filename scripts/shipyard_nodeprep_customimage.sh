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
SINGULARITY_VERSION=2.4.4

# globals
azureblob=0
azurefile=0
blobxferversion=latest
block=
encrypted=
gluster_on_compute=0
networkopt=0
p2p=
p2penabled=0
prefix=
sc_args=
version=

# process command line options
while getopts "h?abcef:m:np:t:v:x:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_nodeprep_customimage.sh parameters"
            echo ""
            echo "-a mount azurefile shares"
            echo "-b block until resources loaded"
            echo "-c mount azureblob containers"
            echo "-e [thumbprint] encrypted credentials with cert"
            echo "-f set up glusterfs on compute"
            echo "-m [type:scid] mount storage cluster"
            echo "-n optimize network TCP settings"
            echo "-p [prefix] storage container prefix"
            echo "-t [enabled:non-p2p concurrent download:seed bias:compression] p2p sharing"
            echo "-v [version] batch-shipyard version"
            echo "-x [blobxfer version] blobxfer version"
            echo ""
            exit 1
            ;;
        a)
            azurefile=1
            ;;
        b)
            block=${SHIPYARD_CONTAINER_IMAGES_PRELOAD}
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
        p)
            prefix="--prefix $OPTARG"
            ;;
        t)
            p2p=${OPTARG,,}
            IFS=':' read -ra p2pflags <<< "$p2p"
            if [ ${p2pflags[0]} == "true" ]; then
                p2penabled=1
            else
                p2penabled=0
            fi
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
    nvidia-docker version
    if [ $? -ne 0 ]; then
        log ERROR "nvidia-docker2 not installed"
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
    out=$(lspci)
    echo "$out" | grep -i nvidia > /dev/null
    rc=$?
    set -e
    echo "$out"
    if [ $rc -ne 0 ]; then
        log INFO "No Nvidia card(s) detected!"
    else
        check_for_nvidia_driver
        # enable persistence mode
        nvidia-smi -pm 1
        nvidia-smi
    fi
}

check_docker_root_dir() {
    set +e
    rootdir=$(docker info | grep "Docker Root Dir" | cut -d' ' -f 4)
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
    # start docker service
    systemctl start docker.service
    systemctl status docker.service
    docker version
    if [ $? -ne 0 ]; then
        log ERROR "Docker not installed"
        exit 1
    fi
    set -e
    docker info
}

check_for_glusterfs_on_compute() {
    set +e
    gluster
    rc0=$?
    glusterfs -V
    rc1=$?
    set -e
    if [ $rc0 -ne 0 ] || [ $rc1 -ne 0 ]; then
        log ERROR "gluster server and client not installed"
        exit 1
    fi
}

check_for_storage_cluster_software() {
    rc=0
    if [ ! -z $sc_args ]; then
        for sc_arg in ${sc_args[@]}; do
            IFS=':' read -ra sc <<< "$sc_arg"
            server_type=${sc[0]}
            if [ $server_type == "nfs" ]; then
                set +e
                mount.nfs4 -V
                rc=$?
                set -e
            elif [ $server_type == "glusterfs" ]; then
                set +e
                glusterfs -V
                rc=$?
                set -e
            else
                log ERROR "Unknown file server type ${sc[0]} for ${sc[1]}"
                exit 1
            fi
        done
    fi
    if [ $rc -ne 0 ]; then
        log ERROR "required storage cluster software to mount $sc_args not installed"
        exit 1
    fi
}

mount_azurefile_share() {
    log INFO "Mounting Azure File Shares"
    chmod +x azurefile-mount.sh
    ./azurefile-mount.sh
    chmod 700 azurefile-mount.sh
    chown root:root azurefile-mount.sh
}

mount_azureblob_container() {
    log INFO "Mounting Azure Blob Containers"
    chmod +x azureblob-mount.sh
    ./azureblob-mount.sh
    chmod 700 azureblob-mount.sh
    chown root:root azureblob-mount.sh
    chmod 600 *.cfg
    chown root:root *.cfg
}

docker_pull_image() {
    image=$1
    log DEBUG "Pulling Docker Image: $1"
    set +e
    retries=60
    while [ $retries -gt 0 ]; do
        pull_out=$(docker pull $image 2>&1)
        rc=$?
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
        let retries=retries-1
        if [ $retries -le 0 ]; then
            log ERROR "Could not pull docker image: $image"
            exit $rc
        fi
        sleep $[($RANDOM % 5) + 1]s
    done
    set -e
}

singularity_basedir=
singularity_setup() {
    offer=$1
    shift
    sku=$1
    shift
    if [ $offer == "ubuntu" ]; then
        if [[ $sku != 16.04* ]]; then
            log WARNING "Singularity not supported on $offer $sku"
            return
        fi
        singularity_basedir=/mnt/singularity
    elif [[ $offer == "centos" ]] || [[ $offer == "rhel" ]]; then
        if [[ $sku != 7* ]]; then
            log WARNING "Singularity not supported on $offer $sku"
            return
        fi
        singularity_basedir=/mnt/resource/singularity
        offer=centos
        sku=7
    else
        log WARNING "Singularity not supported on $offer $sku"
        return
    fi
    log DEBUG "Setting up Singularity for $offer $sku"
    # fetch docker image for singularity bits
    di=alfpark/singularity:${SINGULARITY_VERSION}-${offer}-${sku}
    docker_pull_image $di
    mkdir -p /opt/singularity
    docker run --rm -v /opt/singularity:/opt/singularity $di \
        /bin/sh -c 'cp -r /singularity/* /opt/singularity'
    # symlink for global exec
    ln -sf /opt/singularity/bin/singularity /usr/bin/singularity
    # fix perms
    chown root.root /opt/singularity/libexec/singularity/bin/*
    chmod 4755 /opt/singularity/libexec/singularity/bin/*-suid
    # prep singularity root/container dir
    mkdir -p $singularity_basedir/mnt/container
    mkdir -p $singularity_basedir/mnt/final
    mkdir -p $singularity_basedir/mnt/overlay
    mkdir -p $singularity_basedir/mnt/session
    chmod 755 $singularity_basedir
    chmod 755 $singularity_basedir/mnt
    chmod 755 $singularity_basedir/mnt/container
    chmod 755 $singularity_basedir/mnt/final
    chmod 755 $singularity_basedir/mnt/overlay
    chmod 755 $singularity_basedir/mnt/session
    # create singularity tmp/cache paths
    mkdir -p $singularity_basedir/tmp
    mkdir -p $singularity_basedir/cache/docker
    mkdir -p $singularity_basedir/cache/metadata
    chmod 775 $singularity_basedir/tmp
    chmod 775 $singularity_basedir/cache
    chmod 775 $singularity_basedir/cache/docker
    chmod 775 $singularity_basedir/cache/metadata
    # set proper ownership
    chown -R _azbatch:_azbatchgrp $singularity_basedir/tmp
    chown -R _azbatch:_azbatchgrp $singularity_basedir/cache
    # selftest
    singularity selftest
    # remove docker image
    docker rmi $di
}

process_fstab_entry() {
    desc=$1
    mountpoint=$2
    fstab_entry=$3
    log INFO "Creating host directory for $desc at $mountpoint"
    mkdir -p $mountpoint
    chmod 777 $mountpoint
    log INFO "Adding $mountpoint to fstab"
    echo $fstab_entry >> /etc/fstab
    tail -n1 /etc/fstab
    log INFO "Mounting $mountpoint"
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

echo "Configuration [Custom Image]:"
echo "-----------------------------"
echo "Batch Shipyard version: $version"
echo "Blobxfer version: $blobxferversion"
echo "Distrib ID/Release: $DISTRIB_ID $DISTRIB_RELEASE"
echo "Network optimization: $networkopt"
echo "Encrypted: $encrypted"
echo "Storage cluster mount: ${sc_args[*]}"
echo "Custom mount: $SHIPYARD_CUSTOM_MOUNTS_FSTAB"
echo "P2P: $p2penabled"
echo "Azure File: $azurefile"
echo "Azure Blob: $azureblob"
echo "GlusterFS on compute: $gluster_on_compute"
echo "Block on images: $block"
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
cascadefailed=$AZ_BATCH_NODE_SHARED_DIR/.cascade_failed

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
    SHIPYARD_STORAGE_ENV=`echo $SHIPYARD_STORAGE_ENV | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
    if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
        DOCKER_LOGIN_PASSWORD=`echo $DOCKER_LOGIN_PASSWORD | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
    fi
fi

# set iptables rules
if [ $p2penabled -eq 1 ]; then
    # disable DHT connection tracking
    iptables -t raw -I PREROUTING -p udp --dport 6881 -j CT --notrack
    iptables -t raw -I OUTPUT -p udp --sport 6881 -j CT --notrack
fi

# check for docker host engine
check_for_docker_host_engine
check_docker_root_dir $DISTRIB_ID

# check for nvidia card/driver/docker
check_for_nvidia

# mount azure resources (this must be done every boot)
if [ $azurefile -eq 1 ]; then
    mount_azurefile_share $DISTRIB_ID $DISTRIB_RELEASE
fi
if [ $azureblob -eq 1 ]; then
    mount_azureblob_container $DISTRIB_ID $DISTRIB_RELEASE
fi

# check if we're coming up from a reboot
if [ -f $cascadefailed ]; then
    log ERROR "$cascadefailed file exists, assuming cascade failure during node prep"
    exit 1
elif [ -f $nodeprepfinished ]; then
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

# get ip address of eth0
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

# one-time setup
if [ $networkopt -eq 1 ]; then
    # do not fail script if this function fails
    set +e
    optimize_tcp_network_settings $DISTRIB_ID $DISTRIB_RELEASE
    set -e
    # set sudoers to not require tty
    sed -i 's/^Defaults[ ]*requiretty/# Defaults requiretty/g' /etc/sudoers
fi

# check for gluster
if [ $gluster_on_compute -eq 1 ]; then
    check_for_glusterfs_on_compute
fi

# check for storage cluster software
check_for_storage_cluster_software

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

# set up singularity
singularity_setup $DISTRIB_ID $DISTRIB_RELEASE

# login to registry servers (do not specify -e as creds have been decrypted)
./registry_login.sh
if [ -f singularity-registry-login ]; then
    . singularity-registry-login
fi

# touch node prep finished file to preserve idempotency
touch $nodeprepfinished
# touch cascade failed file, this will be removed once cascade is successful
touch $cascadefailed

# execute cascade
set +e
cascadepid=
envfile=
detached=
if [ $p2penabled -eq 1 ]; then
    detached="-d"
else
    detached="--rm"
fi
# store docker cascade start
if command -v python3 > /dev/null 2>&1; then
    drpstart=`python3 -c 'import datetime;print(datetime.datetime.utcnow().timestamp())'`
else
    drpstart=`python -c 'import datetime;import time;print(time.mktime(datetime.datetime.utcnow().timetuple()))'`
fi
# create env file
envfile=.cascade_envfile
cat > $envfile << EOF
prefix=$prefix
ipaddress=$ipaddress
offer=$offer
sku=$sku
npstart=$npstart
drpstart=$drpstart
p2p=$p2p
`env | grep SHIPYARD_`
`env | grep AZ_BATCH_`
`env | grep DOCKER_LOGIN_`
`env | grep SINGULARITY_`
EOF
chmod 600 $envfile
# pull image
docker_pull_image alfpark/batch-shipyard:${version}-cascade
# set singularity options
singularity_binds=
if [ ! -z $singularity_basedir ]; then
    singularity_binds="\
        -v $singularity_basedir:$singularity_basedir \
        -v $singularity_basedir/mnt:/var/lib/singularity/mnt"
fi
# launch container
log DEBUG "Starting Cascade"
docker run $detached --net=host --env-file $envfile \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /etc/passwd:/etc/passwd:ro \
    -v /etc/group:/etc/group:ro \
    $singularity_binds \
    -v $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR \
    -w $AZ_BATCH_TASK_WORKING_DIR \
    -p 6881-6891:6881-6891 -p 6881-6891:6881-6891/udp \
    alfpark/batch-shipyard:${version}-cascade &
cascadepid=$!

# if not in p2p mode, then wait for cascade exit
if [ $p2penabled -eq 0 ]; then
    wait $cascadepid
    rc=$?
    if [ $rc -ne 0 ]; then
        log ERROR "cascade exited with non-zero exit code: $rc"
        rm -f $nodeprepfinished
        exit $rc
    fi
fi
set -e

# remove cascade failed file
rm -f $cascadefailed

# block for images if necessary
$AZ_BATCH_TASK_WORKING_DIR/wait_for_images.sh $block

# clean up cascade env file if block
if [ ! -z $block ]; then
    rm -f $envfile
fi
