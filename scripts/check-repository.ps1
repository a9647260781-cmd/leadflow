[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$violations = [System.Collections.Generic.List[string]]::new()
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$textExtensions = @(
    '.css', '.env', '.example', '.html', '.ini', '.js', '.json', '.md', '.mjs',
    '.ps1', '.py', '.sh', '.toml', '.ts', '.tsx', '.txt', '.yaml', '.yml'
)
$requiredPortfolioFiles = @(
    'docs/PORTFOLIO_CASE.md',
    'docs/DEMO_SCRIPT.md',
    'docs/portfolio/README.md',
    'docs/portfolio/images/public-desktop.jpg',
    'docs/portfolio/images/public-mobile-390x844.jpg',
    'docs/portfolio/images/manager-demo-list.jpg',
    'docs/portfolio/images/lead-manual-extraction.jpg',
    'docs/portfolio/images/lead-not-configured-mobile-390x844.jpg'
)

function Add-Violation([string]$message) {
    $script:violations.Add($message)
}

Push-Location $projectRoot
try {
    $candidateFiles = @(git ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate Git-visible candidate files.' }

    foreach ($required in $requiredPortfolioFiles) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            Add-Violation "required portfolio file is missing: $required"
        } elseif ($candidateFiles -notcontains $required) {
            Add-Violation "required portfolio file is not Git-visible: $required"
        }
    }

    foreach ($path in $candidateFiles) {
        $normalized = $path.Replace('\', '/')
        if ($normalized -match '(^|/)(\.runtime|artifacts|node_modules|dist|coverage|htmlcov|test-results|playwright-report)(/|$)') {
            Add-Violation "forbidden generated/runtime path is Git-visible: $normalized"
            continue
        }
        if ($normalized -match '(^|/)\.env(?:\..+)?$' -and $normalized -notmatch '(^|/)\.env\.example$') {
            Add-Violation "local environment file is Git-visible: $normalized"
            continue
        }
        if ($normalized -match '\.(?:dump|sqlite3?|log|pem|p12|pfx|key)$') {
            Add-Violation "sensitive/generated file type is Git-visible: $normalized"
            continue
        }

        $extension = [IO.Path]::GetExtension($normalized).ToLowerInvariant()
        if ($textExtensions -notcontains $extension) { continue }
        try {
            $content = $utf8.GetString([IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $path)))
        } catch {
            Add-Violation "text file is not valid UTF-8: $normalized"
            continue
        }

        if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) {
            Add-Violation "text file has no final newline: $normalized"
        }
        $lineNumber = 0
        foreach ($line in ($content -split "`r?`n")) {
            $lineNumber++
            if ($line -match '[ \t]+$') {
                Add-Violation "trailing whitespace: ${normalized}:$lineNumber"
            }
        }

        $secretPatterns = @(
            '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            '(?<![A-Za-z0-9])AKIA[A-Z0-9]{16}(?![A-Za-z0-9])',
            '(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}',
            '(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}',
            '(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{20,}',
            '(?<![A-Za-z0-9])\d{8,10}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])',
            '(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}'
        )
        foreach ($pattern in $secretPatterns) {
            if ($content -match $pattern) {
                Add-Violation "possible credential signature in: $normalized"
                break
            }
        }

        if ($extension -eq '.md') {
            $matches = [regex]::Matches($content, '!??\[[^\]]*\]\((?<target>[^)]+)\)')
            foreach ($match in $matches) {
                $target = $match.Groups['target'].Value.Trim()
                if ($target.StartsWith('<') -and $target.EndsWith('>')) {
                    $target = $target.Substring(1, $target.Length - 2)
                }
                if (-not $target -or $target.StartsWith('#') -or $target -match '^[a-z][a-z0-9+.-]*:') {
                    continue
                }
                $target = ($target -split '#', 2)[0]
                $target = ($target -split '\?', 2)[0]
                if (-not $target) { continue }
                if ([IO.Path]::IsPathRooted($target)) {
                    Add-Violation "absolute local Markdown link in ${normalized}: $target"
                    continue
                }
                $decoded = [Uri]::UnescapeDataString($target)
                $baseDirectory = Split-Path -Parent $path
                if (-not $baseDirectory) { $baseDirectory = '.' }
                $resolved = Join-Path $baseDirectory $decoded
                if (-not (Test-Path -LiteralPath $resolved)) {
                    Add-Violation "broken local Markdown link in ${normalized}: $target"
                }
            }
        }
    }

    $ignoredExamples = @(
        '.env',
        '.runtime/example-secret.env',
        'artifacts/raw-qa.png',
        'frontend/node_modules/example.js',
        'frontend/dist/index.html',
        'example.log',
        'example.dump'
    )
    foreach ($path in $ignoredExamples) {
        git check-ignore -q --no-index -- $path
        if ($LASTEXITCODE -ne 0) { Add-Violation "expected ignored path is visible: $path" }
    }

    $uniqueViolations = @($violations | Sort-Object -Unique)
    if ($uniqueViolations.Count -gt 0) {
        Write-Output "FAIL repository candidate: $($uniqueViolations.Count) issue(s)."
        $uniqueViolations | ForEach-Object { Write-Output "- $_" }
        exit 1
    }
    Write-Output "PASS repository candidate: $($candidateFiles.Count) Git-visible files; required portfolio files, ignore rules, UTF-8, whitespace, local Markdown links and credential signatures checked."
} finally {
    Pop-Location
}
