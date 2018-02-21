#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift

# install LIS
curl -fSsL http://download.microsoft.com/download/6/8/F/68FE11B8-FAA4-4F8D-8C7D-74DA7F2CFC8C/lis-rpms-4.2.3-5.tar.gz | tar -zxvpf -
cd LISISO
./install.sh
cd ..
rm -rf LISISO
shutdown -r now

# install docker
yum install -y yum-utils device-mapper-persistent-data lvm2
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
yum makecache -y fast
yum install -y docker-ce-${dockerversion}

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
