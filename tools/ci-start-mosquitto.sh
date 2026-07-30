#!/usr/bin/env bash
# Start an isolated Mosquitto broker for CI integration tests on self-hosted runners.
set -euo pipefail

RUN_ID="${GITHUB_RUN_ID:-$$}"
JOB_ID="${GITHUB_JOB:-local}"
CONTAINER_NAME="ci-mosquitto-${RUN_ID}-${JOB_ID}"

pick_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

PORT="$(pick_port)"
CONFIG_DIR="$(mktemp -d)"
trap 'rm -rf "${CONFIG_DIR}"' EXIT

cat > "${CONFIG_DIR}/mosquitto.conf" <<EOF
listener 1883
allow_anonymous true
EOF

docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

# Config goes in via `docker cp`, NOT a bind mount. A bind mount silently assumes the
# Docker daemon can see the runner's own filesystem. That holds when the daemon runs on
# the same host (GitHub-hosted runners), but not on the org's ARC pods, where the daemon
# does not share the runner's /tmp: it finds no such source path, creates an empty
# *directory* there, and the run dies with
#   "not a directory: Are you trying to mount a directory onto a file (or vice-versa)?"
# `docker cp` goes through the daemon API instead, so it works either way.
docker create --name "${CONTAINER_NAME}" \
  -p "127.0.0.1:${PORT}:1883" \
  eclipse-mosquitto:2 >/dev/null
docker cp "${CONFIG_DIR}/mosquitto.conf" "${CONTAINER_NAME}:/mosquitto/config/mosquitto.conf"
docker start "${CONTAINER_NAME}" >/dev/null

for _ in $(seq 1 12); do
  if command -v nc >/dev/null && nc -z "127.0.0.1" "${PORT}" 2>/dev/null; then
    echo "Mosquitto is ready (${CONTAINER_NAME} on 127.0.0.1:${PORT})"
    if [[ -n "${GITHUB_ENV:-}" ]]; then
      {
        echo "MQTT_TEST_HOST=127.0.0.1"
        echo "MQTT_TEST_PORT=${PORT}"
        echo "CI_MOSQUITTO_PORT=${PORT}"
        echo "CI_MOSQUITTO_CONTAINER=${CONTAINER_NAME}"
      } >> "${GITHUB_ENV}"
    fi
    exit 0
  fi
  sleep 2
done

echo "Mosquitto failed to start in ${CONTAINER_NAME}. Is Docker available?"
exit 1
