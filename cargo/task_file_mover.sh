#!/usr/bin/env bash

set -e
set -o pipefail
set -f

privatekey=$AZ_BATCH_NODE_STARTUP_DIR/certs/shipyard-enckey.pem

for spec in "$@"; do
    IFS=',' read -ra parts <<< "$spec"
    # encrypt,creds,jobid,taskid,include,exclude,dst
    encrypt=${parts[0],,}
    if [ "$encrypt" == "true" ]; then
        SHIPYARD_BATCH_ENV=$(echo "${parts[1]}" | base64 -d | openssl rsautl -decrypt -inkey "$privatekey")
    else
        SHIPYARD_BATCH_ENV=${parts[1]}
    fi
    unset encrypt
    jobid=${parts[2]}
    taskid=${parts[3]}
    incl=${parts[4]}
    excl=${parts[5]}
    dst=${parts[6]}

    include=
    if [ -n "$incl" ]; then
        include="--include $incl"
    fi
    exclude=
    if [ -n "$excl" ]; then
        exclude="--exclude $excl"
    fi
    # create destination directory
    dest=
    if [ -n "$dst" ]; then
        dest="--dst $dst"
        mkdir -p "$dst"
    fi
    # ingress data from batch task
    export SHIPYARD_BATCH_ENV=$SHIPYARD_BATCH_ENV
    # shellcheck disable=SC2086
    python3 /opt/batch-shipyard/task_file_mover.py "$jobid" "$taskid" ${include} ${exclude} ${dest}
done
