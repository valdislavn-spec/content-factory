#!/usr/bin/env python3
"""Build a Pinterest bulk-upload CSV from generated pin sidecars.

Pinterest Settings → Import content accepts a CSV with columns:
Title (required), Media URL (required), Pinterest board (required),
Thumbnail, Description, Link, Publish date, Keywords.
Boards that do not exist are created automatically.

Usage: python scripts/build_pinterest_csv.py --pins docs/assets/pins --out docs/pinterest-import.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

BOARD_BY_NICHE = {
    "travel": "Travel ideas",
    "crypto": "Crypto",
    "ai": "AI tools",
    "sports": "Sports",
}
KEYWORDS_BY_NICHE = {
    "travel": "travel tips, city breaks, budget travel",
    "crypto": "bitcoin, crypto news, prediction markets",
    "ai": "ai tools, productivity, ai news",
    "sports": "nfl, sports picks, sports news",
}
HUB = "https://valdislavn-spec.github.io/content-factory/"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pins", default="docs/assets/pins")
    parser.add_argument("--out", default="docs/pinterest-import.csv")
    parser.add_argument("--link", default=HUB)
    args = parser.parse_args(argv)

    rows = []
    for path in sorted(Path(args.pins).glob("*.json")):
        if path.name == "index.json":
            continue
        meta = json.loads(path.read_text(encoding="utf-8"))
        pin = meta.get("pin") or {}
        niche = str(meta.get("niche") or "travel")
        rows.append(
            {
                "Title": str(pin.get("title") or "")[:100],
                "Media URL": meta.get("image_url") or "",
                "Pinterest board": BOARD_BY_NICHE.get(niche, "Pins"),
                "Thumbnail": "",
                "Description": str(pin.get("description") or "")[:500],
                "Link": str(pin.get("link") or args.link),
                "Publish date": "",
                "Keywords": KEYWORDS_BY_NICHE.get(niche, "news"),
            }
        )
    if not rows:
        print("no pin sidecars found")
        return 1
    columns = ["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"]
    out = Path(args.out)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print("csv rows:", len(rows), "->", out)
    for row in rows:
        print(" -", row["Pinterest board"], "|", row["Title"], "|", row["Media URL"][:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
