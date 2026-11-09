"""Индикаторы для сигналов: EMA, RSI (Wilder), ATR, средний объём.

Чистый Python (без pandas/numpy), чтобы одинаково работать в GitHub Actions.
"""
from __future__ import annotations

from typing import List, Optional


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """EMA по классической формуле; первые period-1 значений — None."""
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1.0)
    out: List[Optional[float]] = []
    prev: Optional[float] = None
    window: List[float] = []
    for value in values:
        window.append(float(value))
        if len(window) < period:
            out.append(None)
            continue
        if prev is None:
            prev = sum(window[-period:]) / period
        else:
            prev = float(value) * k + prev * (1.0 - k)
        out.append(prev)
    return out


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """RSI по Уайлдеру."""
    if len(values) < period + 1:
        return [None] * len(values)
    out: List[Optional[float]] = [None] * len(values)
    gains = 0.0
    losses = 0.0
    for index in range(1, period + 1):
        delta = values[index] - values[index - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for index in range(period + 1, len(values)):
        delta = values[index] - values[index - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[index] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def atr(candles: List[dict], period: int = 14) -> List[Optional[float]]:
    """ATR по Уайлдеру на основе true range."""
    if not candles:
        return []
    trs: List[float] = []
    for index, candle in enumerate(candles):
        high = candle["high"]
        low = candle["low"]
        if index == 0:
            trs.append(high - low)
            continue
        prev_close = candles[index - 1]["close"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    out: List[Optional[float]] = [None] * len(candles)
    if len(trs) < period:
        return out
    prev = sum(trs[:period]) / period
    out[period - 1] = prev
    for index in range(period, len(trs)):
        prev = (prev * (period - 1) + trs[index]) / period
        out[index] = prev
    return out


def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def volume_ratio(candles: List[dict], period: int = 20) -> Optional[float]:
    """""Объём последней свечи / средний объём за period свечей."""
    if len(candles) < period + 1:
        return None
    average = sum(candle["volume"] for candle in candles[-period - 1 : -1]) / period
    if average <= 0:
        return None
    return candles[-1]["volume"] / average
