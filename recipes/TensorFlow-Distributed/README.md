# TensorFlow-Distributed
This recipe shows how to run [TensorFlow](https://www.tensorflow.org/) in
distributed mode across multiple CPUs or GPUs (either single node or multinode)
using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties if on multiple
GPUs:
* `vm_size` must be one of `STANDARD_NC6`, `STANDARD_NC12`, `STANDARD_NC24`,
`STANDARD_NV6`, `STANDARD_NV12`, `STANDARD_NV24` if using GPUs.
`NC` VM instances feature K80 GPUs for GPU compute acceleration while `NV` VM
instances feature M60 GPUs for visualization workloads. Because TensorFlow is
a GPU-accelerated compute application, it is best to choose `NC` VM instances.
If not using GPUs, another appropriate SKU can be selected.
* `vm_configuration` is the VM configuration
  * `platform_image` specifies to use a platform image
    * `publisher` should be `Canonical` or `OpenLogic` if using GPUs. Other
      supported publishers can be used if not.
    * `offer` should be `UbuntuServer` for Canonical or `CentOS` for OpenLogic
      if using GPUs. Other supported offers can be used if not.
    * `sku` should be `16.04-LTS` for Ubuntu or `7.3` for CentOS if using
      GPUs. Other supported skus can be used if not.

If on multiple CPUs:
* `max_tasks_per_node` must be set to 1 or omitted

Other pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values for multiple CPU configuration.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid TensorFlow Docker
image that can work with multi-instance tasks. The
[alfpark/tensorflow](https://hub.docker.com/r/alfpark/tensorflow)
images have been prepared by using Google's TensorFlow Dockerfile as a base
and extending the image to work with Batch Shipyard along with optimizations
for `STANDARD_NC` VMs (NVIDIA K80).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/tensorflow/0.11.0-gpu` or `alfpark/tensorflow/0.11.0-cpu`
* `command` should contain the command to pass to the Docker run invocation.
To run the example MNIST replica example, the `command` would look
like: `"/bin/bash /sw/launcher.sh"`. The launcher will automatically detect
the number of GPUs and pass the correct number to the TensorFlow script.
Please see the [launcher.sh](docker/gpu/launcher.sh) for the launcher source.
* `gpu` must be set to `true` if run on GPUs. This enables invoking the
`nvidia-docker` wrapper. This property should be omitted or set to `false`
if run on CPUs.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`
  * `resource_files` should be unset or the array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker images can be found [here](./docker).

You must agree to the following license prior to use:
* [TensorFlow License](https://github.com/tensorflow/tensorflow/blob/master/LICENSE)
