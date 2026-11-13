#!/usr/bin/env python3
"""Long-polling growth-бот: deep links /start + inline mode для наших каналов.

    ./.venv/bin/python scripts/telegram-growth-bot.py            # слушать постоянно
    ./.venv/bin/python scripts/telegram-growth-bot.py --once     # один цикл getUpdates
    ./.venv/bin/python scripts/telegram-growth-bot.py --dry-run  # показать настройки

Только живые каналы (EN/ES): `load_network_channels` = основной файл (EN) +
channels.es.yaml; RU-каналы не используются.

Требуются в .env:
    TELEGRAM_BOT_TOKEN            — тот же бот, что публикует посты
    TELEGRAM_GROWTH_BOT_USERNAME  — username бота без @ (для deep links)
    TELEGRAM_CHANNEL_URL_<CHANNEL> — публичная ссылка канала (или @username в description)
В BotFather у бота нужно включить inline mode: /setinline.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_network_channels  # noqa: E402
from content_factory.integrations.telegram_growth import (  # noqa: E402
    TelegramGrowthBot,
    TelegramGrowthError,
)
from content_factory.storage import Storage  # noqa: E402
from content_factory.utils import env  # noqa: E402
from content_factory.locking import LockError, single_instance, telegram_lock_name  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Growth-бот: deep links и inline mode")
    parser.add_argument("--once", action="store_true", help="Один цикл getUpdates и выход")
    parser.add_argument("--timeout", type=int, default=25, help="Long-polling timeout, секунд")
    parser.add_argument("--dry-run", action="store_true", help="Показать настройки и выйти")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.load()
    channels = load_network_channels(settings)  # EN + ES
    token = env("TELEGRAM_BOT_TOKEN", "") or ""
    username = env("TELEGRAM_GROWTH_BOT_USERNAME", "") or ""
    if not token or not username:
        print("Нужны TELEGRAM_BOT_TOKEN и TELEGRAM_GROWTH_BOT_USERNAME в .env")
        return 2
    print(f"Growth-бот @{username}: каналов {len(channels)} — {', '.join(c.id for c in channels)}")
    if args.dry_run:
        for channel in channels:
            from content_factory.integrations.landing import public_url
            from content_factory.integrations.telegram_growth import start_link

            print(
                f"  {channel.id}: start={start_link(username, channel.id)} "
                f"link={public_url(channel) or '—'}"
            )
        return 0
    try:
        with single_instance(settings.data_dir, telegram_lock_name(token)):
            with Storage(settings.db_path) as storage:
                bot = TelegramGrowthBot(token, username, storage, channels, settings)
                if args.once:
                    processed = bot.poll_once(timeout=0)
                    print(f"Обработано обновлений: {processed}")
                    return 0
                print("Слушаю обновления (Ctrl+C для остановки)...")
                while True:
                    bot.poll_once(timeout=args.timeout)
    except LockError as exc:
        print(f"Этот бот уже слушает другой процесс: {exc}")
        return 2
    except KeyboardInterrupt:
        print("\nОстановлено.")
        return 0
    except TelegramGrowthError as exc:
        print(f"Ошибка: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
