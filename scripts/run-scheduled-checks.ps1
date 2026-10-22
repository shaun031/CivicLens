[CmdletBinding()]
param([switch]$DryRun, [switch]$Once, [ValidateRange(1,100)][int]$BatchSize=20)
$ErrorActionPreference = 'Stop'
$backendRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run scripts/setup.ps1 first.' }
$checkArguments = @('-m','app.scripts.run_scheduled_checks','--once','--batch-size',"$BatchSize")
if ($DryRun) { $checkArguments += '--dry-run' }
Push-Location $backendRoot
try { & $venvPython @checkArguments; if ($LASTEXITCODE -ne 0) { throw 'Scheduled checks failed.' } }
finally { Pop-Location }
