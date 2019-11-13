#!/usr/bin/env bash

set -e
set -o pipefail

MOUNT_DIR="$AZ_BATCH_NODE_ROOT_DIR/mounts"

execute_command_with_retry() {
    set +e
    local retries=$1
    shift
    local fatal=$1
    shift
    local rc
    while [ "$retries" -gt 0 ]; do
        "$@"
        rc=$?
        if [ "$rc" -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            echo "Could not execute command: $*"
            if [ "$fatal" -eq 1 ]; then
                exit $rc
            else
                break
            fi
        fi
        sleep 1
    done
    set -e
}

prep_blob_mount_dirs() {
    local bftmp="${1}/blobfuse-tmp/${2}-${3}"
    local hmp="${MOUNT_DIR}/azblob-${2}-${3}"
    mkdir -p "$bftmp"
    chmod 0770 "$bftmp"
    mkdir -p "$hmp"
    chmod 0770  "$hmp"
}

mount_blob_container() {
    local container="$3"
    local bftmp="${1}/blobfuse-tmp/${2}-${container}"
    local hmp="${MOUNT_DIR}/azblob-${2}-${container}"
    export AZURE_STORAGE_ACCOUNT="$2"
    export AZURE_STORAGE_SAS_TOKEN="$4"
    shift 4
    echo "Mounting blob container $container (sa=$AZURE_STORAGE_ACCOUNT) with options: $*"
    # shellcheck disable=SC2068
    execute_command_with_retry 15 1 blobfuse "$hmp" --container-name="${container}" --tmp-path="${bftmp}" $@
}

prep_file_mount_dirs() {
    local hmp="${MOUNT_DIR}/azfile-${1}-${2}"
    mkdir -p "$hmp"
    chmod 0770  "$hmp"
}

mount_file_share() {
    local sa="$1"
    local ep="$2"
    local sakey="$3"
    local share="$4"
    local opts="$5"
    local hmp="${MOUNT_DIR}/azfile-${sa}-${share}"
    local options="vers=3.0,username=${sa},password=${sakey}"
    if [ -n "$opts" ]; then
        options="${options},${opts}"
    fi
    echo "Mounting file share $share (sa=$sa) with options: $opts"
    execute_command_with_retry 15 1 mount -t cifs "//${sa}.file.${ep}/${share}" "${hmp}" -o "$options"
}

