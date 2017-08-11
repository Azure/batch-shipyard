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
* `vm_configuration` is the VM configuration
  * `platform_image` specifies to use a platform image
    * `publisher` should be `Canonical` or `OpenLogic`.
    * `offer` should be `UbuntuServer` for Canonical or `CentOS` for OpenLogic.
    * `sku` should be `16.04-LTS` for Ubuntu or `7.3` for CentOS.
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid CNTK GPU-enabled
Docker image. For singlenode (non-MPI) jobs, you can use the official
[Microsoft CNTK Docker images](https://hub.docker.com/r/microsoft/cntk/).
For MPI jobs, you will need to use Batch Shipyard compatible Docker images
which can be found in the
[alfpark/cntk](https://hub.docker.com/r/alfpark/cntk/) repository.
Images denoted with `refdata` tag suffixes found in
can be used for this recipe which contains reference data for MNIST and
CIFAR-10 examples. If you do not need this reference data then you can use
the images without the `refdata` suffix on the image tag.

### Non-MPI Jobs Configuration (SingleNode+SingleGPU)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container
invocation, e.g., `microsoft/cntk:2.1-gpu-python3.5-cuda8.0-cudnn6.0`
* `command` should contain the command to pass to the Docker run invocation.
For the `microsoft/cntk:2.1-gpu-python3.5-cuda8.0-cudnn6.0` Docker image, and
to run the MNIST convolutional example on a single CPU, the `command` would
be:
`"/bin/bash -c \"source /cntk/activate-cntk && cd /cntk/Examples/Image/DataSets/MNIST && python -u install_mnist.py && cd /cntk/Examples/Image/Classification/ConvNet/Python && python -u ConvNet_MNIST.py\""`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

### MPI Jobs Configuration (SingleNode+MultiGPU, MultiNode+SingleGPU, MultiNode+MultiGPU)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
For this example, this can be
`alfpark/cntk:2.1-gpu-1bitsgd-py35-cuda8-cudnn6-refdata`.
Please note that the `docker_images` in the Global Configuration should match
this image name.
* `command` should contain the command to pass to the Docker run invocation.
For this example, we will run the ResNet-20 Distributed training on CIFAR-10
example in the `alfpark/cntk:2.1-gpu-1bitsgd-py35-cuda8-cudnn6-refdata`
Docker image. The application `command` to run would be:
`"/cntk/run_cntk.sh -s /cntk/Examples/Image/Classification/ResNet/Python/TrainResNet_CIFAR10_Distributed.py -- --network resnet20 -q 1 -a 0 --datadir /cntk/Examples/Image/DataSets/CIFAR-10 --outputdir $AZ_BATCH_TASK_WORKING_DIR/output"`
  * [`run_cntk.sh`](docker/run_cntk.sh) has two parameters
    * `-s` for the Python script to run
    * `-w` for the working directory (not required for this example to run)
    * `--` parameters specified after this are given verbatim to the
      Python script
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.
* `multi_instance` property must be defined for multinode executions
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_specification_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`
  * `resource_files` should be unset or the array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses prior to use:
* [CNTK License](https://github.com/Microsoft/CNTK/blob/master/LICENSE.md)
* [CNTK 1-bit SGD License](https://github.com/microsoft/cntk/wiki/CNTK-1bit-SGD-License)
