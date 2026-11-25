# syntax=docker/dockerfile:1
# Stage 1 builds the console (Next.js static export); stage 2 is the Python server that
# serves the console and the API from one port.

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build:static

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ZEALEAD_DB=/app/data/zealead.db \
    ZEALEAD_KEYS_DIR=/app/keys \
    ZEALEAD_BIND_ADDR=0.0.0.0 \
    ZEALEAD_PORT=8790

WORKDIR /src
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY zealead ./zealead
COPY --from=web /web/out ./zealead/webui
RUN pip install . \
    && cd / && rm -rf /src \
    && useradd --create-home --uid 10001 zealead \
    && mkdir -p /app/data /app/keys \
    && chown zealead /app/data /app/keys \
    && chmod 700 /app/keys

WORKDIR /app
USER zealead
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/api/health')"
CMD ["zealead", "serve"]
