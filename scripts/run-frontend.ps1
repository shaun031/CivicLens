[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Write-Host 'Phase 11 frontend uses /api for private reports, municipal analytics and authorized workflow operations.'
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
    throw 'Frontend dependencies are missing. Run .\scripts\setup.ps1 first.'
}

Push-Location $frontendRoot
try {
    & $npmCommand run dev -- --host localhost --port 5173
    if ($LASTEXITCODE -ne 0) { throw "Vite exited with code $LASTEXITCODE." }
} finally { Pop-Location }

