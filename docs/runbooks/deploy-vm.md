# Runbook: production on one VM (Oracle Cloud Always Free)

How to put BrokerOS on a single ARM virtual machine with Docker Compose (ADR-0020), keep it backed up,
update it, roll back, and recover from losing the machine. Everything here also works on any Ubuntu 24.04
VM (Hetzner, DigitalOcean and so on); only section 1 is Oracle-specific.

Files: `compose.prod.yaml` (production overlay), `deploy/Caddyfile`, `deploy/production.env.example`,
`deploy/bin/*.sh`.

| Script | What it does |
|---|---|
| `bootstrap-vm.sh` | One-time server setup: Docker, firewall, swap, SSH hardening, updates, checkout, cron |
| `init-env.sh <domain> <email>` | Writes the root-only `.env` with fresh random secrets |
| `deploy.sh [ref]` | Backs up the database, builds, migrates and starts a git ref (default `origin/main`) |
| `backup.sh [--db-only]` | Database dump and documents, encrypted off-site with restic (nightly from cron) |
| `restore-check.sh` | Restores the newest dump into a scratch database and counts rows (weekly from cron) |
| `restore.sh <latest\|YYYY-MM-DD>` | Disaster recovery: replaces the database and documents from a backup |
| `healthcheck.sh` | Site, API, disk and backup-age checks every 5 minutes; pings healthchecks.io |

Rehearsed on 2026-10-09 on an ARM64 machine:
- fresh deploy in production mode, HTTPS through Caddy, API lock-down;
- backup, restore drill, and a full restore that brought back a deleted user and document.

---

## 0. Accounts you need

| Account | For | Notes |
|---|---|---|
| Oracle Cloud | The VM, and backup storage (Object Storage, 20 GB free) | A card is needed to verify the account; Always Free resources are not charged |
| Brevo | Email (300 a day free) | SMTP & API → SMTP: copy the **login** and create an **SMTP key**. Senders: verify the address mail comes from |
| Safaricom Daraja | M-Pesa sandbox while testing | The sandbox keys you already have |
| healthchecks.io (optional) | Alerts by email when backups or the site stop | Two checks: "backup" (period 1 day) and "uptime" (period 5 minutes) |

Keep a password manager entry for the server. It holds the SSH key, the finished `.env` and the Oracle
customer secret key.

## 1. Create the VM (Oracle Cloud console)

1. **Home region:** pick it when you sign up. It cannot be changed, and Always Free resources live only
   there. The nearest to Kenya is **South Africa Central (Johannesburg)**. If it keeps saying "out of host
   capacity", another region works too; latency is a little higher.
2. **Compute → Instances → Create instance:**
   - Image: **Canonical Ubuntu 24.04** (the aarch64 build is chosen automatically for Ampere).
   - Shape: **Ampere → VM.Standard.A1.Flex**, **4 OCPU and 24 GB** (the whole free allowance). If capacity is
     short, start with 2 OCPU / 12 GB.
   - Networking: create a VCN with a public subnet; **assign a public IPv4 address**.
   - SSH keys: upload your public key (or let Oracle generate a pair and **save the private key**).
   - Boot volume: 100 GB (the free allowance is 200 GB in total).
