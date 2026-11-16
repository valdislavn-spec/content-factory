"""Optional ML strategy: logistic-regression direction filter.

Disabled by default. Enable with STRATEGY=ml and a trained model file.
"""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .indicators import ema
from .ml_features import extract
from .ml_model import LogitModel
from .models import Candle, Position, Signal

_CACHE: dict[str, LogitModel] = {}


def _model(path: str) -> LogitModel | None:
    key = str(Path(path))
    if key not in _CACHE:
        try:
            _CACHE[key] = LogitModel.load(key)
        except Exception:
            _CACHE[key] = None  # type: ignore[assignment]
    return _CACHE[key]


def evaluate(ticker: str, candles: list[Candle], position: Position | None, cfg: Config, forming: bool = True) -> Signal | None:
    if position is not None:
        stop = position.avg_price * (1 - cfg.stop_loss)
        take = position.avg_price * (1 + cfg.take_profit)
        cur = (candles[:-1] if forming and len(candles) > 1 else candles)[-1]
        if cfg.allow_loss_exit and cfg.stop_loss > 0 and cur.close <= stop:
            return Signal(ticker, "SELL", cur.close, f"ml stop < {stop:.2f}")
        if cur.close >= take:
            return Signal(ticker, "SELL", cur.close, f"ml take > {take:.2f}")
        return None
    model = _model(cfg.ml_model_path)
    if model is None:
        return None
    feats = extract(candles, forming=forming)
    if feats is None:
        return None
    prob = model.predict(feats)
    if prob < cfg.ml_threshold:
        return None
    if cfg.trend_filter:
        closed = candles[:-1] if forming and len(candles) > 1 else candles
        trend = ema([c.close for c in closed], cfg.trend_ema)[-1]
        if trend is None or closed[-1].close <= trend:
            return None
    cur = (candles[:-1] if forming and len(candles) > 1 else candles)[-1]
    return Signal(ticker, "BUY", cur.close, f"ML prob {prob:.3f} >= {cfg.ml_threshold:.2f}", rsi=feats.get("rsi14", 0) * 100)
