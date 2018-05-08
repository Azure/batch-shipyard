# MADL-CPU-IntelMPI
This recipe shows how to run Microsoft Azure Distributed Linear Learner (MADL) on CPUs across
Azure VMs via Intel MPI.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` should be a CPU-only instance, 'STANDARD_D2_V2'.
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted
* `publisher` should be `Canonical` 
* `offer` should be `UbuntuServer`
* `sku` should be `7.3`

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid MADL
Docker image that can be run with OpenMPI. The image denoted with `0.0.1` tag found in [msmadl/symsgd:0.0.1](https://hub.docker.com/r/msmadl/symsgd/)
is compatible with Azure Batch Shipyard VMs. 

### MPI Jobs Configuration (MultiNode)
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation.
For this example, this should be
`msmadl/symsgd:0.0.1`.
Please note that the `docker_images` in the Global Configuration should match
this image name.
* `command` should contain the command to pass to the Docker run invocation.
For this example, we will run MADL training example in the `msmadl/symsgd:0.0.1` Docker image. The
application `command` to run would be:
`"/parasail/run_parasail.sh -w /parasail/supersgd -l 1e-4 -k 32 -m 1e-2 -e 10 -r 10 -f /parasail/rcv1- -t 1 -n 47237 -g 1 -d $AZ_BATCH_TASK_WORKING_DIR/models/"`
  * [`run_parasail.sh`](docker/run_parasail.sh) has these parameters
    * `-w` the MADL superSGD directory
    * `-l` learning rate
    * `-k` approximation rank constant
    * `-m` model combiner convergence threshold
    * `-e` total epochs
    * `-r` rounds per epoch
    * `-f` training file prefix
    * `-t` number of threads
    * `-n` number of features
    * `-g` log global models every this many epochs
    * `-d` log global models to this directory at the host"
* training data should be deployed to each VM under the parasail working directory in a folder with this name 'rcv1-00000'
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`.
  * `resource_files` should be unset or the array can be empty

## Dockerfile and supplementary files
Supplementary files can be found [here](./docker).

You must agree to the following licenses prior to use:
* [MADL License](link to license)
