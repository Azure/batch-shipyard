Set-Variable BlobxferExe -option Constant -value [io.path]::combine($env:AZ_BATCH_NODE_STARTUP_DIR, "wd", "blobxfer.exe")

foreach ($spec in $args)
{
	$parts = $spec -split ':'
	$bxver = $parts[0]
	$kind = $parts[1]
	$encrypted = $parts[2].ToLower()
	
	$sa = $null
	$ep = $null
	$saskey = $null
	$remote_path = $null
	$local_path = $null
	$eo = $null
	
	if ($encrypted == "true") {
		# TODO support credential encryption
		$cipher = $parts[3]
		$local_path = $parts[4]
		$eo = $parts[5]
		Write-Error "ERROR: credential encryption is not supported on windows"
		exit 1
	}
	else
	{
		$sa = $parts[3]
		$ep = $parts[4]
		$saskey = $parts[5]
		$remote_path = $parts[6]
		$local_path = $parts[7]
		$eo = $parts[8]
	}
	
	if ($kind == "i")
	{
		$action = "download"
	}
	elseif ($kind == "e")
	{
		$action = "upload"
	}
	else
	{
		Write-Error "Unknown $kind transfer"
		exit 1
	}
	
	$BlobxferExe $action --storage-account $sa --sas $saskey --endpoint $ep --remote-path $remote_path --local-path $local_path --no-progress-bar $eo
}