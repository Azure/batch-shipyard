# Chainer-CPU
This recipe shows how to run [Chainer](http://chainer.org/) on
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
* `docker_images` array must have a reference to a valid Caffe CPU-enabled
Docker image. The official [chainer](https://hub.docker.com/r/chainer/chainer/)
Docker image can be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `chainer/chainer`
* `command` should contain the command to pass to the Docker run invocation.
For the `chainer/chainer` Docker image and to run the MNIST MLP example, the
`command` would be:
`"/bin/bash -c \"python -c \\\"import requests; print(requests.get(\\\\\\\"https://raw.githubusercontent.com/pfnet/chainer/master/examples/mnist/train_mnist.py\\\\\\\").text)\\\" > train_mnist.py && python -u train_mnist.py\""`
