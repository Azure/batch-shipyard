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
[gcr.io/tensorflow/tensorflow](https://www.tensorflow.org/install/install_linux#InstallingDocker)
can work with this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array to run the
[MNIST convolutional example](https://github.com/tensorflow/models/tree/master/tutorials/image/mnist).
This array should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `gcr.io/tensorflow/tensorflow`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `train_mnist.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/tensorflow/models/master/tutorials/image/mnist/convolutional.py`
* `command` should contain the command to pass to the Docker run invocation.
To run the MNIST convolutional example, the `command` would be:
`python -u convolutional.py`
