# Batch Shipyard Credentials Configuration
This page contains in-depth details on how to configure the credentials
json file for Batch Shipyard.

## Schema
The credentials schema is as follows:

```json
{
    "credentials": {
        "keyvault": {
            "uri": "https://myvault.vault.azure.net/",
            "credentials_secret_id": "https://myvault.vault.azure.net/secrets/credentialsjson",
            "aad": {
                "endpoint": "https://vault.azure.net",
                "directory_id": "01234567-89ab-cdef-0123-456789abcdef",
                "application_id": "01234567-89ab-cdef-0123-456789abcdef",
                "auth_key": "01234...",
                "rsa_private_key_pem": "/path/to/privkey.pem",
                "x509_cert_sha1_thumbprint": "01AB02CD...",
                "user": "me@domain.com",
                "password": "password",
                "token_cache": {
                    "enabled": true,
                    "filename": ""
                }
            }
        },
        "management": {
            "subscription_id": "",
            "aad": {
                "endpoint": "https://management.core.windows.net/",
                "directory_id": "01234567-89ab-cdef-0123-456789abcdef",
                "application_id": "01234567-89ab-cdef-0123-456789abcdef",
                "auth_key": "01234...",
                "rsa_private_key_pem": "/path/to/privkey.pem",
                "x509_cert_sha1_thumbprint": "01AB02CD...",
                "user": "me@domain.com",
                "password": "password",
                "token_cache": {
                    "enabled": true,
                    "filename": ""
                }
            }
        },
        "batch": {
            "account_service_url": "https://awesomebatchaccountname.<region>.batch.azure.com/",
            "aad": {
                "endpoint": "https://batch.core.windows.net/",
                "directory_id": "01234567-89ab-cdef-0123-456789abcdef",
                "application_id": "01234567-89ab-cdef-0123-456789abcdef",
                "auth_key": "01234...",
                "rsa_private_key_pem": "/path/to/privkey.pem",
                "x509_cert_sha1_thumbprint": "01AB02CD...",
                "user": "me@domain.com",
                "password": "password",
                "token_cache": {
                    "enabled": true,
                    "filename": ""
                }
            },
            "resource_group": "",
            "account_key": "batchaccountkey",
            "account_key_keyvault_secret_id": "https://myvault.vault.azure.net/secrets/batchkey"
        },
        "storage": {
            "mystorageaccount": {
                "account": "awesomestorageaccountname",
                "account_key": "storageaccountkey",
                "account_key_keyvault_secret_id": "https://myvault.vault.azure.net/secrets/storagekey",
                "endpoint": "core.windows.net"
            }
        },
        "docker_registry": {
            "hub": {
                "username": "myhublogin",
                "password": "myhubpassword",
                "password_keyvault_secret_id": "https://myvault.vault.azure.net/secrets/docker-hub-password"
            },
            "myserver-myorg.azurecr.io": {
                "username": "azurecruser",
                "password": "mypassword",
                "password_keyvault_secret_id": "https://myvault.vault.azure.net/secrets/myserver-myorg-azurecr-io-password"
            }
        }
    }
}
```

## Details
The `credentials` property is where Azure Batch and Storage credentials
are defined. Azure Active Directory (AAD) must be used with `keyvault` and
`management` credential sections. AAD credentials can be optionally used
for `batch` credentials but are required for `batch` credentials when using
UserSubscription Batch accounts.

### Azure Active Directory: `aad`
The following is a description of `aad` properties that can be used within
each credential section. The `aad` property contains members for Azure Active
Directory credentials. Note that some options are mutually exclusive of each
other depending upon authentication type. The available authentication types
for Batch Shipyard with the required parameters for each are:
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
* (required) `directory_id` AAD directory (tenant) id
* (optional) `application_id` AAD application (client) id
* (optional) `auth_key` Service Principal authentication key
* (optional) `rsa_private_key_pem` path to RSA private key PEM file if using
Certificate-based authentication
* (optional) `x509_cert_sha1_thumbprint` thumbprint of the X.509
certificate for use with Certificate-based authentication
* (optional) `user` AAD username
* (optional) `password` AAD password associated with the user if using
username and password authentication. You can omit this property if you
want to resort to interactive multi-factor authentication.
* (optional) `endpoint` is the AAD endpoint for the associated resource
* (optional) `token_cache` defines token cache properties for multi-factor
  device code auth only. Tokens are not cached for other auth mechanisms.
  * (optional) `enabled` enables the token cache for device code auth
  * (optional) `filename` specifies the file path to cache the signed token

### KeyVault: `keyvault`
Please see the
[Azure KeyVault and Batch Shipyard Guide](74-batch-shipyard-azure-keyvault.md)
for more information.
* (optional) The `keyvault` property defines the required members for
accessing Azure KeyVault with Azure Active Directory credentials. Note that
this property is *mutually exclusive* of all other properties in this file.
If you need to define other members in this config file while using Azure
KeyVault, then you will need to use environment variables or cli parameters
instead for AAD and KeyVault credentials.
  * (optional) `uri` property defines the Azure KeyVault DNS name (URI).
  * (optional) `credentials_secret_id` property defines the KeyVault secret
    id containing an entire credentials.json file.
  * (required) `aad` AAD authentication parameters for KeyVault.

Please refer to the
[Azure KeyVault and Batch Shipyard guide](74-batch-shipyard-azure-keyvault.md)
for more information regarding `*_keyvault_secret_id` properties and how
they are used for credential management with Azure KeyVault.

### Management: `management`
* (optional) The `management` property defines the required members for
accessing Azure Resources (ARM) with Azure Active Directory credentials. This
is required with `fs` filesystem actions and pools that need to be created
with a virtual network specification (thus UserSubscription Batch accounts).
  * (required) `subscription_id` is the subscription id to interact with.
  * (required) `aad` AAD authentication parameters for ARM.

### Batch: `batch`
* (required) The `batch` property defines the Azure Batch account. Members
under the `batch` property can be found in the
[Azure Portal](https://portal.azure.com) under your Batch account.
  * (required) `account_service_url` is the Batch account service URL.
  * (required for UserSubscription Batch accounts, optional otherwise) `aad`
    defines the AAD authentication parameters for Azure Batch.
  * (required for UserSubscription Batch accounts, optional otherwise)
    `resource_group` is the resource group containing the Batch account.
  * (required unless `aad` is specified) `account_key` is the shared
    key. This is required for non-AAD logins. This option takes precendence
    over the `aad` property if specified.
  * (optional) `account_key_keyvault_secret_id` property can be used to
    reference an Azure KeyVault secret id. Batch Shipyard will contact the
    specified KeyVault and replace the `account_key` value as returned by
    Azure KeyVault. This cannot be used with UserSubscription Batch accounts.

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
    property in the `docker_registry`:`private` json object in the global
    configuration.
    * (optional) `username` username to log in to this registry
    * (optional) `password` password associated with this username
    * (optional) `password_keyvault_secret_id` property can be used to
      reference an Azure KeyVault secret id. Batch Shipyard will contact the
      specified KeyVault and replace the `password` value as returned by
      Azure KeyVault.

## Full template
A full template of a credentials file can be found
[here](../config\_templates/credentials.json). Note that this template cannot
be used as-is and must be modified to fit your scenario.
