# Dockerfile for Azure/batch-shipyard (Cargo)

FROM alpine:3.10
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# copy in files
COPY recurrent_job_manager.py recurrent_job_manager.sh task_file_mover.py task_file_mover.sh requirements.txt /opt/batch-shipyard/

# add base packages and python dependencies
RUN apk update \
    && apk add --update --no-cache \
        musl build-base python3 python3-dev openssl-dev libffi-dev \
        ca-certificates openssl bash \
    && python3 -m pip install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir --upgrade -r /opt/batch-shipyard/requirements.txt \
    && apk del --purge \
        build-base python3-dev openssl-dev libffi-dev \
    && rm /var/cache/apk/* \
    && rm -f /opt/batch-shipyard/requirements.txt

# pre-compile files
RUN python3 -m compileall -f /opt/batch-shipyard
