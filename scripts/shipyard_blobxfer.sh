#!/usr/bin/env bash

set -e
set -o pipefail
set -f

for spec in "$@"; do
    # unencrypted = kind:encrypted:sa:ep:saskey:container:include:eo:location
    # encrypted   = kind:encrypted:<encrypted context>:include:eo:location
    IFS=':' read -ra parts <<< "$spec"
    kind=${parts[0]}
    encrypted=${parts[1],,}

    if [ $encrypted == "true" ]; then
        cipher=${parts[2]}
        incl=${parts[3]}
        eo=${parts[4]}
        location=${parts[5]}
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
        sa=${parts[2]}
        ep=${parts[3]}
        saskey=${parts[4]}
        container=${parts[5]}
        incl=${parts[6]}
        eo=${parts[7]}
        location=${parts[8]}
    fi

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
