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
* `sku` should be `16.04-LTS`. Other skus will be supported once they are
available for N-series VMs.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid TensorFlow GPU-enabled
Docker image. The official Google
[gcr.io/tensorflow/tensorflow:1.1.0-gpu](https://www.tensorflow.org/install/install_linux#InstallingDocker)
docker image can be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array to run the
[MNIST convolutional example](https://github.com/tensorflow/models/tree/master/tutorials/image/mnist).
This array should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `gcr.io/tensorflow/tensorflow:1.1.0-gpu`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `train_mnist.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/tensorflow/models/master/tutorials/image/mnist/convolutional.py`
* `command` should contain the command to pass to the Docker run invocation.
To run the MNIST convolutional example, the `command` would be:
`python -u convolutional.py`
* `gpu` must be set to `true`. This enables invoking the `nvidia-docker`
wrapper.

### Tensorboard
If you would like to tunnel Tensorboard to your local machine, use the
`jobs-tb.json` file instead. This requires that a pool SSH user was added,
and `ssh` or `ssh.exe` is available. This configuration will output summary
data to the directory specified in the `--log_dir` parameter. After the job
is submitted, you can start the remote Tensorboard instance with the command:

```shell
shipyard misc tensorboard --image gcr.io/tensorflow/tensorflow:1.1.0-gpu
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
