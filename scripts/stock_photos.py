#!/usr/bin/env python3
"""Free stock photos for pins via Wikimedia Commons (no API key needed).

Pexels API: issuance paused (checked 09.11.2026). Unsplash: registration behind
Cloudflare Turnstile. Commons works without keys — images are CC/PD, we store
license + author credits and render attribution on the pin when required.

Usage:
    python scripts/stock_photos.py --out docs/assets/photos
    python scripts/stock_photos.py --query "Bali rice terrace" --slug bali-photo
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "content-factory/1.0 (travel pins; attribution kept)"
FREE_LICENSES = ("cc0", "public domain", "pd", "cc by 4.0", "cc by 3.0", "cc by-sa 4.0", "cc by-sa 3.0")

QUERIES = {
    "bali": "Bali rice terrace",
    "dubai": "Dubai skyline",
    "lisbon": "Lisbon tram",
    "europe": "Rome Colosseum",
    "esim": "airport terminal traveller phone",
    "car": "coastal road car",
    "flight": "airport departure board",
}


def api(params: dict) -> dict:
    params = {**params, "format": "json"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", text).strip()


def search(query: str, limit: int = 8) -> list[dict]:
    data = api({
        "action": "query", "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}", "gsrlimit": limit, "gsrnamespace": 6,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1600,
    })
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        license_name = clean_html((md.get("LicenseShortName") or {}).get("value", ""))
        if not any(tok in license_name.lower() for tok in FREE_LICENSES):
            continue
        artist = clean_html((md.get("Artist") or {}).get("value", ""))[:80]
        out.append({
            "title": p.get("title"),
            "license": license_name,
            "author": artist,
            "width": ii.get("width"), "height": ii.get("height"),
            "thumb": ii.get("thumburl") or ii.get("url"),
            "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote((p.get("title") or "").replace(" ", "_")),
        })
    # предпочитаем горизонтальные и большие
    out.sort(key=lambda x: (x["width"] or 0) / max(x["height"] or 1, 1), reverse=True)
    return out


def download(item: dict, path: Path) -> None:
    req = urllib.request.Request(item["thumb"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        path.write_bytes(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/assets/photos")
    ap.add_argument("--query")
    ap.add_argument("--slug")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    credits_path = out / "credits.json"
    credits = json.loads(credits_path.read_text()) if credits_path.exists() else {}

    items = [(args.slug, args.query)] if args.query else list(QUERIES.items())
    for slug, query in items:
        results = search(query)
        if not results:
            print(f"{slug}: no free images for '{query}'")
            continue
        pick = results[0]
        dest = out / f"{slug}.jpg"
        try:
            download(pick, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"{slug}: download failed {exc}")
            continue
        credits[slug] = {
            "file": str(dest), "query": query, "license": pick["license"],
            "author": pick["author"], "source": pick["page"],
        }
        print(f"{slug}: OK {pick['license']} | {pick['width']}x{pick['height']} | {dest}")
    credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    print("credits:", credits_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
