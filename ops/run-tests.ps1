# Run backend tests from repo root (subset of scripts/check.ps1).
param()

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

$Python = "python"
$venvPython = Join-Path $PWD ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $Python = $venvPython
}

& $Python tests/check_test_standards.py
& $Python -m pytest -m "not integration" -p no:cacheprovider --cov=src/modeldeck --cov-report=term-missing:skip-covered --cov-fail-under=97
