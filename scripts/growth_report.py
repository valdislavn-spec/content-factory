#!/usr/bin/env python3
"""Ежедневный отчёт роста Telegram-каналов (без Telethon).

Что делает:
1. Резолвит @username каналов через Bot API (в конфигах каналы по числовому ID).
2. Забирает точное число подписчиков через Bot API getChatMemberCount.
3. Забирает публичное превью t.me/s/<username>: просмотры, реакции, даты.
4. Сравнивает с предыдущим снимком (data/analytics/growth/history.jsonl).
5. Печатает отчёт, сохраняет Markdown в data/reports и с --send отправляет
   короткую сводку в Telegram (TELEGRAM_ALERT_CHAT_ID).

Запуск:
    python scripts/growth_report.py            # отчёт в консоль/файл
    python scripts/growth_report.py --send     # ещё и в Telegram
    python scripts/growth_report.py --limit 30

Почему в GitHub Actions: в РФ t.me и api.telegram.org часто недоступны
напрямую, а раннеры Actions ходят туда без прокси. Локально Bot API работает
через TELEGRAM_API_BASE (telegram-proxy), превью — при доступном t.me.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.analytics.growth import (
    append_snapshot,
    build_snapshot,
    format_markdown,
    format_telegram,
    history_path,
    load_previous_snapshot,
    load_username_cache,
    save_username_cache,
    usernames_path,
)
from content_factory.analytics.preview import (
    BROWSER_USER_AGENT,
    PreviewError,
    fetch_preview,
    normalize_username,
)
from content_factory.config import ConfigError, Settings, load_network_channels
from content_factory.models import ChannelConfig
from content_factory.utils import env

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ежедневный отчёт роста Telegram-каналов")
    parser.add_argument("--send", action="store_true", help="Отправить сводку в Telegram")
    parser.add_argument("--limit", type=int, default=20, help="Сколько постов брать из превью")
    parser.add_argument("--timeout", type=float, default=20.0, help="Таймаут сетевых запросов, сек")
    parser.add_argument("--quiet", action="store_true", help="Не печатать Markdown в stdout")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        settings = Settings.load()
    except ConfigError as exc:
        print("Ошибка конфигурации: %s" % exc, file=sys.stderr)
        return 2

    channels = [channel for channel in load_network_channels(settings) if channel.enabled]
    if not channels:
        print("Нет включённых каналов — отчёт не построен", file=sys.stderr)
        return 1

    cache = load_username_cache(usernames_path(settings))
    usernames: Dict[str, str] = {}
    subscribers: Dict[str, int] = {}
    previews = {}
    errors: Dict[str, str] = {}
    for channel in channels:
        username = resolve_username(settings, channel, cache, args.timeout)
        if username:
            usernames[channel.id] = username
        count = fetch_subscribers(settings, channel, args.timeout)
        if count is not None:
            subscribers[channel.id] = count
        if not username:
            errors[channel.id] = "не удалось определить @username"
            continue
        try:
            previews[channel.id] = fetch_preview(username, timeout=args.timeout, limit=args.limit)
        except PreviewError as exc:
            errors[channel.id] = str(exc)

    save_username_cache(usernames_path(settings), {**cache, **_chat_ids(channels, usernames)})

    now = datetime.now(timezone.utc)
    previous = load_previous_snapshot(history_path(settings))
    snapshot = build_snapshot(
        channels,
        previews,
        now=now,
        previous=previous,
        errors=errors,
        subscribers=subscribers,
        limit=args.limit,
    )
    snapshot["usernames"] = usernames
    append_snapshot(history_path(settings), snapshot)

    markdown = format_markdown(snapshot)
    reports_dir = settings.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "growth-{}.md".format(now.strftime("%Y-%m-%d"))
    report_path.write_text(markdown, encoding="utf-8")
    if not args.quiet:
        print(markdown)
    print("Отчёт: %s" % report_path, file=sys.stderr)

    telegram_text = format_telegram(snapshot)
    if args.send:
        return _send_telegram(telegram_text)
    print(telegram_text, file=sys.stderr)
    return 0


def _chat_ids(channels: Sequence[ChannelConfig], usernames: Dict[str, str]) -> Dict[str, str]:
    """Кэш для resolve_username: chat_id → username (уже известные пары)."""
    result: Dict[str, str] = {}
    for channel in channels:
        username = usernames.get(channel.id)
        chat_id = str(channel.telegram_chat_id or "").strip()
        if username and chat_id and not chat_id.startswith("@"):
            result[chat_id] = username
    return result


def _send_telegram(text: str) -> int:
    script = Path(__file__).resolve().parent / "notify_telegram.py"
    return subprocess.call([sys.executable, str(script), text])


if __name__ == "__main__":
    sys.exit(main())
