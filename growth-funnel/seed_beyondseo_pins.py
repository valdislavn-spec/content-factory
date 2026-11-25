#!/usr/bin/env python3
"""Seed the D1 growth queue with the BeyondSEO Pinterest pin set, 2 pins/day.

Reads docs/travel-finds/pins/beyondseo-pins.json (rendered by
scripts/build_beyondseo_pins.py) and seeds platform=pinterest items into
the links-tracker admin queue, two per day starting --start (default today).

The local Playwright scheduler publishes one due item per 6 h, so two due
items per day land as 2 pins/day.

    python3 growth-funnel/seed_beyondseo_pins.py --dry-run
    python3 growth-funnel/seed_beyondseo_pins.py --start 2026-11-24
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "docs" / "travel-finds" / "pins" / "beyondseo-pins.json"
QUEUE_URL = "https://links-tracker.valdislav-n.workers.dev/admin/queue"
PER_DAY = 2


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def build_items(start: date, dues: list[str] | None = None) -> list[dict]:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    items = []
    for index, pin in enumerate(pins):
        payload = pin["payload"]
        if dues:
            due = dues[index]
        else:
            due = (start + timedelta(days=index // PER_DAY)).isoformat()
        items.append(
            {
                "id": "pinterest-{slug}".format(slug=pin["slug"]),
                "platform": "pinterest",
                "due": due,
                "status": "queued",
                "title": payload["title"],
                "description": payload["description"],
                "link": payload["link"],
                "board": payload["board"],
                "image": pin["file"],
                "attempts": 0,
            }
        )
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="", help="YYYY-MM-DD, default today")
    parser.add_argument("--due", default="", help="comma list of due dates, one per pin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start = date.fromisoformat(args.start) if args.start else date.today()
    dues = [part.strip() for part in args.due.split(",") if part.strip()] or None
    if dues and len(dues) != len(json.loads(PINS.read_text(encoding="utf-8"))):
        print("--due needs one date per pin", file=sys.stderr)
        return 2
    items = build_items(start, dues)
    closed = sum(1 for item in items if item["due"] < date.today().isoformat())
    if closed:
        print("WARN: {n} items have a past due date".format(n=closed), file=sys.stderr)

    if args.dry_run:
        for item in items:
            print("{due} | {board:14} | {id} | {image}".format(**{
                "due": item["due"], "board": item["board"], "id": item["id"], "image": item["image"]}))
        print("DRY-RUN: {n} items, nothing sent".format(n=len(items)))
        return 0

    env = load_env(ROOT / ".env")
    token = env.get("LINK_TRACKER_ADMIN_TOKEN", "")
    if not token:
        print("LINK_TRACKER_ADMIN_TOKEN missing in content-factory/.env", file=sys.stderr)
        return 2

    body = json.dumps(items, ensure_ascii=False).encode("utf-8")
    import urllib.request

    request = urllib.request.Request(
        QUEUE_URL + "/seed",
        data=body,
        headers={
            "x-token": token,
            "content-type": "application/json",
            "User-Agent": "curl/8.7.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001
        print("seed failed: {err}".format(err=error), file=sys.stderr)
        return 3
    print(json.dumps({"ok": result.get("ok"), "seeded": len(items), "due": sorted({i["due"] for i in items})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
