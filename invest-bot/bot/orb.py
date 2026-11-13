from __future__ import annotations

"""Opening Range Breakout (ORB) with VWAP, ATR and relative-volume filters.

Long-only. A signal is generated from completed candles only: the newest candle
is treated as still forming and is removed before evaluation.
"""

from datetime import date, datetime, time
from statistics import fmean

from .config import Config
from .models import Candle, Position, Signal

SESSION_OPEN_MINUTE = 10 * 60


def _minutes(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


def _session_day(candles: list[Candle]) -> date:
    return candles[-1].ts.date()


def _session(candles: list[Candle], day: date) -> list[Candle]:
    # Data is sorted; walk back from the right, stop when the day changes.
    out = []
    for c in reversed(candles):
        d = c.ts.date()
        if d == day:
            out.append(c)
        elif d < day:
            break
    out.reverse()
    return out


def opening_range(candles: list[Candle], or_minutes: int) -> tuple[float, float] | None:
    if not candles:
        return None
    day = _session_day(candles)
    end = SESSION_OPEN_MINUTE + or_minutes
    rows = [
        c for c in _session(candles, day)
        if SESSION_OPEN_MINUTE <= _minutes(c.ts) < end
    ]
    if not rows:
        return None
    return max(c.high for c in rows), min(c.low for c in rows)


def session_vwap(candles: list[Candle], day: date) -> float | None:
    rows = _session(candles, day)
    pv = 0.0
    vol = 0.0
    for c in rows:
        typical = (c.high + c.low + c.close) / 3.0
        pv += typical * c.volume
        vol += c.volume
    return pv / vol if vol > 0 else None


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if period <= 0 or len(candles) < period + 1:
        return None
    recent = candles[-(period + 1):]
    ranges = []
    for i in range(1, len(recent)):
        prev = recent[i - 1].close
        c = recent[i]
        ranges.append(max(c.high - c.low, abs(c.high - prev), abs(c.low - prev)))
    return fmean(ranges) if ranges else None


def relative_volume(candles: list[Candle], lookback: int = 20) -> float | None:
    if len(candles) < 2:
        return None
    cur = candles[-1].volume
    prev = [c.volume for c in candles[-lookback - 1:-1]]
    if not prev or cur <= 0:
        return None
    avg = fmean(prev)
    return cur / avg if avg > 0 else None


def _parse_hm(value: str) -> int:
    hh, mm = value.split(":", 1)
    return int(hh) * 60 + int(mm)


def evaluate(ticker: str, candles: list[Candle], position: Position | None, cfg: Config, forming: bool = True) -> Signal | None:
    if len(candles) < 2:
        return None
    closed = candles[:-1] if forming else candles  # newest candle may still be forming
    if len(closed) < max(cfg.atr_period + 2, 20):
        return None
    cur = closed[-1]
    day = _session_day(closed)
    now_min = _minutes(cur.ts)

    if position is not None:
        price = cur.close
        take = position.avg_price * (1 + cfg.take_profit)
        stop = position.avg_price * (1 - cfg.stop_loss)
        profit = price > position.avg_price
        if price >= take:
            return Signal(ticker, "SELL", price, f"ORB take profit >= {take:.2f}", meta={"take": take})
        if cfg.allow_loss_exit and cfg.stop_loss > 0 and price <= stop:
            return Signal(ticker, "SELL", price, f"ORB stop loss <= {stop:.2f}", meta={"stop": stop})
        vwap = session_vwap(closed, day)
        if cfg.allow_loss_exit and profit and vwap and price < vwap:
            return Signal(ticker, "SELL", price, f"ORB close below VWAP {vwap:.2f}", meta={"vwap": vwap})
        return None

    or_levels = opening_range(closed, cfg.or_minutes)
    if or_levels is None:
        return None
    or_high, or_low = or_levels
    # only after the opening range is complete and before the entry cutoff
    if now_min < SESSION_OPEN_MINUTE + cfg.or_minutes:
        return None
    if now_min > _parse_hm(cfg.entry_cutoff):
        return None
    if cur.close <= or_high * (1 + cfg.breakout_buffer):
        return None
    if cur.close <= cur.open:
        return None
    vwap = session_vwap(closed, day)
    if not vwap or cur.close <= vwap:
        return None
    rv = relative_volume(closed, cfg.rel_vol_lookback)
    if rv is None or rv < cfg.rel_vol_min:
        return None
    a = atr(closed, cfg.atr_period)
    if not a or a <= 0:
        return None
    atr_pct = a / cur.close
    if atr_pct < cfg.atr_min_pct or atr_pct > cfg.atr_max_pct:
        return None
    # Classic ORB: stop at the opposite side of the opening range; target at
    # least 2R (and at least the configured percentage target).
    stop = or_low
    risk = max(cur.close - stop, cur.close * 0.002)
    target = cur.close + max(cfg.take_profit * cur.close, cfg.take_r * risk)
    meta = {
        "or_high": round(or_high, 4),
        "or_low": round(or_low, 4),
        "vwap": round(vwap, 4),
        "atr_pct": round(atr_pct, 5),
        "rel_vol": round(rv, 2),
        "stop": round(stop, 4),
        "target": round(target, 4),
    }
    reason = (
        f"ORB break > {or_high:.2f}, VWAP {vwap:.2f}, "
        f"RV {rv:.2f}x, ATR {atr_pct:.2%}"
    )
    return Signal(ticker, "BUY", cur.close, reason, meta=meta)
