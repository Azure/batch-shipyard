#!/usr/bin/env bash

set -e
set -o pipefail

IMAGE_NAME=$1
CIFAR_DATA=$2

BASEDIR=$(pwd)

docker run --rm -v $CIFAR_DATA:$CIFAR_DATA -w $CIFAR_DATA -v $BASEDIR:/code $IMAGE_NAME /bin/bash -c "source /cntk/activate-cntk; python -u /code/cifar_data_processing.py --datadir $CIFAR_DATA"