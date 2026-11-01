#!/usr/bin/env bash
# Runs every 2 minutes (systemd timer): pulls the latest site and refreshes Caddy if anything changed.
set -euo pipefail
REPO=/opt/makaron-site
cd "$REPO"
before=$(git rev-parse HEAD)
git fetch -q origin main
git reset -q --hard origin/main
after=$(git rev-parse HEAD)
IP=$(curl -4 -fsS --max-time 5 http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || hostname -I | awk '{print $1}')
HOSTS=$(grep -v '^\s*#' server/domains.txt | sed '/^\s*$/d' | sed "s/^auto$/$(echo "$IP" | tr . -).sslip.io/" | paste -sd, - | sed 's/,/, /g')
cat > /etc/caddy/Caddyfile <<CADDY
$HOSTS {
	root * $REPO/site
	encode zstd gzip
	@assets path /assets/*
	header @assets Cache-Control "public, max-age=31536000, immutable"
	header /index.html Cache-Control "no-cache"
	header {
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
		-Server
	}
	try_files {path} /index.html
	file_server
}
CADDY
if ! cmp -s /etc/caddy/Caddyfile /run/makaron-caddyfile.last 2>/dev/null; then
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null && systemctl reload caddy
  cp /etc/caddy/Caddyfile /run/makaron-caddyfile.last
fi
[ "$before" != "$after" ] && echo "site updated to ${after:0:7}" || true
