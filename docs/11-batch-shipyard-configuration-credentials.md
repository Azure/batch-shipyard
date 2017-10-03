# Batch Shipyard Credentials Configuration
This page contains in-depth details on how to configure the credentials
configuration file for Batch Shipyard.

## Schema
The credentials schema is as follows:

```yaml
credentials:
  aad:
    directory_id: 01234567-89ab-cdef-0123-456789abcdef
    application_id: 01234567-89ab-cdef-0123-456789abcdef
    auth_key: 01234...
    rsa_private_key_pem: some/path/privatekey.pem
    x509_cert_sha1_thumbprint: 01234...
    user: aad_username
    password: aad_user_password
  batch:
    aad:
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
    account_key: 01234...
    account_key_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
    account_service_url: https://<batch_account_name>.<region>.batch.azure.com/
    resource_group: resource-group-for-vnet-and-remotefs
  storage:
    mystorageaccount:
      account: storage_account_name
      account_key: 01234...
      account_key_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
      endpoint: core.windows.net
  docker_registry:
    hub:
      username: hub_username
      password: hub_user_password
      password_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
    myserver.azurecr.io:
      username: acr_username
      password: acr_user_password
      password_keyvault_secret_id: https://<vault_name>.vault.azure.net/secrets/<secret_id>
  management:
    aad:
      endpoint: https://management.core.windows.net/
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

### Azure Active Directory: `aad`
`aad` can be specified at the "global" level, which would apply to all
resources that can be accessed through Azure Active Directory: `batch`,
`keyvault` and `management`. `aad` should only be specified at the "global"
level if a common set of credentials are permitted to access all three
resources. The `aad` property can also be specified within each individual
credential section for `batch`, `keyvault` and `management`. Any `aad`
properties specified within a credential section will override any "global"
`aad` setting. Note that certain properties such as `endpoint` and
`token_cache` are not available at the "global" level.

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
      key. This is required for non-AAD logins. This option takes precendence
      over the `aad` property if specified.
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
name) can be the same as the storage account name itself.
    * (optional) `account_key_keyvault_secret_id` property can be used to
      reference an Azure KeyVault secret id. Batch Shipyard will contact the
      specified KeyVault and replace the `account_key` value as returned by
      Azure KeyVault.

### Docker Registries: `docker_registry`
* (optional) `docker_registry` property defines logins for Docker registry
servers. This property does not need to be defined if you are using only
public repositories on Docker Hub. However, this is required if pulling from
authenticated private registries such as a secured Azure Container Registry
or private repositories on Docker Hub.
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
      connect to the [Azure Container Registry service](https://azure.microsoft.com/en-us/services/container-registry/).
      The private registry defined here should be defined as the `server`
      property in the `docker_registry`:`private` property in the global
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
with a virtual network specification (thus UserSubscription Batch accounts).
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

## Full template
A full template of a credentials file can be found
[here](https://github.com/Azure/batch-shipyard/tree/master/config_templates).
Note that these templates cannot be used as-is and must be modified to fit
your scenario.
