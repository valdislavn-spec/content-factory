from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from .broker import BrokerError, PaperBroker, TinkoffBroker
from .config import Config
from .models import Position, Signal
from .moex import MSK, MoexData
from .risk import hard_loss_hit, loss_from_start, max_drawdown_pct
from .strategy import evaluate
from .orb import evaluate as evaluate_orb

log = logging.getLogger(__name__)


def market_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(MSK)
    return now.weekday() < 5 and (10, 0) <= (now.hour, now.minute) <= (18, 40)


def entry_allowed(now: datetime | None = None) -> bool:
    now = now or datetime.now(MSK)
    return now.weekday() < 5 and (10, 0) <= (now.hour, now.minute) <= (17, 30)


def force_close_time(now: datetime | None = None) -> bool:
    now = now or datetime.now(MSK)
    return now.weekday() < 5 and (now.hour, now.minute) >= (17, 45)


class Notifier:
    def __init__(self, token: str, chat_id: str, timeout: int = 10):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def send(self, text: str) -> None:
        if not (self.token and self.chat_id):
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True},
                timeout=self.timeout,
            )
        except Exception as exc:  # notifications must never break trading
            log.warning("telegram notify failed: %s", exc)


class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.prices: dict[str, float] = {}
        self.last_signals: dict[str, dict] = {}
        self.last_error = ""
        self.started_at = time.time()
        self.last_tick = ""
        self._stop = threading.Event()
        self.day = ""
        self.day_start_equity = cfg.start_equity
        self.trades_today = 0
        self.notifier = Notifier(cfg.telegram_bot_token, cfg.telegram_chat_id)
        self.trading_enabled = cfg.trading_enabled
        self.kill_switch = False
        self.kill_reason = ""

        if cfg.live_broker:
            self.broker = TinkoffBroker(
                cfg.tinkoff_token, cfg.mode, cfg.tinkoff_class_code,
                cfg.tinkoff_sandbox_topup, verify_tls=cfg.tinkoff_verify_tls,
            )
            self.broker.connect()
            self.data = self.broker
        else:
            self.broker = PaperBroker(cfg.state_path, cfg.start_equity, cfg.fee)
            self.data = MoexData(class_code=cfg.tinkoff_class_code, interval=10)
        try:
            self.risk_start_equity = float(self._equity())
        except Exception:
            self.risk_start_equity = float(cfg.start_equity)
        self.peak_equity = self.risk_start_equity
        if hard_loss_hit(self.risk_start_equity, self.risk_start_equity, cfg.max_total_loss_rub):
            self._set_kill("already at loss limit")

    def stop(self) -> None:
        self._stop.set()

    def _set_kill(self, reason: str) -> None:
        if not self.kill_switch:
            self.kill_switch = True
            self.kill_reason = reason
            log.error("RISK KILL SWITCH: %s", reason)
            self.notifier.send(f"🛑 RISK KILL SWITCH: {reason}\nMode: {self.cfg.mode}")

    def _risk_check(self, equity: float) -> None:
        self.peak_equity = max(self.peak_equity, equity)
        if hard_loss_hit(equity, self.risk_start_equity, self.cfg.max_total_loss_rub):
            loss = loss_from_start(equity, self.risk_start_equity)
            self._set_kill(f"loss {loss:.2f} RUB >= limit {self.cfg.max_total_loss_rub:.2f} RUB")

    # ---------- status ----------
    def status(self) -> dict:
        with self.lock:
            now = datetime.now(MSK)
            equity = self._equity()
            positions = self._positions()
            trades = self.broker.trades(limit=20)
            return {
                "mode": self.cfg.mode,
                "tickers": list(self.cfg.tickers),
                "market_open": market_open(now),
                "entry_allowed": entry_allowed(now),
                "msk_time": now.isoformat(),
                "equity": round(equity, 2),
                "start_equity": self.cfg.start_equity,
                "day_start_equity": round(self.day_start_equity, 2),
                "day_pnl": round(equity - self.day_start_equity, 2),
                "cash": round(self._cash(), 2) if not self.cfg.live_broker else None,
                "positions": positions,
                "prices": {k: round(v, 3) for k, v in self.prices.items()},
                "last_signals": self.last_signals,
                "last_error": self.last_error,
                "last_tick": self.last_tick,
                "uptime_seconds": int(time.time() - self.started_at),
                "trades": trades,
                "risk": {
                    "max_position_rub": self.cfg.max_position_rub,
                    "max_total_exposure_rub": self.cfg.max_total_exposure_rub,
                    "max_positions": self.cfg.max_positions,
                    "allow_loss_exit": self.cfg.allow_loss_exit,
                    "stop_loss": self.cfg.stop_loss,
                    "take_profit": self.cfg.take_profit,
                    "strategy": self.cfg.strategy,
                    "max_trades_per_day": self.cfg.max_trades_per_day,
                    "trades_today": self.trades_today,
                },
                "exposure_rub": round(self._exposure(), 2),
                "risk_guard": {
                    "trading_enabled": self.trading_enabled,
                    "kill_switch": self.kill_switch,
                    "kill_reason": self.kill_reason,
                    "max_total_loss_rub": self.cfg.max_total_loss_rub,
                    "loss_from_start_rub": round(loss_from_start(equity, self.risk_start_equity), 2),
                    "drawdown_from_peak_pct": round(max_drawdown_pct(self.peak_equity, equity), 3),
                },
            }

    def _cash(self) -> float:
        if isinstance(self.broker, PaperBroker):
            return self.broker.cash()
        return 0.0

    def _equity(self) -> float:
        if isinstance(self.broker, PaperBroker):
            return self.broker.equity(self.prices)
        try:
            return self.broker.equity()
        except BrokerError as exc:
            self.last_error = str(exc)
            return 0.0

    def _positions(self) -> list[dict]:
        if isinstance(self.broker, PaperBroker):
            return self.broker.positions()
        try:
            rows = self.broker.positions()
            return [r for r in rows if r["ticker"] in self.cfg.tickers]
        except BrokerError as exc:
            self.last_error = str(exc)
            return []

    def _exposure(self) -> float:
        total = 0.0
        for p in self._positions():
            price = self.prices.get(p["ticker"], float(p["avg_price"]))
            total += float(price) * int(p["qty"])
        return total

    def _position(self, ticker: str) -> Position | None:
        row = next((p for p in self._positions() if p["ticker"] == ticker), None)
        if not row:
            return None
        return Position(ticker=row["ticker"], qty=int(row["qty"]), avg_price=float(row["avg_price"]))

    # ---------- trading ----------
    def tick(self, now: datetime | None = None, execute: bool = True) -> list[dict]:
        now = now or datetime.now(MSK)
        day = now.date().isoformat()
        if self.day != day:
            self.day = day
            self.trades_today = 0
            self.day_start_equity = self._equity() if self.prices else self.cfg.start_equity
            if isinstance(self.broker, PaperBroker):
                self.broker.update_day(now, self.day_start_equity)

        results: list[dict] = []
        for ticker in self.cfg.tickers:
            try:
                if self.cfg.strategy == "orb" and isinstance(self.broker, TinkoffBroker):
                    candles = self.broker.candles(ticker, days=self.cfg.moex_days, interval=self.cfg.candle_interval)
                else:
                    candles = self.data.candles(ticker, days=self.cfg.moex_days)
            except Exception as exc:
                self.last_error = f"{ticker}: {exc}"
                log.warning("candles %s failed: %s", ticker, exc)
                continue
            if not candles:
                continue
            price = candles[-1].close
            self.prices[ticker] = price
            pos = self._position(ticker)
            signal = (
                evaluate_orb(ticker, candles, pos, self.cfg)
                if self.cfg.strategy == "orb"
                else evaluate(ticker, candles, pos, self.cfg)
            )
            if not signal:
                continue
            self.last_signals[ticker] = {
                "action": signal.action,
                "reason": signal.reason,
                "price": round(signal.price, 3),
                "rsi": round(signal.rsi, 1) if signal.rsi is not None else None,
                "meta": signal.meta,
                "ts": now.isoformat(),
            }
            log.info("SIGNAL %s %s %s", ticker, signal.action, signal.reason)
            if not execute:
                results.append({"signal": signal.action, "ticker": ticker, "price": signal.price})
                continue
            if not market_open(now):
                continue
            if signal.action == "BUY":
                if not self.cfg.trading_enabled:
                    continue
                if self.kill_switch:
                    continue
                if not entry_allowed(now) or len(self._positions()) >= self.cfg.max_positions:
                    continue
                if self.trades_today >= self.cfg.max_trades_per_day:
                    continue
                equity = self._equity()
                if self.day_start_equity and equity < self.day_start_equity * (1 - self.cfg.daily_loss_limit):
                    log.warning("daily loss limit reached; skip buy")
                    continue
                budget = min(equity * self.cfg.risk_per_trade, self.cfg.max_position_rub)
                if not self.cfg.live_broker:
                    budget = min(budget, self._cash())
                budget = min(budget, self.cfg.max_total_exposure_rub - self._exposure())
                if budget <= 0:
                    continue
                filled = self.broker.buy(ticker, price, budget, signal.reason, now)
                if filled:
                    self.trades_today += 1
                    results.append(filled)
                    self.notifier.send(f"🟢 BUY {ticker} @ {price:.2f}\n{signal.reason}\nMode: {self.cfg.mode}")
            elif signal.action == "SELL" and pos:
                filled = self.broker.sell(ticker, price, signal.reason, now)
                if filled:
                    results.append(filled)
                    pnl = filled.get("pnl")
                    extra = f"\nPnL: {pnl:.2f} RUB" if pnl is not None else ""
                    self.notifier.send(f"🔴 SELL {ticker} @ {price:.2f}{extra}\n{signal.reason}\nMode: {self.cfg.mode}")
        if execute and force_close_time(now):
            results.extend(self.close_all(now, reason="end of session"))
        self._risk_check(self._equity())
        self.last_tick = now.isoformat()
        return results

    def close_all(self, now: datetime, reason: str = "end of session") -> list[dict]:
        out = []
        for pos in self._positions():
            ticker = pos["ticker"]
            price = self.prices.get(ticker, float(pos["avg_price"]))
            entry = float(pos["avg_price"])
            net_profit = price * (1 - self.cfg.fee) > entry * (1 + self.cfg.fee)
            if not self.cfg.allow_loss_exit and not net_profit:
                self.notifier.send(
                    f"⏸️ HOLD {ticker} @ {price:.2f} (entry {entry:.2f}): "
                    f"not selling at a net loss\nMode: {self.cfg.mode}"
                )
                continue
            try:
                filled = self.broker.sell(ticker, price, reason, now)
                if filled:
                    out.append(filled)
                    self.notifier.send(f"⚪ CLOSE {ticker} @ {price:.2f}\n{reason}\nMode: {self.cfg.mode}")
            except BrokerError as exc:
                self.last_error = str(exc)
                log.warning("close %s failed: %s", ticker, exc)
        return out


    def run_forever(self) -> None:
        log.info("engine started: mode=%s tickers=%s", self.cfg.mode, ",".join(self.cfg.tickers))
        # Warm prices/signals even outside the session so /status is useful on first deploy.
        try:
            self.tick(execute=False)
        except Exception as exc:
            self.last_error = str(exc)
            log.warning("initial data warmup failed: %s", exc)
        while not self._stop.is_set():
            try:
                if market_open():
                    self.tick()
                else:
                    self.last_tick = datetime.now(MSK).isoformat()
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("tick failed: %s", exc)
            for _ in range(max(1, self.cfg.poll_seconds)):
                if self._stop.wait(1):
                    return

    def run_once(self, execute: bool = False) -> dict:
        self.tick(now=datetime.now(MSK), execute=execute)
        return self.status()
