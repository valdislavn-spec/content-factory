from __future__ import annotations

from .config import Config
from .indicators import ema, rsi
from .models import Candle, Position, Signal


def evaluate(ticker: str, candles: list[Candle], position: Position | None, cfg: Config) -> Signal | None:
    """EMA(9/21) crossover + RSI filter. Long-only; exits on cross, stop or take-profit."""
    if len(candles) < 35:
        return None
    # last candle may still be forming; use the previous closed candle
    closed = candles[:-1] if len(candles) > 1 else candles
    closes = [c.close for c in closed]
    fast = ema(closes, 9)
    slow = ema(closes, 21)
    strength = rsi(closes, 14)
    if fast[-1] is None or slow[-1] is None or strength[-1] is None:
        return None
    if len(fast) < 2 or fast[-2] is None or slow[-2] is None:
        return None
    cur = closed[-1]
    prev = closed[-2]
    crossed_up = fast[-2] <= slow[-2] and fast[-1] > slow[-1]
    crossed_down = fast[-2] >= slow[-2] and fast[-1] < slow[-1]

    if position is None:
        if crossed_up and 45 <= strength[-1] <= 72 and cur.close > cur.open:
            return Signal(ticker, "BUY", cur.close, "EMA9/21 bullish cross", fast[-1], slow[-1], strength[-1])
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
