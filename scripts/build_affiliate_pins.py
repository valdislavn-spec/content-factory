#!/usr/bin/env python3
"""Turn travel pins into Travelpayouts affiliate pins + rebuild Pinterest CSV.

Pipeline:
1. read config/travelpayouts.yaml (programs + pin → program mapping);
2. convert brand URLs to partner links via Travelpayouts links API;
3. write hub redirect pages docs/go/<slug>.html (noindex) for each converted pin;
4. rebuild docs/pinterest-import.csv with Link = <hub>/go/<slug>.html for those
   pins and the plain hub for the rest.

Env: TRAVELPAYOUTS_TOKEN, TRAVELPAYOUTS_MARKER, TRAVELPAYOUTS_TRS.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.travelpayouts import (  # noqa: E402
    TravelpayoutsClient,
    TravelpayoutsError,
    partner_url,
    redirect_page,
)

COLUMNS = ["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"]
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


def main(argv=None) -> int:
    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config" / "travelpayouts.yaml"))
    parser.add_argument("--pins", default=str(ROOT / "docs" / "assets" / "pins"))
    parser.add_argument("--go-dir", default=str(ROOT / "docs" / "go"))
    parser.add_argument("--csv", default=str(ROOT / "docs" / "pinterest-import.csv"))
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    hub = str(config.get("hub_public_base") or "https://valdislavn-spec.github.io/content-factory").rstrip("/")
    programs = config.get("programs") or {}
    mapping = config.get("pins") or {}

    client = TravelpayoutsClient.from_env()
    if not client.configured():
        print("Travelpayouts is not configured: set TRAVELPAYOUTS_TOKEN / TRAVELPAYOUTS_MARKER / TRAVELPAYOUTS_TRS")
        return 2

    # collect pins
    pins = {}
    for path in sorted(Path(args.pins).glob("*.json")):
        if path.name == "index.json":
            continue
        meta = json.loads(path.read_text(encoding="utf-8"))
        pins[path.stem] = meta

    to_convert = []
    for slug, rule in mapping.items():
        if slug not in pins:
            continue
        program = str(rule.get("program") or "").strip()
        target = str(programs.get(program) or "").strip()
        if not program or not target:
            continue
        to_convert.append({"url": target, "sub_id": str(rule.get("sub_id") or slug)})

    try:
        converted = client.convert(to_convert, shorten=bool(config.get("shorten", True)))
    except TravelpayoutsError as error:
        print("Travelpayouts API error:", error)
        return 1

    by_url = {}
    for item in converted:
        url = str(item.get("url") or "")
        if url:
            by_url[url] = item

    go_dir = Path(args.go_dir)
    go_dir.mkdir(parents=True, exist_ok=True)
    affiliate_map = {}
    for slug, rule in mapping.items():
        if slug not in pins:
            continue
        program = str(rule.get("program") or "").strip()
        target = str(programs.get(program) or "").strip()
        item = by_url.get(target)
        link = partner_url(item or {}, target)
        if not link:
            print("skip (conversion failed):", slug, program)
            continue
        page = go_dir / (slug + ".html")
        page.write_text(redirect_page(link, title="Redirecting to our travel partner"), encoding="utf-8")
        affiliate_map[slug] = {"program": program, "partner_url": link, "hub_link": "%s/go/%s.html" % (hub, slug)}
        print("affiliate page:", page.name, "->", program)

    (go_dir / "affiliate-map.json").write_text(json.dumps(affiliate_map, indent=2), encoding="utf-8")

    rows = []
    for slug, meta in pins.items():
        pin = meta.get("pin") or {}
        niche = str(meta.get("niche") or "travel")
        link = affiliate_map.get(slug, {}).get("hub_link") or (hub + "/")
        description = str(pin.get("description") or "")
        if slug in affiliate_map and "Ad" not in description:
            description = (description + " Ad · affiliate link")[:500]
        rows.append(
            {
                "Title": str(pin.get("title") or "")[:100],
                "Media URL": meta.get("image_url") or "",
                "Pinterest board": BOARD_BY_NICHE.get(niche, "Pins"),
                "Thumbnail": "",
                "Description": description[:500],
                "Link": link,
                "Publish date": "",
                "Keywords": KEYWORDS_BY_NICHE.get(niche, "news"),
            }
        )
    with Path(args.csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print("csv:", len(rows), "rows ->", args.csv, "| affiliate pins:", len(affiliate_map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
