#!/usr/bin/env python3
"""US-новости в Reddit: собирает свежие новости EN-каналов и публикует дайджест
одним self-постом в сабреддит.

    python scripts/reddit_digest.py --hours 6 --limit 7          # dry-run (показ)
    python scripts/reddit_digest.py --hours 6 --limit 7 --live   # публикация

Нужны REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD/SUBREDDIT (в GitHub Secrets).
Дневной лимит постов — settings.publishers.reddit.daily_limit (по умолчанию 3).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_channels  # noqa: E402
from content_factory.models import Article, ChannelConfig, GeneratedPost  # noqa: E402
from content_factory.pipeline import filter_articles  # noqa: E402
from content_factory.publishers.reddit import RedditPublisher  # noqa: E402
from content_factory.sources import get_adapter  # noqa: E402

US_CHANNELS = ("crypto-news", "ai-news", "sport-news")
BUDGET = ROOT / "data" / "reddit_usage.json"
MAX_TITLE = 300


CHANNEL_QUOTA = {"crypto-news": 3, "ai-news": 2, "sport-news": 2}


def collect(hours: float, limit: int) -> list[Article]:
    settings = Settings.load()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    channels = {c.id: c for c in load_channels(settings, path="config/channels.en.yaml")}
    picked: list[Article] = []
    seen: set[str] = set()
    per_channel: dict[str, list[Article]] = {}
    for channel_id in US_CHANNELS:
        channel = channels.get(channel_id)
        if channel is None:
            continue
        collected = []
        for source in channel.sources:
            if not source.enabled:
                continue
            try:
                collected.extend(get_adapter(source.type).fetch(source, settings) or [])
            except Exception:  # noqa: BLE001 - источник не должен ронять дайджест
                continue
        for article in filter_articles(channel, collected, settings, now=now):
            published = article.published_at
            if published is None:
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < cutoff:
                continue
            key = (article.title or "").strip().lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            picked.append(article)
            per_channel.setdefault(channel_id, []).append(article)
    # Сначала квоты по темам (крипто/AI/спорт), чтобы дайджест был смешанным,
    # потом добор самыми свежими из оставшихся.
    picked.sort(key=lambda article: article.published_at, reverse=True)
    chosen: list[Article] = []
    chosen_ids: set[str] = set()
    for channel_id in US_CHANNELS:
        quota = CHANNEL_QUOTA.get(channel_id, 2)
        for article in per_channel.get(channel_id, [])[:quota]:
            if article.id in chosen_ids:
                continue
            chosen.append(article)
            chosen_ids.add(article.id)
    for article in picked:
        if len(chosen) >= limit:
            break
        if article.id not in chosen_ids:
            chosen.append(article)
            chosen_ids.add(article.id)
    chosen.sort(key=lambda article: article.published_at, reverse=True)
    return chosen[:limit]


def build_post(articles: list[Article], subreddit: str) -> GeneratedPost:
    now = datetime.now(timezone.utc)
    top = articles[0].title if articles else "US news"
    title = "US brief: {} + {} more".format(top[:180].rstrip(), max(0, len(articles) - 1))[:MAX_TITLE]
    lines = [
        "US news roundup · {}".format(now.strftime("%d.%m %H:%M UTC")),
        "",
    ]
    for article in articles:
        lines.append("• {}".format((article.title or "").strip()))
        lines.append("  {}".format(article.source_name))
    lines.append("")
    lines.append("Sources:")
    for article in articles:
        lines.append("- {}".format(article.url))
    text = "\n".join(lines)
    post = GeneratedPost(
        id="reddit-{}".format(now.strftime("%Y%m%d%H%M")),
        channel_id="reddit-us",
        cluster_id="reddit-digest",
        format="digest",
        text=text,
        sources=[{"title": a.title, "url": a.url} for a in articles],
    )
    post.meta["subreddit"] = subreddit
    post.meta["reddit_title"] = title
    return post


def budget_left(limit: int) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        data = json.loads(BUDGET.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    return max(0, limit - int(data.get("count") or 0))


def spend_budget() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        data = json.loads(BUDGET.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    data["count"] = int(data.get("count") or 0) + 1
    BUDGET.parent.mkdir(parents=True, exist_ok=True)
    BUDGET.write_text(json.dumps(data), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--limit", type=int, default=7)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    settings = Settings.load()
    reddit_cfg = (settings.publishers.get("reddit") or {}) if hasattr(settings, "publishers") else {}
    daily_limit = int(reddit_cfg.get("daily_limit") or 3)
    if budget_left(daily_limit) <= 0:
        print("Reddit: дневной лимит постов исчерпан")
        return 0

    articles = collect(args.hours, args.limit)
    if not articles:
        print("Reddit: за окно нет новостей")
        return 0
    subreddit = os.environ.get("REDDIT_SUBREDDIT", "").strip() or "USNewsWire"
    post = build_post(articles, subreddit)
    reddit_channel = ChannelConfig(
        id="reddit-us",
        title="Reddit US brief",
        topics=["news"],
        schedule=["09:00"],
        telegram_chat_id="",
    )
    publisher = RedditPublisher(settings)
    ok, detail = publisher.check(reddit_channel)
    print("Reddit:", detail)
    print("\n=== ЗАГОЛОВОК ===\n{}".format(post.meta.get("reddit_title") or post.text.splitlines()[0]))
    print("\n=== ТЕКСТ ===\n{}".format(post.text))
    if not ok:
        print("\n(dry-run: креды не заданы, публикации не будет)")
        return 0
    if not args.live:
        print("\n(dry-run: добавьте --live для публикации)")
        return 0
    result = publisher.publish(post, reddit_channel, settings)
    print("\npublish ok={} url={} error={}".format(result.ok, result.url, result.error))
    if result.ok:
        spend_budget()
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
