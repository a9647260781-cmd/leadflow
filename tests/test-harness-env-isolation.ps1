[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$harnesses = @(
    'scripts\run-ai-mock-integration.ps1',
    'scripts\run-recovery-backup-integration.ps1',
    'scripts\run-notification-n8n-integration.ps1'
)
$sentinelNames = @(
    'DATABASE_URL',
    'AI_ENABLED',
    'YANDEX_API_KEY',
    'YANDEX_MODEL_URI',
    'YANDEX_API_URL',
    'NOTIFICATIONS_ENABLED',
    'TELEGRAM_BOT_TOKEN',
    'N8N_ENCRYPTION_KEY',
    'N8N_POSTGRES_PASSWORD',
    'DB_POSTGRESDB_DATABASE',
    'PGPASSWORD'
)

function Get-ProcessEnvironment {
    $snapshot = @{}
    Get-ChildItem Env: | ForEach-Object { $snapshot[$_.Name] = $_.Value }
    return $snapshot
}

function Assert-EnvironmentEqual([hashtable]$expected, [hashtable]$actual, [string]$label) {
    $allNames = @($expected.Keys + $actual.Keys | Sort-Object -Unique)
    foreach ($name in $allNames) {
        if (-not $expected.ContainsKey($name) -or -not $actual.ContainsKey($name)) {
            throw "$label changed environment variable membership: $name"
        }
        if ($expected[$name] -cne $actual[$name]) {
            throw "$label changed environment variable value: $name"
        }
    }
}

$saved = @{}
foreach ($name in $sentinelNames) {
    $saved[$name] = [pscustomobject]@{
        Exists = Test-Path "Env:$name"
        Value = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    [Environment]::SetEnvironmentVariable($name, "parent-sentinel-$name", 'Process')
}

try {
    Push-Location $projectRoot
    try {
        foreach ($relativePath in $harnesses) {
            $beforeSuccess = Get-ProcessEnvironment
            & (Join-Path $projectRoot $relativePath) -IsolationProbe | Out-Null
            Assert-EnvironmentEqual $beforeSuccess (Get-ProcessEnvironment) "$relativePath success"

            $beforeFailure = Get-ProcessEnvironment
            $failedAsExpected = $false
            try {
                & (Join-Path $projectRoot $relativePath) -IsolationProbe -InjectIsolationFailure `
                    *> $null
            } catch {
                $failedAsExpected = $true
            }
            if (-not $failedAsExpected) { throw "$relativePath injected failure did not fail" }
            Assert-EnvironmentEqual $beforeFailure (Get-ProcessEnvironment) "$relativePath failure"
        }
    } finally {
        Pop-Location
    }
} finally {
    foreach ($name in $sentinelNames) {
        if ($saved[$name].Exists) {
            [Environment]::SetEnvironmentVariable($name, $saved[$name].Value, 'Process')
        } else {
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
    }
}

Write-Output 'PASS harness environment isolation after child success and injected failure.'
