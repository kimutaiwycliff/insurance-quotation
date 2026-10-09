#!/usr/bin/env bash
# Every 5 minutes from cron: checks the public site, disk space and backup age, then pings
# HEALTHCHECK_UPTIME_URL when all is well (healthchecks.io emails you when the pings stop).
# shellcheck source-path=SCRIPTDIR
source "$(dirname "$0")/lib.sh"

problems=()
domain="$(env_value DOMAIN)"
curl -fsS -m 15 -o /dev/null "https://app.$domain/sign-in" || problems+=("site https://app.$domain is down")
curl -fsS -m 15 -o /dev/null "https://api.$domain/health/live" || problems+=("API health check failed")
used=$(df --output=pcent / | tail -1 | tr -dc '0-9')
(( used < 85 )) || problems+=("disk ${used}% full")
newest=$(find "$BACKUP_DIR/db" -name 'app-*.dump' -mmin -1560 2>/dev/null | head -1)
[[ -n "$newest" ]] || problems+=("no database backup in the last 26 hours")

if (( ${#problems[@]} )); then
  log "UNHEALTHY: ${problems[*]}"
  url="$(env_value HEALTHCHECK_UPTIME_URL)"
  if [[ -n "$url" ]]; then curl -fsS -m 10 -o /dev/null --data-raw "${problems[*]}" "$url/fail" || true; fi
  exit 1
fi
ping_url "$(env_value HEALTHCHECK_UPTIME_URL)"
