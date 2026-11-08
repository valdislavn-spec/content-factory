#!/usr/bin/env python3
"""Рыночные данные Twelve Data: котировки и снапшот для постов.

Примеры:
    python scripts/market_data.py --snapshot
    python scripts/market_data.py --symbols BTC/USD,ETH/USD,SOL/USD
    python scripts/market_data.py --symbols BTC/USD --format json
    python scripts/market_data.py --symbols BTC/USD --series 1h --output 24

Ключ: TWELVEDATA_API_KEY в .env (бесплатный план — 800 кредитов/день).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.integrations.twelvedata import (  # noqa: E402
    DEFAULT_CRYPTO_SYMBOLS,
    TwelveDataClient,
    TwelveDataError,
    format_snapshot,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Котировки Twelve Data для контент-завода")
    parser.add_argument("--symbols", default=",".join(DEFAULT_CRYPTO_SYMBOLS),
                        help="символы через запятую (BTC/USD, ETH/USD, AAPL, EUR/USD)")
    parser.add_argument("--format", choices=("text", "json", "snapshot"), default="text")
    parser.add_argument("--snapshot", action="store_true", help="краткая строка для поста")
    parser.add_argument("--series", default="", help="интервал свечей (1min, 1h, 1day)")
    parser.add_argument("--output", type=int, default=24, help="сколько свечей")
    parser.add_argument("--api-key", default="", help="переопределить TWELVEDATA_API_KEY")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    symbols = [part.strip() for part in args.symbols.split(",") if part.strip()]
    client = TwelveDataClient(api_key=args.api_key or None)
    try:
        if args.series:
            data = [{"symbol": symbol, "candles": client.time_series(symbol, args.series, args.output)}
                    for symbol in symbols]
        else:
            data = client.quotes(symbols)
    except TwelveDataError as exc:
        print("Twelve Data error: {}".format(exc), file=sys.stderr)
        return 1
    if args.snapshot or args.format == "snapshot":
        print(format_snapshot(data))
        return 0
    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    for quote in data:
        if quote.get("error"):
            print("{}: ошибка — {}".format(quote.get("symbol"), quote["error"]))
            continue
        print(
            "{}: {} ({}{})".format(
                quote.get("symbol"),
                quote.get("price"),
                "изм. " if quote.get("percent_change") is not None else "",
                quote.get("percent_change"),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
