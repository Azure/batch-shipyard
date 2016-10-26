# Dockerfile for Azure/batch-shipyard (cli)

FROM gliderlabs/alpine:3.4
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# add base packages and python dependencies
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev openssl-dev libffi-dev \
        ca-certificates openssl openssh-client rsync git bash \
    && pip3 install --no-cache-dir --upgrade pip \
    && git clone https://github.com/Azure/batch-shipyard.git /opt/batch-shipyard \
    && cd /opt/batch-shipyard \
    && pip3 install -r requirements.txt \
    && apk del --purge \
        build-base python3-dev openssl-dev libffi-dev \
    && rm /var/cache/apk/*

# set working dir
WORKDIR /opt/batch-shipyard

# set entrypoint
ENTRYPOINT ["/opt/batch-shipyard/shipyard.py"]
