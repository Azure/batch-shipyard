# Change Log

## [Unreleased]
### Added
- Automated GlusterFS support
- Added `configdir` argument for convenience in loading configuration files,
please see the usage documentation for more details
- Ability to retrieve files from live compute nodes in addition to streaming
- Added `filespec` argument for non-interactive `streamfile` and `gettaskfile`
actions
- Added .gitattributes to designate Unix line-endings for text files
- Sample configuration files for each recipe
- Add TensorFlow-Distributed recipe

### Changed
- Updated configuration docs to detail which properties are required vs. those
that are optional
- SSH tunnel user is now added with a default expiry time of 7 days which can
be modified through the pool configuration file
- Configuration is not output to console by default, `-v` flag added for
verbose output
- Determinstic remote login settings output (node, ip, port) that can be
easily parsed

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

[Unreleased]: https://github.com/Azure/batch-shipyard/compare/0.2.0...HEAD
[0.2.0]: https://github.com/Azure/batch-shipyard/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/Azure/batch-shipyard/compare/ab1fa4d...0.1.0

