#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${MODELDECK_CONFIG_DIR:-/config}"
OPTIONS_FILE="/data/options.json"
RUN_AS_USER="${MODELDECK_RUN_AS_USER:-modeldeck}"
LOCAL_OPTIONS="${CONFIG_DIR}/.addon-options.json"
WEBUI_PORT="${MODELDECK_WEBUI_PORT:-8099}"

export MODELDECK_CONFIG_DIR="${CONFIG_DIR}"
# HAOS mounts Supervisor options at /data (root-only). Persistent writable storage is /config.
STATE_DIR="${CONFIG_DIR}/data"
export MODELDECK_DATA_DIR="${STATE_DIR}"

if [[ ! -f "${OPTIONS_FILE}" ]]; then
  echo "Missing ${OPTIONS_FILE} — add-on options not mounted" >&2
  exit 1
fi

mkdir -p "${CONFIG_DIR}" "${STATE_DIR}"

# Supervisor mounts /data as root-only (dir + file). chmod on the file alone is not
# enough: non-root users also need execute on /data to traverse it. Copy options
# into /config as root, then run render/service as modeldeck.
if [[ "$(id -u)" -eq 0 ]]; then
  install -m 640 -o "${RUN_AS_USER}" -g "${RUN_AS_USER}" \
    "${OPTIONS_FILE}" "${LOCAL_OPTIONS}"
  chown -R "${RUN_AS_USER}:${RUN_AS_USER}" "${CONFIG_DIR}" "${STATE_DIR}"
else
  if [[ ! -r "${OPTIONS_FILE}" ]]; then
    echo "ERROR: cannot read ${OPTIONS_FILE} as uid=$(id -u)." >&2
    echo "Rebuild or reinstall the ModelDeck add-on so /run.sh starts as root." >&2
    exit 1
  fi
  LOCAL_OPTIONS="${OPTIONS_FILE}"
fi

run_as() {
  if [[ "$(id -un)" == "${RUN_AS_USER}" ]]; then
    "$@"
    return
  fi
  if command -v runuser >/dev/null 2>&1; then
    runuser -u "${RUN_AS_USER}" -- "$@"
    return
  fi
  if command -v gosu >/dev/null 2>&1; then
    gosu "${RUN_AS_USER}" "$@"
    return
  fi
  echo "Cannot drop privileges to ${RUN_AS_USER}" >&2
  exit 1
}

echo "Rendering configuration from add-on options..."
run_as modeldeck config render-addon --options "${LOCAL_OPTIONS}" --config-dir "${CONFIG_DIR}"

echo "Starting ModelDeck web UI on port ${WEBUI_PORT}..."
run_as modeldeck webui --host 0.0.0.0 --port "${WEBUI_PORT}" &
WEBUI_PID=$!

echo "Starting ModelDeck service..."
# Trap signals so both processes are cleaned up together.
_shutdown() {
  echo "Shutting down ModelDeck..."
  kill "${WEBUI_PID}" 2>/dev/null || true
  wait "${WEBUI_PID}" 2>/dev/null || true
  exit 0
}
trap _shutdown SIGTERM SIGINT

if [[ "$(id -un)" == "${RUN_AS_USER}" ]]; then
  modeldeck-service &
else
  runuser -u "${RUN_AS_USER}" -- modeldeck-service &
fi
SERVICE_PID=$!

# Wait for either process to exit; exit with that process's code.
wait -n "${SERVICE_PID}" "${WEBUI_PID}" 2>/dev/null || true
EXIT_CODE=$?

# Clean up remaining process.
kill "${SERVICE_PID}" "${WEBUI_PID}" 2>/dev/null || true
wait "${SERVICE_PID}" "${WEBUI_PID}" 2>/dev/null || true
exit "${EXIT_CODE}"
