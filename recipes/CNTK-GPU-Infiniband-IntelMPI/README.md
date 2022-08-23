# CNTK-GPU-Infiniband-IntelMPI
This recipe shows how to run [CNTK](https://cntk.ai/) on GPUs across
Infiniband/RDMA enabled Azure VMs via Intel MPI.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a
[GPU RDMA-enabled instance](https://docs.microsoft.com/azure/virtual-machines/linux/sizes-gpu).
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with GPU+IB/RDMA as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).
* `inter_node_communication_enabled` must be set to `true`
* `task_slots_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid CNTK GPU-enabled
Docker image that can be run with Intel MPI. Images denoted with `gpu` and
`intelmpi` tags found in [alfpark/cntk](https://hub.docker.com/r/alfpark/cntk/)
are compatible with Azure VMs with GPUs and RDMA. Images denoted with
`refdata` tag suffixes found in
[alfpark/cntk](https://hub.docker.com/r/alfpark/cntk/)
can be used for this recipe which contains reference data for MNIST and
CIFAR-10 examples. If you do not need this reference data then you can use
the images without the `refdata` suffix on the image tag. For this example,
`alfpark/cntk:2.1-gpu-1bitsgd-py36-cuda8-cudnn6-intelmpi-refdata` can be used.

### MPI Jobs Configuration (MultiNode)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation.
For this example, this should be
`alfpark/cntk:2.1-gpu-1bitsgd-py36-cuda8-cudnn6-intelmpi-refdata`.
Please note that the `docker_images` in the Global Configuration should match
this image name.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_specification_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard `sshd` is required.
  * `resource_files` should be unset or the array can be empty
  * `pre_execution_command` should source the cntk activation script and the
    Intel `mpivars.sh` script:
    `source /cntk/activate-cntk; source /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh`
  * `mpi` property must be defined
    * `runtime` should be set to `intelmpi`
    * `processes_per_node` should be set to `nvidia-smi -L | wc -l`
* `command` should contain the command to pass to the `mpirun` invocation.
For this example, we will run the ResNet-20 Distributed training on CIFAR-10
example in the `alfpark/cntk:2.1-gpu-1bitsgd-py35-cuda8-cudnn6-refdata`
Docker image. The application `command` to run would be:
`python -u /cntk/Examples/Image/Classification/ResNet/Python/TrainResNet_CIFAR10_Distributed.py --network resnet20 -q 1 -a 0 --datadir /cntk/Examples/Image/DataSets/CIFAR-10 --outputdir $AZ_BATCH_TASK_WORKING_DIR/output`
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.
* `gpus` can be set to `all`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool and can be omitted.

## Dockerfile and supplementary files
Supplementary files can be found [here](./docker).

You must agree to the following licenses prior to use:
* [CNTK License](https://github.com/Microsoft/CNTK/blob/master/LICENSE.md)
* [CNTK 1-bit SGD License](https://github.com/microsoft/cntk/wiki/CNTK-1bit-SGD-License)
