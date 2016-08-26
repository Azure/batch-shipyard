#!/usr/bin/env bash

set -e
set -o pipefail

# ensure we're in the proper directory
cd /opt/batch-shipyard

# add timing markers
if [ ! -z ${CASCADE_TIMING+x} ]; then
    # backfull docker run pull start
    python3 perf.py cascade docker-run-pull-start $prefix --ts $drpstart
    # mark docker run pull end
    python3 perf.py cascade docker-run-pull-end $prefix
    if [ ! -f ".node_prep_finished" ]; then
        # backfill node prep start
        python3 perf.py nodeprep start $prefix --ts $npstart --message "offer=$offer,sku=$sku"
        # mark private registry start
        python3 perf.py privateregistry start $prefix --message "ipaddress=$ipaddress"
    fi
fi

# set up private registry
python3 setup_private_registry.py $privatereg $ipaddress $prefix

# login to docker hub
if [ ! -z ${DOCKER_LOGIN_USERNAME+x} ]; then
    docker login -u $DOCKER_LOGIN_USERNAME -p $DOCKER_LOGIN_PASSWORD
fi

# add timing markers
if [ ! -z ${CASCADE_TIMING+x} ]; then
    if [ ! -f ".node_prep_finished" ]; then
        # mark private registry end
        python3 perf.py privateregistry end $prefix
        # mark node prep finished
        python3 perf.py nodeprep end $prefix
    fi
    # mark cascade start time
    python3 perf.py cascade start $prefix
fi

# execute cascade
python3 cascade.py $p2p --ipaddress $ipaddress $prefix

