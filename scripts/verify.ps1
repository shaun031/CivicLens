[CmdletBinding()]
param(
    [switch]$SkipBrowser,
    [switch]$SkipCoverage
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$infrastructureRoot = Join-Path $projectRoot 'infrastructure'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'Backend virtual environment is missing. Run .\scripts\setup.ps1 first.'
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'npm is unavailable. Install Node.js from https://nodejs.org/.'
}
$npmCommand = (Get-Command npm.cmd).Source
$runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$resultRoot = Join-Path $projectRoot "build\verification\$runName"
New-Item -ItemType Directory -Path $resultRoot | Out-Null
$script:checks = [System.Collections.Generic.List[object]]::new()
$script:verificationStarted = Get-Date
$script:verificationFinished = $false
$priorCoverageFile = [Environment]::GetEnvironmentVariable('COVERAGE_FILE', 'Process')
$env:COVERAGE_FILE = Join-Path $resultRoot 'backend-coverage.sqlite'
Start-Transcript -Path (Join-Path $resultRoot 'verification.log') | Out-Null

function Write-Summary {
    $browserCheck = @($script:checks | Where-Object { $_.name -eq 'Isolated real browser end-to-end and accessibility checks' })
    $backendCheck = @($script:checks | Where-Object { $_.name -eq 'Backend unit, security, migration and concurrency tests' })
    $summary = [ordered]@{
        startedAt = $script:verificationStarted.ToUniversalTime().ToString('o')
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
        checks = @($script:checks.ToArray())
        executedLocalChecks = $(if (@($script:checks | Where-Object {$_.status -eq 'FAIL'}).Count) { 'FAIL' } elseif ($script:verificationFinished) { 'PASS' } else { 'IN_PROGRESS' })
        browser = $(if ($SkipBrowser -or -not $browserCheck.Count) { 'NOT_VERIFIED' } else { $browserCheck[-1].status })
        backendCoverage = $(if ($SkipCoverage -or -not $backendCheck.Count) { 'NOT_VERIFIED' } else { $backendCheck[-1].status })
        frontendCoverage = 'NOT_VERIFIED: coverage provider not installed; interaction and browser tests run'
        awsDeploymentReadiness = 'BLOCKED: source-only artifact, missing cloud domain bindings and hosting/provisioning'
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $resultRoot 'summary.json') -Encoding utf8
}

function Invoke-Check([string]$Name, [string]$WorkingDirectory, [scriptblock]$Command) {
    Write-Host "`n==> $Name" -ForegroundColor Cyan
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $stepLog = Join-Path $resultRoot ('step-{0:D2}.log' -f ($script:checks.Count + 1))
    Push-Location $WorkingDirectory
    try {
        # Start-Transcript alone omits native stdout on some noninteractive Windows hosts.
        & $Command 2>&1 | Tee-Object -FilePath $stepLog
        if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
        $script:checks.Add(@{ name = $Name; status = 'PASS'; log = $stepLog; seconds = [math]::Round($watch.Elapsed.TotalSeconds, 3) })
    } catch {
        $script:checks.Add(@{ name = $Name; status = 'FAIL'; log = $stepLog; seconds = [math]::Round($watch.Elapsed.TotalSeconds, 3) })
        throw
    } finally { Pop-Location; Write-Summary }
}

