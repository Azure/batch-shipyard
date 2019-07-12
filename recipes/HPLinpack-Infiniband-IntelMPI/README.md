# HPLinpack-Infiniband-IntelMPI
This recipe shows how to run the
[HPLinpack (HPL)](http://www.netlib.org/benchmark/hpl/) benchmark
on Linux using Intel MPI over Infiniband/RDMA Azure VM instances in an Azure
Batch compute pool. Execution of this distributed workload requires the use of
[multi-instance tasks](../../docs/80-batch-shipyard-multi-instance-tasks.md).

Execution under both Docker and Singularity are shown in this recipe.

Note that this container can only be executed on Intel processors.

## Configuration
Please see refer to the [set of sample configuration files](./config) for
this recipe. The directory `docker` will contain the Docker-based execution
while the `singularity` directory will contain the Singularity-based
execution configuration.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` should be a CPU-only
[RDMA-enabled instance](https://docs.microsoft.com/azure/virtual-machines/linux/sizes-hpc).
* `vm_configuration` is the VM configuration. Please select an appropriate
`platform_image` with IB/RDMA as
[supported by Batch Shipyard](../../docs/25-batch-shipyard-platform-image-support.md).
* `inter_node_communication_enabled` must be set to `true`

### Global Configuration
#### Docker-based
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid HPLinpack image
that can be run with Intel MPI and Infiniband in a Docker container context
on Azure VM instances. This can be `alfpark/linpack:2018-intel-mkl` which is
published on [Docker Hub](https://hub.docker.com/r/alfpark/linpack).

#### Singularity-based
The global configuration should set the following properties:
* `singularity_images` array must have a reference to a valid HPLinpack image
that can be run with Intel MPI and Infiniband. This can be
`shub://alfpark/linpack` which is
published on [Singularity Hub](https://www.singularity-hub.org/containers/496).

### Jobs Configuration
#### Docker-based
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `docker_image` should be the name of the Docker image for this container
invocation. For this example, this should be `alfpark/linpack:2018-intel-mkl`.
* `command` is the command that should be invoked by `mpirun`. For this recipe,
the `command` should be:
`/bin/bash -c "cd /opt/intel2/mkl/benchmarks/mp_linpack && ./runme_intel64_prv -p $P -q $Q -b $B $PSIZE"`
* `infiniband` can be set to `true`, however, it is implicitly enabled by
Batch Shipyard when executing on a RDMA-enabled compute pool.
* `additional_docker_run_options` property should contain `"--privileged"`
such that HPL can pin and interleave memory
* `resource_files` should contain the reference to the two helper scripts
for the task, one of which is the `setup_hplinpack.sh` script (which
in turn invokes `findpq.py`) as part of the `pre_execution_command`.
* `environment_variables` should have the following settings
  * `AVX` should be set to the appropriate AVX setting according to VM CPU
    capability. Use `AVX` for A8/A9, use `AVX2` for H-series, or use `AVX512`
    for Hc-series.
* `multi_instance` property must be defined
  * `num_instances` should be set to `pool_specification_vm_count_dedicated`,
    `pool_vm_count_low_priority`, `pool_current_dedicated`, or
    `pool_current_low_priority`
  * `coordination_command` should be unset or `null`. For pools with
    `native` container support, this command should be supplied if
    a non-standard launcher is required.
  * `mpi` property must be defined
    * `runtime` should be either `intelmpi_ofa` or `intelmpi` depending upon
      the Intel MPI version used.
    * `processes_per_node` should be set to `1`
  * `pre_execution_command` should invoke the setup script downloaded as
    a resource file (see above). An example invocation would be:
    `source setup_hplinpack.sh -a $AVX -n 50000; source /opt/intel2/compilers_and_libraries/linux/mpi/bin64/mpivars.sh`
    If you do not specify `-n <problem size>` then the script will attempt to
    create the biggest problem size for the machine's available memory.
    The `run_hplinpack.sh` script has many configuration parameters:
    * `-a`: specify AVX mode, see environment setting above.
    * `-b <block size>`: block size, automatically determined from AVX
      setting if not specified
    * `-m <memory size in MB>`: scale problem size to specified memory size in
      MB. Can be specified instead of `-n`.
    * `-n <problem size>`: problem size. Can be specified instead of `-m`.
    * `-p <grid row dim>`: grid row dimension, this must be less than or equal
      to `-q`. If not specified, will be automatically determined from the
      number of nodes.
    * `-q <grid column dim>`: grid column dimension, this must be greater than
      or equal to `-p`. If not specified, will be automatically determined from
      the number of nodes.

#### Singularity-based
The jobs configuration should set nearly the same properties as the
Docker-based execution except for the following:
* `singularity_image` should be the name of the Singularity image for this
container invocation. For this example, this should be
`library://alfpark/linpack/linpack:2018-intel-mkl`.

## Supplementary files
The `Dockerfile` for the Docker image can be found [here](./docker). The
Singularity hub build and resource files can be found
[here](https://github.com/alfpark/linpack).

Please note that you must agree with the
[Intel Linpack License](https://software.intel.com/en-us/articles/intel-linpack-benchmark-download-license-agreement)
before using either of these images.
