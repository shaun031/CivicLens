[CmdletBinding()]
param([ValidateRange(1,100)][int]$BatchSize=20, [ValidateRange(1,100)][int]$MaxBatches=20)
& (Join-Path $PSScriptRoot 'run-worker.ps1') -BatchSize $BatchSize -MaxBatches $MaxBatches
