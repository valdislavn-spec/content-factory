"""BingX: публичные рыночные данные без API-ключа (котировки, свечи).

Официальный API BingX: https://open-api.bingx.com
GitHub: https://github.com/BingX-API (docs, SDK, AI-skills), см. docs/integrations/bingx.md.

Зачем в заводе:
* бесплатный источник цены BTC/ETH/SOL для рыночного блока в постах
  (не нужен API-ключ, в отличие от Twelve Data);
* альтернатива Twelve Data для крипты; форекс/акции — Twelve Data.

Публичные эндпоинты (проверено 08.11.2026):
    GET /openApi/swap/v2/quote/ticker?symbol=BTC-USDT
    GET /openApi/swap/v2/quote/klines?symbol=BTC-USDT&interval=1h&limit=24
    GET /openApi/spot/v1/ticker/24hr?symbol=BTC-USDT

Формат ответа: {"code":0,"msg":"","data":...}; код != 0 — ошибка.

Использование:
    from content_factory.integrations.bingx import BingXClient
    from content_factory.integrations.twelvedata import format_snapshot
    client = BingXClient()
    print(format_snapshot(client.quotes(["BTC/USDT", "ETH/USDT"])))
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

DEFAULT_BASE_URL = "https://open-api.bingx.com"
DEFAULT_TIMEOUT = 20.0
DEFAULT_SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT")


class BingXError(RuntimeError):
    """Ошибка публичного API BingX."""


def _api_symbol(symbol: str) -> str:
    """``BTC/USDT`` / ``BTC-USDT`` → ``BTC-USDT`` (как у BingX)."""
    return str(symbol or "").strip().upper().replace("/", "-")


def _display_symbol(api_symbol: str) -> str:
    """``BTC-USDT`` → ``BTC/USDT`` (для format_snapshot)."""
    return str(api_symbol or "").strip().upper().replace("-", "/")


class BingXClient:
    """Клиент публичного API BingX (без ключей и подписи)."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or os.environ.get("BINGX_API_BASE", "") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = float(timeout)

    def _request(self, path: str, **params: Any) -> Any:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        url = "{}{}?{}".format(self.base_url, path, query)
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "ContentFactory/1.0 (+bingx)"},
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
            raise BingXError("BingX HTTP {}: {}".format(exc.code, detail)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BingXError("BingX недоступен: {}".format(exc)) from exc
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise BingXError("BingX вернул не JSON") from exc
        if not isinstance(payload, dict):
            raise BingXError("BingX: неожиданный ответ")
        if int(payload.get("code", 0) or 0) != 0:
            raise BingXError("BingX: {} (code {})".format(payload.get("msg"), payload.get("code")))
        return payload.get("data")

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def ticker(self, symbol: str) -> Dict[str, Any]:
        """Котировка фьючерсного контракта (USDT-M): цена и изменение за 24ч."""
        data = self._request(
            "/openApi/swap/v2/quote/ticker", symbol=_api_symbol(symbol)
        )
        if not isinstance(data, dict):
            raise BingXError("BingX ticker: пустой ответ")
        api_symbol = str(data.get("symbol") or _api_symbol(symbol))
        return {
            "symbol": _display_symbol(api_symbol),
            "api_symbol": api_symbol,
            "price": self._to_float(data.get("lastPrice")),
            "percent_change": self._to_float(data.get("priceChangePercent")),
            "change": self._to_float(data.get("priceChange")),
            "high": self._to_float(data.get("highPrice")),
            "low": self._to_float(data.get("lowPrice")),
            "volume": self._to_float(data.get("volume")),
            "source": "bingx",
        }

    def spot_ticker(self, symbol: str) -> Dict[str, Any]:
        """Спотовая котировка за 24 часа (список из одного элемента)."""
        data = self._request(
            "/openApi/spot/v1/ticker/24hr", symbol=_api_symbol(symbol)
        )
        rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        if not rows:
            raise BingXError("BingX spot_ticker: пустой ответ")
        row = rows[0]
        return {
            "symbol": _display_symbol(str(row.get("symbol") or _api_symbol(symbol))),
            "price": self._to_float(row.get("lastPrice")),
            "percent_change": self._to_float(row.get("priceChangePercent")),
            "change": self._to_float(row.get("priceChange")),
            "high": self._to_float(row.get("highPrice")),
            "low": self._to_float(row.get("lowPrice")),
            "volume": self._to_float(row.get("volume")),
            "source": "bingx-spot",
        }

    def klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> List[Dict[str, Any]]:
        """Свечи: [{time, open, high, low, close, volume}] (старые → новые)."""
        data = self._request(
            "/openApi/swap/v2/quote/klines",
            symbol=_api_symbol(symbol),
            interval=interval,
            limit=int(limit),
        )
        rows = data if isinstance(data, list) else []
        candles: List[Dict[str, Any]] = []
        for row in rows:
            candles.append(
                {
                    "time": row.get("time"),
                    "open": self._to_float(row.get("open")),
                    "high": self._to_float(row.get("high")),
                    "low": self._to_float(row.get("low")),
                    "close": self._to_float(row.get("close")),
                    "volume": self._to_float(row.get("volume")),
                }
            )
        return candles

    def quotes(self, symbols: Iterable[str]) -> List[Dict[str, Any]]:
        """Пачка котировок; ошибки по символам складываются в error."""
        result: List[Dict[str, Any]] = []
        for symbol in symbols:
            try:
                result.append(self.ticker(symbol))
            except BingXError as exc:
                logger.warning("BingX: %s: %s", symbol, exc)
                result.append({"symbol": str(symbol), "error": str(exc)})
        return result


def build_market_note(
    symbols: Iterable[str] = DEFAULT_SYMBOLS, *, client: Optional[BingXClient] = None, prefix: str = "Markets:"
) -> str:
    """Готовая строка «Markets: ₿ BTC …» для поста (пустая, если данных нет)."""
    from .twelvedata import format_snapshot

    client = client or BingXClient()
    snapshot = format_snapshot(client.quotes(symbols))
    if not snapshot:
        return ""
    return "{} {}".format(prefix, snapshot)
