[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$logDir = Join-Path $runtimeRoot 'logs'
$python = Join-Path $runtimeRoot 'venv\Scripts\python.exe'
$node = (Get-Command node -ErrorAction Stop).Source
$vite = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
$processFile = Join-Path $runtimeRoot 'demo-processes.json'

function Get-TrackedProcess([string]$name, [string]$processName) {
    $entry = $script:trackedEntries | Where-Object Name -eq $name | Select-Object -First 1
    if ($null -eq $entry) { return $null }
    $process = Get-Process -Id $entry.Id -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.ProcessName -ne $processName) { return $null }
    $recordedStart = ([datetime]$entry.StartTimeUtc).ToUniversalTime()
    if ($process.StartTime.ToUniversalTime() -ne $recordedStart) { return $null }
    return $process
}

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

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
& (Join-Path $PSScriptRoot 'portable-postgres.ps1') start

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Local Python environment is missing. Create .runtime/venv and install backend[dev].'
}
if (-not (Test-Path -LiteralPath $vite)) {
    throw 'Frontend dependencies are missing. Run npm ci in frontend/.'
}

$trackedEntries = @()
if (Test-Path -LiteralPath $processFile) {
    $trackedEntries = @(Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json)
}
$backend = Get-TrackedProcess 'backend' 'python'
$worker = Get-TrackedProcess 'worker' 'python'
$frontend = Get-TrackedProcess 'frontend' 'node'

if ($null -eq $backend -and (Test-PortOpen 8000)) {
    throw 'Port 8000 is occupied by an untracked process. LeadFlow did not change it.'
}
if ($null -eq $frontend -and (Test-PortOpen 8080)) {
    throw 'Port 8080 is occupied by an untracked process. LeadFlow did not change it.'
}

. (Join-Path $PSScriptRoot 'load-env.ps1') -Path (Join-Path $runtimeRoot 'local.env')
$aiEnvFile = Join-Path $runtimeRoot 'ai.env'
if (Test-Path -LiteralPath $aiEnvFile) {
    . (Join-Path $PSScriptRoot 'load-env.ps1') -Path $aiEnvFile
}
$notificationEnvFile = Join-Path $runtimeRoot 'notifications.env'
if (Test-Path -LiteralPath $notificationEnvFile) {
    . (Join-Path $PSScriptRoot 'load-env.ps1') -Path $notificationEnvFile
}

Push-Location (Join-Path $projectRoot 'backend')
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
} finally {
    Pop-Location
}

$started = @()
if ($null -eq $backend) {
    $backend = Start-Process -FilePath $python `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
        -WorkingDirectory (Join-Path $projectRoot 'backend') `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'backend.out.log') `
        -RedirectStandardError (Join-Path $logDir 'backend.err.log') `
        -PassThru
    $started += $backend
}

$backendReady = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($backend.HasExited) { break }
    try {
        $backendHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
        if ($backendHealth.status -eq 'ok') {
            $backendReady = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 250
    }
}
if (-not $backendReady) {
    foreach ($process in $started) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id }
    }
    throw "LeadFlow backend did not become ready after migrations. Inspect $logDir."
}

if ($null -eq $worker) {
    $worker = Start-Process -FilePath $python `
        -ArgumentList '-m', 'app.worker' `
        -WorkingDirectory (Join-Path $projectRoot 'backend') `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'worker.out.log') `
        -RedirectStandardError (Join-Path $logDir 'worker.err.log') `
        -PassThru
    $started += $worker
}

if ($null -eq $frontend) {
    $frontend = Start-Process -FilePath $node `
        -ArgumentList $vite, '--host', '127.0.0.1', '--port', '8080', '--strictPort' `
        -WorkingDirectory (Join-Path $projectRoot 'frontend') `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'frontend.out.log') `
        -RedirectStandardError (Join-Path $logDir 'frontend.err.log') `
        -PassThru
    $started += $frontend
}

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    foreach ($namedProcess in @(
        [pscustomobject]@{ Name = 'backend'; Process = $backend }
        [pscustomobject]@{ Name = 'worker'; Process = $worker }
        [pscustomobject]@{ Name = 'frontend'; Process = $frontend }
    )) {
        if ($null -eq $namedProcess.Process -or $namedProcess.Process.HasExited) {
            foreach ($other in $started) {
                if (-not $other.HasExited) { Stop-Process -Id $other.Id }
            }
            throw "LeadFlow $($namedProcess.Name) process is not running. Inspect $logDir."
        }
    }
    try {
        $api = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health' -TimeoutSec 2
        $web = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8080/' -TimeoutSec 2
        if ($api.status -eq 'ok' -and $web.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 250
    }
}

if (-not $ready) {
    foreach ($process in $started) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id }
    }
    throw "Local demo did not become ready through port 8080. Inspect $logDir."
}

$metadata = @(
    [pscustomobject]@{ Name = 'backend'; Id = $backend.Id; StartTimeUtc = $backend.StartTime.ToUniversalTime().ToString('O') }
    [pscustomobject]@{ Name = 'worker'; Id = $worker.Id; StartTimeUtc = $worker.StartTime.ToUniversalTime().ToString('O') }
    [pscustomobject]@{ Name = 'frontend'; Id = $frontend.Id; StartTimeUtc = $frontend.StartTime.ToUniversalTime().ToString('O') }
)
[System.IO.File]::WriteAllText($processFile, ($metadata | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))

Write-Output 'LeadFlow local demo is ready at http://localhost:8080.'
