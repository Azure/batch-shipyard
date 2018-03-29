#!/usr/bin/env bash

set -e
set -o pipefail

python3 /opt/batch-shipyard/recurrent_job_manager.py "$@"
