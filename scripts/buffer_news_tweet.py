"""Safe Buffer news hook.

The old launchd job expected this file. By default it prepares a draft and
exits successfully; actual posting requires BUFFER_NEWS_LIVE=1 and a Buffer key.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "buffer-news"


def read_key() -> str:
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if key:
        return key
    path = ROOT.parent / ".local" / "affiliate" / "buffer-api-key.txt"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", default="auto")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    key = read_key()
    payload = {
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "niche": args.niche,
        "live_requested": args.live,
        "buffer_key_present": bool(key),
        "status": "draft",
        "note": "Add BUFFER_NEWS_LIVE=1 and a reviewed headline before enabling posting.",
    }
    path = OUT / ("draft-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M") + ".json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("buffer-news draft: " + str(path))
    if args.live and os.environ.get("BUFFER_NEWS_LIVE") == "1" and key:
        print("live posting is intentionally disabled in this build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
