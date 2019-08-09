# mpiBench-MPICH
This recipe shows how to run the
[mpiBench](https://github.com/LLNL/mpiBench) benchmark
on Linux using MPICH over Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
[multi-instance tasks](../../docs/80-batch-shipyard-multi-instance-tasks.md).

Execution under both Docker and Singularity are shown in this recipe.

## Configuration
Please see refer to the [set of sample configuration files](./config) for
this recipe. The directory `docker` will contain the Docker-based execution
while the `singularity` directory will contain the Singularity-based
execution configuration.

### Pool Configuration
#### Docker-based
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

#### Singularity-based
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted
* `additional_node_prep` should contains the commands necessary for
  installing MPICH on the node. For example:
    ```
    - apt-get update
    - apt-get install -y --no-install-recommends mpich
    ```
* `container_runtimes` should be set to install `singularity`

### Global Configuration
#### Docker-based
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid mpiBench image that
can be run with MPICH. This can be `vincentlabo/mpibench:mpich` which
is published on [Docker Hub](https://hub.docker.com/r/vincentlabo/mpibench).

#### Singularity-based
The global configuration should set the following properties:
* `singularity_images` array must have a reference to a valid mpiBench image
that can be run with MPICH. This can be
`library://vincent.labonte/mpi/mpibench:mpich` which is published on
[Sylabs Cloud](https://cloud.sylabs.io/library/vincent.labonte/mpi/mpibench).

### Jobs Configuration
#### Docker-based
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container
invocation. For this example, this should be `vincentlabo/mpibench:mpich`.
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
    * `runtime` should be set to `mpich`
    * `processes_per_node` should be set to `nproc`

#### Singularity-based
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `singularity_image` should be the name of the Singularity image for this
container invocation. For this example, this should be
`library://vincent.labonte/mpi/mpibench:mpich`.
* `command` should contain the command to pass to the `mpirun` invocation.
For this example, we will run mpiBench with an ending message size of 1kB.
The application `command` to run would be: `/mpiBench/mpiBench -e 1K`
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_specification_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`.
  * `resource_files` should be unset or the array can be empty
  * `mpi` property must be defined
    * `runtime` should be set to `mpich`
    * `processes_per_node` should be set to `nproc`

## Supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).
The Singularity Definition file for the Singularity image can be found
[here](./singularity).
