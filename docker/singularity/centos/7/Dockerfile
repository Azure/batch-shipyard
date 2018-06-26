# Dockerfile for Singularity on CentOS 7 for Batch Shipyard

FROM centos:7
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

WORKDIR /tmp
ENV SINGULARITY_VERSION=2.5.1

RUN yum groupinstall -y \
        "Development Tools" \
    && yum install -y \
        curl \
        python \
        file \
        libarchive-devel \
    && yum clean all

RUN curl -fSsL https://github.com/singularityware/singularity/releases/download/${SINGULARITY_VERSION}/singularity-${SINGULARITY_VERSION}.tar.gz | tar -zxvpf - \
    && cd singularity-${SINGULARITY_VERSION} \
    && ./configure --prefix=/opt/singularity --sysconfdir=/opt/singularity/etc --localstatedir=/mnt/resource \
    && make -j4 \
    && make install

FROM alpine:3.7

COPY --from=0 /opt/singularity /singularity
