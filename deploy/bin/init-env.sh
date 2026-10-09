#!/usr/bin/env bash
# Creates the production .env (root-only) from deploy/production.env.example with fresh random secrets.
# Usage: deploy/bin/init-env.sh <domain> <acme-email>     e.g. 129-146-10-20.sslip.io you@example.com
set -euo pipefail
cd "$(dirname "$0")/../.."

domain="${1:?usage: init-env.sh <domain> <acme-email>}"
email="${2:?usage: init-env.sh <domain> <acme-email>}"
[[ "$domain" =~ ^[a-z0-9.-]+$ ]] || { echo "Domain must be lowercase letters, digits, dots and dashes" >&2; exit 1; }
if [[ -e .env ]]; then
  echo ".env already exists; not overwriting it (secrets in it protect existing data)." >&2
  exit 1
fi

umask 077
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line//@DOMAIN@/$domain}"
  line="${line//@ACME_EMAIL@/$email}"
  while [[ "$line" == *@secret@* ]]; do
    line="${line/@secret@/$(openssl rand -hex 32)}"
  done
  while [[ "$line" == *@pii_key@* ]]; do
    line="${line/@pii_key@/prod$(date +%Y%m):$(openssl rand -base64 32)}"
  done
  printf '%s\n' "$line"
done < deploy/production.env.example > .env
chmod 600 .env

echo "Wrote .env for https://app.${domain}"
echo "Now fill in the FILL-IN values (Brevo, Daraja sandbox, backups):"
grep -n "FILL-IN" .env | cut -d= -f1 | sed 's/^/  line /'
echo "Then save a copy of .env in your password manager."
