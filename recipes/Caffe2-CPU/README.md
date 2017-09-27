# Caffe2-CPU
This recipe shows how to run [Caffe2](https://caffe2.ai/) on a single CPU node.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable or set the following properties:
* `max_tasks_per_node` must be set to 1 or omitted

Other pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Caffe2 CPU-enabled
Docker image. The official [Caffe2 Docker images](https://hub.docker.com/r/caffe2ai/caffe2/)
can be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container
invocation, e.g., `caffe2ai/caffe2:c2v0.8.1.cpu.full.ubuntu14.04`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `mnist.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/Azure/batch-shipyard/master/recipes/Caffe2-CPU/scripts/mnist.py`
* `command` should contain the command to pass to the Docker run invocation.
For the `caffe2ai/caffe2:c2v0.8.1.cpu.full.ubuntu14.04` Docker image and
the sample script above, the `command` would be: `python -u mnist.py`
