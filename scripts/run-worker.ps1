[CmdletBinding()]
param([switch]$Once, [switch]$Continuous, [ValidateRange(1,100)][int]$BatchSize=20, [ValidateRange(1,100)][int]$MaxBatches=20)
$ErrorActionPreference = 'Stop'
Write-Host 'Phase 11 reuses this foreground worker for noncritical analytics event checkpoints; current SQLite metrics read source snapshots.'
$backendRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run scripts/setup.ps1 first.' }
$workerArguments = @('-m','app.scripts.run_worker','--batch-size',"$BatchSize",'--max-batches',"$MaxBatches")
if ($Once) { $workerArguments += '--once' }
if ($Continuous) { $workerArguments += '--continuous' }
Push-Location $backendRoot
try { & $venvPython @workerArguments; if ($LASTEXITCODE -ne 0) { throw 'Worker failed; durable work is retained.' } }
finally { Pop-Location }
