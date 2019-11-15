# Packer Scripts for Custom Images on Batch Shipyard
If you are downloading these scripts directly from the web (and not via a
git cloned repository), then please ensure that the scripts have not been
mangled with incompatible line endings and all scripts have the executable
bit set.

Each directory may have one or more of the following:

* `build.json` or `build-sig.json` files create images directly into Shared Image Galleries
* `build-mi.json` files create Azure Managed Images (deprecated)
* `build-vhd.json` files create VHD page blobs (deprecated)
