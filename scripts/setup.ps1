[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$infrastructureRoot = Join-Path $projectRoot 'infrastructure'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'

function Get-VersionParts([string]$VersionText) {
    if ($VersionText -notmatch '(\d+)\.(\d+)') {
        throw "Could not parse version from '$VersionText'."
    }
    return [version]::new([int]$Matches[1], [int]$Matches[2])
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3.12 or newer was not found. Install it from https://www.python.org/downloads/windows/ and enable Add Python to PATH.'
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js 20.19+ or 22.12+ was not found. Install the current LTS from https://nodejs.org/.'
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'npm was not found. Reinstall Node.js with npm included.'
}
$npmCommand = (Get-Command npm.cmd).Source

$pythonVersion = Get-VersionParts (& python --version 2>&1)
if ($pythonVersion -lt [version]'3.12') {
    throw "Python $pythonVersion is unsupported; install Python 3.12 or newer."
}
$nodeVersion = Get-VersionParts (& node --version)
if (($nodeVersion.Major -eq 20 -and $nodeVersion -lt [version]'20.19') -or ($nodeVersion.Major -eq 22 -and $nodeVersion -lt [version]'22.12') -or $nodeVersion.Major -lt 20) {
    throw "Node.js $nodeVersion is unsupported; install Node.js 20.19+, 22.12+, or a newer compatible LTS."
}

Write-Host "Using Python $pythonVersion and Node.js $nodeVersion."
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating backend virtual environment...'
    & python -m venv (Join-Path $backendRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}

Write-Host 'Installing backend dependencies...'
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
Push-Location $backendRoot
try {
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
} finally { Pop-Location }

foreach ($nodeProject in @($frontendRoot, $infrastructureRoot)) {
    Write-Host "Installing dependencies in $nodeProject..."
    Push-Location $nodeProject
    try {
        if (Test-Path -LiteralPath (Join-Path $nodeProject 'package-lock.json')) { & $npmCommand ci } else { & $npmCommand install }
        if ($LASTEXITCODE -ne 0) { throw "npm dependency installation failed in $nodeProject. On Windows, stop running CivicLens dev servers and test watchers before rerunning setup (native modules may be locked)." }
    } finally { Pop-Location }
}

foreach ($environment in @(
    @{ Example = (Join-Path $backendRoot '.env.example'); Local = (Join-Path $backendRoot '.env') },
    @{ Example = (Join-Path $frontendRoot '.env.example'); Local = (Join-Path $frontendRoot '.env') }
)) {
    if (-not (Test-Path -LiteralPath $environment.Local)) {
        Copy-Item -LiteralPath $environment.Example -Destination $environment.Local
        Write-Host "Created $($environment.Local) from its example."
    }
}

Write-Host 'Migrating shared operational schema and Phase 11 analytics-owned extensions (existing data preserved)...'
Push-Location $backendRoot
try {
    & $venvPython -m app.scripts.local_auth init
    if ($LASTEXITCODE -ne 0) { throw 'Local authentication initialization failed. Confirm APP_ENV=local and AUTH_PROVIDER=local in backend/.env.' }
} finally { Pop-Location }

Write-Host 'CivicLens local setup completed successfully.' -ForegroundColor Green

