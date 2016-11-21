# Dockerfile for Caffe-CPU for use with Batch Shipyard on Azure Batch

FROM ubuntu:14.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        wget \
        curl \
        gfortran \
        libopenblas-dev \
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
    rm -rf /var/lib/apt/lists/* && \
    curl -fSsL https://bootstrap.pypa.io/get-pip.py | python

# set environment
# FIXME: clone a specific git tag and use ARG instead of ENV once DockerHub supports this.
ENV CAFFE_ROOT=/caffe CLONE_TAG=master
ENV CAFFE_BUILD=${CAFFE_ROOT}/build
ENV PYCAFFE_ROOT=${CAFFE_BUILD}/python CAFFE_BIN=${CAFFE_BUILD}/tools CAFFE_EXAMPLES=${CAFFE_BUILD}/examples
ENV PYTHONPATH=${PYCAFFE_ROOT}:$PYTHONPATH PATH=${CAFFE_BIN}:${PYCAFFE_ROOT}:$PATH

# build caffe
RUN mkdir -p ${CAFFE_ROOT} && \
    cd ${CAFFE_ROOT} && \
    git clone -b ${CLONE_TAG} --depth 1 https://github.com/BVLC/caffe.git . && \
    for req in $(cat python/requirements.txt) pydot; do pip install --no-cache-dir $req; done && \
    mkdir build && \
    cd build && \
    cmake -DCPU_ONLY=1 -DBLAS=open -DCMAKE_INSTALL_PREFIX:PATH=${CAFFE_ROOT} .. && \
    make -j"$(nproc)" install && \
    echo ${CAFFE_BUILD}/lib >> /etc/ld.so.conf.d/caffe.conf && \
    ldconfig && \
    find ${CAFFE_BUILD}/ -name '*.o' -print0 | xargs -0 rm

# copy in sample run script for mnist example
COPY run_mnist.sh ${CAFFE_ROOT}
