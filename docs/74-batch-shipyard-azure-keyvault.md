# Using Azure KeyVault for Credentials with Batch Shipyard
The focus of this article is to explain how to use Azure KeyVault for
managing credentials json files and/or individual keys and passwords for use
with Batch Shipyard.

## Introduction and Concepts
The [credentials.json](10-batch-shipyard-configuration.md#cred) file
contains access keys and passwords for various resources, including
Azure Batch, Azure Storage and Docker Private Registries. This file should
be secured using proper file mode permissions or ACLs. However, it may be
more appropriate to host these credentials or even the entire json file itself
in a repository with secure, controlled access. There are benefits to this
approach such as securing keys without a physical file, centralized repository
of secrets, etc.

[Azure KeyVault](https://azure.microsoft.com/en-us/services/key-vault/) is
a managed service that handles storing sensitive information such as keys
and secrets in a secure manner. Batch Shipyard can interact with provisioned
Key Vaults to store and retrieve credentials required for Batch Shipyard to
operate. Azure KeyVault broadly manages three different types of objects:
keys, arbitrary data (secrets), and certificates. For credential management
with regard to Batch Shipyard, only secret objects are utilized.

Additionally, Azure KeyVault requires valid Azure Active Directory
(AAD) credentials to manage and access data in a KeyVault. This complicates
setup, but is necessary for proper Role-Based Access Control (RBAC) which
is useful for managing sensitive data such as secrets.

## Setup
The following setup sections will guide you through setting up Azure
Active Directory and KeyVault for use with Batch Shipyard.

### Azure Active Directory Setup with Service Principal Key-based Authentication
If you will use your login for accessing your Azure subscription (e.g., your
login to Azure Portal loads your subscription) as credentials to access your
KeyVault in your subscription, then you can skip this section and proceed
to the Azure KeyVault Setup below. If not, or if you prefer to use an Active
Directory Service Principal, then please continue following the directions
below.

If you prefer to use asymmetric X.509 certificate-based authentication, then
please see the next section. You can also augment the Key-based Authentication
with Certificate authentication by following the Certificate guide immediately
after the Key-based authentication guide.

#### Step 0: Get or Create a Directory
First, you will need to create a directory if you do not have any existing
directories (you should have a default directory) or if you are a user of a
directory that does not allow you to register an Application. You will need
to use the [Classic Azure Portal](https://manage.windowsazure.com/) to create
a directory, however, it is recommended to use the default directory that
is associated with your subscription if possible.

#### Step 1: Retrieve the Directory ID
Retrieve the Directory ID of the Active Directory from the
[Azure Portal](https://portal.azure.com). Click on `Azure Active Directory`
on the left menu and then `Properties`. You will see the `Directory ID`
displayed on the next blade on the right.

![74-aad-step1-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-aad-step1-0.png)

Click the copy button (or highlight the ID and copy the text). This is the
argument to pass to the option `--aad-directory-id` or set as the environment
variable `SHIPYARD_AAD_DIRECTORY_ID`.

If you are retrieving this information from the Classic Azure Portal, then
the `Directory ID` is referred to as the `Tenant ID`.

#### Step 2: Register an Application
Next we will need to register an application to use with AAD. Under the
Azure Active Directory blade, click on `App registrations`. Then click on the
`Add` button at the top of the next blade. Finally fill in the fields for
the Create blade.

![74-aad-step2-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-aad-step2-0.png)

Ensure that the Application Type is set as `Web app / API`. The `Redirect URI`
does not have to exist, you can fill in anything you'd like here. Once
completed, hit the `Create` button at the bottom.

#### Step 3: Retrieve the Application ID
Retrieve the `Application ID` for the application you just registered by
refreshing the `App registrations` blade. You will see the `Application ID`
on the top right of the blade.

![74-aad-step3-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-aad-step3-0.png)

Copy the `Application ID`. This is the argument to pass to the option
`--aad-application-id` or set as the environment variable
`SHIPYARD_AAD_APPLICATION_ID`.

If you are retrieving this information from the Classic Azure Portal, then
the `Application ID` is referred to as the `Client ID`.

#### Step 4: Add an Authentication Key
While on the Application blade, to the right you should see the Settings
blade (if not, click the `All settings ->` button). Click on `Keys` under
`API ACCESS` to add an authentication key.

![74-aad-step4-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-aad-step4-0.png)

Add a description for the key and select an appropriate expiration interval.
Click on the `Save` button at the top left of the blade. After you save
the key, the key `VALUE` will be displayed. Copy this value and ensure this
value is stored somewhere safe. This is the argument to pass to the option
`--aad-auth-key` or set as the environment variable `SHIPYARD_AAD_AUTH_KEY`.
Once you navigate away from this blade, the value of the key cannot be
retrieved again.

### Azure Active Directory Setup with Service Principal Certificate-based Authentication
The following describes how to set up Azure Active Directory with asymmetric
X.509 certificate-based authentication. You will need either
[Azure CLI](https://docs.microsoft.com/en-us/azure/xplat-cli-install) or
[Azure CLI 2.0](https://docs.microsoft.com/en-us/cli/azure/install-az-cli2)
to perform the actions in this section. Other tools such as Azure PowerShell
can also be used with the analogs found in the Azure PowerShell cmdlets.

#### Step 0: Login to Azure subscription and get Directory ID
Log in to your Azure subscription with Azure CLI:

```shell
# Azure CLI
azure login
azure account set "<subscription name or id>"
# Azure CLI 2.0
az login
az account set --subscription "<subscription name or id>"
```

If using Azure CLI, ensure that `azure` is running in ARM mode.
Azure CLI 2.0 only operates in ARM mode.

Retrieve the Directory ID with the following command:

```shell
# Azure CLI
azure account show
# Azure CLI 2.0
az account show
```

You will see a line starting with `Tenant ID` (Azure CLI) or a json with
a property of `tenantId` (Azure CLI 2.0). This is the Directory ID. This is
the argument to pass to the option `--aad-directory-id` or set as the
environment variable `SHIPYARD_AAD_DIRECTORY_ID`.

#### Step 1: Create X.509 Certificate with Asymmetric Keys
Execute the following `openssl` command, replacing the `-days` and
`-subj` parameters with the appropriate values:

```shell
openssl req -x509 -days 3650 -newkey rsa:2048 -out cert.pem -nodes -subj '/CN=mykeyvault'
```

This command will create two files: `cert.pem` and `privkey.pem`. The
`cert.pem` file contains the X.509 certificate with public key. This
certificate will be attached to the Active Directory Application.

The `privkey.pem` file contains the RSA private key that will be used to
authenticate with Azure Active Directory for the Service Principal. This
file path is the argument to pass to the option `--aad-cert-private-key` or
set as the environment variable `SHIPYARD_AAD_CERT_PRIVATE_KEY`.

You will also need to get the SHA1 thumbprint of the certificate created.
This can be done with the following command:

```shell
openssl x509 -in cert.pem -fingerprint -noout | sed 's/SHA1 Fingerprint=//g' | sed 's/://g'
```

This value output is the argument to pass to the option
`--aad-cert-thumbprint` or set as the environment variable
`SHIPYARD_AAD_CERT_THUMBPRINT`.

#### Step 2: Create an Active Directory Application and Service Principal with Certificate
Execute the following command to create the AAD application and Service
Principal together with the Certificate data, replacing the `-n` or
`--display-name` value depending upon the CLI used with the name of the
application as desired. If using Azure CLI 2.0, there are additional
parameters to be modified, including `--homepage` and `--identifier-uris`.

```shell
# Azure CLI
azure ad sp create -n mykeyvault --cert-value "$(tail -n+2 cert.pem | head -n-1 | tr -d '\n')"
# Azure CLI 2.0, this will only create the Application. Follow the
# Service Principal creation steps next.
az ad app create --display-name mykeyvault --homepage http://mykeyvault --identifier-uris http://mykeyvault --key-type AsymmetricX509Cert --key-value "$(tail -n+2 cert.pem | head -n-1 | tr -d '\n')"
```

You can specify an optional `--end-date` parameter to change the validity
period of the certificate for both Azure CLI and Azure CLI 2.0.

This action will output something similar to the following if using Azure CLI:
```
data:    Object Id:               abcdef01-2345-6789-abcd-ef0123456789
data:    Display Name:            mykeyvault
data:    Service Principal Names:
data:                             01234567-89ab-cdef-0123-456789abcdef
data:                             http://mykeyvault
```

or, if using Azure CLI 2.0 the output will be similar to the following:

```json
{
  "appId": "01234567-89ab-cdef-0123-456789abcdef",
  "appPermissions": null,
  "availableToOtherTenants": false,
  "displayName": "mykeyvault",
  "homepage": "http://mykeyvault",
  "identifierUris": [
    "http://mykeyvault"
  ],
  "objectId": "abcdef01-2345-6789-abcd-ef0123456789",
  "objectType": "Application",
  "replyUrls": []
}
```

Note the ID under `Service Principal Names:` (Azure CLI) or
`appId` (Azure CLI 2.0). This is the Application ID. This is the argument
to pass to the option `--aad-application-id` or set as the environment
variable `SHIPYARD_AAD_APPLICATION_ID`.

If using Azure CLI 2.0, we will need to create a Service Principal
for the Application since it is not created together in the prior command.
For the `--id` parameter, you can use either the `appId` or the `objectId`
found in the prior json output:

```shell
# Azure CLI 2.0 only
az ad sp create --id abcdef01-2345-6789-abcd-ef0123456789
```

You will see some json output where under `servicePrincipalNames`, you
should see the `appId` in addition to the uri similar to the following:

```json
{
  "appId": "01234567-89ab-cdef-0123-456789abcdef",
  "displayName": "mykeyvault",
  "objectId": "abcdef01-2345-6789-abcd-ef0123456789",
  "objectType": "ServicePrincipal",
  "servicePrincipalNames": [
    "01234567-89ab-cdef-0123-456789abcdef",
    "http://mykeyvault"
  ]
}
```

Take note of this `objectId` returned (which is different than the
Application objectId prior), as this will be used in the next step.

#### Step 3: Create a Role for the Service Principal
Execute the following command to create a role for the service principal.
You will need the `Object Id` (Azure CLI) or `objectId` (Azure CLI 2.0 with
`az ad sp create` command) as displayed in the previous step for use with
the parameter `--objectId` with Azure CLI or `--assignee` with Azure CLI 2.0.
Replace the `-o` (Azure CLI) or `--role` (Azure CLI 2.0) role name with one
of `Owner`, `Contributor`, or `Reader` (if this Service Principal will only
read from KeyVault). You will also need to scope your assignment using
your subscription and any resource providers to reduce permission scope
(if you wish) with the `-c` (Azure CLI) or `--scope` (Azure CLI 2.0)
parameter.

```shell
# Azure CLI
azure role assignment create --objectId abcdef01-2345-6789-abcd-ef0123456789 -o Contributor -c /subscriptions/11111111-2222-3333-4444-555555555555/
# Azure CLI 2.0
az role assignment create --assignee abcdef01-2345-6789-abcd-ef0123456789 --role Contributor --scope /subscriptions/11111111-2222-3333-4444-555555555555/
```

You should receive a message output that the role assignment has been
completed successfully in Azure CLI or a json blob for Azure CLI 2.0.

You can now assign this Service Principal with Certificate-based
authentication to an Azure KeyVault as per instructions below.

#### [Optional] Set Certificate Data for Existing Service Principal
If you followed the prior section for creating a Service Principal with
Key-based authentication, you can augment the Service Principal with
Certificate-based authentication by executing the following command,
replacing the `-o` (Azure CLI) or `--id` (Azure CLI 2.0) parameter with the
Object Id of the AAD Application:

```shell
# Azure CLI
azure ad app set -o abcdef01-2345-6789-abcd-ef0123456789 --cert-value "$(tail -n+2 cert.pem | head -n-1 | tr -d '\n')"
# Azure CLI 2.0
az ad app update --id abcdef01-2345-6789-abcd-ef0123456789 --key-type AsymmetricX509Cert --key-value "$(tail -n+2 cert.pem | head -n-1 | tr -d '\n')"
```

You can specify an optional `--end-date` parameter to change the validity
period of the certificate for both Azure CLI and Azure CLI 2.0.

### Azure KeyVault Setup
The following describes how to set up a new KeyVault for use with Batch
Shipyard.

#### Step 0: Add a KeyVault
First we need to add a new KeyVault to our subscription. In the Azure Portal,
click on `More services >` on the left menu and type `key` in the search box.
This should bring up a service `Key vaults`. Click on `Key vaults` (you can
also optionally favorite this item so it shows up in your left menu by
default).

![74-akv-step0-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-akv-step0-0.png)

Begin creating a KeyVault by clicking the `Add` button on the top left in
the blade that follows.

![74-akv-step0-1.png](https://azurebatchshipyard.blob.core.windows.net/github/74-akv-step0-1.png)

#### Step 1: Create the KeyVault
In the Create Key Vault blade, fill in the `Name`, select the `Subscription`
to use, set the `Resource Group` and `Location` of the KeyVault to be created.

![74-akv-step1-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-akv-step1-0.png)

Then select `Access policies`. If you are using not using an Active Directory
Service Principal, then skip to the next step, but follow the instructions for
the specific Active Directory User. If you are using an Active Directory
Service Principal, then hit the `Add new` button, then `Select principal`. In
the next blade, type the name of the Application added in the prior section
to Active Directory. Select this application by clicking on it and the
`Select` button on the bottom of the blade.

#### Step 2: Set Secret Permissions
From the `Configure from template (optional)` pulldown, select either
`Key & Secret Management` or `Secret Management`, then click the `OK` button.

![74-akv-step2-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-akv-step2-0.png)

Finally, hit the Create button on the Create Key Vault blade to create your
KeyVault.

#### Step 3: Retrieve KeyVault DNS Name
After you receive notification that the KeyVault has been created, navigate
to the KeyVault and select `Properties` under `SETTINGS`. The `DNS NAME`
will be displayed for the KeyVault.

![74-akv-step3-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-akv-step3-0.png)

Copy the `DNS NAME`. This is the argument to pass to the option
`--keyvault-uri` or set as the environment variable `SHIPYARD_KEYVAULT_URI`.

## Interacting with Batch Shipyard with AAD and Azure KeyVault
Once all of the setup steps have been completed, you can now begin interacting
with Batch Shipyard with Azure KeyVault using Azure Active Directory
credentials.

### Authenticating with AAD and Azure KeyVault
You will need to provide one of the following:

1. an AAD Service Principal with an authentication key
2. an AAD Service Principal with a RSA private key and X.509 certificate
thumbprint
3. an AAD User/Password

in order to authenticate for access to your KeyVault. These options
are mutually exclusive. In addition to one of these authentication options,
you must provide the KeyVault URI as a parameter.

You can either provide the required parameters through CLI options,
environment variables, or the `credentials.json` file.

Please see the [configuration guide](10-batch-shipyard-configuration.md) for
the appropriate json properties to populate that correlate with the following
options below. Note that the `keyvault add` command must use a
`credentials.json` file that does not have KeyVault and AAD credentials.
For this command, you will need to use CLI options or environment variables.

For an AAD Service Principal with Key-based authentication, you will need
to provide the following options to your `shipyard` invocation:

```
--aad-directory-id <DIRECTORY-ID> --aad-application-id <APPLICATION-ID> --aad-auth-key <AUTH-KEY>
```

or as environment variables:

```
SHIPYARD_AAD_DIRECTORY_ID=<DIRECTORY-ID> SHIPYARD_AAD_APPLICATION_ID=<APPLICATION-ID> SHIPYARD_AAD_AUTH_KEY=<AUTH-KEY>
```

For an AAD Service Principal with Certificate-based authentication, you will
need to provide the following options to your `shipyard` invocation:

```
--aad-directory-id <DIRECTORY-ID> --aad-application-id <APPLICATION-ID> --aad-cert-private-key <RSA-PRIVATE-KEY-FILE> --aad-cert-thumbprint <CERT-SHA1-THUMBPRINT>
```

or as environment variables:

```
SHIPYARD_AAD_DIRECTORY_ID=<DIRECTORY-ID> SHIPYARD_AAD_APPLICATION_ID=<APPLICATION-ID> SHIPYARD_AAD_CERT_PRIVATE_KEY=<RSA-PRIVATE-KEY-FILE> SHIPYARD_AAD_CERT_THUMBPRINT=<CERT-SHA1-THUMBPRINT>
```

To retrieve the SHA1 thumbprint for the X.509 certificate (not the RSA
private key) associated with your Service Principal, you can run the
following `openssl` command against your certificate file:

```shell
openssl x509 -in cert.pem -fingerprint -noout | sed 's/SHA1 Fingerprint=//g' | sed 's/://g'
```

To use an AAD User/Password to authenticate for access to your KeyVault, you
would need to add the following options to your `shipyard` invocation.

```
--aad-user <USER> --aad-password <PASSWORD>
```

or as environment variables:

```
SHIPYARD_AAD_USER=<USER> SHIPYARD_AAD_PASSWORD=<PASSWORD>
```

Finally, regardless of which authentication mechanism you have set up, you
will need to provide the Azure KeyVault URI (i.e., the DNS name of the
KeyVault resource) as an option:

```
--keyvault-uri <DNS-NAME>
```

or as an environment variable:

```
SHIPYARD_KEYVAULT_URI=<DNS-NAME>
```

### Storing Credentials in KeyVault
You can manually create a secret in your KeyVault using Azure Portal, but
it is recommended to use the Batch Shipyard CLI to store your
`credentials.json` file. This ensures that the file is stored properly
and can allow for potentially very large credential files as compression
is applied to the file prior to placing the secret in KeyVault. To create
a credentials secret, pass all of the required AAD and KeyVault URI options
to `keyvault add`. Note that you cannot use AAD/KeyVault credential options
in a `credentials.json` file to authenticate with KeyVault to store the
same json file. You must use CLI options or environment variables to pass
the appropriate Azure Keyvault and AAD credentials to `shipyard` for this
command. For example:

```shell
# add the appropriate AAD and KeyVault URI options or environment variables
# to the below invocation. These AAD/KeyVault authentication options cannot
# be present in credentials.json.
shipyard keyvault add mycreds --credentials credentials.json
```

Would create a secret named `mycreds` in the Azure KeyVault as specified
by the `--keyvault-uri` option. The value of the secret would be the
contents of the `credentials.json` file. You should see console output
similar to the following:

```
2017-01-06 07:44:13,885Z DEBUG convoy.keyvault:store_credentials_json:154 storing secret in keyvault https://myvault.vault.azure.net/ with name mycreds
2017-01-06 07:44:14,201Z INFO convoy.keyvault:store_credentials_json:161 keyvault secret id for name mycreds: https://myvault.vault.azure.net/secrets/mycreds
```

It is important to note the secret id output in the final line:

```
https://myvault.vault.azure.net/secrets/mycreds
```

This secret id is required for retrieving your `credentials.json` contents
for later invocations that require these particular credentials to interact
with Batch Shipyard. How to pass this secret id will be explained in the next
section.

You can also store individual keys as secrets in your KeyVault and reference
them within your `credentials.json` file. For example:

```json
        "batch": {
            "account": "myaccount",
            "account_key_keyvault_secret_id": "https://myvault.vault.azure.net/secrets/batchkey",
            "account_service_url": "myserviceurl"
        },
```

This excerpt of the credentials.json file does not have a valid `account_key`
property. However, instead there is a property `account_key_keyvault_secret_id`
which points to a KeyVault secret id. Batch Shipyard will attempt to fetch
this secret from KeyVault using the provided AAD credentials passed as
options to the invocation and then populate the `account_key` property from
the value of the secret.

These `*_keyvault_secret_id` properties can be used in lieu of batch account
keys, storage account keys, and private Docker Registry passwords. You will
need to populate the associated KeyVault with these secrets manually and
set the json properties in the `credentials.json` file with the corresponding
secret ids. Please see the
[configuration guide](10-batch-shipyard-configuration.md) for more
information.

Finally, Batch Shipyard does support nested KeyVault secrets. In other words,
the `credentials.json` file can be a secret in KeyVault and there can be
`*_keyvault_secret_id` properties within the json file stored in KeyVault
which subsequently will be fetched automatically.

### Fetching Credentials from KeyVault
To specify a `credentials.json` as a secret in KeyVault, you can omit the
`--credentials` option (or specify a `--configdir` option without a
`credentials.json` file on disk in the path pointed to by `--configdir`) and
instead specify the option:

```
--keyvault-credentials-secret-id <SECRET-ID>
```

or as an environment variable:
```
SHIPYARD_KEYVAULT_CREDENTIALS_SECRET_ID=<SECRET-ID>
```

If you have a physical `credentials.json` file on disk, but with
`*_keyvault_secret_id` properties then you must not specify the above
option as Batch Shipyard will parse the credentials file and perform
the lookup and secret retrieval automatically.

## More Documentation
You can perform many Azure Active Directory setup steps through the Azure CLI.
This [document](https://docs.microsoft.com/en-us/azure/azure-resource-manager/resource-group-authenticate-service-principal-cli)
explains how to create a Service Principal among other topics. To create
an Azure KeyVault with the Azure CLI, this
[document](https://docs.microsoft.com/en-us/azure/key-vault/key-vault-manage-with-cli#register-an-application-with-azure-active-directory)
explains the steps involved. Additionally, it shows how to authorize an AAD
Application for use with KeyVault.

Securing your KeyVault can be handled through the Azure Portal or through
the Azure CLI. This
[document](https://docs.microsoft.com/en-us/azure/key-vault/key-vault-secure-your-key-vault)
explains concepts and how to secure your KeyVault. A general overview of
Role-Based Access Control (RBAC) and how to manage access to various
resources can be found in this
[document](https://docs.microsoft.com/en-us/azure/active-directory/role-based-access-control-what-is).

For further Batch Shipyard documentation, please see
[this page](10-batch-shipyard-configuration.md) for a full
explanation of each property in the configuration files. Please see
[this page](20-batch-shipyard-usage.md) for a full
explanation of all commands and options for `shipyard`.
