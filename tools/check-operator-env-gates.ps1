# Fail when provider tokens are read from raw environment variables.
# PowerShell port of tools/check-operator-env-gates.sh for Windows dev.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$fail = 0

function Test-EnvGate {
    param(
        [string]$Label,
        [string]$Pattern,
        [string]$Path
    )
    if (-not (Test-Path $Path)) {
        Write-Host "OK: $Label (path missing, skipped)"
        return
    }
    $files = Get-ChildItem -Path $Path -Recurse -File -Filter "*.py" -ErrorAction SilentlyContinue
    $matches = $files | Select-String -Pattern $Pattern -ErrorAction SilentlyContinue
    if ($matches) {
        Write-Host "FAIL: $Label"
        $matches | ForEach-Object { Write-Host $_.Line }
        $script:fail = 1
    } else {
        Write-Host "OK: $Label"
    }
}

Test-EnvGate "provider API keys via os.environ" `
    'os\.environ\.get\("(OPENAI|CLAUDE|CURSOR|CODEX)' `
    (Join-Path $Root "src\modeldeck")

Test-EnvGate "provider session tokens via os.environ" `
    'os\.environ\.(get|\[)\("(SESSION|API_KEY)' `
    (Join-Path $Root "src\modeldeck\collectors")

if ($fail -ne 0) {
    exit 1
}
