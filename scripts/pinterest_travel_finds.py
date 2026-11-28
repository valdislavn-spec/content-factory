#!/usr/bin/env python3
"""Pinterest API helper for the Travel Finds pins (list boards / publish pins).

Uses only stdlib. Credentials come from the environment (GitHub Actions secrets):

* ``PINTEREST_ACCESS_TOKEN`` — token with ``boards:read`` / ``pins:write``
* ``PINTEREST_BOARD_ID``    — default board id (optional with --board)
* ``PINTEREST_API_BASE``    — defaults to https://api.pinterest.com/v5

Modes:
    --list                 print every board id + name (no writes)
    --publish FILE         publish pins from a meta.json sidecar list
                           (pins already on the board are skipped, never duplicated)
    --verify FILE          report which meta.json pins are already on the board
    --dry-run              with --publish: print payloads without API calls

Example:
    python scripts/pinterest_travel_finds.py --list
    python scripts/pinterest_travel_finds.py --verify docs/travel-finds/pins/meta.json --board 123
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
TRACKER_REDIRECT_PREFIX = "https://links-tracker.valdislav-n.workers.dev/r/"


def is_tracked_link(link: str) -> bool:
    return str(link or "").strip().startswith(TRACKER_REDIRECT_PREFIX)


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


def entry_body(entry: dict, board_id: str) -> dict:
    payload = entry.get("payload") or {}
    return {
        "board_id": board_id,
        "title": payload.get("title") or entry.get("title", ""),
        "description": payload.get("description", ""),
        "link": payload.get("link") or entry.get("link", ""),
        "alt_text": payload.get("alt_text", ""),
        "media_source": {"source_type": "image_url", "url": entry.get("image_url", "")},
    }


def board_pins(board_id: str) -> list[dict]:
    """All pins on a board (paginated by bookmark)."""
    pins: list[dict] = []
    bookmark = ""
    while True:
        query = f"?page_size=100" + (f"&bookmark={bookmark}" if bookmark else "")
        status, payload = call("GET", f"{BOARDS}/{board_id}/pins{query}")
        if status != 200:
            raise SystemExit(f"board pins request failed: {status} {payload}")
        pins.extend(payload.get("items") or [])
        bookmark = payload.get("bookmark") or ""
        if not bookmark:
            return pins


def find_existing(pins: list[dict], body: dict) -> dict | None:
    """Match a pin payload against existing board pins by tracked link, then by title."""
    link = (body.get("link") or "").strip()
    title = (body.get("title") or "").strip().lower()
    for pin in pins:
        if link and (pin.get("link") or "").strip() == link:
            return pin
    for pin in pins:
        if title and (pin.get("title") or "").strip().lower() == title:
            return pin
    return None


def verify(meta_path: Path, board_id: str) -> int:
    entries = json.loads(meta_path.read_text(encoding="utf-8"))
    pins = board_pins(board_id)
    published = 0
    missing = 0
    for entry in entries:
        body = entry_body(entry, board_id)
        found = find_existing(pins, body)
        if found:
            published += 1
            print(f"[published] {found.get('id')} {str(found.get('created_at'))[:10]}  {body['title'][:60]}")
        else:
            missing += 1
            print(f"[missing]   {body['title'][:60]}  -> {body['link']}")
    print(f"verify: {published}/{len(entries)} published, {missing} missing (board {board_id})")
    return 0 if missing == 0 else 1


def publish(meta_path: Path, board_id: str, dry_run: bool) -> int:
    entries = json.loads(meta_path.read_text(encoding="utf-8"))
    existing = [] if dry_run else board_pins(board_id)
    ok = 0
    skipped = 0
    pending = 0
    invalid = 0
    for entry in entries:
        body = entry_body(entry, board_id)
        if is_tracked_link(body["link"]) is False:
            invalid += 1
            print(f"[skip] {body['title'][:60]} — link is not a tracked /r/ URL: {body['link']}", file=sys.stderr)
            continue
        found = find_existing(existing, body)
        if found:
            skipped += 1
            print(f"[exists] {found.get('id')}  {body['title'][:60]}")
            continue
        if dry_run:
            print(f"[dry-run] {body['title'][:60]} -> board {board_id} | {body['link']}")
            continue
        status, response = call("POST", API, body)
        if status in (200, 201):
            ok += 1
            print(f"published: {response.get('id')}  {body['title'][:60]}")
        elif status == 403 and "trial" in json.dumps(response, ensure_ascii=False).lower():
            pending += 1
            print(f"[pending] {body['title'][:60]} — Standard access ещё не одобрен (Trial)")
        else:
            print(f"failed ({status}): {response}", file=sys.stderr)
    suffix = f" (pending: {pending})" if pending else ""
    extra = f" | already on board: {skipped}" if skipped else ""
    print(f"done: {ok}/{len(entries)} published{suffix}{extra}" + (f" | invalid links: {invalid}" if invalid else ""))
    if invalid:
        return 1
    return 0 if dry_run or ok + skipped + pending == len(entries) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list boards and exit")
    parser.add_argument("--publish", metavar="META_JSON", help="publish pins from a meta.json")
    parser.add_argument("--verify", metavar="META_JSON", help="check which meta.json pins are already on the board")
    parser.add_argument("--board", default=os.environ.get("PINTEREST_BOARD_ID", ""), help="board id")
    parser.add_argument("--dry-run", action="store_true", help="do not call the API when publishing")
    args = parser.parse_args(argv)
    if args.list:
        return list_boards()
    meta = args.publish or args.verify
    if not meta:
        parser.error("use --list, --publish META_JSON or --verify META_JSON")
    if not args.board and not args.dry_run:
        parser.error("board id is required (--board or PINTEREST_BOARD_ID)")
    if args.verify:
        return verify(Path(args.verify), args.board)
    return publish(Path(meta), args.board, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
