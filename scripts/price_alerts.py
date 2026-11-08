#!/usr/bin/env python3
"""Авто-алерты по цене (BingX) → посты в Telegram-каналы.

Примеры:
    python scripts/price_alerts.py --once --dry-run     # один прогон без публикации
    python scripts/price_alerts.py --sample --dry-run   # тестовый алерт
    python scripts/price_alerts.py --loop               # демон, проверка раз в 60 с
    python scripts/price_alerts.py --once --channel crypto-news

Конфиг: config/price_alerts.yaml. Состояние: data/price_alerts_state.json.
Публикация уважает settings.dry_run (TELEGRAM_DRY_RUN); флаг --dry-run
принудительно включает dryrun-публикатор.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from content_factory.config import Settings  # noqa: E402
from content_factory.models import GeneratedPost  # noqa: E402
from content_factory.price_alerts import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    PriceAlertEngine,
    format_alert,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BingX price alerts → Telegram posts")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--once", action="store_true", help="один прогон (по умолчанию)")
    parser.add_argument("--loop", action="store_true", help="работать демоном")
    parser.add_argument("--interval", type=float, default=None, help="интервал проверки, сек")
    parser.add_argument("--dry-run", action="store_true", help="не публиковать, только логи")
    parser.add_argument("--channel", action="append", default=[], help="id канала (можно несколько)")
    parser.add_argument("--state", default="", help="путь к state-файлу")
    parser.add_argument("--sample", action="store_true", help="опубликовать тестовый алерт BTC")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _load_config(path: str) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = _load_config(args.config)
    if args.channel:
        config["channels"] = list(args.channel)
    if config.get("enabled") is False:
        print("price alerts disabled in config")
        return 0
    settings = Settings.load()
    engine = PriceAlertEngine(
        settings,
        config,
        state_path=Path(args.state) if args.state else None,
        dry_run=args.dry_run,
    )
    if not engine.rules:
        print("no rules in config")
        return 1
    if args.sample:
        alert = {
            "symbol": "BTC/USDT",
            "price": 78000.0,
            "percent_change": 2.4,
            "type": "above",
            "level": 78000.0,
        }
        for channel in engine.channels:
            post = GeneratedPost(
                id="alert-sample-{}".format(channel.id),
                channel_id=channel.id,
                cluster_id="price-alert",
                format="alert",
                text=format_alert(alert, channel.language),
            )
            result = engine._publisher().publish(post, channel, settings)  # noqa: SLF001
            print("{}: {}".format(channel.id, "ok" if result.ok else result.error))
            print(post.text)
        return 0
    if args.loop:
        engine.run_forever(args.interval or float(config.get("interval_seconds") or 60))
        return 0
    results = engine.run_once()
    if not results:
        print("no alerts fired (state updated)")
        return 0
    for result in results:
        print("{}: {}{}".format(
            result.channel_id,
            "ok" if result.ok else "fail",
            "" if result.ok else " — {}".format(result.error),
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
