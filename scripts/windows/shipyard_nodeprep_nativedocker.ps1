param(
	[switch] $a,  # mount azurefile shares
	[String] $e,  # encrypted sha1 cert
	[switch] $u,  # custom image
	[String] $v,  # batch-shipyard version
	[String] $x   # blobxfer version
)

Set-Variable NodePrepFinished -option Constant -value (Join-Path $env:AZ_BATCH_NODE_SHARED_DIR -ChildPath ".nodeprepfinished")
Set-Variable MountsPath -option Constant -value (Join-Path $env:AZ_BATCH_NODE_ROOT_DIR -ChildPath "mounts")

function Exec
{
    [CmdletBinding()]
    param (
        [Parameter(Position=0, Mandatory=1)]
        [scriptblock]$Command,
        [Parameter(Position=1, Mandatory=0)]
        [string]$ErrorMessage = "Execution of command failed.`n$Command"
    )
    & $Command
    if ($LastExitCode -ne 0) {
        throw "Exec: $ErrorMessage"
    }
}

Write-Host "Configuration [Native Docker, Windows]:"
Write-Host "---------------------------------------"
Write-Host "Batch Shipyard version: $v"
Write-Host "Blobxfer version: $x"
Write-Host "Mounts path: $MountsPath"
Write-Host "Custom image: $u"
Write-Host "Encrypted: $e"
Write-Host "Azure File: $a"
Write-Host ""

# check for docker
Exec { docker version --format '{{.Server.Version}}' }

# mount azure file shares
if ($a) {
	Write-Host "Mounting file shares"
	New-Item $MountsPath -type directory -force
	.\azurefile-mount.cmd
}

if (Test-Path $NodePrepFinished -pathType Leaf)
{
	Write-Host "$NodePrepFinished file exists, assuming successful completion of node prep"
	exit 0
}

# download blobxfer binary
$bxurl = "https://github.com/Azure/blobxfer/releases/download/${x}/blobxfer-${x}-win-amd64.exe"
$bxoutf = Join-Path $Env:AZ_BATCH_TASK_WORKING_DIR -ChildPath "blobxfer.exe"
Write-Host "Downloading blobxfer $x binary as $bxoutf"
Invoke-WebRequest -Uri $bxurl -OutFile $bxoutf
if (!$?)
{
	Write-Error "Download from $bxurl to $bxoutf failed"
	exit 1
}

# pull required images
Exec { docker pull alfpark/batch-shipyard:${v}-cargo-windows }

# touch node prep finished file
New-Item -ItemType file $NodePrepFinished -Force
