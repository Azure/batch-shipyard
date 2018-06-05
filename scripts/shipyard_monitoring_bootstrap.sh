#!/usr/bin/env bash

# shellcheck disable=SC1091

set -e
set -o pipefail

# version consts
DOCKER_CE_VERSION_DEBIAN=18.05.0

# consts
# TODO switch version back to stable
DOCKER_CE_PACKAGE_DEBIAN="docker-ce=${DOCKER_CE_VERSION_DEBIAN}~ce~3-0~"
SHIPYARD_VAR_DIR=/var/batch-shipyard
SHIPYARD_CONF_FILE=${SHIPYARD_VAR_DIR}/heimdall.json
PROMETHEUS_VAR_DIR=${SHIPYARD_VAR_DIR}/prometheus
GRAFANA_PROVISIONING_DIR=${SHIPYARD_VAR_DIR}/grafana/provisioning
NGINX_VAR_DIR=${SHIPYARD_VAR_DIR}/nginx
LETSENCRYPT_VAR_DIR=${SHIPYARD_VAR_DIR}/letsencrypt

log() {
    local level=$1
    shift
    echo "$(date -u -Ins) - $level - $*"
}

# dump uname immediately
uname -ar

# try to get /etc/lsb-release
if [ -e /etc/lsb-release ]; then
    . /etc/lsb-release
else
    if [ -e /etc/os-release ]; then
        . /etc/os-release
        DISTRIB_ID=$ID
        DISTRIB_RELEASE=$VERSION_ID
    fi
fi
if [ -z ${DISTRIB_ID+x} ] || [ -z ${DISTRIB_RELEASE+x} ]; then
    log ERROR "Unknown DISTRIB_ID or DISTRIB_RELEASE."
    exit 1
fi
DISTRIB_ID=${DISTRIB_ID,,}
DISTRIB_RELEASE=${DISTRIB_RELEASE,,}

# set distribution specific vars
PACKAGER=
if [ "$DISTRIB_ID" == "ubuntu" ]; then
    PACKAGER=apt
elif [ "$DISTRIB_ID" == "debian" ]; then
    PACKAGER=apt
elif [[ $DISTRIB_ID == centos* ]] || [ "$DISTRIB_ID" == "rhel" ]; then
    PACKAGER=yum
else
    PACKAGER=zypper
fi
if [ "$PACKAGER" == "apt" ]; then
    export DEBIAN_FRONTEND=noninteractive
fi

# globals
aad_cloud=
fqdn=
letsencrypt=0
letsencrypt_staging=0
polling_interval=15
storage_account=
table_name=
storage_rg=
shipyardversion=

# process command line options
while getopts "h?a:d:flp:s:v:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_monitoring_bootstrap.sh parameters"
            echo ""
            echo "-a [aad cloud type] AAD cloud type for MSI"
            echo "-d [fqdn] fully qualified domain name"
            echo "-f use staging LE ACME CSR (fake)"
            echo "-l enable lets encrypt"
            echo "-p [polling interval] pollint interval"
            echo "-s [storage account:table name:resource group] monitoring table"
            echo "-v [version] batch-shipyard version"
            echo ""
            exit 1
            ;;
        a)
            aad_cloud=${OPTARG,,}
            ;;
        d)
            fqdn=${OPTARG,,}
            ;;
        f)
            letsencrypt_staging=1
            ;;
        l)
            letsencrypt=1
            ;;
        p)
            polling_interval=${OPTARG}
            ;;
        s)
            IFS=':' read -ra ss <<< "${OPTARG,,}"
            storage_account=${ss[0]}
            table_name=${ss[1]}
            storage_rg=${ss[2]}
            ;;
        v)
            shipyardversion=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift
# check required params
if [ -z "$aad_cloud" ]; then
    log ERROR "AAD cloud type not specified"
    exit 1
fi

check_for_buggy_ntfs_mount() {
    # Check to ensure sdb1 mount is not mounted as ntfs
    set +e
    mount | grep /dev/sdb1 | grep fuseblk
    local rc=$?
    set -e
    if [ $rc -eq 0 ]; then
        log ERROR "/dev/sdb1 temp disk is mounted as fuseblk/ntfs"
        exit 1
    fi
}

