# Change Log

## [Unreleased]

### Added
- `misc tensorboard` command added which automatically instantiates a
Tensorboard instance on the compute node which is running or has ran a
task that has generated TensorFlow summary operation compatible logs. An
SSH tunnel is then created so you can view Tensorboard locally on the
machine running Batch Shipyard. This requires a valid SSH user has been
provisioned via Batch Shipyard with private keys available. This command
will work on Windows if `ssh.exe` is available in `%PATH%` or the current
working directory. Please see the usage guide for more information about
this command.

### Changed
- Added optional `COMMAND` argument to `pool ssh` and `fs cluster ssh`
commands. If `COMMAND` is specified, the command is run non-interactively
with SSH on the target node.
- Added some additional sanity checks in the node prep script
- Updated TensorFlow-CPU and TensorFlow-GPU recipes to 1.1.0. Removed
specialized Docker build for TensorFlow-GPU. Added `jobs-tb.json` files
to TensorFlow-CPU and TensorFlow-GPU recipes as Tensorboard samples.

### Fixed
- Site extension issues
- SSH user add exception on Windows
- `data stream` off-by-one segment issue
- `jobs del --termtasks` will now disable the job prior to running task
termination to prevent active tasks in job from running while tasks are
being terminated
- `jobs listtasks` and `data listfiles` will now accept a `--jobid` that
does not have to be in `jobs.json`

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
[UserSubscription Batch accounts](https://docs.microsoft.com/en-us/azure/batch/batch-account-create-portal#user-subscription-mode)
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

[Unreleased]: https://github.com/Azure/batch-shipyard/compare/2.6.0...HEAD
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
