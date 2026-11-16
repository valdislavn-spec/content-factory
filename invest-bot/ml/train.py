"""Train and validate the optional ML direction model on cached candles.

Run with a Python that has numpy:  PYTHONPATH=. python ml/train.py --history data/history
"""
from __future__ import annotations

import argparse, glob, json, math, sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot.ml_features import FEATURES, extract, cl_ret  # noqa: E402
from bot.models import Candle  # noqa: E402
from bot.ml_model import LogitModel  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.backtest import run_scenario  # noqa: E402
from bot.models import Signal  # noqa: E402


def load(history_dir: str) -> dict[str, list[Candle]]:
    data = {}
    files = sorted(glob.glob(str(Path(history_dir) / "*_365d.json")))
    if not files:
        files = sorted(glob.glob(str(Path(history_dir) / "*_180d.json")))
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        data[d["ticker"]] = [
            Candle(datetime.fromisoformat(c["ts"]), c["open"], c["high"], c["low"], c["close"], c["volume"])
            for c in d["candles"]
        ]
    return data


def rows_for(data, horizon: int, threshold: float):
    rows = []
    for ticker, candles in data.items():
        for i in range(70, len(candles) - horizon):
            feats = extract(candles[max(0, i - 250): i + 1], forming=False)
            if feats is None:
                continue
            fut = candles[i + horizon].close / candles[i].close - 1.0
            rows.append((candles[i].ts, ticker, feats, 1 if fut > threshold else 0))
    return rows


def fit(rows, lam: float = 1.0):
    X = np.array([[r[2][k] for k in FEATURES] for r in rows], dtype=float)
    y = np.array([r[3] for r in rows], dtype=float)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    Z = (X - mean) / std
    Xb = np.c_[np.ones(len(Z)), Z]
    reg = lam * np.eye(Xb.shape[1]); reg[0, 0] = 0.0
    w = np.linalg.solve(Xb.T @ Xb + reg, Xb.T @ y)
    return {"features": FEATURES, "mean": mean.tolist(), "std": std.tolist(),
            "weights": w[1:].tolist(), "bias": float(w[0]), "horizon": 6, "threshold": 0.55}


def probs(model: LogitModel, rows):
    return np.array([model.predict(r[2]) for r in rows])


def evaluate(rows, p, thr):
    y = np.array([r[3] for r in rows])
    pred = (p >= thr).astype(int)
    acc = float((pred == y).mean()) if len(y) else 0.0
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"n": len(y), "pos_rate": round(float(y.mean()), 4) if len(y) else 0,
            "acc": round(acc, 4), "precision": round(prec, 4), "recall": round(rec, 4),
            "tn": tn, "fp": fp, "fn": fn, "tp": tp}


def trading_test(data, model, d0, d1, thr):
    import bot.backtest as bt
    def sig(scenario, ticker, candles, position, cfg):
        if position is not None:
            return None
        f = extract(candles, forming=False)
        if f is None:
            return None
        if model.predict(f) < thr:
            return None
        # simple trend confirmation
        from bot.indicators import ema
        e = ema([c.close for c in candles], 200)[-1]
        if e is None or candles[-1].close <= e:
            return None
        return Signal(ticker, "BUY", candles[-1].close, "ML probability")
    old = bt._strategy_signal; bt._strategy_signal = sig
    try:
        subset = {t: [c for c in rows if d0 <= c.ts.date() <= d1] for t, rows in data.items()}
        subset = {t: r for t, r in subset.items() if r}
        cfg = Config(strategy="ema_rsi", mode="sandbox", allow_loss_exit=True, start_equity=100000,
                     risk_per_trade=1.0, max_positions=1, daily_loss_limit=0.02,
                     take_profit=0.02, stop_loss=0.01, fee=0.0005,
                     max_position_rub=3000, max_total_exposure_rub=3000, max_trades_per_day=2,
                     trend_filter=False)
        r = run_scenario(subset, {t: 1 for t in subset}, "ema_stop", cfg)
        return {k: r[k] for k in ["trades", "net_pnl", "win_rate_pct", "profit_factor", "max_drawdown_pct"]}
    finally:
        bt._strategy_signal = old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="data/history")
    ap.add_argument("--train-end", default="2026-09-18")
    ap.add_argument("--horizon", type=int, default=6)
    ap.add_argument("--label-threshold", type=float, default=0.001)
    ap.add_argument("--save", default="models/ml_logit.json")
    args = ap.parse_args()
    data = load(args.history)
    rows = rows_for(data, args.horizon, args.label_threshold)
    split = datetime.fromisoformat(args.train_end).date()
    train = [r for r in rows if r[0].date() <= split]
    # purge labels that extend past the split
    train = [r for r in train if (r[0].date()).toordinal() + 1 <= split.toordinal()]  # date-level purge
    test = [r for r in rows if r[0].date() > split]
    print("rows", len(rows), "train", len(train), "test", len(test))
    payload = fit(train)
    model = LogitModel(payload)
    for thr in [0.50, 0.55, 0.60, 0.65]:
        print("thr", thr, "train", evaluate(train, probs(model, train), thr), "test", evaluate(test, probs(model, test), thr))
    for thr in [0.55, 0.60, 0.65]:
        print("trading", thr, "train", trading_test(data, model, min(r[0].date() for r in train), split, thr),
              "test", trading_test(data, model, split, max(r[0].date() for r in test), thr))
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", args.save)


if __name__ == "__main__":
    main()
