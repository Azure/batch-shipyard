#!/usr/bin/env bash

set -o pipefail

offer=
p2p=0
prefix=
privatereg=
sku=

while getopts "h?o:p:r:s:t" opt; do
    case "$opt" in
        h|\?)
            echo "nodeprep.sh parameters"
            echo ""
            echo "-o [offer] VM offer"
            echo "-p [prefix] storage container prefix"
            echo "-r [container] enable private registry"
            echo "-s [sku] VM sku"
            echo "-t enable p2p sharing"
            echo ""
            exit 1
            ;;
        o)
            offer=${OPTARG,,}
            ;;
        p)
            prefix=$OPTARG
            ;;
        r)
            privatereg="--privatereg $OPTARG"
            ;;
        s)
            sku=${OPTARG,,}
            ;;
        t)
            p2p=1
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

# get ip address of eth0
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

# install docker host engine
if [ $offer == "ubuntuserver" ]; then
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
    fi
    apt-get update
    apt-get purge -y lxc-docker
    # install required software
    apt-get install -y docker-engine python3-pip
    $srvstop
    # ensure docker opts service modifications are idempotent
    grep '^DOCKER_OPTS=' /etc/default/docker
    if [ $? -ne 0 ]; then
        rm -f /var/lib/docker/network/files/local-kv.db
        echo DOCKER_OPTS="-H tcp://$ipaddress:2375 -H unix:///var/run/docker.sock" >> /etc/default/docker
        if [[ $sku == 16.04.* ]]; then
            sed -i '/^\[Service\]/a EnvironmentFile=-/etc/default/docker' /lib/systemd/system/docker.service
            sed -i '/^ExecStart=/ s/$/ $DOCKER_OPTS/' /lib/systemd/system/docker.service
            systemctl daemon-reload
        fi
    fi
    $srvstart
    # install cascade dependencies
    if [ $p2p -eq 1 ]; then
        apt-get install -y python3-libtorrent
    fi
else
    echo "unsupported offer: $offer (sku: $sku)"
    exit 1
fi

# login to docker hub if no private registry
if [ ! -z $DOCKER_LOGIN_USERNAME ]; then
    docker login -u $DOCKER_LOGIN_USERNAME -p $DOCKER_LOGIN_PASSWORD
fi

# enable p2p sharing
if [ $p2p -eq 1 ]; then
    # install cascade dependencies
    pip3 install azure-storage
    # start cascade
    if [ ! -z $prefix ]; then
        prefix="--prefix $prefix"
    fi
    ./cascade.py $ipaddress $privatereg $prefix > cascade.log &
fi
