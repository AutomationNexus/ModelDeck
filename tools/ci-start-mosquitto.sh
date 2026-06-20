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
docker run -d --name "${CONTAINER_NAME}" \
  -p "127.0.0.1:${PORT}:1883" \
  -v "${CONFIG_DIR}/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" \
  eclipse-mosquitto:2

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
