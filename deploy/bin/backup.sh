#!/usr/bin/env bash
# Nightly backup (ADR-0020): a pg_dump of the whole app database (API and auth schemas) and the document
# store, encrypted and deduplicated by restic into RESTIC_REPOSITORY (off the VM). Keeps 30 daily,
# 12 weekly and 12 monthly snapshots.
# Usage: deploy/bin/backup.sh [--db-only]
# shellcheck source-path=SCRIPTDIR
source "$(dirname "$0")/lib.sh"

db_only=0
[[ "${1:-}" == "--db-only" ]] && db_only=1
work="$BACKUP_DIR"
mkdir -p "$work/db"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump="$work/db/app-$stamp.dump"
db="$(env_value POSTGRES_DB)"

log "Dumping database $db"
dc exec -T postgres pg_dump -U postgres -d "$db" --format=custom --compress=6 > "$dump.partial"
mv "$dump.partial" "$dump"
# Keep the last 7 dumps on the VM for quick restores; the off-site copy is the real backup.
find "$work/db" -name "app-*.dump" | sort -r | tail -n +8 | xargs -r rm -f  # names are UTC timestamps

restic() { restic_run -v "${PROJECT}_storagedata:/backup/storage:ro" -v brokeros-restic-cache:/root/.cache/restic -- "$@"; }

if ! restic cat config >/dev/null 2>&1; then
  log "Initialising the restic repository"
  restic init
fi

# 1. The database dump: must be saved completely, or the backup fails.
log "Uploading the database dump"
# Streamed through stdin, so restic never reads the host folder (sturdier across Docker setups).
restic backup --tag db --stdin --stdin-filename "app-$stamp.dump" < "$dump"

# 2. The document store. Exit code 3 means a file vanished while it was read (RustFS rotates its own
# temp files): the snapshot is complete for everything else, so log it and carry on.
if (( ! db_only )); then
  log "Uploading documents"
  status=0
  restic backup --tag files --exclude /backup/storage/.rustfs.sys/tmp \
    --exclude /backup/storage/.rustfs.sys/multipart /backup/storage || status=$?
  if (( status == 3 )); then
    log "Warning: some document-store files changed during the backup; the snapshot was saved"
  elif (( status != 0 )); then
    log "Document backup FAILED (restic exit $status)"
    exit "$status"
  fi
fi
restic forget --prune --group-by tags --keep-daily 30 --keep-weekly 12 --keep-monthly 12 >/dev/null
log "Backup done: $dump"
(( db_only )) || ping_url "$(env_value HEALTHCHECK_BACKUP_URL)"
