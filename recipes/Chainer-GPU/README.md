# Chainer-GPU
This recipe shows how to run [Chainer](http://chainer.org/) on
GPUs using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be one of `STANDARD_NC6`, `STANDARD_NC12`, `STANDARD_NC24`,
`STANDARD_NV6`, `STANDARD_NV12`, `STANDARD_NV24`. `NC` VM instances feature
K80 GPUs for GPU compute acceleration while `NV` VM instances feature
M60 GPUs for visualization workloads. Because Caffe is a GPU-accelerated
compute application, it is best to choose `NC` VM instances.
* `publisher` should be `Canonical`. Other publishers will be supported
once they are available for N-series VMs.
* `offer` should be `UbuntuServer`. Other offers will be supported once they
are available for N-series VMs.
* `sku` should be `16.04-LTS`. Other skus will be supported once they are
available for N-series VMs.

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
`command` would be: `python -u train_mnist.py -g 0`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

Note that you could have inlined the download in the command itself provided
the Docker image has programs to fetch content from the required source.
