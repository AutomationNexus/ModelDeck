#!/usr/bin/env bash
# Run backend tests from repo root (subset of scripts/check.sh).
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python}"
if [[ -x .venv/bin/python ]]; then
  PYTHON=".venv/bin/python"
fi

"$PYTHON" tests/check_test_standards.py
"$PYTHON" -m pytest -m "not integration" -p no:cacheprovider --cov=src/modeldeck --cov-report=term-missing:skip-covered --cov-fail-under=97