download_file_as() {
    log INFO "Downloading: $1 as $2"
    local retries=10
    set +e
    while [ $retries -gt 0 ]; do
        if curl -fSsL "$1" -o "$2"; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not download: $1"
            exit 1
        fi
        sleep 1
    done
    set -e
}

add_repo() {
    local url=$1
    set +e
    local retries=120
    local rc
    while [ $retries -gt 0 ]; do
        if [ "$PACKAGER" == "apt" ]; then
            curl -fSsL "$url" | apt-key add -
            rc=$?
        elif [ "$PACKAGER" == "yum" ]; then
            yum-config-manager --add-repo "$url"
            rc=$?
        elif [ "$PACKAGER" == "zypper" ]; then
            zypper addrepo "$url"
            rc=$?
        fi
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not add repo: $url"
            exit 1
        fi
        sleep 1
    done
    set -e
}

refresh_package_index() {
    set +e
    local retries=120
    local rc
    while [ $retries -gt 0 ]; do
        if [ "$PACKAGER" == "apt" ]; then
            apt-get update
            rc=$?
        elif [ "$PACKAGER" == "yum" ]; then
            yum makecache -y fast
            rc=$?
        elif [ "$PACKAGER" == "zypper" ]; then
            zypper -n --gpg-auto-import-keys ref
            rc=$?
        fi
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not update package index"
            exit 1
        fi
        sleep 1
    done
    set -e
}

install_packages() {
    set +e
    local retries=120
    local rc
    while [ $retries -gt 0 ]; do
        if [ "$PACKAGER" == "apt" ]; then
            apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends "$@"
            rc=$?
        elif [ "$PACKAGER" == "yum" ]; then
            yum install -y "$@"
            rc=$?
        elif [ "$PACKAGER" == "zypper" ]; then
            zypper -n in "$@"
            rc=$?
        fi
        if [ $rc -eq 0 ]; then
            break
        fi
        retries=$((retries-1))
        if [ $retries -eq 0 ]; then
            log ERROR "Could not install packages ($PACKAGER): $*"
            exit 1
        fi
        sleep 1
    done
    set -e
}

create_batch_shipyard_heimdall_config() {
    mkdir -p ${SHIPYARD_VAR_DIR}
    chmod 755 ${SHIPYARD_VAR_DIR}
cat > ${SHIPYARD_CONF_FILE} << EOF
{
    "aad_cloud": "$aad_cloud",
    "storage": {
        "account": "$storage_account",
        "table_name": "$table_name",
        "resource_group": "$storage_rg"
    },
    "batch_shipyard_version": "$shipyardversion",
    "prometheus_var_dir": "$PROMETHEUS_VAR_DIR",
    "polling_interval": $polling_interval
}
EOF
    log INFO "Batch Shipyard heimdall config created"
}

install_docker_host_engine() {
    log DEBUG "Installing Docker Host Engine"
    # set vars
    if [ "$PACKAGER" == "apt" ]; then
        local repo=https://download.docker.com/linux/"${DISTRIB_ID}"
        local gpgkey="${repo}"/gpg
        local dockerversion="${DOCKER_CE_PACKAGE_DEBIAN}${DISTRIB_ID}"
        local prereq_pkgs="apt-transport-https ca-certificates curl gnupg2 software-properties-common"
    elif [ "$PACKAGER" == "yum" ]; then
        local repo=https://download.docker.com/linux/centos/docker-ce.repo
        local dockerversion="${DOCKER_CE_PACKAGE_CENTOS}"
        local prereq_pkgs="yum-utils device-mapper-persistent-data lvm2"
    elif [ "$PACKAGER" == "zypper" ]; then
        if [[ "$DISTRIB_RELEASE" == 12-sp3* ]]; then
            local repodir=SLE_12_SP3
        fi
        local repo="http://download.opensuse.org/repositories/Virtualization:containers/${repodir}/Virtualization:containers.repo"
        local dockerversion="${DOCKER_CE_PACKAGE_SLES}"
    fi
    # refresh package index
    refresh_package_index
    # install required software first
    # shellcheck disable=SC2086
    install_packages $prereq_pkgs
    if [ "$PACKAGER" == "apt" ]; then
        # add gpgkey for repo
        add_repo "$gpgkey"
        # add repo
        # TODO switch to stable once ready
        add-apt-repository "deb [arch=amd64] $repo $(lsb_release -cs) edge"
    else
        add_repo "$repo"
    fi
    # refresh index
    refresh_package_index
    # install docker engine
    install_packages "$dockerversion"
    systemctl start docker.service
    systemctl enable docker.service
    systemctl --no-pager status docker.service
    docker info
    log INFO "Docker Host Engine installed"
    # install docker-compose
    install_packages python3-pip python3-distutils apache2-utils
    pip3 install --upgrade setuptools wheel
    pip3 install docker-compose
    log INFO "Docker-compose installed"
}

