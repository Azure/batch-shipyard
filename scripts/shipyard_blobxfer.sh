#!/usr/bin/env bash

set -e
set -o pipefail
set -f

for spec in "$@"; do
    # unencrypted = bxver:kind:encrypted:sa:ep:saskey:container:include:eo:location
    # encrypted   = bxver:kind:encrypted:<encrypted context>:include:eo:location
    IFS=':' read -ra parts <<< "$spec"
    bxver=${parts[0]}
    kind=${parts[1]}
    encrypted=${parts[2],,}

    if [ $encrypted == "true" ]; then
        cipher=${parts[3]}
        incl=${parts[4]}
        eo=${parts[5]}
        location=${parts[6]}
        # decrypt ciphertext
        privatekey=$AZ_BATCH_NODE_STARTUP_DIR/certs/key.pem
        cipher=`echo $cipher | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
        IFS=':' read -ra storage <<< "$cipher"
        sa=${storage[0]}
        ep=${storage[1]}
        saskey=${storage[2]}
        container=${storage[3]}
        unset cipher
        unset storage
    else
        sa=${parts[3]}
        ep=${parts[4]}
        saskey=${parts[5]}
        container=${parts[6]}
        incl=${parts[7]}
        eo=${parts[8]}
        location=${parts[9]}
    fi

    include=
    if [ ! -z $incl ]; then
        include="--include $incl"
    fi
    if [ $kind == "i" ]; then
        # create destination directory
        mkdir -p $location
        # ingress data from storage
        docker run --rm -t -v $location:/blobxfer -w /blobxfer \
            alfpark/blobxfer:$bxver $sa $container . \
            --saskey $saskey --remoteresource . --download \
            --no-progressbar $include $eo
    elif [ $kind == "e" ]; then
        # egress from compute node to storage
        docker run --rm -t -v $location:/blobxfer -w /blobxfer \
            alfpark/blobxfer:$bxver $sa $container . \
            --saskey $saskey --upload --no-progressbar $include $eo
    else
        echo "unknown $kind transfer"
        exit 1
    fi
done
