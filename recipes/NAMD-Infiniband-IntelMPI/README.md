# NAMD-Infiniband-IntelMPI
This recipe shows how to run [NAMD](http://www.ks.uiuc.edu/Research/namd/)
on Linux using the Intel MPI libraries over Infiniband/RDMA Azure VM
instances in an Azure Batch compute pool. Execution of this distributed
workload requires the use of
[multi-instance tasks](../docs/80-batch-shipyard-multi-instance-tasks.md).

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

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
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid
NAMD-Infiniband-IntelMPI image compiled against Intel MPI. This
can be `alfpark/namd:2.11-icc-mkl-intelmpi` which is published on
[Docker Hub](https://hub.docker.com/r/alfpark/namd/).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/namd:2.11-icc-mkl-intelmpi`
* `command` should contain the `mpirun` command. If using the sample
`run_namd.sh` script then `"/sw/run_namd.sh <benchmark> <steps> <ppn>"`
can be used to run the included benchmarks:
  * `<benchmark>` is the benchmark to run: `apoa1` or `stmv`
  * `<steps>` is the number of steps to execute
  * `<ppn>` is the number of cores on each compute node. This is optional
    and, if omitted, will be determined dynamically.
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[NAMD license](http://www.ks.uiuc.edu/Research/namd/license.html) before
using this Docker image.
