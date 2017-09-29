#!/usr/bin/env bash

set -e
set -o pipefail

# globals
azurefile=0
blobxferversion=latest
block=
encrypted=
gluster_on_compute=0
networkopt=0
p2p=
p2penabled=0
prefix=
privatereg=
sc_args=
version=

# process command line options
while getopts "h?abef:m:np:r:t:v:x:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_nodeprep_customimage.sh parameters"
            echo ""
            echo "-a install azurefile docker volume driver"
            echo "-b block until resources loaded"
            echo "-e [thumbprint] encrypted credentials with cert"
            echo "-f set up glusterfs on compute"
            echo "-m [type:scid] mount storage cluster"
            echo "-n optimize network TCP settings"
            echo "-p [prefix] storage container prefix"
            echo "-r [container:archive:image id] private registry"
            echo "-t [enabled:non-p2p concurrent download:seed bias:compression:pub pull passthrough] p2p sharing"
            echo "-v [version] batch-shipyard version"
            echo "-x [blobxfer version] blobxfer version"
            echo ""
            exit 1
            ;;
        a)
            azurefile=1
            ;;
        b)
            block=$SHIPYARD_DOCKER_IMAGES_PRELOAD
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
        r)
            privatereg=$OPTARG
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

check_for_glusterfs_on_compute() {
    set +e
    gluster
    rc0=$?
    glusterfs -V
    rc1=$?
    set -e
    if [ $rc0 -ne 0 ] || [ $rc1 -ne 0 ]; then
        echo "ERROR: gluster server and client not installed"
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
                echo "Unknown file server type ${sc[0]} for ${sc[1]}"
                exit 1
            fi
        done
    fi
    if [ $rc -ne 0 ]; then
        echo "ERROR: required storage cluster software to mount $sc_args not installed"
        exit 1
    fi
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

echo "Configuration [Custom Image]:"
echo "-----------------------------"
echo "Batch Shipyard version: $version"
echo "Blobxfer version: $blobxferversion"
echo "Distrib ID/Release: $DISTRIB_ID $DISTRIB_RELEASE"
echo "Network optimization: $networkopt"
echo "Encrypted: $encrypted"
echo "Storage cluster mount: ${sc_args[*]}"
echo "P2P: $p2penabled"
echo "Azure File: $azurefile"
echo "GlusterFS on compute: $gluster_on_compute"
echo "Block on images: $block"

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
    SHIPYARD_STORAGE_ENV=`echo $SHIPYARD_STORAGE_ENV | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
    if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
        DOCKER_LOGIN_PASSWORD=`echo $DOCKER_LOGIN_PASSWORD | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
    fi
    if [ ! -z $privatereg ]; then
        SHIPYARD_PRIVATE_REGISTRY_STORAGE_ENV=`echo $SHIPYARD_PRIVATE_REGISTRY_STORAGE_ENV | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
    fi
fi

# set iptables rules
if [ $p2penabled -eq 1 ]; then
    # disable DHT connection tracking
    iptables -t raw -I PREROUTING -p udp --dport 6881 -j CT --notrack
    iptables -t raw -I OUTPUT -p udp --sport 6881 -j CT --notrack
fi

# check if we're coming up from a reboot
if [ -f $cascadefailed ]; then
    echo "$cascadefailed file exists, assuming cascade failure during node prep"
    exit 1
elif [ -f $nodeprepfinished ]; then
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

# login to registry server
if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
    docker login -u $DOCKER_LOGIN_USERNAME -p $DOCKER_LOGIN_PASSWORD $DOCKER_LOGIN_SERVER
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
envfile=.docker_cascade_envfile
cat > $envfile << EOF
prefix=$prefix
ipaddress=$ipaddress
offer=$offer
sku=$sku
npstart=$npstart
drpstart=$drpstart
privatereg=$privatereg
p2p=$p2p
`env | grep SHIPYARD_`
`env | grep AZ_BATCH_`
`env | grep DOCKER_LOGIN_`
EOF
chmod 600 $envfile
# pull image
docker_pull_image alfpark/batch-shipyard:cascade-$version
# launch container
docker run $detached --net=host --env-file $envfile \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR \
    -w $AZ_BATCH_TASK_WORKING_DIR \
    -p 6881-6891:6881-6891 -p 6881-6891:6881-6891/udp \
    alfpark/batch-shipyard:cascade-$version &
cascadepid=$!

# if not in p2p mode, then wait for cascade exit
if [ $p2penabled -eq 0 ]; then
    wait $cascadepid
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "cascade exited with non-zero exit code: $rc"
        rm -f $nodeprepfinished
        exit $rc
    fi
fi
set -e

# remove cascade failed file
rm -f $cascadefailed

# block until images ready if specified
if [ ! -z $block ]; then
    echo "blocking until images ready: $block"
    IFS=',' read -ra RES <<< "$block"
    declare -a missing
    while :
        do
        for image in "${RES[@]}";  do
            if [ -z "$(docker images -q $image 2>/dev/null)" ]; then
                missing=("${missing[@]}" "$image")
            fi
        done
        if [ ${#missing[@]} -eq 0 ]; then
            echo "all docker images present"
            break
        else
            unset missing
        fi
        sleep 2
    done
    rm -f $envfile
fi
