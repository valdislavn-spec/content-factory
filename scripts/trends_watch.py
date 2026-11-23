"""Collect Google Trends headlines into a local JSON snapshot.

The launchd job asks for --post/--publish; this script only records trends and
never publishes automatically. That keeps the watchdog useful without creating
unreviewed posts.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "trends"


def fetch(geo: str) -> list[str]:
    url = "https://trends.google.com/trending/rss?geo=" + geo
    request = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0 (TrendsWatch/1.0)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())
    titles = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if title:
            titles.append(title)
    return titles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--geo", default="US")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        titles = fetch(args.geo)
    except Exception as exc:
        print("trends unavailable: " + type(exc).__name__ + ": " + str(exc))
        return 0
    payload = {
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "geo": args.geo,
        "hours": args.hours,
        "titles": titles[:30],
    }
    path = OUT / "latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("trends: " + str(len(payload["titles"])) + " -> " + str(path))
    if args.post or args.publish:
        print("publish skipped: trends are review-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
