#!/usr/bin/env python3
"""Генерирует пакет для каталогов из конфигов каналов.

Пишет:
    docs/promo/catalog-package.md  — готовые карточки для копирования
    docs/promo/catalog-cards.json  — те же данные для трекинга/автоматизации

Запуск:
    python scripts/catalog_cards.py
    python scripts/catalog_cards.py --contact @ваш_контакт
    python scripts/catalog_cards.py --out-dir docs/promo --dry-run

@username каналов берутся из data/analytics/growth/usernames.json (кэш
growth_report). Если кэша нет — карточки всё равно сгенерируются, но без
ссылок: сначала прогоните scripts/growth_report.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_network_channels
from content_factory.analytics.growth import load_username_cache, usernames_path
from content_factory.promo import cards_to_json, cards_to_markdown, build_cards


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Пакет карточек каналов для каталогов")
    parser.add_argument("--contact", default="@Novyi0007Bot", help="Контакт для каталогов")
    parser.add_argument("--out-dir", default="docs/promo", help="Куда писать пакет")
    parser.add_argument("--dry-run", action="store_true", help="Только показать текст")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    channels = [channel for channel in load_network_channels(settings) if channel.enabled]
    if not channels:
        print("Нет каналов — нечего генерировать", file=sys.stderr)
        return 1

    cache = load_username_cache(usernames_path(settings))
    usernames = {}
    for channel in channels:
        chat_id = str(channel.telegram_chat_id or "").strip()
        if chat_id in cache:
            usernames[channel.id] = cache[chat_id]
        elif chat_id.startswith("@"):
            usernames[channel.id] = chat_id.lstrip("@")

    cards = build_cards(channels, usernames, contact=args.contact)
    now = datetime.now(timezone.utc)
    markdown = cards_to_markdown(cards, generated_at=now.strftime("%d.%m.%Y %H:%M UTC"), contact=args.contact)
    payload = cards_to_json(cards, generated_at=now.isoformat())

    if args.dry_run:
        print(markdown)
        return 0

    out_dir = Path(args.out_dir)
    out_dir = out_dir if out_dir.is_absolute() else settings.root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "catalog-package.md"
    json_path = out_dir / "catalog-cards.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Карточки: {}".format(md_path))
    print("JSON: {}".format(json_path))
    missing = [card["id"] for card in cards if not card["username"]]
    if missing:
        print("⚠ нет @username для: {} — прогоните scripts/growth_report.py".format(", ".join(missing)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
