#!/usr/bin/env bash

set -e
set -o pipefail

install_azurefile_docker_volume_driver() {
    chown root:root azurefile-dockervolumedriver*
    chmod 755 azurefile-dockervolumedriver
    chmod 640 azurefile-dockervolumedriver.env
    mv azurefile-dockervolumedriver /usr/bin
    mv azurefile-dockervolumedriver.env /etc/default/azurefile-dockervolumedriver
    if [[ $1 == "ubuntuserver" ]] && [[ $2 == 14.04.* ]]; then
        mv azurefile-dockervolumedriver.conf /etc/init
        initctl reload-configuration
        initctl start azurefile-dockervolumedriver
    else
        if [[ $1 == opensuse* ]] || [[ $1 == sles* ]]; then
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

azurefile=0
block=
cascadecontainer=0
encrypted=
hpnssh=0
gluster=0
gpu=
networkopt=0
offer=
p2p=
p2penabled=0
prefix=
privatereg=
sku=

while getopts "h?ab:de:fg:no:p:r:s:t:w" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_nodeprep.sh parameters"
            echo ""
            echo "-a install azurefile docker volume driver"
            echo "-b [resources] block until resources loaded"
            echo "-d use docker container for cascade"
            echo "-e [thumbprint] encrypted credentials with cert"
            echo "-f set up glusterfs cluster"
            echo "-g [nv-series::driver file:nvidia docker pkg] gpu support"
            echo "-n optimize network TCP settings"
            echo "-o [offer] VM offer"
            echo "-p [prefix] storage container prefix"
            echo "-r [container:archive:image id] private registry"
            echo "-s [sku] VM sku"
            echo "-t [enabled:non-p2p concurrent download:seed bias:compression:pub pull passthrough] p2p sharing"
            echo "-w install openssh-hpn"
            echo ""
            exit 1
            ;;
        a)
            azurefile=1
            ;;
        b)
            block=$OPTARG
            ;;
        d)
            cascadecontainer=1
            ;;
        e)
            encrypted=${OPTARG,,}
            ;;
        f)
            gluster=1
            ;;
        g)
            gpu=$OPTARG
            ;;
        n)
            networkopt=1
            ;;
        o)
            offer=${OPTARG,,}
            ;;
        p)
            prefix="--prefix $OPTARG"
            ;;
        r)
            privatereg=$OPTARG
            ;;
        s)
            sku=${OPTARG,,}
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
        w)
            hpnssh=1
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift
# check args
if [ -z $offer ]; then
    echo "vm offer not specified"
    exit 1
fi
if [ -z $sku ]; then
    echo "vm sku not specified"
    exit 1
fi

# TODO temporary check to look for buggy sdb1 mount
set +e
mount | grep /dev/sdb1 | grep fuseblk
if [ $? -eq 0 ]; then
    echo "/dev/sdb1 temp disk is mounted as fuseblk/ntfs"
    exit 1
fi
set -e

# store node prep start
if command -v python3 > /dev/null 2>&1; then
    npstart=`python3 -c 'import datetime;print(datetime.datetime.utcnow().timestamp())'`
else
    npstart=`python -c 'import datetime;import time;print(time.mktime(datetime.datetime.utcnow().timetuple()))'`
fi

# set node prep finished file
nodeprepfinished=$AZ_BATCH_NODE_SHARED_DIR/.node_prep_finished

# set python env vars
LC_ALL=en_US.UTF-8
PYTHONASYNCIODEBUG=1

# get ip address of eth0
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

# one time setup of ssh/tcp tuning
if [ ! -f $nodeprepfinished ]; then
    # set up hpn-ssh
    if [ $hpnssh -eq 1 ]; then
        ./shipyard_hpnssh.sh $offer $sku
    fi
    # optimize network TCP settings
    if [ $networkopt -eq 1 ]; then
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
    fi
fi

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

# copy required shell scripts to shared
cp docker_jp_block.sh shipyard_blobxfer.sh $AZ_BATCH_NODE_SHARED_DIR

