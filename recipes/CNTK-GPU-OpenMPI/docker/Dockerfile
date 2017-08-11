# Dockerfile for CNTK-GPU-OpenMPI for use with Batch Shipyard on Azure Batch

FROM nvidia/cuda:8.0-runtime-ubuntu14.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

COPY ssh_config /root/.ssh/config
RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo \
        ca-certificates \
        wget \
        openssh-client \
        openssh-server \
        iproute2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    # configure ssh server and keys
    && mkdir /var/run/sshd \
    && ssh-keygen -A \
    && sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config \
    && sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd \
    && ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' \
    && chmod 600 /root/.ssh/config \
    && chmod 700 /root/.ssh \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# Get CNTK Binary Distribution
ENV CNTK_VERSION="2.1"
RUN CNTK_VERSION_DASHED=$(echo $CNTK_VERSION | tr . -) && \
    CNTK_SHA256="1a4384918bc6bc4e9f7ddc7bb0cfdb08e0ef5d2d7f1060706c81338f41802d87" && \
    wget -q https://cntk.ai/BinaryDrop/CNTK-${CNTK_VERSION_DASHED}-Linux-64bit-GPU-1bit-SGD.tar.gz && \
    echo "$CNTK_SHA256 CNTK-${CNTK_VERSION_DASHED}-Linux-64bit-GPU-1bit-SGD.tar.gz" | sha256sum --check --strict - && \
    tar -xzf CNTK-${CNTK_VERSION_DASHED}-Linux-64bit-GPU-1bit-SGD.tar.gz && \
    rm -f CNTK-${CNTK_VERSION_DASHED}-Linux-64bit-GPU-1bit-SGD.tar.gz && \
    /bin/bash /cntk/Scripts/install/linux/install-cntk.sh --py-version 35 --docker

WORKDIR /cntk

# make sshd listen on 23 and run by default
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]

COPY run_cntk.sh /cntk/
