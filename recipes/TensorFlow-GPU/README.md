# TensorFlow-GPU
This recipe shows how to run [TensorFlow](https://www.tensorflow.org/) on GPUs
using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be one of `STANDARD_NC6`, `STANDARD_NC12`, `STANDARD_NC24`,
`STANDARD_NV6`, `STANDARD_NV12`, `STANDARD_NV24`. `NC` VM instances feature
K80 GPUs for GPU compute acceleration while `NV` VM instances feature
M60 GPUs for visualization workloads. Because TensorFlow is a GPU-accelerated
compute application, it is best to choose `NC` VM instances.
* `publisher` should be `Canonical`. Other publishers will be supported
once they are available for N-series VMs.
* `offer` should be `UbuntuServer`. Other offers will be supported once they
are available for N-series VMs.
* `sku` should be `16.04.0-LTS`. Other skus will be supported once they are
available for N-series VMs.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid TensorFlow GPU-enabled
Docker image. The
[alfpark/tensorflow:1.0.0-gpu](https://hub.docker.com/r/alfpark/tensorflow/)
image contains TensorFlow optimized for Azure N-Series VMs (NVIDIA K80 and
M60). The official Google
[gcr.io/tensorflow/tensorflow:1.0.0-gpu](https://www.tensorflow.org/install/install_linux#InstallingDocker)
docker image can also be used, but note that image may not provide optimal
performance on `STANDARD_NC` series VMs (NVIDIA K80).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/tensorflow:1.0.0-gpu`
* `command` should contain the command to pass to the Docker run invocation.
To run the
[MNIST convolutional example](https://github.com/tensorflow/models/tree/master/tutorials/image/mnist),
the `command` would look like:
`"/bin/bash -c \"curl -fSsL https://raw.githubusercontent.com/tensorflow/models/master/tutorials/image/mnist/convolutional.py | python\""`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following license prior to use:
* [TensorFlow License](https://github.com/tensorflow/tensorflow/blob/master/LICENSE)
