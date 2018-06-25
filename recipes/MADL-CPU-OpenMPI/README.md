# MADL-CPU-OpenMPI
This recipe shows how to run High Performance ML Algorithms Learner on CPUs across
Azure VMs via Open MPI.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` should be a CPU-only instance, for example, 'STANDARD_D2_V2'.
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

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
For this MADL training example with the `msmadl/symsgd:0.0.1` Docker image. The
application `command` to run would be:
`"/parasail/run_parasail.sh -w /parasail/supersgd -l 1e-4 -k 32 -m 1e-2 -e 10 -r 10 -f $AZ_BATCH_NODE_SHARED_DIR/azblob/<container_name from the data shredding configuration file> -t 1 -g 1 -d $AZ_BATCH_TASK_WORKING_DIR/models -b $AZ_BATCH_NODE_SHARED_DIR/azblob/<container_name from the data shredding configuration file>"`
  * [`run_parasail.sh`](docker/run_parasail.sh) has these parameters
    * `-w` the MADL superSGD directory
    * `-l` learning rate
    * `-k` approximation rank constant
    * `-m` model combiner convergence threshold
    * `-e` total epochs
    * `-r` rounds per epoch
    * `-f` training file prefix
    * `-t` number of threads
    * `-g` log global models every this many epochs
    * `-d` log global models to this directory at the host"
    * `-b` location for the algorithm's binary"
	
* The training data will need to be shredded to match the number of VMs and the thread's count per VM, and then deployed to a mounted Azure blob that the VM docker images have read/write access.  
A basic python script that can be used to shred and deploy the training data to a blob container, and other data shredding files can be found [here](./DataShredding).
* `shared_data_volumes`  should contain the shared data volume with an `azureblob` volume driver as specified in the global configuration file found [here](./config/config.yaml).

* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_current_dedicated`, or
    `pool_current_low_priority`

## Dockerfile and supplementary files
Supplementary files can be found [here](./docker).

You must agree to the following licenses prior to use:
* [High Performance ML Algorithms License](https://github.com/saeedmaleki/Distributed-Linear-Learner/blob/master/High%20Performance%20ML%20Algorithms%20-%20Standalone%20(free)%20Use%20Terms%20V2%20(06-06-18).txt)
* [TPN Ubuntu Container](https://github.com/saeedmaleki/Distributed-Linear-Learner/blob/master/TPN_Ubuntu%20Container_16-04-FINAL.txt)
* [Microsoft Third Party Notice](https://github.com/saeedmaleki/Distributed-Linear-Learner/blob/master/MicrosoftThirdPartyNotice.txt) 
