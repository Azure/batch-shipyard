try {
    $buildver = Get-Content "version_tag.txt"
    echo "##vso[task.setvariable variable=VERSION_TAG;]$buildver"
    Write-Host "tag version: $buildver"
} catch {
    Write-Host "version.txt file not found"
}
