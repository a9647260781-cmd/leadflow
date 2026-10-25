[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $projectRoot '.runtime\n8n-process.json'
if (Test-Path -LiteralPath $processFile) {
    $entry = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    $process = Get-Process -Id $entry.Id -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        $sameStart = $process.StartTime.ToUniversalTime() -eq ([datetime]$entry.StartTimeUtc).ToUniversalTime()
        if ($sameStart -and $process.ProcessName -eq 'node') {
            Stop-Process -Id $process.Id
        }
    }
    Remove-Item -LiteralPath $processFile
}
Write-Output 'Local n8n is stopped; PostgreSQL metadata is preserved.'
