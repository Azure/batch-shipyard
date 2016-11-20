# TensorFlow-Distributed
This recipe shows how to run [TensorFlow](https://www.tensorflow.org/) in
distributed mode across multiple CPUs or GPUs (either single node or multinode)
using N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
**Note: If you are running across multiple GPUs, you must be approved for the
[Azure N-Series Preview](http://gpu.azure.com/) and have escalated a
customer service support ticket with your Batch account details to the Azure
Batch team to enable this feature. Otherwise, your pool allocation will fail.**

The pool configuration should enable the following properties if on multiple
GPUs:
* `vm_size` must be one of `STANDARD_NC6`, `STANDARD_NC12`, `STANDARD_NC24`,
`STANDARD_NV6`, `STANDARD_NV12`, `STANDARD_NV24` if using GPUs.
`NC` VM instances feature K80 GPUs for GPU compute acceleration while `NV` VM
instances feature M60 GPUs for visualization workloads. Because TensorFlow is
a GPU-accelerated compute application, it is best to choose `NC` VM instances.
If not using GPUs, another appropriate SKU can be selected.
* `publisher` should be `Canonical` if using GPUs. Other publishers will be
supported once they are available for N-series VMs.
* `offer` should be `UbuntuServer` if using GPUs. Other offers will be
supported once they are available for N-series VMs.
* `sku` should be `16.04.0-LTS` if using GPUs. Other skus will be supported
once they are available for N-series VMs.

If on multiple CPUs:
* `max_tasks_per_node` must be set to 1 or omitted

Other pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values for multiple CPU configuration.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid TensorFlow Docker
image that can work with multi-instance tasks. The
[alfpark/tensorflow](https://hub.docker.com/r/alfpark/tensorflow)
images have been prepared by extending Google's official TensorFlow image to
work with Batch Shipyard.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/tensorflow/0.10.0-gpu` or `alfpark/tensorflow/0.10.0-cpu`
* `command` should contain the command to pass to the Docker run invocation.
To run the example MNIST replica example, the `command` would look
like: `"/bin/bash /sw/launcher.sh"`. The launcher will automatically detect
the number of GPUs and pass the correct number to the TensorFlow script.
Please see the [launcher.sh](docker/gpu/launcher.sh) for the launcher source.
* `gpu` must be set to `true` if run on GPUs. This enables invoking the
`nvidia-docker` wrapper. This property should be omitted or set to `false`
if run on CPUs.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count` or
    `pool_current_dedicated`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker images can be found [here](./docker).

You must agree to the following license prior to use:
* [TensorFlow License](https://github.com/tensorflow/tensorflow/blob/master/LICENSE)
