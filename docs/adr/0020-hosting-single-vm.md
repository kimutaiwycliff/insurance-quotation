# ADR-0020: Hosting on a single VM with Docker Compose

- Status: Accepted
- Date: 2026-10-08
- Resolves: D6

## Context
The product owner will host on **one virtual machine running Docker Compose**: the same tool used in
development and CI. The domain is not chosen yet (D7).

## Decision
- **Production overlay** `compose.prod.yaml` on top of `compose.yaml`:
  - **Caddy** in front: automatic HTTPS for the web app (and API if exposed) once a domain points at the VM;
  - only ports 80 and 443 are open; no service is published on the host otherwise;
  - restart policies, resource limits, log rotation, and secrets from a root-only `.env` on the VM.
- **Storage:** RustFS on a local volume for documents, replicated nightly to off-site S3-compatible storage
  (e.g. Cloudflare R2 or Backblaze B2).
- **Backups:**
  - nightly `pg_dump` (custom format), encrypted and uploaded off-site, kept 30 days;
  - weekly restore test into a scratch database;
  - the runbook gives a timed restore drill.
- **Deploys:** `git pull` plus `docker compose -f compose.yaml -f compose.prod.yaml up -d --build --wait`.
  Migrations run in the `migrate` service before the API starts. Rollback means checking out the previous
  tag and running the same command, as long as migrations are backward compatible (expand, then contract).
- **Monitoring:** a health-check cron (or uptime service) on `/health/ready`, Sentry for errors, and a disk
  and backup-age alert script.

## Consequences
- One machine is a single point of failure. That is acceptable for the pilot; the next step is a managed
  Postgres or a second VM.
- Everything stays reproducible from the repo; no cloud-specific IaC is needed.