3. **Open ports 80 and 443** in the VCN. Go to Networking → Virtual cloud networks → your VCN → Security
   Lists → Default → Add ingress rules:
   - source `0.0.0.0/0`, TCP, destination port `80`;
   - source `0.0.0.0/0`, TCP, destination port `443`;
   - source `0.0.0.0/0`, UDP, destination port `443`.
   (The bootstrap script opens the same ports in the VM's own firewall.)
4. **Recommended: upgrade the account to Pay As You Go** (Billing → Upgrade).
   - Free-tier VMs that sit idle for 7 days can be reclaimed. Paid accounts are exempt, and Always Free
     resources stay free.
   - Add a budget alert of USD 1 so any charge emails you.
5. Note the **public IP**, e.g. `129.146.10.20`.

## 2. Set up the server

```bash
ssh ubuntu@129.146.10.20
curl -fsSL https://raw.githubusercontent.com/kimutaiwycliff/insurance-quotation/main/deploy/bin/bootstrap-vm.sh | sudo bash
exit   # log out and in again so the docker group applies
```

## 3. Configure (`.env`)

Until there is a domain, use the free wildcard DNS **sslip.io**: the IP with dashes resolves to itself.

```bash
ssh ubuntu@129.146.10.20
cd /opt/brokeros
deploy/bin/init-env.sh 129-146-10-20.sslip.io you@example.com
nano .env
```

`init-env.sh` writes every password and key itself. Fill in the lines marked `FILL-IN`:
- **Brevo:**
  - `SMTP_USERNAME` and `SMTP_PASSWORD` (the SMTP key);
  - `EMAIL_FROM_ADDRESS`, and the address inside `EMAIL_FROM`: your verified sender.
- **Daraja sandbox:** `PLATFORM_MPESA_CONSUMER_KEY`, `PLATFORM_MPESA_CONSUMER_SECRET`,
  `PLATFORM_MPESA_PASSKEY` (shortcode `174379` is already set).
- **Backups** (Oracle Object Storage):
  1. Storage → Buckets → Create bucket `brokeros-backups` (Standard tier, private).
  2. Your namespace is shown on the bucket page; your region identifier is e.g. `af-johannesburg-1`.
  3. Profile → **Customer secret keys** → Generate. The access key and the secret become
     `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` (the secret is shown once).
  4. `RESTIC_REPOSITORY=s3:https://<namespace>.compat.objectstorage.<region>.oraclecloud.com/brokeros-backups`
     and `AWS_DEFAULT_REGION=<region>`.
- **Optional:** `HEALTHCHECK_BACKUP_URL` and `HEALTHCHECK_UPTIME_URL` (healthchecks.io ping URLs), and
  `SENTRY_DSN`.

Then **save the whole `.env` in your password manager**:
- `PII_ENCRYPTION_KEYS` and `PII_LOOKUP_KEY` decrypt client data;
- `RESTIC_PASSWORD` decrypts backups.

Without them, a restore is useless.

## 4. First deploy

```bash
deploy/bin/deploy.sh        # 5–10 minutes the first time (builds the images on the VM)
deploy/bin/backup.sh        # the first backup also creates the restic repository
deploy/bin/restore-check.sh
```

Open `https://app.129-146-10-20.sslip.io` and check:
- **Sign-up:** create an account; the confirmation email arrives through Brevo (check spam the first time).
- **Agency:** create the agency; Settings → Plan & billing shows the 30-day trial.
- **Payments:** Settings → Payments → connect M-Pesa with the sandbox keys (environment *sandbox*). An
  invoice payment prompt to the sandbox test phone goes through.
- **Billing:** Plan & billing → pay with M-Pesa (sandbox) goes through too.

Safaricom calls back to `https://api.<DOMAIN>/api/v1/webhooks/...`; Caddy exposes only those paths, the
unsubscribe links and `/health/live` on the API host.

## 5. Everyday operations

| Task | Command (in `/opt/brokeros`) |
|---|---|
| Deploy the latest `main` | `deploy/bin/deploy.sh` |
| Deploy a tag or commit | `deploy/bin/deploy.sh v0.3.0` |
| Roll back | `deploy/bin/deploy.sh <previous-sha> --skip-backup` (printed by every deploy; history in `deploy/releases.log`) |
| Status | `docker compose -f compose.yaml -f compose.prod.yaml ps` |
| Logs | `docker compose -f compose.yaml -f compose.prod.yaml logs -f --tail=200 api worker` |
| Backup now | `deploy/bin/backup.sh` |
| List backups | `source deploy/bin/lib.sh && restic_run -- snapshots` |
| Logs of cron jobs | `/var/backups/brokeros/{backup,restore-check,health}.log` |

Rollback and migrations:
- Migrations are written expand-then-contract (ADR-0020), so the previous release runs on the newer schema.
- If a release ever has to undo a migration, restore the pre-deploy backup instead. `deploy.sh` takes a
  database-only backup before every deploy.

## 6. Disaster recovery (the VM is gone)

1. Create a new VM (section 1) and run the bootstrap (section 2).
2. Put the saved `.env` back at `/opt/brokeros/.env` (`chmod 600`). **Do not run `init-env.sh`:** new keys
   cannot read the old data.
3. `deploy/bin/deploy.sh --skip-backup` (starts an empty stack).
4. `deploy/bin/restore.sh latest`, or `deploy/bin/restore.sh 2026-10-20` for the last backup on or before
   that day. Type `RESTORE` to confirm.
5. If the IP changed, update `DOMAIN` (section 7), then check sign-in, a client, and downloading a document.

Expect about 15 minutes plus download time. At worst a day of changes is lost (the backup runs nightly at
01:30 EAT).

## 7. Moving to the paid VM or a real domain

- **Real domain:**
  1. Create DNS A records `app`, `api` and `files` pointing to the VM's IP.
  2. Replace the old domain everywhere in `.env`: `sed -i 's/129-146-10-20.sslip.io/example.co.ke/g' .env`.
  3. Run `deploy/bin/deploy.sh`.
  4. Everyone signs in again (cookies belong to the old host).
  5. Tenants with Paybill payments: Settings → Payments → *Register Paybill payments* again, so
     Safaricom gets the new callback URL.
  6. In Brevo, authenticate the domain (SPF and DKIM records) and send from it.
- **Another VM:** take a fresh backup on the old VM, then follow section 6 on the new one with the same `.env`.

## 8. Going live (beyond testing)

- `PLATFORM_MPESA_*`: production keys for our own Paybill (`docs/runbooks/mpesa-go-live.md`).
- `MPESA_CALLBACK_ALLOWED_IPS`: Safaricom's callback IPs.
- A real domain (D7).
- Test a restore once a quarter.
