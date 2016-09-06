#!/usr/bin/env bash

set -e

# set vars
BIN=$CAFFE_ROOT/bin
MNIST_DIR=examples/mnist
DATA=data/mnist
BACKEND="lmdb"

# get data set
mkdir -p $DATA
cp $CAFFE_ROOT/data/mnist/get_mnist.sh $DATA
$DATA/get_mnist.sh

# create LMDB db
echo "Creating ${BACKEND}..."
mkdir -p $MNIST_DIR
rm -rf $MNIST_DIR/mnist_train_${BACKEND}
rm -rf $MNIST_DIR/mnist_test_${BACKEND}
$BIN/convert_mnist_data $DATA/train-images-idx3-ubyte \
    $DATA/train-labels-idx1-ubyte $MNIST_DIR/mnist_train_${BACKEND} \
    --backend=${BACKEND}
$BIN/convert_mnist_data $DATA/t10k-images-idx3-ubyte \
    $DATA/t10k-labels-idx1-ubyte $MNIST_DIR/mnist_test_${BACKEND} \
    --backend=${BACKEND}
echo "Done."

# prep train spec and switch solver mode to default to cpu
cp $CAFFE_ROOT/examples/mnist/lenet_solver.prototxt $MNIST_DIR
cp $CAFFE_ROOT/examples/mnist/lenet_train_test.prototxt $MNIST_DIR
sed -i 's#solver_mode: GPU#solver_mode: CPU##' $MNIST_DIR/lenet_solver.prototxt

# train
$BIN/caffe train --solver=$MNIST_DIR/lenet_solver.prototxt $*
