# Makaron website

Static site for makaron.com, served by Caddy on a Hetzner Cloud server.

- `site/` — the website (index.html + assets). Whatever is on `main` is live within 2 minutes.
- `server/domains.txt` — hostnames the server answers on. Add `makaron.com` and `www.makaron.com` once DNS points at the server.
- `server/install.sh` — one-time server setup (run by cloud-init on first boot).
- `server/sync.sh` — the 2-minute sync job installed by `install.sh`.
- `tools/build.py` — run `python3 tools/build.py` after editing `site/index.html`. It regenerates the per-page copies (`/craft/`, `/journal/…`), `sitemap.xml`, `robots.txt` and `llms.txt` used for SEO. Commit its output.
