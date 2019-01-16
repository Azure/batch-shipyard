param(
	[switch] $a,  # mount azurefile shares
	[String] $e,  # encrypted sha1 cert
	[switch] $q,  # batch insights
	[switch] $u,  # custom image
	[String] $v,  # batch-shipyard version
	[String] $x   # blobxfer version
)

Set-Variable NodePrepFinished -option Constant -value (Join-Path $env:AZ_BATCH_NODE_ROOT_DIR -ChildPath "volatile" | Join-Path -ChildPath ".batch_shipyard_node_prep_finished")
Set-Variable VolatileStartupSave -option Constant -value (Join-Path $env:AZ_BATCH_NODE_ROOT_DIR -ChildPath "volatile" | Join-Path -ChildPath "startup" | Join-Path -ChildPath ".save")
Set-Variable MountsPath -option Constant -value (Join-Path $env:AZ_BATCH_NODE_ROOT_DIR -ChildPath "mounts")

# Enable TLS > 1.0
$security_protcols = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::SystemDefault
if ([Net.SecurityProtocolType].GetMember("Tls11").Count -gt 0) {
    $security_protcols = $security_protcols -bor [Net.SecurityProtocolType]::Tls11
}
if ([Net.SecurityProtocolType].GetMember("Tls12").Count -gt 0) {
    $security_protcols = $security_protcols -bor [Net.SecurityProtocolType]::Tls12
}
[Net.ServicePointManager]::SecurityProtocol = $security_protcols

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

# touch volatile startup save file
New-Item -ItemType file $VolatileStartupSave -Force

# check for docker
Exec { docker info }

# start batch insights
if ($q) {
    Write-Host "Enabling Batch Insights"
    $bi = Join-Path $Env:AZ_BATCH_TASK_WORKING_DIR -ChildPath "batch-insights.exe"
    $biapp = "batchappinsights"
    # remove scheduled task if it exists
    $exists = Get-ScheduledTask | Where-Object {$_.TaskName -like $biapp }
    if ($exists)
    {
        Write-Host "$biapp scheduled task already exists"
        Stop-ScheduledTask -TaskName $biapp
        Unregister-ScheduledTask -Confirm:$false -TaskName $biapp
    }
    # install scheduled task
    Write-Host "Installing $biapp scheduled task"
    $action = New-ScheduledTaskAction -WorkingDirectory $env:AZ_BATCH_TASK_WORKING_DIR -Execute 'Powershell.exe' -Argument "Start-Process $bi -ArgumentList ('$env:AZ_BATCH_POOL_ID', '$env:AZ_BATCH_NODE_ID', '$env:APP_INSIGHTS_INSTRUMENTATION_KEY') -RedirectStandardOutput .\node-stats.log -RedirectStandardError .\node-stats.err.log -NoNewWindow"
    $principal = New-ScheduledTaskPrincipal -UserID 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -Action $action -Principal $principal -TaskName $biapp -Force
    Start-ScheduledTask -TaskName $biapp
    Get-ScheduledTask -TaskName $biapp
    Write-Host "Batch Insights enabled"
}

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
	throw "Download from $bxurl to $bxoutf failed"
}

# pull required images
Exec { docker pull alfpark/batch-shipyard:${v}-cargo-windows }

# touch node prep finished file
New-Item -ItemType file $NodePrepFinished -Force
