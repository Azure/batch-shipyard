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
array to run the
[MNIST MLP example](https://github.com/pfnet/chainer/tree/master/examples/mnist).
This array should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `chainer/chainer`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `train_mnist.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/pfnet/chainer/master/examples/mnist/train_mnist.py`
* `command` should contain the command to pass to the Docker run invocation.
For the `chainer/chainer` Docker image and to run the MNIST MLP example, the
`command` would be: `python -u train_mnist.py`

Note that you could have inlined the download in the command itself provided
the Docker image has programs to fetch content from the required source.
