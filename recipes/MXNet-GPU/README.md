# MXNet-GPU
This recipe shows how to run [MXNet](http://mxnet.io/) on GPUs on one or
more N-series Azure VM instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because MXNet is a GPU-accelerated
compute application, you should choose a GPU compute accelerated VM
instance size.
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with GPU as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).
* `inter_node_communication_enabled` must be set to `true`
* `task_slots_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid MXNet GPU-enabled
Docker image.
[alfpark/mxnet:gpu](https://hub.docker.com/r/alfpark/mxnet/)
can be used for this recipe.
* `volumes` must be populated with the following if running a MXNet
multi-node job:
  * `shared_data_volumes` should contain an Azure File Docker volume driver,
    a GlusterFS share or a manually configured NFS share. Batch
    Shipyard has automatic support for setting up Azure File Docker Volumes
    and GlusterFS, please refer to the
    [Batch Shipyard Configuration doc](../../docs/10-batch-shipyard-configuration.md).

### SingleNode Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/mxnet:gpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/mxnet:gpu` Docker image and to run the MNIST python-backend
example utilizing all GPUs on the node, the `command` would simply be:
`"/mxnet/run_mxnet.sh mnist-py . --model-prefix $AZ_BATCH_TASK_WORKING_DIR/mnist-model"`.
The source for `run_mxnet.sh` can be found [here](./docker/run_mxnet.sh).
  * The first argument to `run_mxnet.sh` is the training example to run. This
    can be one of: `cifar-10-r`, `cifar-10-py`, `mnist-r`, `mnist-py`.
    `cifar-10` examples run resnet. `mnist` examples run lenet.
  * The second argument to `run_mxnet.sh` is the shared file system location.
    For single node executions, this should be `.`.
  * Arguments after the second are passed to the training script. In this
    example, we specify where to save the model.
* `gpus` can be set to `all`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool and can be omitted.

### MultiNode Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation.
This can be `alfpark/mxnet:gpu`. Please note that the `docker_images` in
the Global Configuration should match this image name.
* `command` should contain the command to pass to the Docker run invocation.
For this example, we will run the CIFAR-10 Resnet example across distributed
nodes in the `alfpark/mxnet:gpu` Docker image. Note that for multinode jobs,
the R backend for mxnet currently does not support multiple nodes, please
use the python backend and scripts. The application `command`
to run would be:
`"/mxnet/run_mxnet.sh cifar-10-py $AZ_BATCH_NODE_SHARED_DIR/gfs --model-prefix $AZ_BATCH_TASK_WORKING_DIR/cifar-10-model"`.
The source for `run_mxnet.sh` can be found [here](./docker/run_mxnet.sh).
`run_mxnet.sh` will automatically use all available GPUs on every node.
  * **NOTE:** tasks that span multiple compute nodes will need their input
    stored on a shared file system, otherwise MXNet will not be
    able to start. To override the input directory for the example
    above, specify the parameter to the shell script with the location of
    the shared file system such as Azure File Docker Volume, NFS,
    GlusterFS, etc. The example above already is writing to a GlusterFS share.
* `shared_data_volumes` should have a valid volume name as defined in the
global configuration file. Please see the global configuration section above
for details.
* `gpus` can be set to `all`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool and can be omitted.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses before using this image:
* [MXNet license](https://github.com/dmlc/mxnet/blob/master/LICENSE)
* [R licenses](https://www.r-project.org/Licenses/)
* [R Intel MKL license](https://mran.revolutionanalytics.com/assets/text/mkl-eula.txt)
