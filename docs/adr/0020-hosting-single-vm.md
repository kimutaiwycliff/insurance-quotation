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

## Amendment (2026-10-09): implementation (R2.6)
- Test hosting: an **Oracle Cloud Always Free** Ampere A1 VM (ARM64), chosen by the product owner. The same
  files later run on the paid VM. CI builds every image on ARM64, and all third-party images have native
  ARM64 builds.
- **Hosts:** `app.<DOMAIN>` (web), `api.<DOMAIN>` (only M-Pesa webhooks, unsubscribe links and
  `/health/live`; everything else is 404), and `files.<DOMAIN>` (presigned storage URLs). Without a domain,
  `DOMAIN` is `<ip-with-dashes>.sslip.io`.
- **Deploys build on the VM** (`git checkout` + `docker compose build`). There is no image registry.
  `deploy/bin/deploy.sh` takes a database backup first and prints the rollback command.
- **Email:** Brevo SMTP relay (STARTTLS on 587).
- **Backups:** restic (`restic/restic` image, run only on the VM, not an application dependency):
  - the database dump is streamed in; the RustFS volume is backed up as files;
  - both are encrypted, to an S3-compatible bucket (Oracle Object Storage while testing);
  - kept as 30 daily, 12 weekly and 12 monthly snapshots;
  - a weekly scratch-database restore check;
  - `restore.sh` restores by date.
- **Monitoring:** cron checks for the site, the API, disk space and backup age, pinging healthchecks.io.
- Runbook: `docs/runbooks/deploy-vm.md`.

