# Chainer-GPU
This recipe shows how to run [Chainer](http://chainer.org/) on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because Chainer is a GPU-accelerated
compute application, you should choose a GPU compute accelerated VM
instance size.
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with GPU as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Caffe GPU-enabled
Docker image. The official [chainer](https://hub.docker.com/r/chainer/chainer/)
Docker image can be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array to run the
[MNIST MLP example](https://github.com/pfnet/chainer/tree/master/examples/mnist).
This array should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `chainer/chainer`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `train_mnist.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/pfnet/chainer/master/examples/mnist/train_mnist.py`
* `command` should contain the command to pass to the Docker run invocation.
For the `chainer/chainer` Docker image and to run the MNIST MLP example, the
`command` would be: `python -u train_mnist.py -g 0`
* `gpus` can be set to `all`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool and can be omitted.

Note that you could have inlined the download in the command itself provided
the Docker image has programs to fetch content from the required source.
