# Caffe-GPU
This recipe shows how to run [Caffe](http://caffe.berkeleyvision.org/) on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because Caffe is a GPU-accelerated
compute application, you should choose an `ND`, `NC` or `NCv2` VM instance
size.
* `vm_configuration` is the VM configuration
  * `platform_image` specifies to use a platform image
    * `publisher` should be `Canonical` or `OpenLogic`.
    * `offer` should be `UbuntuServer` for Canonical or `CentOS` for OpenLogic.
    * `sku` should be `16.04-LTS` for Ubuntu or `7.3` for CentOS.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Caffe GPU-enabled
Docker image. Although you can use the official
[BVLC/caffe](https://hub.docker.com/r/bvlc/caffe/) Docker images, for this
recipe the [alfpark/caffe:gpu](https://hub.docker.com/r/alfpark/caffe/)
contains all of the required files and scripts to run the MNIST convolutional
example.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/caffe:gpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/caffe:gpu` Docker image and to run the MNIST convolutional
example on all available GPUs, we are using a
[`run_mnist.sh` helper script](docker/run_mnist.sh). Thus, the `command` would
simply be: `"/caffe/run_mnist.sh -gpu all"`
* `gpu` can be set to `true`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the [Caffe License](https://github.com/BVLC/caffe/blob/master/LICENSE)
prior to use.
