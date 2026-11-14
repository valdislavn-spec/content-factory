#!/usr/bin/env python3
"""RSS-фид для Pinterest и читалок: travel-гиды с картинками.

    ./.venv/bin/python scripts/build_feed.py

Пишет docs/feed.xml. Каждый элемент — гид + пин 1000×1500 в enclosure и
media:content, чтобы RSS→Pinterest сервисы могли создать пин с картинкой.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
GUIDES = DOCS / "travel"
PINS = DOCS / "assets" / "pins-travel"
BASE = "https://valdislavn-spec.github.io/content-factory"
OUT = DOCS / "feed.xml"

# гид → слаг пина (bottom-вариант: текст внизу, лучше читается в ленте)
ITEMS = [
    ("europe-under-300", "Travel on a budget", "Europe for under $300"),
    ("bali-budget", "Travel on a budget", "Bali on a budget"),
    ("rome-48-hours", "City breaks", "48 hours in Rome"),
    ("travel-esim", "Travel tips", "Travel eSIM: internet abroad"),
    ("car-rental-europe", "Travel tips", "Car rental without hidden fees"),
    ("airport-transfer-guide", "Travel tips", "Airport transfers: fixed price"),
    ("luggage-storage-guide", "Travel tips", "Luggage storage guide"),
    ("skip-the-line-tickets-guide", "City breaks", "Skip-the-line tickets"),
    ("almaty-48-hours", "City breaks", "48 hours in Almaty"),
    ("minsk-weekend", "City breaks", "Minsk weekend guide"),
]


def page_meta(slug: str) -> tuple[str, str]:
    source = (GUIDES / f"{slug}.html").read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", source, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', source)
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S)
    text_title = html_lib.unescape(re.sub(r"<[^>]+>", "", heading.group(1))).strip() if heading else slug
    description = html_lib.unescape(desc.group(1)).strip() if desc else text_title
    return text_title, description


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        "  <channel>",
        "    <title>Content Factory — travel guides</title>",
        f"    <link>{BASE}/travel/</link>",
        "    <description>Budget travel guides: flights, eSIM, transfers, city breaks. English.</description>",
        "    <language>en</language>",
        f"    <lastBuildDate>{format_datetime(now)}</lastBuildDate>",
        f"    <atom:link href=\"{BASE}/feed.xml\" rel=\"self\" type=\"application/rss+xml\" xmlns:atom=\"http://www.w3.org/2005/Atom\"/>",
    ]

    for index, (slug, board, fallback_title) in enumerate(ITEMS):
        title, description = page_meta(slug)
        title = title or fallback_title
        link = f"{BASE}/travel/{slug}.html"
        image = f"{BASE}/assets/pins-travel/{slug}-bottom.jpg"
        image_path = PINS / f"{slug}-bottom.jpg"
        size = image_path.stat().st_size if image_path.exists() else 0
        published = now - timedelta(days=len(ITEMS) - index)
        lines += [
            "    <item>",
            f"      <title>{escape(title)}</title>",
            f"      <link>{link}</link>",
            f"      <guid isPermaLink=\"true\">{link}</guid>",
            f"      <description>{escape(description)}</description>",
            f"      <category>{escape(board)}</category>",
            f"      <pubDate>{format_datetime(published)}</pubDate>",
            f'      <enclosure url="{image}" type="image/jpeg" length="{size}"/>',
            f'      <media:content url="{image}" medium="image" type="image/jpeg">',
            '        <media:title type="plain">' + escape(title) + "</media:title>",
            "      </media:content>",
            "    </item>",
        ]

    lines += ["  </channel>", "</rss>", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"feed: {OUT.relative_to(ROOT)} · элементов: {len(ITEMS)} · {OUT.stat().st_size} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
