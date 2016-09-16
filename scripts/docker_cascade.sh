#!/usr/bin/env bash

set -e
set -o pipefail

# ensure we're in the proper directory
cd /opt/batch-shipyard

# add timing markers
if [ ! -z ${CASCADE_TIMING+x} ]; then
    # backfill node prep start
    python3 perf.py nodeprep start $prefix --ts $npstart --message "offer=$offer,sku=$sku"
    # backfull docker run pull start
    python3 perf.py shipyard pull-start $prefix --ts $drpstart
    # mark docker run pull end
    python3 perf.py shipyard pull-end $prefix
    # mark private registry start
    if [ ! -z $privatereg ]; then
        python3 perf.py privateregistry start $prefix --message "ipaddress=$ipaddress"
    fi
fi

# set up private registry
if [ ! -z $privatereg ]; then
    python3 setup_private_registry.py $privatereg $ipaddress $prefix
fi

# login to docker hub
if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
    docker login -u $DOCKER_LOGIN_USERNAME -p $DOCKER_LOGIN_PASSWORD
fi

# add timing markers
if [ ! -z ${CASCADE_TIMING+x} ]; then
    # mark private registry end
    if [ ! -z $privatereg ]; then
        python3 perf.py privateregistry end $prefix
    fi
    # mark node prep finished
    python3 perf.py nodeprep end $prefix
    # mark cascade start time
    python3 perf.py cascade start $prefix
fi

# execute cascade
python3 cascade.py $p2p --ipaddress $ipaddress $prefix

