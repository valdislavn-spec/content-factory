#!/usr/bin/env python3
"""Pinterest API helper for the Travel Finds pins (list boards / publish pins).

Uses only stdlib. Credentials come from the environment (GitHub Actions secrets):

* ``PINTEREST_ACCESS_TOKEN`` — token with ``boards:read`` / ``pins:write``
* ``PINTEREST_BOARD_ID``    — default board id (optional with --board)
* ``PINTEREST_API_BASE``    — defaults to https://api.pinterest.com/v5

Modes:
    --list                 print every board id + name (no writes)
    --publish FILE         publish pins from a meta.json sidecar list
    --dry-run              with --publish: print payloads without API calls

Example:
    python scripts/pinterest_travel_finds.py --list
    python scripts/pinterest_travel_finds.py --publish docs/travel-finds/pins/meta.json --board 123
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = (os.environ.get("PINTEREST_API_BASE") or "https://api.pinterest.com/v5").rstrip("/")
API = API_BASE + "/pins"
BOARDS = API_BASE + "/boards"


def token() -> str:
    value = os.environ.get("PINTEREST_ACCESS_TOKEN", "").strip()
    if not value:
        raise SystemExit("PINTEREST_ACCESS_TOKEN is not set")
    return value


def call(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
            "User-Agent": "content-factory/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:500]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, {"error": raw[:500]}


def list_boards() -> int:
    status, payload = call("GET", f"{BOARDS}?page_size=100")
    if status != 200:
        print(f"boards request failed: {status} {payload}", file=sys.stderr)
        return 1
    items = payload.get("items") or []
    print(f"boards: {len(items)}")
    for item in items:
        print(f"  {item.get('id')}  {item.get('name')}  ({item.get('pin_count', '?')} pins)")
    return 0


def publish(meta_path: Path, board_id: str, dry_run: bool) -> int:
    entries = json.loads(meta_path.read_text(encoding="utf-8"))
    ok = 0
    for entry in entries:
        payload = entry.get("payload") or {}
        body = {
            "board_id": board_id,
            "title": payload.get("title") or entry.get("title", ""),
            "description": payload.get("description", ""),
            "link": payload.get("link") or entry.get("link", ""),
            "alt_text": payload.get("alt_text", ""),
            "media_source": {"source_type": "image_url", "url": entry.get("image_url", "")},
        }
        if dry_run:
            print(f"[dry-run] {body['title'][:60]} -> board {board_id}")
            continue
        status, response = call("POST", API, body)
        if status in (200, 201):
            ok += 1
            print(f"published: {response.get('id')}  {body['title'][:60]}")
        else:
            print(f"failed ({status}): {response}", file=sys.stderr)
    print(f"done: {ok}/{len(entries)} published")
    return 0 if ok == len(entries) or dry_run else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list boards and exit")
    parser.add_argument("--publish", metavar="META_JSON", help="publish pins from a meta.json")
    parser.add_argument("--board", default=os.environ.get("PINTEREST_BOARD_ID", ""), help="board id")
    parser.add_argument("--dry-run", action="store_true", help="do not call the API when publishing")
    args = parser.parse_args(argv)
    if args.list:
        return list_boards()
    if not args.publish:
        parser.error("use --list or --publish META_JSON")
    if not args.board and not args.dry_run:
        parser.error("board id is required (--board or PINTEREST_BOARD_ID)")
    return publish(Path(args.publish), args.board, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
