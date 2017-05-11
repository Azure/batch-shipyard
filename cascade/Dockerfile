# Dockerfile for Azure/batch-shipyard (Cascade)

FROM gliderlabs/alpine:3.4
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# set environment variables
# currently libtorrent-rasterbar 1.1.0+ DHT implementations are broken
ENV libtorrent_version=1.0.11 \
    CFLAGS=-lstdc++ PYTHON=/usr/bin/python3 PYTHON_VERSION=3.5

# add base packages, python dependencies, create script directory,
# build libtorrent-rasterbar for python3 and cleanup packaging
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev openssl-dev libffi-dev \
        ca-certificates boost boost-dev boost-python3 file curl tar pigz \
        docker bash \
    && pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir --upgrade azure-storage==0.34.2 \
    && curl -SL https://github.com/arvidn/libtorrent/releases/download/libtorrent-${libtorrent_version//./_}/libtorrent-rasterbar-${libtorrent_version}.tar.gz -o libtorrent-${libtorrent_version}.tar.gz \
    && tar zxvpf libtorrent-${libtorrent_version}.tar.gz \
    && cd libtorrent-rasterbar-${libtorrent_version} \
    && ./configure --prefix=/usr --enable-debug=no --enable-python-binding --with-boost-system=boost_system \
    && make -j2 install \
    && ldconfig /usr/lib \
    && cd .. \
    && rm -rf libtorrent-rasterbar-${libtorrent_version} \
    && rm -f libtorrent-${libtorrent_version}.tar.gz \
    && apk del --purge \
        build-base python3-dev openssl-dev libffi-dev python boost-dev \
        file curl \
    && apk add --no-cache boost-random \
    && rm /var/cache/apk/* \
    && mkdir -p /opt/batch-shipyard

# copy in files
COPY cascade.py setup_private_registry.py perf.py docker_cascade.sh /opt/batch-shipyard/

# pre-compile files
RUN python3 -m compileall -f /opt/batch-shipyard

# set command
CMD ["/opt/batch-shipyard/docker_cascade.sh"]

