# Batch Shipyard and Singularity Encrypted Containers
The focus of this article is to describe how the Singularity Encrypted
Container feature is integrated ito Batch Shipyard.

## Overview
[Singularity](https://sylabs.io/singularity/), as of version 3.4.0, provides
the ability to build and execute
[encrypted containers](https://sylabs.io/guides/3.4/user-guide/encryption.html).
Batch Shipyard simplifies executing encrypted Singularity containers by
leveraging built-in Batch support for certificates and automatically managing
the decryption keys for task execution.

### Mental Model
The process for creating an encrypted container and executing is modeled
below. The first step is to build a Singularity image with an encrypted
rootfs. Although Singularity supports both passphrase and asymmetric key
based encryption, Batch Shipyard only supports asymmetric key based
encryption. Next, you can optionally sign the image. When the container is
downloaded (pulled), the container signature is verified if it was signed.
When the container is run the associated private key is used to decrypt
the container to execute.

```
+---------------------+
|     RSA KeyPair     |
|                     |
| +-----------------+ |                                 +---------------------+
| |                 | |                                 |                     |
| | RSA Public Key  +---->  singularity build -e  +---->+ Encrypted Container |
| |                 | |                                 |        (SIF)        |
| +-----------------+ |                                 |                     |
|                     |                                 +----------+----------+    +-----------------+
| +-----------------+ |                                            |               |   GPG KeyPair   |
| |                 | |                                            |               |                 |
| | RSA Private Key | |         +------------------+               v               | +-------------+ |
| |                 | |         |                  |                               | |             | |
| +--------+--------+ |         | Signed Encrypted +<----+  singularity sign  <------+ Private Key | |
|          |          |         | Container (SIF)  |           (optional)          | |             | |
+---------------------+         |                  |                               | +-------------+ |
           |                    +--------+---------+                               |                 |
           |                             |                                         | +-------------+ |
           |                             v                                         | |             | |
           |                                                                       | | Public Key  | |
           |                      singularity push                                 | |             | |
           |                                                                       | +------+------+ |
           |                                                                       |        |        |
           |                                                                       +-----------------+
           |                                                  Verify Signature              |
           |                      singularity pull  <---------------------------------------+
           |                             +
           |                             |
           |                             v
           |  Decrypt
           +----------->  singularity run/exec --pem-path=...
                                        +
                                        |
                                        v

                       Verified Encrypted Container Execution
```

Batch Shipyard wraps up the complexity of managing the keys for decryption for
tasks with associated encrypted containers. For any encrypted container,
you can upload the RSA private key as a PFX certificate on your Batch
account. When you deploy a Batch pool with encrypted Singularity containers,
the matching certificates are automatically deployed to the Batch pool.
Batch tasks which execute an encrypted container are automatically matched
to the appropriate decryption certificate and executed on your behalf.

```
 +-----------------+           +-----------------------------------+        +----------------------+
 |                 |           |                                   |        |                      |
 | RSA Private Key |           |            Batch Task             |        | Sylabs Cloud or File |
 |                 |           |                                   |        |                      |
 +--------+--------+           | +-------------------------------+ |        |  +----------------+  |
          |                    | |                               | | Verify |  |                |  |
          | Convert            | | oras://.../encryptedimg:0.0.1 <-------------+ GPG Public Key |  |
          v                    | |                               | |        |  |                |  |
 +--------+--------+           | +----------------------------^--+ |        |  +----------------+  |
 |                 |           |                              |    |        |                      |
 | PFX Certificate |           +------+----------------------------+        +----------------------+
 |                 |                  ^                       |
 +--------+--------+                  | Execute               |
          |                           |                       |
          | Upload         +----------+----------+            | Decrypt
          v                |                     |            |
  +-------+-------+        |     Batch Pool      |            |
  |               | Deploy |                     |            |
  | Batch Account +--------> +-----------------+ |         +--+--------------+
  |               |        | |                 | |         |                 |
  +---------------+        | | PFX Certificate +-----------> RSA Private Key |
                           | |                 | | Convert |                 |
                           | +-----------------+ |         +-----------------+
                           |                     |
                           +---------------------+
```

## Simple End-to-End Walkthrough
The following will showcase a simple end-to-end walkthrough of building and
running a signed and encrypted container with Batch Shipyard.

#### Step 1: Create RSA Keypair
Batch Shipyard can create the RSA Keypair for encryption for you.

```shell
shipyard cert create --file-prefix mycert --pfx-password <password>
```

This will generate two files a PKCS8 Public Key PEM file and a password
protected PFX file (containing the RSA Keypair) for use with Azure Batch.

Singularity uses PKCS1 PEM RSA keys so in order to encrypt, we will convert
the public key:

```shell
openssl rsa -pubin -in mycert.pem -out rsapub.pem -RSAPublicKey_out
```

#### Step 2: Create GPG Keypair
In order to sign a container, you will need to create a GPG Keypair. If you
do not have an existing GPG Keypair, or would like to use a different
keypair, you will need to generate a new one:

```shell
# via GPG
gpg --full-generate-key

# or via Singularity
singularity key newpair
```

Follow the command input prompts to complete the key generation process.
If you created a key with GPG, then you will need to import the keypair
into Singularity's keyring. To do this, we need to export the GPG key and
then import:

```shell
gpg --armor --export-secret-keys <KeyId> > gpgpriv.asc
singularity key import gpgpriv.asc
rm gpgpriv.asc
```

#### Step 3: Publish Public GPG Key
If you wish to utilize Sylab's Public Keyserver, then you can push your
public Key so that container signed with this key are verified automatically.
To do this, perform the following:

```shell
singularity key push <KeyId>
```

Alternatively, you can associate signed container images with local public
keyfiles that you can upload as part of your Batch pool.

#### Step 4: Build Encrypted Container
Now you can build an encrypted container. For the example in this walkthrough
we will create an encrypted "lolcow" container. The following is the
def file for the image:

```
Bootstrap: library
From: debian:9

%post
apt-get update
apt-get install -y fortune cowsay lolcat
apt-get clean

%environment
export PATH=$PATH:/usr/games
export LC_ALL=C

%runscript
fortune | cowsay | lolcat
```

To build an encrypted container, we will specify the RSA public key in PKCS1
format during the build command:

```shell
# build the encrypted container image (requires root to build encrypted containers)
sudo singularity build -e --pem-path=rsapub.pem lolcow.sif lolcow.def

# verify encrypted rootfs
singularity sif list lolcow.sif
```

The `sif list` command will output something similar to the following:
```
ID   |GROUP   |LINK    |SIF POSITION (start-end)  |TYPE
------------------------------------------------------------------------------
1    |1       |NONE    |32768-32976               |Def.FILE
2    |1       |NONE    |36864-98193408            |FS (Encrypted squashfs/*System/amd64)
3    |1       |2       |98193408-98193808         |Cryptographic Message (PEM/RSA-OAEP)
```

Where you can observe the encrypted rootfs in ID 2 and 3.

#### Step 5: Sign Encrypted Container
Next we will sign the encrypted container with our GPG public key. This is
done with the following command:

```shell
# First determine the Key index of the private key to use to sign
singularity key list -s

# Using the key index, sign the image
singularity sign -k <KeyIndex> lolcow.sif

# verify the signature
singularity sif list lolcow.sif
```

The `sif list` command will output something similar to the following:
```
ID   |GROUP   |LINK    |SIF POSITION (start-end)  |TYPE
------------------------------------------------------------------------------
1    |1       |NONE    |32768-32976               |Def.FILE
2    |1       |NONE    |36864-98193408            |FS (Encrypted squashfs/*System/amd64)
3    |1       |2       |98193408-98193808         |Cryptographic Message (PEM/RSA-OAEP)
4    |1       |2       |98197504-98198459         |Signature (SHA384)
```

Where you can observe the signature in ID 4.

#### Step 6: Push Signed Encrypted Container to Registry
Now we can push the image to a compliant registry. You can push this to either
Sylabs cloud or an ORAS compliant registry such as Azure Container Registry:

```shell
singularity push --docker-username=... --docker-password=... lolcow.sif oras://<user>.azurecr.io/repo/lolcow:0.0.1
```

#### Step 7: Associate Certificate with Batch Account
Now we will need to associate the RSA private key (via PFX created in Step 1)
with our Batch account. Batch Shipyard will use this certificate to
automatically associate the decryption key with the encrypted images.

```shell
shipyard cert add --file mycert.pfx --pfx-password <password>
# pfx is not strictly needed anymore and can be removed, however, ensure that
# the associated RSA public key is kept for future encryption needs
rm mycert.pfx
```

This command will print important information about the certificate that you
will need later, for example:

```
2019-11-11 18:49:47.343 INFO - added pfx cert with thumbprint d1cb1fc03d027e843e54a4db3dc7d4b10c120982 to account myaccount
```

The SHA1 thumbprint will be used in the next step.

#### Step 8: Configure Batch Pool
Encrypted Singularity images are referenced in the `global_resources` section
of the global configuration (typically `config.yaml`) file. The following is
an example:

```yaml
# ... other config

global_resources:
  singularity_images:
    signed:
      - image: oras://<user>.azurecr.io/repo/lolcow:0.0.1
        signing_key:
          fingerprint: 000123000123000123000123000123000123ABCD
        encryption:
          certificate:
            sha1_thumbprint: d1cb1fc03d027e843e54a4db3dc7d4b10c120982

```

The `signing_key` `fingerprint` property is the `KeyId` of the GPG key used
to sign the image. If you have uploaded the signing key to Sylabs Cloud, then
the image will be automatically verified upon pulling the image. Notice
that the `sha1_thumbprint` specified matches the thumbprint output in the
prior step.

#### Step 9: Execute Batch Task with Encrypted Singularity Image
There are no special steps or configuration needed in the jobs configuration
(typically `jobs.yaml`) to execute encrypted Singularity images. Batch
Shipyard will automatically feed the proper key to the executing task to
enable the container to be decrypted and run. Notice that the command
does not need to be run in elevated mode for proper functionality
including decryption.

```yaml
job_specifications:
- id: encrypted
  tasks:
  - singularity_image: oras://<user>.azurecr.io/repo/lolcow:0.0.1
    singularity_execution:
      cmd: run
```

Executing this sample jobs configuration on a pool with the
`singularity_images` specified from Step 8:

```shell
> shipyard jobs add --tail stdout.txt
2019-11-11 20:48:37.642 INFO - Adding job encrypted to pool mypool
2019-11-11 20:48:38.103 DEBUG - constructing 1 task specifications for submission to job encrypted
2019-11-11 20:48:38.571 DEBUG - submitting 1 task specifications to job encrypted
2019-11-11 20:48:38.571 DEBUG - submitting 1 tasks (0 -> 0) to job encrypted
2019-11-11 20:48:39.670 INFO - submitted all 1 tasks to job encrypted
2019-11-11 20:48:39.670 DEBUG - attempting to stream file stdout.txt from job=encrypted task=task-00000
 _______________________________________
/ Delay not, Caesar. Read it instantly. \
|                                       |
| -- Shakespeare, "Julius Caesar" 3,1   |
|                                       |
| Here is a letter, read it at your     |
| leisure.                              |
|                                       |
| -- Shakespeare, "Merchant of Venice"  |
| 5,1                                   |
|                                       |
| [Quoted in "VMS Internals and Data    |
| Structures", V4.4, when               |
|                                       |
\ referring to I/O system services.]    /
 ---------------------------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
```

