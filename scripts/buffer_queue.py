#!/usr/bin/env python3
"""Queue the daily pin in Buffer, adapted per connected network.

Picks one pin per day (rotation by day-of-year), builds network-specific text
(Bluesky / X / Facebook) with a hub link + UTM, then creates one post per
channel with ``mode: addToQueue`` (Buffer queue) or ``customScheduled``.

Env: BUFFER_API_KEY. Dry-run by default; use --live to create posts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.buffer import BufferClient, BufferError  # noqa: E402


def hub_link(base: str, utm: dict) -> str:
    query = urllib.parse.urlencode({k: v for k, v in (utm or {}).items() if v})
    return base + ("?" + query if query else "")


def clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rsplit(" ", 1)[0] + "…"


def build_text(pin: dict, channel: dict, hub_url: str) -> str:
    service = str(channel.get("service") or "")
    limit = int(channel.get("max_chars") or 280)
    title = str(pin.get("title") or "").strip()
    description = str(pin.get("description") or "").strip()
    link = hub_link(hub_url, channel.get("utm") or {})
    disclosure = " Ad" if pin.get("affiliate") else ""
    title_part = clip(title, 90)
    suffix = "\n\n" + link + disclosure
    budget = limit - len(title_part) - len(suffix) - 2
    description_part = clip(description, max(20, budget))
    body = title_part + ("\n\n" + description_part if description_part else "")
    text = body + suffix
    if len(text) > limit:
        text = clip(text, limit)
    return text


def main(argv=None) -> int:
    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config" / "buffer.yaml"))
    parser.add_argument("--pins", default=str(ROOT / "docs" / "assets" / "pins"))
    parser.add_argument("--live", action="store_true", help="create posts (default: dry-run)")
    parser.add_argument("--date", default="", help="override day (YYYY-MM-DD) for rotation/log")
    parser.add_argument("--report", default=str(ROOT / "data" / "reports"))
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    hub_url = str(config.get("hub_url") or "https://valdislavn-spec.github.io/content-factory/")
    org_id = str(config.get("organization_id") or "")
    mode = str(config.get("mode") or "addToQueue")
    channels = config.get("channels") or []

    pin_files = [p for p in sorted(Path(args.pins).glob("*.json")) if p.name != "index.json"]
    if not pin_files:
        print("no pins found in", args.pins)
        return 1
    now = datetime.now(timezone.utc)
    day = args.date or now.strftime("%Y-%m-%d")
    index = now.timetuple().tm_yday % len(pin_files)
    sidecar = json.loads(pin_files[index].read_text(encoding="utf-8"))
    pin_payload = sidecar.get("pin") or {}
    pin = {
        "title": pin_payload.get("title") or sidecar.get("title") or "",
        "description": pin_payload.get("description") or sidecar.get("description") or "",
        "affiliate": bool(sidecar.get("affiliate") or pin_payload.get("link")),
    }
    print("pin:", pin_files[index].name, "| date:", day, "| channels:", len(channels))

    client = BufferClient.from_env() if args.live else BufferClient(token="preview")
    results = []
    for channel in channels:
        text = build_text(pin, channel, hub_url)
        record = {
            "date": day,
            "service": channel.get("service"),
            "channel_id": channel.get("channel_id"),
            "name": channel.get("name"),
            "text": text,
            "chars": len(text),
            "mode": mode,
            "ok": False,
        }
        if args.live:
            try:
                post = client.create_post(
                    str(channel.get("channel_id")),
                    text,
                    mode=mode,
                    metadata=channel.get("metadata"),
                )
                record.update({"ok": True, "post_id": post.get("id"), "due_at": post.get("dueAt")})
                print("queued:", channel.get("service"), "->", post.get("dueAt"))
            except BufferError as error:
                record["error"] = str(error)
                print("FAIL:", channel.get("service"), error)
        else:
            record["ok"] = True
            print("--- %s (%d chars) ---\n%s" % (channel.get("service"), len(text), text))
        results.append(record)

    report_dir = Path(args.report)
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / ("buffer-queue-%s.json" % day)
    report.write_text(json.dumps({"pin": pin_files[index].name, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report:", report)
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
