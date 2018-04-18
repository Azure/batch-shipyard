# Keras+Theano-GPU
This recipe shows how to run [Keras](https://keras.io/) with the
[Theano](http://www.deeplearning.net/software/theano/) backend on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because Keras is a GPU-accelerated
compute application, you should choose a GPU compute accelerated VM
instance size.
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with GPU as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Keras+Theano
GPU-enabled Docker image.
[alfpark/keras:gpu](https://hub.docker.com/r/alfpark/keras/) can be used for
this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/keras:gpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/keras:gpu` Docker image and to run the MNIST convolutional
example, the `command` would simply be:
`"python -u /keras/examples/mnist_cnn.py"`
* `gpu` can be set to `true`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses prior to use:
* [Keras License](https://github.com/fchollet/keras/blob/master/LICENSE)
* [Theano License](https://github.com/Theano/Theano/blob/master/doc/LICENSE.txt)
