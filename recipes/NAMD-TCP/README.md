# NAMD-TCP
This recipe shows how to run NAMD 2.10 on Linux using the native Charm++
runtime (as opposed to MPI) over TCP/IP-connected machines in an Azure Batch
pool. Regardless of the underlying message passing infrastructure,
execution requires the use of multi-instance tasks.

Interested in an Infiniband-enabled version of NAMD for use with Batch
Shipyard? Visit [this recipe](../NAMD-Infiniband).

## Configuration
### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` should be set to `true`
* `max_tasks_per_node` should be set to 1

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array should have a reference to the NAMD-TCP image. This
can be `alfpark/namd:2.10-tcp` which is published on
[Docker Hub](https://hub.docker.com/r/alfpark/namd/).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `command` should be something to the effect of
`"/sw/run\_namd.sh <benchmark> <steps> <ppn>"`
  * `<benchmark>` is the benchmark to run: apoa1 or stmv
  * `<steps>` is the number of steps to execute
  * `<ppn>` is the number of cores on each compute node. This is optional
    and, if omitted, will be determined dynamically.
* `infiniband` should be set to `false`
* `multi_instance` property should be defined
  * `num_instances` should be set to `pool_specification_vm_count` or
    `pool_current_dedicated`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be empty

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[NAMD license](http://www.ks.uiuc.edu/Research/namd/license.html) before
using this Docker image.
