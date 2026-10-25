[CmdletBinding()]
param(
    [Parameter(DontShow)]
    [switch]$IsolatedChild,

    [Parameter(DontShow)]
    [switch]$IsolationProbe,

    [Parameter(DontShow)]
    [switch]$InjectIsolationFailure
)

if (-not $IsolatedChild) {
    $powerShell = (Get-Process -Id $PID).Path
    $childArguments = @('-NoProfile', '-NonInteractive', '-File', $PSCommandPath, '-IsolatedChild')
    if ($IsolationProbe) { $childArguments += '-IsolationProbe' }
    if ($InjectIsolationFailure) { $childArguments += '-InjectIsolationFailure' }
    & $powerShell @childArguments
    $childExitCode = $LASTEXITCODE
    if ($childExitCode -ne 0) {
        throw "Notification integration child process failed with exit code $childExitCode."
    }
    return
}

$ErrorActionPreference = 'Stop'

if ($IsolationProbe) {
    $env:DATABASE_URL = 'postgresql+psycopg://child-only/notifications'
    $env:NOTIFICATIONS_ENABLED = 'true'
    $env:TELEGRAM_BOT_TOKEN = 'child-only-fixture-token'
    $env:N8N_ENCRYPTION_KEY = 'child-only-encryption-key'
    $env:N8N_POSTGRES_PASSWORD = 'child-only-password'
    $env:PGPASSWORD = 'child-only-password'
    if ($InjectIsolationFailure) { throw 'Injected notification harness isolation failure.' }
    Write-Output 'PASS notification harness child environment probe.'
    return
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$python = Join-Path $runtimeRoot 'venv\Scripts\python.exe'
$node = Join-Path $runtimeRoot 'node24\node-v24.22.1-win-x64\node.exe'
$n8n = Join-Path $runtimeRoot 'n8n\node_modules\n8n\bin\n8n'
$postgresBin = Join-Path $env:LOCALAPPDATA 'LeadFlowRuntime\postgresql\pgsql\bin'
$psql = Join-Path $postgresBin 'psql.exe'
$createdb = Join-Path $postgresBin 'createdb.exe'
$dropdb = Join-Path $postgresBin 'dropdb.exe'
$backendDatabase = 'leadflow_test_notifications_integration'
$started = @()

function Test-PortOpen([int]$port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync('127.0.0.1', $port).Wait(250) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Stop-StartedProcesses {
    foreach ($process in $script:started) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

function Set-FixtureNotificationEnv {
    $env:NOTIFICATIONS_ENABLED = 'true'
    $env:TELEGRAM_BOT_TOKEN = 'fixture-bot-token'
    $env:TELEGRAM_CHAT_ID = 'fixture-chat'
    $env:NOTIFICATION_REMINDER_MINUTES = '1'
    $env:MANAGER_PUBLIC_URL = 'http://localhost:8080'
    $env:TELEGRAM_API_BASE_URL = 'http://127.0.0.1:18081'
    $env:NOTIFICATION_REQUEST_TIMEOUT_SECONDS = '1'
    $env:NOTIFICATION_RETRY_BASE_SECONDS = '1'
    $env:NOTIFICATION_RETRY_CAP_SECONDS = '5'
}

foreach ($path in @($python, $node, $n8n, $psql, $createdb, $dropdb)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required local runtime is missing: $path" }
}
foreach ($port in @(5680, 18000, 18081)) {
    if (Test-PortOpen $port) { throw "Fixture port $port is occupied. Nothing was changed." }
}

& (Join-Path $PSScriptRoot 'portable-postgres.ps1') start | Out-Null
. (Join-Path $PSScriptRoot 'load-env.ps1') -Path (Join-Path $runtimeRoot 'local.env')
$mainDatabaseUrl = $env:DATABASE_URL
if ($mainDatabaseUrl -notmatch '/leadflow(?:\?.*)?$') {
    throw 'Refusing to derive a fixture URL from an unexpected DATABASE_URL.'
}
$env:DATABASE_URL = $mainDatabaseUrl -replace '/leadflow(?=\?|$)', "/$backendDatabase"
$env:APP_ORIGIN = 'http://localhost:8080'
$env:ADDITIONAL_ALLOWED_ORIGINS = ''

$adminPassword = [System.IO.File]::ReadAllText((Join-Path $runtimeRoot 'postgres-password.txt')).Trim()
$env:PGPASSWORD = $adminPassword
try {
    $exists = & $psql -h 127.0.0.1 -p 55432 -U leadflow -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$backendDatabase'"
    if (-not $exists) {
        & $createdb -h 127.0.0.1 -p 55432 -U leadflow -O leadflow $backendDatabase
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the dedicated backend fixture database.' }
    }

    . (Join-Path $PSScriptRoot 'load-env.ps1') -Path (Join-Path $runtimeRoot 'notifications.env')
    $n8nTestDatabase = "$($env:N8N_POSTGRES_DB)_test"
    if ($n8nTestDatabase -ne 'leadflow_n8n_test') {
        throw 'Refusing to reset an unexpected n8n fixture database.'
    }
    & $dropdb -h 127.0.0.1 -p 55432 -U leadflow --if-exists --force $n8nTestDatabase
    if ($LASTEXITCODE -ne 0) { throw 'Could not reset the dedicated n8n fixture database.' }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
& (Join-Path $PSScriptRoot 'initialize-local-n8n-db.ps1') -TestDatabase | Out-Null

Set-FixtureNotificationEnv
$env:LEADFLOW_N8N_NODE = $node
$env:LEADFLOW_N8N_CLI = $n8n

try {
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & $python -m alembic downgrade base | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Backend fixture database reset failed.' }
        & $python -m alembic upgrade head | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Backend fixture database migration failed.' }
        . (Join-Path $PSScriptRoot 'load-env.ps1') -Path (Join-Path $runtimeRoot 'demo-credentials.env')
        & $python -m app.cli create-manager | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Backend fixture manager creation failed.' }
    } finally {
        Pop-Location
    }

    . (Join-Path $PSScriptRoot 'set-local-n8n-env.ps1') -TestDatabase -Port 5680
    & (Join-Path $PSScriptRoot 'import-local-n8n-workflows.ps1') -TestDatabase -BackendBaseUrl 'http://127.0.0.1:18000' | Out-Null
    . (Join-Path $PSScriptRoot 'set-local-n8n-env.ps1') -TestDatabase -Port 5680
    Set-FixtureNotificationEnv

    $telegram = Start-Process -FilePath $python `
        -ArgumentList (Join-Path $projectRoot 'tests\fixtures\telegram_mock_server.py') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
    $started += $telegram
    $backend = Start-Process -FilePath $python `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18000' `
        -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru
    $started += $backend

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($telegram.HasExited -or $backend.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:18000/api/health' -TimeoutSec 2
            if ($health.status -eq 'ok' -and (Test-PortOpen 18081)) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) { throw 'Backend or Telegram fixture did not become ready.' }

    & $python (Join-Path $projectRoot 'tests\integration_notifications_n8n.py')
    if ($LASTEXITCODE -ne 0) { throw 'Real n8n notification integration failed.' }

    foreach ($workflowId in @('leadflow-new-lead-notifications-v1', 'leadflow-reminder-notifications-v1')) {
        & $node $n8n publish:workflow --id $workflowId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not activate fixture workflow $workflowId." }
    }
    $scheduleServer = Start-Process -FilePath $node -ArgumentList $n8n, 'start' `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeRoot 'logs\n8n-schedule-test.out.log') `
        -RedirectStandardError (Join-Path $runtimeRoot 'logs\n8n-schedule-test.err.log')
    $started += $scheduleServer

    $scheduleReady = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if ($scheduleServer.HasExited) { break }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5680/healthz/readiness' -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $scheduleReady = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $scheduleReady) { throw 'n8n schedule fixture did not become ready.' }

    $env:PGPASSWORD = $env:N8N_POSTGRES_PASSWORD
    try {
        $scheduled = $false
        for ($attempt = 0; $attempt -lt 75; $attempt++) {
            $newSql = 'SELECT count(*) FROM execution_entity WHERE "workflowId" = ''leadflow-new-lead-notifications-v1'' AND mode = ''trigger'''
            $reminderSql = 'SELECT count(*) FROM execution_entity WHERE "workflowId" = ''leadflow-reminder-notifications-v1'' AND mode = ''trigger'''
            $newCount = & $psql -h 127.0.0.1 -p 55432 -U $env:N8N_POSTGRES_USER -d $n8nTestDatabase -tAc $newSql
            $reminderCount = & $psql -h 127.0.0.1 -p 55432 -U $env:N8N_POSTGRES_USER -d $n8nTestDatabase -tAc $reminderSql
            if ([int]$newCount -gt 0 -and [int]$reminderCount -gt 0) {
                $scheduled = $true
                break
            }
            Start-Sleep -Seconds 1
        }
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
    if (-not $scheduled) { throw 'Both active n8n schedules did not execute within 75 seconds.' }
    Write-Output 'PASS real n8n schedules: 30-second new-lead and 1-minute reminder workflows executed against the guarded fixture endpoint.'
} finally {
    Stop-StartedProcesses
}
