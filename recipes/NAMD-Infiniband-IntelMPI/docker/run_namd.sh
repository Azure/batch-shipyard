#!/usr/bin/env bash

# populate benchmark template file
echo Executing benchmark $1 for $2 steps...
cp $NAMD_DIR/$1/* .
mv $1.namd.template $1.namd
echo "outputname $1-out" | tee -a $1.namd
echo "numsteps $2" | tee -a $1.namd

# set PEs
ppn=$3
if [ -z $ppn ]; then
    ppn=`nproc`
fi

# calculate total number of processors
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}
np=$(($nodes * $ppn))

# execute NAMD
echo "Executing namd on $np processors (ppn=$ppn)..."
source $MPIVARS_SCRIPT
mpirun -np $np -ppn $ppn -hosts $AZ_BATCH_HOST_LIST $NAMD_DIR/namd2 $1.namd
