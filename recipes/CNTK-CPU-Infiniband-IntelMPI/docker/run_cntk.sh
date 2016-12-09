#!/usr/bin/env bash

# calculate total number of hosts
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}

# execute cntk with mpirun
source /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh
mpirun -v -np $nodes -ppn 1 -hosts $AZ_BATCH_HOST_LIST /cntk/build-mkl/cpu/release/bin/cntk $*
