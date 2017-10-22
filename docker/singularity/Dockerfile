# Dockerfile for Singularity 2.4

FROM alpine:3.6
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

RUN apk update \
    && apk add --update --no-cache \
        curl file build-base autoconf automake libtool linux-headers \
        tar gzip bash python squashfs-tools \
    && cd /tmp \
    && curl -fSsL https://github.com/singularityware/singularity/releases/download/2.4/singularity-2.4.tar.gz | tar -zxvpf - \
    && cd singularity-2.4 \
    && ./configure --prefix=/opt/singularity --sysconfdir=/opt/singularity/etc --localstatedir=/var/lib \
    && make -j4 \
    && make install \
    && cd .. \
    && rm -rf singularity-2.4 \
    && ldconfig /opt/singularity/lib/singularity \
    && ln -s /opt/singularity/bin/singularity /usr/bin/singularity \
    && apk del --purge \
        curl file build-base autoconf automake libtool linux-headers
