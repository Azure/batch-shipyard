# DotNet-Windows
This recipe shows how to run a sample DotNet application on
a single node running Windows Server Containers.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
Pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Windows Docker image.
[microsoft/dotnet-samples:dotnetapp-nanoserver-1809](https://hub.docker.com/r/microsoft/dotnet-samples/)
can be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `microsoft/dotnet-samples:dotnetapp-nanoserver-1809`
* `additional_docker_run_options` property is needed to override the working directory
set by Batch to use the working directory as specified by the image with
`--workdir C:\\app`. Note that not all images will require this option as it is
dependent upon if the application requires starting in a certain working directory.
* `command` should contain the command to pass to the Docker run invocation. This
particular Docker image does not need a command, but will echo anything passed in.
