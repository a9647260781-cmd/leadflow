[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$credentialsFile = Join-Path $runtimeRoot 'demo-credentials.env'

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

if (Test-Path -LiteralPath $credentialsFile) {
    Write-Output 'Existing ignored demo credentials were preserved.'
    exit 0
}

$bytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$password = 'Lf!' + [Convert]::ToBase64String($bytes).Replace('+', 'A').Replace('/', 'B').TrimEnd('=')
$email = 'manager@example.com'

$content = @(
    "MANAGER_EMAIL=$email"
    'MANAGER_NAME=Менеджер LeadFlow'
    "MANAGER_PASSWORD=$password"
) -join [Environment]::NewLine

[System.IO.File]::WriteAllText(
    $credentialsFile,
    $content + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Output 'Generated ignored demo credentials in .runtime/demo-credentials.env.'
