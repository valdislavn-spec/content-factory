from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from .models import Candle

log = logging.getLogger(__name__)
MSK = timezone(timedelta(hours=3))


class MoexData:
    """Public MOEX ISS candles. No token required; interval=10 is the finest available consistently."""

    def __init__(self, class_code: str = "TQBR", interval: int = 10, timeout: int = 20):
        self.class_code = class_code
        self.interval = interval
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "content-factory-invest-bot/1.0"})

    def candles(self, ticker: str, days: int = 7) -> list[Candle]:
        now = datetime.now(MSK)
        params = {
            "interval": self.interval,
            "from": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
            "till": now.strftime("%Y-%m-%d"),
            "iss.meta": "off",
        }
        url = (
            "https://iss.moex.com/iss/engines/stock/markets/shares/boards/"
            f"{self.class_code}/securities/{ticker}/candles.json"
        )
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json().get("candles", {})
        columns = payload.get("columns", [])
        rows = payload.get("data", [])
        if not columns:
            return []
        index = {name: i for i, name in enumerate(columns)}
        result: list[Candle] = []
        for row in rows:
            try:
                result.append(
                    Candle(
                        ts=datetime.fromisoformat(str(row[index["begin"]])).replace(tzinfo=MSK),
                        open=float(row[index["open"]]),
                        high=float(row[index["high"]]),
                        low=float(row[index["low"]]),
                        close=float(row[index["close"]]),
                        volume=float(row[index["volume"]]),
                    )
                )
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                log.warning("MOEX bad candle %s: %s", ticker, exc)
        return result