# install docker host engine
if [ $offer == "ubuntuserver" ] || [ $offer == "debian" ]; then
    DEBIAN_FRONTEND=noninteractive
    name=
    if [[ $sku == 14.04.* ]]; then
        name=ubuntu-trusty
        srvstart="initctl start docker"
        srvstop="initctl stop docker"
        gfsstart="initctl start glusterfs-server"
    elif [[ $sku == 16.04.* ]]; then
        name=ubuntu-xenial
        srvstart="systemctl start docker.service"
        srvstop="systemctl stop docker.service"
        srvenable="systemctl enable docker.service"
        gfsstart="systemctl start glusterfs-server"
        gfsenable="systemctl enable glusterfs-server"
    elif [[ $sku == "8" ]]; then
        name=debian-jessie
        srvstart="systemctl start docker.service"
        srvstop="systemctl stop docker.service"
        srvenable="systemctl enable docker.service"
        gfsstart="systemctl start glusterfs-server"
        gfsenable="systemctl enable glusterfs-server"
    else
        echo "unsupported sku: $sku for offer: $offer"
        exit 1
    fi
    if [ ! -z $gpu ] && [ $name != "ubuntu-xenial" ]; then
        echo "gpu unsupported on this sku: $sku for offer $offer"
        exit 1
    fi
    # reload network settings
    if [ $networkopt -eq 1 ]; then
        service procps reload
    fi
    # check if docker apt source list file exists
    aptsrc=/etc/apt/sources.list.d/docker.list
    if [ ! -e $aptsrc ] || [ ! -s $aptsrc ]; then
        # refresh package index
        apt-get update
        # install required software first
        if [ $offer == "debian" ]; then
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
                apt-transport-https ca-certificates
        else
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
                linux-image-extra-$(uname -r) linux-image-extra-virtual
        fi
        apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D
        echo deb https://apt.dockerproject.org/repo $name main > /etc/apt/sources.list.d/docker.list
        # update package index with docker repo and purge old docker if it exists
        apt-get update
        apt-get purge -y -q lxc-docker
    fi
    # ensure docker opts service modifications are idempotent
    set +e
    grep '^DOCKER_OPTS=' /etc/default/docker
    if [ $? -ne 0 ]; then
        # install docker engine
        apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
            docker-engine
        set -e
        $srvstop
        set +e
        rm -f /var/lib/docker/network/files/local-kv.db
        sed -i -e '/^DOCKER_OPTS=.*/,${s||DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/docker\"|;b};$q1' /etc/default/docker || echo DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/docker\" >> /etc/default/docker
        if [[ $sku == 16.04.* ]]; then
            sed -i '/^\[Service\]/a EnvironmentFile=-/etc/default/docker' /lib/systemd/system/docker.service
            sed -i '/^ExecStart=/ s/$/ $DOCKER_OPTS/' /lib/systemd/system/docker.service
            set -e
            systemctl daemon-reload
            $srvenable
            set +e
        fi
        set -e
        $srvstart
        # setup and start azure file docker volume driver
        if [ $azurefile -eq 1 ]; then
            install_azurefile_docker_volume_driver $offer $sku
        fi
        set +e
    fi
    set -e
    # install gpu related items
    if [ ! -z $gpu ] && [ ! -f $nodeprepfinished ]; then
        # split arg into two
        IFS=':' read -ra GPUARGS <<< "$gpu"
        # take special actions if we're on NV-series VMs
        if [ ${GPUARGS[0]} == "True" ]; then
            # remove nouveau
            apt-get --purge remove xserver-xorg-video-nouveau
            rmmod nouveau
            # blacklist nouveau from being loaded if rebooted
cat > /etc/modprobe.d/blacklist-nouveau.conf << EOF
blacklist nouveau
blacklist lbm-nouveau
options nouveau modeset=0
alias nouveau off
alias lbm-nouveau off
EOF
        fi
        nvdriver=${GPUARGS[1]}
        nvdocker=${GPUARGS[2]}
        # get development essentials for nvidia driver
        apt-get install -y -q --no-install-recommends \
            build-essential xserver-xorg-dev nvidia-modprobe
        # install driver
        ./$nvdriver -s
        # install nvidia-docker
        dpkg -i $nvdocker
        # enable and start nvidia docker service
        systemctl enable nvidia-docker.service
        systemctl start nvidia-docker.service
        systemctl status nvidia-docker.service
        # get driver version
        nvdriverver=`cat /proc/driver/nvidia/version | grep "Kernel Module" | cut -d ' ' -f 9`
        echo nvidia driver version $nvdriverver detected
        # create the docker volume now to avoid volume driver conflicts for
        # tasks. run this in a loop as it can fail if triggered too quickly
        # after start
        NV_START=$(date -u +"%s")
        set +e
        while :
        do
            echo "Attempting to create nvidia-docker volume with version $nvdriverver"
            docker volume create -d nvidia-docker --name nvidia_driver_$nvdriverver
            if [ $? -eq 0 ]; then
                break
            else
                NV_NOW=$(date -u +"%s")
                NV_DIFF=$((($NV_NOW-$NV_START)/60))
                # fail after 5 minutes of attempts
                if [ $NV_DIFF -ge 5 ]; then
                    echo "could not create nvidia-docker volume"
                    exit 1
                fi
                sleep 1
            fi
        done
        set -e
    fi
    # set up glusterfs
    if [ $gluster -eq 1 ] && [ ! -f $nodeprepfinished ]; then
        apt-get install -y -q --no-install-recommends glusterfs-server
        if [[ ! -z $gfsenable ]]; then
            $gfsenable
        fi
        $gfsstart
        # create brick directory
        mkdir -p /mnt/gluster
    fi
    # install dependencies if not using cascade container
    if [ $cascadecontainer -eq 0 ]; then
        # install azure storage python dependency
        apt-get install -y -q --no-install-recommends \
            build-essential libssl-dev libffi-dev libpython3-dev python3-dev python3-pip
        pip3 install --no-cache-dir azure-storage==0.33.0
        # install cascade dependencies
        if [ $p2penabled -eq 1 ]; then
            apt-get install -y -q --no-install-recommends python3-libtorrent pigz
        fi
    fi
