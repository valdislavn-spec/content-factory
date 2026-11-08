#!/usr/bin/env python3
"""Собрать стек новостей за последние N часов по всем каналам (EN+ES).

Только чтение: источники → фильтр темы/свежести → отбор по времени публикации.
Пишет Markdown в data/reports/stack-YYYY-MM-DD-HHMM.md и печатает в stdout.

    python scripts/collect_stack.py --hours 4
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_channels  # noqa: E402
from content_factory.pipeline import filter_articles  # noqa: E402
from content_factory.sources import get_adapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument("--per-channel", type=int, default=10)
    args = parser.parse_args()

    settings = Settings.load()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.hours)
    channels = []
    for path in ("config/channels.en.yaml", "config/channels.es.yaml"):
        try:
            channels.extend(load_channels(settings, path=path))
        except Exception as exc:  # noqa: BLE001
            print(f"каналы {path}: ошибка {exc}", file=sys.stderr)

    lines = [f"# Стек новостей за {args.hours:g} ч · {now.strftime('%d.%m.%Y %H:%M UTC')}", ""]
    total = 0
    for channel in channels:
        collected = []
        errors = []
        for source in channel.sources:
            if not source.enabled:
                continue
            try:
                items = get_adapter(source.type).fetch(source, settings) or []
                collected.extend(items)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source.id}: {type(exc).__name__}")
        filtered = filter_articles(channel, collected, settings, now=now)
        recent = []
        seen = set()
        for article in filtered:
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
            recent.append(article)
        recent.sort(key=lambda article: article.published_at, reverse=True)
        total += len(recent)
        lines.append(f"## {channel.title} ({channel.id}) — {len(recent)}")
        for article in recent[: args.per_channel]:
            stamp = article.published_at.astimezone(timezone.utc).strftime("%H:%M")
            lines.append(f"- [{stamp}] {article.title} — {article.source_name}")
            lines.append(f"  {article.url}")
        if errors:
            lines.append(f"  _ошибки источников: {', '.join(errors[:6])}_")
        lines.append("")

    report = "\n".join(lines)
    out_dir = ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"stack-{now.strftime('%Y-%m-%d-%H%M')}.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nИтого новостей за {args.hours:g} ч: {total}; отчёт: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
