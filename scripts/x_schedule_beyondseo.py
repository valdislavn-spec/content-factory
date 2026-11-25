#!/usr/bin/env python3
"""Schedule the BeyondSEO X series in Buffer, two posts per week (Mon/Thu 16:00 UTC).

Reads config/x_promo_series_beyondseo.yaml and creates customScheduled posts on
the X channel. Dry-run by default; --live creates real Buffer posts.

    python3 scripts/x_schedule_beyondseo.py --dry-run
    python3 scripts/x_schedule_beyondseo.py --live
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.buffer import ORG_ID, BufferClient, BufferError  # noqa: E402

CONFIG = ROOT / "config" / "x_promo_series_beyondseo.yaml"
SLOT_HOUR_UTC = 16
WEEKDAYS = (0, 1, 3, 4)  # Monday, Tuesday, Thursday, Friday
MAX_WEIGHTED = 280
import re

URL_RE = re.compile(r"https?://\S+")


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


def weighted(text: str) -> int:
    return len(URL_RE.sub("x" * 23, text))


def load_posts() -> list[dict[str, str]]:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    posts = []
    for index, item in enumerate(data.get("series") or [], 1):
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError("post #{n} is empty".format(n=index))
        size = weighted(text)
        if size > MAX_WEIGHTED:
            raise ValueError("post #{n} weighted {s} > 280".format(n=index, s=size))
        posts.append({"id": str(item.get("id") or "post-{n}".format(n=index)), "text": text, "weighted": str(size)})
    if not posts:
        raise ValueError("series is empty")
    return posts


def slots(count: int, start: datetime, weekdays: tuple[int, ...] = WEEKDAYS) -> list[datetime]:
    result: list[datetime] = []
    day = start
    while len(result) < count:
        if day.weekday() in weekdays:
            due = day.replace(hour=SLOT_HOUR_UTC, minute=0, second=0, microsecond=0)
            if due > start:
                result.append(due)
        day += timedelta(days=1)
        if (day - start).days > 120:
            raise ValueError("could not build schedule")
    return result


def resolve_channels(client: BufferClient) -> str:
    explicit = ""
    env_value = __import__("os").environ.get("BUFFER_X_CHANNEL_ID", "").strip()
    if env_value:
        return env_value
    for org in client.organizations():
        for channel in client.channels(str(org.get("id"))):
            if str(channel.get("service") or "").lower() in ("twitter", "x"):
                return str(channel.get("id"))
    raise BufferError("X/Twitter channel not found in Buffer")


POSTS_QUERY = """
query Posts($org: OrganizationId!, $channel: [ChannelId!], $first: Int, $after: String) {
  posts(input: {organizationId: $org, filter: {channelIds: $channel}}, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges { node { id text status dueAt channelId } }
  }
}
"""

ACTIVE_STATUSES = {"scheduled", "queued", "draft", "added", "pending"}


def list_channel_posts(client: BufferClient, channel_id: str) -> list[dict]:
    nodes: list[dict] = []
    after: str | None = None
    for _ in range(20):
        data = client.gql(POSTS_QUERY, {"org": ORG_ID, "channel": [channel_id], "first": 50, "after": after})
        page = data.get("posts") or {}
        nodes.extend(edge.get("node") or {} for edge in (page.get("edges") or []))
        info = page.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
    return [node for node in nodes if str(node.get("channelId") or "") == channel_id]


def delete_scheduled_copies(client: BufferClient, channel_id: str, posts: list[dict[str, str]]) -> list[str]:
    nodes = list_channel_posts(client, channel_id)
    wanted = {post["text"].strip(): post["id"] for post in posts}
    removed: list[str] = []
    for node in nodes:
        if str(node.get("channelId") or "") != channel_id:
            continue
        if str(node.get("status") or "").lower() not in ACTIVE_STATUSES:
            continue
        text = str(node.get("text") or "").strip()
        if text not in wanted:
            continue
        client.delete_post(str(node["id"]))
        removed.append(wanted[text])
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="create posts in Buffer")
    parser.add_argument("--dry-run", action="store_true", help="preview only (default)")
    parser.add_argument("--start", default="", help="YYYY-MM-DD, default today UTC")
    parser.add_argument("--weekdays", default="0,1,3,4", help="ISO weekdays, 1=Mon (default Mon,Tue,Thu,Fri)")
    parser.add_argument("--replace", action="store_true", help="delete already scheduled copies of these posts first")
    args = parser.parse_args()

    posts = load_posts()
    start = datetime.now(timezone.utc)
    if args.start:
        start = datetime.fromisoformat(args.start + "T00:00:00+00:00")
    weekdays = tuple(int(part.strip()) for part in args.weekdays.split(",") if part.strip())
    if not weekdays or any(day < 0 or day > 6 for day in weekdays):
        print("--weekdays expects ISO days 0-6", file=sys.stderr)
        return 2
    due = slots(len(posts), start, weekdays)
    for post, when in zip(posts, due):
        print("{when} | {id} | weighted {size}\n{text}\n".format(
            when=when.strftime("%Y-%m-%d %H:%M UTC"), id=post["id"], size=post["weighted"], text=post["text"]))

    if not args.live:
        print("DRY-RUN: {n} posts planned, nothing sent.".format(n=len(posts)))
        return 0

    env = load_env(ROOT / ".env")
    token = env.get("BUFFER_API_KEY", "")
    if not token:
        print("BUFFER_API_KEY missing in content-factory/.env", file=sys.stderr)
        return 2
    import os

    os.environ.setdefault("BUFFER_API_KEY", token)
    client = BufferClient.from_env()
    channel_id = resolve_channels(client)
    if args.replace:
        removed = delete_scheduled_copies(client, channel_id, posts)
        print("removed old scheduled posts: {items}".format(items=", ".join(removed) or "none"))
    created = []
    for post, when in zip(posts, due):
        try:
            result = client.create_post(
                channel_id,
                post["text"],
                mode="customScheduled",
                due_at=when.isoformat().replace("+00:00", "Z"),
            )
        except BufferError as error:
            print("FAILED {id}: {err}".format(id=post["id"], err=error), file=sys.stderr)
            print(json.dumps({"created": created}, ensure_ascii=False, indent=1))
            return 3
        created.append({"id": post["id"], "buffer_id": result.get("id"), "due_at": result.get("dueAt"), "status": result.get("status")})
        print("created {id} -> {bid} due {due}".format(id=post["id"], bid=result.get("id"), due=result.get("dueAt")))
    print(json.dumps({"ok": True, "created": created}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
