# Dockerfile for Caffe-GPU for use with Batch Shipyard on Azure Batch

FROM nvidia/cuda:7.5-cudnn5-devel-ubuntu14.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        wget \
        libatlas-base-dev \
        libboost-all-dev \
        libgflags-dev \
        libgoogle-glog-dev \
        libhdf5-serial-dev \
        libleveldb-dev \
        liblmdb-dev \
        libopencv-dev \
        libprotobuf-dev \
        libsnappy-dev \
        protobuf-compiler \
        python-dev \
        python-numpy \
        python-pip \
        python-scipy && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# set environment
# FIXME: clone a specific git tag and use ARG instead of ENV once DockerHub supports this.
ENV CAFFE_ROOT=/opt/caffe CAFFE_SRC=/opt/src/caffe CLONE_TAG=master
ENV PYCAFFE_ROOT=$CAFFE_ROOT/python
ENV PYTHONPATH=$PYCAFFE_ROOT:$PYTHONPATH PATH=$CAFFE_ROOT/bin:$PYCAFFE_ROOT:$PATH

# build caffe
RUN mkdir -p ${CAFFE_SRC} && \
    cd ${CAFFE_SRC} && \
    git clone -b ${CLONE_TAG} --depth 1 https://github.com/BVLC/caffe.git . && \
    for req in $(cat python/requirements.txt) pydot; do pip install $req; done && \
    mkdir build && \
    cd build && \
    cmake -DUSE_CUDNN=1 -DCMAKE_INSTALL_PREFIX:PATH=${CAFFE_ROOT} .. && \
    make -j"$(nproc)" install && \
    echo ${CAFFE_ROOT}/lib >> /etc/ld.so.conf.d/caffe.conf && \
    ldconfig && \
    ln -s ${CAFFE_SRC}/data ${CAFFE_ROOT} && \
    ln -s ${CAFFE_SRC}/docs ${CAFFE_ROOT} && \
    ln -s ${CAFFE_SRC}/examples ${CAFFE_ROOT} && \
    ln -s ${CAFFE_SRC}/models ${CAFFE_ROOT} && \
    ln -s ${CAFFE_SRC}/scripts ${CAFFE_ROOT} && \
    make clean && \
    cd .. && \
    rm -rf build

# copy in sample run script for mnist example
COPY run_mnist.sh /opt/
