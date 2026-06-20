# Multi-stage not required — headless MQTT bridge with no frontend.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system modeldeck \
    && useradd --system --gid modeldeck --home-dir /app modeldeck

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir ".[service]"

RUN mkdir -p /config /data \
    && chown -R modeldeck:modeldeck /app /config /data

USER modeldeck

CMD ["modeldeck-service"]
