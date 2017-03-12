# Batch Shipyard Configuration
This page contains in-depth details on how to configure Batch Shipyard.

## Configuration Files
Batch Shipyard is driven by the following json configuration files:

1. [Credentials](11-batch-shipyard-configuration-credentials.md) -
credentials for Azure Batch, Storage, KeyVault, Management and Docker private
registries
2. [Global config](12-batch-shipyard-configuration-global.md) -
Batch Shipyard and Docker-specific configuration settings
3. [Pool](13-batch-shipyard-configuration-pool.md) -
Batch Shipyard pool configuration
4. [Jobs](14-batch-shipyard-configuration-jobs.md) -
Batch Shipyard jobs and tasks configuration
5. [FS](15-batch-shipyard-configuration-fs.md) -
Batch Shipyard remote filesystem configuration. This configuration is
entirely optional unless using the remote filesystem capabilities of
Batch Shipyard.

Note that all potential properties are described here and that specifying
all such properties may result in invalid configuration as some properties
may be mutually exclusive. Please read the following document carefully when
crafting your configuration files.

Each property is marked with required or optional. Properties marked with
experimental should be considered as features for testing only.

Example config templates can be found in [this directory](../config\_templates)
of the repository. Note that templates contain every possible property and
may be invalid if specified as such. They must be modified for your execution
scenario. All [sample recipe](../recipes) also have a set of configuration
files that can be modified to fit your needs.

## Batch Shipyard Usage
Continue on to [Batch Shipyard Usage](20-batch-shipyard-usage.md).
