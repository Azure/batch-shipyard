# TensorFlow-GPU
This recipe shows how to run [TensorFlow](https://www.tensorflow.org/) on GPUs
using N-series Azure VM instances in an Azure Batch compute pool.

Execution under both Docker and Singularity are shown in this recipe.

## Configuration
Please see refer to the [set of sample configuration files](./config) for
this recipe. The directory `docker` will contain the Docker-based execution
while the `singularity` directory will contain the Singularity-based
execution configuration.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because TensorFlow is a
GPU-accelerated compute application, you should choose a GPU compute
accelerated VM instance size.
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with GPU as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).
VM instance size.

### Global Configuration
#### Docker-based
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid TensorFlow GPU-enabled
Docker image. The official Google
[TensorFlow GPU Docker images](https://www.tensorflow.org/install/install_linux#gpu_support)
can be used for this recipe (e.g., gcr.io/tensorflow/tensorflow:latest-gpu)

#### Singularity-based
The global configuration should set the following properties:
* `singularity_images` array must have a reference to a valid TensorFlow
GPU-enabled Docker image. The Docker Hub Google
[TensorFlow GPU Docker images](https://hub.docker.com/r/tensorflow/tensorflow/)
on can be used for this recipe
(e.g., docker://tensorflow/tensorflow:latest-gpu)

### Jobs Configuration
#### Docker-based
The jobs configuration should set the following properties within the `tasks`
array to run the
[MNIST convolutional example](https://github.com/tensorflow/models/tree/master/tutorials/image/mnist).
This array should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container
invocation that matches the global configuration Docker image,
e.g., `gcr.io/tensorflow/tensorflow:latest-gpu`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `convolutional.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/tensorflow/models/master/tutorials/image/mnist/convolutional.py`
* `command` should contain the command to pass to the Docker run invocation.
To run the MNIST convolutional example, the `command` would be:
`python -u convolutional.py`
* `gpu` can be set to `true`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool.

#### Singularity-based
The jobs configuration should set the following properties within the `tasks`
array to run the
[MNIST convolutional example](https://github.com/tensorflow/models/tree/master/tutorials/image/mnist).
This array should have a task definition containing:
* `singularity_image` should be the name of the Singularity image for this
container invocation that matches the global configuration image,
e.g., `docker://tensorflow/tensorflow:latest-gpu`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `convolutional.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/tensorflow/models/master/tutorials/image/mnist/convolutional.py`
* `command` should contain the command to pass to the Docker run invocation.
To run the MNIST convolutional example, the `command` would be:
`python -u convolutional.py`
* `gpu` can be set to `true`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool.

### Tensorboard
If you would like to tunnel Tensorboard to your local machine, use the
`jobs-tb.yaml` file instead. This requires that a pool SSH user was added,
and `ssh` or `ssh.exe` is available. This configuration will output summary
data to the directory specified in the `--log_dir` parameter. After the job
is submitted, you can start the remote Tensorboard instance with the command:

```shell
shipyard misc tensorboard
```

Which will output some text similar to the following:

```
>> Please connect to Tensorboard at http://localhost:6006/

>> Note that Tensorboard may take a while to start if the Docker image is
>> not present. Please keep retrying the URL every few seconds.

>> Terminate your session with CTRL+C

>> If you cannot terminate your session cleanly, run:
     shipyard pool ssh --nodeid tvm-1518333292_4-20170428t151941z sudo docker kill 9e7879b8
```

With a web browser, navigate to http://localhost:6006/ where Tensorboard
will be displayed.

Note that the task does not have to be completed for Tensorboard to be run,
it can be running while Tensorboard is running.
