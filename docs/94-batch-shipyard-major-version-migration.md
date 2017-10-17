# Batch Shipyard Major Version Migration Guide
This guide is to help you understand potential issues and provide guidance
when migrating your workload between major versions of Batch Shipyard.
Please pay special attention to breaking changes and potential
backward-incompatible actions.

## Migrating from 2.x to 3.x
There are significant changes between 2.x and 3.x in terms of configuration
format, options/properties and implied behavior. Please read through each
section carefully.

### Important Notes
* If you have existing 2.x pools, do not issue `pool del` with the 3.x
CLI until you have migrated all of your jobs to 3.x pools. Failure to do
so will render your existing pools unable to resize up (either manually
or via autoscale).
* Do not mix 2.x and 3.x pools with the same storage account used for
backing metadata used by Batch Shipyard.
* If you must used a mixed-mode environment, please specify a different
storage account for metadata between the two versions in the global
configuration file.

### YAML Configuration Support
Although you can still use your configuration files in JSON format, it
is recommended to migrate to YAML as all documentation and recipes are now
shown in this format. You need not perform this conversion by hand. To
perform automatic conversion, first install the converter program and
then run for each config file.

```shell
# recommended to install the following with --user or in a virtual env
pip3 install ruamel.yaml.cmd

yaml json credentials.json > credentials.yaml
yaml json config.json > config.yaml
yaml json pool.json > pool.yaml
yaml json jobs.json > jobs.yaml

# verify YAML conversion first, then delete json files (assuming the
# aforementioned json files are the only json files that exist in this
# directory)
rm *.json
```

You can create an automated conversion script to perform this across
multiple files. For example, this simple script takes in a directory
as its only argument and automatically performs conversion of all `.json`
files found.

```shell
#!/usr/bin/env bash

for file in $1/*; do
    ext="${file##*.}"
    if [ "$ext" == ".yaml" ]; then
        continue
    fi
    stem="${file%.*}"
    ymlfile="$stem.yaml"
    yaml json $file > $ymlfile
    rm $file
done
```

You may wish to edit your YAML configuration files to reorder properties
as you see fit (conforming to correct configuration) as the converter
alpha orders by key property name.

### Commandline Changes
#### CLI Docker Image Naming
The Docker image name for the CLI has changed. Batch Shipyard Docker images
now follow the `version-component` naming convetion for tags. Thus, the
`latest` CLI version will now be `alfpark/batch-shipyard:latest-cli`. This
will also apply to versioned CLI images. For example, version `3.0.0` will
be named as `alfpark/batch-shipyard:3.0.0-cli`.

#### Environment Variable Naming
Environment variable names have changed as configuration files are no longer
exclusively JSON formatted. The `_JSON` suffix is now replaced with `_CONF`.
The variable mapping is as follows:

| Old                         | New                         |
|-----------------------------|-----------------------------|
| `SHIPYARD_CREDENTIALS_JSON` | `SHIPYARD_CREDENTIALS_CONF` |
| `SHIPYARD_CONFIG_JSON`      | `SHIPYARD_CONFIG_CONF`      |
| `SHIPYARD_POOL_JSON`        | `SHIPYARD_POOL_CONF`        |
| `SHIPYARD_JOBS_JSON`        | `SHIPYARD_JOBS_CONF`        |
| `SHIPYARD_FS_JSON`          | `SHIPYARD_FS_CONF`          |

#### `--configdir` Default
`--configdir` (or `SHIPYARD_CONFIGDIR` environment variable) now defaults
to the current working directory, i.e., `.`, if no other configuration file
options are specified.

### General Configuration Changes
#### `input_data` with `azure_storage`
Due to the migration to `blobxfer 1.0.0`, any specification with data
ingress from Azure Storage has been changed to take advantage of the new
features.

The old configuration style:

```json
"input_data": {
    "azure_storage": [
        {
            "storage_account_settings": "mystorageaccount",
            "container": "mycontainer",
            "include": ["data/*.bin"],
            "destination": "$AZ_BATCH_NODE_SHARED_DIR/mydata",
            "blobxfer_extra_options": null
        }
    ]
}
```

