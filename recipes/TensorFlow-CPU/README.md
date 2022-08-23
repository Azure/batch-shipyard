# TensorFlow-CPU
This recipe shows how to run [TensorFlow](https://www.tensorflow.org/)
on a single node using a CPU only.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `task_slots_per_node` must be set to 1 or omitted

Other pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid TensorFlow Docker
image that can execute on CPUs. The official Google TensorFlow image
[tensorflow/tensorflow](https://www.tensorflow.org/install/install_linux#InstallingDocker)
can work with this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array to run the
[MNIST convolutional example](https://github.com/tensorflow/models/tree/master/tutorials/image/mnist).
This array should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `tensorflow/tensorflow`
* `resource_files` array should be populated if you want Azure Batch to handle
the download of the training file from the web endpoint:
  * `file_path` is the local file path which should be set to
    `convolutional.py`
  * `blob_source` is the remote URL of the file to retrieve:
    `https://raw.githubusercontent.com/tensorflow/models/master/tutorials/image/mnist/convolutional.py`
* `command` should contain the command to pass to the Docker run invocation.
To run the MNIST convolutional example, the `command` would be:
`python -u convolutional.py`

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