elif [[ $offer == centos* ]] || [[ $offer == "rhel" ]] || [[ $offer == "oracle-linux" ]]; then
    # ensure container only support
    if [ $cascadecontainer -eq 0 ]; then
        echo "only supported through shipyard container"
        exit 1
    fi
    # gpu is not supported on these offers
    if [ ! -z $gpu ]; then
        echo "gpu unsupported on this sku: $sku for offer $offer"
        exit 1
    fi
    if [[ $sku == 7.* ]]; then
        if [[ $offer == "oracle-linux" ]]; then
            srvenable="systemctl enable docker.service"
            gfsenable="systemctl enable glusterd"
        else
            srvenable="chkconfig docker on"
            gfsenable="chkconfig glusterd on"
        fi
    else
        echo "unsupported sku: $sku for offer: $offer"
        exit 1
    fi
    # reload network settings
    if [ $networkopt -eq 1 ]; then
        sysctl -p
    fi
    # add docker repo to yum
    yumrepo=/etc/yum.repos.d/docker.repo
    if [ ! -e $yumrepo ] || [ ! -s $yumrepo ]; then
        baseurl=
        if [[ $offer == "oracle-linux" ]]; then
            baseurl=https://yum.dockerproject.org/repo/main/oraclelinux/7
            # TODO, in order to support docker > 1.9, need to upgrade to UEKR4
            echo "oracle linux is not supported at this time"
            exit 1
        else
            baseurl=https://yum.dockerproject.org/repo/main/centos/7/
        fi
cat > $yumrepo << EOF
[dockerrepo]
name=Docker Repository
baseurl=$baseurl
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF
        # update yum repo and install docker engine
        yum install -y docker-engine
        # modify docker opts
        sed -i -e '/^DOCKER_OPTS=.*/,${s||DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\"|;b};$q1' /etc/default/docker || echo DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\" >> /etc/default/docker
        sed -i '/^\[Service\]/a EnvironmentFile=-/etc/default/docker' /lib/systemd/system/docker.service
        sed -i '/^ExecStart=/ s/$/ $DOCKER_OPTS/' /lib/systemd/system/docker.service
        systemctl daemon-reload
        # start docker service and enable docker daemon on boot
        $srvenable
        systemctl start docker.service
        # setup and start azure file docker volume driver
        if [ $azurefile -eq 1 ]; then
            install_azurefile_docker_volume_driver $offer $sku
        fi
        # set up glusterfs
        if [ $gluster -eq 1 ] && [ ! -f $nodeprepfinished ]; then
            yum install -y epel-release centos-release-gluster38
            sed -i -e "s/enabled=1/enabled=0/g" /etc/yum.repos.d/CentOS-Gluster-3.8.repo
            yum install -y --enablerepo=centos-gluster38,epel glusterfs-server
            $gfsenable
            systemctl start glusterd
            # create brick directory
            mkdir -p /mnt/resource/gluster
        fi
    fi
