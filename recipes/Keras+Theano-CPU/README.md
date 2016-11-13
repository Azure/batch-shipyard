# Keras+Theano-CPU
This recipe shows how to run [Keras](https://keras.io/) with the
[Theano](http://www.deeplearning.net/software/theano/) backend on
a single node using CPU only.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `max_tasks_per_node` must be set to 1 or omitted

Other pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Keras+Theano
CPU-enabled Docker image.
[alfpark/keras:cpu](https://hub.docker.com/r/alfpark/keras/) can be used for
this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/keras:cpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/keras:cpu` Docker image and to run the MNIST convolutional
example, the `command` would simply be:
`"python /keras/examples/mnist_cnn.py"`

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses prior to use:
* [Keras License](https://github.com/fchollet/keras/blob/master/LICENSE)
* [Theano License](https://github.com/Theano/Theano/blob/master/doc/LICENSE.txt)
