# HPLinpack-Infiniband-IntelMPI
This recipe shows how to run the
[HPLinpack (HPL)](http://www.netlib.org/benchmark/hpl/) benchmark
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
* `sku` should be `7.3` for `CentOS-HPC` or `12-SP1` for `SLES-HPC`.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid HPLinpack image
that can be run with Intel MPI and Infiniband in a Docker container context
on Azure VM instances. This can be `alfpark/linpack:cpu-intel-mkl` which is
published on [Docker Hub](https://hub.docker.com/r/alfpark/linpack).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
For this example, this can be `alfpark/linpack:cpu-intel-mkl`.
* `command` should contain the `mpirun` command. If using the sample
[run\_hplinpack.sh](docker/run_hplinpack.sh) script then the command can be:
`/sw/run_hplinpack.sh -n <problem size>`. If you do not specify
`-n <problem size>` then the script will attempt to create the biggest problem
size for the machine's available memory. The `run_hplinpack.sh` script has
many configuration parameters:
  * `-2`: enable `MKL_CBWR=AVX2`. Specify this option for H-series VMs.
  * `-b <block size>`: block size, defaults to 256
  * `-m <memory size in MB>`: scale problem size to specified memory size in
    MB. Can be specified instead of `-n`.
  * `-n <problem size>`: problem size. Can be specified instead of `-m`.
  * `-p <grid row dim>`: grid row dimension, this must be less than or equal
    to `-q`. If not specified, will be automatically determined from the
    number of nodes.
  * `-q <grid column dim>`: grid column dimension, this must be greater than
    or equal to `-p`. If not specified, will be automatically determined from
    the number of nodes.
* `additional_docker_run_options` json array should contain `"--privileged"`
such that HPL can pin and interleave memory
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
