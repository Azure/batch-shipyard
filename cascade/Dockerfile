# Dockerfile for Azure/batch-shipyard (Cascade)

# base image containing libtorrent
FROM alfpark/libtorrent:1.0.11-py36

# base image containing singularity
FROM alfpark/singularity:2.4.5

FROM alpine:3.7
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# copy libtorrent dynlib and python package from base
COPY --from=0 /usr/lib/libtorrent-rasterbar.so.8.0.0 /usr/lib/
COPY --from=0 /usr/lib/python3.6/site-packages/*libtorrent* /usr/lib/python3.6/site-packages/

# copy singularity
COPY --from=1 /opt/singularity /opt/singularity

# copy in files
COPY cascade.py perf.py cascade.sh requirements.txt /opt/batch-shipyard/

# add dependencies, symlink libtorrent, compile python files
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev libressl-dev libffi-dev \
        ca-certificates boost boost-python3 boost-random \
        tar pigz docker python squashfs-tools bash \
    && pip3 install --no-cache-dir --upgrade -r /opt/batch-shipyard/requirements.txt \
    && ln -s /usr/lib/libboost_python3.so.1.62.0 /usr/lib/libboost_python.so.1.62.0 \
    && ln -s /usr/lib/libtorrent-rasterbar.so.8.0.0 /usr/lib/libtorrent-rasterbar.so \
    && ln -s /usr/lib/libtorrent-rasterbar.so.8.0.0 /usr/lib/libtorrent-rasterbar.so.8 \
    && ldconfig /usr/lib \
    && ln -s /opt/singularity/bin/singularity /usr/bin/singularity \
    && ldconfig /opt/singularity/lib/singularity \
    && apk del --purge build-base python3-dev libressl-dev libffi-dev \
    && rm /var/cache/apk/* \
    && python3 -m compileall -f /opt/batch-shipyard

# set command
CMD ["/opt/batch-shipyard/cascade.sh"]
