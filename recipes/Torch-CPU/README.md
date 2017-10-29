# Torch-CPU
This recipe shows how to run [Torch](http://torch.ch/) on
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
* `docker_images` array must have a reference to a valid Torch CPU-enabled
Docker image. [alfpark/torch:cpu](https://hub.docker.com/r/alfpark/torch/) can
be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/torch:cpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/torch:cpu` Docker image and to run the MNIST convolutional
example, the [`run_mnist.sh` helper script](docker/run_mnist.sh) is used.
The `command` should be: `"/root/torch/run_mnist.sh"`

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the [Torch License](https://github.com/torch/torch7/blob/master/COPYRIGHT.txt)
prior to use.