setup_docker_compose_systemd() {
    # create systemd area for docker compose
    mkdir -p /etc/docker/compose/batch-shipyard-monitoring
    chmod 644 docker-compose.yml
    cp docker-compose.yml /etc/docker/compose/batch-shipyard-monitoring/
    # substitute LE/fqdn vars
    if [ "$letsencrypt" -eq 1 ]; then
        sed -i "s/{GF_SERVER_DOMAIN}/- GF_SERVER_DOMAIN=$fqdn/g" /etc/docker/compose/batch-shipyard-monitoring/docker-compose.yml
        if [ "$letsencrypt_staging" -eq 1 ]; then
            sed -i "s/{LE_CERT_DIR}/archive/g" /etc/docker/compose/batch-shipyard-monitoring/docker-compose.yml
        else
            sed -i "s/{LE_CERT_DIR}/live/g" /etc/docker/compose/batch-shipyard-monitoring/docker-compose.yml
        fi
    fi
    # substitute batch shipyard version
    sed -i "s/{BATCH_SHIPYARD_VERSION}/$shipyardversion/g" /etc/docker/compose/batch-shipyard-monitoring/docker-compose.yml
    # create systemd unit file
cat << EOF > /etc/systemd/system/docker-compose@.service
[Unit]
Description=%i service with docker compose
Requires=docker.service
After=docker.service

[Service]
Restart=always

WorkingDirectory=/etc/docker/compose/%i

# Remove old containers, images and volumes
ExecStartPre=/usr/local/bin/docker-compose down -v
ExecStartPre=/usr/local/bin/docker-compose rm -fv
ExecStartPre=-/bin/bash -c 'docker volume ls -qf "name=%i_" | xargs -r docker volume rm'
ExecStartPre=-/bin/bash -c 'docker network ls -qf "name=%i_" | xargs -r docker network rm'
ExecStartPre=-/bin/bash -c 'docker ps -aqf "name=%i_*" | xargs -r docker rm'

# Compose up
ExecStart=/usr/local/bin/docker-compose up

# Compose down, remove containers and volumes
ExecStop=/usr/local/bin/docker-compose down -v

[Install]
WantedBy=multi-user.target
EOF
    log INFO "systemd unit files for docker compose installed"
}

run_nginx_acme_challenge() {
    if [ "$letsencrypt" -eq 0 ]; then
        log WARNING "Let's encrypt disabled, skipping nginx setup"
    fi
    log INFO "Configuring letsencrypt"
    mkdir -p ${LETSENCRYPT_VAR_DIR}/html
    mkdir -p ${NGINX_VAR_DIR}
cat << EOF > ${NGINX_VAR_DIR}/nginx.conf
server {
    listen 80;
    listen [::]:80;
    server_name ${fqdn};

    location ~ /.well-known/acme-challenge {
        allow all;
        root /usr/share/nginx/html;
    }

    root /usr/share/nginx/html;
    index index.html;
}
EOF
    # create dhparam
    mkdir -p ${NGINX_VAR_DIR}/dhparam
    openssl dhparam -out ${NGINX_VAR_DIR}/dhparam/dhparam-2048.pem 2048
    # run nginx detached for letsencrypt ACME challenge
    docker run -d --rm \
        -v ${NGINX_VAR_DIR}/nginx.conf:/etc/nginx/conf.d/default.conf \
        -v ${LETSENCRYPT_VAR_DIR}/html:/usr/share/nginx/html \
        -p 80:80 \
        --name nginx \
        nginx:mainline-alpine
    log INFO "Nginx waiting for ACME challenge"
}

