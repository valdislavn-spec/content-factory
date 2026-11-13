from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from math import floor, sqrt
from pathlib import Path
from statistics import mean, pstdev

from .broker import TinkoffBroker
from .config import Config
from .models import Candle, Position
from .orb import evaluate as orb_evaluate
from .strategy import evaluate as ema_evaluate

MSK = timezone(timedelta(hours=3))
INTERVAL = "CANDLE_INTERVAL_5_MIN"


@dataclass
class Trade:
    ticker: str
    side: str
    entry_ts: str
    exit_ts: str
    entry: float
    exit: float
    qty: int
    pnl: float
    reason: str
    overnight: bool = False


def load_candles(tickers: list[str], days: int, token: str) -> tuple[dict[str, list[Candle]], dict[str, int]]:
    broker = TinkoffBroker(token, "sandbox")
    data: dict[str, list[Candle]] = {}
    lots: dict[str, int] = {}
    for ticker in tickers:
        print(f"loading {ticker} ...", flush=True)
        rows = broker.candles(ticker, days=days, interval=INTERVAL)
        if not rows:
            print(f"  no candles for {ticker}", flush=True)
            continue
        data[ticker] = rows
        lots[ticker] = int(broker.instrument(ticker).get("lot", 1) or 1)
        print(f"  {len(rows)} candles, lot={lots[ticker]}, {rows[0].ts} .. {rows[-1].ts}", flush=True)
    return data, lots


def _strategy_signal(scenario: str, ticker: str, candles: list[Candle], position: Position | None, cfg: Config):
    if scenario.startswith("orb"):
        return orb_evaluate(ticker, candles, position, cfg, forming=False)
    return ema_evaluate(ticker, candles, position, cfg, forming=False)


