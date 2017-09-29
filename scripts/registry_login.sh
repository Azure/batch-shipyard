#!/usr/bin/env bash

set -e
set -o pipefail

# decrypt passwords if necessary
if [ "$1" == "-e" ]; then
    if [ ! -z $DOCKER_LOGIN_PASSWORD ]; then
        DOCKER_LOGIN_PASSWORD=$(echo $DOCKER_LOGIN_PASSWORD | base64 -d | openssl rsautl -decrypt -inkey ../certs/key.pem)
    fi
fi

# login to registries
if [ ! -z $DOCKER_LOGIN_SERVER ]; then
    # parse env vars
    IFS=',' read -ra servers <<< "${DOCKER_LOGIN_SERVER}"
    IFS=',' read -ra users <<< "${DOCKER_LOGIN_USERNAME}"
    IFS=',' read -ra passwords <<< "${DOCKER_LOGIN_PASSWORD}"
    # loop through each server and login
    nservers=${#servers[@]}
    echo "Logging into $nservers Docker registry servers..."
    for i in $(seq 0 $((nservers-1))); do
        docker login --username ${users[$i]} --password ${passwords[$i]} ${servers[$i]}
    done
    echo "Docker registry logins completed."
else
    echo "No Docker registry servers found."
fi
