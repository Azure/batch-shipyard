# Caffe-CPU
This recipe shows how to run [Caffe](http://caffe.berkeleyvision.org/) on
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
* `docker_images` array must have a reference to a valid Caffe GPU-enabled
Docker image. [alfpark/caffe:cpu](https://hub.docker.com/r/alfpark/caffe/) can
be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/caffe:cpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/caffe:cpu` Docker image and to run the MNIST convolutional
example, the `command` would simply be:
`"/opt/run_mnist.sh"`

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the [Caffe License](https://github.com/BVLC/caffe/blob/master/LICENSE)
prior to use.
