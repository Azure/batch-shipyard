# OSUMicroBenchmarks-Infiniband-MVAPICH
This recipe shows how to run the
[OSU Micro-Benchmarks](http://mvapich.cse.ohio-state.edu/benchmarks/)
on Linux using MVAPICH and Infiniband over Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
[multi-instance tasks](../../docs/80-batch-shipyard-multi-instance-tasks.md).

This recipe demonstrates Singularity usage.

## Configuration
Please see refer to the [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `inter_node_communication_enabled` must be set to `true`
* `task_slots_per_node` must be set to 1 or omitted
* `vm_configuration` must be defined
  * `platform_image` must be defined
    * `publisher` must be set to `OpenLogic`
    * `offer` must be set to `CentOS-HPC`
    * `sku` must be set to `7.6` or later
* `vm_size` must be set to an SR-IOV RDMA compatible VM size such as
`STANDARD_HB60rs` or `STANDARD_HC44rs`

### Global Configuration
The global configuration should set the following properties:
* `singularity_images` array have a reference to a valid OSU
Micro-Benchmark image with MVAPICH. This can be
`library://alfpark/mvapich/mvapich:2.3.2`
Since this image is signed, it should be placed under the `signed` section
with the appropriate `signing_key`. Please see the `config.yaml` file for
more information.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `singularity_iamge` should be the name of the Singularity image for this
container task invocation. For this example, this should be
`library://alfpark/mvapich/mvapich:2.3.2`.
* `environment_variables` are the environment variables to set
    * `BENCHMARK` is the OSU benchmark to execute
    * `BENCHMARK_ARGS` are any arguments to pass to the benchmark executable
* `command` should contain the command to pass to the `mpirun` invocation.
Please see the example `jobs.yaml` configuration for an example.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_specification_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `pre_execution_command` should be the `module load` command to load the
    appropriate MPI into the current environment.
  * `mpi` property must be defined
    * `runtime` should be set to `mvapich`
    * `processes_per_node` should be set to `1`

## Supplementary files
The Singularity image definition file can be found [here](./singularity).
