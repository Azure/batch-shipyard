#!/usr/bin/env bash

set -e

avx2=0
b=
memhpl=
n=
p=
q=
while getopts "h?2b:m:n:p:q:" opt; do
    case "$opt" in
        h|\?)
            echo "run_hplinpack.sh parameters"
            echo ""
            echo "-2 enable avx2"
            echo "-b [block size]"
            echo "-m [memory MB to use]"
            echo "-n [problem size] overrides m"
            echo "-p [p] must be less than q"
            echo "-q [q]"
            echo ""
            exit 1
            ;;
        2)
            avx2=1
            ;;
        b)
            b=$OPTARG
            ;;
        m)
            memhpl=$OPTARG
            ;;
        n)
            n=$OPTARG
            ;;
        p)
            p=$OPTARG
            ;;
        q)
            q=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

psize=
if [ -z $n ] && [ -z $memhpl ]; then
    memfree=$(free | awk '/^Mem:/{print $4}')
    memfree=$(($memfree / 1024))
    memhpl=$(($memfree - 768))
    echo Mem MB avail: $memfree
    echo Mem MB for HPLinpack: $memhpl
    if [ $memhpl -lt 0 ]; then
        echo "Not enough memory available to run HPLinpack. Choose a larger VM size."
        exit 1
    fi
    psize=" -m $memhpl"
else
    if [ -z $n ]; then
        echo "-m or -n must be specified"
        exit 1
    fi
    echo Problem size: $n
    psize=" -n $n"
fi

if [ -z $b ]; then
    b=256
fi
echo b: $b

# get nodes and compute number of processors
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
ppn=$(nproc)
nodes=${#HOSTS[@]}
echo num nodes: $nodes
echo ppn: $ppn

# compute p and q if not specified
if [ -z $p ] || [ -z $q ]; then
    vals=$(python /sw/findpq.py $nodes)
    IFS=' ' read -ra PQ <<< "$vals"
    p=${PQ[0]}
    q=${PQ[1]}
    echo p: $p
    echo q: $q
fi

# source intel mpi vars script
export MANPATH=/usr/local/man
source /opt/intel2/compilers_and_libraries/linux/mpi/bin64/mpivars.sh

# set exports
export MPI_PER_NODE=1
export I_MPI_DAPL_DIRECT_COPY_THRESHOLD=655360
if [ $avx2 -eq 1 ]; then
    export MKL_CBWR=AVX2
else
    export MKL_CBWR=AVX
fi
export HPL_EXE=xhpl_intel64

# execute benchmark
cd /opt/intel2/mkl/benchmarks/mp_linpack/bin_intel/intel64
mpirun -hosts $AZ_BATCH_HOST_LIST -perhost 1 -np $nodes /opt/intel2/mkl/benchmarks/mp_linpack/bin_intel/intel64/runme_intel64_prv -p $p -q $q -b $b $psize
