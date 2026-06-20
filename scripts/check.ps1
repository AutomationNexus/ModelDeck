# Mirror CI quality gates locally. Run from repo root: .\scripts\check.ps1
param(
    [switch]$Fix,
    [switch]$Integration,
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

$Python = "python"
$venvPython = Join-Path $PWD ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $Python = $venvPython
}

Write-Host "==> ruff"
if ($Fix) {
    & $Python -m ruff check src tests tools --fix
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m ruff format src tests tools
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    & $Python -m ruff check src tests tools
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m ruff format --check src tests tools
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "==> operator env gates"
if ($env:OS -match "Windows") {
    & (Join-Path $PSScriptRoot "..\tools\check-operator-env-gates.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    bash (Join-Path $PWD "tools/check-operator-env-gates.sh")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Quick) {
    Write-Host "Quick check complete."
    exit 0
}

Write-Host "==> test standards"
& $Python tests/check_test_standards.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> doc entity IDs"
& $Python tests/check_docs_entity_ids.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> pytest (unit, 97% coverage)"
& $Python -m pytest `
    -m "not integration" `
    -p no:cacheprovider `
    --cov=src/modeldeck `
    --cov-report=term-missing:skip-covered `
    --cov-fail-under=97
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> config validate"
& $Python -m modeldeck config validate --config templates/modeldeck.example.yaml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Integration) {
    Write-Host "==> integration (Mosquitto)"
    & $Python -m pytest -m integration -v --tb=short
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "All checks passed."
