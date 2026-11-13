from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Position:
    ticker: str
    qty: int
    avg_price: float


@dataclass(frozen=True)
class Signal:
    ticker: str
    action: str  # BUY | SELL | HOLD
    price: float
    reason: str
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
    meta: dict | None = None
