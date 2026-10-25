[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$downloadRoot = Join-Path $runtimeRoot 'downloads'
$nodeVersion = '24.22.1'
$n8nVersion = '2.44.6'
$archiveName = "node-v$nodeVersion-win-x64.zip"
$archivePath = Join-Path $downloadRoot $archiveName
$checksumPath = Join-Path $downloadRoot "SHASUMS256-node-v$nodeVersion.txt"
$nodeRoot = Join-Path $runtimeRoot 'node24'
$nodeVersionRoot = Join-Path $nodeRoot "node-v$nodeVersion-win-x64"
$node = Join-Path $nodeVersionRoot 'node.exe'
$npmCli = Join-Path $nodeVersionRoot 'node_modules\npm\bin\npm-cli.js'
$n8nRoot = Join-Path $runtimeRoot 'n8n'
$n8nCli = Join-Path $n8nRoot 'node_modules\n8n\bin\n8n'

New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
if (-not (Test-Path -LiteralPath $archivePath)) {
    Invoke-WebRequest -UseBasicParsing -Uri "https://nodejs.org/dist/v$nodeVersion/$archiveName" -OutFile $archivePath
}
if (-not (Test-Path -LiteralPath $checksumPath)) {
    Invoke-WebRequest -UseBasicParsing -Uri "https://nodejs.org/dist/v$nodeVersion/SHASUMS256.txt" -OutFile $checksumPath
}
$expectedLine = Get-Content -LiteralPath $checksumPath | Where-Object { $_ -match "$([regex]::Escape($archiveName))$" } | Select-Object -First 1
if (-not $expectedLine) { throw 'Official Node.js checksum entry was not found.' }
$expected = ($expectedLine -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Portable Node.js archive checksum mismatch.' }

if (-not (Test-Path -LiteralPath $node)) {
    New-Item -ItemType Directory -Force -Path $nodeRoot | Out-Null
    Expand-Archive -LiteralPath $archivePath -DestinationPath $nodeRoot
}
& $node $npmCli install --prefix $n8nRoot --save-exact "n8n@$n8nVersion"
if ($LASTEXITCODE -ne 0) { throw 'Project-local n8n installation failed.' }
$installed = & $node $n8nCli --version
if ($installed.Trim() -ne $n8nVersion) { throw "Unexpected n8n version: $installed" }
Write-Output "Installed project-local n8n $n8nVersion on verified portable Node $nodeVersion."
