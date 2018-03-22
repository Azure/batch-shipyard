#!/usr/bin/env bash

set -e
set -o pipefail
set -f

for spec in "$@"; do
    # unencrypted = bxver:kind:encrypted:sa:ep:saskey:remote_path:local_path:eo
    # encrypted   = bxver:kind:encrypted:<encrypted context>:local_path:eo
    IFS=',' read -ra parts <<< "$spec"
    bxver=${parts[0]}
    kind=${parts[1]}
    encrypted=${parts[2],,}

    if [ $encrypted == "true" ]; then
        cipher=${parts[3]}
        local_path=${parts[4]}
        eo=${parts[5]}
        # decrypt ciphertext
        privatekey=$AZ_BATCH_NODE_STARTUP_DIR/certs/key.pem
        cipher=`echo $cipher | base64 -d | openssl rsautl -decrypt -inkey $privatekey`
        IFS=',' read -ra storage <<< "$cipher"
        sa=${storage[0]}
        ep=${storage[1]}
        saskey=${storage[2]}
        remote_path=${storage[3]}
        unset cipher
        unset storage
    else
        sa=${parts[3]}
        ep=${parts[4]}
        saskey=${parts[5]}
        remote_path=${parts[6]}
        local_path=${parts[7]}
        eo=${parts[8]}
    fi

    wd=$(dirname "$local_path")
    if [ $kind == "i" ]; then
        # create destination working directory
        mkdir -p $wd
        # ingress data from storage
        action=download
    elif [ $kind == "e" ]; then
        # egress from compute node to storage
        action=upload
    else
        echo "ERROR: unknown $kind transfer"
        exit 1
    fi

    # execute blobxfer
    docker run --rm -t -v $wd:$wd -w $wd alfpark/blobxfer:$bxver \
        $action --storage-account $sa --sas $saskey --endpoint $ep \
        --remote-path $remote_path --local-path $local_path \
        --no-progress-bar $eo
done
