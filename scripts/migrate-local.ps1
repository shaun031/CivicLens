[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$migrationRoot = Split-Path -Parent $PSScriptRoot
$migrationBackend = Join-Path $migrationRoot 'backend'
$migrationPython = Join-Path $migrationBackend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $migrationPython)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location $migrationBackend
try {
    & $migrationPython -m app.scripts.local_auth init
    if ($LASTEXITCODE -ne 0) { throw 'Local schema migration failed; no data reset was attempted.' }
} finally { Pop-Location }
