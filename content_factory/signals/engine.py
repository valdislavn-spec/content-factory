"""Сигнальный движок: мультибиржевой анализ пар.

Вход: ``data[pair][exchange] = {"15m": [...], "1h": [...]}``.
Выход: список сигналов с направлением, entry/SL/TP и списком подтвердивших бирж.

Идея: сигнал засчитывается, только если его подтверждают минимум
``min_confirmations`` бирж (тренд + EMA на входном ТФ). Это отсекает шум
одиночной биржи и заодно даёт «кросс-биржевое» обоснование в посте.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .indicators import atr, ema, rsi, volume_ratio


def _stats(candles_entry: List[dict], candles_trend: List[dict], strategy: Dict) -> Optional[Dict[str, float]]:
    fast = int(strategy.get("ema_fast") or 20)
    slow = int(strategy.get("ema_slow") or 50)
    trend_period = int(strategy.get("ema_trend") or 200)
    rsi_period = int(strategy.get("rsi_period") or 14)
    atr_period = int(strategy.get("atr_period") or 14)
    if len(candles_entry) < max(slow, rsi_period, atr_period) + 2:
        return None
    if len(candles_trend) < trend_period + 2:
        return None
    closes = [candle["close"] for candle in candles_entry]
    trend_closes = [candle["close"] for candle in candles_trend]
    ema_fast = ema(closes, fast)[-1]
    ema_slow = ema(closes, slow)[-1]
    trend_ema = ema(trend_closes, trend_period)[-1]
    rsi_value = rsi(closes, rsi_period)[-1]
    atr_value = atr(candles_entry, atr_period)[-1]
    vol_ratio = volume_ratio(candles_entry, int(strategy.get("volume_period") or 20))
    if None in (ema_fast, ema_slow, trend_ema, rsi_value, atr_value) or not vol_ratio:
        return None
    return {
        "close": closes[-1],
        "ema_fast": float(ema_fast),
        "ema_slow": float(ema_slow),
        "trend_ema": float(trend_ema),
        "rsi": float(rsi_value),
        "atr": float(atr_value),
        "volume_ratio": float(vol_ratio),
        "bar_ts": int(candles_entry[-1]["ts"]),
    }


def build_signals(data: Dict[str, Dict[str, Dict[str, List[dict]]]], config: Dict) -> List[dict]:
    strategy = config.get("strategy") or {}
    schema = config.get("timeframes") or {}
    entry_tf = str(schema.get("entry") or "15m")
    trend_tf = str(schema.get("trend") or "1h")
    min_confirmations = int(config.get("min_confirmations") or 2)
    long_range = strategy.get("rsi_long") or [45, 72]
    short_range = strategy.get("rsi_short") or [28, 55]
    volume_mult = float(strategy.get("volume_mult") or 1.1)
    sl_atr = float(strategy.get("sl_atr") or 1.2)
    tp_atr = float(strategy.get("tp_atr") or 2.0)
    signals: List[dict] = []

    for pair, per_exchange in sorted((data or {}).items()):
        stats: Dict[str, Dict[str, float]] = {}
        for exchange, tfs in (per_exchange or {}).items():
            if not isinstance(tfs, dict):
                continue
            result = _stats(tfs.get(entry_tf) or [], tfs.get(trend_tf) or [], strategy)
            if result:
                stats[exchange] = result
        if len(stats) < min_confirmations:
            continue

        bulls = [
            name
            for name, stat in stats.items()
            if stat["ema_fast"] > stat["ema_slow"] and stat["close"] > stat["trend_ema"]
        ]
        bears = [
            name
            for name, stat in stats.items()
            if stat["ema_fast"] < stat["ema_slow"] and stat["close"] < stat["trend_ema"]
        ]
        primary_name = "bingx" if "bingx" in stats else sorted(stats)[0]
        primary = stats[primary_name]

        side = ""
        confirmations: List[str] = []
        if (
            primary["ema_fast"] > primary["ema_slow"]
            and primary["close"] > primary["trend_ema"]
            and long_range[0] <= primary["rsi"] <= long_range[1]
            and primary["volume_ratio"] >= volume_mult
            and len(bulls) >= min_confirmations
        ):
            side = "LONG"
            confirmations = sorted(bulls)
        elif (
            primary["ema_fast"] < primary["ema_slow"]
            and primary["close"] < primary["trend_ema"]
            and short_range[0] <= primary["rsi"] <= short_range[1]
            and primary["volume_ratio"] >= volume_mult
            and len(bears) >= min_confirmations
        ):
            side = "SHORT"
            confirmations = sorted(bears)
        if not side:
            continue

        entry = primary["close"]
        stop = entry - sl_atr * primary["atr"] if side == "LONG" else entry + sl_atr * primary["atr"]
        take = entry + tp_atr * primary["atr"] if side == "LONG" else entry - tp_atr * primary["atr"]
        risk = abs(entry - stop)
        reward = abs(take - entry)
        signals.append(
            {
                "pair": pair,
                "side": side,
                "timeframe": entry_tf,
                "entry": entry,
                "stop": stop,
                "take": take,
                "rr": (reward / risk) if risk else 0.0,
                "rsi": primary["rsi"],
                "volume_ratio": primary["volume_ratio"],
                "confirmations": confirmations,
                "exchanges_seen": sorted(stats),
                "bar_ts": primary["bar_ts"],
                "primary": primary_name,
            }
        )
    signals.sort(key=lambda item: len(item["confirmations"]), reverse=True)
    return signals
