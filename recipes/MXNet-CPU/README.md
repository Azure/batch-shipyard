# MXNet-CPU
This recipe shows how to run [MXNet](http://mxnet.io/) on CPUs on one or
many compute nodes via SSH.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid MXNet CPU-enabled
Docker image.
[alfpark/mxnet:cpu](https://hub.docker.com/r/alfpark/mxnet/)
can be used for this recipe.
* `docker_volumes` must be populated with the following if running a MXNet
multi-node job:
  * `shared_data_volumes` should contain an Azure File Docker volume driver,
    a GlusterFS share or a manually configured NFS share. Batch
    Shipyard has automatic support for setting up Azure File Docker Volumes
    and GlusterFS, please refer to the
    [Batch Shipyard Configuration doc](../../docs/10-batch-shipyard-configuration.md).

### SingleNode Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/mxnet:cpu`
* `command` should contain the command to pass to the Docker run invocation.
For the `alfpark/mxnet:cpu` Docker image and to run the MNIST python-backend
example on a single CPU, the `command` would simply be:
`"/mxnet/run_mxnet.sh mnist-py ."`. The source for `run_mxnet.sh` can
be found [here](./docker/run_mxnet.sh).
  * The first argument to `run_mxnet.sh` is the training example to run. This
    can be one of: `cifar-10-r`, `cifar-10-py`, `mnist-r`, `mnist-py`.
    `cifar-10` examples run resnet. `mnist` examples run lenet.
  * The second argument to `run_mxnet.sh` is the shared file system location.
    For single node executions, this should be `.`.
  * Arguments after the second are passed to the training script. For
    instance, if using `mnist` examples, one could pass `--network lenet` to
    change the training network from `mlp` to `lenet`.

### MultiNode Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation.
This can be `alfpark/mxnet:cpu`. Please note that the `docker_images` in
the Global Configuration should match this image name.
* `name` is a unique name given to the Docker container instance. This is
required for Multi-Instance tasks.
* `command` should contain the command to pass to the Docker run invocation.
For this example, we will run the
[CIFAR-10 Example](https://blogs.technet.microsoft.com/machinelearning/2016/09/15/building-deep-neural-networks-in-the-cloud-with-azure-gpu-vms-mxnet-and-microsoft-r-server/)
across distributed nodes in the `alfpark/mxnet:cpu` Docker image. The
application `command` to run would be:
`"/mxnet/run_mxnet.sh cifar-10-r $AZ_BATCH_NODE_SHARED_DIR/gfs"`. The source
for `run_mxnet.sh` can be found [here](./docker/run_mxnet.sh).
  * **NOTE:** tasks that span multiple compute nodes will need their input
    and output stored on a shared file system, otherwise MXNet will not be
    able to start. To override the input/output directory for the example
    above, specify the parameter to the shell script with the location of
    the shared file system such as Azure File Docker Volume, NFS,
    GlusterFS, etc. The example above already is writing to a GlusterFS share.
* `shared_data_volumes` should have a valid volume name as defined in the
global configuration file. Please see the global configuration section above
for details.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count` or
    `pool_current_dedicated`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses before using this image:
* [MXNet license](https://github.com/dmlc/mxnet/blob/master/LICENSE)
* [R licenses](https://www.r-project.org/Licenses/)
* [R Intel MKL license](https://mran.revolutionanalytics.com/assets/text/mkl-eula.txt)
