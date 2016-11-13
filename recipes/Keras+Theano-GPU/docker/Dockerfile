# Dockerfile for Keras+Theano-GPU for use with Batch Shipyard on Azure Batch

FROM nvidia/cuda:7.5-cudnn5-devel
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gfortran \
        git \
        wget \
        curl \
        ca-certificates \
        libhdf5-dev \
        liblapack-dev \
        libopenblas-dev \
        python-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# upgrade pip and install dependencies
RUN curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | python && \
    pip install --upgrade --no-cache-dir setuptools wheel six && \
    pip install --upgrade --no-cache-dir pyyaml nose h5py && \
    pip install --upgrade --no-cache-dir numpy && \
    pip install --upgrade --no-cache-dir scipy

# install theano and keras
RUN pip install --upgrade --no-deps git+git://github.com/Theano/Theano.git && \
    git clone https://github.com/fchollet/keras.git && \
    cd keras && \
    python setup.py install

# set keras backend to theano
ENV KERAS_BACKEND=theano

# copy in default theanorc file
COPY theanorc /root/.theanorc
