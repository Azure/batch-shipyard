# DiskSpd-Windows
This recipe shows how to run the [DiskSpd](https://github.com/Microsoft/diskspd)
tool on a single node running Windows Server Containers.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
Pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid Windows Docker image.
[stefanscherer/diskspd:nano](https://hub.docker.com/r/stefanscherer/diskspd/) can
be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `stefanscherer/diskspd:nano`
* `additional_docker_run_options` property is needed to set the
[isolation mode](https://docs.microsoft.com/virtualization/windowscontainers/manage-containers/hyperv-container)
for container execution as `--isolation=hyperv`. This is required as this
container is built using the base OS image that is different from the Host
OS. You can view the Windows container compatibility matrix
[here](https://docs.microsoft.com/virtualization/windowscontainers/deploy-containers/version-compatibility).
* `command` should contain the command to pass to the Docker run invocation. For
this example, we use: `-c8192k -d1 testfile.dat`
