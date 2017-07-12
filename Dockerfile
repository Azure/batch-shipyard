# Dockerfile for Azure/batch-shipyard (cli)

FROM alpine:3.6
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# add base packages and python dependencies
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev libressl-dev libffi-dev \
        ca-certificates libressl openssh-client rsync git bash \
    && pip3 install --no-cache-dir --upgrade pip \
    && git clone -b master --single-branch https://github.com/Azure/batch-shipyard.git /opt/batch-shipyard \
    && cd /opt/batch-shipyard \
    && rm -rf .git \
    && rm -f .git* .travis.yml install* \
    && pip3 install --no-cache-dir -r requirements.txt \
    && python3 -m compileall -f /opt/batch-shipyard \
    && apk del --purge \
        build-base python3-dev libressl-dev libffi-dev git \
    && rm /var/cache/apk/*

# set working dir
WORKDIR /opt/batch-shipyard

# set entrypoint
ENTRYPOINT ["/opt/batch-shipyard/shipyard.py"]
