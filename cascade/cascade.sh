#!/usr/bin/env bash

# this script runs in the context of env vars imported inside of a
# Docker run env, thus disable ref but not assigned shellcheck warnings.
# shellcheck disable=SC2154

set -e
set -o pipefail

# login to registry servers (do not specify -e as creds have been decrypted)
./registry_login.sh
# singularity registries will be imported via env

# ensure we're in the proper directory
cd /opt/batch-shipyard

# add timing markers
if [[ -n ${SHIPYARD_TIMING+x} ]]; then
    if [ $is_start_task -eq 1 ]; then
        # backfill node prep start
        # shellcheck disable=SC2086
        python3 perf.py nodeprep start --prefix "$prefix" --ts "$npstart" --message "offer=$offer,sku=$sku"
        # backfill docker run pull start
        # shellcheck disable=SC2086
        python3 perf.py shipyard pull-start --prefix "$prefix" --ts "$drpstart"
        # mark docker run pull end
        # shellcheck disable=SC2086
        python3 perf.py shipyard pull-end --prefix "$prefix" --ts "$drpend"
        # mark node prep finished
        # shellcheck disable=SC2086
        python3 perf.py nodeprep end --prefix "$prefix" --ts "$npend"
    fi
    # mark cascade start time
    # shellcheck disable=SC2086
    python3 perf.py cascade start --prefix "$prefix" --message "mode=$cascade_mode"
fi

# execute cascade
# shellcheck disable=SC2086
python3 cascade.py --mode "$cascade_mode" --concurrent "$concurrent_source_downloads" --prefix "$prefix"
