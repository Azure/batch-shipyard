# mpiBench-Infiniband-OpenMPI
This recipe shows how to run the
[mpiBench](https://github.com/LLNL/mpiBench) benchmark
on Linux using Open MPI and Infiniband over Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
[multi-instance tasks](../../docs/80-batch-shipyard-multi-instance-tasks.md).

## Configuration
Please see refer to the [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `task_slots_per_node` must be set to 1 or omitted
* `vm_configuration` must be defined
  * `platform_image` must be defined
    * `publisher` must be set to `OpenLogic`
    * `offer` must be set to `CentOS-HPC`
    * `sku` must be set to `7.6`
* `vm_size` must be set to an SR-IOV RDMA compatible VM size such as
`STANDARD_HB60rs` or `STANDARD_HC44rs`

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid mpiBench image that
can be run with Open MPI. This can be `vincentlabo/mpibench:openmpi-ib` which
is published on [Docker Hub](https://hub.docker.com/r/vincentlabo/mpibench).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container
invocation. For this example, this should be `vincentlabo/mpibench:openmpi-ib`.
* `command` should contain the command to pass to the `mpirun` invocation.
For this example, we will run mpiBench with an ending message size of 1kB.
The application `command` to run would be: `/mpiBench/mpiBench -e 1K`
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_specification_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.
  * `resource_files` should be unset or the array can be empty
  * `mpi` property must be defined
    * `runtime` should be set to `openmpi`
    * `processes_per_node` should be set to `nproc`

## Supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).
The Singularity Definition file for the Singularity image can be found
[here](./singularity).
