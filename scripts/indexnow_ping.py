#!/usr/bin/env python3
"""Ping IndexNow (Bing, Yandex, Seznam) with all hub URLs from sitemap.xml.

IndexNow instantly notifies search engines about new/updated pages — free traffic
for the travel guides and channel pages. Env: INDEXNOW_KEY (host it at /<key>.txt).

    INDEXNOW_KEY=... python scripts/indexnow_ping.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "docs" / "sitemap.xml"
ENDPOINT = "https://api.indexnow.org/indexnow"
HOST = "valdislavn-spec.github.io"
# GitHub Pages отдаёт репозиторий как project page: docs/… → /content-factory/…
# keyLocation должен быть на том же хосте, но файл лежит под /content-factory/.
SITE_PATH = "/content-factory"


def main() -> int:
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if not key:
        print("INDEXNOW_KEY is not set")
        return 2
    urls = re.findall(r"<loc>([^<]+)</loc>", SITEMAP.read_text(encoding="utf-8"))
    if not urls:
        print("no urls in sitemap")
        return 1
    payload = json.dumps({"host": HOST, "key": key,
                          "keyLocation": f"https://{HOST}{SITE_PATH}/{key}.txt",
                          "urlList": urls}).encode()
    request = urllib.request.Request(ENDPOINT, data=payload, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "content-factory-indexnow/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print("indexnow: HTTP", response.status, "| urls:", len(urls))
            return 0
    except Exception as error:  # noqa: BLE001
        print("indexnow error:", type(error).__name__, str(error)[:200])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
