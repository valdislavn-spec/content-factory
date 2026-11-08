"""Twelve Data: рыночные данные для контент-завода (крипто/финтех/спорт).

Официальный Python-клиент: https://github.com/twelvedata/twelvedata-python
Здесь — тонкая обёртка над REST API без внешних зависимостей, чтобы не тянуть
`requests`/`pandas` в прод и в CI. Если нужен полный клиент (WebSocket,
технические индикаторы, fundamentals) — можно поставить `pip install twelvedata`
и использовать `TDClient` напрямую; этот модуль покрывает то, что нужно заводу.

API:
    GET https://api.twelvedata.com/quote?symbol=BTC/USD&apikey=...
    GET https://api.twelvedata.com/price?symbol=BTC/USD&apikey=...
    GET https://api.twelvedata.com/time_series?symbol=BTC/USD&interval=1h&outputsize=24&apikey=...
    GET https://api.twelvedata.com/exchange_rate?symbol=EUR/USD&apikey=...

Ключ: https://twelvedata.com/pricing → бесплатный план (800 кредитов/день,
8 запросов/минуту). В .env: TWELVEDATA_API_KEY.

Типовое использование:
    from content_factory.integrations.twelvedata import TwelveDataClient, format_snapshot
    client = TwelveDataClient()
    quotes = client.quotes(["BTC/USD", "ETH/USD"])
    print(format_snapshot(quotes))
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.twelvedata.com"
DEFAULT_TIMEOUT = 20.0
DEFAULT_CRYPTO_SYMBOLS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD")

# эмодзи/подписи для снапшота (по базовой валюте)
_SYMBOL_STYLE = {
    "BTC": ("₿", "BTC"),
    "ETH": ("Ξ", "ETH"),
    "SOL": ("◎", "SOL"),
    "XRP": ("✕", "XRP"),
    "BNB": ("BNB", "BNB"),
    "DOGE": ("Ð", "DOGE"),
    "ADA": ("₳", "ADA"),
    "AVAX": ("A", "AVAX"),
    "LINK": ("⬡", "LINK"),
    "EUR": ("€", "EUR"),
    "GBP": ("£", "GBP"),
    "USD": ("$", "USD"),
    "SPX": ("S&P", "SPX"),
}


class TwelveDataError(RuntimeError):
    """Ошибка API Twelve Data (сеть, HTTP-статус, error в JSON)."""


class TwelveDataClient:
    """Минимальный клиент REST API Twelve Data."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = (api_key or os.environ.get("TWELVEDATA_API_KEY", "") or "").strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = float(timeout)

    # ------------------------------------------------------------------
    # низкий уровень
    # ------------------------------------------------------------------
    def _request(self, endpoint: str, **params: Any) -> Any:
        if not self.api_key:
            raise TwelveDataError(
                "TWELVEDATA_API_KEY не задан (бесплатный ключ: https://twelvedata.com/pricing)"
            )
        query = {"apikey": self.api_key}
        for key, value in params.items():
            if value is None:
                continue
            query[key] = str(value)
        url = "{}/{}?{}".format(self.base_url, endpoint.lstrip("/"), urllib.parse.urlencode(query))
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "ContentFactory/1.0 (+twelvedata)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                detail = ""
            raise TwelveDataError("Twelve Data HTTP {}: {}".format(exc.code, detail)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TwelveDataError("Twelve Data недоступен: {}".format(exc)) from exc
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise TwelveDataError("Twelve Data вернул не JSON") from exc
        if isinstance(data, dict) and data.get("status") == "error":
            raise TwelveDataError(
                "Twelve Data: {} (code {})".format(
                    data.get("message") or "unknown error", data.get("code")
                )
            )
        return data

    # ------------------------------------------------------------------
    # данные
    # ------------------------------------------------------------------
    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def quote(self, symbol: str) -> Dict[str, Any]:
        """Нормализованная котировка: цена, изменение, %, биржа, время."""
        data = self._request("quote", symbol=symbol)
        if not isinstance(data, dict):
            raise TwelveDataError("Twelve Data quote: неожиданный ответ")
        return {
            "symbol": data.get("symbol") or symbol,
            "name": data.get("name") or "",
            "exchange": data.get("exchange") or "",
            "currency": data.get("currency") or "",
            "price": self._to_float(data.get("close")),
            "previous_close": self._to_float(data.get("previous_close")),
            "change": self._to_float(data.get("change")),
            "percent_change": self._to_float(data.get("percent_change")),
            "is_market_open": bool(data.get("is_market_open", False)),
            "timestamp": data.get("timestamp"),
            "datetime": data.get("datetime") or "",
        }

    def price(self, symbol: str) -> Optional[float]:
        """Текущая цена символа (без метаданных)."""
        data = self._request("price", symbol=symbol)
        if isinstance(data, dict):
            return self._to_float(data.get("price"))
        return None

    def time_series(
        self, symbol: str, interval: str = "1h", outputsize: int = 24
    ) -> List[Dict[str, Any]]:
        """Свечи: список {datetime, open, high, low, close, volume} (новые сверху)."""
        data = self._request(
            "time_series", symbol=symbol, interval=interval, outputsize=outputsize
        )
        values = (data or {}).get("values") or []
        candles: List[Dict[str, Any]] = []
        for row in values:
            candles.append(
                {
                    "datetime": row.get("datetime"),
                    "open": self._to_float(row.get("open")),
                    "high": self._to_float(row.get("high")),
                    "low": self._to_float(row.get("low")),
                    "close": self._to_float(row.get("close")),
                    "volume": self._to_float(row.get("volume")),
                }
            )
        return candles

    def exchange_rate(self, symbol: str) -> Optional[float]:
        """Курс валютной пары (EUR/USD и т.п.)."""
        data = self._request("exchange_rate", symbol=symbol)
        if isinstance(data, dict):
            return self._to_float(data.get("rate"))
        return None

    def quotes(self, symbols: Iterable[str]) -> List[Dict[str, Any]]:
        """Пачка котировок; ошибки по отдельным символам складываются в error."""
        result: List[Dict[str, Any]] = []
        for symbol in symbols:
            try:
                result.append(self.quote(symbol))
            except TwelveDataError as exc:
                logger.warning("Twelve Data: %s: %s", symbol, exc)
                result.append({"symbol": symbol, "error": str(exc)})
        return result


# ----------------------------------------------------------------------
# форматирование для постов
# ----------------------------------------------------------------------
def _fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value >= 1000:
        return "{:,.2f}".format(value).replace(",", " ")
    if value >= 1:
        return "{:,.2f}".format(value)
    return "{:.6f}".format(value)


def _fmt_change(percent: Optional[float]) -> str:
    if percent is None:
        return ""
    sign = "+" if percent >= 0 else "−"
    return " ({}{:.2f}%)".format(sign, abs(percent))


def format_snapshot(quotes: Iterable[Dict[str, Any]], max_items: int = 4) -> str:
    """Строка для поста: ``₿ BTC $75 625.00 (−5.99%) · Ξ ETH $2 225.00 (−7.96%)``."""
    parts: List[str] = []
    for quote in quotes:
        if len(parts) >= max_items:
            break
        if quote.get("error") or quote.get("price") is None:
            continue
        symbol = str(quote.get("symbol") or "")
        base = symbol.split("/")[0].upper()
        emoji, label = _SYMBOL_STYLE.get(base, ("•", base or symbol))
        parts.append(
            "{} {} {}{}".format(
                emoji, label, _fmt_price(quote.get("price")), _fmt_change(quote.get("percent_change"))
            )
        )
    return " · ".join(parts)


def build_market_note(
    symbols: Iterable[str] = DEFAULT_CRYPTO_SYMBOLS,
    *,
    client: Optional[TwelveDataClient] = None,
    prefix: str = "Markets:",
) -> str:
    """Готовая строка «Markets: …» для поста (или пустая строка, если данных нет)."""
    client = client or TwelveDataClient()
    snapshot = format_snapshot(client.quotes(symbols))
    if not snapshot:
        return ""
    return "{} {}".format(prefix, snapshot)
