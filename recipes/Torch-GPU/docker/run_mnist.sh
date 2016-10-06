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

# modify training script for cuda
sed -i "/require 'paths'/a \
require 'cunn'\n\
require 'cutorch'" $train
sed -i "/testData:normalizeGlobal(mean, std)/a \
model = model:cuda()\n\
criterion = criterion:cuda()\n\
parameters,gradParameters = model:getParameters()\n\
trainData.data = trainData.data:cuda()\n\
trainData.labels = trainData.labels:cuda()\n\
testData.labels = testData.labels:cuda()" $train
sed -i "/      local targets = torch.Tensor(opt.batchSize)/a \
      inputs = inputs:cuda()\n\
      targets = targets:cuda()\n" $train

# train
th $train -t "$(nproc)" $*
