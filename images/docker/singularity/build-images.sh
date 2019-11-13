#!/usr/bin/env bash

set -e
set -o pipefail

SINGULARITY_VERSION=$(grep -m1 _SINGULARITY_VERSION ../../../convoy/misc.py | cut -d "'" -f 2)
REPO=alfpark/singularity

echo "Extracted Singularity Version: $SINGULARITY_VERSION"
echo "Publishing to repo: $REPO"

LSD=(/var/lib /mnt /mnt/resource)
TAGS=(default mnt mnt-resource)

i=0
for lsd in "${LSD[@]}"; do
    tag="-${TAGS[$i]}"
    if [ "$tag" == "-default" ]; then
        tag=""
    fi
    di="${REPO}:${SINGULARITY_VERSION}${tag}"
    docker build --pull -t "$di" --build-arg SINGULARITY_VERSION="$SINGULARITY_VERSION" --build-arg LOCAL_STATE_DIR="$lsd" -f Dockerfile .
    docker push "$di"
    i=$((i + 1))
done
