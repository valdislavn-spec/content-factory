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

from content_factory.integrations.bingx import (  # noqa: E402
    DEFAULT_SYMBOLS as BINGX_SYMBOLS,
    BingXClient,
    BingXError,
)
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
    parser.add_argument("--source", choices=("auto", "bingx", "twelvedata"), default="auto",
                        help="bingx = бесплатно без ключа (крипта); twelvedata = ключ (крипта/форекс/акции); auto = bingx для крипты, иначе twelvedata")
    return parser.parse_args(argv)


def _looks_crypto(symbol: str) -> bool:
    quote = symbol.split("/")[-1].upper() if "/" in symbol else ""
    return quote in {"USDT", "USDC", "USD", "BTC", "ETH"}


def _to_bingx(symbol: str) -> str:
    """BTC/USD → BTC-USDT (у BingX пары USDT-маржинальные)."""
    if "/" in symbol:
        base, quote = symbol.split("/", 1)
        if quote.upper() in {"USD", "USDC"}:
            quote = "USDT"
        return f"{base}/{quote}"
    return symbol


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    symbols = [part.strip() for part in args.symbols.split(",") if part.strip()]
    source = args.source
    if source == "auto":
        source = "bingx" if all(_looks_crypto(symbol) for symbol in symbols) else "twelvedata"
        if source == "twelvedata" and not (args.api_key or os.environ.get("TWELVEDATA_API_KEY")):
            source = "bingx" if all(_looks_crypto(symbol) for symbol in symbols) else "twelvedata"
    try:
        if source == "bingx":
            bingx_symbols = [_to_bingx(symbol) for symbol in symbols]
            client = BingXClient()
            if args.series:
                data = [{"symbol": symbol, "candles": client.klines(api_symbol, args.series, args.output)}
                        for symbol, api_symbol in zip(symbols, bingx_symbols)]
            else:
                quotes = client.quotes(bingx_symbols)
                for quote, display in zip(quotes, symbols):
                    quote["symbol"] = display
                data = quotes
        else:
            client = TwelveDataClient(api_key=args.api_key or None)
            if args.series:
                data = [{"symbol": symbol, "candles": client.time_series(symbol, args.series, args.output)}
                        for symbol in symbols]
            else:
                data = client.quotes(symbols)
    except (TwelveDataError, BingXError) as exc:
        print("market data error: {}".format(exc), file=sys.stderr)
        return 1
    if args.series:
        if args.format == "json":
            print(json.dumps(data, ensure_ascii=False, indent=1))
            return 0
        for item in data:
            candles = item.get("candles") or []
            last = candles[-1] if candles else {}
            print("{}: {} свечей, close={}".format(item.get("symbol"), len(candles), last.get("close")))
        return 0
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
