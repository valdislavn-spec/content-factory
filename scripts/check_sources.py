#!/usr/bin/env python3
"""Проверка RSS/Atom-источников: доступность, свежесть, число материалов.

    python scripts/check_sources.py                       # все источники из конфигов
    python scripts/check_sources.py --url https://a/feed  # отдельные адреса
    python scripts/check_sources.py --candidates candidates.txt

Печатает таблицу: статус, число элементов, дата последнего, первый заголовок.
Код возврата 1, если хоть один источник не отдал материалы.
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; ContentFactory/1.0) AppleWebKit/537.36 Chrome/124"}


def configured_urls() -> List[str]:
    urls: List[str] = []
    for name in ("channels.en.yaml", "channels.es.yaml", "channels.yaml"):
        path = ROOT / "config" / name
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for channel in data.get("channels") or []:
            for source in channel.get("sources") or []:
                if str(source.get("type")) == "rss" and source.get("url"):
                    urls.append(str(source["url"]))
    return sorted(set(urls))


def parse_feed(raw: bytes) -> Dict[str, Any]:
    root = ET.fromstring(raw)
    items = []
    for element in root.iter():
        if element.tag.split("}")[-1] not in ("item", "entry"):
            continue
        title = date = ""
        for child in element:
            tag = child.tag.split("}")[-1]
            if tag == "title":
                title = (child.text or "").strip()
            elif tag in ("pubDate", "updated", "published", "date"):
                date = (child.text or "").strip()
        items.append((title, date))
    return {"count": len(items), "first": items[0][0] if items else "", "date": items[0][1] if items else ""}


def check(url: str) -> Dict[str, Any]:
    try:
        request = urllib.request.Request(url, headers=UA)
        raw = urllib.request.urlopen(request, timeout=25).read()
        info = parse_feed(raw)
        info.update({"url": url, "status": 200, "error": ""})
        return info
    except urllib.error.HTTPError as exc:
        return {"url": url, "status": exc.code, "count": 0, "first": "", "date": "", "error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status": 0, "count": 0, "first": "", "date": "", "error": type(exc).__name__}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка источников")
    parser.add_argument("--url", action="append", default=[], help="адрес (можно несколько)")
    parser.add_argument("--candidates", default="", help="файл со списком адресов")
    parser.add_argument("--min-items", type=int, default=1)
    args = parser.parse_args(argv)

    urls = list(args.url) or configured_urls()
    if args.candidates:
        urls += [line.strip() for line in Path(args.candidates).read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]

    bad = 0
    for url in dict.fromkeys(urls):
        info = check(url)
        ok = info["status"] == 200 and info["count"] >= args.min_items
        bad += 0 if ok else 1
        mark = "OK " if ok else "!! "
        print(f"{mark}{info['status']:>4} items={info['count']:>3}  {url[:70]:<72} {info['first'][:44]} {info['error']}")
    print(f"\nвсего: {len(urls)} · проблемных: {bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
