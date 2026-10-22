[CmdletBinding()]
param([switch]$DryRun,[switch]$Diagnose,[switch]$Full,[string]$Start,[string]$End,[string]$Aggregation,[ValidateRange(1,50)][int]$BatchSize=25)
$ErrorActionPreference='Stop'
$backendRoot=Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'
$venvPython=Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run scripts/setup.ps1 first.' }
$analyticsArguments=@('-m','app.scripts.rebuild_analytics','--batch-size',"$BatchSize")
if ($DryRun) { $analyticsArguments+='--dry-run' }
if ($Diagnose) { $analyticsArguments+='--diagnose' }
if ($Full) { $analyticsArguments+='--full' }
if ($Start) { $analyticsArguments+=@('--start',$Start) }
if ($End) { $analyticsArguments+=@('--end',$End) }
if ($Aggregation) { $analyticsArguments+=@('--aggregation',$Aggregation) }
Push-Location $backendRoot
try { & $venvPython @analyticsArguments; if ($LASTEXITCODE -ne 0) { throw 'Analytics command failed; operational records were not reset.' } }
finally { Pop-Location }
