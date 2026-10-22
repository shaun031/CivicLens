[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$infrastructureRoot = Join-Path $projectRoot 'infrastructure'
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'npm.cmd is unavailable. Install a supported Node.js LTS from https://nodejs.org/ and run .\scripts\setup.ps1.'
}
$npmCommand = (Get-Command npm.cmd).Source
if (-not (Test-Path -LiteralPath (Join-Path $infrastructureRoot 'node_modules'))) {
    throw 'Infrastructure dependencies are missing. Run .\scripts\setup.ps1 first.'
}

$offlineAwsPath = Join-Path ([System.IO.Path]::GetTempPath()) ('civiclens-no-aws-' + [guid]::NewGuid().ToString('N'))
$offlineEnvironment = @{
    AWS_ACCESS_KEY_ID = $null; AWS_SECRET_ACCESS_KEY = $null; AWS_SESSION_TOKEN = $null
    AWS_PROFILE = $null; AWS_DEFAULT_PROFILE = $null; AWS_WEB_IDENTITY_TOKEN_FILE = $null
    AWS_ROLE_ARN = $null; AWS_ROLE_SESSION_NAME = $null
    AWS_CONTAINER_CREDENTIALS_RELATIVE_URI = $null; AWS_CONTAINER_CREDENTIALS_FULL_URI = $null
    AWS_EC2_METADATA_DISABLED = 'true'
    AWS_CONFIG_FILE = $offlineAwsPath; AWS_SHARED_CREDENTIALS_FILE = $offlineAwsPath
}
$previousOfflineEnvironment = @{}
foreach ($offlineName in $offlineEnvironment.Keys) {
    $previousOfflineEnvironment[$offlineName] = [Environment]::GetEnvironmentVariable($offlineName, 'Process')
    if ($null -eq $offlineEnvironment[$offlineName]) {
        Remove-Item -LiteralPath "Env:$offlineName" -ErrorAction SilentlyContinue
    } else {
        [Environment]::SetEnvironmentVariable($offlineName, $offlineEnvironment[$offlineName], 'Process')
    }
}
Push-Location $infrastructureRoot
try {
    foreach ($check in @('build', 'test', 'synth', 'check:templates', 'check:local')) {
        Write-Host "`n==> Infrastructure: $check" -ForegroundColor Cyan
        & $npmCommand run $check
        if ($LASTEXITCODE -ne 0) { throw "Infrastructure $check failed with exit code $LASTEXITCODE." }
    }
} finally {
    Pop-Location
    foreach ($offlineName in $previousOfflineEnvironment.Keys) {
        if ($null -eq $previousOfflineEnvironment[$offlineName]) {
            Remove-Item -LiteralPath "Env:$offlineName" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($offlineName, $previousOfflineEnvironment[$offlineName], 'Process')
        }
    }
}
Write-Host 'Phase 13 infrastructure verification passed offline. Nothing was deployed; credential settings restored.' -ForegroundColor Green
