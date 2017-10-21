#!/usr/bin/env bash

set -e

IFS='#' read -ra cip <<< "$1"
block_docker=${cip[0]}
block_singularity=${cip[1]}

echo "DEBUG: Block for Docker images: $block_docker"
echo "DEBUG: Block for Singularity images: $block_singularity"

if [ ! -z $block_docker ]; then
    echo "INFO: blocking until Docker images ready: $block_docker"
    IFS=',' read -ra RES <<< "$block_docker"
    declare -a missing
    while :
        do
        for image in "${RES[@]}";  do
            if [ -z "$(docker images -q $image 2>/dev/null)" ]; then
                missing=("${missing[@]}" "$image")
            fi
        done
        if [ ${#missing[@]} -eq 0 ]; then
            echo "INFO: all Docker images present"
            break
        else
            unset missing
        fi
        sleep 1
    done
fi

if [ ! -z $block_singularity ]; then
    echo "INFO: blocking until Singularity images ready: $block_singularity"
    echo "DEBUG: Singularity cache dir: ${SINGULARITY_CACHEDIR}"
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
            echo "INFO: all Singularity images present"
            break
        else
            unset missing
        fi
        sleep 1
    done
fi
