# Dockerfile for Slurm on CentOS 7 for Batch Shipyard

FROM centos:7
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

WORKDIR /tmp
ENV SLURM_VERSION=18.08.5-2

RUN yum install -y epel-release \
    && yum makecache -y fast \
    && yum groupinstall -y \
        "Development Tools" \
    && yum install -y \
        curl \
        file \
        python \
        perl-devel \
        openssl-devel \
        openssl \
        ruby \
        ruby-devel \
        munge-devel \
        pam-devel \
        mariadb-devel \
        numactl-devel \
        numactl \
        hwloc-devel \
        hwloc \
    && gem install fpm \
    && yum clean all

RUN curl -fSsL https://download.schedmd.com/slurm/slurm-${SLURM_VERSION}.tar.bz2 | tar -jxpf - \
    && cd slurm-${SLURM_VERSION} \
    && ./configure --prefix=/tmp/slurm-build --sysconfdir=/etc/slurm --with-pam_dir=/usr/lib64/security/ \
    && make -j4 \
    && make -j4 contrib \
    && make install \
    && cd /root \
    && fpm -s dir -t rpm -v 1.0 -n slurm-${SLURM_VERSION} --prefix=/usr -C /tmp/slurm-build .

FROM alpine:3.10

COPY --from=0 /root/slurm-*.rpm /root/
COPY slurm*.service /root/
