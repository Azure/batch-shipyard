# Dockerfile for Singularity

FROM ubuntu:18.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

ARG SINGULARITY_VERSION
ARG LOCAL_STATE_DIR

ENV GO_VERSION=1.13.4 \
    GOOS=linux \
    GOARCH=amd64

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        libssl-dev \
        uuid-dev \
        libgpgme11-dev \
        squashfs-tools \
        libseccomp-dev \
        cryptsetup-bin \
        pkg-config \
        curl \
        file \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN cd /usr/local \
    && curl -fSsL https://dl.google.com/go/go${GO_VERSION}.linux-amd64.tar.gz | tar -zxpf - \
    && export GOPATH=${HOME}/go \
    && export PATH=/usr/local/go/bin:${PATH}:${GOPATH}/bin \
    && go get -u github.com/golang/dep

RUN export GOPATH=${HOME}/go \
    && export PATH=/usr/local/go/bin:${PATH}:${GOPATH}/bin \
    && cd /tmp \
    && curl -fSsL https://github.com/sylabs/singularity/releases/download/v${SINGULARITY_VERSION}/singularity-${SINGULARITY_VERSION}.tar.gz | tar -zxvpf - \
    && cd singularity \
    && ./mconfig --prefix=/opt/singularity --sysconfdir=/opt/singularity/etc --localstatedir=${LOCAL_STATE_DIR} \
    && cd builddir \
    && make -j"$(nproc)" \
    && make install \
    && cd .. \
    && rm -rf singularity \
    && ldconfig /opt/singularity/lib/singularity \
    && ln -s /opt/singularity/bin/singularity /usr/bin/singularity

FROM alpine:3.10

COPY --from=0 /opt/singularity /opt/singularity
