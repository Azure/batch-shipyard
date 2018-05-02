#!/usr/bin/env bash

# get VMs Nodes 
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}
# print configuration
echo num nodes: $nodes
echo "hosts: ${HOSTS[@]}"

# source Intel compiler and mpi vars script
source /opt/intel/bin/compilervars.sh intel64
source /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh

export I_MPI_FABRICS=tcp
export I_MPI_MIC=enable
export I_MPI_DAPL_PROVIDER=ofa-v2-ib0
export I_MPI_DYNAMIC_CONNECTION=0
export I_MPI_PROCESS_MANAGER=hydra

#Create training, testing, and output directories
mkdir $AZ_BATCH_TASK_WORKING_DIR/models

echo "set variables"
set -e		
w=	
l=
k=
mc=
e=
r=
f=
t=
n=
gl=
glDir=

while getopts "h?w:l:k:m:e:r:f:t:n:g:d:" opt; do
    case "$opt" in
        h|\?)
            echo "run_parasail.sh parameters"
            echo ""
            echo "-w superSGD directory"
            echo "-l learning rate"
            echo "-k approximation rank constant"
            echo "-mc model combiner convergence threshold"
            echo "-e total epochs"
            echo "-r rounds per epoch"
            echo "-f file prefix"
            echo "-t number of threads"
            echo "-n number of features"
            echo "-gl log global models every this many epochs"
            echo "-glDir log global models to this directory at the host"
            echo ""
            exit 1
            ;;
        w)
            w=${OPTARG}
			;;
        l)
            l=${OPTARG}
            ;;
        k)
            k=${OPTARG}
            ;;
        m)
            mc=${OPTARG}
            ;;
        e)
            e=${OPTARG}
            ;;
        r)
            r=${OPTARG}
            ;;
        f)
            f=${OPTARG}
            ;;
        t)
            t=${OPTARG}
            ;;
        n)
            n=${OPTARG}
            ;;
        g)
            gl=${OPTARG}
            ;;
        d)
            glDir=${OPTARG}
            ;; 
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift
echo "end set variables"

echo "start mpi execute job"

mpiexec.hydra -np $nodes $w -l $l -k $k -mc $mc -e $e -r $r -f $f -t $t -n $n -gl $gl -glDir $glDir

echo "end mpi job"
