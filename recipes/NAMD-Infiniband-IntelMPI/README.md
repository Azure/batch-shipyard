# NAMD-Infiniband-IntelMPI
This recipe shows how to run [NAMD](http://www.ks.uiuc.edu/Research/namd/)
on Linux using the Intel MPI libraries over Infiniband/RDMA Azure VM
instances in an Azure Batch compute pool. Execution of this distributed
workload requires the use of
[multi-instance tasks](../../docs/80-batch-shipyard-multi-instance-tasks.md).

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` should be a CPU-only
[RDMA-enabled instance](https://docs.microsoft.com/azure/virtual-machines/linux/sizes-hpc).
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with IB/RDMA as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid
NAMD-Infiniband-IntelMPI image compiled against Intel MPI. This
can be `alfpark/namd:2.11-icc-mkl-intelmpi` which is published on
[Docker Hub](https://hub.docker.com/r/alfpark/namd/).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/namd:2.11-icc-mkl-intelmpi`
* `resource_files` should contain the `set_up_namd.sh` script which populate
the benchmark template file and configure Intel MPI.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.
  * `resource_files` array can be empty
  * `pre_execution_command` should source the `set_up_namd.sh` script. This
    script will generate a config file `<benchmark>.namd`.
    Usage: `set_up_namd.sh <benchmark> <steps>`
    * `<benchmark>` is the benchmark to run: `apoa1` or `stmv`
    * `<steps>` is the number of steps to execute
  * `mpi` property must be defined
    * `runtime` should be set to `intelmpi`
    * `processes_per_node` should be set to `16`
* `command` should contain the command to pass to the `mpirun` invocation.
For this example, the application `command` to run would be:
`$NAMD_DIR/namd2 apoa1.namd`
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[NAMD license](http://www.ks.uiuc.edu/Research/namd/license.html) before
using this Docker image.
