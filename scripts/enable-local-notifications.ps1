[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$configPath = Join-Path $runtimeRoot 'notifications.env'
$node = Join-Path $runtimeRoot 'node24\node-v24.22.1-win-x64\node.exe'
$n8n = Join-Path $runtimeRoot 'n8n\node_modules\n8n\bin\n8n'

if (-not (Test-Path -LiteralPath $configPath)) {
    throw 'Run scripts/create-local-notification-config.ps1 and fill Telegram settings first.'
}
. (Join-Path $PSScriptRoot 'load-env.ps1') -Path $configPath
if ($env:NOTIFICATIONS_ENABLED -ne 'true') {
    throw 'Set NOTIFICATIONS_ENABLED=true in .runtime/notifications.env first.'
}
foreach ($name in @('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'NOTIFICATIONS_SERVICE_TOKEN')) {
    if (-not (Get-Item "Env:$name" -ErrorAction SilentlyContinue).Value) {
        throw "$name must be configured in .runtime/notifications.env."
    }
}
if (-not (Test-Path -LiteralPath $node) -or -not (Test-Path -LiteralPath $n8n)) {
    throw 'Run scripts/install-local-n8n.ps1 first.'
}

& (Join-Path $PSScriptRoot 'stop-local-n8n.ps1') | Out-Null
& (Join-Path $PSScriptRoot 'initialize-local-n8n-db.ps1') | Out-Null
& (Join-Path $PSScriptRoot 'import-local-n8n-workflows.ps1') | Out-Null
. (Join-Path $PSScriptRoot 'set-local-n8n-env.ps1')
foreach ($workflowId in @('leadflow-new-lead-notifications-v1', 'leadflow-reminder-notifications-v1')) {
    & $node $n8n publish:workflow --id $workflowId | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not publish n8n workflow $workflowId." }
}

& (Join-Path $PSScriptRoot 'stop-local-demo.ps1') -KeepPostgres | Out-Null
& (Join-Path $PSScriptRoot 'start-local-demo.ps1') | Out-Null
& (Join-Path $PSScriptRoot 'start-local-n8n.ps1') -SkipImport | Out-Null
if ($env:MANAGER_PUBLIC_URL -match '^http://(localhost|127\.0\.0\.1)(:\d+)?$') {
    Write-Warning 'MANAGER_PUBLIC_URL points to this computer. Telegram links will not open on a phone until you configure a reachable URL; no tunnel was created.'
}
Write-Output 'Local Telegram notifications are enabled and both n8n workflows are published.'
