# shellcheck shell=bash
# Shared by the deploy scripts. Source it; do not run it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# Overridable for rehearsals on another machine; the defaults are what the VM uses.
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
PROJECT="${COMPOSE_PROJECT_NAME:-brokeros}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/brokeros}"
[[ -f "$ENV_FILE" ]] || { echo "No $ENV_FILE: run deploy/bin/init-env.sh first" >&2; exit 1; }

# Production compose: the base file plus the production overlay.
dc() { docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.prod.yaml "$@"; }

# Reads one value from the env file without sourcing it (values may contain spaces and angle brackets).
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }

# restic in a container, with the repository settings from the env file. Extra docker args come first:
#   restic_run [docker-args...] -- [restic-args...]
restic_run() {
  local docker_args=()
  while (( $# )) && [[ "$1" != "--" ]]; do docker_args+=("$1"); shift; done
  shift
  local repo; repo="$(env_value RESTIC_REPOSITORY)"
  # A local path repository (rehearsals) is mounted into the container at the same path.
  [[ "$repo" == /* ]] && docker_args+=(-v "$repo:$repo")
  docker run --rm -i \
    -e RESTIC_REPOSITORY="$repo" \
    -e RESTIC_PASSWORD="$(env_value RESTIC_PASSWORD)" \
    -e AWS_ACCESS_KEY_ID="$(env_value AWS_ACCESS_KEY_ID)" \
    -e AWS_SECRET_ACCESS_KEY="$(env_value AWS_SECRET_ACCESS_KEY)" \
    -e AWS_DEFAULT_REGION="$(env_value AWS_DEFAULT_REGION)" \
    --hostname brokeros \
    "${docker_args[@]}" restic/restic:0.18.0 "$@"
}

# Pings a healthchecks.io-style URL if one is configured; never fails the caller.
ping_url() { local url="$1"; [[ -n "$url" ]] && curl -fsS -m 10 --retry 3 -o /dev/null "$url" || true; }

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
