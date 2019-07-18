# CNTK-CPU-OpenMPI
This recipe shows how to run [CNTK](https://cntk.ai/) on CPUs on one or
many compute nodes via MPI.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid CNTK CPU-enabled
Docker image. For singlenode (non-MPI) jobs, you can use the official
[Microsoft CNTK Docker images](https://hub.docker.com/r/microsoft/cntk/).
For MPI jobs, you will need to use Batch Shipyard compatible Docker images
which can be found in the
[alfpark/cntk](https://hub.docker.com/r/alfpark/cntk/) repository.
Images denoted with `refdata` tag suffixes found in
can be used for this recipe which contains reference data for MNIST and
CIFAR-10 examples. If you do not need this reference data then you can use
the images without the `refdata` suffix on the image tag.

### Non-MPI Jobs Configuration (SingleNode)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container
invocation, e.g., `microsoft/cntk:2.1-cpu-python3.5`
* `command` should contain the command to pass to the Docker run invocation.
For the `microsoft/cntk:2.1-cpu-python3.5` Docker image and to run
the MNIST convolutional example on a single CPU, the `command` would be:
`"/bin/bash -c \"source /cntk/activate-cntk && cd /cntk/Examples/Image/DataSets/MNIST && python -u install_mnist.py && cd /cntk/Examples/Image/Classification/ConvNet/Python && python -u ConvNet_MNIST.py\""`

### MPI Jobs Configuration (MultiNode)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation.
For this example, this should be `alfpark/cntk:2.1-cpu-py35-refdata`.
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
  * `mpi` property must be defined
    * `runtime` should be set to `openmpi`
    * `executable_path` should be set to `/root/openmpi/bin/mpiexec`
    * `processes_per_node` should be set to `1`
* `command` should contain the command to pass to the `mpiexec` invocation.
For this example, we will run the MNIST convolutional example with Data
augmentation in the `alfpark/cntk:2.1-cpu-py35-refdata` Docker image. Before
running the example, we need to activate CNTK. The application `command` to
run would then be:
`/bin/bash -c "source /cntk/activate-cntk; python -u /cntk/Examples/Image/Classification/ConvNet/Python/ConvNet_CIFAR10_DataAug_Distributed.py -datadir /cntk/Examples/Image/DataSets/CIFAR-10 -outputdir $AZ_BATCH_TASK_WORKING_DIR/output"`

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker).

You must agree to the following licenses prior to use:
* [CNTK License](https://github.com/Microsoft/CNTK/blob/master/LICENSE.md)
* [CNTK 1-bit SGD License](https://github.com/microsoft/cntk/wiki/CNTK-1bit-SGD-License)
