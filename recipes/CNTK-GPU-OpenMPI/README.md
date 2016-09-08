# CNTK-GPU-OpenMPI
This recipe shows how to run [CNTK](https://cntk.ai/) on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
### Pool Configuration
**Note: You must be approved for the
[Azure N-Series Preview](http://gpu.azure.com/) and have escalated a
customer service support ticket to the Azure Batch team to enable this
feature. Otherwise, your pool allocation will fail.**

The pool configuration should enable the following properties:
* `vm_size` must be one of `STANDARD_NC6`, `STANDARD_NC12`, `STANDARD_NC24`,
`STANDARD_NV6`, `STANDARD_NV12`, `STANDARD_NV24`. `NC` VM instances feature
K80 GPUs for GPU compute acceleration while `NV` VM instances feature
M60 GPUs for visualization workloads.
* `publisher` should be `Canonical`. Other publishers will be supported
once they are available for N-series VMs.
* `offer` should be `UbuntuServer`. Other offers will be supported once they
are available for N-series VMs.
* `sku` should be `16.04.0-LTS`. Other skus will be supported once they are
available for N-series VMs.
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Caffe GPU-enabled
Docker image.
[alfpark/cntk:gpu-openmpi-mnist-cifar](https://hub.docker.com/r/alfpark/cntk/)
can be used for this recipe which contains reference data for MNIST and CIFAR
examples. If you do not need this reference data then you can use the
`alfpark/cntk:gpu-openmpi` image instead.

### Non-MPI Jobs Configuration (SingleNode+SingleGPU)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/cntk:gpu-openmpi-mnist-cifar`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/cntk:gpu-openmpi-mnist-cifar` Docker image and to run the
MNIST convolutional example on a single GPU, the `command` would simply
be:
`"/bin/bash -c \"cp -r /cntk/Examples/Image/MNIST/* . && /cntk/build/cpu/release/bin/cntk configFile=Config/02_Convolution_ndl_deprecated.cntk RootDir=.\""`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

### MPI Jobs Configuration (SingleNode+MultiGPU, MultiNode+SingleGPU, MultiNode+MultiGPU)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
Since we are not using either the MNIST or CIFAR examples, this can simply
be `alfpark/cntk:gpu-openmpi`. Please note that the `docker_images` in
the Global Configuration should match this image name.
* `name` is a unique name given to the Docker container instance. This is
required for Multi-Instance tasks.
* `command` should contain the command to pass to the Docker run invocation.
For this example, we will run the Multigpu Simple2d Example in the
`alfpark/cntk:gpu-openmpi` Docker image. The application `command` to run
would be:
`"mpirun --allow-run-as-root --host $AZ_BATCH_HOST_LIST --mca btl_tcp_if_exclude docker0 /bin/bash -c \"export LD_LIBRARY_PATH=/usr/local/openblas/lib:/usr/local/nvidia/lib64 && cp -r /cntk/Examples/Other/Simple2d/* . && /cntk/build/gpu/release/bin/cntk configFile=Config/Multigpu.cntk RootDir=. parallelTrain=true\""`
  * **NOTE:** tasks that span multiple compute nodes will need their output
    stored on a shared file system, otherwise CNTK will fail during test
    as all of the output is written by rank 0 to the specified output
    directory only on that compute node. To override the output directory for
    the example above, add `OutputDir=/some/path` to a shared file system
    location such as Azure File Docker Volume, NFS, GlusterFS, etc. Batch
    Shipyard has automatic support for setting up Azure File Docker Volumes,
    please refer to the
    [Batch Shipyard Configuration doc](../../docs/02-batch-shipyard-configuration.md).
  * `mpirun` requires the following flags:
    * `--alow-run-as-root` allows OpenMPI to run as root, as container is run
      as root.
    * `--host` specifies the host list. Note that you will need to modify
      the `--host` parameter as necessary to ensure OpenMPI properly utilizes
      all of the GPUs on the node if there are more than one. Recall that
      `$AZ_BATCH_HOST_LIST` contains only a list of compute nodes in the pool,
      and not the number of slots. Thus, if this job is run on two
      `STANDARD_NC12` compute nodes, then the `--host` parameter would need to
      be `--host $AZ_BATCH_HOST_LIST,$AZ_BATCH_HOST_LIST` for OpenMPI to
      properly schedule processes across 2 nodes and 4 GPUs (i.e., 4 slots
      total).
    * `--mca btl_tcp_if_exclude docker0` directs OpenMPI to ignore the
      `docker0` interface bridge in the container as this will cause issues
      attempting to connect outbound to other running containers on different
      compute nodes.
  * Please note that for Dockerized MPI containers with gpu (i.e.,
    `nvidia-docker` invocations), although the `exec` call can be wrapped by
    the `nvidia-docker` wrapper, the subsequent `mpirun` which performs a
    remote shell into the other containers does not have this capability. Thus
    some convenience of the `nvidia-docker` wrapper are lost for the invocation
    itself (but not the device pass-through as that has already occurred for
    `docker run`). Thus CUDA library locations will need to be explicitly
    specified in `LD_LIBRARY_PATH` as shown above.
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count` or
    `pool_current_dedicated`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses prior to use:
* [CNTK License](https://github.com/Microsoft/CNTK/blob/master/LICENSE.md)
* [CNTK 1-bit SGD Non-Commercial License](https://cntk1bitsgd.codeplex.com/SourceControl/latest#LICENSE-NON-COMMERCIAL.md)
