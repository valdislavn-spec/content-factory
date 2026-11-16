from __future__ import annotations

from .config import Config
from .indicators import ema, rsi
from .models import Candle, Position, Signal


def evaluate(ticker: str, candles: list[Candle], position: Position | None, cfg: Config, forming: bool = True) -> Signal | None:
    """EMA(9/21) crossover + RSI filter. Long-only; exits on cross, stop or take-profit."""
    if len(candles) < 35:
        return None
    # last candle may still be forming; use the previous closed candle
    closed = candles[:-1] if forming and len(candles) > 1 else candles
    closes = [c.close for c in closed]
    fast = ema(closes, cfg.ema_fast)
    slow = ema(closes, cfg.ema_slow)
    strength = rsi(closes, cfg.rsi_period)
    if fast[-1] is None or slow[-1] is None or strength[-1] is None:
        return None
    if len(fast) < 2 or fast[-2] is None or slow[-2] is None:
        return None
    cur = closed[-1]
    prev = closed[-2]
    crossed_up = fast[-2] <= slow[-2] and fast[-1] > slow[-1]
    crossed_down = fast[-2] >= slow[-2] and fast[-1] < slow[-1]

    if position is None:
        trend_ok = True
        if cfg.trend_filter:
            trend = ema(closes, cfg.trend_ema)[-1]
            trend_ok = trend is not None and cur.close > trend
        if (crossed_up and trend_ok and cfg.rsi_min <= strength[-1] <= cfg.rsi_max
                and cur.close > cur.open):
            return Signal(ticker, "BUY", cur.close,
                          f"EMA{cfg.ema_fast}/{cfg.ema_slow} bullish cross", fast[-1], slow[-1], strength[-1])
        return None

    stop = position.avg_price * (1 - cfg.stop_loss)
    take = position.avg_price * (1 + cfg.take_profit)
    profit = cur.close > position.avg_price
    if crossed_down and (cfg.allow_loss_exit or profit):
        return Signal(ticker, "SELL", cur.close, "EMA9/21 bearish cross", fast[-1], slow[-1], strength[-1])
    if cfg.allow_loss_exit and cfg.stop_loss > 0 and cur.close <= stop:
        return Signal(ticker, "SELL", cur.close, f"stop loss < {stop:.2f}", fast[-1], slow[-1], strength[-1])
    if cur.close >= take:
        return Signal(ticker, "SELL", cur.close, f"take profit > {take:.2f}", fast[-1], slow[-1], strength[-1])
    return None
