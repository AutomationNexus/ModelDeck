#!/usr/bin/env bash
# Fail CI when provider tokens are read from raw environment variables.
set -euo pipefail

fail=0

check() {
  local label="$1"
  local pattern="$2"
  local path="$3"
  if rg -n "$pattern" "$path" 2>/dev/null; then
    echo "FAIL: $label"
    fail=1
  else
    echo "OK: $label"
  fi
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

check "provider API keys via os.environ" \
  'os\.environ\.get\("(OPENAI|CLAUDE|CURSOR|CODEX)' \
  "$ROOT/src/modeldeck/"

check "provider session tokens via os.environ" \
  'os\.environ\.(get|\[)\("(SESSION|API_KEY)' \
  "$ROOT/src/modeldeck/collectors/"

exit "$fail"
