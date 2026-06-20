#!/usr/bin/env bash
# Mirror CI quality gates locally. Run from repo root: ./scripts/check.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FIX=false
INTEGRATION=false
QUICK=false

usage() {
  cat <<'EOF'
Usage: ./scripts/check.sh [--fix] [--integration] [--quick]

  --fix          Auto-fix ruff issues and format files
  --integration  Also run Mosquitto integration tests (MQTT_TEST_HOST required)
  --quick        Lint and format only (skip tests and validators)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix) FIX=true ;;
    --integration) INTEGRATION=true ;;
    --quick) QUICK=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

PYTHON="${PYTHON:-python}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

echo "==> ruff"
if [[ "$FIX" == true ]]; then
  "$PYTHON" -m ruff check src tests tools --fix
  "$PYTHON" -m ruff format src tests tools
else
  "$PYTHON" -m ruff check src tests tools
  "$PYTHON" -m ruff format --check src tests tools
fi

echo "==> operator env gates"
bash "$ROOT/tools/check-operator-env-gates.sh"

if [[ "$QUICK" == true ]]; then
  echo "Quick check complete."
  exit 0
fi

echo "==> test standards"
"$PYTHON" tests/check_test_standards.py

echo "==> doc entity IDs"
"$PYTHON" tests/check_docs_entity_ids.py

echo "==> pytest (unit, 97% coverage)"
"$PYTHON" -m pytest \
  -m "not integration" \
  -p no:cacheprovider \
  --cov=src/modeldeck \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=97

echo "==> config validate"
"$PYTHON" -m modeldeck config validate --config templates/modeldeck.example.yaml

if [[ "$INTEGRATION" == true ]]; then
  echo "==> integration (Mosquitto)"
  "$PYTHON" -m pytest -m integration -v --tb=short
fi

echo "All checks passed."
