#!/usr/bin/env bash

set -e
set -o pipefail

offer=$1
sku=$2

if [ $offer == "ubuntuserver" ] || [ $offer == "debian" ]; then
    if [[ $sku == 14.04* ]]; then
        srvrestart="initctl restart sshd"
        mkdir /tmp/hpnssh
        pushd /tmp/hpnssh
        wget https://launchpad.net/~yoda-jazz-kc/+archive/ubuntu/hpn-ssh/+files/openssh-client_6.6p1-hpn14v5-1~ubuntu14.04.1_amd64.deb
        wget https://launchpad.net/~yoda-jazz-kc/+archive/ubuntu/hpn-ssh/+files/openssh-server_6.6p1-hpn14v5-1~ubuntu14.04.1_amd64.deb
        wget https://launchpad.net/~yoda-jazz-kc/+archive/ubuntu/hpn-ssh/+files/openssh-sftp-server_6.6p1-hpn14v5-1~ubuntu14.04.1_amd64.deb
        dpkg -i --force-confold openssh-*.deb
        popd
        rm -rf /tmp/hpnssh
    elif [[ $sku == 16.04* ]]; then
        srvrestart="systemctl restart sshd"
        mkdir /tmp/hpnssh
        pushd /tmp/hpnssh
        wget https://launchpad.net/~yoda-jazz-kc/+archive/ubuntu/hpn-ssh/+files/openssh-client_7.1p2-hpn14v9-2~ubuntu16.04.1_amd64.deb
        wget https://launchpad.net/~yoda-jazz-kc/+archive/ubuntu/hpn-ssh/+files/openssh-server_7.1p2-hpn14v9-2~ubuntu16.04.1_amd64.deb
        wget https://launchpad.net/~yoda-jazz-kc/+archive/ubuntu/hpn-ssh/+files/openssh-sftp-server_7.1p2-hpn14v9-2~ubuntu16.04.1_amd64.deb
        dpkg -i --force-confold openssh-*.deb
        popd
        rm -rf /tmp/hpnssh
    else
        echo "OpenSSH-HPN is not supported on this sku: $sku for offer $offer"
        exit 1
    fi
    # modify sshd config settings
    echo "HPNDisabled=no" >> /etc/ssh/sshd_config
    echo "TcpRcvBufPoll=yes" >> /etc/ssh/sshd_config
    echo "NoneEnabled=yes" >> /etc/ssh/sshd_config
    # restart sshd
    $srvrestart
elif [[ $offer == centos* ]] || [[ $offer == "rhel" ]] || [[ $offer == "oracle-linux" ]]; then
    echo "OpenSSH-HPN is not supported on this sku: $sku for offer $offer"
    exit 1
elif [[ $offer == opensuse* ]] || [[ $offer == sles* ]]; then
    echo "OpenSSH-HPN is not supported on this sku: $sku for offer $offer"
    exit 1
else
    echo "OpenSSH-HPN is not supported on this sku: $sku for offer $offer"
    exit 1
fi
