#!/usr/bin/env bash

set -e
set -o pipefail

# login to registry servers (do not specify -e as creds have been decrypted)
./registry_login.sh

# ensure we're in the proper directory
cd /opt/batch-shipyard

# add timing markers
if [ ! -z ${SHIPYARD_TIMING+x} ]; then
    # backfill node prep start
    python3 perf.py nodeprep start $prefix --ts $npstart --message "offer=$offer,sku=$sku"
    # backfill docker run pull start
    python3 perf.py shipyard pull-start $prefix --ts $drpstart
    # mark docker run pull end
    python3 perf.py shipyard pull-end $prefix
    # mark node prep finished
    python3 perf.py nodeprep end $prefix
    # mark cascade start time
    python3 perf.py cascade start $prefix
fi

# execute cascade
python3 cascade.py $p2p --ipaddress $ipaddress $prefix
