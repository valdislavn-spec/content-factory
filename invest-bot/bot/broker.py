from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)
MSK = timezone(timedelta(hours=3))


class BrokerError(RuntimeError):
    pass


def _money(value) -> float:
    """Tinkoff money: {'currency':'rub','units':'123','nano':450000000}."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        units = value.get("units", 0) or 0
        nano = value.get("nano", 0) or 0
        return float(units) + float(nano) / 1e9
    return 0.0


class PaperBroker:
    """SQLite-backed paper account. Safe default: never touches a broker."""

    def __init__(self, state_path: str, start_equity: float, fee: float = 0.0005):
        self.state_path = state_path
        self.fee = fee
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(state_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cash REAL NOT NULL,
                start_equity REAL NOT NULL,
                day TEXT,
                day_start_equity REAL
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT PRIMARY KEY,
                qty INTEGER NOT NULL,
                avg_price REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL,
                qty INTEGER NOT NULL,
                price REAL NOT NULL,
                fee REAL NOT NULL,
                pnl REAL NOT NULL DEFAULT 0,
                reason TEXT
            );
            """
        )
        if self.conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0:
            self.conn.execute(
                "INSERT INTO account(id,cash,start_equity,day,day_start_equity) VALUES(1,?,?,?,?)",
                (start_equity, start_equity, None, start_equity),
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _account(self) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM account WHERE id=1").fetchone()

    def cash(self) -> float:
        return float(self._account()["cash"])

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash()
        for row in self.conn.execute("SELECT ticker,qty,avg_price FROM positions").fetchall():
            price = float(prices.get(row["ticker"], row["avg_price"]))
            total += int(row["qty"]) * price
        return total

    def position(self, ticker: str) -> dict | None:
        row = self.conn.execute(
            "SELECT ticker,qty,avg_price FROM positions WHERE ticker=?", (ticker,)
        ).fetchone()
        return dict(row) if row else None

    def positions(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT ticker,qty,avg_price FROM positions")]

    def update_day(self, when: datetime, equity: float) -> None:
        day = when.astimezone(MSK).date().isoformat()
        with self._lock:
            acct = self._account()
            if acct["day"] != day:
                self.conn.execute(
                    "UPDATE account SET day=?, day_start_equity=? WHERE id=1", (day, equity)
                )
                self.conn.commit()

    def day_start_equity(self, fallback: float) -> float:
        v = self._account()["day_start_equity"]
        return float(v) if v is not None else float(fallback)

    def buy(self, ticker: str, price: float, budget: float, reason: str, ts: datetime) -> dict | None:
        if price <= 0 or budget <= 0:
            return None
        qty = int(budget // (price * (1 + self.fee)))
        if qty < 1:
            return None
        with self._lock:
            cash = self.cash()
            cost = qty * price
            fee = cost * self.fee
            if cost + fee > cash + 1e-9:
                qty = int(cash // (price * (1 + self.fee)))
                if qty < 1:
                    return None
                cost = qty * price
                fee = cost * self.fee
            existing = self.conn.execute(
                "SELECT qty,avg_price FROM positions WHERE ticker=?", (ticker,)
            ).fetchone()
            if existing:
                new_qty = int(existing["qty"]) + qty
                avg = (int(existing["qty"]) * float(existing["avg_price"]) + qty * price) / new_qty
                self.conn.execute(
                    "UPDATE positions SET qty=?,avg_price=? WHERE ticker=?", (new_qty, avg, ticker)
                )
            else:
                self.conn.execute(
                    "INSERT INTO positions(ticker,qty,avg_price) VALUES(?,?,?)", (ticker, qty, price)
                )
            self.conn.execute(
                "UPDATE account SET cash=cash-? WHERE id=1", (cost + fee,)
            )
            self.conn.execute(
                "INSERT INTO trades(ts,ticker,side,qty,price,fee,pnl,reason) VALUES(?,?,?,?,?,?,?,?)",
                (ts.astimezone(MSK).isoformat(), ticker, "BUY", qty, price, fee, 0.0, reason),
            )
            self.conn.commit()
        return {"ticker": ticker, "side": "BUY", "qty": qty, "price": price, "fee": fee}

    def sell(self, ticker: str, price: float, reason: str, ts: datetime) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT qty,avg_price FROM positions WHERE ticker=?", (ticker,)
            ).fetchone()
            if not row or price <= 0:
                return None
            qty = int(row["qty"])
            proceeds = qty * price
            fee = proceeds * self.fee
            pnl = (price - float(row["avg_price"])) * qty - fee
            self.conn.execute("DELETE FROM positions WHERE ticker=?", (ticker,))
            self.conn.execute("UPDATE account SET cash=cash+? WHERE id=1", (proceeds - fee,))
            self.conn.execute(
                "INSERT INTO trades(ts,ticker,side,qty,price,fee,pnl,reason) VALUES(?,?,?,?,?,?,?,?)",
                (ts.astimezone(MSK).isoformat(), ticker, "SELL", qty, price, fee, pnl, reason),
            )
            self.conn.commit()
        return {"ticker": ticker, "side": "SELL", "qty": qty, "price": price, "fee": fee, "pnl": pnl}

    def trades(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts,ticker,side,qty,price,fee,pnl,reason FROM trades ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def reset(self, equity: float) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM positions; DELETE FROM trades;")
            self.conn.execute(
                "UPDATE account SET cash=?, start_equity=?, day_start_equity=? WHERE id=1",
                (equity, equity, equity),
            )
            self.conn.commit()


class TinkoffBroker:
    """Tinkoff Invest REST gateway: sandbox by default, prod only behind an explicit allow flag."""

    SANDBOX = "https://sandbox-invest-public-api.tinkoff.ru/rest"
    PROD = "https://invest-public-api.tinkoff.ru/rest"
    PREFIX = "/tinkoff.public.invest.api.contract.v1."

    def __init__(self, token: str, mode: str, class_code: str = "TQBR",
                 sandbox_topup: float = 100_000.0, timeout: int = 20):
        if mode not in {"sandbox", "prod"}:
            raise ValueError("TinkoffBroker mode must be sandbox or prod")
        self.token = token
        self.mode = mode
        self.class_code = class_code
        self.sandbox_topup = sandbox_topup
        self.timeout = timeout
        self.base = self.SANDBOX if mode == "sandbox" else self.PROD
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "content-factory-invest-bot/1.0",
            }
        )
        self.account_id = ""
        self._instruments: dict[str, dict] = {}
        self._ticker_by_figi: dict[str, str] = {}
        self.trade_log = Path(os.getenv("TRADE_LOG", "/tmp/invest-bot/trades.jsonl"))
        self.trade_log.parent.mkdir(parents=True, exist_ok=True)

    def _post(self, service: str, method: str, payload: dict) -> dict:
        url = f"{self.base}{self.PREFIX}{service}/{method}"
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400:
            detail = data.get("message") or data.get("description") or resp.text[:300]
            raise BrokerError(f"{service}/{method}: HTTP {resp.status_code}: {detail}")
        return data

    def connect(self) -> str:
        if self.mode == "sandbox":
            data = self._post("SandboxService", "GetSandboxAccounts", {})
            accounts = data.get("accounts", [])
            if accounts:
                self.account_id = accounts[0]["id"]
            else:
                created = self._post("SandboxService", "OpenSandboxAccount", {})
                self.account_id = created.get("accountId", "")
            if not self.account_id:
                raise BrokerError("could not create/find sandbox account")
            if self.sandbox_topup > 0:
                portfolio = self._post("OperationsService", "GetPortfolio", {"accountId": self.account_id})
                equity = _money(portfolio.get("totalAmountPortfolio"))
                if equity < self.sandbox_topup * 0.5:
                    self._post("SandboxService", "SandboxPayIn", {
                        "accountId": self.account_id,
                        "amount": {"currency": "rub", "units": str(int(self.sandbox_topup)), "nano": 0},
                    })
        else:
            data = self._post("UsersService", "GetAccounts", {})
            accounts = data.get("accounts", [])
            if not accounts:
                raise BrokerError("no Tinkoff accounts available")
            self.account_id = accounts[0]["id"]
        log.info("Tinkoff %s connected: account=%s", self.mode, self.account_id[:4] + "***")
        return self.account_id

    def instrument(self, ticker: str) -> dict:
        if ticker in self._instruments:
            return self._instruments[ticker]
        data = self._post("InstrumentsService", "ShareBy", {
            "idType": "INSTRUMENT_ID_TYPE_TICKER",
            "classCode": self.class_code,
            "id": ticker,
        })
        inst = data.get("instrument") or {}
        if not inst.get("figi"):
            raise BrokerError(f"instrument not found: {ticker}")
        info = {"figi": inst["figi"], "lot": int(inst.get("lot", 1) or 1), "ticker": ticker}
        self._instruments[ticker] = info
        self._ticker_by_figi[info["figi"]] = ticker
        return info

    def candles(self, ticker: str, days: int = 7) -> list:
        from .models import Candle

        info = self.instrument(ticker)
        now = datetime.now(timezone.utc)
        data = self._post("MarketDataService", "GetCandles", {
            "figi": info["figi"],
            "from": (now - timedelta(days=days)).isoformat().replace("+00:00", "Z"),
            "to": now.isoformat().replace("+00:00", "Z"),
            "interval": "CANDLE_INTERVAL_10_MIN",
        })
        out = []
        for c in data.get("candles", []):
            try:
                ts = datetime.fromisoformat(c["time"].replace("Z", "+00:00")).astimezone(MSK)
                out.append(Candle(
                    ts=ts, open=_money(c["open"]), high=_money(c["high"]),
                    low=_money(c["low"]), close=_money(c["close"]),
                    volume=float(c.get("volume", 0) or 0),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("Tinkoff bad candle %s: %s", ticker, exc)
        return out

    def _last_price(self, ticker: str) -> float:
        info = self.instrument(ticker)
        data = self._post("MarketDataService", "GetLastPrices", {"figi": [info["figi"]]})
        for item in data.get("lastPrices", []):
            if item.get("figi") == info["figi"]:
                return _money(item.get("price"))
        raise BrokerError(f"no last price for {ticker}")

    def equity(self) -> float:
        data = self._post("OperationsService", "GetPortfolio", {"accountId": self.account_id})
        total = _money(data.get("totalAmountPortfolio"))
        if total > 0:
            return total
        total = 0.0
        for pos in data.get("positions", []):
            qty = _money(pos.get("quantity"))
            if pos.get("instrumentType") == "currency":
                total += qty
            else:
                total += qty * _money(pos.get("currentPrice"))
        return total

    def positions(self) -> list[dict]:
        data = self._post("OperationsService", "GetPortfolio", {"accountId": self.account_id})
        out = []
        for pos in data.get("positions", []):
            figi = pos.get("figi") or ""
            ticker = self._ticker_by_figi.get(figi) or pos.get("ticker") or figi
            qty = int(_money(pos.get("quantity")))
            if qty:
                out.append({"ticker": ticker, "qty": qty, "avg_price": _money(pos.get("averagePositionPrice"))})
        return out

    def _log(self, rec: dict) -> None:
        rec = {"ts": datetime.now(MSK).isoformat(), **rec}
        with self.trade_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _wait_order(self, order_id: str, initial_status: str = "") -> str:
        if "FILL" in initial_status:
            return initial_status
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                data = self._post("OrdersService", "GetOrderState", {
                    "accountId": self.account_id, "orderId": order_id,
                })
            except BrokerError as exc:
                # Some sandbox deployments answer 404 for an order that already filled;
                # do not turn a filled order into a runtime failure.
                if "404" in str(exc):
                    return initial_status or "SUBMITTED"
                raise
            status = data.get("executionReportStatus", "")
            if "FILL" in status:
                return status
            if status in {
                "ORDER_EXECUTION_REPORT_STATUS_REJECTED",
                "ORDER_EXECUTION_REPORT_STATUS_CANCELLED",
            }:
                raise BrokerError(f"order {order_id} {status}")
            time.sleep(2)
        raise BrokerError(f"order {order_id} not filled in time")

    def buy(self, ticker: str, price: float, budget: float, reason: str, ts: datetime) -> dict | None:
        info = self.instrument(ticker)
        lots = int(budget // (price * info["lot"] * 1.001))
        if lots < 1:
            return None
        data = self._post("OrdersService", "PostOrder", {
            "accountId": self.account_id,
            "instrumentId": info["figi"],
            "quantity": str(lots),
            "direction": "ORDER_DIRECTION_BUY",
            "orderType": "ORDER_TYPE_MARKET",
            "orderId": str(uuid.uuid4()),
        })
        order_id = data.get("orderId", "")
        if not order_id:
            raise BrokerError(f"no orderId: {data}")
        self._wait_order(order_id, data.get("executionReportStatus", ""))
        rec = {"ticker": ticker, "side": "BUY", "lots": lots, "price": price, "reason": reason}
        self._log(rec)
        return rec

    def sell(self, ticker: str, price: float, reason: str, ts: datetime) -> dict | None:
        info = self.instrument(ticker)
        held = next((p for p in self.positions() if p["ticker"] == ticker), None)
        if not held:
            return None
        # Tinkoff portfolio quantity for shares is already expressed in lots.
        lots = int(held["qty"])
        if lots < 1:
            return None
        data = self._post("OrdersService", "PostOrder", {
            "accountId": self.account_id,
            "instrumentId": info["figi"],
            "quantity": str(lots),
            "direction": "ORDER_DIRECTION_SELL",
            "orderType": "ORDER_TYPE_MARKET",
            "orderId": str(uuid.uuid4()),
        })
        order_id = data.get("orderId", "")
        if not order_id:
            raise BrokerError(f"no orderId: {data}")
        self._wait_order(order_id, data.get("executionReportStatus", ""))
        rec = {"ticker": ticker, "side": "SELL", "lots": lots, "price": price, "reason": reason}
        self._log(rec)
        return rec

    def trades(self, limit: int = 50) -> list[dict]:
        if not self.trade_log.exists():
            return []
        lines = self.trade_log.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out
