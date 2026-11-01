#!/usr/bin/env bash
# First-time setup for a fresh Ubuntu server: Caddy + the site, kept in sync from GitHub every 2 minutes.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl debian-keyring debian-archive-keyring apt-transport-https gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq && apt-get install -y -qq caddy
if [ ! -d /opt/makaron-site/.git ]; then git clone -q https://github.com/lo-kar/makaron-site.git /opt/makaron-site; fi
install -m 755 /opt/makaron-site/server/sync.sh /usr/local/bin/makaron-sync
cat > /etc/systemd/system/makaron-sync.service <<'UNIT'
[Unit]
Description=Pull the Makaron site from GitHub and refresh Caddy
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/makaron-sync
UNIT
cat > /etc/systemd/system/makaron-sync.timer <<'UNIT'
[Unit]
Description=Sync the Makaron site every 2 minutes
[Timer]
OnBootSec=30s
OnUnitActiveSec=2min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now caddy
systemctl enable --now makaron-sync.timer
/usr/local/bin/makaron-sync
echo "Makaron site installed."
