[CmdletBinding()]
param(
    [switch]$TestDatabase,
    [string]$BackendBaseUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$node = Join-Path $runtimeRoot 'node24\node-v24.22.1-win-x64\node.exe'
$n8n = Join-Path $runtimeRoot 'n8n\node_modules\n8n\bin\n8n'
$importRoot = Join-Path $runtimeRoot $(if ($TestDatabase) { 'n8n-test-import' } else { 'n8n-import' })
$workflowRoot = Join-Path $importRoot 'workflows'

if (-not (Test-Path -LiteralPath $node) -or -not (Test-Path -LiteralPath $n8n)) {
    throw 'Project-local Node 24 and n8n 2.44.6 are required.'
}
if ($BackendBaseUrl -notmatch '^http://(127\.0\.0\.1|localhost|backend)(:\d+)?$') {
    throw 'BackendBaseUrl must be an expected local or Compose HTTP origin.'
}

New-Item -ItemType Directory -Force -Path $workflowRoot | Out-Null
. (Join-Path $PSScriptRoot 'set-local-n8n-env.ps1') -TestDatabase:$TestDatabase

$sourceFiles = @(
    'leadflow-new-lead-notifications.json'
    'leadflow-reminder-notifications.json'
)
foreach ($filename in $sourceFiles) {
    $source = Join-Path $projectRoot "automation\n8n\$filename"
    $workflow = Get-Content -Raw -LiteralPath $source | ConvertFrom-Json
    $requestNode = $workflow.nodes | Where-Object type -eq 'n8n-nodes-base.httpRequest' | Select-Object -First 1
    if ($null -eq $requestNode) { throw "HTTP Request node is missing in $filename" }
    $requestNode.parameters.url = "$BackendBaseUrl/api/internal/notifications/dispatch"
    if ($TestDatabase) {
        $manualName = 'Fixture manual trigger'
        $workflow.nodes += [pscustomobject][ordered]@{
            parameters = [pscustomobject]@{}
            id = "fixture-manual-$($workflow.id)"
            name = $manualName
            type = 'n8n-nodes-base.manualTrigger'
            typeVersion = 1
            position = @(-260, 0)
        }
        $edge = [pscustomobject][ordered]@{
            node = $requestNode.name
            type = 'main'
            index = 0
        }
        $manualConnection = [pscustomobject]@{ main = @(, @($edge)) }
        $workflow.connections | Add-Member -NotePropertyName $manualName -NotePropertyValue $manualConnection
    }
    $target = Join-Path $workflowRoot $filename
    [System.IO.File]::WriteAllText($target, ($workflow | ConvertTo-Json -Depth 100), [System.Text.UTF8Encoding]::new($false))
}

$credential = @(
    [ordered]@{
        id = 'leadflow-backend-dispatch-auth'
        name = 'LeadFlow Backend Dispatch Auth'
        type = 'httpHeaderAuth'
        data = [ordered]@{
            name = 'Authorization'
            value = "Bearer $($env:NOTIFICATIONS_SERVICE_TOKEN)"
        }
    }
)
$credentialPath = Join-Path $importRoot 'leadflow-backend-dispatch-auth.json'
[System.IO.File]::WriteAllText($credentialPath, ($credential | ConvertTo-Json -Depth 10 -AsArray), [System.Text.UTF8Encoding]::new($false))

& $node $n8n import:credentials --input $credentialPath | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'n8n credential import failed.' }
& $node $n8n import:workflow --separate --input $workflowRoot | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'n8n workflow import failed.' }

Write-Output 'Imported two inactive LeadFlow workflows and the encrypted Header Auth credential into PostgreSQL-backed n8n.'
