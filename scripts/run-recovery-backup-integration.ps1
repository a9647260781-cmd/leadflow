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
        throw "Recovery integration child process failed with exit code $childExitCode."
    }
    return
}

$ErrorActionPreference = 'Stop'

if ($IsolationProbe) {
    $env:DATABASE_URL = 'postgresql+psycopg://child-only/recovery'
    $env:AI_ENABLED = 'true'
    $env:YANDEX_API_KEY = 'child-only-fixture-key'
    $env:N8N_ENCRYPTION_KEY = 'child-only-encryption-key'
    $env:DB_POSTGRESDB_DATABASE = 'child_only_n8n'
    $env:PGPASSWORD = 'child-only-password'
    if ($InjectIsolationFailure) { throw 'Injected recovery harness isolation failure.' }
    Write-Output 'PASS recovery harness child environment probe.'
    return
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$qaRoot = Join-Path $runtimeRoot 'release-recovery-qa'
$logDir = Join-Path $qaRoot 'logs'
$backupDir = Join-Path $runtimeRoot 'backups'
$portableRoot = Join-Path $env:LOCALAPPDATA 'LeadFlowRuntime'
$postgresRoot = Join-Path $portableRoot 'postgresql\pgsql'
$dataDir = Join-Path $portableRoot 'release-recovery-postgres-data'
$pgBin = Join-Path $postgresRoot 'bin'
$pgCtl = Join-Path $pgBin 'pg_ctl.exe'
$initDb = Join-Path $pgBin 'initdb.exe'
$pgIsReady = Join-Path $pgBin 'pg_isready.exe'
$createdb = Join-Path $pgBin 'createdb.exe'
$dropdb = Join-Path $pgBin 'dropdb.exe'
$pgDump = Join-Path $pgBin 'pg_dump.exe'
$pgRestore = Join-Path $pgBin 'pg_restore.exe'
$python = Join-Path $runtimeRoot 'venv\Scripts\python.exe'
$node = Join-Path $runtimeRoot 'node24\node-v24.22.1-win-x64\node.exe'
$n8n = Join-Path $runtimeRoot 'n8n\node_modules\n8n\bin\n8n'
$passwordFile = Join-Path $qaRoot 'postgres-password.txt'
$encryptionKeyFile = Join-Path $qaRoot 'n8n-encryption-key.txt'
$port = 55433
$apiPort = 18100
$fixturePort = 18181
$n8nPort = 15678
$appSource = 'leadflow_recovery_source'
$appRestore = 'leadflow_recovery_restore'
$n8nSource = 'leadflow_n8n_recovery_source'
$n8nRestore = 'leadflow_n8n_recovery_restore'
$started = @()

function Test-PortOpen([int]$targetPort) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync('127.0.0.1', $targetPort).Wait(250) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function New-RandomText([int]$bytes = 32) {
    $buffer = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer).Replace('+', 'A').Replace('/', 'B').TrimEnd('=')
}

function Invoke-BoundedProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory = $projectRoot,
    [int]$TimeoutSeconds = 60
) {
    $stdout = Join-Path $logDir "$Name.out.log"
    $stderr = Join-Path $logDir "$Name.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "$Name timed out after $TimeoutSeconds seconds. Inspect ignored QA logs."
    }
    if ($process.ExitCode -ne 0) {
        throw "$Name failed with exit code $($process.ExitCode). Inspect ignored QA logs."
    }
}

function Test-ClusterReady {
    & $pgIsReady -h 127.0.0.1 -p $port -U leadflow -d postgres *> $null
    return $LASTEXITCODE -eq 0
}

