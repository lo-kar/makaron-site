#!/usr/bin/env python3
"""Build the crawlable copies of the Makaron site from site/index.html.

site/index.html stays the single source (and the home page). This script:
  * fills the <!-- seo --> block in its <head> (title, description, canonical, Open Graph, JSON-LD),
  * writes one static copy per route (site/craft/index.html, site/journal/<slug>/index.html, ...) with that
    route's head and its section visible, so crawlers that do not run JavaScript see the right page,
  * writes sitemap.xml, robots.txt, llms.txt and llms-full.txt.

The browser still runs the whole site as one page: the router in index.html swaps sections without a reload.

Usage:  python3 tools/build.py            # write everything
        python3 tools/build.py --check    # exit 1 if anything is out of date (nothing is written)
Env:    SITE_URL (default https://makaron.com) — the production origin used in canonical URLs and the sitemap.
Only Python's standard library is used. Output is deterministic, so re-running without changes writes nothing.
"""
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'site'
SOURCE = ROOT / 'index.html'
SITE_URL = os.environ.get('SITE_URL', 'https://makaron.com').rstrip('/')
PROD_HOST = re.sub(r'^https?://', '', SITE_URL).split('/')[0]
DEFAULT_IMAGE = '/assets/og-image.jpg'

ORG = {
    '@type': 'Organization',
    '@id': SITE_URL + '/#org',
    'name': 'Makaron',
    'legalName': 'Metrics34 UK Limited',
    'url': SITE_URL + '/',
    'logo': SITE_URL + '/assets/emblem.png',
    'email': 'hello@makaron.com',
    'telephone': '+90 532 433 69 79',
    'sameAs': ['https://www.instagram.com/makaronoliveoil/'],
    'address': {'@type': 'PostalAddress', 'streetAddress': '81 Turners Hill', 'addressLocality': 'Cheshunt',
                'addressRegion': 'Hertfordshire', 'postalCode': 'EN8 9BD', 'addressCountry': 'GB'},
}
WEBSITE = {'@type': 'WebSite', '@id': SITE_URL + '/#website', 'name': 'Makaron', 'url': SITE_URL + '/',
           'inLanguage': 'en', 'publisher': {'@id': SITE_URL + '/#org'}}


