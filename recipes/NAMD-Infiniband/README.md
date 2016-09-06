# NAMD-Infiniband
This recipe shows how to run [NAMD](http://www.ks.uiuc.edu/Research/namd/)
2.10 on Linux using the Intel MPI libraries over Infiniband/RDMA Azure VM
instances in an Azure Batch compute pool. Execution of this distributed
workload requires the use of
[multi-instance tasks](../docs/80-batch-shipyard-multi-instance-tasks.md).

Interested in an TCP/IP-enabled version of NAMD for use with Batch Shipyard
instead? Visit [this recipe](../NAMD-TCP).

## Configuration
### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be either `STANDARD_A8` or `STANDARD_A9`
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted
* `publisher` should be `OpenLogic`. `SUSE` will be supported in a future
version of Batch Shipyard.
* `offer` should be `CentOS-HPC`. `SLES-HPC` will be supported in a future
version of Batch Shipyard.
* `sku` should be `7.1` for the current latest RDMA-enabled CentOS-HPC sku
supported by the Azure Batch service.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid NAMD-Infiniband
image compiled against Intel MPI.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
* `name` is a unique name given to the Docker container instance. This is
required for Multi-Instance tasks.
* `command` should contain the `mpirun` command. If using the sample
`run_namd.sh` script then `"/sw/run_namd.sh <benchmark> <steps> <ppn>"`
can be used to run the included benchmarks:
  * `<benchmark>` is the benchmark to run: `apoa1` or `stmv`
  * `<steps>` is the number of steps to execute
  * `<ppn>` is the number of cores on each compute node. This is optional
    and, if omitted, will be determined dynamically.
* `infiniband` must be set to `true`
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count` or
    `pool_current_dedicated`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[NAMD license](http://www.ks.uiuc.edu/Research/namd/license.html) before
using this Docker image.
