# Dockerfile for Azure/batch-shipyard (Task file mover)

FROM gliderlabs/alpine:3.4
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# add base packages and python dependencies
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev openssl-dev libffi-dev \
        ca-certificates openssl bash \
    && pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir --upgrade azure-batch==1.1.0 \
    && apk del --purge \
        build-base python3-dev openssl-dev libffi-dev \
    && rm /var/cache/apk/*

# copy in files
COPY task_file_mover.py task_file_mover.sh /opt/batch-shipyard/

# pre-compile files
RUN python3 -m compileall -f /opt/batch-shipyard

# set entrypoint
ENTRYPOINT ["/opt/batch-shipyard/task_file_mover.sh"]
