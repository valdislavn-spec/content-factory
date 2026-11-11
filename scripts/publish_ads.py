#!/usr/bin/env python3
"""Публикация одобренных рекламных заявок в каналы (завершает монетизацию).

    ./.venv/bin/python scripts/publish_ads.py --dry-run            # показать, что выйдет
    ./.venv/bin/python scripts/publish_ads.py --order <id> --publish
    ./.venv/bin/python scripts/publish_ads.py --all --publish

Берёт заявки со статусом ``approved`` из data/ads/queue/, публикует через
официальный Bot API (тот же бот, что админ канала), переводит заявку в
``published`` и переносит файл в data/ads/published/. По умолчанию — dry-run.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_network_channels  # noqa: E402
from content_factory.monetization import AdOrderStore, MonetizationError, ad_order_to_post  # noqa: E402
from content_factory.publishers import get_publisher  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Публикация одобренной рекламы")
    parser.add_argument("--order", default="", help="id заявки")
    parser.add_argument("--all", action="store_true", help="Опубликовать все approved")
    parser.add_argument("--limit", type=int, default=5, help="Максимум заявок за запуск")
    parser.add_argument("--publish", action="store_true", help="Реальная публикация (по умолчанию dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Явно только показать посты")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    settings.ensure_dirs()
    queue_dir = Path(settings.data_dir) / "ads" / "queue"
    published_dir = Path(settings.data_dir) / "ads" / "published"
    published_dir.mkdir(parents=True, exist_ok=True)
    channels = {channel.id: channel for channel in load_network_channels(settings)}
    with AdOrderStore(settings.db_path) as store:
        if args.order:
            orders = [store.get(args.order)]
            orders = [order for order in orders if order is not None]
        else:
            orders = store.list(status="approved", limit=args.limit)
        if not orders:
            print("Нет одобренных заявок (scripts/ad_orders.py list --status approved)")
            return 0
        failures = 0
        for order in orders:
            channel = channels.get(order.channel_id)
            if channel is None:
                print(f"{order.id}: канал {order.channel_id} не найден среди EN/ES-каналов")
                failures += 1
                continue
            try:
                post = ad_order_to_post(order)
            except MonetizationError as exc:
                print(f"{order.id}: {exc}")
                failures += 1
                continue
            if args.dry_run or not args.publish:
                print(f"[dry-run] {order.id} → «{order.channel_id}» ({order.tariff}, {order.amount}⭐):")
                print(post.text[:500])
                print("---")
                continue
            os.environ["CONTENT_FACTORY_DRY_RUN"] = "false"
            publisher = get_publisher("telegram", settings)
            result = publisher.publish(post, channel, settings)
            if not result.ok:
                print(f"{order.id}: ошибка публикации: {result.error}")
                failures += 1
                continue
            target = published_dir / f"{order.id}.json"
            source_file = Path(order.queue_file) if order.queue_file else (queue_dir / f"{order.id}.json")
            if source_file.is_file() and source_file != target:
                shutil.move(str(source_file), str(target))
            store.update(order.id, status="published", queue_file=str(target))
            print(f"{order.id}: опубликовано в «{channel.id}» — {result.url or result.external_id}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
