#!/usr/bin/env bash

set -e
set -o pipefail

TPNFILE=../THIRD_PARTY_NOTICES.txt

DEPENDENCIES=(
    adal
    https://github.com/AzureAD/azure-activedirectory-library-for-python
    https://github.com/AzureAD/azure-activedirectory-library-for-python/raw/master/LICENSE
    azure-cosmos-table-python
    https://github.com/Azure/azure-cosmos-table-python
    https://raw.githubusercontent.com/Azure/azure-cosmos-table-python/master/LICENSE.txt
    azure-sdk-for-python
    https://github.com/Azure/azure-sdk-for-python
    https://github.com/Azure/azure-sdk-for-python/raw/master/LICENSE.txt
    azure-storage-python
    https://github.com/Azure/azure-storage-python
    https://github.com/Azure/azure-storage-python/raw/master/LICENSE.txt
    blobxfer
    https://github.com/Azure/blobxfer
    https://github.com/Azure/blobxfer/raw/master/LICENSE
    boost
    http://boost.org
    https://github.com/boostorg/boost/raw/master/LICENSE_1_0.txt
    click
    https://github.com/pallets/click
    https://github.com/pallets/click/raw/master/LICENSE.rst
    msrest
    https://github.com/Azure/msrest-for-python
    https://github.com/Azure/msrest-for-python/raw/master/LICENSE.md
    msrestazure
    https://github.com/Azure/msrestazure-for-python
    https://github.com/Azure/msrestazure-for-python/raw/master/LICENSE.md
    pykwalify
    https://github.com/Grokzen/pykwalify
    https://github.com/Grokzen/pykwalify/raw/master/docs/License.txt
    Python
    https://python.org
    https://github.com/python/cpython/raw/master/LICENSE
    python-dateutil
    https://github.com/dateutil/dateutil
    https://github.com/dateutil/dateutil/raw/master/LICENSE
    requests
    https://github.com/requests/requests
    https://github.com/requests/requests/raw/master/LICENSE
    ruamel.yaml
    https://sourceforge.net/p/ruamel-yaml/code/ci/default/tree/
    "https://sourceforge.net/p/ruamel-yaml/code/ci/default/tree/LICENSE?format=raw"
    singularity
    https://github.com/hpcng/singularity
    https://github.com/hpcng/singularity/raw/master/LICENSE.md
)
DEPLEN=${#DEPENDENCIES[@]}

add_attribution() {
    name=$1
    url=$2
    license=$(curl -fSsL "$3")

    { echo ""; echo "-------------------------------------------------------------------------------"; \
      echo ""; echo "$name ($url)"; echo ""; echo "$license"; } >> $TPNFILE
}

cat << 'EOF' > $TPNFILE
Do Not Translate or Localize

This product incorporates copyrighted material from the open source projects
listed below (Third Party IP). The license terms of Microsoft Corporation's
product do not apply to the Third Party IP which is licensed to you under its
original license terms which are provided below. Microsoft reserves all rights
not expressly granted herein, whether by implication, estoppel or otherwise.
You may find a copy of the Corresponding Source code, if and as required under
the Third Party IP License, at http://3rdpartysource.microsoft.com. You may
also obtain a copy of the source code for a period of three years after our
last shipment of this product, if and as required under the Third Party IP
license, by sending a check or money order for US$5.00 to:

Source Code Compliance Team
Microsoft Corporation
One Microsoft Way
Redmond, WA 98052 USA

Please write "source for [Third Party IP]" in the memo line of your payment.
EOF

echo -n "Generating $((DEPLEN / 3)) attributions: ["
i=0
while [ $i -lt "$DEPLEN" ]; do
    add_attribution "${DEPENDENCIES[$i]}" "${DEPENDENCIES[$((i+1))]}" "${DEPENDENCIES[$((i+2))]}"
    i=$((i + 3))
    echo -n "."
done
{ echo ""; echo "-------------------------------------------------------------------------------"; } >> $TPNFILE
echo "] done."