elif [[ $offer == opensuse* ]] || [[ $offer == sles* ]]; then
    # ensure container only support
    if [ $cascadecontainer -eq 0 ]; then
        echo "only supported through shipyard container"
        exit 1
    fi
    # gpu is not supported on these offers
    if [ ! -z $gpu ]; then
        echo "gpu unsupported on this sku: $sku for offer $offer"
        exit 1
    fi
    # reload network settings
    if [ $networkopt -eq 1 ]; then
        sysctl -p
    fi
    if [ ! -f $nodeprepfinished ]; then
        # add Virtualization:containers repo for recent docker builds
        repodir=
        if [[ $offer == opensuse* ]]; then
            if [[ $sku == "13.2" ]]; then
                repodir=openSUSE_13.2
            elif [[ $sku == "42.1" ]]; then
                repodir=openSUSE_Leap_42.1
            fi
            # add container repo for zypper
            zypper addrepo http://download.opensuse.org/repositories/Virtualization:containers/$repodir/Virtualization:containers.repo
            zypper -n --gpg-auto-import-keys ref
            # uninstall existing docker
            set +e
            zypper -n rm docker
            set -e
        elif [[ $offer == sles* ]]; then
            if [[ $sku == "12" ]]; then
                repodir=SLE_12
            elif [[ $sku == "12-sp1" ]]; then
                repodir=SLE_12_SP1
            fi
            # enable container module
            SUSEConnect -p sle-module-containers/12/x86_64 -r ''
            zypper ref
        fi
        if [ -z $repodir ]; then
            echo "unsupported sku: $sku for offer: $offer"
            exit 1
        fi
        # install docker engine
        zypper -n in docker
        # modify docker opts, docker opts in /etc/sysconfig/docker
        sed -i -e '/^DOCKER_OPTS=.*/,${s||DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\"|;b};$q1' /etc/sysconfig/docker || echo DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\" >> /etc/sysconfig/docker
        systemctl daemon-reload
        # start docker service and enable docker daemon on boot
        systemctl enable docker
        systemctl start docker
        # setup and start azure file docker volume driver
        if [ $azurefile -eq 1 ]; then
            install_azurefile_docker_volume_driver $offer $sku
        fi
        # set up glusterfs
        if [ $gluster -eq 1 ]; then
            zypper addrepo http://download.opensuse.org/repositories/filesystems/$repodir/filesystems.repo
            zypper -n --gpg-auto-import-keys ref
            zypper -n in glusterfs
            systemctl daemon-reload
            systemctl enable glusterd
            systemctl start glusterd
            # create brick directory
            mkdir -p /mnt/resource/gluster
        fi
        # if hpc sku, set up intel mpi
        if [[ $offer == sles-hpc* ]]; then
            if [ $sku != "12-sp1" ]; then
                echo "unsupported sku for intel mpi setup on SLES"
                exit 1
            fi
            zypper -n in lsb
            rpm -Uvh /opt/intelMPI/intel_mpi_packages/intel-mpi-rt-intel64-5.0.3p-048.x86_64.rpm
            mkdir -p /opt/intel/compilers_and_libraries/linux
            ln -s /opt/intel/impi/5.0.3.048 /opt/intel/compilers_and_libraries/linux/mpi
        fi
    fi
else
    echo "unsupported offer: $offer (sku: $sku)"
    exit 1
fi

# retrieve docker images related to data movement
docker pull alfpark/blobxfer
docker pull alfpark/batch-shipyard:tfm-latest

# login to docker hub if no private registry
if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
    docker login -u $DOCKER_LOGIN_USERNAME -p $DOCKER_LOGIN_PASSWORD
fi

# touch node prep finished file to preserve idempotency
touch $nodeprepfinished

# execute cascade
envfile=
if [ $cascadecontainer -eq 1 ]; then
    detached=
    if [ $p2penabled -eq 1 ]; then
        detached="-d"
    else
        detached="--rm"
    fi
    # store docker run pull start
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
    # launch container
    docker run $detached --net=host --env-file $envfile \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v $AZ_BATCH_NODE_ROOT_DIR:$AZ_BATCH_NODE_ROOT_DIR \
        -w $AZ_BATCH_TASK_WORKING_DIR \
        -p 6881-6891:6881-6891 -p 6881-6891:6881-6891/udp \
        alfpark/batch-shipyard
else
    # backfill node prep start
    if [ ! -z ${SHIPYARD_TIMING+x} ]; then
        ./perf.py nodeprep start $prefix --ts $npstart --message "offer=$offer,sku=$sku"
    fi
    # install private registry if required
    if [ ! -z $privatereg ]; then
        # mark private registry start
        if [ ! -z ${SHIPYARD_TIMING+x} ]; then
            ./perf.py privateregistry start $prefix --message "ipaddress=$ipaddress"
        fi
        ./setup_private_registry.py $privatereg $ipaddress $prefix
        # mark private registry end
        if [ ! -z ${SHIPYARD_TIMING+x} ]; then
            ./perf.py privateregistry end $prefix
        fi
    fi
    # mark node prep finished
    if [ ! -z ${SHIPYARD_TIMING+x} ]; then
        ./perf.py nodeprep end $prefix
    fi
    # start cascade
    if [ ! -z ${SHIPYARD_TIMING+x} ]; then
        ./perf.py cascade start $prefix
    fi
    ./cascade.py $p2p --ipaddress $ipaddress $prefix &
fi

# if not in p2p mode, then wait for cascade exit
if [ $p2penabled -eq 0 ]; then
    wait
fi

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
    if [ $cascadecontainer -eq 1 ]; then
        rm -f $envfile
    fi
fi
