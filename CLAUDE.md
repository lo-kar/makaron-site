# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Static marketing site for makaron.com (Makaron olive oil, operated by Metrics34 UK Limited). There is no framework, package manager or test suite. The whole site lives in `site/index.html` (CSS, markup and JS inline) plus `site/assets/` (~43 MB, mostly MP4). `HANDOVER.md` is the original developer handover. It predates the real-path routing and SEO build described below.

## The one build step

`site/index.html` is the single source of truth and is also the home page. After **any** edit to it, run:

```sh
python3 tools/build.py          # regenerate route copies, sitemap.xml, robots.txt, llms.txt, llms-full.txt
python3 tools/build.py --check  # exit 1 if anything is stale (writes nothing)
```

- The script uses the Python standard library only, and its output is deterministic.
- Generated files are **committed**: `site/<route>/index.html`, `site/sitemap.xml`, `site/robots.txt`, `site/llms*.txt`. This way any static host serves them without running a build.
- Never edit a generated route copy, or the `<!-- seo -->…<!-- /seo -->` block in `index.html`. Both are rewritten from the `data-*` attributes on each page section.
- `SITE_URL` (default `https://makaron.com`) sets the canonical origin.
- On any other hostname, an inline script in the SEO block adds `noindex`. On the server, a demo that only has `auto` in `domains.txt` also sends an `X-Robots-Tag: noindex` header.

## Local development

- The site is served by Laravel Herd at **http://makaron.test**. `site/` is linked with `herd link makaron`, run from inside `site/`.
- Herd's built-in Craft CMS driver claims any folder containing `craft`, which the `/craft/` route creates. A custom driver at `~/Library/Application Support/Herd/config/valet/Drivers/MakaronValetDriver.php` serves this site the way Caddy does instead. It is machine-local and not part of the repo.
- Locally, Herd's nginx 404s `/robots.txt` and `/favicon.ico`. Production Caddy serves both.

## Routing

- Each page is a `<section class="Page" id="…">`. Its metadata lives in attributes on that section: `data-path`, `data-title`, `data-description`, and for articles `data-type="article" data-published data-image data-section`.
- `#shop` is an in-page anchor on home. It has its own `data-path="/shop/"` with `data-canonical="/"`.
- The router in the bottom `<script>` builds its route table from `[data-path]`. It intercepts same-origin link clicks and uses `history.pushState`, so pages switch without a reload. Loader, videos and Lenis keep running.
- On every switch the router updates `document.title`, the description, canonical and og tags.
- Old `#process`-style hashes are rewritten to their real path.
- Section ids do not match URLs:

  | Section id | URL |
  |---|---|
  | `process` | `/craft/` |
  | `foods` | `/oils/` |
  | `mission` | `/grove/` |
  | `care` | `/at-the-table/` |
  | `article-*` | `/journal/<slug>/` |

- To add a page: add the section with its `data-*` attributes, link it by path, then run the build.
- All asset URLs are root-absolute (`/assets/…`). Relative URLs break under `/journal/<slug>/` and after `pushState`.

## Deployment model

- Production runs on a Hetzner Cloud server with Caddy serving `site/` as web root, using `try_files {path} {path}/index.html /index.html`.
- `server/install.sh` is the one-time cloud-init setup. It clones the repo to `/opt/makaron-site` and installs `server/sync.sh` as `/usr/local/bin/makaron-sync` on a 2-minute systemd timer.
- On every run, `sync.sh` does `git fetch` + `git reset --hard origin/main`. It then:
  - reinstalls itself if the repo copy changed;
  - regenerates `/etc/caddy/Caddyfile` from `server/domains.txt`;
  - reloads Caddy if the config changed.
- **Pushing to `main` is the deploy.** The server does not run `tools/build.py`, so commit the generated files.
- `server/domains.txt` lists one hostname per line. `auto` expands to `<ip-with-dashes>.sslip.io`.
- `install.sh` hardcodes the clone URL `https://github.com/lo-kar/makaron-site.git`. Update it if the repo moves.

## Architecture of `site/index.html`

- **CSS**:
  - Design tokens are on `:root`: `--cream`, `--brown`, `--black`, `--fs-*`, `--space-*`.
  - Desktop rules come first, then the mobile refinements.
  - The **PHONE PARITY** block is last and wins. It gives phones the desktop compositions instead of stacked columns: offset title lines, side-by-side story text, two-column staggered shop/product/journal grids.
- **JS** is one vanilla `<script>`. The only external dependency is Lenis (`lenis@1.1.18` from jsDelivr). The menu carries `data-lenis-prevent` and stops Lenis while it is open. Modules:
  - loader and router (above);
  - the home "story canvas": pinned, scroll-driven stills and text layers, with an SVG connector placed by `placeConnector()` from measured layout boxes;
  - the entry-point cascade (`driveEv`): the same sine wave on every screen size;
  - `setNavTheme()`, which also syncs `theme-color`;
  - IntersectionObserver video play/pause (off-screen videos never autoplay);
  - journal filters, contact form, consent sheet.
- **Consent gating**: add third-party tags as `<script type="text/plain" data-consent="analytics|marketing">`.
- **Asset cache-busting**: `/assets/*` is cached for a year as `immutable`. When you replace a file, bump its `?v=N`.
- **Structured data**: `tools/build.py` emits a JSON-LD `@graph` per route:
  - every page: Organization, WebSite, WebPage plus breadcrumbs;
  - home, oils and shop: Product (parsed from the `.Shop-item` cards);
  - grove: FAQPage (from `.Faq-item`);
  - articles: BlogPosting;
  - journal: Blog.

  Prices, analysis figures and FAQ answers are read from the HTML. Change them there.

## Known gaps

- The contact form is front-end only: it validates, shows thanks and sends nothing. Its copy still promises a 10% code by email.
- "Order now" buttons link to `/contact/`. There is no cart or checkout.
- Legal pages contain placeholders: `[GB 000 0000 00]` (VAT number), `[two years]`, `[90 days]`.
- No analytics are installed.
- Unknown paths serve the home page with status 200 (soft 404).
- The tin label prints makaronoliveoil.com, while the site targets makaron.com.

## Copy rules (from the owner)

- Say "peppery taste/finish", never "pepper" as a noun.
- Never mention bitterness.
- Use "cold extraction" or "cold extracted", never "cold pressed", except where an article quotes the term to critique it.
