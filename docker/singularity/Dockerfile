# Dockerfile for Singularity

FROM ubuntu:18.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        libssl-dev \
        uuid-dev \
        libgpgme11-dev \
        squashfs-tools \
        libseccomp-dev \
        pkg-config \
        curl \
        file \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV GO_VERSION=1.12 \
    GOOS=linux \
    GOARCH=amd64

RUN cd /usr/local \
    && curl -fSsL https://dl.google.com/go/go${GO_VERSION}.linux-amd64.tar.gz | tar -zxpf - \
    && export GOPATH=${HOME}/go \
    && export PATH=/usr/local/go/bin:${PATH}:${GOPATH}/bin \
    && go get -u github.com/golang/dep

ARG LOCAL_STATE_DIR

#ENV SINGULARITY_VERSION=3.3.0
#    && curl -fSsL https://github.com/sylabs/singularity/releases/download/${SINGULARITY_VERSION}/singularity-${SINGULARITY_VERSION}.tar.gz | tar -zxvpf - \
#    && cd singularity-${SINGULARITY_VERSION} \
#    && rm -rf singularity-${SINGULARITY_VERSION} \

RUN export GOPATH=${HOME}/go \
    && export PATH=/usr/local/go/bin:${PATH}:${GOPATH}/bin \
    && cd /tmp \
    && git clone -b master --single-branch https://github.com/sylabs/singularity.git \
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
