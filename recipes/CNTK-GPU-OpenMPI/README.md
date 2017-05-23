# CNTK-GPU-OpenMPI
This recipe shows how to run [CNTK](https://cntk.ai/) on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

Please note that CNTK currently uses MPI even for multiple GPUs on a single
node.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be one of `STANDARD_NC6`, `STANDARD_NC12`, `STANDARD_NC24`,
`STANDARD_NV6`, `STANDARD_NV12`, `STANDARD_NV24`. `NC` VM instances feature
K80 GPUs for GPU compute acceleration while `NV` VM instances feature
M60 GPUs for visualization workloads. Because CNTK is a GPU-accelerated
compute application, it is best to choose `NC` VM instances.
* `publisher` should be `Canonical`. Other publishers will be supported
once they are available for N-series VMs.
* `offer` should be `UbuntuServer`. Other offers will be supported once they
are available for N-series VMs.
* `sku` should be `16.04-LTS`. Other skus will be supported once they are
available for N-series VMs.
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid CNTK GPU-enabled
Docker image. Images denoted with `refdata` tag suffixes found in
[alfpark/cntk](https://hub.docker.com/r/alfpark/cntk/)
can be used for this recipe which contains reference data for MNIST and
CIFAR-10 examples. If you do not need this reference data then you can use
the images without the `refdata` suffix on the image tag. For this example,
`alfpark/cntk:2.0beta4-gpu-openmpi-refdata` can be used.
* `docker_volumes` must be populated with the following if running a CNTK MPI
job (multi-node):
  * `shared_data_volumes` should contain an Azure File Docker volume driver,
    a GlusterFS share or a manually configured NFS share. Batch
    Shipyard has automatic support for setting up Azure File Docker Volumes
    and GlusterFS, please refer to the
    [Batch Shipyard Configuration doc](../../docs/10-batch-shipyard-configuration.md).

### Non-MPI Jobs Configuration (SingleNode+SingleGPU)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/cntk:2.0beta4-gpu-openmpi-refdata`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/cntk:2.0beta4-gpu-openmpi-refdata` Docker image, you can
simply invoke the sample helper script
[run\_convnet\_mnist\_gpu.sh](docker/run_convnet_mnist_gpu.sh) to run
the MNIST convolutional example on a single GPU. The `command` would simply
be: `"/cntk/run_convnet_mnist_gpu.sh"`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

### MPI Jobs Configuration (SingleNode+MultiGPU, MultiNode+SingleGPU, MultiNode+MultiGPU)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
For this example, this should be `alfpark/cntk:2.0beta4-gpu-openmpi-refdata`.
Please note that the `docker_images` in the Global Configuration should match
this image name.
* `command` should contain the command to pass to the Docker run invocation.
For this example, simply invoke the sample helper script
[run\_convnet\_mnist\_gpu.sh](docker/run_convnet_mnist_gpu.sh) to run
the ConvNet MNIST Example that has been modified to run in parallel in
the `alfpark/cntk:2.0beta4-gpu-openmpi-refdata` Docker image. If running on
a single node, the application `command` to run would be:
`"/cntk/run_convnet_mnist_gpu.sh ."` If running on multiple nodes, the
application `command` to run would be:
`"/cntk/run_convnet_mnist_gpu.sh $AZ_BATCH_NODE_SHARED_DIR/gfs"`. In both
cases, the script to run is identical, but the first argument to pass is where
the output should be written. If the execution spans multiple nodes, then
the parameter should be a path to a shared file system.
  * **NOTE:** tasks that span multiple compute nodes
    (i.e., MultiNode+SingleGPU or MultiNode+MultiGPU) will need their output
    stored on a shared file system, otherwise CNTK will fail during test
    as the checkpoints and model are written to the specified output directory
    only by the first rank. To override the output directory for
    the example above, replace the first argument to the script with a shared
    file system location such as Azure File Docker Volume, NFS, GlusterFS, etc.
* `shared_data_volumes` should have a valid volume name as defined in the
global configuration file. Please see the global configuration section above
for details.
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.
* `multi_instance` property must be defined for multinode executions
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`
  * `resource_files` should be unset or the array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses prior to use:
* [CNTK License](https://github.com/Microsoft/CNTK/blob/master/LICENSE.md)
* [CNTK 1-bit SGD License](https://github.com/microsoft/cntk/wiki/CNTK-1bit-SGD-License)
