# OpenFOAM-TCP-OpenMPI
This recipe shows how to run [OpenFOAM](http://www.openfoam.org/)
on Linux using OpenMPI over TCP in an Azure Batch compute pool.
Execution of this distributed workload requires the use of
[multi-instance tasks](../../docs/80-batch-shipyard-multi-instance-tasks.md).

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `per_job_auto_scratch` must be set to `true`. A job autoscratch is needed to
  share a common input data set between the nodes.
* `task_slots_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid OpenFOAM image
that can be run with MPI in a Docker container context. This can be
`alfpark/openfoam:4.0-gcc-openmpi` or `alfpark/openfoam:v1606plus-gcc-openmpi`
which are published on
[Docker Hub](https://hub.docker.com/r/alfpark/openfoam).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation.
For this example, this should be `alfpark/openfoam:4.0-gcc-openmpi`.
* `resource_files` should contain the `set_up_sample.sh` script which set up
the sample and export environement variables used by `mpi` `options`.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_specification_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.
  * `resource_files` array can be empty
  * `pre_execution_command` should source the `set_up_sample.sh` script.
  * `mpi` property must be defined
    * `runtime` should be set to `openmpi`
    * `options` should contains `-np $np`, `--hostfile $hostfile`, `-x PATH`,
      `-x LD_LIBRARY_PATH`, `-x MPI_BUFFER_SIZE`, `-x $mpienvopts`, and
      `-x $mpienvopts2`. These options use the environemnt variables set by
      the `set_up_sample.sh` script.
* `command` should contain the command to pass to the `mpirun` invocation.
For this example, the application `command` to run would be:
`simpleFoam -parallel`

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[OpenFOAM license](http://openfoam.org/licence/) before using this Docker
image.
