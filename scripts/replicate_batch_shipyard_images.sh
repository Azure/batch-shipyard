#!/usr/bin/env bash

set -e
set -o pipefail

log() {
    local level=$1
    shift
    echo "$(date -u -Iseconds) - $level - $*"
}

bsver=
bxver=
keep=0
password=
registry=
sinver=
username=

# process command line options
while getopts "h?b:kp:r:s:u:x:" opt; do
    case "$opt" in
        h|\?)
            echo "replicate_batch_shipyard_images.sh parameters"
            echo ""
            echo "-b [version] batch shipyard version"
            echo "-k keep temporary images (any existing images may be removed)"
            echo "-p [password] password for login or can be DOCKER_LOGIN_PASSWORD envvar"
            echo "-r [server] target registry server"
            echo "-s [version] singularity version"
            echo "-u [username] username for login"
            echo "-x [version] blobxfer version"
            echo ""
            exit 1
            ;;
        b)
            bsver=$OPTARG
            ;;
        k)
            keep=1
            ;;
        p)
            password=$OPTARG
            ;;
        r)
            registry=$OPTARG
            ;;
        s)
            sinver=$OPTARG
            ;;
        x)
            bxver=$OPTARG
            ;;
        u)
            username=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

if [ -z "$username" ]; then
    log ERROR "Username for login not specified"
    exit 1
fi
if [ -z "$registry" ]; then
    log ERROR "Target Docker registry not specified"
    exit 1
fi
if [ -z "$password" ]; then
    password="$DOCKER_LOGIN_PASSWORD"
    if [ -z "$password" ]; then
        log ERROR "Password for login not specified"
        exit 1
    fi
fi
if [ -z "$bsver" ] || [ -z "$bxver" ] || [ -z "$sinver" ]; then
    log ERROR "All required versions not specified"
    exit 1
fi

mirror_docker_image() {
    local src=$1
    local dst="$registry/$src"
    docker pull "$src"
    docker tag "$src" "$dst"
    docker push "$dst"
    docker rmi "$dst"
    if [ "$keep" -eq 0 ]; then
        docker rmi "$src"
    fi
}

log INFO "Logging into target Docker registry"
docker login --username "$username" --password "$password" "$registry"

log INFO "Mirroring Docker images"
mirror_docker_image "alfpark/blobxfer:$bxver"
mirror_docker_image "alfpark/batch-shipyard:${bsver}-cascade"
mirror_docker_image "alfpark/batch-shipyard:${bsver}-cargo"
mirror_docker_image "alfpark/singularity:${sinver}-ubuntu-16.04"
#mirror_docker_image "alfpark/singularity:${sinver}-ubuntu-18.04"
mirror_docker_image "alfpark/singularity:${sinver}-centos-7"

log INFO "Docker image mirroring complete"
