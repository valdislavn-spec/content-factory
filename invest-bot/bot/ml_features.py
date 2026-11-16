"""Feature extraction shared by ML training and live inference (stdlib only)."""
from __future__ import annotations

import math

from .indicators import ema, rsi
from .models import Candle

FEATURES = [
    "ret1", "ret3", "ret6", "ret12", "ret24",
    "ema9_21", "ema21_50", "close_ema200",
    "rsi14", "atr14_pct", "vol_ratio", "tod_sin", "tod_cos",
]


def _atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    recent = candles[-(period + 1):]
    ranges = []
    for i in range(1, len(recent)):
        prev = recent[i - 1].close
        c = recent[i]
        ranges.append(max(c.high - c.low, abs(c.high - prev), abs(c.low - prev)))
    return sum(ranges) / len(ranges) if ranges else None


def extract(candles: list[Candle], forming: bool = True) -> dict[str, float] | None:
    closed = candles[:-1] if forming and len(candles) > 1 else candles
    if len(closed) < 60:
        return None
    closes = [c.close for c in closed]
    cur = closed[-1]
    e9 = ema(closes, 9)[-1]
    e21 = ema(closes, 21)[-1]
    e50 = ema(closes, 50)[-1]
    e200 = ema(closes, 200)[-1]
    r = rsi(closes, 14)[-1]
    a = _atr(closed, 14)
    if None in (e9, e21, e50, e200, r) or a is None or cur.close <= 0:
        return None
    vol_avg = sum(c.volume for c in closed[-21:-1]) / 20.0
    mins = cur.ts.hour * 60 + cur.ts.minute
    return {
        "ret1": cl_ret(closes, 1),
        "ret3": cl_ret(closes, 3),
        "ret6": cl_ret(closes, 6),
        "ret12": cl_ret(closes, 12),
        "ret24": cl_ret(closes, 24),
        "ema9_21": e9 / e21 - 1.0 if e21 else 0.0,
        "ema21_50": e21 / e50 - 1.0 if e50 else 0.0,
        "close_ema200": cur.close / e200 - 1.0 if e200 else 0.0,
        "rsi14": r / 100.0,
        "atr14_pct": a / cur.close,
        "vol_ratio": cur.volume / vol_avg if vol_avg > 0 else 1.0,
        "tod_sin": math.sin(2.0 * math.pi * mins / (24.0 * 60.0)),
        "tod_cos": math.cos(2.0 * math.pi * mins / (24.0 * 60.0)),
    }


def cl_ret(closes: list[float], n: int) -> float:
    if len(closes) <= n or closes[-1 - n] == 0:
        return 0.0
    return closes[-1] / closes[-1 - n] - 1.0
