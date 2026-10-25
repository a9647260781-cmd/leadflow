[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('seed', 'reset')]
    [string]$Action = 'seed',

    [switch]$ConfirmReset
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$python = Join-Path $runtimeRoot 'venv\Scripts\python.exe'
$localEnv = Join-Path $runtimeRoot 'local.env'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Local Python environment is missing at .runtime/venv.'
}
if (-not (Test-Path -LiteralPath $localEnv)) {
    throw 'Local PostgreSQL configuration is missing at .runtime/local.env.'
}
if ($Action -eq 'reset' -and -not $ConfirmReset) {
    throw 'Demo reset requires the explicit -ConfirmReset switch.'
}

$savedDatabaseUrl = [Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')
$savedAiEnabled = [Environment]::GetEnvironmentVariable('AI_ENABLED', 'Process')
$savedNotificationsEnabled = [Environment]::GetEnvironmentVariable(
    'NOTIFICATIONS_ENABLED', 'Process'
)

try {
    . (Join-Path $PSScriptRoot 'load-env.ps1') -Path $localEnv
    if ($env:DATABASE_URL -notmatch '^postgresql\+psycopg://[^/]+@127\.0\.0\.1:55432/leadflow(?:\?.*)?$') {
        throw 'Refusing to manage demo data outside the expected local LeadFlow database.'
    }
    $env:AI_ENABLED = 'false'
    $env:NOTIFICATIONS_ENABLED = 'false'

    Push-Location (Join-Path $projectRoot 'backend')
    try {
        $arguments = @('-m', 'app.cli')
        if ($Action -eq 'seed') {
            $arguments += 'seed-demo'
        } else {
            $arguments += @('reset-demo', '--confirm')
        }
        & $python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Demo data command failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
} finally {
    if ($null -eq $savedDatabaseUrl) { Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue }
    else { $env:DATABASE_URL = $savedDatabaseUrl }
    if ($null -eq $savedAiEnabled) { Remove-Item Env:AI_ENABLED -ErrorAction SilentlyContinue }
    else { $env:AI_ENABLED = $savedAiEnabled }
    if ($null -eq $savedNotificationsEnabled) {
        Remove-Item Env:NOTIFICATIONS_ENABLED -ErrorAction SilentlyContinue
    } else {
        $env:NOTIFICATIONS_ENABLED = $savedNotificationsEnabled
    }
}
