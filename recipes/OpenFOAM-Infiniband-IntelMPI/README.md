# OpenFOAM-Infiniband-IntelMPI
This recipe shows how to run [OpenFOAM](http://www.openfoam.org/)
on Linux using Intel MPI over Infiniband/RDMA Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
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
* `docker_images` array must have a reference to a valid OpenFOAM image
that can be run with Intel MPI and Infiniband in a Docker container context
on Azure VM instances. This can be `alfpark/openfoam:4.0-icc-intelmpi` or
`alfpark/openfoam:v1606plus-icc-intelmpi`
which are published on [Docker Hub](https://hub.docker.com/r/alfpark/openfoam).
* `docker_volumes` must be populated with the following:
  * `shared_data_volumes` should contain an Azure File Docker volume driver,
    a GlusterFS share or a manually configured NFS share. Batch
    Shipyard has automatic support for setting up Azure File Docker Volumes
    and GlusterFS, please refer to the
    [Batch Shipyard Configuration doc](../../docs/10-batch-shipyard-configuration.md).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
For this example, this can be `alfpark/openfoam:4.0-icc-intelmpi`.
* `command` should contain the `mpirun` command. If using the sample
`run_sample.sh` script then the command should be simply:
`/opt/OpenFOAM/run_sample.sh`
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.
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
