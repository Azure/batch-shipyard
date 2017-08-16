# Dockerfile for Azure/batch-shipyard (Cascade)

# base image containing libtorrent
FROM alfpark/libtorrent:1.0.11-py36

FROM alpine:3.6
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# copy libtorrent dynlib and python package from base
COPY --from=0 /usr/lib/libtorrent-rasterbar.so.8.0.0 /usr/lib/
COPY --from=0 /usr/lib/python3.6/site-packages/*libtorrent* /usr/lib/python3.6/site-packages/

# add dependencies, symlink libtorrent, create script directory
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev libressl-dev libffi-dev \
        ca-certificates boost boost-python3 boost-random \
        tar pigz docker bash \
    && pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir --upgrade azure-storage==0.35.1 \
    && ln -s /usr/lib/libboost_python3.so.1.62.0 /usr/lib/libboost_python.so.1.62.0 \
    && ln -s /usr/lib/libtorrent-rasterbar.so.8.0.0 /usr/lib/libtorrent-rasterbar.so \
    && ln -s /usr/lib/libtorrent-rasterbar.so.8.0.0 /usr/lib/libtorrent-rasterbar.so.8 \
    && ldconfig /usr/lib \
    && apk del --purge \
        build-base python3-dev libressl-dev libffi-dev \
    && rm /var/cache/apk/* \
    && mkdir -p /opt/batch-shipyard

# copy in files
COPY cascade.py setup_private_registry.py perf.py docker_cascade.sh /opt/batch-shipyard/

# pre-compile files
RUN python3 -m compileall -f /opt/batch-shipyard

# set command
CMD ["/opt/batch-shipyard/docker_cascade.sh"]

