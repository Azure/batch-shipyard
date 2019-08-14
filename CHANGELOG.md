# Change Log

## [Unreleased]

### Fixed
- Provisioning Network Direct RDMA VM sizes (A8/A9/NC24rX/H16r/H16mr) resulted
in start task failures

## [3.8.0] - 2019-08-13
### Added
- Revamped Singularity support, including support for Singularity 3,
SIF images, and pull support from ACR registries for SIF images via ORAS.
Please see the global and jobs configuration docs for more information.
([#146](https://github.com/Azure/batch-shipyard/issues/146))
- New MPI interface in jobs configuration for seamless multi-instance task
executions with automatic configuration for SR-IOV RDMA VM sizes with support
for popular MPI runtimes including OpenMPI, MPICH, Intel MPI, and MVAPICH
([#287](https://github.com/Azure/batch-shipyard/issues/287))
- Support for Hb/Hc SR-IOV RDMA VM sizes
([#277](https://github.com/Azure/batch-shipyard/issues/277))
- Support for NC/NV/H Promo VM sizes
- Support for user-specified job preparation and release tasks on the host
([#202](https://github.com/Azure/batch-shipyard/issues/202))
- Support for conditional output data
([#230](https://github.com/Azure/batch-shipyard/issues/230))
- Support for bring your own public IP addresses on Batch pools.
Please see the pool configuration doc and the
[Virtual Networks and Public IPs guide](docs/64-batch-shipyard-byovnet.md)
for more information.
- Support for Shared Image Gallery for custom images
- Support for CentOS HPC 7.6 native conversion
- Additional Slurm configuration options
- New recipes: mpiBench across various configurations,
OpenFOAM-Infiniband-OpenMPI, OSUMicroBenchmarks-Infiniband-MVAPICH

### Changed
- **Breaking Change:** the `singularity_images` property in the global
configuration has been modified to accomodate Singularity 3 support.
Please see the global configuration doc for more information.
([#146](https://github.com/Azure/batch-shipyard/issues/146))
- **Breaking Change:** the `gpu` property in the jobs configuration has
been changed to `gpus` to accommodate the new native GPU execution
support in Docker 19.03. Please see the jobs configuration doc for
more information.
([#293](https://github.com/Azure/batch-shipyard/issues/293))
- `pool images` commands now support Singularity
- Non-native task execution is now proxied via script
([#235](https://github.com/Azure/batch-shipyard/issues/235))
- Batch Shipyard images have been migrated to the Microsoft Container Registry
([#278](https://github.com/Azure/batch-shipyard/issues/278))
- Updated Docker CE to 19.03.1
- Updated blobxfer to 1.9.0
- Updated LIS to 4.3.3
- Updated NC/ND driver to 418.67, NV driver to 430.30
- Updated Batch Insights to 1.3.0
- Updated dependencies to latest, where applicable
- Updated Python to 3.7.4 for pre-built binaries
- Updated Docker images to use Alpine 3.10
- Various recipe updates to showcase the new MPI schema, HPLinpack and HPCG
updates to SR-IOV RDMA VM sizes

### Fixed
- Cargo Batch service client update missed
([#274](https://github.com/Azure/batch-shipyard/issues/274), [#296](https://github.com/Azure/batch-shipyard/issues/296))
- Premium File Shares were not enumerating correctly with AAD
([#294](https://github.com/Azure/batch-shipyard/issues/294))
- Per-job autoscratch setup failing for more than 2 nodes

### Removed
- Peer-to-peer image distribution support
- Python 3.4 support

## [3.7.1] - 2019-07-23
### Fixed
- Detection of graph root was broken with new version of Docker client (CLI)
on GPU pools ([#291](https://github.com/Azure/batch-shipyard/issues/291))

## [3.7.0] - 2019-02-28
### Added
- Slurm on Batch support: provision Slurm clusters with elastic cloud bursting
on Azure Batch pools. Please see the
[Slurm on Batch guide](https://github.com/Azure/batch-shipyard/blob/master/docs/69-batch-shipyard-slurm.md).
- Batch Insights integration ([#259](https://github.com/Azure/batch-shipyard/issues/259)),
please see the pool and credentials configuration docs.
- Support environment variables on additional node prep commands ([#253](https://github.com/Azure/batch-shipyard/pull/253))
- Support CentOS 7.6
- `pool exists` command
- `--recreate` flag for `pool add` to allow existing pools to be recreated
- `fs cluster orchestrate` command
- Sample Windows container recipes ([#246](https://github.com/Azure/batch-shipyard/issues/246))

### Changed
- **Breaking Change:** the `additional_node_prep_commands` property has
been migrated under the new `additional_node_prep` property as
`commands` ([#252](https://github.com/Azure/batch-shipyard/issues/252))
- Performance improvements to speed up job submission with large task
factories or large amount of tasks. Verbosity of task generation progress
has been increased which can be modified with `-v`.
- Updated blobxfer to 1.7.0 ([#255](https://github.com/Azure/batch-shipyard/issues/255))
- Updated LIS, NV driver to 410.92 and NC/ND driver to 410.104
- Updated other dependencies to latest

### Fixed
- Some commands were incorrectly failing due to nodeid conflicts with
supplied parameters ([#249](https://github.com/Azure/batch-shipyard/issues/249))
- Azure Function extension installation failure ([#260](https://github.com/Azure/batch-shipyard/issues/260))
- Block job submission on non-active pools ([#251](https://github.com/Azure/batch-shipyard/issues/251))
- Missing files included in binary distributions ([#258](https://github.com/Azure/batch-shipyard/issues/258))
- Pools with accelerated networking would fail provisioning sometimes due to
infiniband devices being present for non-RDMA VM sizes

### Security
- Updated Docker CE to 18.09.2 to address the runc CVE-2019-5736
- Updated Singularity to 2.6.1 to address the shared mount propagation
vulnerability CVE-2018-19295

## [3.6.1] - 2018-12-03
### Added
- `force_enable_task_dependencies` property in jobs configuration to turn
on task dependencies on a job even when no task dependencies are present
initially. This is useful when tasks are added at a later time that may
have dependencies. Please consult the jobs documentation for more information.
- Windows Server 2019 support
- Genomics and Bioinformatics recipes: BLAST and RNASeq
- PyTorch recipes

### Changed
- Updated Docker CE to 18.09.0
- Updated blobxfer to 1.5.5
- Updated NC/ND driver to 410.79
- Updated NV driver to 410.71 with CUDA10 support
- Updated other dependencies to latest

### Fixed
- `--tail` console output occasionally repeating characters
- NV provisioning regressions
- Windows node prep issue
- fs cluster status issue
- Retry MSI provisioning for discrete VM resources

## [3.6.0] - 2018-11-06 (SC18 Edition)
### Added
- Kata containers support: run containers on Linux compute nodes with a higher
level of isolation through lightweight VMs. Please see the pool doc for more
information.
- Per-job distributed scratch space support: create on-demand scratch
space shared between tasks of a job which can be particularly useful for MPI
and multi-instance tasks without having to manage a GlusterFS-on-compute
shared data volume. Please see both the pool doc and jobs doc for more
information.
- Add `restrict_default_bind_mounts` option to jobs specifications. This
will restrict automatic host directory bindings to the container filesystem
only to `$AZ_BATCH_TASK_DIR`. This is particularly useful in combination with
container runtimes enforcing VM-level isolation such as Kata containers.
- Allow installation and selection of multiple container runtimes along with
a default container runtime for Docker invocations. Please see the pool doc
for more information under `container_runtimes`.
- Support for Standard SSD and Ultra SSD managed disks for RemoteFS clusters.
In conjunction with this change, Availability Zone support has been added
for manage disks and storage cluster VMs. Please see the relevant
documentation for more information.

### Changed
- **Breaking Change:** the `premium` property under `remote_fs`:`managed_disks`
has been replaced with `sku`. Please see the RemoteFS configuration doc for
more information.
- **Breaking Change:** the Singularity container runtime is no longer installed
by default, please see the pool doc to configure pools to install Singularity
as needed under `container_runtimes`:`install`.
- Renamed MADL recipe to HPMLA
- Updated NC/ND driver to 410.72 with CUDA 10 support
- Updated blobxfer to 1.5.4
- Updated LIS, Prometheus, and Grafana
- Updated other dependencies to latest
- Updated binary builds and Windows Docker images to Python 3.7.1

### Fixed
- `input_data` utilizing Azure File shares ([#243](https://github.com/Azure/batch-shipyard/issues/243))
- New NV driver location ([#244](https://github.com/Azure/batch-shipyard/issues/244))
- Fixed non-public Azure region AAD login issues
- Fixed Singularity image download issues
- Fixed Grafana update regression with default Batch Shipayrd Dashboard
- Fixed SSH login to monitoring resource after federation feature merge
- Enable Singularity on Ubuntu 18.04

### Removed
- Debian 8 host support

## [3.6.0b1] - 2018-09-20
### Added
- Task and node count commands: `jobs tasks counts` and `pool nodes counts`
respectively ([#228](https://github.com/Azure/batch-shipyard/issues/228)).
Please see the usage doc for more information.
- Enhance blocked action tracking for federations. Please see the usage
doc for `fed jobs list` for more information.
- Support for Ubuntu 18.04
- Support for CentOS 7.5 in both non-native and native mode
- MacOS binary for the CLI

### Changed
- Updated Docker to 18.06.1
- Updated Singularity to 2.6.0
- Updated blobxfer to 1.5.0
- Updated Nvidia driver for NC/ND-series to 396.44
- Update various other dependencies to latest
- Windows binary is now signed

### Fixed
- Batch Shipyard site extension on nuget.org has been restored ([#224](https://github.com/Azure/batch-shipyard/issues/224))
- Pool auto-scaling beyond low priority limit ([#239](https://github.com/Azure/batch-shipyard/issues/239))
- Fix `jobs tasks term` command without pool SSH info
- Fix task id generator for federations

## [3.6.0a1] - 2018-08-06
### Added
- Federation support. Please see the
[federation guide](https://github.com/Azure/batch-shipyard/blob/master/docs/68-batch-shipyard-federation.md)
for more information.
- `monitor status` command with `--raw` support

### Changed
- Updated dependencies

## [3.5.3] - 2018-07-31
### Added
- Support Docker image preload delay for Linux native container pools.
Please see the global configuration docs for more information.

### Changed
- Improve registry login robustness with retries

### Fixed
- Docker Hub private registry login failures
- Environment variable issues ([#234](https://github.com/Azure/batch-shipyard/issues/234))

## [3.5.2] - 2018-07-20
### Fixed
- Non-native pool allocation on N-series VMs failing due to unpinned
dependent package for nvidia-docker2 ([#231](https://github.com/Azure/batch-shipyard/issues/231))

## [3.5.1] - 2018-07-17
### Changed
- Update GlusterFS on Compute on CentOS to 4.1
- Updated NC/ND Nvidia driver to 396.37
- Updated NV Nvidia driver to 390.75
- Updated LIS, Prometheus and Grafana
- Updated dependencies

### Fixed
- Properly terminate image pull without fallback on failure
- Fix pool metadata dump check logic
- Fix storage cluster provisioning with Node Exporter options

## [3.5.0] - 2018-06-29
### Added
- CentOS 7.5 and Microsoft Windows Server semi-annual
`datacenter-core-1803-with-containers-smalldisk` host support. Please see
the platform image support doc for more information.
- `fallback_registry` to improve robustness during provisioning when Docker
Hub has an outage or is degraded
([#215](https://github.com/Azure/batch-shipyard/issues/215), [#217](https://github.com/Azure/batch-shipyard/issues/217))
    - `misc mirror-images` command to help mirror Batch Shipyard system
      images to the designated fallback registry
- Support for XFS filesystem in storage clusters ([#218](https://github.com/Azure/batch-shipyard/issues/219))
- Experimental support for disk array RAID expansion for mdadm-based devices
via `fs cluster expand`
- Option to auto-upload Batch compute node service logs on unusable ([#216](https://github.com/Azure/batch-shipyard/issues/216))
- Microsoft Azure Distributed Linear Learner recipe ([#195](https://github.com/Azure/batch-shipyard/pull/195))

### Changed
- `pool nodes list` can now filter nodes with start task failed and/or
unusable states
- `diag logs upload` command can generate a read only SAS for the target
container via `--generate-sas`
- `storage clear` and `storage del` now allow multiple `--poolid` arguments
along with `--diagnostics-logs` to clear/delete diagnostics logs containers
- `storage sas create` now allows container and file share level SAS creation
along with `--list` permission now available as an option
- Pools failing to allocate with unusable or start task failed nodes will now
dump a listing of problematic nodes detailing the error
- Updated RemoteFS storage clusters using GlusterFS and Ubuntu/Debian-based
GlusterFS-on-compute to 4.1
- Updated blobxfer to 1.3.1
- Updated Singularity to 2.5.1
- Updated dependencies

### Fixed
- GlusterFS on compute provisioning ([#220](https://github.com/Azure/batch-shipyard/issues/220))
- Regression in KeyVault credential conf loading ([#214](https://github.com/Azure/batch-shipyard/issues/214))
- Task file mover command arg left unpopulated ([#29](https://github.com/Azure/batch-shipyard/issues/29))
- Recurring job manager failing to unpickle tasks with dependencies ([#221](https://github.com/Azure/batch-shipyard/issues/221))
- Task add regression when collections are too large from individual slices

### Removed
- CentOS 7.3 host support

## [3.5.0b3] - 2018-06-13
### Changed
- All supported platform images support blobfuse, including native mode

### Fixed
- blobfuse check preventing valid pool provisioning ([#213](https://github.com/Azure/batch-shipyard/issues/213))
- Pool resize not adding SSH users if keys are specified

## [3.5.0b2] - 2018-06-12
### Added
- Support for Prometheus monitoring and Grafana visualization
([#205](https://github.com/Azure/batch-shipyard/issues/205)). Please see the
monitoring doc and
[guide](https://github.com/Azure/batch-shipyard/blob/master/docs/66-batch-shipyard-resource-monitoring.md)
for more information.
- Support for specifying a maximum increment per autoscale evaluation and
the ability to define weekdays and workhours ([#210](https://github.com/Azure/batch-shipyard/issues/210))
- Support for native container support Marketplace platform images. Please
see the platform image support doc for more information. ([#204](https://github.com/Azure/batch-shipyard/issues/204))
- Allow configuration to enable SSH users to access Docker daemon ([#206](https://github.com/Azure/batch-shipyard/issues/206))
- Support for GPUs on CentOS 7.4 ([#199](https://github.com/Azure/batch-shipyard/issues/199))
- Support for CentOS-HPC 7.4 ([#184](https://github.com/Azure/batch-shipyard/issues/184))

### Changed
- **Breaking Change:** You can no longer specify both an `account_key`
and `aad` with the `batch` section of the credentials config. The prior
behavior was that `account_key` would take precedence over `aad`. Now
these options are mutually exclusive. This will now break configurations
that specified `aad` at the global level while having a shared `account_key`
at the `batch` level. ([#197](https://github.com/Azure/batch-shipyard/issues/197))
- **Breaking Change:** `install.sh` now installs into a virtual env by
default. Use the `-u` switch to retain the old (non-recommended)
default behavior. ([#200](https://github.com/Azure/batch-shipyard/issues/200))
- GlusterFS for RemoteFS and gluster on compute updated to 4.0.
- Update NC driver to 396.26 supporting CUDA 9.2
- blobxfer updated to 1.2.1

### Fixed
- Errant credentials check for configuration from commandline which affected
config load from KeyVault
- Blobxfer extra options regression
- Cache container/file share creations for data egress ([#211](https://github.com/Azure/batch-shipyard/issues/211))

## [3.5.0b1] - 2018-05-02
### Added
- Output to JSON for a subset of commands via `--raw` commmand line switch.
JSON output is directed to stdout. Please see the usage doc for which commands
are supported and important information regarding output stability. ([#177](https://github.com/Azure/batch-shipyard/issues/177))
- Allow AAD on the `storage` section in the credentials configuration.
Please see the credential doc for more information. ([#179](https://github.com/Azure/batch-shipyard/issues/179))
- Boot diagnostics are now enabled for all VMs provisioned for RemoteFS
clusters. This also enables serial console support in the portal. ([#193](https://github.com/Azure/batch-shipyard/issues/193))
- `product_iterables` task factory support. Please see the task factory
doc for more information. ([#187](https://github.com/Azure/batch-shipyard/issues/187))
- `default_working_dir` option as the job and task-level to set the
default working directory when a container executes as a task. Please
see the jobs doc for more information. ([#190](https://github.com/Azure/batch-shipyard/issues/190))
- `--no-generate-tunnel-script` option to `pool nodes grls`

### Changed
- Greatly improve throughput speed of many commands that internally iterated
sequences of actions ([#188](https://github.com/Azure/batch-shipyard/issues/188))
- RemoteFS clusters provisioned using Ubuntu 18.04-LTS
([#161](https://github.com/Azure/batch-shipyard/issues/161), [#185](https://github.com/Azure/batch-shipyard/issues/185))
- Update Nvidia NC driver to 390.46 supporting CUDA 9.1
- Update Nvidia NV driver to 390.42.
- Singularity updated to 2.5.0
- blobxfer updated to 1.2.0
- Docker CE updated to 18.03.1
- Update dependencies to latest
- Unify nodeprep scripts ([#176](https://github.com/Azure/batch-shipyard/issues/176))
- Integrate shellcheck ([#177](https://github.com/Azure/batch-shipyard/issues/177))
- Extend retry policy for all clients
- Add Windows file version info and icon to CLI binary

### Fixed
- Kernel unattended upgrades causes GPU jobs to fail on reboot ([#174](https://github.com/Azure/batch-shipyard/issues/174))
- Task submission speed regression when using task factory or large task
arrays with unnamed tasks ([#183](https://github.com/Azure/batch-shipyard/issues/183))
- Fix determinism in cardinality of results from `pool nodes grls`
- Env var export for tasks without env vars
- Ensure Nvidia persistence mode on reboots
- Pin nvidia-docker2 installations
- Site extension broken install issues (and fallback manual recovery)

### Removed
- Ubuntu 14.04 host support ([#164](https://github.com/Azure/batch-shipyard/issues/164))

## [3.4.0] - 2018-03-26
### Added
- Support for adding network access rules to the remote access port (SSH or
RDP). Please see the pool configuration guide for more details.
- Support for adding certificate references to a pool. Please see the
pool configuration guide for more details. Also please see below for
improvements to the `cert` command.
- Support for
[NCv3 VM sizes](https://azure.microsoft.com/blog/ncv3-vms-generally-available-other-gpus-expanding-regions/).
Note that ND/NCv2/NCv3 all require separate quota approval; please raise a
ticket through the Azure Portal.
- Support for uploading Batch compute node service logs to the specified
Azure storage account used by Batch Shipyard. Please see the
`diag logs upload` command in the usage docs.
- Support for fine-tuning `/etc/exports` when creating NFS file servers via
`server_options` and `nfs`. Please see the remote FS configuration doc
for more information.
- Support for job-level default task exit condition options. These options
can be overriden on a per-task basis. Please see the job configuration doc
for more information.

### Changed
- Improve `cert` commands
    - Support adding arbitrary cer, pem and pfx certificates to a Batch
      account via command line options
    - Support deleting arbitrary certificates by thumbprint, including
      multiple at once; also ask for confirmation before deleting
    - Support creating pem/pfx pairs with `cert create` without having
      to define an `encryption` section in the global configuration for
      use in scenarios outside of credential encryption
- `depends_on` and `depends_on_range` now apply to tasks generated by
`task_factory` (#173). Please see the job configuration doc for more
information.
- `pool nodes del` and `pool nodes reboot` now accept multiple `--nodeid`
arguments to specify deleting and rebooting multiple nodes at the same time,
respectively
- `pool nodes prune`, `pool nodes reboot`, `pool nodes zap` will now ask
for confirmation first. `-y` flag can be specified to suppress confirmation.
- Added Batch Shipyard version to user agent for all ARM clients
- Improved node prep scripts with more timestamp detail, Docker and
Nvidia details
- CUDA 9.1 support on ND/NCv2/NCv3 with Tesla Driver 390.30
- Docker CE updated to 18.03.0
- Singularity updated to 2.4.4
- Dependencies updated

### Fixed
- Previous environment variable expansion fix applied to multi-instance tasks
- `jobs tasks list` command with undefined job action but with dependency
actions
- `job_action` for task default exit condition was being overwritten
incorrectly in certain scenarios

## [3.3.0] - 2018-03-01
### Added
- Support for specifying default task exit conditions (i.e., non-zero exit
codes). Please see the jobs configuration doc for more information.
- New commands (please see usage doc for more information):
    - `pool nodes prune` will remove all unused Docker-related data on all
      nodes in the pool (requires an SSH user)
    - `pool nodes ps` performs a `docker ps -a` on all nodes in the pool
      (requires an SSH user)
    - `pool nodes zap` will kill (and optionally remove) **all** running
      Docker containers on nodes in a pool (requires an SSH user). Note that
      `jobs tasks term` is the preferred command to control individual
      (or grouped) task termination or `jobs term --termtasks` to terminate
      at the job level.
    - `storage sas create` command added as a utility helper function to
      create SAS tokens for given storage accounts in credentials
- Support for activating
[Azure Hybrid Use Benefit](https://azure.microsoft.com/pricing/hybrid-benefit/)
for Windows pools

### Changed
- Greatly expand pool, node, job, and task details for `list` sub-commands
- Expand error detail key/value pairs if present
- Name resources for RemoteFS with 3 digits (e.g., 000 instead of 0) for
improved alpha ordering
- Move site extension to nuget.org (#172)

### Fixed
- Command lines in non-native mode now properly expand environment variables
with normal quoting
- RemoteFS cluster del with disks error
- RemoteFS cluster status decoding issues
- Unintended interaction between native mode and custom images
- Handle starting Docker service for all deployments
- Do not automatically mount storage cluster or custom linux mounts on boot
due to potential race conditions with the ephemeral disk mount
- Fix TLS issue with powershell (#171)
- Fix conflicts when using install.sh with Anaconda environments
- Update packer scripts and fix typos
- Minor doc updates

## [3.2.0] - 2018-02-21
### Added
- Custom Linux Mount support for `shared_data_volumes`. Please see the
global configuration doc for more information.
- New commands (please see usage doc for more information):
    - `account` command added with the following sub-commands (requires
      AAD auth):
        - `info` provides information about a Batch account (including account
          level quotas)
        - `list` provides information about all (or a resource group subset)
          of accounts within the subscription specified in credentials
        - `quota` provides service level quota information for the
          subscription for a given location
    - `pool rdp` sub-command added, please see usage doc for more information.
      Requires Batch Shipyard executing on Windows with target Windows
      containers pools.
- `pool images update` command now supports updating Docker images
in native container support pools via SSH
- Ability to specify an AAD authority URL via the `aad`:`authority_url`
credential configuration, `--aad-authority-url` command line option or
`SHIPYARD_AAD_AUTHORITY_URL` environment variable. Please see relevant
documentation for credentials and usage.
- Support for CentOS 7.4 and Debian 9 compute node hosts. CentOS 7.4
on GPU nodes is currently unsupported; CentOS 7.3 will continue to work on
N-series.
- Support for publisher `MicrosoftWindowsServer`, offer
`WindowsServerSemiAnnual`, and sku
`Datacenter-Core-1709-with-Containers-smalldisk`
- `--delete-resource-group` option added to `fs disks del` command
- CentOS-HPC 7.1, CentOS 7.3 GPU, and CentOS 7.4 packer scripts added to
contrib area
- Add documentation for which `platform_image`s are supported

### Changed
- **Breaking Change:** `additional_node_prep_commands` is now a dictionary
of `pre` and `post` properties which are executed either before or after the
Batch Shipyard startup task. Please see the pool configuration doc for more
information.
- Allow provisioning of OpenLogic CentOS-HPC 7.1
- Default management endpoint for public Azure cloud updated
- Improve some error messages/handling
- Update dependencies to latest
- Linux pre-built binary is no longer gzipped
- Update packer scripts in contrib area

### Fixed
- AAD auth for ARM endpoints in non-public Azure cloud regions
- Custom image + native mode deployment for Linux pools
- Potential command launch problems in native mode
- Minor schema validation updates
- AAD check logic for different points in pool allocation
- `--ssh` parameter for `pool images update` was not correctly set as a flag
- `--jobs` was not properly being merged with `--configdir` (#163)
- Fix regression in `pool images update` that would not login to
registries in multi-instance mode
- Fix `pool images` commands to more reliably work with SSH
- Fix `output_data` with windows containers pools (#165)

## [3.1.0] - 2018-01-30
### Added
- Configuration validation. Validator supports both YAML and JSON
configuration, please see special note in the Removed section below (#145)
- Support for Azure Blob storage container mounting via blobfuse (#159)
- Support for merge tasks which depend on all tasks specified in the
`tasks` array. Please see the jobs configuration guide for more
information (#149).
- Support for accelerated networking in RemoteFS storage clusters (#158)

### Changed
- Update Docker CE to 17.12.0 for Ubuntu/CentOS
- Update nvidia-docker 1.0.1 to nvidia-docker2
- Update blobxfer to 1.1.1
- Updated dependencies to latest

### Fixed
- Disabling `remove_container_after_exit`, `gpu`, `infiniband` at the
task-level was not being honored properly

### Removed
- Integration of the schema validator has now removed or enforced strict
behavior for the following previously deprecated configuration properties:
    - `credentials`:`batch`:`account` has been removed
    - `pool_specification`:`vm_count` must be a map of `dedicated` and
      `low_priority` VM counts
    - `pool_specification`:`vm_configuration` must be specified instead of
      directly specifying `publisher`, `offer`, `sku` on `pool_specification`
    - `global_resources`:`docker_volumes` is no longer valid and must be
      replaced with `global_resources`:`volumes`
    - `job_specifications`:`tasks`:`image` is no longer valid and must be
      replaced with `job_specifications`:`tasks`:`docker_image`

## [3.0.3] - 2018-01-22
### Security
- Update NV driver to 384.111 to work with updated Linux kernels with
speculative execution side channel vulnerability patches (#154)

## [3.0.2] - 2018-01-12
### Fixed
- Errant bind option being propagated to volume name
- Clarify error path on attempting `infiniband` on non-supported images
- Fix quickstart recipe links from Read the Docs (#150)

### Security
- Update NC driver to 384.111 to work with updated Linux kernels with
speculative execution side channel vulnerability patches

## [3.0.1] - 2017-11-22
### Fixed
- Fix on-disk file naming for Docker images pulled with Singularity
- Data movement regressions
- Public IP configs in RemoteFS recipes
- Support more than 16 data disks per VM for RemoteFS servers
- Documentation and other typos

## [3.0.0] - 2017-11-13 (SC17 Edition)
### Added
- CLI Singularity image (#135)

### Changed
- Start LUN numbering for remote fs disks at 0
- Allow path to `python.exe` to be specified in `install.cmd`
- Ensure persistence daemon/mode is enabled for GPUs
- Update dependencies to latest

### Fixed
- Non-Ubuntu/CentOS cascade failures from non-existent Singularity
- Default Singularity tagged image names on disk
- Circular dependency in `task_factory` and `settings`
- `misc tensorboard` command broken from latest TF image
- Update NV driver

## [3.0.0rc1] - 2017-11-08
### Changed
- Update VM size support
- SSH private key filemode check no longer results in an exception if it
fails. Instead a warning is issued - this is to allow SSH invocations on WSL.
- Install scripts now uninstall `azure-storage` first due to conflicts with
the Azure Storage Python split library.
- Updated to blobxfer 1.0.0

### Fixed
- Job submission on custom image pools with 4.0 SDK changes
- Empty coordination command issue for Docker tasks
- Singularity registries with passwords in keyvault

## [3.0.0b1] - 2017-11-05
### Added
- Singularity support (#135)
- Preliminary Windows server support (#7)
- Pre-built binaries for CLI for some Linux distributions and Windows (#131)
- Windows Docker image for CLI
- Singularity HPCG and TensorFlow-GPU recipes

### Changed
- **Breaking Change:** Many commands have been placed under more
appropriate hierachies. Please see the major version migration guide for
more information.

### Fixed
- Mount `/opt/intel` into Singularity containers
- Retry image configuration error pulls from Docker registries
- AAD MFA token cache on Python2
- Non-native coordination command fix, if not specified
- Include min node counts in autoscale scenarios (#139)
- `jobs tasks list` when there is a failed task (#142)

## [3.0.0a2] - 2017-10-27
### Added
- Major version migration guide (#134)
- Support for mounting multiple Azure File shares as `shared_data_volumes`
to a pool (#123)
- `bind_options` support for `data_volumes` and `shared_data_volumes`
- More packer samples for custom images
- Singularity HPLinpack recipe

### Changed
- **Breaking Change:** `global_resources`:`docker_volumes` is now named
`global_resources`:`volumes`. Although backward compatibility is maintained
for this property, it is recommended to migrate as volumes are now shared
between Docker and Singularity containers.
- Azure Files (with `volume_driver` of `azurefile`) specified under
`shared_data_volumes` are now mounted directly to the host (#123)
- The internal root mount point for all `shared_data_volumes` is now under
`$AZ_BATCH_NODE_ROOT_DIR/mounts` to reduce clutter/confusion under the
old root mount point of `$AZ_BATCH_NODE_SHARED_DIR`. The container mount
points (i.e., `container_path`) are unaffected.
- Canonical UbuntuServer 16.04-LTS is no longer pinned to a specific
release. Please avoid using the version `16.04.201709190`.
- Update to blobxfer 1.0.0rc3
- Updated custom image guide

### Fixed
- Multi-instance Docker-based application command was not being launched
under a user identity if specified
- Allow min node allocation with `bias_last_sample` without required
sample percentage (#138)

## [3.0.0a1] - 2017-10-04
### Added
- Support for deploying compute nodes to an ARM Virtual Network with Batch
Service Batch accounts (#126)
- Support for deploying custom image compute nodes from an ARM Image resource
(#126)
- Support for multiple public and private container registries (#127)
- YAML configuration support. JSON formatted configuration files will continue
to be supported, however, note the breaking change with the corresponding
environment variable names for specifying individual config files from the
commandline. (#122)
- Option to automatically attempt recovery of unusable nodes during
pool allocation or resize. See the `attempt_recovery_on_unusable` option in
the pool configuration doc.
- Virtual Network guide

### Changed
- **Breaking Change:** Docker image tag for the CLI has been renamed to
`alfpark/batch-shipyard:<version>-cli` where `<version>` is the release
version or `latest` for whatever is in `master`. (#130)
- **Breaking Change:** Fully qualified Docker image names are now required
under both the global config `global_resources`.`docker_images` and jobs
`task` array `docker_image` (or `image`). The `docker_registry` property
in the global config file is no longer valid. (#106)
- **Breaking Change:** Docker private registries backed to Azure Storage blobs
are no longer supported. This is not to be confused with the Classic Azure
Container Registries which are still supported. (#44)
- **Breaking Change:** `docker_registry` property in the global config is
no longer required. An `additional_registries` option is available for any
additional registries that are not present from the `docker_images`
array in `global_resources` but require a valid login. (#106)
- **Breaking Change:** Data ingress/egress from/to Azure Storage along with
`task_factory`:`file` has changed to accommodate `blobxfer 1.0.0` commandline
and options. There are new expanded options available, including multiple
`include` and `exclude` along with `remote_path` explicit specifications
(instead of general `container` or `file_share`). Please see the appropriate
global config, pool or job configuration docs for more information. (#47)
- **Breaking Change:** `image_uris` in the `vm_configuration`:`custom_image`
property of the pool configuration has been replaced with `arm_image_id`
which is a reference to an ARM Image resource. Please see the custom image
guide for more information. (#126)
- **Breaking Change:** environment variables `SHIPYARD_CREDENTIALS_JSON`,
`SHIPYARD_CONFIG_JSON`, `SHIPYARD_POOL_JSON`, `SHIPYARD_JOBS_JSON`, and
`SHIPYARD_FS_JSON` have been renamed to `SHIPYARD_CREDENTIALS_CONF`,
`SHIPYARD_CONFIG_CONF`, `SHIPYARD_POOL_CONF`, `SHIPYARD_JOBS_CONF`, and
`SHIPYARD_FS_CONF` respectively. (#122)
- `--configdir` or `SHIPYARD_CONFIGDIR` now defaults to the current working
directory (i.e., `.`) if no other conf file options are specified.
- `aad` can be specified at a "global" level in the credentials configuration
file, which is then applied to `batch`, `keyvault` and/or `management`
section. Please see the credentials configuration guide for more information.
- `docker_image` is now preferred over the deprecated `image` property in
the `task` array in the jobs configuration file
- `gpu` and `infiniband` under the jobs configuration are now optional. GPU
and/or RDMA capable compute nodes will be autodetected and the proper
devices and other settings will be automatically be applied to tasks running
on these compute nodes. You can force disable GPU and/or RDMA by setting
`gpu` and `infiniband` properties to `false`. (#124)
- Update Docker CE to 17.09.0
- Update NC driver to 384.81 (CUDA 9.0 support)

## [2.9.6] - 2017-10-03
### Added
- Migrate to Read the Docs for [documentation](https://batch-shipyard.readthedocs.io/en/latest/)

### Fixed
- RemoteFS disk attach fixes
- Nvidia docker volume mount check

## [2.9.5] - 2017-09-24
### Added
- Optional `version` support for `platform_image`. This property can be
used to set a host OS version to prevent possible issues that occur with
`latest` image versions.
- `--all-starting` option for `pool delnode` which will delete all nodes
in starting state

### Changed
- Prevent invalid configuration of HPC offers with non-RDMA VM sizes
- Expanded network tuning exemptions for new Dv3 and Ev3 sizes
- Temporarily override Canonical UbuntuServer 16.04-LTS latest version to
a prior version due to recent linux-azure kernel issues

### Fixed
- NV driver updates
- Various OS updates and Docker issues
- CentOS 7.3 to 7.4 Nvidia driver breakage
- Regression in `pool ssh` on Windows
- Exception in unusable nodes with pool stats on allocation
- Handle package manager db locks during conflicts for local package installs

## [2.9.4] - 2017-09-12
### Changed
- Update dependencies to latest available
- Improve Docker builds

### Fixed
- Missing `join_by` function in blobxfer helper script (#115)
- Fix `clear()` for `pool udi` with Python 2.7 (#118)

## [2.9.3] - 2017-08-29
### Fixed
- Ignore `resize_timeout` for autoscale-enabled pools
- Present a warning for `jobs migrate` indicating Docker image requirements
- Various doc typos and updates

## [2.9.2] - 2017-08-16
### Added
- Deep learning Jupyter notebooks (thanks to @msalvaris and @thdeltei)
- Automatic site-extensions NuGet package updates with tagged releases via
AppVeyor builds
- Caffe2-CPU and Caffe2-GPU Recipes

### Changed
- Python 3.3 is no longer supported (due to `cryptography` dropping support
for 3.3).
- Use multi-stage build for Cascade to improve build times and reduce
Docker image size

### Fixed
- Provide more helpful feedback for invalid clients
- Fix provisioning clusters with disks larger than 2TB
- RemoteFS issues in resize and expand
- Various site extension issues, will now proper install/upgrade to the
associated tagged version

## [2.9.0rc1] - 2017-08-09
### Added
- Recurring job support (job schedules). Please see jobs configuration doc
for more information.
- `custom` task factory. See the task factory guide for more information.
- `--all-jobschedules` option for `jobs term` and `jobs del`
- `--jobscheduleid` option for `jobs disable`, `jobs enable` and
`jobs migrate`
- `--all` option for `jobs listtasks`

### Changed
- `autogenerated_task_id_prefix` configuration setting is now named
`autogenerated_task_id` and is a complex property. It has member properties
named `prefix` and `zfill_width` to control how autogenerated task ids are
named.
- `jobs list` will now output job schedules in addition to jobs
- `--all` parameter for `jobs term` and `jobs del` renamed to `--all-jobs`
- list subcommands now output in a more human readable format

## [2.9.0b2] - 2017-08-04
### Added
- `random` and `file` task factories. See the task factory guide for more
information.
- Summary statistics: `pool stats` and `jobs stats`. See the usage doc for
more information.
- Delete unusable nodes from pool with `--all-unusable` option for
`pool delnode`
- CentOS-HPC 7.3 support
- CNTK-GPU-Infiniband-IntelMPI recipe

### Changed
- `remove_container_after_exit` now defaults to `true`
- `input_data`:`azure_storage` files with an include filter that does not
include wildcards (i.e., targets a single file) will now be placed at
the `destination` directly as specified.
- Nvidia Tesla driver updated to 384.59
- TensorFlow recipes updated for 1.2.1. TensorFlow-Distributed `launcher.sh`
script is now generalized to take a script as the first parameter and
relocated to `/shipyard/launcher.sh`.
- CNTK recipes updated for 2.1. `run_cntk.sh` script now takes in CNTK
Python scripts for execution.

### Fixed
- Task termination with force failing due to new task generators
- pool udi over SSH terminal mangling

## [2.9.0b1] - 2017-07-31
### Added
- Autoscale support. Please see the Autoscale guide for more information.
- Autopool support
- Task factory and parametric sweep support. Please see the task factory
guide for more information.
- Job priority support
- Job migration support with new command `jobs migrate`
- Compute node fill type support
- New commands: `jobs enable` and `jobs disable`. Please see the usage doc
for more information.
- From Scratch: Step-by-Step guide
- Azure Cloud Shell information

### Changed
- Auto-generated task prefix is now `task-`. This can now be overridden with
the `autogenerated_task_id_prefix` property in the global configuration.
- Update dependencies to latest except for azure-mgmt-compute due to
broken changes

### Fixed
- RemoteFS regressions
- Pool deletion with poolid argument cleanup

## [2.8.0] - 2017-07-06
### Added
- Support for CentOS 7.3 NC/NV gpu pools
- `--all-start-task-failed` parameter for `pool delnode`

### Changed
- Improve robustness of docker image pulls within node prep scripts
- Restrict node list queries until pool allocation state emerges from resizing

### Fixed
- Remove nvidia gpu driver property from FFmpeg recipe
- Further improve retry logic for docker image pulls in cascade

## [2.8.0rc2] - 2017-06-30
### Added
- Support Mac OS X and Windows Subsystem for Linux installations via
`install.sh` (#101)
- Guide for Windows Subsystem for Linux installations
- Automated Nvidia driver install for NV-series

### Changed
- Drop unsupported designations for Mac OS X and Windows
- Update Docker engine to 17.06 for Ubuntu, Debian, CentOS and 17.04 for
OpenSUSE

### Fixed
- Regression in private registry image pulls

## [2.8.0rc1] - 2017-06-27
### Added
- Version metadata added to pools and jobs with warnings generated for
mismatches (#89)
- Cloud shell installation support

### Changed
- Update Docker images to Alpine 3.6 (#65)
- Improve robustness of package downloads
- Add retries for docker pull within cascade context
- Download cascade.log on start up failures

### Fixed
- Patch job for auto completion (#97)
- Tensorboard command with custom images
- conda-forge detection in installation scripts (#100)

## [2.8.0b1] - 2017-06-07
### Added
- Custom image support, please see the pool configuration doc and custom
image guide for more information. (#94)
- `contrib` area with `packer` scripts

### Changed
- **Breaking Change:** `publisher`, `offer`, `sku` is now part of a complex
property named `vm_configuration`:`platform_image`. This change is to
accommodate custom images. The old configuration schema is now deprecated and
will be removed in a future release.
- Updated NVIDIA Tesla driver to 375.66

### Fixed
- Improved pool resize/allocation logic to fail early with low priority core
quota reached with no dedicated nodes

## [2.7.0] - 2017-05-31
### Added
- `--poolid` parameter for `pool del` to specify a specific pool to delete

### Changed
- Prompt for confirmation for `jobs cmi`
- Updated to latest dependencies
- Split low-priority considerations into separate doc

### Fixed
- Remote FS allocation issue with `vm_count` deprecation check
- Better handling of package index refresh errors
- `pool udi` over SSH issues (#92)
- Duplicate volume checks between job and task definitions

## [2.7.0rc1] - 2017-05-24
### Added
- `pool listimages` command which will list all common Docker images on
all nodes and provide warning for mismatched images amongst compute nodes.
This functionality requires a provisioned SSH user and private key.
- `max_wall_time` option for both jobs and tasks. Please consult the
documentation for the difference when specifying this option at either the
job or task level.
- `--poll-until-tasks-complete` option for `jobs listtasks` to block the CLI
from exiting until all tasks under jobs for which the command is run have
completed
- `--tty` option for `pool ssh` and `fs cluster ssh` to enable allocation
of a pseudo-tty for the SSH session

### Changed
- `remove_container_after_exit`, `retention_time`, `shm_size`, `infiniband`,
`gpu` can now be specified at the job-level and overriden at the task-level
in the jobs configuration
- `data_volumes` and `shared_data_volumes` can now be specified at the
job-level and any volumes specified at the task level will be *merged* with
the job-level volumes to be exposed for the container

### Fixed
- Add missing deprecation path for `pool_specification_vm_count` for
multi-instance tasks. Please upgrade your jobs configuration to explicitly
use either `pool_specification_vm_count_dedicated` or
`pool_specification_vm_count_low_priority`.
- Speed up task collection additions by caching last task id
- Issues with pool resize and wait logic with low priority

## [2.7.0b2] - 2017-05-18
### Changed
- Allow the prior `vm_count` behavior, but provide a deprecation warning. The
old `vm_count` behavior will be removed in a future release. (#84)
- Add tasks via collection (#86)
- Log if node is dedicated in `pool listnodes`
- Updated all recipes with new `vm_count` changes

### Fixed
- Improve pool resize wait logic for pools with mixed node types
- Do not override workdir if specified (#87)
- Prevent container scanning for data ingress from Azure Storage if include
filter contains no wildcards (#88)

## [2.7.0b1] - 2017-05-12
### Added
- Support for [Low Priority Batch Compute Nodes](https://docs.microsoft.com/azure/batch/batch-low-pri-vms)
- `resize_timeout` can now be specified on the pool specification
- `--clear-tables` option to `storage del` command which will delete
blob containers and queues but clear table entries
- `--ssh` option to `pool udi` command which will force the update Docker
images command to update over SSH instead of through a Batch job. This is
useful if you want to perform an out-of-band update of Docker image(s), e.g.,
your pool is currently busy processing tasks and would not be able to
accommodate another task.

### Changed
- **Breaking Change:** `vm_count` in the pool specification is now a
complex property consisting of the properties `dedicated` and `low_priority`
- Updated all dependencies to latest

### Fixed
- Improve node startup time for GPU NC-series by removing extraneous
dependencies
- `fs cluster ssh` storage cluster id and command argument ordering was
inverted. This has been corrected to be as intended where the command
is the last argument, e.g., `fs cluster ssh mynfs -- df -h`

## [2.6.2] - 2017-05-05
### Added
- Docker image build for `develop` branch

### Changed
- Allow NVIDIA license agreement to be auto-confirmed via `-y` option
- Use requests for file downloading since it is already being installed
as a dependency
- Update dependencies to latest versions

### Fixed
- TensorFlow image not being set if no suitable image is found for
`misc tensorboard` command
- Authentication for running images not present in global config sourced
from a private registry

## [2.6.1] - 2017-05-01
### Added
- `misc tensorboard` command added which automatically instantiates a
Tensorboard instance on the compute node which is running or has ran a
task that has generated TensorFlow summary operation compatible logs. An
SSH tunnel is then created so you can view Tensorboard locally on the
machine running Batch Shipyard. This requires a valid SSH user that has been
provisioned via Batch Shipyard with private keys available. This command
will work on Windows if `ssh.exe` is available in `%PATH%` or the current
working directory. Please see the usage guide for more information about
this command.
- Pool-level `resource_files` support

### Changed
- Added optional `COMMAND` argument to `pool ssh` and `fs cluster ssh`
commands. If `COMMAND` is specified, the command is run non-interactively
with SSH on the target node.
- Added some additional sanity checks in the node prep script
- Updated TensorFlow-CPU and TensorFlow-GPU recipes to 1.1.0. Removed
specialized Docker build for TensorFlow-GPU. Added `jobs-tb.json` files
to TensorFlow-CPU and TensorFlow-GPU recipes as Tensorboard samples.
- Optimize some Batch calls

### Fixed
- Site extension issues
- SSH user add exception on Windows
- `jobs del --termtasks` will now disable the job prior to running task
termination to prevent active tasks in job from running while tasks are
being terminated
- `jobs listtasks` and `data listfiles` will now accept a `--jobid` that
does not have to be in `jobs.json`
- Data ingress on pool create issue with single node

## [2.6.0] - 2017-04-20
### Changed
- Update to latest dependencies

### Fixed
- Checks that prevented ssh/scp/openssl interaction on Windows
- SSH private key regression in data ingress direct to compute node

## [2.6.0rc1] - 2017-04-14
### Added
- Richer SSH options with new `ssh_public_key_data` and `ssh_private_key`
properties in `ssh` configuration blocks (for both `pool.json` and
`fs.json`).
  - `ssh_public_key_data` allows direct embedding of SSH public keys in
    OpenSSH format into the config files.
  - `ssh_private_key` specifies where the private key is located with
    respect to pre-created public keys (either `ssh_public_key` or
    `ssh_public_key_data`). This allows transparent `pool ssh` or
    `fs cluster ssh` commands with pre-created keys.
- RemoteFS-GlusterFS+BatchPool recipe

### Changed
- Docker installations are now pinned to a specific Docker version which
should reduce sudden breaking changes introduced upstream by Docker and/or
the distribution
- Fault domains for multi-vm storage clusters are now set to 2 by default but
can be configured using the `fault_domains` property. This was lowered from
the prior default of 3 due to managed disks and availability set restrictions
as some regions do not support 3 fault domains with this combination.
- Updated NC-series Tesla driver to 375.51

### Fixed
- Broken Docker installations due to gpgkey changes
- Possible race condition between disk setup and glusterfs volume create
- Forbid SSH username to be the same as the samba username
- Allow smbd.service to auto-restart with delay
- Data ingress to glusterfs on compute with no remotefs settings

### Removed
- Host support for OpenSUSE 13.2 and SLES 12

## [2.6.0b3] - 2017-04-03
### Added
- Created [Azure App Service Site Extension](https://www.siteextensions.net/packages/batch-shipyard).
You can now one-click install Batch Shipyard as a site extension (after you
have Python installed) and use Batch Shipyard from an Azure Function trigger.
- Samba support on storage cluster servers
- Add sample RemoteFS recipes for NFS and GlusterFS
- `install.cmd` installer for Windows. `install_conda_windows.cmd` has been
replaced by `install.cmd`, please see the install doc for more information.

### Changed
- **Breaking Change:** `multi_instance_auto_complete` under
`job_specifications` is now named `auto_complete`. This property will apply
to all types of jobs and not just multi-instance tasks. The default is now
`false` (instead of `true` for the old `multi_instance_auto_complete`).
- **Breaking Change:** `static_public_ip` has been replaced with a `public_ip`
complex property. This is to accommodate for situations where public IP for
RemoteFS is disabled. Please see the Remote FS configuration doc for more
info.
- `install.sh` now handles Anaconda Python environments
- `--cardinal 0` is now implicit if no `--hostname` or `--nodeid` is specified
for `fs cluster ssh` or `pool ssh` commands, respectively
- Allow `docker_images` in `global_resources` to be empty. Note that it is
always recommended to pre-load images on to pools for consistent scheduling
latencies from pool idle.

### Fixed
- Removed requirement of a `batch` credential section for pure `fs` operations
- Multi-instance auto complete setting not being properly read
- `install.sh` virtual environment issues
- Fix pool ingress data calls with remotefs (#62)
- Move additional node prep commands to last set of commands to execute in
start task (#63)
- `glusterfs_on_compute` shared data volume issues
- future and pathlib compat issues
- Python2 unicode/str issues with management libraries

## [2.6.0b2] - 2017-03-22
### Added
- Added virtual environment install option for `install.sh` which is now
the recommended way to install Batch Shipyard. Please see the install
guide for more information. (#55)

### Changed
- Force SSD optimizations for btrfs with premium storage

### Fixed
- Incorrect FS server options parsing at script time
- KeyVault client not initialized in `fs` contexts (#57)
- Check pool current node count prior to executing `pool udi` task (#58)
- Initialization with KeyVault uri on commandline (#59)

## [2.6.0b1] - 2017-03-16
### Added
- Support for provisioning storage clusters via the `fs cluster` command
  - Support for NFS (single VM, scale up)
  - Support for GlusterFS (multi VM, scale up and out)
- Support for provisioning managed disks via the `fs disks` command
- Support for data ingress to provisioned storage clusters
- Support for
[UserSubscription Batch accounts](https://docs.microsoft.com/azure/batch/batch-account-create-portal#user-subscription-mode)
- Azure Active Directory authentication support for Batch accounts
- Support for specifying a virtual network to use with a compute pool
- `allow_run_on_missing_image` option to jobs that allows tasks to execute
under jobs with Docker images that have not been pre-loaded via the
`global_resources`:`docker_images` setting in config.json. Note that, if
possible, you should attempt to specify all Docker images that you intend
to run in the `global_resources`:`docker_images` property in the global
configuration to minimize scheduling to task execution latency.
- Support for running containers as a different user identity (uid/gid)
- Support for Canonical/UbuntuServer/16.04-LTS. 16.04-LTS should be used over
the old 16.04.0-LTS sku due to
[issue #31](https://github.com/Azure/batch-shipyard/issues/31) and is no
longer receiving updates.

### Changed
- **Breaking Change:** `glusterfs` `volume_driver` for `shared_data_volumes`
should now be named as `glusterfs_on_compute`. This is to distinguish between
co-located GlusterFS on compute nodes with standalone GlusterFS
`storage_cluster` remote mounted distributed file system.
- Logging now has less verbose details (call origin) by default. Prior
behavior can be restored with the `-v` option.
- Pool existance is now checked prior to job submission and can now proceed
to add without an active pool.
- Batch `account` (name) is now an optional property in the credentials config
- Configuration doc broken up into multiple pages
- Update all recipes using Canonical/UbuntuServer/16.04.0-LTS to use
Canonical/UbuntuServer/16.04-LTS instead
- Configuration is no longer shown with `-v`. Use `--show-config` to dump
the complete configuration being used for the command.
- Precompile Python files during build for Docker images
- All dependencies updated to latest versions
- Update Batch API call compatibility for `azure-batch 2.0.0`

### Fixed
- Logging time format and incorrect Zulu time designation.
- `scp` and `multinode_scp` data movement capability is now supported in
Windows given `ssh.exe` and `scp.exe` can be found in `%PATH%` or the current
working directory. `rsync` methods are not supported on Windows.
- Credential encryption is now supported in Windows given `openssl.exe` can
be found in `%PATH%` or the current working directory.

## [2.5.4] - 2017-03-08
### Changed
- Downloaded files are now verified via SHA256 instead of MD5
- Updated NC-series Tesla driver to 375.39

### Fixed
- `nvidia-docker` updated to 1.0.1 for compatibility with Docker CE

## [2.5.3] - 2017-03-01
### Added
- `pool rebootnode` command added which allows single node reboot control.
Additionally, the option `--all-start-task-failed` will reboot all nodes in
the specified pool with the start task failed state.
- `jobs del` and `jobs term` now provide a `--termtasks` option to
allow the logic of `jobs termtasks` to precede the delete or terminate
action to the job. This option requires a valid SSH user to the remote nodes
as specified in the `ssh` configuration property in `pool.json`. This new
option is normally not needed if all tasks within the jobs have completed.

### Changed
- The Docker image used for blobxfer is now tied to the specific Batch
Shipyard release
- Default SSH user expiry time if not specified is now 30 days
- All recipes now have the default config.json storage account set to the
link as named in the provided credentials.json file. Now, only the credentials
file needs to be modified to run a recipe.

## [2.5.2] - 2017-02-23
### Added
- Chainer-CPU and Chainer-GPU recipes
- [Troubleshooting guide](docs/96-troubleshooting-guide.md)

### Changed
- Perform automatic container path substitution with host path for
GlusterFS data ingress/egress from/to Azure Storage (#37)
- Allow NAMD-TCP recipe to be run on a single node

### Fixed
- CNTK-GPU-OpenMPI run script fixed to allow multinode+singlegpu executions
- TensorFlow recipes updated for 1.0.0 release
- blobxfer data ingress on Windows (#39)
- Minor delete job and terminate tasks fixes

## [2.5.1] - 2017-02-01
### Added
- Support for max task retries (#23). See configuration doc for more
information.
- Support for task data retention time (#30). See configuration doc for
more information.

### Changed
- **Breaking Change:** `environment_variables_secret_id` was erroneously
named and has been renamed to `environment_variables_keyvault_secret_id` to
follow the other properties with similar behavior.
- Include Python 3.6 Travis CI target

### Fixed
- Automatically assigned task ids are now in the format `dockertask-NNNNN`
and will increment properly past 99999 but will not be padded after that (#27)
- Defect in list tasks for tasks that have not run (#28)
- Docker temporary directory not being set properly
- SLES-HPC will now install all Intel MPI related rpms
- Defect in task file mover for unencrypted credentials (#29)

## [2.5.0] - 2017-01-19
### Added
- Support for
[Task Dependency Id Ranges](https://docs.microsoft.com/azure/batch/batch-task-dependencies#task-id-range)
with the `depends_on_range` property under each task json property in `tasks`
in the jobs configuration file. Please see the configuration doc for more
information.
- Support for `environment_variables_secret_id` in job and task definitions.
Specifying these properties will fetch manually added secrets (in the form of
a string representation of a json key-value dictionary) from the specified
KeyVault using AAD credentials. Please see the configuration doc for more
information.

### Fixed
- Remove extraneous import (#12)
- Defect in handling per key secret ids (#13)
- Defect in environment variable dict merge (#17)
- Update Nvidia Docker to 1.0.0 (#21)

## [2.4.0] - 2017-01-11
### Added
- Support for credentials stored in Azure KeyVault
  - `keyvault` command added. Please see the usage doc for more information.
  - `*_keyvault_secret_id` properties added for keys and passwords in
    credentials json. Please see the configuration doc for more information.
- Using Azure KeyVault with Batch Shipyard guide

### Changed
- Updated NC-series Tesla driver to 375.20

## [2.3.1] - 2017-01-03
### Added
- Add support for nvidia-docker with ssh docker tunnel

### Fixed
- Fix multi-job bug with jpcmd

## [2.3.0] - 2016-12-15
### Added
- `pool ssh` command. Please see the usage doc for more information.
- `shm_size` json property added to the json object within the `tasks` array
of a job. Please see the configuration doc for more information.
- SSH, Interactive Sessions and Docker SSH Tunnel guide

### Changed
- Improve usability of the generated SSH docker tunnel script

## [2.2.0] - 2016-12-09
### Added
- CNTK-CPU-Infiniband-IntelMPI recipe

### Changed
- `/opt/intel` is now automatically mounted once again for infiniband-enabled
containers on SUSE SLES-HPC hosts.

### Fixed
- Fix masked KeyErrors on `input_data` and `output_data`
- Fix SAS key generation for data movement
- Typo in ssh public key check on Windows prevented pool add actions
- Pin version of tfm docker image on data transfers

## [2.1.0] - 2016-11-30
### Added
- Allow `--configdir`, `--credentials`, `--config`, `--jobs`, `--pool` config
options to be specified as environment variables. Please see the usage doc
for more information.
- Added subcommand `listskus` to the `pool` command to list available
VM configurations (publisher, offer, sku) for the Batch account

### Changed
- Nodeprep now references cascade and tfm docker images by version instead
of latest to prevent breaking changes affecting older versions. Docker builds
of cascade and tfm based on latest commits are now disabled.

### Fixed
- Cascade docker image run not propagating exit code

## [2.0.0] - 2016-11-23
### Added
- Support for any Internet accessible container registry, including
[Azure Container Registry](https://azure.microsoft.com/services/container-registry/).
Please see the configuration doc for information on how to integrate with
a private container registry.

### Changed
- GPU driver for `STANDARD_NC` instances defined in the
`gpu`:`nvidia_driver`:`source` property is no longer required. If omitted,
an NVIDIA driver will be downloaded automatically with an NVIDIA License
agreement prompt. For `STANDARD_NV` instances, a driver URL is still required.
- Docker container name auto-tagging now prepends the job id in order to
prevent conflicts in case of un-named simultaneous tasks from multiple jobs
- Update CNTK docker images to 2.0beta4 and optimize GPU images for use
with NVIDIA K80/M60
- Update Caffe docker image, default to using OpenBLAS over ATLAS, and
optimize GPU images for use with NVIDIA K80/M60
- Update MXNet GPU docker image optimized for use with NVIDIA K80/M60
- Update TensorFlow docker images to 0.11.0 and optimize GPU images for use
with NVIDIA K80/M60

### Fixed
- Cascade thread exceptions will terminate with non-zero exit code
- Some improvements with node prep and reboots
- Task termination will only issue `docker rm` if the container exists

## [2.0.0rc3] - 2016-11-14 (SC16 Edition)
### Added
- `install_conda_windows.cmd` helper script for installing Batch Shipyard
under Anaconda for Windows
- Added `relative_destination_path` json property for `files` ingress into
node destinations. This allows arbitrary specification of where ingressed
files should be placed relative to the destination path.
- Added ability to ingress directly into the host without the requirement
of GlusterFS for pools with one compute node. A GlusterFS shared volume is
required for pools with more than one compute node for direct to pool data
ingress.
- New commands and options:
  - `pool udi`: Update docker images on all compute nodes in a pool. `--image`
    and `--digest` options can restrict the scope of the update.
  - `data stream`: `--disk` will stream the file as binary to disk instead
    of as text to the local console
  - `data listfiles`: `--jobid` and `--taskid` allows scoping of the list
    files action
  - `jobs listtasks`: `--jobid` allows scoping of list tasks to a specific job
  - `jobs add`: `--tail` allows tailing the specified file for the last job
    and task added
- Keras+Theano-CPU and Keras+Theano-GPU recipes
- Keras+Theano-CPU added as an option in the quickstart guide

### Changed
- **Breaking Change:** Properties of `docker_registry` have changed
significantly to support eventual integration with the Azure Container
Registry service. Credentials for docker logins have moved to the credentials
json file. Please see the configuration doc for more information.
- `files` data ingress no longer creates a directory where files to
be uploaded exist. For example if uploading from a path `/a/b/c`, the
directory `c` is no longer created at the destination. Instead all files
found in `/a/b/c` will be immediately placed directly at the destination
path with sub-directories preserved. This behavior can be modified with
the `relative_destination_path` property.
- `CUDA_CACHE_*` variables are now set for GPU jobs such that compiled targets
pass-through to the host. This allows subsequent container invocations within
the same node the ability to reuse cached PTX JIT targets.
- `batch_shipyard`:`storage_entity_prefix` is now optional and defaults to
`shipyard` if not specified.
- Major internal configuration/settings refactor

### Fixed
- Pool resize down with wait
- More Python2/3 compatibility issues
- Ensure pools that deploy GlusterFS volumes have more than 1 node

## [2.0.0rc2] - 2016-11-02
### Added
- `install.sh` install/setup helper script
- `shipyard` execution helper script created via `install.sh`
- `generated_sas_expiry_days` json property to config json for the ability to
override the default number of days generated SAS keys are valid for.
- New options on commands/subcommands:
  - `jobs add`: `--recreate` recreate any jobs which have completed and use
    the same id
  - `jobs termtasks`: `--force` force docker kill to tasks even if they are
    in completed state
  - `pool resize`: `--wait` wait for completion of resize
- HPCG-Infiniband-IntelMPI and HPLinpack-Infiniband-IntelMPI recipes

### Changed
- Default SAS expiry time used for resource files and data movement changed
from 7 to 30 days.
- Pools failing to start will now automatically retrieve stdout.txt and
stderr.txt to the current working directory under
`poolid/<node ids>/std{out,err}.txt`. These files can be inspected
locally and submitted as context for GitHub issues if pertinent.
- Pool resizing will now attempt to add an SSH user on the new nodes if
an SSH public key is referenced or found in the invocation directory
- Improve installation doc

### Fixed
- Improve Python2/3 compatibility
- Unicode literals warning with Click
- Config file loading issue in some contexts
- Documentation typos

## [2.0.0rc1] - 2016-10-28
### Added
- Comprehensive data movement support. Please see the data movement guide
and configuration doc for more information.
  - Ingress from local machine with `files` in global configuration
    - To GlusterFS shared volume
    - To Azure Blob Storage
    - To Azure File Storage
  - Ingress from Azure Blob Storage, Azure File Storage, or another Azure
    Batch Task with `input_data` in pool and jobs configuration
    - Pool-level: to compute nodes
    - Job-level: to compute nodes prior to running the specified job
    - Task-level: to compute nodes prior to running a task of a job
  - Egress to local machine as actions
    - Single file from compute node
    - Entire task-level directories from compute node
    - Entire node-level directories from compute node
  - Egress to Azure Blob of File Storage with `output_data` in jobs
    configuration
    - Task-level: to Azure Blob or File Storage on successful completion of a
      task
- Credential encryption support. Please see the credential encryption guide
and configuration doc for more information.
- Experimental support for OpenSSH with HPN patches on Ubuntu
- Support pool resize up with GlusterFS
- Support GlusterFS volume options
- Configurable path to place files generated by `pool add` or `pool asu`
commands
- MXNet-CPU and Torch-CPU as options in the quickstart guide
- Update CNTK recipes for 1.7.2 and switch multinode/multigpu samples to
MNIST
- MXNet-CPU and MXNet-GPU recipes

### Changed
- **Breaking Change:** All new CLI experience with proper multilevel commands.
Please see usage doc for more information.
  - Added new commands: `cert`, `data`
  - Added many new convenience subcommands
  - `--filespec` is now delimited by `,` instead of `:`
- **Breaking Change:** `ssh_docker_tunnel` in the `pool_specification` has
been replaced by the `ssh` property. `generate_tunnel_script` has been renamed
to `generate_docker_tunnel_script`. Please see the configuration doc for
more information.
- The `name` property of a task json object in the jobs specification is no
longer required for multi-instance tasks. If not specified, `name` defaults
to `id` for all task types.
- `data stream` no longer has an arbitrary max streaming time; the action will
stream the file indefinitely until the task completes
- Validate container with `storage_entity_prefix` for length issues
- `pool del` action now cleans up and deletes some storage containers
immediately afterwards (with confirmation prompts)
- `/opt/intel` is no longer automatically mounted for infiniband-enabled
containers on SUSE SLES-HPC hosts. Please see the configuration doc
on how to manually map this directory if required. OpenLogic CentOS-HPC
hosts remain unchanged.
- Modularized code base

### Fixed
- GlusterFS mount ownership/permissions fixed such that SSH users can
read/write
- Azure File shared volume setup when invoked from Windows
- Python2 compatibility issues with file encoding
- Allow shipyard.py to be invoked outside of the root of the GitHub cloned
base directory
- TensorFlow-Distributed recipe issues

## [1.1.0] - 2016-10-05
### Added
- Transparent Infiniband assist for SUSE SLES-HPC 12-SP1 image
- Add version for shipyard.py script
- NAMD-GPU, OpenFOAM-Infiniband-IntelMPI, Torch-CPU, Torch-GPU recipes

### Changed
- GlusterFS mountpoint is now within `$AZ_BATCH_NODE_SHARED_DIR` so files can
be viewed/downloaded with Batch APIs
- NAMD-Infiniband-IntelMPI recipe now contains a real Docker image link

### Fixed
- GlusterFS not properly starting on Ubuntu

## [1.0.0] - 2016-09-22
### Added
- Automated GlusterFS support
- Added `configdir` argument for convenience in loading configuration files,
please see the usage documentation for more details
- Ability to retrieve files from live compute nodes in addition to streaming
- Added `filespec` argument for non-interactive `streamfile` and `gettaskfile`
actions
- Added .gitattributes to designate Unix line-endings for text files
- Sample configuration files for each recipe
- Caffe-CPU, OpenFOAM-TCP-OpenMPI, TensorFlow-CPU, TensorFlow-Distributed
recipes

### Changed
- Updated configuration docs to detail which properties are required vs. those
that are optional
- SSH tunnel user is now added with a default expiry time of 7 days which can
be modified through the pool configuration file
- Configuration is not output to console by default, `-v` flag added for
verbose output
- Determinstic remote login settings output (node, ip, port) that can be
easily parsed
- Update Azurefile Docker Volume Driver plugin to 0.5.1

### Fixed
- Cascade (container-only) start issue with no private registry
- Non-shipyard docker image node prep with new azure-storage package
- Inter-node communication not specified key error on addpool
- Cross-platform fixes:
  - Temp file creation used for environment variables
  - SSH tunnel creation disabled on Windows if public key is not supplied
- Batch Shipyard Docker container not getting cleaned up if peer-to-peer is
disabled

### Removed
- `gpu`:`nvidia_driver`:`version` property removed from pool configuration
and is no longer required as the version is now automatically detected

## [0.2.0] - 2016-09-08
### Added
- Transparent GPU support for Azure N-Series VMs
- New recipes added: Caffe-GPU, CNTK-CPU-OpenMPI, CNTK-GPU-OpenMPI,
FFmpeg-GPU, NAMD-Infiniband-IntelMPI, NAMD-TCP, TensorFlow-GPU

### Changed
- Multi-instance tasks now automatically complete their job by default. This
removes the need to run the `cleanmijobs` action in the shipyard tool.
Please refer to the
[multi-instance documentation](docs/80-batch-shipyard-multi-instance-tasks.md)
for more information and limitations.
- Dumb back-off policy for DHT router convergence
- Optimzed Docker image storage location for Azure VMs
- Prompts added for destructive operations in the shipyard tool

### Fixed
- Incorrect file location of node prep finished
- Blocking wait for global resource on pool can now be disabled
- Incorrect process call to query for docker image size when peer-to-peer
transfer is disabled
- Use azure-storage 0.33.0 to fix Edm.Int64 overflow issue

## [0.1.0] - 2016-09-01
#### Added
- Initial release

[Unreleased]: https://github.com/Azure/batch-shipyard/compare/3.8.0...HEAD
[3.8.0]: https://github.com/Azure/batch-shipyard/compare/3.7.1...3.8.0
[3.7.1]: https://github.com/Azure/batch-shipyard/compare/3.7.0...3.7.1
[3.7.0]: https://github.com/Azure/batch-shipyard/compare/3.6.1...3.7.0
[3.6.1]: https://github.com/Azure/batch-shipyard/compare/3.6.0...3.6.1
[3.6.0]: https://github.com/Azure/batch-shipyard/compare/3.6.0b1...3.6.0
[3.6.0b1]: https://github.com/Azure/batch-shipyard/compare/3.6.0a1...3.6.0b1
[3.6.0a1]: https://github.com/Azure/batch-shipyard/compare/3.5.3...3.6.0a1
[3.5.3]: https://github.com/Azure/batch-shipyard/compare/3.5.2...3.5.3
[3.5.2]: https://github.com/Azure/batch-shipyard/compare/3.5.1...3.5.2
[3.5.1]: https://github.com/Azure/batch-shipyard/compare/3.5.0...3.5.1
[3.5.0]: https://github.com/Azure/batch-shipyard/compare/3.5.0b3...3.5.0
[3.5.0b3]: https://github.com/Azure/batch-shipyard/compare/3.5.0b2...3.5.0b3
[3.5.0b2]: https://github.com/Azure/batch-shipyard/compare/3.5.0b1...3.5.0b2
[3.5.0b1]: https://github.com/Azure/batch-shipyard/compare/3.4.0...3.5.0b1
[3.4.0]: https://github.com/Azure/batch-shipyard/compare/3.3.0...3.4.0
[3.3.0]: https://github.com/Azure/batch-shipyard/compare/3.2.0...3.3.0
[3.2.0]: https://github.com/Azure/batch-shipyard/compare/3.1.0...3.2.0
[3.1.0]: https://github.com/Azure/batch-shipyard/compare/3.0.3...3.1.0
[3.0.3]: https://github.com/Azure/batch-shipyard/compare/3.0.2...3.0.3
[3.0.2]: https://github.com/Azure/batch-shipyard/compare/3.0.1...3.0.2
[3.0.1]: https://github.com/Azure/batch-shipyard/compare/3.0.0...3.0.1
[3.0.0]: https://github.com/Azure/batch-shipyard/compare/3.0.0rc1...3.0.0
[3.0.0rc1]: https://github.com/Azure/batch-shipyard/compare/3.0.0b1...3.0.0rc1
[3.0.0b1]: https://github.com/Azure/batch-shipyard/compare/3.0.0a2...3.0.0b1
[3.0.0a2]: https://github.com/Azure/batch-shipyard/compare/3.0.0a1...3.0.0a2
[3.0.0a1]: https://github.com/Azure/batch-shipyard/compare/2.9.6...3.0.0a1
[2.9.6]: https://github.com/Azure/batch-shipyard/compare/2.9.5...2.9.6
[2.9.5]: https://github.com/Azure/batch-shipyard/compare/2.9.4...2.9.5
[2.9.4]: https://github.com/Azure/batch-shipyard/compare/2.9.3...2.9.4
[2.9.3]: https://github.com/Azure/batch-shipyard/compare/2.9.2...2.9.3
[2.9.2]: https://github.com/Azure/batch-shipyard/compare/2.9.0rc1...2.9.2
[2.9.0rc1]: https://github.com/Azure/batch-shipyard/compare/2.9.0b2...2.9.0rc1
[2.9.0b2]: https://github.com/Azure/batch-shipyard/compare/2.9.0b1...2.9.0b2
[2.9.0b1]: https://github.com/Azure/batch-shipyard/compare/2.8.0...2.9.0b1
[2.8.0]: https://github.com/Azure/batch-shipyard/compare/2.8.0rc2...2.8.0
[2.8.0rc2]: https://github.com/Azure/batch-shipyard/compare/2.8.0rc1...2.8.0rc2
[2.8.0rc1]: https://github.com/Azure/batch-shipyard/compare/2.8.0b1...2.8.0rc1
[2.8.0b1]: https://github.com/Azure/batch-shipyard/compare/2.7.0...2.8.0b1
[2.7.0]: https://github.com/Azure/batch-shipyard/compare/2.7.0rc1...2.7.0
[2.7.0rc1]: https://github.com/Azure/batch-shipyard/compare/2.7.0b2...2.7.0rc1
[2.7.0b2]: https://github.com/Azure/batch-shipyard/compare/2.7.0b1...2.7.0b2
[2.7.0b1]: https://github.com/Azure/batch-shipyard/compare/2.6.2...2.7.0b1
[2.6.2]: https://github.com/Azure/batch-shipyard/compare/2.6.1...2.6.2
[2.6.1]: https://github.com/Azure/batch-shipyard/compare/2.6.0...2.6.1
[2.6.0]: https://github.com/Azure/batch-shipyard/compare/2.6.0rc1...2.6.0
[2.6.0rc1]: https://github.com/Azure/batch-shipyard/compare/2.6.0b3...2.6.0rc1
[2.6.0b3]: https://github.com/Azure/batch-shipyard/compare/2.6.0b2...2.6.0b3
[2.6.0b2]: https://github.com/Azure/batch-shipyard/compare/2.6.0b1...2.6.0b2
[2.6.0b1]: https://github.com/Azure/batch-shipyard/compare/2.5.4...2.6.0b1
[2.5.4]: https://github.com/Azure/batch-shipyard/compare/2.5.3...2.5.4
[2.5.3]: https://github.com/Azure/batch-shipyard/compare/2.5.2...2.5.3
[2.5.2]: https://github.com/Azure/batch-shipyard/compare/2.5.1...2.5.2
[2.5.1]: https://github.com/Azure/batch-shipyard/compare/2.5.0...2.5.1
[2.5.0]: https://github.com/Azure/batch-shipyard/compare/2.4.0...2.5.0
[2.4.0]: https://github.com/Azure/batch-shipyard/compare/2.3.1...2.4.0
[2.3.1]: https://github.com/Azure/batch-shipyard/compare/2.3.0...2.3.1
[2.3.0]: https://github.com/Azure/batch-shipyard/compare/2.2.0...2.3.0
[2.2.0]: https://github.com/Azure/batch-shipyard/compare/2.1.0...2.2.0
[2.1.0]: https://github.com/Azure/batch-shipyard/compare/2.0.0...2.1.0
[2.0.0]: https://github.com/Azure/batch-shipyard/compare/2.0.0rc3...2.0.0
[2.0.0rc3]: https://github.com/Azure/batch-shipyard/compare/2.0.0rc2...2.0.0rc3
[2.0.0rc2]: https://github.com/Azure/batch-shipyard/compare/2.0.0rc1...2.0.0rc2
[2.0.0rc1]: https://github.com/Azure/batch-shipyard/compare/1.1.0...2.0.0rc1
[1.1.0]: https://github.com/Azure/batch-shipyard/compare/1.0.0...1.1.0
[1.0.0]: https://github.com/Azure/batch-shipyard/compare/0.2.0...1.0.0
[0.2.0]: https://github.com/Azure/batch-shipyard/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/Azure/batch-shipyard/compare/ab1fa4d...0.1.0
