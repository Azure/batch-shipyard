#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift

# temporarily stop yum service conflicts if applicable
set +e
systemctl stop yum.cron
systemctl stop packagekit
set -e

# temporarily stop waagent
systemctl stop waagent.service

# cleanup any aborted yum transactions
yum-complete-transaction --cleanup-only

# temporarily stop hv services
set +e
systemctl stop hv_kvp_daemon.service
systemctl stop hv_vss_daemon.service
set -e

# install hypervkvpd
curl -fSsLO http://vault.centos.org/7.1.1503/os/x86_64/Packages/hyperv-daemons-license-0-0.25.20141008git.el7.noarch.rpm
curl -fSsLO http://vault.centos.org/7.1.1503/os/x86_64/Packages/hypervkvpd-0-0.25.20141008git.el7.x86_64.rpm
rpm -Uvh hyperv-daemons-license-0-0.25.20141008git.el7.noarch.rpm hypervkvpd-0-0.25.20141008git.el7.x86_64.rpm
rm -f hyperv*.rpm

# install rdma driver
set +e
yum erase -y microsoft-hyper-v-rdma-kmod microsoft-hyper-v-rdma
set -e
rpm -Uvh /opt/microsoft/rdma/rhel71/kmod-microsoft-hyper-v-rdma-4.2.3.1.144-20180209.x86_64.rpm
rpm -Uvh /opt/microsoft/rdma/rhel71/microsoft-hyper-v-rdma-4.2.3.1.144-20180209.x86_64.rpm

# install docker
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
yum makecache -y fast
yum install -y yum-utils device-mapper-persistent-data lvm2 docker-ce-${dockerversion}

# prep docker
set +e
systemctl stop docker.service
set -e
mkdir -p /mnt/resource/docker-tmp
sed -i -e 's,.*export DOCKER_TMPDIR=.*,export DOCKER_TMPDIR="/mnt/resource/docker-tmp",g' /etc/default/docker || echo export DOCKER_TMPDIR=\"/mnt/resource/docker-tmp\" >> /etc/default/docker
sed -i -e '/^DOCKER_OPTS=.*/,${s||DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\"|;b};$q1' /etc/default/docker || echo DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\" >> /etc/default/docker
sed -i '/^\[Service\]/a EnvironmentFile=/etc/default/docker' /lib/systemd/system/docker.service
sed -i '/^ExecStart=/ s/$/ $DOCKER_OPTS/' /lib/systemd/system/docker.service
systemctl daemon-reload
# do not auto-enable docker to start due to temp disk issues
systemctl disable docker.service
systemctl start docker.service
systemctl status docker.service

# complete all outstanding yum transactions
yum-complete-transaction
