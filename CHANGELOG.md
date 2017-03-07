# Change Log

## [Unreleased]
### Changed
- All dependencies updated to latest versions
- Update Batch API call compatibility for `azure-batch 2.0.0`
- Precompile python files for Docker images

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
[Task Dependency Id Ranges](https://docs.microsoft.com/en-us/azure/batch/batch-task-dependencies#task-id-range)
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
[Azure Container Registry](https://azure.microsoft.com/en-us/services/container-registry/).
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

[Unreleased]: https://github.com/Azure/batch-shipyard/compare/2.5.4...HEAD
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
