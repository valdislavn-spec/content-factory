#!/usr/bin/env python3
"""Бот продажи рекламных постов за Telegram Stars (XTR), long-polling.

    ./.venv/bin/python scripts/ad_bot.py --dry-run   # показать тарифы и статус
    ./.venv/bin/python scripts/ad_bot.py --once      # один цикл getUpdates
    ./.venv/bin/python scripts/ad_bot.py             # слушать постоянно

Требуется в .env:
    TELEGRAM_BOT_TOKEN        — бот, которого добавляем в каналы
    TELEGRAM_ADMIN_CHAT_ID    — ваш chat_id для уведомлений и кнопок модерации

Внимание: одновременно с scripts/telegram-growth-bot.py один и тот же бот
запускать нельзя (конфликт getUpdates) — либо объедините процессы, либо
запускайте по очереди.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.monetization import (  # noqa: E402
    AdOrderStore,
    AdSalesBot,
    MonetizationError,
    load_offers,
)
from content_factory.utils import env  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Бот продажи рекламы за Telegram Stars")
    parser.add_argument("--config", default="config/monetization.yaml", help="YAML с каналами и тарифами")
    parser.add_argument("--once", action="store_true", help="Один цикл getUpdates и выход")
    parser.add_argument("--timeout", type=int, default=25, help="Long-polling timeout, секунд")
    parser.add_argument("--dry-run", action="store_true", help="Показать тарифы/статус и выйти")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.load()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(settings.root) / config_path
    try:
        raw, offers = load_offers(config_path)
    except MonetizationError as exc:
        print(f"Монетизация: {exc}")
        return 2
    token = env("TELEGRAM_BOT_TOKEN", "") or ""
    admin_chat_id = env(str(raw.get("admin_chat_id_env") or "TELEGRAM_ADMIN_CHAT_ID"), "") or ""
    queue_dir = Path(settings.data_dir) / "ads" / "queue"
    print("Каналы и тарифы (Stars):")
    for offer in offers.values():
        tariffs = ", ".join(f"{tariff.code}={tariff.price}⭐" for tariff in offer.tariffs)
        print(f"  {offer.id}: {offer.title} — {tariffs}")
    if args.dry_run:
        print(f"admin_chat_id: {admin_chat_id or 'НЕ ЗАДАН (уведомления не будут приходить)'}")
        print(f"очередь одобренных: {queue_dir}")
        print(f"бот: {'токен задан' if token else 'TELEGRAM_BOT_TOKEN НЕ ЗАДАН'}")
        return 0
    if not token:
        print("Нужен TELEGRAM_BOT_TOKEN в .env")
        return 2
    try:
        with AdOrderStore(settings.db_path) as store:
            bot = AdSalesBot(
                token=token,
                store=store,
                offers=offers,
                admin_chat_id=admin_chat_id,
                queue_dir=queue_dir,
            )
            if args.once:
                processed = bot.poll_once(timeout=0)
                print(f"Обработано обновлений: {processed}")
                return 0
            print("Слушаю заказы (Ctrl+C для остановки)...")
            while True:
                bot.poll_once(timeout=args.timeout)
    except KeyboardInterrupt:
        print("\nОстановлено.")
        return 0
    except MonetizationError as exc:
        print(f"Ошибка: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
