# Caffe2-GPU
This recipe shows how to run [Caffe2](https://caffe2.ai/) on a single GPU
N-series VM.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because Caffe2 is a GPU-accelerated
compute application, you should choose an `ND`, `NC` or `NCv2` VM instance
size.
* `vm_configuration` is the VM configuration
  * `platform_image` specifies to use a platform image
    * `publisher` should be `Canonical` or `OpenLogic`
    * `offer` should be `UbuntuServer` for Canonical or `CentOS` for OpenLogic
    * `sku` should be `16.04-LTS` for Ubuntu or `7.3` for CentOS

Other pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Caffe2 GPU-enabled
Docker image. The official [Caffe2 Docker images](https://hub.docker.com/r/caffe2ai/caffe2/)
can be used for this recipe. The Docker image `caffe2ai/caffe2` may be used.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container
invocation, e.g., `caffe2ai/caffe2`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `mnist.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/Azure/batch-shipyard/master/recipes/Caffe2-CPU/scripts/mnist.py`
* `command` should contain the command to pass to the Docker run invocation.
For the `caffe2ai/caffe2` Docker image and the sample script above, the
`command` would be: `python -u mnist.py --gpu`
* `gpu` can be set to `true`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool.
