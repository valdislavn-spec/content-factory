import json
from pathlib import Path

from bot.config import Config
from bot.ml_strategy import evaluate
from bot.models import Candle


def make_candles(n=240):
    ts = 0
    out = []
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    for i in range(n):
        p = 100.0 + i * 0.1
        out.append(Candle(base + timedelta(minutes=5 * i), p, p + 0.5, p - 0.5, p, 1000))
    return out


def model_file(tmp_path: Path, bias: float = 2.0):
    payload = {
        "features": ["ret1", "ret3", "ret6", "ret12", "ret24", "ema9_21", "ema21_50",
                     "close_ema200", "rsi14", "atr14_pct", "vol_ratio", "tod_sin", "tod_cos"],
        "mean": [0.0] * 13, "std": [1.0] * 13, "weights": [0.0] * 13,
        "bias": bias, "horizon": 6, "threshold": 0.6,
    }
    p = tmp_path / "m.json"
    p.write_text(json.dumps(payload))
    return str(p)


def test_ml_strategy_uses_model(tmp_path):
    cfg = Config(strategy="ml", ml_model_path=model_file(tmp_path), ml_threshold=0.6)
    sig = evaluate("SBER", make_candles(), None, cfg)
    assert sig is not None and sig.action == "BUY"


def test_ml_strategy_missing_model_is_safe(tmp_path):
    cfg = Config(strategy="ml", ml_model_path=str(tmp_path / "missing.json"))
    assert evaluate("SBER", make_candles(), None, cfg) is None