def run_scenario(data: dict[str, list[Candle]], lots: dict[str, int], scenario: str, cfg: Config) -> dict:
    indexes = {t: {c.ts: i for i, c in enumerate(rows)} for t, rows in data.items()}
    timestamps = sorted({c.ts for rows in data.values() for c in rows})
    last_prices: dict[str, float] = {}
    cash = cfg.start_equity
    position = None  # dict with ticker, qty, entry, stop, take, entry_ts
    day = None
    day_start_equity = cfg.start_equity
    trades_today = 0
    trades: list[Trade] = []
    equity_curve: list[tuple[datetime, float]] = []
    overnight_holds = 0

    def mark_equity() -> float:
        value = cash
        if position:
            value += position["qty"] * last_prices.get(position["ticker"], position["entry"])
        return value

    def close_position(ts: datetime, price: float, reason: str) -> None:
        nonlocal position, cash
        if not position:
            return
        fills = price * (1 - cfg.fee)
        proceeds = position["qty"] * fills
        cash += proceeds
        pnl = proceeds - position["qty"] * position["entry"] * (1 + cfg.fee)
        trades.append(Trade(
            ticker=position["ticker"], side="SELL", entry_ts=position["entry_ts"].isoformat(),
            exit_ts=ts.isoformat(), entry=round(position["entry"], 4), exit=round(price, 4),
            qty=position["qty"], pnl=round(pnl, 4), reason=reason,
            overnight=position["entry_ts"].date() != ts.date(),
        ))
        position = None

    for ts in timestamps:
        d = ts.date()
        if d != day:
            day = d
            trades_today = 0
            day_start_equity = mark_equity()
        for ticker, rows in data.items():
            i = indexes[ticker].get(ts)
            if i is None:
                continue
            candles = rows[max(0, i - 600):i + 1]
            c = candles[-1]
            last_prices[ticker] = c.close

            if position and position["ticker"] == ticker:
                # Intrabar risk exits (conservative: stop wins if both hit)
                if cfg.allow_loss_exit and c.low <= position["stop"]:
                    close_position(ts, min(position["stop"], c.open), "stop")
                elif c.high >= position["take"]:
                    close_position(ts, max(position["take"], c.open), "take")
                elif ts.time() >= time(17, 45) and (
                    cfg.allow_loss_exit
                    or c.close * (1 - cfg.fee) > position["entry"] * (1 + cfg.fee)
                ):
                    close_position(ts, c.close, "end of session")
                elif candles:
                    sig = _strategy_signal(scenario, ticker, candles, Position(ticker, position["qty"], position["entry"]), cfg)
                    if sig and sig.action == "SELL":
                        close_position(ts, c.close, sig.reason)
                continue

            if position:
                continue
            if trades_today >= cfg.max_trades_per_day:
                continue
            if not (time(10, 15) <= ts.time() <= time(16, 30)):
                continue
            if mark_equity() < day_start_equity * (1 - cfg.daily_loss_limit):
                continue
            # only take a signal from the current candle's ticker
            sig = _strategy_signal(scenario, ticker, candles, None, cfg)
            if not sig or sig.action != "BUY":
                continue
            budget = min(cash, cfg.max_position_rub, cfg.max_total_exposure_rub)
            if budget < 100:
                continue
            entry = c.close * (1.0005)  # conservative slippage
            qty = int(floor(budget / (entry * lots[ticker]))) * lots[ticker]
            if qty <= 0:
                continue
            cost = qty * entry
            fee = cost * cfg.fee
            if cost + fee > cash:
                continue
            cash -= cost + fee
            meta = sig.meta or {}
            stop = float(meta.get("stop") or entry * (1 - cfg.stop_loss))
            take = float(meta.get("target") or entry * (1 + cfg.take_profit))
            position = {
                "ticker": ticker, "qty": qty, "entry": entry,
                "stop": min(stop, entry), "take": max(take, entry),
                "entry_ts": ts,
            }
            trades_today += 1

        equity_curve.append((ts, mark_equity()))

    if position:
        last_ts = equity_curve[-1][0] if equity_curve else datetime.now(MSK)
        close_position(last_ts, last_prices.get(position["ticker"], position["entry"]), "backtest end")
        equity_curve.append((last_ts, mark_equity()))

    final = equity_curve[-1][1] if equity_curve else cfg.start_equity
    peak = cfg.start_equity
    max_dd = 0.0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        if peak:
            max_dd = max(max_dd, (peak - eq) / peak)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    daily_eq: dict[object, float] = {}
    for ts, eq in equity_curve:
        daily_eq[ts.date()] = eq
    daily_returns = []
    prev = cfg.start_equity
    for d in sorted(daily_eq):
        eq = daily_eq[d]
        if prev:
            daily_returns.append(eq / prev - 1)
        prev = eq
    sharpe = (mean(daily_returns) / pstdev(daily_returns) * sqrt(252)) if len(daily_returns) > 2 and pstdev(daily_returns) > 0 else 0.0
    exposure_days = len({t.entry_ts[:10] for t in trades})
    return {
        "scenario": scenario,
        "start_equity": cfg.start_equity,
        "final_equity": round(final, 2),
        "net_pnl": round(final - cfg.start_equity, 2),
        "return_pct": round((final / cfg.start_equity - 1) * 100, 3),
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(trades), 2) if trades else 0.0,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else (None if not gross_win else 999.0),
        "avg_trade_rub": round(mean([t.pnl for t in trades]), 2) if trades else 0.0,
        "max_drawdown_pct": round(max_dd * 100, 3),
        "sharpe_daily": round(sharpe, 3),
        "overnight_holds": sum(1 for t in trades if t.overnight),
        "max_position_rub": cfg.max_position_rub,
        "allow_loss_exit": cfg.allow_loss_exit,
        "trades_list": [asdict(t) for t in trades],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--tickers", default="SBER,GAZP,ROSN,VTBR,TATN,MTSS")
    ap.add_argument("--token-file", default="")
    ap.add_argument("--out", default="backtest_results.json")
    args = ap.parse_args()
    token = ""
    if args.token_file:
        token = Path(args.token_file).read_text().strip()
    if not token:
        import os
        token = os.getenv("TINKOFF_TOKEN", "").strip()
    if not token:
        raise SystemExit("set TINKOFF_TOKEN or --token-file")
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    data, lots = load_candles(tickers, args.days, token)
    if not data:
        raise SystemExit("no data")
    base = dict(
        tickers=tuple(data),
        start_equity=100_000.0,
        risk_per_trade=1.0,
        max_positions=1,
        daily_loss_limit=0.02,
        take_profit=0.02,
        stop_loss=0.01,
        fee=0.0005,
        max_position_rub=3000.0,
        max_total_exposure_rub=3000.0,
        max_trades_per_day=2,
        or_minutes=15,
        entry_cutoff="16:30",
        rel_vol_min=1.4,
        atr_period=14,
        atr_min_pct=0.0015,
        atr_max_pct=0.015,
        take_r=2.0,
    )
    scenarios = {
        "ema_stop": Config(strategy="ema_rsi", allow_loss_exit=True, **base),
        "orb_stop": Config(strategy="orb", allow_loss_exit=True, **base),
        "orb_no_loss": Config(strategy="orb", allow_loss_exit=False, **base),
    }
    results = [run_scenario(data, lots, name, cfg) for name, cfg in scenarios.items()]
    out = {"days": args.days, "tickers": list(data), "results": results}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "trades_list"}, ensure_ascii=False))
    print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
