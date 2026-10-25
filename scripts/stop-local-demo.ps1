[CmdletBinding()]
param(
    [switch]$KeepPostgres
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $projectRoot '.runtime\demo-processes.json'

if (Test-Path -LiteralPath $processFile) {
    $entries = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    foreach ($entry in $entries) {
        $process = Get-Process -Id $entry.Id -ErrorAction SilentlyContinue
        if ($null -eq $process) { continue }
        $sameStart = $process.StartTime.ToUniversalTime() -eq ([datetime]$entry.StartTimeUtc).ToUniversalTime()
        $allowedName = $process.ProcessName -in @('python', 'node')
        if ($sameStart -and $allowedName) {
            Stop-Process -Id $process.Id
        }
    }
    Remove-Item -LiteralPath $processFile
}

if (-not $KeepPostgres) {
    & (Join-Path $PSScriptRoot 'portable-postgres.ps1') stop
}

Write-Output 'LeadFlow local demo is stopped.'
