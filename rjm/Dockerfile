# Dockerfile for Azure/batch-shipyard (Recurrent job manager)

FROM alpine:3.6
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# copy in files
COPY recurrent_jm.py requirements.txt /opt/batch-shipyard/

# add base packages and python dependencies
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev libressl-dev libffi-dev \
        ca-certificates libressl bash \
    && pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir --upgrade -r /opt/batch-shipyard/requirements.txt \
    && apk del --purge \
        build-base python3-dev libressl-dev libffi-dev \
    && rm /var/cache/apk/* \
    && rm -f /opt/batch-shipyard/requirements.txt

# pre-compile files
RUN python3 -m compileall -f /opt/batch-shipyard

# set entrypoint
ENTRYPOINT ["/opt/batch-shipyard/recurrent_jm.py"]