# No credentials are required or inherited by tests/synthesis. Restore caller settings afterwards.
$credentialNames = @('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','AWS_PROFILE','AWS_DEFAULT_PROFILE','AWS_WEB_IDENTITY_TOKEN_FILE','AWS_ROLE_ARN','AWS_ROLE_SESSION_NAME','AWS_CONTAINER_CREDENTIALS_RELATIVE_URI','AWS_CONTAINER_CREDENTIALS_FULL_URI','AWS_EC2_METADATA_DISABLED','AWS_CONFIG_FILE','AWS_SHARED_CREDENTIALS_FILE')
$savedCredentials = @{}
foreach ($name in $credentialNames) {
    $savedCredentials[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    # PowerShell/.NET versions can preserve null assignment as an EMPTY env value.
    # boto3 treats AWS_PROFILE='' as a selected nonexistent profile, not as unset.
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}
$env:AWS_EC2_METADATA_DISABLED = 'true'
$env:AWS_CONFIG_FILE = Join-Path $resultRoot 'intentionally-absent-config'
$env:AWS_SHARED_CREDENTIALS_FILE = Join-Path $resultRoot 'intentionally-absent-credentials'
try {
Invoke-Check 'Backend unit, security, migration and concurrency tests' $backendRoot {
    if ($SkipCoverage) { & $venvPython -m pytest }
    else { & $venvPython -m pytest --cov=app --cov-branch --cov-report=term --cov-report="json:$resultRoot\backend-coverage.json" }
}
Invoke-Check 'Isolated complaint process-restart integration' $backendRoot { & $venvPython -m pytest ..\tests\integration -q }
Invoke-Check 'Phase 5 disposable indexed discovery benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_phase5 }
Invoke-Check 'Phase 6 synthetic matching evaluation' $backendRoot { & $venvPython -m app.scripts.evaluate_matching }
Invoke-Check 'Phase 6 disposable matching benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_matching }
Invoke-Check 'Phase 7 synthetic clustering evaluation' $backendRoot { & $venvPython -m app.scripts.evaluate_clustering }
Invoke-Check 'Phase 7 disposable incident benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_incidents }
Invoke-Check 'Phase 8 priority evaluation and sensitivity' $backendRoot { & $venvPython -m app.scripts.evaluate_priority_model }
Invoke-Check 'Phase 8 disposable priority benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_priority }
Invoke-Check 'Phase 9 disposable allocation and workload benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_allocation }
Invoke-Check 'Phase 10 disposable event workflow benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_events }
Invoke-Check 'Phase 11 disposable municipal analytics benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_analytics }
Invoke-Check 'Phase 12 labeled synthetic intelligence evaluation' $backendRoot { & $venvPython -m app.scripts.evaluate_intelligence }
Invoke-Check 'Phase 12 disposable repair and fairness benchmark' $backendRoot { & $venvPython -m app.scripts.benchmark_intelligence }
Invoke-Check 'Phase 13 reproducible research artifacts' $backendRoot { & $venvPython -m app.scripts.evaluate_civiclens --output "$resultRoot\evaluation" }
Invoke-Check 'Phase 13 isolated ASGI API p95 benchmark and query plans' $backendRoot { & $venvPython -m app.scripts.benchmark_api --output "$resultRoot\api-benchmark.json" }
Invoke-Check 'Python dependency compatibility' $backendRoot { & $venvPython -m pip check }
Invoke-Check 'Backend and integration lint' $backendRoot { & $venvPython -m ruff check . ..\tests\integration --config pyproject.toml }
Invoke-Check 'Backend and integration format check' $backendRoot { & $venvPython -m ruff format --check . ..\tests\integration --config pyproject.toml }
Invoke-Check 'Frontend lint' $frontendRoot { & $npmCommand run lint }
Invoke-Check 'Frontend TypeScript check' $frontendRoot { & $npmCommand run typecheck }
Invoke-Check 'Browser test TypeScript check' $frontendRoot { & $npmCommand run typecheck:browser }
Invoke-Check 'Frontend tests' $frontendRoot { & $npmCommand test }
Invoke-Check 'Frontend production build' $frontendRoot { & $npmCommand run build }
Invoke-Check 'Offline CDK compilation, assertions, synthesis and safety' $projectRoot { & (Join-Path $PSScriptRoot 'verify-infrastructure.ps1') }
Invoke-Check 'Backend and synthesized cloud API route contract' $backendRoot { & $venvPython -m app.scripts.verify_api_contract --template '..\infrastructure\cdk.out\CivicLens-demo.template.json' }
if (-not $SkipBrowser) {
    Invoke-Check 'Isolated real browser end-to-end and accessibility checks' $frontendRoot { & $npmCommand run test:browser }
} else {
    $script:checks.Add(@{name='Browser end-to-end';status='NOT_VERIFIED';seconds=0})
}
Invoke-Check 'Release source and installed dependency manifest' $backendRoot { & $venvPython -m app.scripts.release_manifest --output "$resultRoot\release-manifest.json" }

$script:verificationFinished = $true
Write-Host "`nExecuted local checks passed. AWS deployment remains BLOCKED. Evidence: $resultRoot" -ForegroundColor Green
if ($SkipBrowser -or $SkipCoverage) { Write-Warning 'Requested skipped categories remain NOT_VERIFIED; do not claim full verification.' }
} finally {
    if ($null -eq $priorCoverageFile) {
        Remove-Item -LiteralPath 'Env:COVERAGE_FILE' -ErrorAction SilentlyContinue
    } else {
        [Environment]::SetEnvironmentVariable('COVERAGE_FILE', $priorCoverageFile, 'Process')
    }
    foreach ($name in $credentialNames) {
        if ($null -eq $savedCredentials[$name]) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($name, $savedCredentials[$name], 'Process')
        }
    }
    Write-Summary
    Stop-Transcript | Out-Null
}

