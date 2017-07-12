# NAMD-TCP
This recipe shows how to run [NAMD](http://www.ks.uiuc.edu/Research/namd/)
on Linux using the
[Charm++ runtime](http://charm.cs.illinois.edu/manuals/html/charm++/)
(as opposed to pure MPI) over TCP/IP-connected machines in an Azure Batch
compute pool. Regardless of the underlying parallel/distributed programming
paradigm, execution of this distributed workload requires the use of
[multi-instance tasks](../docs/80-batch-shipyard-multi-instance-tasks.md)
when run across multiple nodes.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `max_tasks_per_node` must be set to 1 or omitted

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to the NAMD-TCP image. This
can be `alfpark/namd:2.11-tcp` which is published on
[Docker Hub](https://hub.docker.com/r/alfpark/namd/).

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/namd:2.11-tcp`
* `command` should contain the `mpirun` command. If using the sample NAMD-TCP
image provided, `"/sw/run_namd.sh <benchmark> <steps> <ppn>"` can be used
to run the included benchmarks:
  * `<benchmark>` is the benchmark to run: `apoa1` or `stmv`
  * `<steps>` is the number of steps to execute
  * `<ppn>` is the number of cores on each compute node. This is optional
    and, if omitted, will be determined dynamically.
* `infiniband` must be set to `false`
* `multi_instance` property must be defined for NAMD tasks spanning multiple
nodes.
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`
  * `resource_files` array can be unset or empty

To run this example on just one node, you can omit the `multi_instance`
property altogether.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). Please
note that you must agree with the
[NAMD license](http://www.ks.uiuc.edu/Research/namd/license.html) before
using this Docker image.
