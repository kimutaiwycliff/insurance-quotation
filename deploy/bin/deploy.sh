#!/usr/bin/env bash
# Deploys a git ref (default: origin/main) to this VM. Rollback = run it again with the previous ref,
# which is printed at the end and kept in deploy/releases.log.
# Usage: deploy/bin/deploy.sh [ref] [--skip-backup]
# shellcheck source-path=SCRIPTDIR
source "$(dirname "$0")/lib.sh"

ref="origin/main"
backup=1
for arg in "$@"; do
  case "$arg" in
    --skip-backup) backup=0 ;;
    *) ref="$arg" ;;
  esac
done

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "The checkout has local changes; refusing to deploy over them:" >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

previous="$(git rev-parse --short HEAD)"
git fetch --quiet --tags origin
git checkout --quiet --detach "$ref"
RELEASE="$(git rev-parse --short HEAD)"
export RELEASE
log "Deploying $RELEASE (was $previous)"

# A database backup before migrations run, if the stack is already up.
if (( backup )) && dc ps --status running --services 2>/dev/null | grep -qx postgres; then
  deploy/bin/backup.sh --db-only || { echo "Pre-deploy backup failed; aborting (use --skip-backup to override)" >&2; git checkout --quiet --detach "$previous"; exit 1; }
fi

dc build --pull
if ! dc up -d --wait --wait-timeout 300 --remove-orphans; then
  log "Deploy of $RELEASE failed. Logs: docker compose -f compose.yaml -f compose.prod.yaml logs --tail=200"
  log "Roll back with: deploy/bin/deploy.sh $previous --skip-backup"
  exit 1
fi

printf '%s %s -> %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$previous" "$RELEASE" >> deploy/releases.log
docker image prune -f >/dev/null
log "Deployed $RELEASE. Site: https://app.$(env_value DOMAIN)"
log "Roll back with: deploy/bin/deploy.sh $previous --skip-backup"
