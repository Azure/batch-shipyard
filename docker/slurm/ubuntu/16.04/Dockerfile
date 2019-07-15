# Dockerfile for Slurm on Ubuntu 16.04 for Batch Shipyard

FROM ubuntu:16.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

WORKDIR /tmp
ENV SLURM_VERSION=18.08.5-2

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        file \
        python \
        libssl-dev \
        openssl \
        ruby \
        ruby-dev \
        libmunge-dev \
        libpam0g-dev \
        libmariadb-client-lgpl-dev \
        libmysqlclient-dev \
        libnuma-dev \
        numactl \
        libhwloc-dev \
        hwloc \
    && gem install fpm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fSsL https://download.schedmd.com/slurm/slurm-${SLURM_VERSION}.tar.bz2 | tar -jxvpf - \
    && cd slurm-${SLURM_VERSION} \
    && ./configure --prefix=/tmp/slurm-build --sysconfdir=/etc/slurm --with-pam_dir=/lib/x86_64-linux-gnu/security/ \
    && make -j4 \
    && make -j4 contrib \
    && make install \
    && cd /root \
    && fpm -s dir -t deb -v 1.0 -n slurm-${SLURM_VERSION} --prefix=/usr -C /tmp/slurm-build .

FROM alpine:3.10

COPY --from=0 /root/slurm-*.deb /root/
COPY slurm*.service /root/
