#!/usr/bin/env bash
# Disaster recovery: restores the database and the document store from a restic snapshot.
# DESTRUCTIVE: replaces the current database and documents. Runbook: docs/runbooks/deploy-vm.md.
# Usage: deploy/bin/restore.sh <latest|YYYY-MM-DD> [--yes]
#   latest: the newest database dump and documents; a date: the last of each taken on or before that day.
# shellcheck source-path=SCRIPTDIR
source "$(dirname "$0")/lib.sh"

when="${1:?usage: restore.sh <latest|YYYY-MM-DD> [--yes]}"
if [[ "${2:-}" != "--yes" ]]; then
  read -r -p "This replaces the database and all documents with the backup from $when. Type RESTORE to go on: " answer
  [[ "$answer" == "RESTORE" ]] || { echo "Cancelled"; exit 1; }
fi

work="$BACKUP_DIR/restore"
rm -rf "$work" && mkdir -p "$work"
db="$(env_value POSTGRES_DB)"

restic() { restic_run -v "$work:/restore" -- "$@"; }

# Picks the newest snapshot with this tag, taken on or before the chosen day.
pick() {
  local tag="$1" cutoff="9999-12-31"
  [[ "$when" == latest ]] || cutoff="$when"
  restic snapshots --tag "$tag" --json \
    | jq -r --arg cutoff "$cutoff" '[.[] | select(.time[:10] <= $cutoff)] | max_by(.time) | if . then "\(.short_id) \(.paths[0])" else empty end'
}
read -r db_snapshot db_path <<< "$(pick db)"
[[ -n "${db_snapshot:-}" ]] || { echo "No database backup on or before $when" >&2; exit 1; }
log "Fetching database snapshot $db_snapshot ($db_path)"
dump="$work/app.dump"
restic dump "$db_snapshot" "$db_path" > "$dump"
[[ -s "$dump" ]] || { echo "The database snapshot is empty" >&2; exit 1; }
read -r files_snapshot _ <<< "$(pick files)"
if [[ -n "${files_snapshot:-}" ]]; then
  log "Fetching documents snapshot $files_snapshot"
  restic restore "$files_snapshot" --target /restore
fi

log "Stopping the application"
dc stop caddy web auth api worker

log "Restoring database from $(basename "$dump")"
dc exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" -c "CREATE DATABASE \"$db\""
dc exec -T postgres pg_restore -U postgres -d "$db" --exit-on-error < "$dump"

if [[ -d "$work/backup/storage" ]]; then
  log "Restoring documents"
  dc stop storage
  docker run --rm -v "${PROJECT}_storagedata:/data" -v "$work/backup/storage:/from:ro" alpine:3.22 \
    sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null; cp -a /from/. /data/'
else
  log "No documents backup found; keeping current documents"
fi

log "Starting the application"
dc up -d --wait
rm -rf "$work"
log "Restore finished"
