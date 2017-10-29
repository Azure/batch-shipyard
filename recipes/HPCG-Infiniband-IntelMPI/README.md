# HPCG-Infiniband-IntelMPI
This recipe shows how to run the High Performance Conjugate Gradients
[HPCG](http://www.hpcg-benchmark.org/index.html) benchmark
on Linux using Intel MPI over Infiniband/RDMA Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
[multi-instance tasks](../docs/80-batch-shipyard-multi-instance-tasks.md).

Execution under both Docker and Singularity are shown in this recipe.

## Configuration
Please see refer to the [set of sample configuration files](./config) for
this recipe. The directory `docker` will contain the Docker-based execution
while the `singularity` directory will contain the Singularity-based
execution configuration.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` should be a CPU-only RDMA-enabled instance:
`STANDARD_A8`, `STANDARD_A9`, `STANDARD_H16R`, `STANDARD_H16MR`
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted
* `publisher` should be `OpenLogic` or `SUSE`
* `offer` should be `CentOS-HPC` for `OpenLogic` or `SLES-HPC` for `SUSE`
* `sku` should be `7.3` for `CentOS-HPC` or `12-SP1` for `SLES-HPC`

### Global Configuration
#### Docker-based
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid HPCG image
that can be run with Intel MPI and Infiniband in a Docker container context
on Azure VM instances. This can be `alfpark/linpack:cpu-intel-mkl` which is
published on [Docker Hub](https://hub.docker.com/r/alfpark/linpack). HPCG is
included in the Linpack image.

#### Singularity-based
The global configuration should set the following properties:
* `singularity_images` array must have a reference to a valid HPCG image
that can be run with Intel MPI and Infiniband. This can be
`shub://alfpark/linpack` which is
published on [Singularity Hub](https://www.singularity-hub.org/containers/496).

### Jobs Configuration
#### Docker-based
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container
invocation. For this example, this can be `alfpark/linpack:cpu-intel-mkl`.
* `command` should contain the `mpirun` command. If using the sample
[run\_hpcg.sh](docker/run_hpcg.sh) script then the command can be:
`/sw/run_hpcg.sh -n <problem size> -t <run time>`. `-n <problem size>` should
be selected such that the problem is large enough to fit in available memory.
The `run_hpcg.sh` script has many configuration parameters:
  * `-2`: Use the AVX2 optimized version of the benchmark. Specify this option
    for H-series VMs.
  * `-n <problem size>`: nx, ny and nz are set to this value
  * `-t <run time>`: limit execution time to specified seconds. Official runs
    must be at least 1800 seconds (30 min).
  * `-x <nx>`: set nx to this value
  * `-y <ny>`: set ny to this value
  * `-z <nz>`: set nz to this value
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.

#### Singularity-based
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `singularity_image` should be the name of the Singularity image for this
container invocation. For this example, this should be
`shub://alfpark/linpack`.
* `command` should contain the `mpirun` command. If using the sample
[run\_hpcg.sh](https://github.com/alfpark/linpack/blob/master/run_hpcg.sh)
script then the command can be:
`/sw/run_hpcg.sh -n <problem size> -t <run time>`. `-n <problem size>` should
be selected such that the problem is large enough to fit in available memory.
The `run_hpcg.sh` script has many configuration parameters:
  * `-2`: Use the AVX2 optimized version of the benchmark. Specify this option
    for H-series VMs.
  * `-n <problem size>`: nx, ny and nz are set to this value
  * `-t <run time>`: limit execution time to specified seconds. Official runs
    must be at least 1800 seconds (30 min).
  * `-x <nx>`: set nx to this value
  * `-y <ny>`: set ny to this value
  * `-z <nz>`: set nz to this value
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`

## Supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). The
Singularity hub build and resource files can be found
[here](https://github.com/alfpark/linpack).

Please note that you must agree with the
[Intel Linpack License](https://software.intel.com/en-us/articles/intel-linpack-benchmark-download-license-agreement)
before using this Docker image.
