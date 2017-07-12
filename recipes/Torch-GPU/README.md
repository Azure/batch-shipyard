# Torch-GPU
This recipe shows how to run [Torch](http://torch.ch/) on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be one of `STANDARD_NC6`, `STANDARD_NC12`, `STANDARD_NC24`,
`STANDARD_NV6`, `STANDARD_NV12`, `STANDARD_NV24`. `NC` VM instances feature
K80 GPUs for GPU compute acceleration while `NV` VM instances feature
M60 GPUs for visualization workloads. Because Torch is a GPU-accelerated
compute application, it is best to choose `NC` VM instances.
* `vm_configuration` is the VM configuration
  * `platform_image` specifies to use a platform image
    * `publisher` should be `Canonical` or `OpenLogic`.
    * `offer` should be `UbuntuServer` for Canonical or `CentOS` for OpenLogic.
    * `sku` should be `16.04-LTS` for Ubuntu or `7.3` for CentOS.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Torch GPU-enabled
Docker image. [alfpark/torch:gpu](https://hub.docker.com/r/alfpark/torch/) can
be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/torch:gpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/torch:gpu` Docker image and to run the MNIST convolutional
example on the GPU, the `command` would simply be:
`"/root/torch/run_mnist.sh"`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the [Torch License](https://github.com/torch/torch7/blob/master/COPYRIGHT.txt)
prior to use.
