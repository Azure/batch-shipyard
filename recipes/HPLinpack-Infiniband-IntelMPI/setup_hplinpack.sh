#!/usr/bin/env bash

set -e
set -o pipefail

echo "args: $*"
avx=
B=
memhpl=
n=
P=
Q=
while getopts "h?a:b:m:n:p:q:" opt; do
    case "$opt" in
        h|\?)
            echo "setup_hplinpack.sh parameters"
            echo ""
            echo "-a [avx]"
            echo "-b [block size]"
            echo "-m [memory MB to use]"
            echo "-n [problem size] overrides m"
            echo "-p [p] must be less than q"
            echo "-q [q]"
            echo ""
            exit 1
            ;;
        a)
            avx=${OPTARG^^}
            ;;
        b)
            B=$OPTARG
            ;;
        m)
            memhpl=$OPTARG
            ;;
        n)
            n=$OPTARG
            ;;
        p)
            P=$OPTARG
            ;;
        q)
            Q=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

PSIZE=
if [ -z $n ] && [ -z $memhpl ]; then
    memfree=$(free | awk '/^Mem:/{print $4}')
    memfree=$(($memfree / 1024))
    memhpl=$(($memfree - 768))
    echo Mem MB avail: $memfree
    echo Mem MB for HPLinpack: $memhpl
    if [ $memhpl -lt 0 ]; then
        echo "ERROR: Not enough memory available to run HPLinpack. Choose a larger VM size."
        exit 1
    fi
    export PSIZE="-m $memhpl"
else
    if [ -z $n ]; then
        echo "ERROR: -m or -n must be specified"
        exit 1
    fi
    export PSIZE="-n $n"
fi

if [ -z "$avx" ] || [ "$avx" == "AVX1" ]; then
    export MKL_CBWR=AVX
else
    export MKL_CBWR="$avx"
fi
if [ -z $B ]; then
    if [ "$avx" == "AVX512" ]; then
        export B=384
    else
        export B=256
    fi
fi

# compute p and q if not specified
if [ -z $P ] || [ -z $Q ]; then
    # get nodes
    IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
    nodes=${#HOSTS[@]}
    echo num nodes: $nodes
    vals=$(python findpq.py $nodes)
    IFS=' ' read -ra PQ <<< "$vals"
    export P="${PQ[0]}"
    export Q="${PQ[1]}"
fi

# set program exports
export MPI_PER_NODE=1
export I_MPI_DAPL_DIRECT_COPY_THRESHOLD=655360
export HPL_EXE=xhpl_intel64_dynamic
