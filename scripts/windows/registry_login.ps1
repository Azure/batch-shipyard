if (!([String]::IsNullOrEmpty($env:DOCKER_LOGIN_PASSWORD))) {
	$servers = $env:DOCKER_LOGIN_SERVER -split ','
	$users = $env:DOCKER_LOGIN_USERNAME -split ','
	$passwords = $env:DOCKER_LOGIN_PASSWORD -split ','
	
	$nservers = $servers.Length
	if ($nservers > 0) {
		Write-Host "Logging into $nservers Docker registry servers..."
		for ($i = 0; $i -lt $nservers; $i++) {
			docker login --username $users[$i] --password $password[$i] $servers[$i]
			if ($LastExitCode -ne 0) {
				Write-Error "Aborting Docker Logins due to failures"
				exit $LastExitCode
			}
		}
		Write-Host "Docker registry logins completed."
	}
	else
	{
		Write-Host "No Docker registry servers found."
	}
}