acquire_letsencrypt_certs() {
    if [ "$letsencrypt" -eq 0 ]; then
        log WARNING "Let's encrypt disabled, skipping cert acquisition"
    fi
    # execute letsencrypt test/staging
    mkdir -p ${LETSENCRYPT_VAR_DIR}/etc
    mkdir -p ${LETSENCRYPT_VAR_DIR}/var/lib
    mkdir -p ${LETSENCRYPT_VAR_DIR}/var/log
    log DEBUG "Testing stage ACME challenge"
    docker run --rm \
        -v ${LETSENCRYPT_VAR_DIR}/etc:/etc/letsencrypt \
        -v ${LETSENCRYPT_VAR_DIR}/var/lib:/var/lib/letsencrypt \
        -v ${LETSENCRYPT_VAR_DIR}/html:/data/letsencrypt \
        -v ${LETSENCRYPT_VAR_DIR}/var/log:/var/log/letsencrypt \
        certbot/certbot certonly \
        --webroot --webroot-path=/data/letsencrypt -d "${fqdn}" \
        --register-unsafely-without-email --agree-tos --staging
    # execute letsencrypt prod
    if [ "$letsencrypt_staging" -eq 0 ]; then
        rm -rf ${LETSENCRYPT_VAR_DIR}
        mkdir -p ${LETSENCRYPT_VAR_DIR}/etc
        mkdir -p ${LETSENCRYPT_VAR_DIR}/var/lib
        mkdir -p ${LETSENCRYPT_VAR_DIR}/var/log
        log DEBUG "Using prod ACME challenge"
        docker run --rm \
            -v ${LETSENCRYPT_VAR_DIR}/etc:/etc/letsencrypt \
            -v ${LETSENCRYPT_VAR_DIR}/var/lib:/var/lib/letsencrypt \
            -v ${LETSENCRYPT_VAR_DIR}/html:/data/letsencrypt \
            -v ${LETSENCRYPT_VAR_DIR}/var/log:/var/log/letsencrypt \
            certbot/certbot certonly \
            --webroot --webroot-path=/data/letsencrypt -d "${fqdn}" \
            --register-unsafely-without-email --no-eff-email --agree-tos
    fi
    log INFO "Letsencrypt certs acquired"
}

add_cert_renewal_crontab() {
    if [ "$letsencrypt" -eq 0 ]; then
        log WARNING "Let's encrypt disabled, skipping cert auto-renew"
    fi
    local staging
    if [ "$letsencrypt_staging" -eq 1 ]; then
        staging="--staging"
    fi
cat << EOF > /etc/cron.daily/certbot-renew
#!/bin/sh

set -e

docker run --rm \
    -v ${LETSENCRYPT_VAR_DIR}/etc:/etc/letsencrypt \
    -v ${LETSENCRYPT_VAR_DIR}/var/lib:/var/lib/letsencrypt \
    -v ${LETSENCRYPT_VAR_DIR}/html:/data/letsencrypt \
    -v ${LETSENCRYPT_VAR_DIR}/var/log:/var/log/letsencrypt \
    certbot/certbot renew $staging
EOF
    chmod 755 /etc/cron.daily/certbot-renew
    log INFO "Cert renewal add to crontab"
}

