#!/usr/bin/env bash

set -e
set -o pipefail

for spec in "$@"; do
    # sa:ep:saskey:container:include:eo:dst
    IFS=':' read -ra parts <<< "$spec"
    sa=${parts[0]}
    ep=${parts[1]}
    saskey=${parts[2]}
    container=${parts[3]}
    incl=${parts[4]}
    eo=${parts[5]}
    dst=${parts[6]}
    include=
    if [ ! -z $incl ]; then
        include="--include $incl"
    fi
    # create destination directory
    mkdir -p $dst
    # ingress data from blobs
    docker run --rm -t -v $dst:/blobxfer -w /blobxfer alfpark/blobxfer $sa $container . --saskey $saskey --remoteresource . --download --no-progressbar $include $eo
done
