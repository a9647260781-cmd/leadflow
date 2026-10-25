param(
    [switch]$TestDatabase,
    [int]$Port = 5678,
    [string]$UserFolder
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
. (Join-Path $PSScriptRoot 'load-env.ps1') -Path (Join-Path $runtimeRoot 'notifications.env')

$database = if ($TestDatabase) { "$($env:N8N_POSTGRES_DB)_test" } else { $env:N8N_POSTGRES_DB }
$env:DB_TYPE = 'postgresdb'
$env:DB_POSTGRESDB_HOST = '127.0.0.1'
$env:DB_POSTGRESDB_PORT = '55432'
$env:DB_POSTGRESDB_DATABASE = $database
$env:DB_POSTGRESDB_USER = $env:N8N_POSTGRES_USER
$env:DB_POSTGRESDB_PASSWORD = $env:N8N_POSTGRES_PASSWORD
$env:N8N_HOST = '127.0.0.1'
$env:N8N_PORT = "$Port"
$env:N8N_RUNNERS_BROKER_PORT = if ($TestDatabase) { '5681' } else { '5679' }
$env:N8N_PROTOCOL = 'http'
$env:N8N_EDITOR_BASE_URL = "http://127.0.0.1:$Port"
$env:N8N_SECURE_COOKIE = 'false'
$env:GENERIC_TIMEZONE = 'Europe/Moscow'
$env:TZ = 'Europe/Moscow'
$env:N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS = 'false'
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = 'true'
$env:N8N_DIAGNOSTICS_ENABLED = 'false'
$env:N8N_PERSONALIZATION_ENABLED = 'false'
$env:N8N_VERSION_NOTIFICATIONS_ENABLED = 'false'
$env:N8N_TEMPLATES_ENABLED = 'false'
$env:N8N_USER_FOLDER = if ($UserFolder) { $UserFolder } elseif ($TestDatabase) { Join-Path $runtimeRoot 'n8n-test-data' } else { Join-Path $runtimeRoot 'n8n-data' }
