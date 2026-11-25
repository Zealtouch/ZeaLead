#!/usr/bin/env bash
# leadscout — build and start the console with Docker.
#
#   ./start.sh            build (first time / after an update) and start in the background
#   ./start.sh --no-build start without rebuilding
#
# Then open http://localhost:8790 and create the admin account.
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"

info(){ printf '\033[36m[*]\033[0m %s\n' "$*"; }
ok(){   printf '\033[32m[+]\033[0m %s\n' "$*"; }
warn(){ printf '\033[33m[!]\033[0m %s\n' "$*"; }
die(){  printf '\033[31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found — install Docker Desktop (macOS/Windows) or Docker Engine (Linux)"
docker compose version >/dev/null 2>&1 || die "'docker compose' (v2) not available"
docker info >/dev/null 2>&1 || die "the Docker daemon isn't running — start Docker and retry"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  ok "created .env from .env.example"
fi

if ! grep -qE '^ANTHROPIC_API_KEY=.+' .env; then
  warn "ANTHROPIC_API_KEY is empty in .env — the console will start, but tasks can't run until you set it"
  warn "edit .env, then run: docker compose up -d"
fi

build=(--build)
[ "${1:-}" = "--no-build" ] && build=()

info "starting leadscout…"
docker compose up -d "${build[@]}"

port="$(grep -E '^LEADSCOUT_PUBLISH_PORT=' .env 2>/dev/null | cut -d= -f2 || true)"
port="${port:-8790}"

info "waiting for the server…"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then
    ok "leadscout is running → http://localhost:${port}"
    ok "first visit: create the admin account on the setup page"
    exit 0
  fi
  sleep 1
done
warn "the server didn't answer yet — check: docker compose logs leadscout"