function Start-QaCluster {
    if (Test-ClusterReady) { return }
    if (Test-PortOpen $port) {
        throw "Port $port is occupied by a process other than the isolated QA cluster."
    }
    & $pgCtl start -D $dataDir -l (Join-Path $logDir 'postgres.log') `
        -o "-p $port -h 127.0.0.1" -w -t 15
    if ($LASTEXITCODE -ne 0 -or -not (Test-ClusterReady)) {
        throw 'Isolated PostgreSQL cluster did not become ready.'
    }
}

function Stop-QaCluster {
    if (Test-Path -LiteralPath (Join-Path $dataDir 'postmaster.pid')) {
        & $pgCtl stop -D $dataDir -m fast -w -t 15
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop isolated PostgreSQL cluster.' }
    }
}

function Reset-QaDatabase([string]$database) {
    if ($database -notmatch '^leadflow_(recovery|n8n_recovery)_(source|restore)$') {
        throw "Refusing to reset unexpected database '$database'."
    }
    & $dropdb -h 127.0.0.1 -p $port -U leadflow --if-exists --force $database 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Could not drop isolated database $database." }
    & $createdb -h 127.0.0.1 -p $port -U leadflow -O leadflow $database
    if ($LASTEXITCODE -ne 0) { throw "Could not create isolated database $database." }
}

function Get-DatabaseUrl([string]$database) {
    $password = [System.IO.File]::ReadAllText($passwordFile).Trim()
    return "postgresql+psycopg://leadflow:$password@127.0.0.1:$port/$database"
}

function Set-N8nEnvironment([string]$database) {
    $env:DB_TYPE = 'postgresdb'
    $env:DB_POSTGRESDB_HOST = '127.0.0.1'
    $env:DB_POSTGRESDB_PORT = "$port"
    $env:DB_POSTGRESDB_DATABASE = $database
    $env:DB_POSTGRESDB_USER = 'leadflow'
    $env:DB_POSTGRESDB_PASSWORD = [System.IO.File]::ReadAllText($passwordFile).Trim()
    $env:N8N_ENCRYPTION_KEY = [System.IO.File]::ReadAllText($encryptionKeyFile).Trim()
    $env:N8N_USER_FOLDER = Join-Path $qaRoot 'n8n-data'
    $env:N8N_HOST = '127.0.0.1'
    $env:N8N_PORT = "$n8nPort"
    $env:N8N_RUNNERS_BROKER_PORT = '15679'
    $env:N8N_PROTOCOL = 'http'
    $env:N8N_EDITOR_BASE_URL = "http://127.0.0.1:$n8nPort"
    $env:N8N_DIAGNOSTICS_ENABLED = 'false'
    $env:N8N_PERSONALIZATION_ENABLED = 'false'
    $env:N8N_VERSION_NOTIFICATIONS_ENABLED = 'false'
    $env:N8N_TEMPLATES_ENABLED = 'false'
    $env:N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS = 'false'
    $env:N8N_SECURE_COOKIE = 'false'
    $env:GENERIC_TIMEZONE = 'Europe/Moscow'
    $env:TZ = 'Europe/Moscow'
}

function Wait-ApiHealth([System.Diagnostics.Process]$process, [int]$timeoutSeconds = 15) {
    $deadline = [datetime]::UtcNow.AddSeconds($timeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        if ($process.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/api/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { return }
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    throw 'Isolated backend API did not become healthy within the bounded wait.'
}

function Start-QaBackend([string]$label) {
    $process = Start-Process -FilePath $python `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$apiPort" `
        -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir "$label.out.log") `
        -RedirectStandardError (Join-Path $logDir "$label.err.log")
    $script:started += $process
    Wait-ApiHealth $process
    return $process
}

function Start-QaWorker([string]$label) {
    $process = Start-Process -FilePath $python -ArgumentList '-m', 'app.worker' `
        -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir "$label.out.log") `
        -RedirectStandardError (Join-Path $logDir "$label.err.log")
    $script:started += $process
    Start-Sleep -Milliseconds 300
    if ($process.HasExited) { throw 'Isolated extraction worker exited during startup.' }
    return $process
}

function Start-QaN8n([string]$label) {
    $process = Start-Process -FilePath $node -ArgumentList $n8n, 'start' `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir "$label.out.log") `
        -RedirectStandardError (Join-Path $logDir "$label.err.log")
    $script:started += $process
    $deadline = [datetime]::UtcNow.AddSeconds(60)
    while ([datetime]::UtcNow -lt $deadline) {
        if ($process.HasExited) { break }
        try {
            $response = Invoke-WebRequest -UseBasicParsing `
                -Uri "http://127.0.0.1:$n8nPort/healthz/readiness" -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return $process }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw 'Isolated n8n did not become ready within the bounded wait.'
}

function Stop-QaProcess([System.Diagnostics.Process]$process) {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        if (-not $process.WaitForExit(10000)) {
            throw "Process $($process.Id) did not stop within the bounded wait."
        }
    }
}

