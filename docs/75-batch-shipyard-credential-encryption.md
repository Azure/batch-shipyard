# Credential Encryption and Batch Shipyard
The focus of this article is to explain why, when and how to encrypt your
credentials used by the backend of the Batch Shipyard system for various
purposes. Please refer to the
[installation doc](01-batch-shipyard-installation.md) for information
regarding required software in order to use the credential encryption features
for Batch Shipyard.

## Azure Batch Service and Encryption
Azure Batch naturally must deal with potentially sensitive information that
customers submit for job scheduling, such as command lines for processes,
environment variables, and URLs for resource files. All of this information
is encrypted from the time it sent from the your submission machine or Portal
and stored in the Azure Batch service. All REST API calls are encrypted in
transit through HTTPS to the Azure Batch service endpoints. Any sensitive
information as described above is then encrypted. Encryption of this
information is maintained until it is needed, such as executing the task
which contains the command line to run.

If the Azure Batch service takes care of encrypting all of the sensitive
user information, then why does Batch Shipyard need to encrypt credentials?
The answer lies in if your scenario requires it. Because Batch Shipyard needs
credentials for some of its components to work, such as Azure Storage,
these credentials must be exposed to the compute node through environment
variables or command line arguments. As explained above due to the strict
encryption policies enforced by the Azure Batch service, these credentials
would never pose a risk to be exposed on their own, however, tools such
as the Azure Portal, Azure Batch Explorer, Azure CLI or Azure PowerShell
cmdlets can expose these credentials because command lines and environment
variables are decrypted by the Azure Batch service and sent over HTTPS
back to the user so that they may be viewable for status monitoring and
diagnosis. Again, there is no risk for exposure to other parties while
in-transit, however, they can be viewed once the data reaches the point of
display - be it the web browser displaying the Azure Portal or the Azure
Batch Explorer UI.

The question for you is, does this matter or not? Is there a risk of
credential leakage by means of these UI or command line display mechanisms?
If the answer is no, then no action needs to be taken. However, if you
believe that credentials may be exposed when displayed through the
aforementioned mechanisms, then please read on for steps to enable
credential encryption with Batch Shipyard.

## Credential Encryption
There are various places where credentials are passed from the user from
configuration input files to the compute nodes. By enabling credential
encryption, these strings are replaced with encrypted versions rendering
viewing of them inconsequential without the private key. The series of
actions that need to be taken in order to enable credential encryption are:

1. Create certificates and keys locally
2. Modify the global configuration file to reference these certificates
3. Add the certificate to your Batch account (optional)

For step 1, invoke the `createcert` command with `shipyard.py` which will
create the necessary certificates and keys. The end result should be two files
(the names of which you will be prompted for) created: (1) a PFX file for
use with the Azure Batch service and (2) an RSA public key PEM file for
use locally to encrypt.

For step 2, there is one json object that must be configured under
`batch_shipyard` in the global configuration file prior to taking any action:

```json
        "encryption" : {
            "enabled": true,
            "pfx": {
                "filename": "encrypt.pfx",
                "passphrase": "mysupersecretpassword",
                "sha1_thumbprint": "123456789..."
            },
            "public_key_pem": "encrypt.pem"
        }
```

Ensure that the `enabled` property is set to `true` and that the `pfx`
members are correctly populated. It is recommended to fill the
`public_key_pem` and `sha1_thumbprint` (which is output at the end of
`createcert`) members such that they do not need to be generated each
time encryption is required.

Step 3 is optional, but one may invoke `addcert` with `shipyard.py` to
add the certificate to the Batch account specified in the credentials json
file. If `encryption` is enabled, then this `addcert` action is automatically
invoked for every subsequent `addpool`.

## Encryption Details
System-installed `openssl` is used in all certificate, encryption and
decryption routines. RSA asymmetric encryption (instead of symmetric key
enveloping techniques) is used as the amount of data that needs to be
encrypted is small which keeps the process simple and understandable.

All applicable Azure Storage account keys, generated SAS keys, Docker login
passwords, and Azure Batch credentials are encrypted if credential encryption
is enabled.

## Configuration Documentation
Please see [this page](10-batch-shipyard-configuration.md) for a full
explanation of each credential encryption configuration option.
