# Dockerfile for Torch-CPU for use with Batch Shipyard on Azure Batch

FROM ubuntu:16.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

RUN DEBIAN_FRONTEND=noninteractive && \
    apt-get update && apt-get install -y --no-install-recommends \
        apt-utils software-properties-common cron python-apt python-pycurl \
        unattended-upgrades && \
    apt-get install -y --no-install-recommends \
        build-essential sudo curl wget cmake git-core unzip && \
    apt-get install -y --no-install-recommends \
        gfortran gcc-4.9 libgfortran-4.9-dev g++-4.9 && \
    apt-get install -y --no-install-recommends \
        libfftw3-dev sox libsox-dev libsox-fmt-all libreadline-dev \
        libzmq3-dev ipython && \
    apt-get install -y --no-install-recommends \
        imagemagick libgraphicsmagick1-dev libqt4-dev libjpeg-dev libpng-dev \
        ncurses-dev && \
    apt-get install -y --no-install-recommends \
        gnuplot gnuplot-x11 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# set environment
ENV TORCH_ROOT=/root/torch

# build openblas and torch
RUN cd tmp && \
    git clone https://github.com/xianyi/OpenBLAS.git && \
    cd OpenBLAS && \
    make NO_AFFINITY=1 USE_OPENMP=1 -j"$(nproc)" && \
    make install && \
    cd .. && \
    rm -rf OpenBLAS && \
    mkdir -p ${TORCH_ROOT} && \
    cd ${TORCH_ROOT} && \
    git clone https://github.com/torch/distro.git . --recursive && \
    ./install.sh

# copy in sample run script for mnist example
COPY run_mnist.sh ${TORCH_ROOT}
