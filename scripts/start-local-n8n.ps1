[CmdletBinding()]
param(
    [switch]$SkipImport
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$logDir = Join-Path $runtimeRoot 'logs'
$node = Join-Path $runtimeRoot 'node24\node-v24.22.1-win-x64\node.exe'
$n8n = Join-Path $runtimeRoot 'n8n\node_modules\n8n\bin\n8n'
$processFile = Join-Path $runtimeRoot 'n8n-process.json'

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

function Get-TrackedN8n {
    if (-not (Test-Path -LiteralPath $processFile)) { return $null }
    $entry = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    $process = Get-Process -Id $entry.Id -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.ProcessName -ne 'node') { return $null }
    if ($process.StartTime.ToUniversalTime() -ne ([datetime]$entry.StartTimeUtc).ToUniversalTime()) { return $null }
    return $process
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
& (Join-Path $PSScriptRoot 'create-local-notification-config.ps1') | Out-Null
& (Join-Path $PSScriptRoot 'initialize-local-n8n-db.ps1') | Out-Null
. (Join-Path $PSScriptRoot 'set-local-n8n-env.ps1')

$process = Get-TrackedN8n
$importedInactive = $false
if ($null -eq $process -and (Test-PortOpen 5678)) {
    throw 'Port 5678 is occupied by an untracked process. LeadFlow did not change it.'
}
if ($null -eq $process) {
    if (-not $SkipImport) {
        & (Join-Path $PSScriptRoot 'import-local-n8n-workflows.ps1') | Out-Null
        $importedInactive = $true
    }
    $process = Start-Process -FilePath $node -ArgumentList $n8n, 'start' `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'n8n.out.log') `
        -RedirectStandardError (Join-Path $logDir 'n8n.err.log')
}

$ready = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ($process.HasExited) { break }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5678/healthz/readiness' -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $ready) {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id }
    throw "n8n did not become ready. Inspect $logDir."
}

$metadata = [ordered]@{
    Id = $process.Id
    StartTimeUtc = $process.StartTime.ToUniversalTime().ToString('O')
}
[System.IO.File]::WriteAllText($processFile, ($metadata | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
$workflowState = if ($importedInactive) { 'LeadFlow workflows imported inactive' } else { 'existing workflow publication state preserved' }
Write-Output "Local PostgreSQL-backed n8n 2.44.6 is ready at http://127.0.0.1:5678; $workflowState."