foreach ($required in @($pgCtl, $initDb, $pgIsReady, $createdb, $dropdb, $pgDump, $pgRestore, $python, $node, $n8n)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required local runtime is missing: $required" }
}
foreach ($reservedPort in @($apiPort, $fixturePort, $n8nPort, 15679)) {
    if (Test-PortOpen $reservedPort) {
        throw "Fixture port $reservedPort is already occupied. Nothing was changed."
    }
}

New-Item -ItemType Directory -Force -Path $qaRoot, $logDir, $backupDir | Out-Null
if (-not (Test-Path -LiteralPath $passwordFile)) {
    [System.IO.File]::WriteAllText($passwordFile, (New-RandomText), [System.Text.UTF8Encoding]::new($false))
}
if (-not (Test-Path -LiteralPath $encryptionKeyFile)) {
    [System.IO.File]::WriteAllText($encryptionKeyFile, (New-RandomText 48), [System.Text.UTF8Encoding]::new($false))
}
if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'PG_VERSION'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dataDir) | Out-Null
    & $initDb -D $dataDir -U leadflow --pwfile=$passwordFile `
        --auth-host=scram-sha-256 --auth-local=trust --encoding=UTF8 --no-locale | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize isolated PostgreSQL cluster.' }
}

$env:PGPASSWORD = [System.IO.File]::ReadAllText($passwordFile).Trim()
try {
    Start-QaCluster
    foreach ($database in @($appSource, $appRestore, $n8nSource, $n8nRestore)) {
        Reset-QaDatabase $database
    }

    $env:DATABASE_URL = Get-DatabaseUrl $appSource
    $env:APP_ORIGIN = 'http://127.0.0.1:18180'
    $env:ADDITIONAL_ALLOWED_ORIGINS = ''
    $env:AI_ENABLED = 'true'
    $env:YANDEX_API_KEY = 'fixture-only-key'
    $env:YANDEX_MODEL_URI = 'gpt://fixture-folder/yandexgpt/latest'
    $env:YANDEX_API_URL = "http://127.0.0.1:$fixturePort/foundationModels/v1/completion"
    $env:YANDEX_DATA_LOGGING_ENABLED = 'false'
    $env:EXTRACTION_POLL_INTERVAL_SECONDS = '0.2'
    $env:EXTRACTION_REQUEST_TIMEOUT_SECONDS = '12'
    $env:EXTRACTION_MAX_ATTEMPTS = '3'
    $env:EXTRACTION_LEASE_SECONDS = '2'
    $env:EXTRACTION_RETRY_BASE_SECONDS = '1'
    $env:DB_CONNECT_TIMEOUT_SECONDS = '1'
    $env:NOTIFICATIONS_ENABLED = 'false'

    Invoke-BoundedProcess 'alembic-upgrade' $python @('-m', 'alembic', 'upgrade', 'head') `
        (Join-Path $projectRoot 'backend') 60
    $backend = Start-QaBackend 'backend-source'
    Invoke-BoundedProcess 'seed-app' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'), 'seed-app'
    ) (Join-Path $projectRoot 'backend') 30

    $env:LEADFLOW_FIXTURE_PORT = "$fixturePort"
    $env:LEADFLOW_FIXTURE_DELAY_SECONDS = '4'
    $fixture = Start-Process -FilePath $python `
        -ArgumentList (Join-Path $projectRoot 'tests\fixtures\yandex_mock_server.py') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'fixture.out.log') `
        -RedirectStandardError (Join-Path $logDir 'fixture.err.log')
    $started += $fixture
    for ($attempt = 0; $attempt -lt 30 -and -not (Test-PortOpen $fixturePort); $attempt++) {
        if ($fixture.HasExited) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($fixture.HasExited -or -not (Test-PortOpen $fixturePort)) {
        throw 'Loopback Yandex fixture did not become ready.'
    }

    $worker = Start-QaWorker 'worker-source'
    Invoke-BoundedProcess 'wait-processing' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'),
        'wait-processing', '--timeout', '10'
    ) (Join-Path $projectRoot 'backend') 15

    Stop-QaCluster
    Start-Sleep -Seconds 6
    if ($worker.HasExited) { throw 'Extraction worker exited during PostgreSQL outage.' }
    $workerLog = Get-Content -Raw -LiteralPath (Join-Path $logDir 'worker-source.err.log') -ErrorAction SilentlyContinue
    if ($workerLog -notmatch 'database unavailable; retrying') {
        throw 'Worker stayed alive but no bounded database-retry evidence was recorded.'
    }
    Start-QaCluster
    Wait-ApiHealth $backend
    Invoke-BoundedProcess 'wait-succeeded' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'),
        'wait-succeeded', '--timeout', '20'
    ) (Join-Path $projectRoot 'backend') 25
    Invoke-BoundedProcess 'verify-app-source' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'), 'verify-app'
    ) (Join-Path $projectRoot 'backend') 30

    Set-N8nEnvironment $n8nSource
    $workflowImport = Join-Path $qaRoot 'workflow-import'
    New-Item -ItemType Directory -Force -Path $workflowImport | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot 'automation\n8n\leadflow-new-lead-notifications.json') -Destination $workflowImport -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'automation\n8n\leadflow-reminder-notifications.json') -Destination $workflowImport -Force
    Invoke-BoundedProcess 'n8n-import-workflows' $node @(
        $n8n, 'import:workflow', '--separate', '--input', $workflowImport
    ) $projectRoot 120
    $n8nSourceProcess = Start-QaN8n 'n8n-source'
    Stop-QaProcess $n8nSourceProcess

    $appDump = Join-Path $backupDir 'release-qa-app.dump'
    $n8nDump = Join-Path $backupDir 'release-qa-n8n.dump'
    Invoke-BoundedProcess 'dump-app' $pgDump @(
        '-h', '127.0.0.1', '-p', "$port", '-U', 'leadflow', '-Fc', '-f', $appDump, $appSource
    ) $projectRoot 60
    Invoke-BoundedProcess 'dump-n8n' $pgDump @(
        '-h', '127.0.0.1', '-p', "$port", '-U', 'leadflow', '-Fc', '-f', $n8nDump, $n8nSource
    ) $projectRoot 60
    Invoke-BoundedProcess 'restore-app' $pgRestore @(
        '-h', '127.0.0.1', '-p', "$port", '-U', 'leadflow', '--no-owner',
        '--exit-on-error', '-d', $appRestore, $appDump
    ) $projectRoot 60
    Invoke-BoundedProcess 'restore-n8n' $pgRestore @(
        '-h', '127.0.0.1', '-p', "$port", '-U', 'leadflow', '--no-owner',
        '--exit-on-error', '-d', $n8nRestore, $n8nDump
    ) $projectRoot 120

    $env:DATABASE_URL = Get-DatabaseUrl $appRestore
    Invoke-BoundedProcess 'verify-app-restore' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'), 'verify-app'
    ) (Join-Path $projectRoot 'backend') 30
    $env:SOURCE_DATABASE_URL = Get-DatabaseUrl $n8nSource
    $env:RESTORED_DATABASE_URL = Get-DatabaseUrl $n8nRestore
    Invoke-BoundedProcess 'verify-n8n-restore' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'), 'verify-n8n'
    ) (Join-Path $projectRoot 'backend') 30

    Stop-QaCluster
    Start-QaCluster
    $env:DATABASE_URL = Get-DatabaseUrl $appRestore
    Stop-QaProcess $worker
    Stop-QaProcess $backend
    $backendRestored = Start-QaBackend 'backend-restored'
    $workerRestored = Start-QaWorker 'worker-restored'
    Invoke-BoundedProcess 'verify-app-after-restart' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'), 'verify-app'
    ) (Join-Path $projectRoot 'backend') 30
    Set-N8nEnvironment $n8nRestore
    $n8nRestoredProcess = Start-QaN8n 'n8n-restored'
    Invoke-BoundedProcess 'verify-n8n-after-restart' $python @(
        (Join-Path $projectRoot 'tests\integration_recovery_backup.py'), 'verify-n8n'
    ) (Join-Path $projectRoot 'backend') 30
    if ($backendRestored.HasExited -or $workerRestored.HasExited -or $n8nRestoredProcess.HasExited) {
        throw 'A restored runtime process exited before persistence verification completed.'
    }

    Write-Output 'PASS clean local API health, worker outage/recovery, app+n8n backup/restore, and process/database restart persistence.'
    Write-Output 'Ignored backup artifacts: .runtime/backups/release-qa-app.dump and release-qa-n8n.dump.'
} finally {
    foreach ($process in $started) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    try { Stop-QaCluster } catch { Write-Warning $_.Exception.Message }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
