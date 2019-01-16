# Dockerfile for Singularity on Ubuntu 16.04 for Batch Shipyard

FROM ubuntu:16.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

WORKDIR /tmp
ENV SINGULARITY_VERSION=2.6.1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        python \
        file \
        libarchive-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fSsL https://github.com/sylabs/singularity/releases/download/${SINGULARITY_VERSION}/singularity-${SINGULARITY_VERSION}.tar.gz | tar -zxvpf - \
    && cd singularity-${SINGULARITY_VERSION} \
    && ./configure --prefix=/opt/singularity --sysconfdir=/opt/singularity/etc --localstatedir=/mnt \
    && make -j4 \
    && make install

FROM alpine:3.8

COPY --from=0 /opt/singularity /singularity
