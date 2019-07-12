#!/usr/bin/env bash

# populate benchmark template file
echo Executing benchmark $1 for $2 steps...
cp $NAMD_DIR/$1/* .
mv $1.namd.template $1.namd
echo "outputname $1-out" | tee -a $1.namd
echo "numsteps $2" | tee -a $1.namd

# source mpivars
source /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh
