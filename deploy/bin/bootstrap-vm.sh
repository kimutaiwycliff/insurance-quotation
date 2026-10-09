#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 VM (Oracle Cloud Ampere A1 or any other), run as the login user:
#   curl -fsSL https://raw.githubusercontent.com/kimutaiwycliff/insurance-quotation/main/deploy/bin/bootstrap-vm.sh | sudo bash
# Installs Docker, opens ports 80/443 in the host firewall, adds swap, hardens SSH, turns on automatic
# security updates, clones the repo to /opt/brokeros and installs the cron jobs. Safe to run again.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/kimutaiwycliff/insurance-quotation.git}"
APP_DIR="/opt/brokeros"
BACKUP_DIR="/var/backups/brokeros"
DEPLOY_USER="${SUDO_USER:-ubuntu}"

[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }
id "$DEPLOY_USER" >/dev/null 2>&1 || { echo "User $DEPLOY_USER does not exist" >&2; exit 1; }
say() { printf '\n==> %s\n' "$*"; }

say "Packages and automatic security updates"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git jq openssl cron fail2ban unattended-upgrades iptables-persistent
dpkg-reconfigure -f noninteractive unattended-upgrades

say "Docker Engine and the Compose plugin"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "local",
  "log-opts": { "max-size": "20m", "max-file": "5" },
  "live-restore": true
}
JSON
systemctl enable --now docker
systemctl restart docker
usermod -aG docker "$DEPLOY_USER"

say "Firewall: allow HTTP and HTTPS (Oracle's Ubuntu images reject everything but SSH by default)"
for rule in "-p tcp --dport 80" "-p tcp --dport 443" "-p udp --dport 443"; do
  # shellcheck disable=SC2086
  iptables -C INPUT $rule -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null \
    || iptables -I INPUT 1 $rule -m conntrack --ctstate NEW -j ACCEPT
done
netfilter-persistent save

say "Swap (4 GB) for build peaks"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -qw vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/90-brokeros.conf

say "SSH: keys only, no root login"
cat > /etc/ssh/sshd_config.d/90-brokeros.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
sshd -t && systemctl reload ssh
systemctl enable --now fail2ban

say "Application checkout in $APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --quiet "$REPO_URL" "$APP_DIR"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
install -d -m 0700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$BACKUP_DIR"

say "Cron: nightly backup 01:30 EAT, Sunday restore check, health check every 5 minutes"
cat > /etc/cron.d/brokeros <<CRON
# BrokerOS (deploy/bin). Times are UTC: 22:30 UTC = 01:30 in Nairobi.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
30 22 * * * $DEPLOY_USER $APP_DIR/deploy/bin/backup.sh >> $BACKUP_DIR/backup.log 2>&1
30 23 * * 0 $DEPLOY_USER $APP_DIR/deploy/bin/restore-check.sh >> $BACKUP_DIR/restore-check.log 2>&1
*/5 * * * * $DEPLOY_USER $APP_DIR/deploy/bin/healthcheck.sh >> $BACKUP_DIR/health.log 2>&1
CRON
chmod 644 /etc/cron.d/brokeros
cat > /etc/logrotate.d/brokeros <<ROTATE
$BACKUP_DIR/*.log {
  weekly
  rotate 8
  compress
  missingok
  notifempty
}
ROTATE

say "Done. Next (as $DEPLOY_USER, after logging out and in again so the docker group applies):"
echo "  cd $APP_DIR && deploy/bin/init-env.sh <domain> <your-email>"
echo "  nano .env    # fill in the FILL-IN values"
echo "  deploy/bin/deploy.sh"
