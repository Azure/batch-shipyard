#!/usr/bin/env bash

set -e
set -o pipefail

azurefile=0
cascadecontainer=0
offer=
p2p=
prefix=
privatereg=
sku=

while getopts "h?ado:p:r:s:t:" opt; do
    case "$opt" in
        h|\?)
            echo "nodeprep.sh parameters"
            echo ""
            echo "-a install azurefile docker volume driver"
            echo "-d use docker container for cascade"
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
        d)
            cascadecontainer=1
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

# set iptables rules
if [ ! -z "$p2p" ]; then
    # disable DHT connection tracking
    iptables -t raw -I PREROUTING -p udp --dport 6881 -j CT --notrack
    iptables -t raw -I OUTPUT -p udp --sport 6881 -j CT --notrack
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
        afdvdenable="systemctl enable azurefile-dockervolumedriver"
        afdvdstart="systemctl start azurefile-dockervolumedriver"
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
    apt-get install -y -q -o Dpkg::Options::="--force-confnew" linux-image-extra-$(uname -r) docker-engine
    # ensure docker opts service modifications are idempotent
    set +e
    grep '^DOCKER_OPTS=' /etc/default/docker
    if [ $? -ne 0 ]; then
        set -e
        $srvstop
        # set up azure file docker volume driver if instructed
        if [ $azurefile -eq 1 ]; then
            chown root:root azurefile-dockervolumedriver*
            chmod 755 azurefile-dockervolumedriver
            chmod 640 azurefile-dockervolumedriver.env
            mv azurefile-dockervolumedriver /usr/bin
            mv azurefile-dockervolumedriver.env /etc/default/azurefile-dockervolumedriver
            mv azurefile-dockervolumedriver.service /etc/systemd/system
        fi
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
        # start azure file docker volume driver
        if [ $azurefile -eq 1 ]; then
            $afdvdenable
            $afdvdstart
            # create docker volumes
            chmod +x azurefile-dockervolume-create.sh
            ./azurefile-dockervolume-create.sh
        fi
        set +e
    fi
    set -e
    if [ $cascadecontainer -eq 0 ]; then
        # install azure storage python dependency
        apt-get install -y -q python3-pip
        pip3 install --no-cache-dir azure-storage==0.32.0
        # backfill node prep start
        if [ ! -z ${CASCADE_TIMING+x} ] && [ ! -f ".node_prep_finished" ]; then
            ./perf.py nodeprep start $prefix --ts $npstart --message "offer=$offer,sku=$sku"
        fi
        # install cascade dependencies
        if [ ! -z "$p2p" ]; then
            apt-get install -y -q python3-libtorrent pigz
        fi
        # install private registry if required
        if [ ! -z "$privatereg" ]; then
            # mark private registry start
            if [ ! -z ${CASCADE_TIMING+x} ] && [ ! -f ".node_prep_finished" ]; then
                ./perf.py privateregistry start $prefix --message "ipaddress=$ipaddress"
            fi
            ./setup_private_registry.py $privatereg $ipaddress $prefix
            # mark private registry end
            if [ ! -z ${CASCADE_TIMING+x} ] && [ ! -f ".node_prep_finished" ]; then
                ./perf.py privateregistry end $prefix
            fi
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
touch .node_prep_finished

# execute cascade
if [ $cascadecontainer -eq 1 ]; then
    detached=
    if [ -z "$p2p" ]; then
        detached="--rm"
    else
        detached="-d"
    fi
    # store docker run pull start
    if command -v python3 > /dev/null 2>&1; then
        drpstart=`python3 -c 'import datetime;print(datetime.datetime.utcnow().timestamp())'`
    else
        drpstart=`python -c 'import datetime;import time;print(time.mktime(datetime.datetime.utcnow()))'`
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
PRIVATE_REGISTRY_STORAGE_ENV=$PRIVATE_REGISTRY_STORAGE_ENV
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
        alfpark/shipyard
else
    # mark node prep finished
    if [ ! -z ${CASCADE_TIMING+x} ] && [ ! -f ".node_prep_finished" ]; then
        ./perf.py nodeprep end $prefix
    fi
    # start cascade
    if [ ! -z ${CASCADE_TIMING+x} ]; then
        ./perf.py cascade start $prefix
    fi
    ./cascade.py $p2p --ipaddress $ipaddress $prefix &
fi

# if not in p2p mode, then wait for cascade exit
if [ -z "$p2p" ]; then
    wait
fi

