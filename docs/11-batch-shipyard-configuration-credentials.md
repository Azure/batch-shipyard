# Batch Shipyard Credentials Configuration
This page contains in-depth details on how to configure the credentials
configuration file for Batch Shipyard.

## Schema
The credentials schema is as follows:

```yaml
credentials:
  aad:
    authority_url: https://login.microsoftonline.com
    directory_id: 01234567-89ab-cdef-0123-456789abcdef
    application_id: 01234567-89ab-cdef-0123-456789abcdef
    auth_key: 01234...
    rsa_private_key_pem: some/path/privatekey.pem
    x509_cert_sha1_thumbprint: 01234...
    user: aad_username
    password: aad_user_password
  batch:
    aad:
      authority_url: https://login.microsoftonline.com
      endpoint: https://management.azure.com/
      directory_id: 01234567-89ab-cdef-0123-456789abcdef
      application_id: 01234567-89ab-cdef-0123-456789abcdef
      auth_key: 01234...
      rsa_private_key_pem: some/path/privatekey.pem
      x509_cert_sha1_thumbprint: 01234...
      user: aad_username
      password: aad_user_password
      token_cache:
        enabled: true
        filename: some/path/token.cache
    account_key: 01234...
    account_key_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
    account_service_url: https://<batch_account_name>.<region>.batch.azure.com/
    resource_group: resource-group-of-batch-account
  storage:
    aad:
      authority_url: https://login.microsoftonline.com
      endpoint: https://batch.core.windows.net/
      directory_id: 01234567-89ab-cdef-0123-456789abcdef
      application_id: 01234567-89ab-cdef-0123-456789abcdef
      auth_key: 01234...
      rsa_private_key_pem: some/path/privatekey.pem
      x509_cert_sha1_thumbprint: 01234...
      user: aad_username
      password: aad_user_password
      token_cache:
        enabled: true
        filename: some/path/token.cache
    mystorageaccount:
      account: storage_account_name
      account_key: 01234...
      account_key_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
      endpoint: core.windows.net
      resource_group: resource-group-of-storage-account
  docker_registry:
    hub:
      username: hub_username
      password: hub_user_password
      password_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
    myserver.azurecr.io:
      username: acr_username
      password: acr_user_password
      password_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
  singularity_registry:
    myserver.azurecr.io:
      username: acr_username
      password: acr_user_password
      password_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
  management:
    aad:
      authority_url: https://login.microsoftonline.com
      endpoint: https://management.azure.com/
      directory_id: 01234567-89ab-cdef-0123-456789abcdef
      application_id: 01234567-89ab-cdef-0123-456789abcdef
      auth_key: 01234...
      rsa_private_key_pem: some/path/privatekey.pem
      x509_cert_sha1_thumbprint: 01234...
      user: aad_username
      password: aad_user_password
      token_cache:
        enabled: true
        filename: some/path/token.cache
    subscription_id: 01234567-89ab-cdef-0123-456789abcdef
  keyvault:
    aad:
      authority_url: https://login.microsoftonline.com
      endpoint: https://keyvault.core.windows.net/
      directory_id: 01234567-89ab-cdef-0123-456789abcdef
      application_id: 01234567-89ab-cdef-0123-456789abcdef
      auth_key: 01234...
      rsa_private_key_pem: some/path/privatekey.pem
      x509_cert_sha1_thumbprint: 01234...
      user: aad_username
      password: aad_user_password
      token_cache:
        enabled: true
        filename: some/path/token.cache
    credentials_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
    uri: https://<vault_name>.vault.azure.net/
```

## Details
The `credentials` property is where Azure Batch and Storage credentials
are defined. Azure Active Directory (AAD) must be used with `keyvault` and
`management` credential sections. AAD credentials can be optionally used
for `batch` credentials but are required for `batch` credentials when using
UserSubscription Batch accounts.

