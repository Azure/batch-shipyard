# OpenFOAM-TCP-OpenMPI
This recipe shows how to run [OpenFOAM](http://www.openfoam.org/)
on Linux using OpenMPI over TCP in an Azure Batch compute pool.
Execution of this distributed workload requires the use of
[multi-instance tasks](../docs/80-batch-shipyard-multi-instance-tasks.md).

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid OpenFOAM image
that can be run with MPI in a Docker container context. This can be
`alfpark/openfoam:4.0-gcc-openmpi` or `alfpark/openfoam:v1606plus-gcc-openmpi`
which are published on
[Docker Hub](https://hub.docker.com/r/alfpark/openfoam).
* `volumes` must be populated with the following:
  * `shared_data_volumes` should contain an Azure File Docker volume driver,
    a GlusterFS share or a manually configured NFS share. Batch
    Shipyard has automatic support for setting up Azure File Docker Volumes
    and GlusterFS, please refer to the
    [Batch Shipyard Configuration doc](../../docs/10-batch-shipyard-configuration.md).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation.
For this example, this should be `alfpark/openfoam:4.0-gcc-openmpi`.
* `command` should contain the `mpirun` command. If using the sample
`run_sample.sh` script then the command should be simply:
`/opt/OpenFOAM/run_sample.sh`
* `shared_data_volumes` should have a valid volume name as defined in the
global configuration file. Please see the previous section for details.
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
[OpenFOAM license](http://openfoam.org/licence/) before using this Docker
image.
