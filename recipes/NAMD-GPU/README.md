# NAMD-GPU
This recipe shows how to run [NAMD](http://www.ks.uiuc.edu/Research/namd/)
2.11 on Linux using the
[Charm++ runtime](http://charm.cs.illinois.edu/manuals/html/charm++/)
for single-node GPU execution which can span multiple GPUs if available.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because NAMD is a GPU-accelerated
compute application, you should choose a GPU compute accelerated VM
instance size.
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with GPU as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to the NAMD-GPU image. This
can be `alfpark/namd:2.11-cuda` which is published on
[Docker Hub](https://hub.docker.com/r/alfpark/namd/).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/namd:2.11-cuda`
* `command` should contain the `mpirun` command. If using the sample NAMD-GPU
image provided, `"/sw/run_namd.sh <benchmark> <steps> <ppn>"` can be used
to run the included benchmarks:
  * `<benchmark>` is the benchmark to run: `apoa1` or `stmv`
  * `<steps>` is the number of steps to execute
  * `<ppn>` is the number of cores on each compute node. This is optional
    and, if omitted, will be determined dynamically.
* `gpus` can be set to `all`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool and can be omitted.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[NAMD license](http://www.ks.uiuc.edu/Research/namd/license.html) before
using this Docker image.
