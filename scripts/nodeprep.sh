#!/usr/bin/env bash

set -e
set -o pipefail

nonp2pcd=
offer=
p2p=
prefix=
privatereg=
sku=

while getopts "h?co:p:r:s:t:" opt; do
    case "$opt" in
        h|\?)
            echo "nodeprep.sh parameters"
            echo ""
            echo "-c concurrent downloading in non-p2p mode"
            echo "-o [offer] VM offer"
            echo "-p [prefix] storage container prefix"
            echo "-r [container:archive:image id] private registry"
            echo "-s [sku] VM sku"
            echo "-t [compression:seed bias] enable p2p sharing"
            echo ""
            exit 1
            ;;
        c)
            nonp2pcd="--nonp2pcd"
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
    npstart=`python -c 'import datetime;import time;print(time.mktime(datetime.datetime.utcnow()))'`
fi

# set python env vars
LC_ALL=en_US.UTF-8
#PYTHONIOENCODING=utf-8
PYTHONASYNCIODEBUG=1

# get ip address of eth0
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

# set torrent flag and iptables rules
torrentflag=
if [ ! -z "$p2p" ]; then
    # disable DHT connection tracking
    iptables -t raw -I PREROUTING -p udp --dport 6881 -j CT --notrack
    iptables -t raw -I OUTPUT -p udp --sport 6881 -j CT --notrack
else
    torrentflag="--no-torrent"
fi

# copy job prep docker block file to shared
cp jpdockerblock.sh $AZ_BATCH_NODE_SHARED_DIR

# install docker host engine
if [ $offer == "ubuntuserver" ]; then
    DEBIAN_FRONTEND=noninteractive
    name=
    if [[ $sku == 14.04.* ]]; then
        name=ubuntu-trusty
        srvstart="service docker start"
        srvstop="service docker stop"
    elif [[ $sku == 16.04.* ]]; then
        name=ubuntu-xenial
        srvstart="systemctl start docker.service"
        srvstop="systemctl stop docker.service"
    else
        echo "unsupported sku: $sku for offer: $offer"
        exit 1
    fi
    # check if docker apt source list file exists
    aptsrc=/etc/apt/sources.list.d/docker.list
    if [ ! -e $aptsrc ] || [ ! -s $aptsrc ]; then
        apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D
        echo deb https://apt.dockerproject.org/repo $name main > /etc/apt/sources.list.d/docker.list
        # update package index and purge old docker if it exists
        apt-get update
        apt-get purge -y -q lxc-docker
    fi
    # install required software
    apt-get install -y -q -o Dpkg::Options::="--force-confnew" linux-image-extra-$(uname -r) docker-engine python3-pip
    # ensure docker opts service modifications are idempotent
    set +e
    grep '^DOCKER_OPTS=' /etc/default/docker
    if [ $? -ne 0 ]; then
        set -e
        $srvstop
        set +e
        rm -f /var/lib/docker/network/files/local-kv.db
        echo DOCKER_OPTS="-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock" >> /etc/default/docker
        if [[ $sku == 16.04.* ]]; then
            sed -i '/^\[Service\]/a EnvironmentFile=-/etc/default/docker' /lib/systemd/system/docker.service
            sed -i '/^ExecStart=/ s/$/ $DOCKER_OPTS/' /lib/systemd/system/docker.service
            set -e
            systemctl daemon-reload
            set +e
        fi
        set -e
        $srvstart
        set +e
    fi
    set -e
    # install azure storage python dependency
    pip3 install --no-cache-dir azure-storage
    if [ ! -f ".node_prep_finished" ]; then
        ./perf.py nodeprep start $prefix --ts $npstart --message "offer=$offer,sku=$sku"
    fi
    # install cascade dependencies
    if [ ! -z "$p2p" ]; then
        apt-get install -y -q python3-libtorrent pigz
    fi
    # install private registry if required
    if [ ! -z "$privatereg" ]; then
        # mark private registry start
        if [ ! -f ".node_prep_finished" ]; then
            ./perf.py privateregistry start $prefix --message "ipaddress=$ipaddress"
        fi
        ./setup_private_registry.py $privatereg $ipaddress $prefix
        # mark private registry end
        if [ ! -f ".node_prep_finished" ]; then
            ./perf.py privateregistry end $prefix
        fi
    fi
else
    echo "unsupported offer: $offer (sku: $sku)"
    exit 1
fi

# login to docker hub if no private registry
if [ ! -z $DOCKER_LOGIN_USERNAME ]; then
    docker login -u $DOCKER_LOGIN_USERNAME -p $DOCKER_LOGIN_PASSWORD
fi

# mark node prep finished
if [ ! -f ".node_prep_finished" ]; then
    ./perf.py nodeprep end $prefix
    # touch file to prevent subsequent perf recording if rebooted
    touch .node_prep_finished
fi

# start cascade
./perf.py cascade start $prefix
./cascade.py $p2p --ipaddress $ipaddress $prefix $torrentflag $nonp2pcd > cascade.log &
# if not in p2p mode, then wait for cascade exit
if [ -z "$p2p" ]; then
    wait
fi
