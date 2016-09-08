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
gpu=
networkopt=0
offer=
p2p=
prefix=
privatereg=
sku=

while getopts "h?ab:dg:no:p:r:s:t:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_nodeprep.sh parameters"
            echo ""
            echo "-a install azurefile docker volume driver"
            echo "-b [resources] block until resources loaded"
            echo "-d use docker container for cascade"
            echo "-g [nv-series:driver version:driver file:nvidia docker pkg] gpu support"
            echo "-n optimize network TCP settings"
            echo "-o [offer] VM offer"
            echo "-p [prefix] storage container prefix"
            echo "-r [container:archive:image id] private registry"
            echo "-s [sku] VM sku"
            echo "-t [enabled:non-p2p concurrent download:seed bias:compression:pub pull passthrough] p2p sharing"
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

# set iptables rules
if [ ! -z $p2p ]; then
    # disable DHT connection tracking
    iptables -t raw -I PREROUTING -p udp --dport 6881 -j CT --notrack
    iptables -t raw -I OUTPUT -p udp --sport 6881 -j CT --notrack
fi

# optimize network TCP settings
if [ $networkopt -eq 1 ]; then
    sysctlfile=/etc/sysctl.d/60-azure-shipyard.conf
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

# copy required shell scripts to shared
cp docker_jp_block.sh $AZ_BATCH_NODE_SHARED_DIR

# install docker host engine
if [ $offer == "ubuntuserver" ] || [ $offer == "debian" ]; then
    DEBIAN_FRONTEND=noninteractive
    name=
    if [[ $sku == 14.04.* ]]; then
        name=ubuntu-trusty
        srvstart="initctl start docker"
        srvstop="initctl stop docker"
    elif [[ $sku == 16.04.* ]]; then
        name=ubuntu-xenial
        srvstart="systemctl start docker.service"
        srvstop="systemctl stop docker.service"
        srvenable="systemctl enable docker.service"
    elif [[ $sku == "8" ]]; then
        name=debian-jessie
        srvstart="systemctl start docker.service"
        srvstop="systemctl stop docker.service"
        srvenable="systemctl enable docker.service"
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
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" apt-transport-https ca-certificates
        else
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" linux-image-extra-$(uname -r) linux-image-extra-virtual
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
        apt-get install -y -q -o Dpkg::Options::="--force-confnew" docker-engine
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
        nvdriverver=${GPUARGS[1]}
        nvdriver=${GPUARGS[2]}
        nvdocker=${GPUARGS[3]}
        # get development essentials
        apt-get install -y -q build-essential xserver-xorg-dev nvidia-modprobe
        # install driver
        ./$nvdriver -s
        # install nvidia-docker
        dpkg -i $nvdocker
        # enable and start nvidia docker service
        systemctl enable nvidia-docker.service
        systemctl start nvidia-docker.service
        systemctl status nvidia-docker.service
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
    if [ $cascadecontainer -eq 0 ]; then
        # install azure storage python dependency
        apt-get install -y -q python3-pip
        pip3 install --no-cache-dir azure-storage==0.33.0
        # backfill node prep start
        if [ ! -z ${CASCADE_TIMING+x} ]; then
            ./perf.py nodeprep start $prefix --ts $npstart --message "offer=$offer,sku=$sku"
        fi
        # install cascade dependencies
        if [ ! -z $p2p ]; then
            apt-get install -y -q python3-libtorrent pigz
        fi
        # install private registry if required
        if [ ! -z $privatereg ]; then
            # mark private registry start
            if [ ! -z ${CASCADE_TIMING+x} ]; then
                ./perf.py privateregistry start $prefix --message "ipaddress=$ipaddress"
            fi
            ./setup_private_registry.py $privatereg $ipaddress $prefix
            # mark private registry end
            if [ ! -z ${CASCADE_TIMING+x} ]; then
                ./perf.py privateregistry end $prefix
            fi
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
        else
            srvenable="chkconfig docker on"
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
        elif [[ $offer == sles* ]]; then
            if [[ $sku == "12" ]]; then
                repodir=SLE_12_SP1
            elif [[ $sku == "12-sp1" ]]; then
                repodir=SLE_12
            fi
        fi
        if [ -z $repodir ]; then
            echo "unsupported sku: $sku for offer: $offer"
            exit 1
        fi
        # uninstall existing docker
        set +e
        zypper -n rm docker
        set -e
        # update zypper repo and install docker engine
        zypper addrepo http://download.opensuse.org/repositories/Virtualization:containers/$repodir/Virtualization:containers.repo
        zypper -n --gpg-auto-import-keys ref
        zypper -n in docker
        set +e
        /usr/lib/docker-image-migrator/do-image-migration-v1to2.sh
        set -e
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
    fi
else
    echo "unsupported offer: $offer (sku: $sku)"
    exit 1
fi

# login to docker hub if no private registry
if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
    docker login -u $DOCKER_LOGIN_USERNAME -p $DOCKER_LOGIN_PASSWORD
fi

# touch file to prevent subsequent perf recording if rebooted
touch $nodeprepfinished

# execute cascade
if [ $cascadecontainer -eq 1 ]; then
    detached=
    if [ -z $p2p ]; then
        detached="--rm"
    else
        detached="-d"
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
`env | grep CASCADE_`
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
    # mark node prep finished
    if [ ! -z ${CASCADE_TIMING+x} ]; then
        ./perf.py nodeprep end $prefix
    fi
    # start cascade
    if [ ! -z ${CASCADE_TIMING+x} ]; then
        ./perf.py cascade start $prefix
    fi
    ./cascade.py $p2p --ipaddress $ipaddress $prefix &
fi

# if not in p2p mode, then wait for cascade exit
if [ -z $p2p ]; then
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
fi
