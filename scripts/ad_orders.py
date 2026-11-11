#!/usr/bin/env python3
"""Ручное управление заявками на рекламу (без бота).

    ./.venv/bin/python scripts/ad_orders.py list
    ./.venv/bin/python scripts/ad_orders.py list --status moderation
    ./.venv/bin/python scripts/ad_orders.py approve <order_id>
    ./.venv/bin/python scripts/ad_orders.py reject <order_id>
    ./.venv/bin/python scripts/ad_orders.py stats

Одобренная заявка пишется в data/ads/queue/<order_id>.json — её забирает
публикация контент-завода (или публикуется вручную).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.monetization import AdOrderStore, MonetizationError, refund_star_payment  # noqa: E402
from content_factory.utils import env  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Заявки на рекламу")
    parser.add_argument("action", choices=["list", "approve", "reject", "stats", "refund"])
    parser.add_argument("order_id", nargs="?", default="")
    parser.add_argument("--status", default="", help="Фильтр статуса для list")
    parser.add_argument("--limit", type=int, default=30)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    settings.ensure_dirs()
    queue_dir = Path(settings.data_dir) / "ads" / "queue"
    with AdOrderStore(settings.db_path) as store:
        if args.action == "stats":
            print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
            return 0
        if args.action == "list":
            orders = store.list(status=args.status or None, limit=args.limit)
            for order in orders:
                print(
                    f"{order.id} | {order.status:14} | {order.channel_id} {order.tariff} "
                    f"| {order.amount}⭐ | {order.ad_text[:60]}"
                )
            if not orders:
                print("Заявок нет")
            return 0
        if not args.order_id:
            print("Укажите order_id")
            return 2
        order = store.get(args.order_id)
        if order is None:
            print(f"Заявка {args.order_id} не найдена")
            return 2
        if args.action == "approve":
            queue_dir.mkdir(parents=True, exist_ok=True)
            path = queue_dir / f"{order.id}.json"
            path.write_text(json.dumps(order.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            order = store.update(order.id, status="approved", queue_file=str(path))
            print(f"Одобрено: {order.id} → {path}")
            return 0
        if args.action == "reject":
            store.update(order.id, status="rejected")
            print(f"Отклонено: {order.id}")
            return 0
        if args.action == "refund":
            token = env("TELEGRAM_BOT_TOKEN", "") or ""
            if not token:
                print("Нужен TELEGRAM_BOT_TOKEN для возврата Stars")
                return 2
            try:
                refund_star_payment(token, order.buyer_id, order.payment_charge_id)
            except MonetizationError as exc:
                print(f"Возврат не выполнен: {exc}")
                return 1
            store.update(order.id, status="refunded")
            print(f"Возврат Stars выполнен: {order.id} ({order.amount}⭐)")
            return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
