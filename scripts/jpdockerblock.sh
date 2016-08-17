#!/usr/bin/env bash

set -e

declare -a missing

while :
    do
    for image in "$@"; do
        if [ -z "$(docker images -q $image 2>/dev/null)" ]; then
            missing=("${missing[@]}" "$image")
        fi
    done
    if [ ${#missing[@]} -eq 0 ]; then
        echo "all docker images present"
        break
    else
        echo "docker images missing: ${missing[@]}"
        unset missing
    fi
    sleep 1
done
