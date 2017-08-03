# CNTK-CPU-Infiniband-IntelMPI
This recipe shows how to run [CNTK](https://cntk.ai/) on CPUs across
Infiniband/RDMA enabled Azure VMs via Intel MPI.

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
* `sku` should be `7.1` for `CentOS-HPC` or `12-SP1` for `SLES-HPC`.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid CNTK CPU-enabled
Docker image that can be run with Intel MPI. Images denoted with `cpu-intelmpi`
tags found in [alfpark/cntk](https://hub.docker.com/r/alfpark/cntk/) are
compatible with Azure VMs. Images denoted with `refdata` tag suffixes found in
[alfpark/cntk](https://hub.docker.com/r/alfpark/cntk/)
can be used for this recipe which contains reference data for MNIST and
CIFAR-10 examples. If you do not need this reference data then you can use
the images without the `refdata` suffix on the image tag. For this example,
`alfpark/cntk:2.0beta5-cpu-intelmpi-refdata` can be used.
* `docker_volumes` must be populated with the following if running a CNTK MPI
job (multi-node):
  * `shared_data_volumes` should contain an Azure File Docker volume driver,
    a GlusterFS share or a manually configured NFS share. Batch
    Shipyard has automatic support for setting up Azure File Docker Volumes
    and GlusterFS, please refer to the
    [Batch Shipyard Configuration doc](../../docs/10-batch-shipyard-configuration.md).

### MPI Jobs Configuration (MultiNode)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
For this example, this should be `alfpark/cntk:2.0beta5-cpu-intelmpi-refdata`.
Please note that the `docker_images` in the Global Configuration should match
this image name.
* `command` should contain the command to pass to the Docker run invocation.
For this example, we will run the ConvNet MNIST Example that has been modified
to run in parallel in the `alfpark/cntk:2.0beta5-cpu-intelmpi-refdata` Docker
image. There is also a helper script [run\_cntk.sh](docker/run_cntk.sh) that
helps launch CNTK with the Intel MPI runtime. The application `command` to
run would be:
`"/cntk/run_cntk.sh configFile=/cntk/Examples/Image/Classification/ConvNet/BrainScript/ConvNet_MNIST_Parallel.cntk rootDir=. dataDir=/cntk/Examples/Image/DataSets/MNIST outputDir=$AZ_BATCH_NODE_SHARED_DIR/gfs parallelTrain=true"`
  * **NOTE:** tasks that span multiple compute nodes will need their output
    stored on a shared file system, otherwise CNTK will fail during test
    as the checkpoints and model are written to the specified output directory
    only by the first rank. To override the output directory for the example
    above, add `OutputDir=/some/path` to a shared file system location such
    as Azure File Docker Volume, NFS, GlusterFS, etc. The example above
    already is writing to a GlusterFS share.
* `infiniband` must be set to `true`
* `shared_data_volumes` should have a valid volume name as defined in the
global configuration file. Please see the global configuration section above
for details.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`
  * `resource_files` should be unset or the array can be empty

## Dockerfile and supplementary files
Supplementary files can be found [here](./docker).

You must agree to the following licenses prior to use:
* [CNTK License](https://github.com/Microsoft/CNTK/blob/master/LICENSE.md)
* [CNTK 1-bit SGD License](https://github.com/microsoft/cntk/wiki/CNTK-1bit-SGD-License)
