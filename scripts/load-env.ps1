param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

Get-Content -LiteralPath $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    $name, $value = $line -split '=', 2
    if (-not $name -or $null -eq $value) { throw "Invalid env line in ${Path}: $line" }
    Set-Item -Path "Env:$name" -Value $value
}
