#!/usr/bin/env bash

set -e
set -o pipefail
set -f

for spec in "$@"; do
    # kind:sa:ep:saskey:container:include:eo:location
    IFS=':' read -ra parts <<< "$spec"
    kind=${parts[0]}
    sa=${parts[1]}
    ep=${parts[2]}
    saskey=${parts[3]}
    container=${parts[4]}
    incl=${parts[5]}
    eo=${parts[6]}
    location=${parts[7]}
    include=
    if [ ! -z $incl ]; then
        include="--include $incl"
    fi
    if [ $kind == "ingress" ]; then
        # create destination directory
        mkdir -p $location
        # ingress data from storage
        docker run --rm -t -v $location:/blobxfer -w /blobxfer \
            alfpark/blobxfer $sa $container . --saskey $saskey \
            --remoteresource . --download --no-progressbar $include $eo
    elif [ $kind == "egress" ]; then
        # egress from compute node to storage
        docker run --rm -t -v $location:/blobxfer -w /blobxfer \
            alfpark/blobxfer $sa $container . --saskey $saskey \
            --upload --no-progressbar $include $eo
    else
        echo "unknown $kind transfer"
        exit 1
    fi
done
