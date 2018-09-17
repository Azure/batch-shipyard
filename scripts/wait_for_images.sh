#!/usr/bin/env bash

set -e

log() {
    local level=$1
    shift
    echo "$(date -u -Ins) - $level - $*"
}

IFS='#' read -ra cip <<< "$1"
block_docker=${cip[0]}
block_singularity=${cip[1]}

log DEBUG "Block for Docker images: $block_docker"
log DEBUG "Block for Singularity images: $block_singularity"

if [ -n "$block_docker" ]; then
    log INFO "blocking until Docker images ready: $block_docker"
    IFS=',' read -ra RES <<< "$block_docker"
    declare -a missing
    while :
        do
        for image in "${RES[@]}";  do
            if [ -z "$(docker images -q "$image" 2>/dev/null)" ]; then
                missing=("${missing[@]}" "$image")
            fi
        done
        if [ ${#missing[@]} -eq 0 ]; then
            log INFO "all Docker images present"
            break
        else
            unset missing
        fi
        sleep 1
    done
fi

if [ -n "$block_singularity" ]; then
    log INFO "blocking until Singularity images ready: $block_singularity"
    log DEBUG "Singularity cache dir: ${SINGULARITY_CACHEDIR}"
    IFS=',' read -ra RES <<< "$block_singularity"
    declare -a missing
    while :
        do
        for image in "${RES[@]}";  do
            if [ ! -f "${SINGULARITY_CACHEDIR}/${image}" ]; then
                missing=("${missing[@]}" "$image")
            fi
        done
        if [ ${#missing[@]} -eq 0 ]; then
            log INFO "all Singularity images present"
            break
        else
            unset missing
        fi
        sleep 1
    done
fi
