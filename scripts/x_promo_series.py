"""X promo series via Buffer API."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from content_factory.integrations.buffer import BufferClient, BufferError

DEFAULT_CONFIG = ROOT / "config" / "x_promo_series.yaml"
MAX_WEIGHTED = 280
URL_RE = re.compile(r"https?://\S+")


def x_weighted_length(text: str) -> int:
    return len(URL_RE.sub("x" * 23, text))


def load_series(path: Path) -> List[Dict[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    posts = data.get("series") or []
    result: List[Dict[str, str]] = []
    for index, item in enumerate(posts, 1):
        if not isinstance(item, dict):
            raise ValueError(f"post #{index}: expected object")
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError(f"post #{index}: empty text")
        weighted = x_weighted_length(text)
        if weighted > MAX_WEIGHTED:
            raise ValueError(f"post #{index}: weighted {weighted} > {MAX_WEIGHTED}")
        result.append({"id": str(item.get("id") or f"post-{index}"), "text": text,
                       "raw_len": str(len(text)), "weighted_len": str(weighted)})
    if not result:
        raise ValueError("no posts in series")
    return result


def parse_times(raw: str) -> List[time]:
    values = []
    for part in (raw or "16:00,22:00").split(","):
        part = part.strip()
        if not part:
            continue
        hour, minute = part.split(":", 1)
        values.append(time(int(hour), int(minute), tzinfo=timezone.utc))
    if not values:
        raise ValueError("no valid --times")
    return sorted(values)


def schedule_times(start_date: date, times: List[time], count: int) -> List[datetime]:
    now = datetime.now(timezone.utc)
    slots: List[datetime] = []
    day = 0
    while len(slots) < count:
        current = start_date + timedelta(days=day)
        for slot_time in times:
            due = datetime.combine(current, slot_time)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due > now:
                slots.append(due)
                if len(slots) >= count:
                    break
        day += 1
        if day > 60:
            raise ValueError("could not build schedule")
    return slots


def resolve_x_channel(client: BufferClient) -> str:
    explicit = (os.environ.get("BUFFER_X_CHANNEL_ID") or "").strip()
    if explicit:
        return explicit
    organizations = client.organizations()
    org_ids = [str(item.get("id")) for item in organizations if item.get("id")] or ["68d276b0ab330eddbacc2da8"]
    for org_id in org_ids:
        for channel in client.channels(org_id):
            if str(channel.get("service") or "").lower() in ("twitter", "x"):
                return str(channel.get("id"))
    raise BufferError("X/Twitter channel not found in Buffer")


def print_preview(posts: List[Dict[str, str]], slots: List[datetime]) -> None:
    for index, (post, due) in enumerate(zip(posts, slots), 1):
        stamp = due.isoformat().replace("+00:00", "Z")
        print("\n--- {:02d} {} | due {} | raw {} / weighted {} ---".format(index, post["id"], stamp, post["raw_len"], post["weighted_len"]))
        print(post["text"])


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="X promo series via Buffer")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--live", action="store_true", help="create posts in Buffer")
    parser.add_argument("--start-date", default="", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--times", default="16:00,22:00", help="UTC slots, comma-separated")
    parser.add_argument("--first-now", action="store_true", help="publish the first post now")
    args = parser.parse_args(argv)

    posts = load_series(Path(args.config))
    start = date.fromisoformat(args.start_date) if args.start_date else datetime.now(timezone.utc).date()
    slots = schedule_times(start, parse_times(args.times), len(posts))
    print_preview(posts, slots)
    if not args.live:
        print("\nDRY-RUN: pass --live to create these posts in Buffer.")
        return 0

    client = BufferClient.from_env()
    if not client.configured():
        print("BUFFER_API_KEY is not set", file=sys.stderr)
        return 2
    channel_id = resolve_x_channel(client)
    created = []
    for index, (post, due) in enumerate(zip(posts, slots)):
        try:
            if index == 0 and args.first_now:
                result = client.create_post(channel_id, post["text"], mode="shareNow")
            else:
                result = client.create_post(channel_id, post["text"], mode="customScheduled",
                                            due_at=due.isoformat().replace("+00:00", "Z"))
        except Exception as error:
            print("FAILED {}: {}: {}".format(post["id"], type(error).__name__, error), file=sys.stderr)
            print(json.dumps({"created": created}, ensure_ascii=False, indent=2))
            return 3
        created.append({"id": post["id"], "buffer_id": result.get("id"),
                        "status": result.get("status"), "due_at": result.get("dueAt"),
                        "external_url": result.get("externalLink")})
        print("created {} -> {} {} {}".format(post["id"], result.get("id"), result.get("status"), result.get("dueAt") or ""))
    print(json.dumps({"ok": True, "channel_id": channel_id, "created": created},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