For non-public Azure regions, please see [this section](#non-public) after
reviewing the options below.

### Azure Active Directory: `aad`
`aad` can be specified at the "global" level, which would apply to all
resources that can be accessed through Azure Active Directory: `batch`,
`storage`, `keyvault` and `management`. `aad` should only be specified at
the "global" level if a common set of credentials are permitted to access
all four resources. The `aad` property can also be specified within each
individual credential section for `batch`, `keyvault` and `management`.
Any `aad` properties specified within a credential section will override
any "global" `aad` setting. Note that certain properties such as `endpoint`
and `token_cache` are not available at the "global" level.

The `aad` property contains members for Azure Active Directory credentials.
This section may not be needed or applicable for every credential section.
Note that some options are mutually exclusive of each other depending upon
authentication type. The available authentication types for Batch Shipyard
with the required parameters for each are:

* Service principal authentication key: `application_id` and `auth_key`
* Certificate-based asymmetric key auth: `application_id`,
`rsa_private_key_pem` and `x509_cert_sha1_thumbprint`
* Username directory authentication: `username` and `password` if multi-factor
authentication is not required, or just `username` if multi-factor
authentication is required.

In a nutshell, you are only required the authentication parameters necessary
to authenticate your service principal or AAD user account. This will not
require all of the following properties to be specified. Note that most of
the following properties can be specified as a CLI option or as an
environment variable instead. For example, if you do not want to store the
`auth_key` in the file, it can be specified at runtime.

Authentication independent settings:

* (optional) `authority_url` is the AAD authority URL. If this is not
specified, then this defaults to the Azure Public cloud AAD authority.
* (optional) `endpoint` is the AAD endpoint for the associated resource. If
not specified, these default to the Azure Public cloud endpoints for the
respective resource.
* (required) `directory_id` AAD directory (tenant) id
* (optional) `application_id` AAD application (client) id

Service principal authentication key settings:

* (optional) `auth_key` Service Principal authentication key

Certificate-based asymmetric key authentication settings:

* (optional) `rsa_private_key_pem` path to RSA private key PEM file if using
Certificate-based authentication
* (optional) `x509_cert_sha1_thumbprint` thumbprint of the X.509
certificate for use with Certificate-based authentication

Username authentication settings:

* (optional) `user` AAD username
* (optional) `password` AAD password associated with the user if using
username and password authentication. You can omit this property if you
want to resort to interactive multi-factor authentication.
* (optional) `token_cache` defines token cache properties for multi-factor
device code auth only. Tokens are not cached for other auth mechanisms.
    * (optional) `enabled` enables the token cache for device code auth
    * (optional) `filename` specifies the file path to cache the signed token

### Batch: `batch`
* (required) The `batch` property defines the Azure Batch account. Members
under the `batch` property can be found in the
[Azure Portal](https://portal.azure.com) under your Batch account or via
the Azure CLI.
    * (required) `account_service_url` is the Batch account service URL.
    * (required for auth via AAD) `aad` defines the AAD authentication
      parameters for Azure Batch.
    * (required for `virtual_network` in pool settings if `arm_subnet_id` is
      not specified) `resource_group` is the resource group containing the
      Batch account.
    * (required unless `aad` is specified) `account_key` is the shared
      key. This is required for non-AAD logins. You cannot specify both
      this option and `aad` at the same time.
    * (optional) `account_key_keyvault_secret_id` property can be used to
      reference an Azure KeyVault secret id. Batch Shipyard will contact the
      specified KeyVault and replace the `account_key` value as returned by
      Azure KeyVault. This cannot be used with Batch accounts authenticated
      with `aad`.

### Storage: `storage`
* (required) Multiple storage properties can be defined which references
different Azure Storage account credentials under the `storage` property. This
may be needed for more flexible configuration in other configuration files. In
the example above, we only have one storage account defined which is aliased
by the property name `mystorageaccount`. The alias (or storage account link
name) can be the same as the storage account name itself. Note that it is
possible to not specify an `account_key` directly through the use of `aad`
or `account_key_keyvault_secret_id`.
    * (optional) `aad` AAD authentication parameters for Azure Storage.
    * (required, at least 1) `<account-name-link>` is an arbitrary account
      name link. This does not necessarily need to be the name of the storage
      account but the link name to be referred in other configuration files.
      This link name cannot be named `aad`.
        * (required) `account` is the storage account name
        * (required unless `aad` or `account_key_keyvault_secret_id` is
          specified) `account_key` is the storage account key
        * (optional) `account_key_keyvault_secret_id` property can be used to
          reference an Azure KeyVault secret id. Batch Shipyard will contact
          the specified KeyVault and replace the `account_key` value as
          returned by Azure KeyVault.
        * (optional) `endpoint` is the storage endpoint to use. The default
          if not specified is `core.windows.net` which is the Public Azure
          default.
        * (required if `aad` is specified) `resource_group` is the resource
          group of the storage account. This is required if `account_key`
          is not specified and `aad` is used instead.

### Docker and Singularity Registries: `docker_registry` and `singularity_registry`
* (optional) `docker_registry` or `singularity_registry` property defines
logins for Docker and Singularity registry servers. Currently, a Singularity
registry server is a Docker registry server to support `docker://` private
URIs. This property does not need to be defined if you are using only
public repositories on Docker Hub or Singularity Hub. However, this is
required if pulling from authenticated private registries such as a secured
Azure Container Registry or private repositories on Docker Hub.
    * (optional) `hub` defines the login property to Docker Hub. This is only
    required for private repos on Docker Hub.
    * (optional) `username` username to log in to Docker Hub
    * (optional) `password` password associated with the username
    * (optional) `password_keyvault_secret_id` property can be used to
      reference an Azure KeyVault secret id. Batch Shipyard will contact the
      specified KeyVault and replace the `password` value as returned by
      Azure KeyVault.
    * (optional) `myserver-myorg.azurecr.io` is an example property that
      defines a private container registry to connect to. This is an example to
      connect to the [Azure Container Registry service](https://azure.microsoft.com/services/container-registry/).
      The private registry defined here should be included as a server prefix
      of an image for `global_resources`:`docker_images`,
      `global_resources`:`singularity_images`,
      `global_resources`:`additional_registries`:`docker`,
      `global_resources`:`additional_registries`:`singularity` in the global
      configuration.
      * (optional) `username` username to log in to this registry
      * (optional) `password` password associated with this username
      * (optional) `password_keyvault_secret_id` property can be used to
        reference an Azure KeyVault secret id. Batch Shipyard will contact the
        specified KeyVault and replace the `password` value as returned by
        Azure KeyVault.

### Management: `management`
* (optional) The `management` property defines the required members for
accessing Azure Resources (ARM) with Azure Active Directory credentials. This
is required with `fs` filesystem actions and pools that need to be created
with a `virtual_network` specification.
    * (required) `subscription_id` is the subscription id to interact with.
    * (required) `aad` AAD authentication parameters for ARM.

### KeyVault: `keyvault`
Please see the
[Azure KeyVault and Batch Shipyard Guide](74-batch-shipyard-azure-keyvault.md)
for more information. This section is not strictly required for using
Batch Shipyard.

* (optional) The `keyvault` property defines the required members for
accessing Azure KeyVault with Azure Active Directory credentials. Note that
this property is *mutually exclusive* of all other properties in this file.
If you need to define other members in this config file while using Azure
KeyVault, then you will need to use environment variables or cli parameters
instead for AAD and KeyVault credentials.
    * (optional) `uri` property defines the Azure KeyVault DNS name (URI).
    * (optional) `credentials_secret_id` property defines the KeyVault secret
      id containing an entire credentials.yaml file.
    * (required) `aad` AAD authentication parameters for KeyVault.

Please refer to the
[Azure KeyVault and Batch Shipyard guide](74-batch-shipyard-azure-keyvault.md)
for more information regarding `*_keyvault_secret_id` properties and how
they are used for credential management with Azure KeyVault.

## <a name="non-public"></a>Non-Public Azure Regions
To connect to non-public Azure regions, you will need to ensure that your
credentials configuration is populated with the correct `authority_url` and
`endpoint` for each section. Please refer to the appropriate documentation
below for your region:

* [Azure China](https://docs.microsoft.com/azure/china/china-get-started-developer-guide#check-endpoints-in-azure)
* [Azure Germany](https://docs.microsoft.com/azure/germany/germany-developer-guide#endpoint-mapping)
* [Azure Government](https://docs.microsoft.com/azure/azure-government/documentation-government-developer-guide#endpoint-mapping)

Here is an example skeleton for connecting to Azure Government with AAD:

```yaml
credentials:
  aad:
    authority_url: https://login.microsoftonline.us
    directory_id: # insert your directory/tenant id
    application_id: # insert your service principal/app id
    # fill in your AAD auth method of choice
  batch:
    aad:
      endpoint: https://batch.core.usgovcloudapi.net/
    account_service_url: # insert your account service url/endpoint
    resource_group: # insert your batch account resource group
  management:
    aad:
      endpoint: https://management.usgovcloudapi.net/
    subscription_id: # insert your subscription id
  storage:
    mystorageaccount:
      account: # insert your account name
      account_key: # insert your account key or omit if accessing via aad
      endpoint: core.usgovcloudapi.net
  # other credentials settings
```

If you are using shared key auth, you would remove all `aad` settings and
add your `batch`:`account_key` instead.

## Full template
A full template of a credentials file can be found
[here](https://github.com/Azure/batch-shipyard/tree/master/config_templates).
Note that these templates cannot be used as-is and must be modified to fit
your scenario.
