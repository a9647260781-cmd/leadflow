[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'status',

    [int]$Port = 55432
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
# PostgreSQL's Windows bootstrap process cannot initialize inside this
# repository's non-ASCII path. Keep the per-project engine/data under the
# current user's local application data instead of installing a system service.
$portableRuntimeRoot = Join-Path $env:LOCALAPPDATA 'LeadFlowRuntime'
$postgresRoot = Join-Path $portableRuntimeRoot 'postgresql\pgsql'
$dataDir = Join-Path $portableRuntimeRoot 'postgres-data'
$logDir = Join-Path $portableRuntimeRoot 'logs'
$passwordFile = Join-Path $runtimeRoot 'postgres-password.txt'
$localEnvFile = Join-Path $runtimeRoot 'local.env'
$pgCtl = Join-Path $postgresRoot 'bin\pg_ctl.exe'
$initDb = Join-Path $postgresRoot 'bin\initdb.exe'
$createdb = Join-Path $postgresRoot 'bin\createdb.exe'
$pgIsReady = Join-Path $postgresRoot 'bin\pg_isready.exe'

function Assert-Binaries {
    if (-not (Test-Path -LiteralPath $pgCtl)) {
        throw "Portable PostgreSQL was not found at $postgresRoot. Extract the official Windows binaries there first."
    }
}

function Test-PostgresReady {
    & $pgIsReady -h 127.0.0.1 -p $Port -U leadflow -d leadflow *> $null
    return $LASTEXITCODE -eq 0
}

Assert-Binaries

switch ($Action) {
    'start' {
        New-Item -ItemType Directory -Force -Path $runtimeRoot, $portableRuntimeRoot, $logDir | Out-Null

        if (-not (Test-Path -LiteralPath $passwordFile)) {
            $bytes = New-Object byte[] 32
            [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
            $password = [Convert]::ToBase64String($bytes).Replace('+', 'A').Replace('/', 'B').TrimEnd('=')
            [System.IO.File]::WriteAllText($passwordFile, $password, [System.Text.UTF8Encoding]::new($false))
        }

        $password = [System.IO.File]::ReadAllText($passwordFile).Trim()
        if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'PG_VERSION'))) {
            & $initDb -D $dataDir -U leadflow --pwfile=$passwordFile --auth-host=scram-sha-256 --auth-local=trust --encoding=UTF8 --no-locale
            if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
        }

        if (-not (Test-PostgresReady)) {
            $serverLog = Join-Path $logDir 'postgres.log'
            & $pgCtl start -D $dataDir -l $serverLog -o "-p $Port -h 127.0.0.1" -w
            if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed to start' }
        }

        $env:PGPASSWORD = $password
        & $createdb -h 127.0.0.1 -p $Port -U leadflow leadflow 2>$null
        if ($LASTEXITCODE -ne 0) {
            # createdb returns non-zero when the database already exists; verify it instead.
            if (-not (Test-PostgresReady)) { throw 'Could not create or connect to the leadflow database' }
        }

        $databaseUrl = "postgresql+psycopg://leadflow:$password@127.0.0.1:$Port/leadflow"
        $localEnv = @(
            "DATABASE_URL=$databaseUrl"
            'APP_ORIGIN=http://localhost:8080'
            'ADDITIONAL_ALLOWED_ORIGINS=http://127.0.0.1:8080'
            'SESSION_COOKIE_SECURE=false'
        ) -join [Environment]::NewLine
        [System.IO.File]::WriteAllText($localEnvFile, $localEnv + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        Write-Output "Portable PostgreSQL is ready on 127.0.0.1:$Port. Local secrets are stored under ignored .runtime/."
    }
    'stop' {
        if (Test-Path -LiteralPath (Join-Path $dataDir 'postmaster.pid')) {
            & $pgCtl stop -D $dataDir -m fast -w
            if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed to stop' }
        }
        Write-Output 'Portable PostgreSQL is stopped.'
    }
    'status' {
        if (Test-PostgresReady) {
            Write-Output "Portable PostgreSQL is ready on 127.0.0.1:$Port."
            exit 0
        }
        Write-Output 'Portable PostgreSQL is not ready.'
        exit 1
    }
}
