# Dockerfile for Azure/batch-shipyard (Cascade libtorrent multi-stage base)

FROM alpine:3.8
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# set environment variables
ENV libtorrent_version=1.1.9 \
    CFLAGS=-lstdc++ PYTHON=/usr/bin/python3 PYTHON_VERSION=3.6

# build libtorrent-rasterbar for python3 and cleanup packaging
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev libressl-dev libffi-dev \
        boost boost-dev boost-python3 file curl tar bash \
    && curl -SL https://github.com/arvidn/libtorrent/releases/download/libtorrent-${libtorrent_version//./_}/libtorrent-rasterbar-${libtorrent_version}.tar.gz -o libtorrent-${libtorrent_version}.tar.gz \
    && tar zxvpf libtorrent-${libtorrent_version}.tar.gz \
    && cd libtorrent-rasterbar-${libtorrent_version} \
    && ./configure --prefix=/usr --enable-debug=no --enable-python-binding --with-boost-system=boost_system \
    && make -j"$(nproc)" install \
    && ldconfig /usr/lib \
    && cd .. \
    && rm -rf libtorrent-rasterbar-${libtorrent_version} \
    && rm -f libtorrent-${libtorrent_version}.tar.gz \
    && apk del --purge \
        build-base python3-dev libressl-dev libffi-dev python boost-dev \
        file curl \
    && rm /var/cache/apk/*