configure_nginx_with_certs() {
    if [ "$letsencrypt" -eq 0 ]; then
        log WARNING "Let's encrypt disabled, skipping nginx cert setup"
    fi
    # kill existing nginx container
    docker kill nginx
    # configure nginx with real certs
    chmod 644 nginx.conf
    cp nginx.conf ${NGINX_VAR_DIR}/
    # substitute fqdn
    sed -i "s/{FQDN}/$fqdn/g" ${NGINX_VAR_DIR}/nginx.conf
    # substitute le cert suffix
    if [ "$letsencrypt_staging" -eq 1 ]; then
        sed -i "s/{LE_CERT_SUFFIX}/1/g" ${NGINX_VAR_DIR}/nginx.conf
    else
        sed -i "s/{LE_CERT_SUFFIX}//g" ${NGINX_VAR_DIR}/nginx.conf
    fi
    # substitute resolver
    resolver=$(grep '^nameserver ' /etc/resolv.conf | cut -d' ' -f 2)
    sed -i "s/{RESOLVER}/$resolver/g" ${NGINX_VAR_DIR}/nginx.conf
    log INFO "Nginx configured with letsencrypt certs"
}

# configure prometheus/grafana
configure_prometheus_grafana() {
    mkdir -p ${PROMETHEUS_VAR_DIR}
    chmod 644 prometheus.yml
    cp prometheus.yml ${PROMETHEUS_VAR_DIR}
    mkdir -p ${GRAFANA_PROVISIONING_DIR}/datasources
    mkdir -p ${GRAFANA_PROVISIONING_DIR}/dashboards
    chmod 644 batch_shipyard_dashboard.json
    cp batch_shipyard_dashboard.json ${GRAFANA_PROVISIONING_DIR}/dashboards
    # download any additional dashboards
    if [ -f additional_dashboards.txt ]; then
        readarray -t dbarr <<< "$(<additional_dashboards.txt)"
        for dbpair in "${dbarr[@]}"; do
            IFS=',' read -ra dbent <<< "${dbpair}"
            download_file_as "${dbent[1]}" "${GRAFANA_PROVISIONING_DIR}/dashboards/${dbent[0]}"
            chmod 644 "${GRAFANA_PROVISIONING_DIR}/dashboards/${dbent[0]}"
        done
    fi
cat << EOF > ${GRAFANA_PROVISIONING_DIR}/datasources/prometheus.yml
apiVersion: 1

deleteDatasources:
  - name: Prometheus
    orgId: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    orgId: 1
    url: http://prometheus:9090
    basicAuth: false
    withCredentials: false
    isDefault: true
    version: 1
    editable: true
EOF
cat << EOF > ${GRAFANA_PROVISIONING_DIR}/dashboards/dashboard.yml
apiVersion: 1

providers:
  - name: Prometheus
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    editable: true
    options:
      path: /etc/grafana/provisioning/dashboards
EOF
}

log INFO "Bootstrap start"
echo "Configuration:"
echo "--------------"
echo "OS Distribution: $DISTRIB_ID $DISTRIB_RELEASE"
echo "Batch Shipyard version: $shipyardversion"
echo "AAD cloud: $aad_cloud"
echo "FQDN: $fqdn"
echo "Lets Encrypt: $letsencrypt Staging=$letsencrypt_staging"
echo "Polling interval: $polling_interval"
echo "Storage: $storage_account:$table_name:$storage_rg"
echo ""

# check sdb1 mount
check_for_buggy_ntfs_mount

# set sudoers to not require tty
sed -i 's/^Defaults[ ]*requiretty/# Defaults requiretty/g' /etc/sudoers

# write batch shipyard config
create_batch_shipyard_heimdall_config

# install docker host engine and docker compose
install_docker_host_engine

# setup docker compose on startup
setup_docker_compose_systemd

# configure nginx for ACME challenge
run_nginx_acme_challenge

# get let's encrypt certs and re-configure nginx
acquire_letsencrypt_certs
configure_nginx_with_certs

# add certbot renewal to crontab
add_cert_renewal_crontab

# configure prometheus and grafana
configure_prometheus_grafana

# start and enable services
systemctl daemon-reload
systemctl start docker-compose@batch-shipyard-monitoring
systemctl enable docker-compose@batch-shipyard-monitoring
systemctl --no-pager status docker-compose@batch-shipyard-monitoring

log INFO "Bootstrap completed"
