# HPCG-Infiniband-IntelMPI
This recipe shows how to run the High Performance Conjugate Gradients
[HPCG](http://www.hpcg-benchmark.org/index.html) benchmark
on Linux using Intel MPI over Infiniband/RDMA Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
[multi-instance tasks](../docs/80-batch-shipyard-multi-instance-tasks.md).

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be either `STANDARD_A8`, `STANDARD_A9`, `STANDARD_H16R`,
`STANDARD_H16MR`
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted
* `publisher` should be `OpenLogic` or `SUSE`.
* `offer` should be `CentOS-HPC` for `OpenLogic` or `SLES-HPC` for `SUSE`.
* `sku` should be `7.1` for `CentOS-HPC` or `12-SP1` for `SLES-HPC`.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid HPCG image
that can be run with Intel MPI and Infiniband in a Docker container context
on Azure VM instances. This can be `alfpark/linpack:cpu-intel-mkl` which is
published on [Docker Hub](https://hub.docker.com/r/alfpark/linpack). HPCG is
included in the Linpack image.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
For this example, this can be `alfpark/linpack:cpu-intel-mkl`.
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
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[Intel Linpack License](https://software.intel.com/en-us/articles/intel-linpack-benchmark-download-license-agreement)
before using this Docker image.
