[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$configPath = Join-Path $runtimeRoot 'notifications.env'

function New-RandomValue([int]$byteCount = 48) {
    $bytes = New-Object byte[] $byteCount
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
if (Test-Path -LiteralPath $configPath) {
    Write-Output 'Local notification configuration already exists; nothing was overwritten.'
    return
}

$lines = @(
    '# Local-only notification and n8n settings. Never commit or print secret values.'
    'NOTIFICATIONS_ENABLED=false'
    'TELEGRAM_BOT_TOKEN='
    'TELEGRAM_CHAT_ID='
    "NOTIFICATIONS_SERVICE_TOKEN=$(New-RandomValue)"
    'NOTIFICATION_REMINDER_MINUTES=30'
    'MANAGER_PUBLIC_URL=http://localhost:8080'
    'N8N_POSTGRES_DB=leadflow_n8n'
    'N8N_POSTGRES_USER=leadflow_n8n'
    "N8N_POSTGRES_PASSWORD=$(New-RandomValue)"
    "N8N_ENCRYPTION_KEY=$(New-RandomValue)"
)
[System.IO.File]::WriteAllLines($configPath, $lines, [System.Text.UTF8Encoding]::new($false))
Write-Output 'Created ignored .runtime/notifications.env with blank Telegram fields and random local service/database/encryption secrets.'
