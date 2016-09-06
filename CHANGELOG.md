# Change Log

## [Unreleased]

## [0.2.0] - 2016-09-06
### Added
- Transparent GPU support for Azure N-Series VMs
- Optimzed Docker image storage location for Azure VMs
- NAMD-TCP, NAMD-Infiniband, TensorFlow-GPU, Caffe-GPU recipes

### Changed
- Multi-instance tasks now automatically complete their job by default. This
removes the need to run the `cleanmijobs` action in the shipyard tool.
Please refer to the
[multi-instance documentation](docs/80-batch-shipyard-multi-instance-tasks.md)
for more information and limitations.
- Dumb back-off policy for DHT router convergence

### Fixed
- Incorrect file location of node prep finished
- Blocking wait for global resource on pool can now be disabled
- Incorrect query for docker image size when peer-to-peer transfer is disabled

## [0.1.0] - 2016-09-01
#### Added
- Initial release

[Unreleased]: https://github.com/Azure/batch-shipyard/compare/0.2.0...HEAD
[0.2.0]: https://github.com/Azure/batch-shipyard/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/Azure/batch-shipyard/compare/ab1fa4d...0.1.0

