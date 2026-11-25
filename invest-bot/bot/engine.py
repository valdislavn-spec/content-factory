from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .broker import BrokerError, PaperBroker, TinkoffBroker
from .config import Config
from .models import Position, Signal
from .moex import MSK, MoexData
from .risk import hard_loss_hit, loss_from_start, max_drawdown_pct
from .state import StateStore
from .strategy import evaluate
from .orb import evaluate as evaluate_orb
from .ml_strategy import evaluate as evaluate_ml

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
        self.last_known_equity = 0.0
        self._stop = threading.Event()
        self.state = StateStore(cfg.state_path)
        self.day = str(self.state.get("day", "") or "")
        self.day_start_equity = self.state.get_float("day_start_equity", 0.0)
        self.trades_today = self.state.get_int("trades_today", 0)
        self.notifier = Notifier(cfg.telegram_bot_token, cfg.telegram_chat_id)
        self.trading_enabled = cfg.trading_enabled
        self.kill_switch = self.state.get_bool("kill_switch", False)
        self.kill_reason = str(self.state.get("kill_reason", "") or "")

        trade_log = cfg.trade_log or str(Path(cfg.state_path).with_name("trades.jsonl"))
        if cfg.live_broker:
            self.broker = TinkoffBroker(
                cfg.tinkoff_token, cfg.mode, cfg.tinkoff_class_code,
                cfg.tinkoff_sandbox_topup, verify_tls=cfg.tinkoff_verify_tls,
                account_id=cfg.tinkoff_account_id, trade_log=trade_log,
            )
            self.broker.connect()
            self.data = self.broker
        else:
            self.broker = PaperBroker(cfg.state_path, cfg.start_equity, cfg.fee)
            self.data = MoexData(class_code=cfg.tinkoff_class_code, interval=10)
        try:
            current_equity = float(self._equity())
        except Exception:
            current_equity = 0.0
        stored_risk = self.state.get_float("risk_start_equity", 0.0)
        self.risk_start_equity = stored_risk if stored_risk > 0 else float(cfg.start_equity)
        self.peak_equity = max(self.state.get_float("peak_equity", 0.0), current_equity)
        today = datetime.now(MSK).date().isoformat()
        if self.day != today or self.day_start_equity <= 0:
            self.day = today
            self.day_start_equity = current_equity if current_equity > 0 else float(cfg.start_equity)
            self.trades_today = 0
        self._save_state()
        if self.kill_switch:
            log.error("persisted kill switch active: %s", self.kill_reason)
        elif hard_loss_hit(current_equity, self.risk_start_equity, cfg.max_total_loss_rub):
            self._set_kill("already at loss limit")

    def stop(self) -> None:
        self._stop.set()

    def _save_state(self) -> None:
        self.state.set("risk_start_equity", self.risk_start_equity)
        self.state.set("peak_equity", self.peak_equity)
        self.state.set("day", self.day)
        self.state.set("day_start_equity", self.day_start_equity)
        self.state.set("trades_today", self.trades_today)
        self.state.set("kill_switch", self.kill_switch)
        self.state.set("kill_reason", self.kill_reason)

    def _set_kill(self, reason: str) -> None:
        if not self.kill_switch:
            self.kill_switch = True
            self.kill_reason = reason
            self._save_state()
            log.error("RISK KILL SWITCH: %s", reason)
            self.notifier.send(f"🛑 RISK KILL SWITCH: {reason}\nMode: {self.cfg.mode}")

    def _risk_check(self, equity: float) -> None:
        self.peak_equity = max(self.peak_equity, equity)
        self._save_state()
        if hard_loss_hit(equity, self.risk_start_equity, self.cfg.max_total_loss_rub):
            loss = loss_from_start(equity, self.risk_start_equity)
            self._set_kill(f"loss {loss:.2f} RUB >= limit {self.cfg.max_total_loss_rub:.2f} RUB")

    # ---------- status ----------
    def status(self) -> dict:
        with self.lock:
            now = datetime.now(MSK)
            try:
                equity = self._equity()
            except BrokerError:
                equity = self.last_known_equity
            try:
                positions = self._positions()
            except BrokerError:
                positions = []
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
                "day_pnl": round(equity - self.day_start_equity, 2) if self.day_start_equity > 0 else 0.0,
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
                "exposure_rub": round(self._safe_exposure(), 2),
                "risk_guard": {
                    "trading_enabled": self.trading_enabled,
                    "kill_switch": self.kill_switch,
                    "kill_reason": self.kill_reason,
                    "max_total_loss_rub": self.cfg.max_total_loss_rub,
                    "risk_start_equity": round(self.risk_start_equity, 2),
                    "peak_equity": round(self.peak_equity, 2),
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
            equity = self.broker.equity(self.prices)
            self.last_known_equity = float(equity)
            return float(equity)
        try:
            equity = float(self.broker.equity())
        except BrokerError as exc:
            self.last_error = str(exc)
            log.warning("equity request failed: %s", exc)
            if self.last_known_equity > 0:
                return self.last_known_equity
            raise
        self.last_known_equity = equity
        return equity

    def _positions(self) -> list[dict]:
        if isinstance(self.broker, PaperBroker):
            return self.broker.positions()
        try:
            rows = self.broker.positions()
        except BrokerError as exc:
            self.last_error = str(exc)
            log.warning("positions request failed: %s", exc)
            raise
        return [r for r in rows if r["ticker"] in self.cfg.tickers]

    def _exposure(self) -> float:
        total = 0.0
        for p in self._positions():
            price = self.prices.get(p["ticker"], float(p["avg_price"]))
            total += float(price) * int(p["qty"])
        return total

    def _safe_exposure(self) -> float:
        try:
            return self._exposure()
        except BrokerError:
            return 0.0

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
            equity = self._equity()
            self.day_start_equity = (
                equity if equity > 0 else (self.day_start_equity or self.cfg.start_equity)
            )
            if isinstance(self.broker, PaperBroker):
                self.broker.update_day(now, self.day_start_equity)
            self._save_state()

        if self.cfg.live_broker:
            shorts = [p for p in self._positions() if int(p["qty"]) < 0]
            if shorts:
                self.last_error = "negative position detected; entries halted: " + ",".join(
                    f"{p['ticker']} {p['qty']}" for p in shorts
                )
                log.error(self.last_error)
                return []

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
            if self.cfg.strategy == "orb":
                signal = evaluate_orb(ticker, candles, pos, self.cfg)
            elif self.cfg.strategy == "ml":
                signal = evaluate_ml(ticker, candles, pos, self.cfg)
            else:
                signal = evaluate(ticker, candles, pos, self.cfg)
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
                    self._save_state()
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
            except (BrokerError, requests.RequestException) as exc:
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
