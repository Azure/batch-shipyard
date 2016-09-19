# TensorFlow-CPU
This recipe shows how to run [TensorFlow](https://www.tensorflow.org/)
on a single node using a CPU only.

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
* `docker_images` array must have a reference to a valid TensorFlow Docker
image that can execute on CPUs. The official Google TensorFlow image
[gcr.io/tensorflow/tensorflow](https://www.tensorflow.org/versions/r0.10/get_started/os_setup.html#docker-installation)
can work with this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `gcr.io/tensorflow/tensorflow`
* `command` should contain the command to pass to the Docker run invocation.
To run the example MNIST convolutional example, the `command` would look like:
`"python -m tensorflow.models.image.mnist.convolutional"`
