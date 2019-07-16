# OpenFOAM-Infiniband-IntelMPI
This recipe shows how to run [OpenFOAM](http://www.openfoam.org/)
on Linux using Intel MPI over Infiniband/RDMA Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
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
* `per_job_auto_scratch` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid OpenFOAM image
that can be run with Intel MPI and Infiniband in a Docker container context
on Azure VM instances. This can be `alfpark/openfoam:4.0-icc-intelmpi` or
`alfpark/openfoam:v1606plus-icc-intelmpi`
which are published on [Docker Hub](https://hub.docker.com/r/alfpark/openfoam).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation.
For this example, this can be `alfpark/openfoam:4.0-icc-intelmpi`.
* `resource_files` should contain the `set_up_sample.sh` script which configure
Intel MPI and set up the sample.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.
  * `resource_files` array can be empty
  * `pre_execution_command` should source the `set_up_sample.sh` script.
  * `mpi` property must be defined
    * `runtime` should be set to `intelmpi`
    * `options` should contains `-np $np`, `-ppn $ppn`, and
      `-hosts $AZ_BATCH_HOST_LIST`. These options use the environemnt
      variables set by `set_up_sample.sh` script.
* `command` should contain the command to pass to the `mpirun` invocation.
For this example, the application `command` to run would be:
`simpleFoam -parallel`
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[OpenFOAM license](http://openfoam.org/licence/) before using this Docker
image.
