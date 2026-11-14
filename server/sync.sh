#!/usr/bin/env bash
# Runs every 2 minutes (systemd timer): pulls the latest site and refreshes Caddy if anything changed.
set -euo pipefail
REPO=/opt/makaron-site
cd "$REPO"
before=$(git rev-parse HEAD)
git fetch -q origin main
git reset -q --hard origin/main
after=$(git rev-parse HEAD)
# keep this script itself up to date: if the repo holds a newer copy, install it and hand over to it
if ! cmp -s "$REPO/server/sync.sh" "$0"; then
  install -m 755 "$REPO/server/sync.sh" /usr/local/bin/makaron-sync
  exec /usr/local/bin/makaron-sync
fi
IP=$(curl -4 -fsS --max-time 5 http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || hostname -I | awk '{print $1}')
# a server that only answers on its sslip.io address is a demo: tell search engines not to index it
if grep -v '^\s*#' server/domains.txt | sed '/^\s*$/d' | grep -qv '^auto$'; then ROBOTS=""; else ROBOTS='header X-Robots-Tag "noindex, nofollow"'; fi
SSLIP="$(echo "$IP" | tr . -).sslip.io"
mapfile -t LIST < <(grep -v '^\s*#' server/domains.txt | sed '/^\s*$/d' | sed "s/^auto$/$SSLIP/")
# the first real hostname in domains.txt is the site's address. If its twin is listed too (makaron.uk for
# www.makaron.uk, or the other way round), the twin does not serve the site: it redirects to the address.
PRIMARY=""; TWIN=""
for h in "${LIST[@]}"; do if [ "$h" != "$SSLIP" ]; then PRIMARY=$h; break; fi; done
if [ -n "$PRIMARY" ]; then
  case "$PRIMARY" in www.*) t=${PRIMARY#www.} ;; *) t=www.$PRIMARY ;; esac
  for h in "${LIST[@]}"; do if [ "$h" = "$t" ]; then TWIN=$t; fi; done
fi
HOSTS=""; for h in "${LIST[@]}"; do if [ "$h" != "$TWIN" ]; then HOSTS="${HOSTS:+$HOSTS, }$h"; fi; done
REDIRECT=""; if [ -n "$TWIN" ]; then REDIRECT="$TWIN {
	redir https://$PRIMARY{uri} permanent
}
"; fi
cat > /etc/caddy/Caddyfile <<CADDY
$REDIRECT$HOSTS {
	root * $REPO/site
	encode zstd gzip
	@assets path /assets/*
	header @assets Cache-Control "public, max-age=31536000, immutable"
	@pages not path /assets/*
	header @pages Cache-Control "no-cache"
	$ROBOTS
	header {
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
		-Server
	}
	# real files first, then the route copies built by tools/build.py (/craft/ -> /craft/index.html), then the app shell
	try_files {path} {path}/index.html /index.html
	file_server
}
CADDY
if ! cmp -s /etc/caddy/Caddyfile /run/makaron-caddyfile.last 2>/dev/null; then
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null && systemctl reload caddy
  cp /etc/caddy/Caddyfile /run/makaron-caddyfile.last
fi
[ "$before" != "$after" ] && echo "site updated to ${after:0:7}" || true
