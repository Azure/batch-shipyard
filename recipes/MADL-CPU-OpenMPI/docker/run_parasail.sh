#!/usr/bin/env bash

# get VMs Nodes 
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}
# print configuration
echo num nodes: $nodes
echo "hosts: ${HOSTS[@]}"

# create output directories
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
gl=
glDir=
bd=
while getopts "h?w:l:k:m:e:r:f:t:n:g:d:b:" opt; do
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
            echo "-gl log global models every this many epochs"
            echo "-glDir log global models to this directory at the host"
            echo "-bd location for the binary data"
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
        g)
            gl=${OPTARG}
            ;;
        d)
            glDir=${OPTARG}
            ;; 
        b)
            bd=${OPTARG}
            ;; 
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift
echo "end set variables"

echo "start mpi execute job"
mpirun --allow-run-as-root --mca btl_tcp_if_exclude docker0 -np $nodes $w -l $l -k $k -mc $mc -e $e -r $r -f $f -t $t -gl $gl -glDir $glDir -mem -bd $bd -dl
echo "end mpi job"
