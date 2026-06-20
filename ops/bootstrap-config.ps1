# Seed ./config and ./data for docker compose bind mounts.
# Usage: .\ops\bootstrap-config.ps1 [-Mode quickstart|production]
param(
    [ValidateSet("quickstart", "production")]
    [string]$Mode = "quickstart"
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ConfigDir = Join-Path $Root "config"
$DataDir = Join-Path $Root "data"

New-Item -ItemType Directory -Force -Path $ConfigDir, $DataDir | Out-Null

$Src = if ($Mode -eq "production") {
    Join-Path $Root "templates\modeldeck.example.yaml"
} else {
    Join-Path $Root "templates\modeldeck.quickstart.yaml"
}

Copy-Item -Force $Src (Join-Path $ConfigDir "modeldeck.yaml")
Copy-Item -Force (Join-Path $Root "templates\secrets.example.yaml") (Join-Path $ConfigDir "secrets.yaml")

$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item -Force (Join-Path $Root ".env.example") $EnvFile
    Write-Host "Created .env from .env.example"
}

Write-Host "Config ready in $ConfigDir (mode: $Mode)"
Write-Host "Edit config\modeldeck.yaml and config\secrets.yaml, then:"
Write-Host "  docker compose -f templates/docker-compose.yml up -d"
