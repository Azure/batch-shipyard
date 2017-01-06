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

### Azure Active Directory Setup
If you will use your login for accessing your Azure subscription (e.g., your
login to Azure Portal loads your subscription) as credentials to access your
KeyVault in your subscription, then you can skip this section and proceed
to the Azure KeyVault Setup below. If not, or if you prefer to use an Active
Directory Service Principal, then please continue following the directions
below.

#### Step 0: Get or Create a Directory
First, you will need to create a directory if you do not have any existing
directories (you should have a default directory) or if you are a user of a
directory that does not allow you to register an Application. You will need
to use the [Classic Azure Portal](https://manage.windowsazure.com/) to create
a directory.

#### Step 1: Retrieve the Directory ID
Retrieve the Directory ID of the Active Directory from the Azure Portal.
Click on `Azure Active Directory` on the left menu and then `Properties`. You
will see the `Directory ID` displayed on the next blade on the right.

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

Ensure that the Application Type is set as `Native`. The `Redirect URI` does
not have to exist, you can fill in anything you'd like here. Once completed,
hit the Create button at the bottom.

#### Step 3: Retrieve the Application ID
Retrieve the `Application ID` for the application you just registered by
refreshing the App registrations blade. You will see the `Application ID`
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
the key, the key `VALUE` will be displayed. Copy this value. This is the
argument to pass to the option `--aad-auth-key` or set as the environment
variable `SHIPYARD_AAD_AUTH_KEY`.

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

#### Step 1: Create KeyVault
In the Create Key Vault blade, fill in the `Name`, select the `Subscription`
to use, set the `Resource Group` and `Location` of the KeyVault to be created.

![74-akv-step1-0.png](https://azurebatchshipyard.blob.core.windows.net/github/74-akv-step1-0.png)

Then select `Access policies`. If you are using not using an Active Directory
Service Principal, then skip to the next step, but follow the instructions for
the specific Active Directory User. If you are using an Active Directory
Service Principal, then hit the `Add new` button, then `Select principal`. In
the next blade, type the name of the Application added in the prior section
to Active Directory. Select this application by clicking on it and the Select
button on the bottom of the blade.

#### Step 2: Set Secret Permissions
From the `Configure from template (optional)` pulldown, select either
`Key & Secret Management` or `Secret Management`, then hit OK.

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
You will need to provide *either* an AAD Service Principal or AAD
User/Password to authenticate for access to your KeyVault. These options
are mutually exclusive. For an AAD Service Principal, you would need to
provide the following options to your `shipyard` invocation:

```
--aad-directory-id <DIRECTORY-ID> --aad-application-id <APPLICATION-ID> --aad-auth-key <AUTH-KEY>
```

or as environment variables:

```
SHIPYARD_AAD_DIRECTORY_ID=<DIRECTORY-ID> SHIPYARD_AAD_APPLICATION_ID=<APPLICATION-ID> SHIPYARD_AAD_AUTH_KEY=<AUTH-KEY>
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

Additionally, you will need to provide the Azure KeyVault URI (i.e., the
DNS name of the KeyVault resource) as an option:

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
to `keyvault add`. For example:

```shell
# add the appropriate AAD and KeyVault URI options or environment variables
# to the below invocation
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
for latter invocations that require valid credentials to use Batch Shipyard.

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
keys, storage account keys, and private docker registry passwords. Please
see the [configuration guide](10-batch-shipyard-configuration.md) for more
information.

Finally, Batch Shipyard does support nested KeyVault secrets. In other words,
the `credentials.json` file can be a secret in KeyVault and there can be
`*_keyvault_secret_id` properties within the json file stored in KeyVault
which will then be fetched.

### Fetching Credentials from KeyVault
To specify a `credentials.json` as a secret in KeyVault, you can omit the
`--credentials` option (or specify a `--configdir` option without a
`credentials.json` file in the path pointed to by `--configdir`) and instead
specify the option:

```
--keyvault-credentials-secret-id <SECRET-ID>
```

or as an environment variable:
```
SHIPYARD_KEYVAULT_CREDENTIALS_SECRET_ID=<SECRET-ID>
```

If you have a physical `credentials.json` file on disk, but with
`*_keyvault_secret_id` properties then you do not need to specify the above
option as Batch Shipyard will parse the credentials file and perform
the lookup and secret retrieval.

## Configuration Documentation
Please see [this page](10-batch-shipyard-configuration.md) for a full
explanation of each configuration option.

## Usage Documentation
Please see [this page](20-batch-shipyard-usage.md) for a full
explanation of all commands and options for `shipyard`.