def text(fragment):
    """Plain text of an HTML fragment."""
    fragment = re.sub(r'<(script|style|svg)\b.*?</\1>', '', fragment, flags=re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


def abs_url(path):
    return SITE_URL + path if path.startswith('/') else path


# ---------------------------------------------------------------- read the source
def load_routes(src):
    """Every element with data-path is a route: the .Page sections plus in-page anchors such as #shop."""
    routes = []
    for m in re.finditer(r'<(section|div) class="(?:Page|Shop)" id="([^"]+)"([^>]*)>', src):
        attrs = dict((k, html.unescape(v)) for k, v in re.findall(r'data-([a-z]+)="([^"]*)"', m.group(3)))
        if 'path' not in attrs:
            continue
        is_page = m.group(1) == 'section'
        body = ''
        if is_page:
            end = src.index('</section>', m.end())
            body = src[m.end():end]
        routes.append({'id': m.group(2), 'page': m.group(2) if is_page else 'home', 'body': body, **attrs})
    by_id = {r['id']: r for r in routes}
    for r in routes:
        r['canonical'] = r.get('canonical', r['path'])
        r.setdefault('title', 'Makaron')
        if not r['body']:
            r['body'] = by_id[r['page']]['body']
    return routes


def load_products(src):
    products = []
    for m in re.finditer(r'<article class="Shop-item.*?</article>', src, re.S):
        block = m.group(0)
        img = re.search(r'<img[^>]*src="([^"?]+)[^"]*"[^>]*alt="([^"]*)"', block)
        products.append({
            'name': text(re.search(r'<h3 class="Shop-name">(.*?)</h3>', block).group(1)),
            'description': text(re.search(r'<p class="Shop-desc">(.*?)</p>', block).group(1)),
            'price': re.search(r'Shop-price">£([\d.,]+)<', block).group(1).replace(',', ''),
            'image': img.group(1), 'alt': html.unescape(img.group(2)),
        })
    return products


def load_analysis(src):
    lot = re.search(r'Certificate of analysis</p><p class="t-eyebrow">([^<]+)<', src)
    rows = [(text(a), text(b)) for a, b in re.findall(r'<div class="Coa-row"><span>(.*?)</span><b>(.*?)</b></div>', src)]
    return (lot.group(1) if lot else ''), rows


def load_faq(body):
    return [(text(q), text(a)) for q, a in re.findall(
        r'<button class="Faq-q"[^>]*><span>(.*?)</span>.*?<div class="Faq-a"><div>(.*?)</div></div>', body, re.S)]


# ---------------------------------------------------------------- structured data
def jsonld(route, routes, products, faq):
    url = abs_url(route['canonical'])
    graph = [ORG, WEBSITE]
    crumbs = [('Home', '/')]
    if route['path'].startswith('/journal/') and route['path'] != '/journal/':
        crumbs.append(('Journal', '/journal/'))
    if route['path'] != '/':
        crumbs.append((route['title'].split(' | ')[0].split(' — ')[0], route['path']))
    page = {'@type': 'WebPage', '@id': url + '#webpage', 'url': url, 'name': route['title'],
            'description': route.get('description', ''), 'isPartOf': {'@id': SITE_URL + '/#website'}, 'inLanguage': 'en'}
    if len(crumbs) > 1:
        page['breadcrumb'] = {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': abs_url(p)} for i, (n, p) in enumerate(crumbs)]}
    graph.append(page)

    if route['id'] in ('home', 'foods', 'shop'):
        for i, p in enumerate(products):
            graph.append({
                '@type': 'Product', '@id': SITE_URL + '/#product-' + str(i + 1),
                'name': 'Makaron Early-Harvest Extra Virgin Olive Oil — ' + p['name'],
                'description': p['description'], 'image': abs_url(p['image']),
                'brand': {'@type': 'Brand', 'name': 'Makaron'}, 'manufacturer': {'@id': SITE_URL + '/#org'},
                'countryOfOrigin': 'TR', 'category': 'Extra virgin olive oil',
                'offers': {'@type': 'Offer', 'price': p['price'], 'priceCurrency': 'GBP', 'url': SITE_URL + '/shop/',
                           'seller': {'@id': SITE_URL + '/#org'}},
            })
    if faq:
        graph.append({'@type': 'FAQPage', '@id': url + '#faq', 'mainEntity': [
            {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faq]})
    if route.get('type') == 'article':
        graph.append({
            '@type': 'BlogPosting', '@id': url + '#article', 'mainEntityOfPage': {'@id': url + '#webpage'},
            'headline': route['title'].replace(' | Makaron Journal', ''), 'description': route.get('description', ''),
            'image': abs_url(route['image']), 'datePublished': route['published'], 'dateModified': route['published'],
            'articleSection': route.get('section', ''), 'inLanguage': 'en',
            'author': {'@id': SITE_URL + '/#org'}, 'publisher': {'@id': SITE_URL + '/#org'},
        })
    if route['id'] == 'journal':
        posts = [r for r in routes if r.get('type') == 'article']
        posts.sort(key=lambda r: r['published'], reverse=True)
        graph.append({'@type': 'Blog', '@id': url + '#blog', 'name': 'Makaron Journal', 'url': url,
                      'publisher': {'@id': SITE_URL + '/#org'},
                      'blogPost': [{'@id': abs_url(r['path']) + '#article'} for r in posts]})
    return json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False, separators=(',', ':'))


def head_block(route, routes, products, faq):
    url = abs_url(route['canonical'])
    image = route.get('image') or DEFAULT_IMAGE
    e = lambda v: html.escape(v, quote=True)
    lines = [
        '<!-- seo -->',
        '<!-- generated by tools/build.py from the data-* attributes on each page; edit those, not this block -->',
        f'<title>{e(route["title"])}</title>',
        f'<meta name="description" content="{e(route.get("description", ""))}">',
        f'<link rel="canonical" href="{e(url)}">',
        # any host other than the production one (demo, staging, local) asks search engines not to index it
        '<script>if(!/(^|\\.)' + re.escape(PROD_HOST) + '$/.test(location.hostname)){var r=document.createElement("meta");'
        'r.name="robots";r.content="noindex, nofollow";document.head.appendChild(r)}</script>',
        '<meta property="og:site_name" content="Makaron">',
        f'<meta property="og:type" content="{"article" if route.get("type") == "article" else "website"}">',
        f'<meta property="og:title" content="{e(route["title"])}">',
        f'<meta property="og:description" content="{e(route.get("description", ""))}">',
        f'<meta property="og:url" content="{e(url)}">',
        f'<meta property="og:image" content="{e(abs_url(image))}">',
        '<meta property="og:locale" content="en_GB">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if image == DEFAULT_IMAGE:
        lines += ['<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">']
    if route.get('type') == 'article':
        lines.append(f'<meta property="article:published_time" content="{route["published"]}">')
    lines.append('<script type="application/ld+json">' + jsonld(route, routes, products, faq).replace('</', '<\\/') + '</script>')
    lines.append('<!-- /seo -->')
    return '\n'.join(lines)


def render(src, route, routes, products, faq):
    out = re.sub(r'<!-- seo -->.*?<!-- /seo -->', lambda _: head_block(route, routes, products, faq), src, count=1, flags=re.S)

    def toggle(m):
        attrs = re.sub(r'\s+hidden(?=\s|$)', '', m.group(2))
        return f'<section class="Page" id="{m.group(1)}"{attrs}{"" if m.group(1) == route["page"] else " hidden"}>'
    return re.sub(r'<section class="Page" id="([^"]+)"([^>]*)>', toggle, out)


# ---------------------------------------------------------------- markdown for llms-full.txt
class Markdown(HTMLParser):
    SKIP = {'script', 'style', 'svg', 'video', 'noscript', 'template', 'form', 'select'}
    BLOCK = {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'figcaption', 'blockquote', 'tr', 'button', 'div', 'header', 'aside', 'figure', 'cite'}
    VOID = {'img', 'br', 'hr', 'input', 'meta', 'link', 'source', 'use', 'path', 'circle'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.buf, self.stack, self.skip_depth, self.links = [], [], [], 0, []

    def flush(self, prefix=''):
        t = re.sub(r'\s+', ' ', ''.join(self.buf)).strip()
        t = re.sub(r'\s+([,.;:!?)])', r'\1', t)
        self.buf = []
        if t:
            self.lines.append(prefix + t)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.VOID:
            if tag == 'br':
                self.buf.append(' ')
            return
        if self.skip_depth:                      # inside a hidden subtree: track nesting only
            self.stack.append((tag, False))
            return
        hide = tag in self.SKIP or 'hidden' in a or a.get('aria-hidden') == 'true' \
            or any(c in (a.get('class') or '') for c in ('Pills', 'Journal-filters', 'NextArticle', 'Loader'))
        self.stack.append((tag, bool(hide)))
        if hide:
            self.skip_depth += 1
            return
        if tag in self.BLOCK:
            self.flush(self.prefix())
        if tag == 'a':
            self.links.append((a.get('href') or '', len(''.join(self.buf))))

    def prefix(self):
        for tag, _ in reversed(self.stack[:-1] if self.stack else []):
            if tag in ('h1', 'h2', 'h3', 'h4'):
                return '#' * (int(tag[1]) + 1) + ' '
            if tag == 'li':
                return '- '
        return ''

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        while self.stack:
            t, opened_skip = self.stack.pop()
            if opened_skip:
                self.skip_depth -= 1
            if t == tag:
                break
        if self.skip_depth:
            return
        if tag in ('span', 'b', 'strong', 'em', 'i'):   # display lines and stat pairs are separate words on screen
            self.buf.append(' ')
        if tag == 'a' and self.links:
            href, start = self.links.pop()
            joined = ''.join(self.buf)
            label = joined[start:].strip()
            if label and (href.startswith('/') or href.startswith('mailto:')):
                target = abs_url(href) if href.startswith('/') else href
                self.buf = [joined[:start], f'[{label}]({target})']
        if tag in self.BLOCK or tag in ('h1', 'h2', 'h3', 'h4'):
            pre = {'h1': '## ', 'h2': '### ', 'h3': '#### ', 'h4': '#### ', 'li': '- '}.get(tag, '')
            self.flush(pre)

    def handle_data(self, data):
        if not self.skip_depth:
            self.buf.append(data)

    def markdown(self):
        self.flush()
        out = []
        for line in self.lines:
            if out and out[-1] == line:
                continue
            out.append(line)
        return '\n\n'.join(out)


def page_markdown(route):
    md = Markdown()
    md.feed(route['body'])
    return md.markdown()


# ---------------------------------------------------------------- site-wide files
def sitemap(routes):
    rows = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for r in routes:
        if r['canonical'] != r['path']:
            continue
        rows.append('  <url><loc>' + html.escape(abs_url(r['path'])) + '</loc>'
                    + (f'<lastmod>{r["published"]}</lastmod>' if r.get('published') else '') + '</url>')
    rows.append('</urlset>')
    return '\n'.join(rows) + '\n'


def robots():
    return ('# Search engines and AI assistants are welcome to read and cite this site.\n'
            'User-agent: *\nAllow: /\n\n'
            '# named explicitly so a later blanket rule cannot shut them out by accident\n'
            + ''.join(f'User-agent: {bot}\nAllow: /\n\n' for bot in (
                'Googlebot', 'Bingbot', 'GPTBot', 'OAI-SearchBot', 'ChatGPT-User', 'ClaudeBot', 'Claude-User',
                'Claude-SearchBot', 'PerplexityBot', 'Perplexity-User', 'Google-Extended', 'Applebot-Extended'))
            + f'Sitemap: {SITE_URL}/sitemap.xml\n')


def llms(routes, products, analysis):
    lot, rows = analysis
    by_id = {r['id']: r for r in routes}
    out = ['# Makaron', '',
           '> ' + by_id['home']['description'], '',
           'Makaron is an early-harvest, single-origin extra virgin olive oil from one grove of Edremit (Ayvalık) olive '
           'trees on the Edremit Gulf in the north Aegean, Türkiye. It is sold in the UK by Metrics34 UK Limited.', '',
           '## Key facts', '']
    if lot:
        out.append(f'- Certificate of analysis: {lot}')
    out += [f'- {k}: {v}' for k, v in rows]
    out += ['- Packaging: light-proof tins', '- Contact: hello@makaron.com · Instagram @makaronoliveoil', '',
            '## Products and prices (GBP)', '']
    out += [f'- {p["name"]} — £{p["price"]}: {p["description"]}' for p in products]
    out += ['', '## Pages', '']
    for r in routes:
        if r['canonical'] != r['path'] or r.get('type') == 'article':
            continue
        out.append(f'- [{r["title"].split(" | ")[0]}]({abs_url(r["path"])}): {r.get("description", "")}')
    out += ['', '## Journal', '']
    for r in sorted((r for r in routes if r.get('type') == 'article'), key=lambda r: r['published'], reverse=True):
        out.append(f'- [{r["title"].replace(" | Makaron Journal", "")}]({abs_url(r["path"])}) ({r["published"]}): {r.get("description", "")}')
    out += ['', '## Optional', '', f'- [Full text of every page]({SITE_URL}/llms-full.txt)', '']
    return '\n'.join(out)


def llms_full(routes):
    out = ['# Makaron — full site text', '', f'Source: {SITE_URL}/', '']
    for r in routes:
        if r['canonical'] != r['path']:
            continue
        out += ['---', '', f'# {r["title"]}', '', f'URL: {abs_url(r["path"])}']
        if r.get('published'):
            out.append(f'Published: {r["published"]}')
        out += ['', page_markdown(r), '']
    return '\n'.join(out) + '\n'


# ---------------------------------------------------------------- main
def main():
    check = '--check' in sys.argv
    src = SOURCE.read_text(encoding='utf-8')
    assert '<!-- seo -->' in src and '<!-- /seo -->' in src, 'index.html is missing the <!-- seo --> markers'
    routes = load_routes(src)
    products = load_products(src)
    by_id = {r['id']: r for r in routes}
    faq = {r['id']: load_faq(r['body']) for r in routes if r['id'] == r['page']}

    outputs = {}
    home = render(src, by_id['home'], routes, products, faq.get('home'))
    outputs[SOURCE] = home
    for r in routes:
        if r['id'] == 'home':
            continue
        outputs[ROOT / r['path'].strip('/') / 'index.html'] = render(home, r, routes, products, faq.get(r['id']))
    outputs[ROOT / 'sitemap.xml'] = sitemap(routes)
    outputs[ROOT / 'robots.txt'] = robots()
    outputs[ROOT / 'llms.txt'] = llms(routes, products, load_analysis(src))
    outputs[ROOT / 'llms-full.txt'] = llms_full(routes)

    stale = [p for p, body in outputs.items() if not p.exists() or p.read_text(encoding='utf-8') != body]
    if check:
        for p in stale:
            print('out of date:', p.relative_to(ROOT.parent))
        sys.exit(1 if stale else 0)
    for p in stale:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(outputs[p], encoding='utf-8')
        print('wrote', p.relative_to(ROOT.parent))
    if not stale:
        print('up to date')


if __name__ == '__main__':
    main()
