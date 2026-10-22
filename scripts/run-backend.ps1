[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'Backend virtual environment is missing. Run .\scripts\setup.ps1 first.'
}

Push-Location $backendRoot
try {
    Write-Host 'Phase 11 API adds analytics-owned schema8 extensions. Existing accounts and operational work are preserved.'
    & $venvPython -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw "Uvicorn exited with code $LASTEXITCODE." }
} finally { Pop-Location }

