[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$backendRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run .\scripts\setup.ps1 first.' }
Push-Location $backendRoot
try {
    & $venvPython -m app.scripts.create_local_user
    if ($LASTEXITCODE -ne 0) { throw 'Local account provisioning failed; see the validation message above.' }
} finally { Pop-Location }