`container` or `file_share` is no longer a valid property. The new version
of `blobxfer` allows specifying the exact remote Azure path to source data
from which gives you greater control and flexibility without having to resort
to individual configuration blocks with single include filters. Thus,
`container` or `file_share` is now simply `remote_path` which is the
Azure storage path including the container or file share name with all
virtual directories (if required), and if downloading a single entity, the
name of the remote object. Thus, you can specify, for example,
`mycontainer/dir` to download all of the blob objects with the `dir`
directory of `mycontainer`. Or you can even specify, for example,
`myfileshare/dir/myfile.dat` to download just the single file. To specify
that your `remote_path` is on Azure Files rather than Azure
Blob Storage, you will need to specify `is_file_share` as `true`.

`include` is now truly a list property where you can specify zero or more
include filters to be applied to the `remote_path`. Additionally, there is
now support for zero or more `exclude` filters (specified as a list, similar
to `include`) which will be applied after all of the include filters are
applied.

`destination` is now renamed as `local_path` to conform with the new
`blobxfer` command structure.

For the example above, this old 2.x configuration should be converted to:

```yaml
input_data:
  azure_storage:
  - storage_account_settings: mystorageaccount
    remote_path: mycontainer/data
    include:
    - '*.bin'
    is_file_share: false
    local_path: $AZ_BATCH_NODE_SHARED_DIR/mydata
```

### Credentials Configuration Changes
#### `aad` can be "globally" set
Most of the `aad` members can now be set at the global level under an
`aad` property which will apply to all services that can or must be accessed
via Azure Active Directory. You should only apply this type of configuration
if your service principal (application/client) has sufficient permission and
action permissions for operations required. Please see the
[credentials documentation](11-batch-shipyard-configuration-credentials.md)
for more information.

### Global Configuration Changes
#### `docker_registry` is no longer valid
Configuration for Docker image references to add to a pool have now been
greatly simplified. This section is no longer valid and should not be
specified. Instead, please specify fully qualified Docker image names
within the `docker_images` property of `global_resources`. See the next
section for more information. `docker_registry` under credentials is
still required for registry servers requiring valid logins.

#### Fully-qualified Docker image names in `docker_images`
Images specified in the `docker_images` property of `global_resources`
should be fully-qualified with any Docker registry server prepended to the
image as if referencing this image on a local machine with `docker pull`
or `docker run`. Image names with no server will default to Docker public hub.

If the Docker registry server where the image resides requires a login,
then the server must have a corresponding credential in the credentials
configuration under `docker_registry`.

#### Private registries backed to Azure Storage Blob
Private registries backed directly to Azure Storage Blob are no longer
supported. This is not to be confused with a "Classic" Azure Container
Registry which is still supported.

