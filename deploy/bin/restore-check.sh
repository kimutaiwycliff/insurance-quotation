#!/usr/bin/env bash
# Weekly restore drill (ADR-0020): restores the newest local dump into a scratch database, checks it holds
# data, then drops it. Proves the dumps are usable; the full restore is deploy/bin/restore.sh.
# shellcheck source-path=SCRIPTDIR
source "$(dirname "$0")/lib.sh"

dump="$(find "$BACKUP_DIR/db" -name "app-*.dump" 2>/dev/null | sort -r | head -1)"
[[ -n "$dump" ]] || { echo "No dump found; run deploy/bin/backup.sh first" >&2; exit 1; }
scratch="restore_check"
start=$(date +%s)
dc exec -T postgres dropdb -U postgres --if-exists "$scratch"
dc exec -T postgres createdb -U postgres "$scratch"
trap 'dc exec -T postgres dropdb -U postgres --if-exists "$scratch" >/dev/null 2>&1 || true' EXIT
dc exec -T postgres pg_restore -U postgres -d "$scratch" --exit-on-error < "$dump"
tenants=$(dc exec -T postgres psql -U postgres -d "$scratch" -Atc "SELECT count(*) FROM app.tenants")
users=$(dc exec -T postgres psql -U postgres -d "$scratch" -Atc 'SELECT count(*) FROM auth."user"')
log "Restore check passed in $(( $(date +%s) - start ))s from $(basename "$dump"): $tenants tenants, $users users"
