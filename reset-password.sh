#!/usr/bin/env bash
# ZeaLead — reset a console user's password.
#
#   ./reset-password.sh <username>           Docker install (runs inside the container)
#   ./reset-password.sh <username> --local   pip install (uses ZEALEAD_DB / zealead.db)
#
# The new password is typed at a hidden prompt (never on the command line). The user's
# existing sessions stop working at once. To create the first admin on a server with no
# browser access, use: docker compose exec zealead zealead user add <name> --admin
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"

die(){ printf '\033[31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: ./reset-password.sh <username> [--local]"
user="$1"

if [ "${2:-}" = "--local" ]; then
  command -v zealead >/dev/null 2>&1 || die "ZeaLead CLI not found (activate your virtualenv)"
  exec zealead user reset-password "$user"
fi

command -v docker >/dev/null 2>&1 || die "docker not found (for a pip install, add --local)"
docker compose ps --status running zealead 2>/dev/null | grep -q zealead \
  || die "the ZeaLead container isn't running — start it with ./start.sh"
exec docker compose exec zealead zealead user reset-password "$user"
