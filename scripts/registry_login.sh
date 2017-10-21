#!/usr/bin/env bash

set -e
set -o pipefail

# decrypt passwords if necessary
if [ "$1" == "-e" ]; then
    if [ ! -z $DOCKER_LOGIN_PASSWORD ]; then
        DOCKER_LOGIN_PASSWORD=$(echo $DOCKER_LOGIN_PASSWORD | base64 -d | openssl rsautl -decrypt -inkey ../certs/key.pem)
    fi
    if [ ! -z $SINGULARITY_LOGIN_PASSWORD ]; then
        SINGULARITY_LOGIN_PASSWORD=$(echo $SINGULARITY_LOGIN_PASSWORD | base64 -d | openssl rsautl -decrypt -inkey ../certs/key.pem)
    fi
fi

# login to Docker registries
if [ ! -z $DOCKER_LOGIN_PASSWORD ]; then
    # parse env vars
    IFS=',' read -ra servers <<< "${DOCKER_LOGIN_SERVER}"
    IFS=',' read -ra users <<< "${DOCKER_LOGIN_USERNAME}"
    IFS=',' read -ra passwords <<< "${DOCKER_LOGIN_PASSWORD}"
    # loop through each server and login
    nservers=${#servers[@]}
    if [ $nservers -ge 1 ]; then
        echo "Logging into $nservers Docker registry servers..."
        for i in $(seq 0 $((nservers-1))); do
            docker login --username ${users[$i]} --password ${passwords[$i]} ${servers[$i]}
        done
        echo "Docker registry logins completed."
    fi
else
    echo "No Docker registry servers found."
fi

# "login" to Singularity registries
if [ ! -z $SINGULARITY_LOGIN_PASSWORD ]; then
    # parse env vars
    IFS=',' read -ra servers <<< "${SINGULARITY_LOGIN_SERVER}"
    IFS=',' read -ra users <<< "${SINGULARITY_LOGIN_USERNAME}"
    IFS=',' read -ra passwords <<< "${SINGULARITY_LOGIN_PASSWORD}"
    # loop through each server and login
    nservers=${#servers[@]}
    if [ $nservers -ge 1 ]; then
        echo "Creating export script into $nservers Singularity registry servers..."
        touch singularity-registry-login
        for i in $(seq 0 $((nservers-1))); do
cat >> singularity-login << EOF
SINGULARITY_DOCKER_USERNAME=${users[$i]}
SINGULARITY_DOCKER_PASSWORD=${passwords[$i]}
EOF
        done
        chmod 600 singularity-registry-login
        echo "Singularity registry logins script created."
    fi
else
    echo "No Singularity registry servers found."
fi
