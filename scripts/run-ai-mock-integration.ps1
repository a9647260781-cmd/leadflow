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
        throw "AI integration child process failed with exit code $childExitCode."
    }
    return
}

$ErrorActionPreference = 'Stop'

if ($IsolationProbe) {
    $env:DATABASE_URL = 'postgresql+psycopg://child-only/fixture'
    $env:AI_ENABLED = 'true'
    $env:YANDEX_API_KEY = 'child-only-fixture-key'
    $env:YANDEX_MODEL_URI = 'gpt://child-only/model'
    $env:YANDEX_API_URL = 'http://127.0.0.1:1/child-only'
    if ($InjectIsolationFailure) { throw 'Injected AI harness isolation failure.' }
    Write-Output 'PASS AI harness child environment probe.'
    return
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$python = Join-Path $runtimeRoot 'venv\Scripts\python.exe'
$localEnvPath = Join-Path $runtimeRoot 'local.env'
$credentialEnv = Join-Path $runtimeRoot 'demo-credentials.env'
$testDatabaseName = 'leadflow_test_ai_integration'
$postgresBin = Join-Path $env:LOCALAPPDATA 'LeadFlowRuntime\postgresql\pgsql\bin'
$psql = Join-Path $postgresBin 'psql.exe'
$createdb = Join-Path $postgresBin 'createdb.exe'
$postgresPasswordFile = Join-Path $runtimeRoot 'postgres-password.txt'
$apiPort = 18000
$fixturePort = 18081
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
            Stop-Process -Id $process.Id -Force
        }
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Local Python environment is missing. Create .runtime/venv and install backend[dev].'
}
if (-not (Test-Path -LiteralPath $localEnvPath)) {
    throw 'Local PostgreSQL configuration is missing at .runtime/local.env.'
}
if (-not (Test-Path -LiteralPath $credentialEnv)) {
    throw 'Local test manager credentials are missing at .runtime/demo-credentials.env.'
}
foreach ($required in @($psql, $createdb, $postgresPasswordFile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Local PostgreSQL prerequisite is missing: $required"
    }
}
foreach ($port in @($apiPort, $fixturePort)) {
    if (Test-PortOpen $port) {
        throw "Fixture port $port is already occupied. Nothing was changed."
    }
}

& (Join-Path $PSScriptRoot 'portable-postgres.ps1') start | Out-Null
. (Join-Path $PSScriptRoot 'load-env.ps1') -Path $localEnvPath
if ($env:DATABASE_URL -notmatch '/leadflow(?:\?.*)?$') {
    throw 'Refusing to derive an integration URL from an unexpected DATABASE_URL.'
}
$env:PGPASSWORD = [System.IO.File]::ReadAllText($postgresPasswordFile).Trim()
try {
    $exists = & $psql -h 127.0.0.1 -p 55432 -U leadflow -d postgres -tAc `
        "SELECT 1 FROM pg_database WHERE datname = '$testDatabaseName'"
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the dedicated AI integration database.' }
    if (-not $exists) {
        & $createdb -h 127.0.0.1 -p 55432 -U leadflow -O leadflow $testDatabaseName
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the dedicated AI integration database.' }
    }
    $connectedDatabase = & $psql -h 127.0.0.1 -p 55432 -U leadflow -d $testDatabaseName `
        -tAc 'SELECT current_database()'
    if ($LASTEXITCODE -ne 0 -or $connectedDatabase.Trim() -ne $testDatabaseName) {
        throw 'Dedicated AI integration database verification failed.'
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
$env:DATABASE_URL = $env:DATABASE_URL -replace '/leadflow(?=\?|$)', "/$testDatabaseName"
$env:APP_ORIGIN = 'http://127.0.0.1:18080'
$env:ADDITIONAL_ALLOWED_ORIGINS = ''
$env:AI_ENABLED = 'true'
$env:YANDEX_API_KEY = 'fixture-only-key'
$env:YANDEX_MODEL_URI = 'gpt://fixture-folder/yandexgpt/latest'
$env:YANDEX_API_URL = "http://127.0.0.1:$fixturePort/foundationModels/v1/completion"
$env:YANDEX_DATA_LOGGING_ENABLED = 'false'
$env:EXTRACTION_POLL_INTERVAL_SECONDS = '0.1'
$env:EXTRACTION_REQUEST_TIMEOUT_SECONDS = '2'
$env:EXTRACTION_MAX_ATTEMPTS = '2'
$env:EXTRACTION_LEASE_SECONDS = '10'
$env:EXTRACTION_RETRY_BASE_SECONDS = '1'
$env:LEADFLOW_TEST_API = "http://127.0.0.1:$apiPort/api"
$env:LEADFLOW_TEST_ORIGIN = $env:APP_ORIGIN

try {
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & $python -m alembic downgrade base | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Dedicated test database reset failed.' }
        & $python -m alembic upgrade head | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Dedicated test database migration failed.' }

        . (Join-Path $PSScriptRoot 'load-env.ps1') -Path $credentialEnv
        & $python -m app.cli create-manager | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Dedicated test manager creation failed.' }
    } finally {
        Pop-Location
    }

    $fixture = Start-Process -FilePath $python `
        -ArgumentList (Join-Path $projectRoot 'tests\fixtures\yandex_mock_server.py') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
    $started += $fixture

    $backend = Start-Process -FilePath $python `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$apiPort" `
        -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru
    $started += $backend

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($fixture.HasExited -or $backend.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/api/health" -TimeoutSec 2
            if ($health.status -eq 'ok' -and (Test-PortOpen $fixturePort)) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) { throw 'Fixture API did not become ready.' }

    $worker = Start-Process -FilePath $python -ArgumentList '-m', 'app.worker' `
        -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru
    $started += $worker
    Start-Sleep -Milliseconds 250
    if ($worker.HasExited) { throw 'Fixture extraction worker exited early.' }

    & $python (Join-Path $projectRoot 'tests\integration_ai_mock.py')
    if ($LASTEXITCODE -ne 0) { throw 'Fixture-only AI integration test failed.' }
} finally {
    Stop-StartedProcesses
}
