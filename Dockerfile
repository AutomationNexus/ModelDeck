# syntax=docker/dockerfile:1.4
# Multi-stage: Node builds the Vite UI into src/modeldeck/webui/static/;
# runtime stays on python:3.11-slim. Node is not in the final image.

# ---------- Stage 1: Vite/React dashboard ----------
FROM node:24-bookworm-slim AS frontend

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# outDir is ../src/modeldeck/webui/static relative to frontend/ (see vite.config.ts)
RUN npm run build

# ---------- Stage 2: runtime (Python service + baked UI) ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system modeldeck \
    && useradd --system --gid modeldeck --home-dir /app modeldeck

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Copy built UI assets before pip install so they land in the wheel.
COPY --from=frontend /build/src/modeldeck/webui/static/ ./src/modeldeck/webui/static/

RUN python -m pip install --no-cache-dir ".[service]"

RUN mkdir -p /config /data \
    && chown -R modeldeck:modeldeck /app /config /data

USER modeldeck

CMD ["modeldeck-service"]
