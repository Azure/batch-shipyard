# Dockerfile for TensorFlow-GPU for use with Batch Shipyard on Azure Batch
# Adapted from official TensorFlow Dockerfile.devel-gpu

FROM nvidia/cuda:8.0-cudnn5-devel
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# We need to add a custom PPA to pick up JDK8, since trusty doesn't
# have an openjdk8 backport.  openjdk-r is maintained by a reliable contributor:
# Matthias Klose (https://launchpad.net/~doko).  It will do until
# we either update the base image beyond 14.04 or openjdk-8 is
# finally backported to trusty; see e.g.
#   https://bugs.launchpad.net/trusty-backports/+bug/1368094
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        libcurl3-dev \
        libfreetype6-dev \
        libpng12-dev \
        libzmq3-dev \
        pkg-config \
        python \
        python-dev \
        rsync \
        software-properties-common \
        swig \
        unzip \
        zip \
        zlib1g-dev \
        && \
    add-apt-repository -y ppa:openjdk-r/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
        openjdk-8-jdk openjdk-8-jre-headless \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fSsL https://bootstrap.pypa.io/get-pip.py | python && \
    pip install --no-cache-dir \
        ipykernel \
        jupyter \
        matplotlib \
        numpy \
        scipy \
        sklearn \
        && \
    python -m ipykernel.kernelspec

# Set up our notebook config.
COPY jupyter_notebook_config.py /root/.jupyter/

# Jupyter has issues with being run directly:
#   https://github.com/ipython/ipython/issues/7062
# We just add a little wrapper script.
COPY run_jupyter.sh /

# Set up Bazel.

ENV BAZELRC /root/.bazelrc
# Install the most recent bazel release.
ENV BAZEL_VERSION 0.3.2
# Running bazel inside a `docker build` command causes trouble, cf:
#   https://github.com/bazelbuild/bazel/issues/134
# The easiest solution is to set up a bazelrc file forcing --batch.
RUN echo "startup --batch" >>/root/.bazelrc && \
# Similarly, we need to workaround sandboxing issues:
#   https://github.com/bazelbuild/bazel/issues/418
    echo "build --spawn_strategy=standalone --genrule_strategy=standalone" >>/root/.bazelrc && \
    cd / && \
    mkdir /bazel && \
    cd /bazel && \
    curl -fSsL -O https://github.com/bazelbuild/bazel/releases/download/$BAZEL_VERSION/bazel-$BAZEL_VERSION-installer-linux-x86_64.sh && \
    curl -fSsL -o /bazel/LICENSE.txt https://raw.githubusercontent.com/bazelbuild/bazel/master/LICENSE.txt && \
    chmod +x bazel-*.sh && \
    ./bazel-$BAZEL_VERSION-installer-linux-x86_64.sh && \
    cd / && \
    rm -f /bazel/bazel-$BAZEL_VERSION-installer-linux-x86_64.sh

# Download and build TensorFlow.

# Configure the build for our CUDA configuration.
ENV LD_LIBRARY_PATH /usr/local/cuda/extras/CUPTI/lib64:$LD_LIBRARY_PATH
ENV TF_NEED_CUDA 1
ENV TF_CUDA_COMPUTE_CAPABILITIES=3.7,5.2

RUN cd / && \
    git clone https://github.com/tensorflow/tensorflow.git && \
    cd tensorflow && \
    git checkout r0.11 && \
    tensorflow/tools/ci_build/builds/configured GPU \
    bazel build -c opt --config=cuda tensorflow/tools/pip_package:build_pip_package && \
    bazel-bin/tensorflow/tools/pip_package/build_pip_package /tmp/pip && \
    pip install --upgrade /tmp/pip/tensorflow-*.whl && \
    rm -rf /tmp/pip && \
    rm -rf /root/.cache
# Clean up pip wheel and Bazel cache when done.

# TensorBoard
EXPOSE 6006
# IPython
EXPOSE 8888

WORKDIR "/notebooks"

CMD ["/run_jupyter.sh"]
