# Dockerfile for Azure/batch-shipyard (cli)

FROM python:3.9.4-alpine3.13
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

ARG GIT_BRANCH
ARG GIT_COMMIT

RUN apk update \
    && apk add --update --no-cache \
        musl build-base openssl-dev libffi-dev rust cargo ca-certificates git \
        openssl openssh-client rsync bash \
    && python3 -m ensurepip --upgrade \
    && pip3 install --no-cache-dir --upgrade pip setuptools setuptools-rust wheel \
    && git clone -b $GIT_BRANCH --single-branch https://github.com/Azure/batch-shipyard.git /opt/batch-shipyard \
    && cd /opt/batch-shipyard \
    && git checkout $GIT_COMMIT \
    && rm -rf .git .github .vsts \
    && rm -f .git* .travis.yml *.yml install* \
    && pip3 install --no-cache-dir -r requirements.txt \
    && python3 -m compileall -f /opt/batch-shipyard/shipyard.py /opt/batch-shipyard/convoy \
    && pip3 uninstall -y setuptools-rust wheel \
    && apk del --purge build-base patch openssl-dev libffi-dev rust cargo git \
    && rm /var/cache/apk/*
    && rm -rf /root/.cache /root/.cargo

ENTRYPOINT ["/opt/batch-shipyard/shipyard.py"]
