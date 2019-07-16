#!/usr/bin/env bash

set -e
set -o pipefail

# get mpi ref and set up openfoam env
OPENFOAM_DIR=/opt/OpenFOAM/OpenFOAM-4.0
source /etc/profile.d/modules.sh
module add mpi/openmpi-x86_64
source $OPENFOAM_DIR/etc/bashrc

# copy sample into auto scratch shared area
AUTO_SCRATCH_DIR=$AZ_BATCH_TASK_DIR/auto_scratch
cd $AUTO_SCRATCH_DIR
cp -r $OPENFOAM_DIR/tutorials/incompressible/simpleFoam/pitzDaily .
cp $OPENFOAM_DIR/tutorials/incompressible/simpleFoam/pitzDailyExptInlet/system/decomposeParDict pitzDaily/system/

# get nodes and compute number of processors
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}
ppn=`nproc`
np=$(($nodes * $ppn))

# substitute proper number of subdomains
sed -i -e "s/^numberOfSubdomains 4/numberOfSubdomains $np;/" pitzDaily/system/decomposeParDict
root=`python -c "import math; x=int(math.sqrt($np)); print x if x*x==$np else -1"`
if [ $root -eq -1 ]; then
    sed -i -e "s/\s*n\s*(2 2 1)/    n               ($ppn $nodes 1)/g" pitzDaily/system/decomposeParDict
else
    sed -i -e "s/\s*n\s*(2 2 1)/    n               ($root $root 1)/g" pitzDaily/system/decomposeParDict
fi

# decompose
cd pitzDaily
blockMesh
decomposePar -force

# create hostfile
hostfile="hostfile"
touch $hostfile
>| $hostfile
for node in "${HOSTS[@]}"
do
    echo $node slots=$ppn max-slots=$ppn >> $hostfile
done

# export parameters
export mpirun=`which mpirun`
export mpienvopts=`echo \`env | grep WM_ | sed -e "s/=.*$//"\` | sed -e "s/ / -x /g"`
export mpienvopts2=`echo \`env | grep FOAM_ | sed -e "s/=.*$//"\` | sed -e "s/ / -x /g"`
export np
export hostfile
