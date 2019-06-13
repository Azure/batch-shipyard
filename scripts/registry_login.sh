#!/usr/bin/env bash

set -e
set -o pipefail

log() {
    local level=$1
    shift
    echo "$(date -u -Iseconds) - $level - $*"
}

docker_login() {
    local user=$1
    local password=$2
    local server=$3
    local rc
    log DEBUG "Logging into Docker registry: $server with user: $user"
    set +e
    local retries=50
    while [ $retries -gt 0 ]; do
        local login_out
        login_out=$(echo "y" | docker login --username "$user" --password "$password" "$server" 2>&1)
        rc=$?
        if [ $rc -eq 0 ]; then
            echo "$login_out"
            break
        fi
        # non-zero exit code: check login output
        local tmr
        tmr=$(grep -i 'toomanyrequests' <<<"$login_out")
        local crbp
        crbp=$(grep -i 'connection reset by peer' <<<"$login_out")
        local uhs
        uhs=$(grep -i 'received unexpected HTTP status' <<<"$login_out")
        local tht
        tht=$(grep -i 'TLS handshake timeout' <<<"$login_out")
        if [[ -n "$tmr" ]] || [[ -n "$crbp" ]] || [[ -n "$uhs" ]] || [[ -n "$tht" ]]; then
            log WARNING "will retry: $login_out"
        else
            log ERROR "$login_out"
            exit 1
        fi
        retries=$((retries-1))
        if [ $retries -le 0 ]; then
            log ERROR "Could not login to registry: $server with user: $user"
            exit 1
        fi
        sleep $((RANDOM % 5 + 1))s
    done
    set -e
}

# decrypt passwords if necessary
if [ "$1" == "-e" ]; then
    if [ -n "$DOCKER_LOGIN_PASSWORD" ]; then
        DOCKER_LOGIN_PASSWORD=$(echo "$DOCKER_LOGIN_PASSWORD" | base64 -d | openssl rsautl -decrypt -inkey ../certs/key.pem)
    fi
    if [ -n "$SINGULARITY_LOGIN_PASSWORD" ]; then
        SINGULARITY_LOGIN_PASSWORD=$(echo "$SINGULARITY_LOGIN_PASSWORD" | base64 -d | openssl rsautl -decrypt -inkey ../certs/key.pem)
    fi
fi

# login to Docker registries
if [ -n "$DOCKER_LOGIN_PASSWORD" ]; then
    # parse env vars
    IFS=',' read -ra servers <<< "${DOCKER_LOGIN_SERVER}"
    IFS=',' read -ra users <<< "${DOCKER_LOGIN_USERNAME}"
    IFS=',' read -ra passwords <<< "${DOCKER_LOGIN_PASSWORD}"
    # loop through each server and login
    nusers=${#users[@]}
    if [ "$nusers" -ge 1 ]; then
        log DEBUG "Logging into $nusers Docker registry servers..."
        for i in $(seq 0 $((nusers-1))); do
            docker_login "${users[$i]}" "${passwords[$i]}" "${servers[$i]}"
        done
        log INFO "Docker registry logins completed."
    fi
else
    log WARNING "No Docker registry servers found."
fi

# "login" to Singularity registries
if [ -n "$SINGULARITY_LOGIN_PASSWORD" ]; then
    # parse env vars
    IFS=',' read -ra servers <<< "${SINGULARITY_LOGIN_SERVER}"
    IFS=',' read -ra users <<< "${SINGULARITY_LOGIN_USERNAME}"
    IFS=',' read -ra passwords <<< "${SINGULARITY_LOGIN_PASSWORD}"
    # loop through each server and login
    nusers=${#users[@]}
    if [ "$nusers" -ge 1 ]; then
        log DEBUG "Logging into $nusers Singularity registry servers..."
        for i in $(seq 0 $((nusers-1))); do
            docker_login "${users[$i]}" "${passwords[$i]}" "${servers[$i]}"
        done
        log INFO "Singularity registry logins completed."
    fi
else
    log WARNING "No Singularity registry servers found."
fi
