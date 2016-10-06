#!/usr/bin/env bash

set -e

# load torch env
. $TORCH_ROOT/install/bin/torch-activate

# set vars
github_url=https://raw.githubusercontent.com/torch/demos/master/train-a-digit-classifier
dataset=dataset-mnist.lua
train=train-on-mnist.lua

# retrieve files
curl -O $github_url/$dataset
curl -O $github_url/$train

# train
th $train -t "$(nproc)" $*
