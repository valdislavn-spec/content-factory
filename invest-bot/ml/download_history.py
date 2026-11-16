"""Download cached 5-minute candles for ML research (not used by live bot).

Example:
  cd content-factory/invest-bot
  CANDLES_DELAY=0.5 PYTHONPATH=. ../.venv/bin/python ml/download_history.py --days 365
"""
from __future__ import annotations

import argparse, json, os, time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bot.broker import TinkoffBroker

TICKERS = ["SBER", "GAZP", "LKOH", "YDEX", "ROSN", "VTBR", "TATN", "MTSS"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", default="data/history")
    ap.add_argument("--token-file", default="../../.local/tinkoff/t1.txt")
    args = ap.parse_args()
    token = Path(args.token_file).read_text().strip()
    broker = TinkoffBroker(token, "sandbox")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for ticker in TICKERS:
        dst = out / f"{ticker}_{args.days}d.json"
        if dst.exists():
            print(f"skip {dst}", flush=True)
            continue
        rows = broker.candles(ticker, days=args.days, interval="CANDLE_INTERVAL_5_MIN")
        if not rows:
            print(f"no data {ticker}", flush=True); continue
        dst.write_text(json.dumps({"ticker": ticker, "lot": broker.instrument(ticker).get("lot", 1),
                                   "interval": "5min", "candles": [asdict(c) for c in rows]},
                                  ensure_ascii=False, default=str), encoding="utf-8")
        print(f"saved {ticker}: {len(rows)}", flush=True)
        time.sleep(float(os.getenv("TICKER_DELAY", "2") or 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
