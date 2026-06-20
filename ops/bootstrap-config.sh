#!/usr/bin/env bash
# Seed ./config and ./data for docker compose bind mounts.
# Usage: ./ops/bootstrap-config.sh [quickstart|production]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-quickstart}"

mkdir -p "$ROOT/config" "$ROOT/data"

if [[ "$MODE" == "production" ]]; then
  SRC="$ROOT/templates/modeldeck.example.yaml"
else
  SRC="$ROOT/templates/modeldeck.quickstart.yaml"
fi

cp "$SRC" "$ROOT/config/modeldeck.yaml"
cp "$ROOT/templates/secrets.example.yaml" "$ROOT/config/secrets.yaml"
chmod 600 "$ROOT/config/secrets.yaml" 2>/dev/null || true

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example"
fi

echo "Config ready in $ROOT/config (mode: $MODE)"
echo "Edit config/modeldeck.yaml and config/secrets.yaml, then:"
echo "  docker compose -f templates/docker-compose.yml up -d"
