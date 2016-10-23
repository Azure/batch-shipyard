# CNTK-GPU-OpenMPI
This recipe shows how to run [CNTK](https://cntk.ai/) on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

Please note that CNTK currently uses MPI even for multiple GPUs on a single
node.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
**Note: You must be approved for the
[Azure N-Series Preview](http://gpu.azure.com/) and have escalated a
customer service support ticket with your Batch account details to the Azure
Batch team to enable this feature. Otherwise, your pool allocation will fail.**

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
* `sku` should be `16.04.0-LTS`. Other skus will be supported once they are
available for N-series VMs.
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted
* `gpu` property should be specified with the following members:
  * `nvidia_driver` property contains the following members:
    * `source` is a URL for the driver installer .run file

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid CNTK GPU-enabled
Docker image.
[alfpark/cntk:1.7.2-gpu-openmpi-refdata](https://hub.docker.com/r/alfpark/cntk/)
can be used for this recipe which contains reference data for MNIST and CIFAR
examples. If you do not need this reference data then you can use the
`alfpark/cntk:1.7.2-gpu-openmpi` image instead.
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
e.g., `alfpark/cntk:1.7.2-gpu-openmpi-refdata`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/cntk:1.7.2-gpu-openmpi-refdata` Docker image and to run the
MNIST convolutional example on a single GPU, the `command` would simply
be:
`"/bin/bash -c \"/cntk/build-mkl/gpu/release/bin/cntk configFile=/cntk/Examples/Image/Classification/ConvNet/ConvNet_MNIST.cntk rootDir=. dataDir=/cntk/Examples/Image/DataSets/MNIST\""`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

### MPI Jobs Configuration (SingleNode+MultiGPU, MultiNode+SingleGPU, MultiNode+MultiGPU)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
Since we are not using either the MNIST or CIFAR examples, this can simply
be `alfpark/cntk:1.7.2-gpu-openmpi`. Please note that the `docker_images` in
the Global Configuration should match this image name.
* `name` is a unique name given to the Docker container instance. This is
required for Multi-Instance tasks. This is not required for running on a
single node.
* `command` should contain the command to pass to the Docker run invocation.
For this example, we will run the ConvNet MNIST Example that has been modified
to run in parallel in the `alfpark/cntk:1.7.2-gpu-openmpi-refdata` Docker
image. If running on a single node, the application `command` to run would be:
`"/cntk/run_convnet_mnist_gpu.sh ."` If running on multiple nodes, the
application `command` to run would be:
`"/cntk/run_convnet_mnist_gpu.sh $AZ_BATCH_NODE_SHARED_DIR/gfs"`. In both
cases, the script to run is identical, but the argument to pass varies
depending upon if the execution spans multiple nodes - as it defines where
to place the output model files.
  * **NOTE:** tasks that span multiple compute nodes
    (i.e., MultiNode+SingleGPU or MultiNode+MultiGPU) will need their output
    stored on a shared file system, otherwise CNTK will fail during test
    as individual outputs are written by each rank to the specified output
    directory only on that compute node. To override the output directory for
    the example above, replace the first argument to the script with a shared
    file system location such as Azure File Docker Volume, NFS, GlusterFS, etc.
  * Please note that for Dockerized MPI containers with gpu (i.e.,
    `nvidia-docker` invocations), although the `exec` call can be wrapped by
    the `nvidia-docker` wrapper, the subsequent `mpirun` which performs a
    remote shell into the other containers does not have this capability. Thus
    some convenience of the `nvidia-docker` wrapper are lost for the invocation
    itself (but not the device pass-through as that has already occurred for
    `docker run`). Thus CUDA library locations will need to be explicitly
    specified in `LD_LIBRARY_PATH` as shown above.
* `shared_data_volumes` should have a valid volume name as defined in the
global configuration file. Please see the global configuration section above
for details.
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.
* `multi_instance` property must be defined for multinode executions
  * `num_instances` should be set to `pool_specification_vm_count` or
    `pool_current_dedicated`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses prior to use:
* [CNTK License](https://github.com/Microsoft/CNTK/blob/master/LICENSE.md)
* [CNTK 1-bit SGD Non-Commercial License](https://cntk1bitsgd.codeplex.com/SourceControl/latest#LICENSE-NON-COMMERCIAL.md)
