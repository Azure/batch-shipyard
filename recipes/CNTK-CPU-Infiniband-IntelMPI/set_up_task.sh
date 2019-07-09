#!/usr/bin/env bash

set -e
set -o pipefail

# activate cntk environment
source /cntk/activate-cntk

# source intel mpi vars
source /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh
