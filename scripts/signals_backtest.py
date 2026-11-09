#!/usr/bin/env python3
"""Бэктест сигнальной стратегии на публичных свечах BingX.

Проверяет ту же логику, что и ``scripts/crypto_signals.py`` (EMA20/50 на 15m,
EMA200 на 1h, RSI, объём, ATR-стопы), но на истории: считает winrate,
средний R, profit factor. Нужен, чтобы включать только плюсовые настройки.

Запуск:
    python scripts/signals_backtest.py --limit 1000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.signals.indicators import atr, ema, rsi, volume_ratio  # noqa: E402
from content_factory.signals.market import fetch_candles  # noqa: E402

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def _line(candles: List[dict], period: int) -> List[Optional[float]]:
    return ema([candle["close"] for candle in candles], period)


def _trend_at(trend_ts: List[int], trend_ema: List[Optional[float]], ts: int) -> Optional[float]:
    value = None
    for index, trend_time in enumerate(trend_ts):
        if trend_time > ts:
            break
        value = trend_ema[index]
    return value


def backtest_pair(pair: str, limit: int) -> Dict[str, float]:
    entry_candles = fetch_candles("bingx", pair, "15m", limit)
    trend_candles = fetch_candles("bingx", pair, "1h", min(limit, 300))
    if not entry_candles or not trend_candles:
        return {"pair": pair, "error": "no data"}
    closes = [candle["close"] for candle in entry_candles]
    trend_ts = [candle["ts"] for candle in trend_candles]
    trend_ema = _line(trend_candles, 200)
    ema20 = _line(entry_candles, 20)
    ema50 = _line(entry_candles, 50)
    rsi14 = rsi(closes, 14)
    atr14 = atr(entry_candles, 14)
    trades = []
    last_bar = -999
    for index in range(210, len(entry_candles) - 1):
        if index - last_bar < 6:  # кулдаун 90 минут на 15m
            continue
        if None in (ema20[index], ema50[index], rsi14[index], atr14[index]):
            continue
        trend_value = _trend_at(trend_ts, trend_ema, entry_candles[index]["ts"])
        if trend_value is None:
            continue
        vol_ratio = volume_ratio(entry_candles[: index + 1], 20)
        if not vol_ratio:
            continue
        close = closes[index]
        side = ""
        if (
            ema20[index] > ema50[index]
            and close > trend_value
            and 45 <= rsi14[index] <= 72
            and vol_ratio >= 1.1
        ):
            side = "LONG"
        elif (
            ema20[index] < ema50[index]
            and close < trend_value
            and 28 <= rsi14[index] <= 55
            and vol_ratio >= 1.1
        ):
            side = "SHORT"
        if not side:
            continue
        entry = entry_candles[index + 1]["open"]
        risk = 1.2 * atr14[index]
        if risk <= 0:
            continue
        stop = entry - risk if side == "LONG" else entry + risk
        take = entry + 2.0 * atr14[index] if side == "LONG" else entry - 2.0 * atr14[index]
        result = None
        for offset in range(index + 1, min(index + 96, len(entry_candles))):
            candle = entry_candles[offset]
            if side == "LONG":
                if candle["low"] <= stop:
                    result = -1.0
                    break
                if candle["high"] >= take:
                    result = 2.0 / 1.2
                    break
            else:
                if candle["high"] >= stop:
                    result = -1.0
                    break
                if candle["low"] <= take:
                    result = 2.0 / 1.2
                    break
        if result is None:
            exit_price = entry_candles[min(index + 95, len(entry_candles) - 1)]["close"]
            move = (exit_price - entry) if side == "LONG" else (entry - exit_price)
            result = move / risk
        trades.append({"side": side, "r": result})
        last_bar = index
    wins = [trade for trade in trades if trade["r"] > 0]
    gross_win = sum(trade["r"] for trade in wins)
    gross_loss = -sum(trade["r"] for trade in trades if trade["r"] < 0)
    return {
        "pair": pair,
        "trades": len(trades),
        "winrate": (len(wins) / len(trades) * 100.0) if trades else 0.0,
        "avg_r": (sum(trade["r"] for trade in trades) / len(trades)) if trades else 0.0,
        "total_r": sum(trade["r"] for trade in trades),
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf") if gross_win else 0.0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Бэктест крипто-сигналов (BingX)")
    parser.add_argument("--limit", type=int, default=1000, help="сколько 15m-свечей брать")
    parser.add_argument("--pair", default="", help="одна пара, например BTC/USDT")
    args = parser.parse_args(argv)
    pairs = [args.pair] if args.pair else PAIRS
    results = []
    for pair in pairs:
        result = backtest_pair(pair, max(300, args.limit))
        results.append(result)
        print(
            "%-9s trades=%-3d winrate=%5.1f%% avgR=%+.2f totalR=%+.1f PF=%.2f"
            % (
                result.get("pair"),
                int(result.get("trades") or 0),
                float(result.get("winrate") or 0.0),
                float(result.get("avg_r") or 0.0),
                float(result.get("total_r") or 0.0),
                float(result.get("profit_factor") or 0.0),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
