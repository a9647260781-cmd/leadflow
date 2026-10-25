[CmdletBinding()]
param(
    [switch]$TestDatabase
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$configPath = Join-Path $runtimeRoot 'notifications.env'
$passwordPath = Join-Path $runtimeRoot 'postgres-password.txt'
$postgresBin = Join-Path $env:LOCALAPPDATA 'LeadFlowRuntime\postgresql\pgsql\bin'
$psql = Join-Path $postgresBin 'psql.exe'
$createdb = Join-Path $postgresBin 'createdb.exe'

if (-not (Test-Path -LiteralPath $configPath)) {
    throw 'Run scripts/create-local-notification-config.ps1 first.'
}
if (-not (Test-Path -LiteralPath $passwordPath)) {
    throw 'Portable PostgreSQL admin password is missing.'
}

& (Join-Path $PSScriptRoot 'portable-postgres.ps1') start | Out-Null
. (Join-Path $PSScriptRoot 'load-env.ps1') -Path $configPath

$role = $env:N8N_POSTGRES_USER
$database = if ($TestDatabase) { "$($env:N8N_POSTGRES_DB)_test" } else { $env:N8N_POSTGRES_DB }
$rolePassword = $env:N8N_POSTGRES_PASSWORD
if ($role -notmatch '^[a-z][a-z0-9_]*$' -or $database -notmatch '^[a-z][a-z0-9_]*$') {
    throw 'Local n8n PostgreSQL role/database names contain unsupported characters.'
}
if ($rolePassword -notmatch '^[A-Za-z0-9_-]{32,}$') {
    throw 'Local n8n PostgreSQL password must be a long URL-safe random value.'
}

$env:PGPASSWORD = [System.IO.File]::ReadAllText($passwordPath).Trim()
try {
    $roleExists = & $psql -h 127.0.0.1 -p 55432 -U leadflow -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$role'"
    if (-not $roleExists) {
        & $psql -h 127.0.0.1 -p 55432 -U leadflow -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE $role LOGIN PASSWORD '$rolePassword'" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the local n8n PostgreSQL role.' }
    } else {
        & $psql -h 127.0.0.1 -p 55432 -U leadflow -d postgres -v ON_ERROR_STOP=1 -c "ALTER ROLE $role PASSWORD '$rolePassword'" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not synchronize the local n8n PostgreSQL role.' }
    }

    $databaseExists = & $psql -h 127.0.0.1 -p 55432 -U leadflow -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$database'"
    if (-not $databaseExists) {
        & $createdb -h 127.0.0.1 -p 55432 -U leadflow -O $role $database
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the local n8n PostgreSQL database.' }
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Output "Local n8n PostgreSQL database '$database' is ready with its dedicated role."
