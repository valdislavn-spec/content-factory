from datetime import datetime, timedelta, timezone

from bot.config import Config
from bot.models import Candle, Position
from bot.orb import atr, evaluate, opening_range

MSK = timezone(timedelta(hours=3))


def candles_from_closes(closes, start=datetime(2026, 11, 10, 10, 0, tzinfo=MSK), volumes=None):
    out = []
    for i, close in enumerate(closes):
        vol = volumes[i] if volumes else 1000.0
        out.append(Candle(start + timedelta(minutes=5 * i), close - 0.05, close + 0.1, close - 0.1, close, vol))
    return out


def test_opening_range_uses_first_15_minutes():
    closes = [100.0] * 8
    candles = candles_from_closes(closes)
    high, low = opening_range(candles, 15)
    assert high == 100.1
    assert low == 99.9


def test_atr_positive():
    candles = candles_from_closes([100 + i * 0.1 for i in range(20)])
    value = atr(candles, 14)
    assert value is not None and value > 0


def test_no_entry_before_opening_range_complete():
    closes = [100.0] * 6
    candles = candles_from_closes(closes)
    signal = evaluate("SBER", candles, None, Config(strategy="orb"))
    assert signal is None


def test_no_loss_exit_by_default():
    closes = [100.0] * 30
    candles = candles_from_closes(closes)
    candles = candles + [Candle(candles[-1].ts + timedelta(minutes=5), 97, 97.2, 96.8, 97.0, 5000)]
    pos = Position("SBER", 10, 100.0)
    assert evaluate("SBER", candles, pos, Config(strategy="orb")) is None


def test_stop_exit_when_explicitly_enabled():
    closes = [100.0] * 30
    candles = candles_from_closes(closes)
    candles = candles + [
        Candle(candles[-1].ts + timedelta(minutes=5), 97, 97.2, 96.8, 97.0, 5000),
        Candle(candles[-1].ts + timedelta(minutes=10), 97, 97.2, 96.8, 97.0, 5000),
    ]
    pos = Position("SBER", 10, 100.0)
    signal = evaluate("SBER", candles, pos, Config(strategy="orb", allow_loss_exit=True, stop_loss=0.01))
    assert signal is not None and signal.action == "SELL"


def test_orb_breakout_generates_buy():
    start = datetime(2026, 11, 10, 10, 0, tzinfo=MSK)
    candles = []
    for i in range(3):
        candles.append(Candle(start + timedelta(minutes=5 * i), 100.0, 100.2, 99.8, 100.0, 1000))
    for i in range(3, 30):
        close = 100.0 + 0.1 * i
        vol = 5000 if i == 29 else 1000
        candles.append(Candle(start + timedelta(minutes=5 * i), close - 0.05, close + 0.1, close - 0.1, close, vol))
    cfg = Config(
        strategy="orb", or_minutes=15, rel_vol_min=1.0, rel_vol_lookback=5,
        atr_period=2, atr_min_pct=0.0001, atr_max_pct=1.0, take_r=2.0,
        max_position_rub=3000, max_total_exposure_rub=3000,
    )
    signal = evaluate("SBER", candles, None, cfg, forming=False)
    assert signal is not None and signal.action == "BUY"
    assert signal.meta["stop"] <= signal.price
    assert signal.meta["target"] > signal.price
