#!/usr/bin/env python3
"""Build feed.xml (RSS 2.0) for the Travel Finds site and link it from every page.

Items are taken from docs/travel-finds/blog/*.html (title, description, canonical,
og:image).  The script is idempotent: it rewrites feed.xml, injects
``<link rel="alternate" type="application/rss+xml">`` into pages that lack it,
and adds the feed to sitemap.xml once.

Usage (from content-factory):
    python3 scripts/build_travel_finds_feed.py
"""
from __future__ import annotations

import email.utils
import html
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "docs" / "travel-finds"
SITE = "https://travel-finds.surge.sh"
FEED_PATH = SITE_DIR / "feed.xml"
CHANNEL_TITLE = "Travel Finds — cheap flights & hotels"
CHANNEL_DESC = "Flexible-date flight and hotel finds, city breaks and fare math. Ad · affiliate links."
FEED_LINK = (
    '<link rel="alternate" type="application/rss+xml" title="Travel Finds RSS" href="{}/feed.xml">'.format(SITE)
)


def read_meta(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    def grab(pattern: str) -> str:
        m = re.search(pattern, text, re.S)
        return html.unescape(m.group(1).strip()) if m else ""
    title = grab(r"<title>(.*?)</title>").split("|")[0].strip()
    description = grab(r'<meta name="description" content="([^"]*)"') or grab(r'<meta property="og:description" content="([^"]*)"')
    canonical = grab(r'<link rel="canonical" href="([^"]*)"') or f"{SITE}/blog/{page.name}"
    image = grab(r'<meta property="og:image" content="([^"]*)"')
    published = datetime.fromtimestamp(page.stat().st_mtime, tz=timezone.utc)
    return {"title": title, "description": description, "link": canonical, "image": image, "date": published}


def item_xml(meta: dict) -> str:
    parts = [
        "    <item>",
        f"      <title>{html.escape(meta['title'])}</title>",
        f"      <link>{html.escape(meta['link'])}</link>",
        f"      <guid isPermaLink=\"true\">{html.escape(meta['link'])}</guid>",
        f"      <pubDate>{email.utils.format_datetime(meta['date'], usegmt=True)}</pubDate>",
        f"      <description>{html.escape(meta['description'])}</description>",
    ]
    if meta["image"]:
        parts.append(f'      <enclosure url="{html.escape(meta["image"])}" type="image/jpeg" length="0"/>')
    parts.append("    </item>")
    return "\n".join(parts)


def build_feed() -> str:
    posts = sorted(
        (p for p in SITE_DIR.glob("blog/*.html") if p.name != "index.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    items = "\n".join(item_xml(read_meta(post)) for post in posts)
    build_date = email.utils.format_datetime(datetime.now(tz=timezone.utc), usegmt=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="/feed.xsl"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html.escape(CHANNEL_TITLE)}</title>
    <link>{SITE}/</link>
    <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{html.escape(CHANNEL_DESC)}</description>
    <language>en</language>
    <lastBuildDate>{build_date}</lastBuildDate>
{items}
  </channel>
</rss>
"""


def link_pages() -> int:
    changed = 0
    for page in SITE_DIR.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        if "application/rss+xml" in text:
            continue
        if "</head>" not in text:
            continue
        page.write_text(text.replace("</head>", FEED_LINK + "\n</head>", 1), encoding="utf-8")
        changed += 1
    return changed


def link_sitemap() -> bool:
    sm = SITE_DIR / "sitemap.xml"
    if not sm.exists():
        return False
    text = sm.read_text(encoding="utf-8")
    entry = f"  <url><loc>{SITE}/feed.xml</loc></url>\n"
    if f"{SITE}/feed.xml" in text:
        return False
    sm.write_text(text.replace("</urlset>", entry + "</urlset>", 1), encoding="utf-8")
    return True


XSL = """<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="html" encoding="UTF-8" indent="yes"/>
<xsl:template match="/rss/channel">
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title><xsl:value-of select="title"/></title>
<style>
body{margin:0;background:#f5f7fb;color:#14181f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;line-height:1.55}
.wrap{max-width:760px;margin:0 auto;padding:28px 20px 56px}
h1{font-size:24px;margin:0 0 4px}.sub{color:#5c6470;font-size:14px;margin:0 0 24px}
a{color:#1857e6}.item{background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:18px 20px;margin:0 0 14px}
.item h2{font-size:18px;margin:0 0 6px}.item h2 a{text-decoration:none}
.item time{color:#7a8290;font-size:13px}.item p{margin:8px 0 0;color:#3a424e;font-size:15px}
.note{margin-top:22px;font-size:12.5px;color:#7a8290}
.note a{color:#7a8290}
</style></head><body><div class="wrap">
<h1><xsl:value-of select="title"/></h1>
<p class="sub"><xsl:value-of select="description"/></p>
<xsl:for-each select="item">
<div class="item">
<h2><a href="{link}"><xsl:value-of select="title"/></a></h2>
<time><xsl:value-of select="pubDate"/></time>
<p><xsl:value-of select="description"/></p>
</div>
</xsl:for-each>
<p class="note">RSS 2.0 feed · <a href="https://travel-finds.surge.sh/">travel-finds.surge.sh</a></p>
</div></body></html>
</xsl:template>
</xsl:stylesheet>
"""

def main() -> int:
    feed = build_feed()
    FEED_PATH.write_text(feed, encoding="utf-8")
    (SITE_DIR / "feed.xsl").write_text(XSL, encoding="utf-8")
    (SITE_DIR / "rss.xml").write_text(feed, encoding="utf-8")
    pages = link_pages()
    sitemap = link_sitemap()
    posts = len(list(SITE_DIR.glob("blog/*.html")))
    print(f"feed: {FEED_PATH.relative_to(ROOT)} ({posts} items) | pages linked: {pages} | sitemap updated: {sitemap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
