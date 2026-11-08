#!/usr/bin/env python3
"""Tumblr: подробный дайджест новостей раз в 5 часов (только Tumblr).

Telegram-конвейер не затрагивается: этот скрипт собирает свежие новости
EN-каналов (crypto / AI / sports) за окно ``--hours``, формирует подробную
сводку с аналитикой и публикует её в Tumblr через ``TumblrPublisher``
(OAuth 1.0a). По расписанию запускается из ``.github/workflows/tumblr-digest.yml``
каждые 5 часов; Telegram продолжает постить по своему расписанию.

Запуск:
    python scripts/tumblr_digest.py --hours 5 --limit 12          # dry-run (показ)
    python scripts/tumblr_digest.py --hours 5 --limit 12 --live   # публикация

Нужны TUMBLR_CONSUMER_KEY/SECRET, TUMBLR_OAUTH_TOKEN/SECRET, TUMBLR_BLOG
(GitHub Secrets). Дневной лимит — settings.publishers.tumblr.daily_limit (5).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_channels  # noqa: E402
from content_factory.models import Article, ChannelConfig, GeneratedPost  # noqa: E402
from content_factory.pipeline import filter_articles  # noqa: E402
from content_factory.publishers.tumblr import TumblrPublisher  # noqa: E402
from content_factory.sources import get_adapter  # noqa: E402
from content_factory.utils import normalize_space, strip_html, truncate  # noqa: E402

US_CHANNELS = ("crypto-news", "ai-news", "sport-news")
TOPIC_LABELS = {
    "crypto-news": "🪙 Crypto",
    "ai-news": "🤖 AI",
    "sport-news": "🏆 Sports",
}
HASHTAGS = ["news", "crypto", "ai", "sports", "digest", "contentfactory"]
BUDGET = ROOT / "data" / "tumblr_usage.json"
MAX_TEXT = 11000          # Tumblr-публикатор принимает до 12 000 символов
SUMMARY_CHARS = 320       # сколько текста новости показывать в сводке
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has",
    "have", "had", "will", "would", "could", "should", "its", "his", "her", "their",
    "they", "them", "you", "your", "our", "about", "after", "before", "over", "under",
    "into", "than", "then", "more", "most", "less", "least", "says", "said", "also",
    "new", "news", "report", "reports", "according", "amid", "via", "just", "now",
    "today", "week", "year", "first", "last", "next", "one", "two", "three", "not",
    "but", "out", "off", "on", "in", "at", "to", "of", "a", "an", "is", "be", "by",
    "as", "it", "or", "if", "we", "he", "she", "us", "up", "down", "how", "why",
    "what", "when", "where", "who", "which", "while", "per", "may", "can", "could",
    "would", "still", "even", "back", "top", "get", "gets", "set", "sets", "hit",
    "hits", "make", "makes", "made", "say", "says", "said", "take", "takes", "took",
    "much", "many", "some", "any", "all", "every", "each", "other", "another",
}


def _summary(article: Article, max_chars: int = SUMMARY_CHARS) -> str:
    text = normalize_space(strip_html(article.summary or article.text or ""))
    return truncate(text, max_chars, suffix="…") if text else ""


def collect(hours: float, limit: int) -> list[tuple[str, Article]]:
    """Свежие новости EN-каналов за окно: [(channel_id, Article)]."""
    settings = Settings.load()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(0.5, float(hours)))
    channels = {c.id: c for c in load_channels(settings, path="config/channels.en.yaml")}
    per_channel: dict[str, list[Article]] = {}
    seen: set[str] = set()
    for channel_id in US_CHANNELS:
        channel = channels.get(channel_id)
        if channel is None:
            continue
        collected: list[Article] = []
        for source in channel.sources:
            if not source.enabled:
                continue
            try:
                collected.extend(get_adapter(source.type).fetch(source, settings) or [])
            except Exception:  # noqa: BLE001 - источник не должен ронять дайджест
                continue
        picked: list[Article] = []
        for article in filter_articles(channel, collected, settings, now=now):
            published = article.published_at
            if published is None:
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < cutoff:
                continue
            key = (article.title or "").strip().lower()[:80]
            if not key or key in seen:
                continue
            seen.add(key)
            picked.append(article)
        picked.sort(key=lambda article: article.published_at, reverse=True)
        per_channel[channel_id] = picked[: max(1, limit)]
    # Круговая нарезка по темам: в сводку попадают новости всех трёх каналов.
    result: list[tuple[str, Article]] = []
    queues = {channel_id: list(items) for channel_id, items in per_channel.items()}
    while queues and len(result) < limit:
        progressed = False
        for channel_id in list(queues):
            if len(result) >= limit:
                break
            if not queues[channel_id]:
                queues.pop(channel_id, None)
                continue
            result.append((channel_id, queues[channel_id].pop(0)))
            progressed = True
        if not progressed:
            break
    return result


def top_keywords(items: list[tuple[str, Article]], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for _channel_id, article in items:
        text = normalize_space(strip_html(article.title or "") + " " + (article.text or ""))
        for word in text.lower().split():
            cleaned = "".join(ch for ch in word if ch.isalpha())
            if len(cleaned) < 5 or cleaned in STOPWORDS:
                continue
            counter[cleaned] += 1
    return [word for word, _count in counter.most_common(limit)]


def build_text(items: list[tuple[str, Article]], hours: float) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "📊 Content Factory — подробный дайджест новостей за {} ч".format(int(hours)),
        now.strftime("%d.%m.%Y %H:%M UTC"),
        "Темы: 🪙 Crypto · 🤖 AI · 🏆 US Sports",
        "",
    ]
    for index, (channel_id, article) in enumerate(items, start=1):
        title = normalize_space(strip_html(article.title or "Без заголовка"))
        label = TOPIC_LABELS.get(channel_id, channel_id)
        lines.append(f"{index}. {title}")
        summary = _summary(article)
        if summary:
            lines.append(f"   {summary}")
        source = normalize_space(strip_html(article.source_name or ""))
        if source:
            lines.append(f"   Источник: {source}")
        if article.url:
            lines.append(f"   {article.url}")
        lines.append("")
    # --- аналитика ---
    topics = Counter(channel_id for channel_id, _ in items)
    sources = Counter(normalize_space(strip_html(a.source_name or "")) for _, a in items)
    keywords = top_keywords(items)
    lines.append("")
    lines.append("📈 Аналитика:")
    lines.append("Новостей в сводке: {}".format(len(items)))
    if topics:
        lines.append(
            "По темам: " + ", ".join(
                "{} — {}".format(TOPIC_LABELS.get(cid, cid), count)
                for cid, count in topics.most_common()
            )
        )
    if sources:
        lines.append(
            "Топ-источники: " + ", ".join(
                "{} ({})".format(name or "?", count) for name, count in sources.most_common(5)
            )
        )
    if keywords:
        lines.append("Ключевые слова: " + ", ".join(keywords))
    if items:
        main_title = normalize_space(strip_html(items[0][1].title or ""))
        lines.append("Главное сейчас: " + main_title)
    text = "\n".join(lines).strip()
    return truncate(text, MAX_TEXT, suffix="…")


def build_post(items: list[tuple[str, Article]], hours: float) -> GeneratedPost:
    now = datetime.now(timezone.utc)
    return GeneratedPost(
        id="tumblr-digest-{}".format(now.strftime("%Y%m%d%H%M")),
        channel_id="tumblr-digest",
        cluster_id="tumblr-digest",
        format="digest",
        text=build_text(items, hours),
        hashtags=list(HASHTAGS),
        sources=[{"title": a.title, "url": a.url} for _cid, a in items],
    )


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


def digest_channel() -> ChannelConfig:
    """Технический канал для Tumblr-публикатора (без ссылки на Telegram)."""
    return ChannelConfig(
        id="tumblr-digest",
        title="Content Factory — Crypto, AI & Sports",
        topics=["crypto", "ai", "sports"],
        schedule=["00:00"],
        telegram_chat_id="",
        description="",
        language="en",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Подробный дайджест новостей в Tumblr")
    parser.add_argument("--hours", type=float, default=5.0, help="Окно новостей, часов")
    parser.add_argument("--limit", type=int, default=12, help="Сколько новостей в дайджесте")
    parser.add_argument("--live", action="store_true", help="Реально опубликовать")
    args = parser.parse_args()

    settings = Settings.load()
    tumblr_cfg = settings.publishers.get("tumblr") or {}
    daily_limit = int(tumblr_cfg.get("daily_limit") or 5)
    if budget_left(daily_limit) <= 0:
        print("Tumblr: дневной лимит постов исчерпан")
        return 0

    items = collect(args.hours, max(4, int(args.limit)))
    if not items:
        print("Tumblr: за окно нет новостей")
        return 0
    post = build_post(items, args.hours)
    channel = digest_channel()
    publisher = TumblrPublisher(settings)
    ok, detail = publisher.check(channel)
    print("Tumblr:", detail)
    print("\n=== ТЕКСТ ДАЙДЖЕСТА ({} символов) ===\n{}".format(len(post.text), post.text))
    if not ok:
        print("\n(dry-run: креды не заданы, публикации не будет)")
        return 0
    if not args.live:
        print("\n(dry-run: добавьте --live для публикации)")
        return 0
    result = publisher.publish(post, channel, settings)
    print("\npublish ok={} url={} error={}".format(result.ok, result.url, result.error))
    if result.ok:
        spend_budget()
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
