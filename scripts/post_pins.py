#!/usr/bin/env python3
"""Post generated pins (JSON sidecars from generate_pins.py) to Pinterest API v5.

Requires PINTEREST_ACCESS_TOKEN with pins:write, and a board id either in
PINTEREST_BOARD_ID or passed with --board. Dry-run by default; use --live.
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="folder with *.json sidecars")
    parser.add_argument("--board", default=os.environ.get("PINTEREST_BOARD_ID", ""))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--live", action="store_true", help="actually create pins (default: dry-run)")
    parser.add_argument("--only-affiliate", action="store_true", help="post only pins with affiliate links")
    args = parser.parse_args(argv)

    token = os.environ.get("PINTEREST_ACCESS_TOKEN", "").strip()
    if not token:
        print("PINTEREST_ACCESS_TOKEN is not set")
        return 1
    files = sorted(Path(args.dir).glob("*.json"))
    files = [f for f in files if f.name != "index.json"]
    payloads = []
    for file in files:
        meta = json.loads(file.read_text(encoding="utf-8"))
        if args.only_affiliate and not meta.get("affiliate"):
            continue
        payload = dict(meta.get("pin") or {})
        if args.board:
            payload["board_id"] = args.board
        if "<BOARD_ID>" in str(payload.get("board_id", "")):
            print("skip %s: board id is not set" % file.name)
            continue
        payloads.append((file.name, payload))
    if args.limit:
        payloads = payloads[: args.limit]

    for name, payload in payloads:
        if not args.live:
            print("[dry-run] %s -> %s | %s" % (name, payload.get("title"), payload.get("link", "")))
            continue
        request = urllib.request.Request(
            API,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "User-Agent": "content-factory-pins/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            print("posted %s: https://www.pinterest.com/pin/%s/" % (name, data.get("id")))
        except urllib.error.HTTPError as error:
            print("FAIL %s: HTTP %s %s" % (name, error.code, error.read()[:300]))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