If you are still using this mechanism, please migrate your images to another
Docker registry such as
[Azure Container Registry](https://azure.microsoft.com/en-us/services/container-registry/).

#### Additional registries
If you want to execute tasks referencing Docker images that are not specified
in the `docker_images` property under `global_resources` but require valid
logins, then you should specify these registry servers under the
`additional_registries` property.

### Pool Configuration Changes
#### Virtual Network
Virtual networks can now be specified with the ARM Subnet Id directly.
Set `arm_subnet_id` to the full ARM Subnet Id. This will cause other
properties within the `virtual_network` property to be ignored.

You can find an ARM Subnet Id through the portal by selecting `Properties`
on the corresponding virtual network and then appending
`/subnets/<subnet_name>` where `<subnet_name>` is the name of the subnet.

Note that you must use a `aad` credential with your Batch account. Please
see the [Virtual Network guide](64-batch-shipyard-byovnet.md) for more
information.

#### Custom Images
Custom images are now provisioned from an ARM Image Resource rather than
a page blob VHD. Set the `arm_image_id` to the ARM Image Id. You can find
an ARM Image Id through the portal by clicking on the ARM Image resource
where it will be displayed as `RESOURCE ID`.

Please see the [Custom Image guide](63-batch-shipyard-custom-images.md) for
more information.

#### Native container support pools
Azure Batch can now provision pools with Docker container support built-in.
You can specify the `native` property as `true`. Batch Shipyard will determine
if the specified platform image is compatible with native container support
and will enable it, if so. Custom images can also be natively supported, but
may fail provisioning if requisite software is not installed. If you follow
the [Custom Image guide](63-batch-shipyard-custom-images.md) then the image
should be `native` compatible.

Please see this
[FAQ item](97-faq.md#what-is-native-under-pool-platform_image-and-custom_image)
regarding when to choose `native` container support pools.

### Jobs Configuration Changes
#### `docker_image` preferred over `image`
In the tasks array, `docker_image` is now preferred over `image` for
disambiguation.

#### Fully-qualified Docker image name required
The `docker_image` (or deprecated `image`) name specified for the task
must be fully qualified with any Docker registry server prefixed (e.g.,
as if you are on a local machine executing `docker pull` or `docker run`).
Image names with no server will default to Docker public hub.

#### Specialized hardware flags
Both `gpu` and `infiniband` no longer need to be explicitly set to `true`.
Batch Shipyard will automatically detect if these settings can be enabled
and will apply them on your behalf. If you wish to explicitly disable
exposing specialized hardware to the container, you can set either or both
of these flags to `false`.

#### `output_data` with `azure_storage`
Due to the migration to `blobxfer 1.0.0`, any specification within the tasks
array with data egress to Azure Storage has been changed to take advantage
of the new features.

The old configuration style:

```json
"output_data": {
    "azure_storage": [
        {
            "storage_account_settings": "mystorageaccount",
            "container": "output",
            "source": null,
            "include": ["out*.bin"],
            "blobxfer_extra_options": null
        }
    ]
}
```

`container` or `file_share` is no longer a valid property. The new version
of `blobxfer` allows specifying the exact remote Azure path to place data
to which gives you greater control and flexibility without having to resort
to individual configuration blocks with single include filters. Thus,
`container` or `file_share` is now simply `remote_path` which is the
Azure storage path including the container or file share name with all
virtual directories (if required), and if uploading a single entity, the
name of the remote object. Thus, you can specify, for example,
`myfileshare/dir` to upload all local files to the `dir` directory directly.
 To specify that your `remote_path` is on Azure Files rather than Azure
Blob Storage, you will need to specify `is_file_share` as `true`.
Or you can even specify, for example, `myfileshare/dir/myfile.dat` to upload
just the single file. If you are uploading a single entity, remember to
use `--rename` in the `blobxfer_extra_options` list.

`include` is now truly a list property where you can specify zero or more
include filters to be applied to the `remote_path`. Additionally, there is
now support for zero or more `exclude` filters (specified as a list, similar
to `include`) which will be applied after all of the include filters are
applied.

`source` is now renamed as `local_path` to conform with the new
`blobxfer` command structure. `local_path` can be empty (which will default
to the task's directory, i.e., `$AZ_BATCH_TASK_DIR`).

For the example above, this old 2.x configuration should be converted to:

```yaml
output_data:
  azure_storage:
  - storage_account_settings: mystorageaccount
    remote_path: output
    include:
    - 'out*.bin'
    is_file_share: false
```

#### File-based `task_factory` with `azure_storage`
Due to the migration to `blobxfer 1.0.0`, any specification within the tasks
array with a `file` `task_factory` and `azure_storage` has been changed.

The old configuration style:

```json
"task_factory": {
    "file": {
        "azure_storage": {
            "storage_account_settings": "mystorageaccount",
            "file_share": "myfileshare",
            "include": ["*.png"],
            "exclude": ["*.tmp"]
        },
        "task_filepath": "file_name"
    }
}
```

`container` or `file_share` is no longer a valid property. The new version
of `blobxfer` allows specifying the exact remote Azure path to source data
from which gives you greater control and flexibility without having to resort
to individual configuration blocks with single include filters. Thus,
`container` or `file_share` is now simply `remote_path` which is the
Azure storage path including the container or file share name with all
virtual directories (if required). Thus, you can specify, for example,
`mycontainer/dir` to generate tasks based on all of the blob objects with
the `dir` directory of `mycontainer`. To specify that your `remote_path`
is on Azure Files rather than Azure Blob Storage, you will need to specify
`is_file_share` as `true`.

For the example above, this old 2.x configuration should be converted to:

```yaml
task_factory:
  file:
    azure_storage:
      storage_account_settings: mystorageaccount
      remote_path: myfileshare
      is_file_share: true
      exclude:
      - '*.tmp'
      include:
      - '*.png'
    task_filepath: file_name
```
