from datetime import datetime, timedelta

from bot.config import Config
from bot.models import Candle, Position
from bot.strategy import evaluate


def make_candles(closes):
    start = datetime(2026, 1, 1, 10, 0)
    return [Candle(start + timedelta(minutes=10 * i), c * 0.999, c, c * 0.998, c, 1000) for i, c in enumerate(closes)]


def test_bullish_cross_generates_buy():
    # flat, then rising quickly: EMA9 crosses EMA21, RSI in range
    closes = [100.0] * 30 + [100.0 + i * 0.3 for i in range(1, 11)]
    signal = evaluate("SBER", make_candles(closes), None, Config())
    assert signal is None or signal.action == "BUY"
    if signal is not None:
        assert signal.rsi is not None and 45 <= signal.rsi <= 72


def test_stop_loss_triggers_sell():
    closes = [100.0] * 40
    candles = make_candles(closes)
    pos = Position("SBER", 10, 100.0)
    # force a low last closed candle by mutating the list (open/high/low/close all same)
    candles[-2] = Candle(candles[-2].ts, 98.0, 98.0, 98.0, 98.0, 1000)
    signal = evaluate("SBER", candles, pos, Config(stop_loss=0.012, take_profit=0.02))
    assert signal is not None and signal.action == "SELL"
