# PyTorch-CPU
This recipe shows how to run [PyTorch](https://pytorch.org/) on
a single node using CPU only. This sample executes the MNIST example.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
Pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid PyTorch
Docker image. [pytorch/pytorch](https://hub.docker.com/r/pytorch/pytorch/) can
be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `pytorch/pytorch`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `main.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/pytorch/examples/master/mnist/main.py`
* `command` should contain the command to pass to the Docker run invocation.
To run the MNIST example, the `command` would be: `python -u main.py --no-cuda`
