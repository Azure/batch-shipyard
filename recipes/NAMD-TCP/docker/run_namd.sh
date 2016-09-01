#!/usr/bin/env bash

echo Executing benchmark $1 for $2 steps...
cp $NAMD_DIR/$1/* .
mv $1.namd.template $1.namd
echo "outputname $1-out" | tee -a $1.namd
echo "numsteps $2" | tee -a $1.namd

ppn=$3
if [ -z $ppn ]; then
    ppn=`nproc`
fi

IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}
np=$(($nodes * $ppn))
# create node list
nodelist=.nodelist.charm
rm -f $nodelist
touch $nodelist
for node in "${HOSTS[@]}"; do
    echo host $node >> $nodelist
done
timeout=900

echo "Executing namd on $np processors (ppn=$ppn)..."
$NAMD_DIR/charmrun ++verbose ++timeout $timeout ++batch $ppn ++remote-shell ssh ++p $np ++ppn $ppn ++nodelist $nodelist $NAMD_DIR/namd2 $1.namd

