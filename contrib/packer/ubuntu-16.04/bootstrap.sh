#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift

USER_MOUNTPOINT=/mnt

# install docker
apt-get update
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    apt-transport-https ca-certificates curl software-properties-common cgroup-lite
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
apt-get update
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    docker-ce=$dockerversion

# prep docker
systemctl stop docker.service
rm -rf /var/lib/docker
mkdir -p /etc/docker
echo "{ \"graph\": \"$USER_MOUNTPOINT/docker\", \"hosts\": [ \"fd://\", \"unix:///var/run/docker.sock\", \"tcp://127.0.0.1:2375\" ] }" > /etc/docker/daemon.json
sed -i 's|^ExecStart=/usr/bin/dockerd.*|ExecStart=/usr/bin/dockerd|' /lib/systemd/system/docker.service
systemctl daemon-reload
# do not auto-enable docker to start due to temp disk issues
systemctl disable docker.service
systemctl start docker.service
systemctl status docker.service
