log() {
    local level=$1
    shift
    echo "$(date -u -Ins) - $level - $*"
}

# globals
block=
cascadecontainer=0
cascade_docker_image=
cascade_singularity_image=
concurrent_source_downloads=10
envfile=
is_start_task=0
prefix=
singularity_basedir=

# process command line options
while getopts "h?b:c:de:i:j:l:p:s:t" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_cascade.sh parameters"
            echo ""
            echo "-b [images] block on images"
            echo "-c [concurrent source downloads] concurrent source downloads"
            echo "-d use docker container for cascade"
            echo "-e [envfile] environment file"
            echo "-i [cascade docker image] cascade docker image"
            echo "-j [cascade singularity image] cascade singularity image"
            echo "-l [log directory] log directory"
            echo "-p [prefix] storage container prefix"
            echo "-s [singularity basedir] singularity base directory"
            echo "-t run cascade as part of the start task"
            echo ""
            exit 1
            ;;
        b)
            block=$OPTARG
            ;;
        c)
            concurrent_source_downloads=$OPTARG
            ;;
        d)
            cascadecontainer=1
            ;;
        e)
            envfile=$OPTARG
            ;;
        i)
            cascade_docker_image=$OPTARG
            ;;
        j)
            cascade_singularity_image=$OPTARG
            ;;
        l)
            log_directory=$OPTARG
            ;;
        p)
            prefix=$OPTARG
            ;;
        s)
            singularity_basedir=$OPTARG
            ;;
        t)
            is_start_task=1
            ;;
    esac
done

if [ $cascadecontainer -eq 1 ] && [ -z "$envfile" ]; then
    log ERROR "envfile not specified"
    exit 1
fi

if [ $cascadecontainer -eq 1 ] && [ -z $cascade_docker_image ]; then
    log ERROR "cascade docker image not specified"
    exit 1
fi

if [ $cascadecontainer -eq 1 ] && [ -n "$singularity_basedir" ] && [ -z $cascade_singularity_image ]; then
    log ERROR "cascade singularity image not specified"
    exit 1
fi

if [ -z "$log_directory" ]; then
    log ERROR "log directory not specified"
    exit 1
fi

if [ -z "$prefix" ]; then
    log ERROR "prefix not specified"
    exit 1
fi

spawn_cascade_process() {
    set +e
    local cascade_docker_pid
    local cascade_singularity_pid
    local detached
    if [ -z "$block" ]; then
        detached="-d"
    fi
    if [ $cascadecontainer -eq 1 ]; then
        tmp_envfile="$envfile.tmp"
        cp $envfile $tmp_envfile
        echo "log_directory=$log_directory" >> $tmp_envfile
        # run cascade for docker
        log DEBUG "Starting $cascade_docker_image"
        # shellcheck disable=SC2086
        docker run $detached --rm --runtime runc --env-file $tmp_envfile \
            -e "cascade_mode=docker" \
            -e "is_start_task=$is_start_task" \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -v /etc/passwd:/etc/passwd:ro \
            -v /etc/group:/etc/group:ro \
            -v "$AZ_BATCH_NODE_ROOT_DIR":"$AZ_BATCH_NODE_ROOT_DIR" \
            -w "$AZ_BATCH_TASK_WORKING_DIR" \
            "$cascade_docker_image" &
        cascade_docker_pid=$!
        # run cascade for singularity
        if [ -n "$singularity_basedir" ]; then
            log DEBUG "Starting $cascade_singularity_image"
            local singularity_binds
            # set singularity options
            singularity_binds="\
                -v $singularity_basedir:$singularity_basedir \
                -v $singularity_basedir/mnt:/var/lib/singularity/mnt"
            # shellcheck disable=SC2086
            docker run $detached --rm --runtime runc --env-file $tmp_envfile \
                -e "cascade_mode=singularity" \
                -v /etc/passwd:/etc/passwd:ro \
                -v /etc/group:/etc/group:ro \
                ${singularity_binds} \
                -v "$AZ_BATCH_NODE_ROOT_DIR":"$AZ_BATCH_NODE_ROOT_DIR" \
                -w "$AZ_BATCH_TASK_WORKING_DIR" \
                "$cascade_singularity_image" &
            cascade_singularity_pid=$!
        fi
    else
        # add timings
        if [[ -n ${SHIPYARD_TIMING+x} ]]; then
            # mark start cascade
            # shellcheck disable=SC2086
            ./perf.py cascade start --prefix "$prefix"
        fi
        log DEBUG "Starting Cascade Docker mode"
        # shellcheck disable=SC2086
        PYTHONASYNCIODEBUG=1 ./cascade.py --mode docker \
            --concurrent "$concurrent_source_downloads" \
            --prefix "$prefix" \
            --log-directory "$log_directory" &
        cascade_docker_pid=$!
        # run cascade for singularity
        if [ -n "$singularity_basedir" ]; then
            log DEBUG "Starting Cascade Singularity mode"
            # shellcheck disable=SC2086
            PYTHONASYNCIODEBUG=1 ./cascade.py --mode singularity \
                --concurrent "$concurrent_source_downloads" \
                --prefix "$prefix" \
                --log-directory "$log_directory" &
            cascade_singularity_pid=$!
        fi
    fi

    # wait for cascade exit
    if [ -n "$block" ]; then
        local rc
        wait $cascade_docker_pid
        rc=$?
        if [ $rc -eq 0 ]; then
            log DEBUG "Cascade Docker exited successfully"
        else
            log ERROR "Cascade Docker exited with non-zero exit code: $rc"
            exit $rc
        fi
        if [ -n "$singularity_basedir" ]; then
            wait $cascade_singularity_pid
            rc=$?
            if [ $rc -eq 0 ]; then
                log DEBUG "Cascade Singularity exited successfully"
            else
                log ERROR "Cascade Singularity exited with non-zero exit code: $rc"
                exit $rc
            fi
        fi
    else
        log INFO "Not waiting for cascade due to non-blocking option"
    fi
    set -e
}

block_for_container_images() {
    # wait for images via cascade
    "${AZ_BATCH_TASK_WORKING_DIR}"/wait_for_images.sh "$block"
}

spawn_cascade_process
# block for images if necessary
block_for_container_images
