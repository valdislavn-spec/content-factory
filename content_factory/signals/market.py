"""Публичные OHLCV-свечи с бирж — без API-ключей.

Поддерживаются биржи, которые «есть» в проекте по партнёркам/аккаунтам:
BingX, Bitget, MEXC, Coinbase, Crypto.com, Kraken.

Интерфейс: ``fetch_candles(exchange, pair, interval, limit) -> list[dict]``
где свеча = ``{"ts": ms, "open", "high", "low", "close", "volume"}``.
Любая ошибка сети/формата по одной бирже не роняет остальные: возвращается [].
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List

LOGGER = logging.getLogger(__name__)

TIMEOUT = 10.0
UA = "Mozilla/5.0 (compatible; content-factory-signals/1.0)"

# Символы по биржам (USDT-пары; где нет USDT — USD).
_SYMBOLS: Dict[str, Dict[str, str]] = {
    "bingx": {"BTC/USDT": "BTC-USDT", "ETH/USDT": "ETH-USDT", "SOL/USDT": "SOL-USDT"},
    "bitget": {"BTC/USDT": "BTCUSDT", "ETH/USDT": "ETHUSDT", "SOL/USDT": "SOLUSDT"},
    "mexc": {"BTC/USDT": "BTCUSDT", "ETH/USDT": "ETHUSDT", "SOL/USDT": "SOLUSDT"},
    "coinbase": {"BTC/USDT": "BTC-USD", "ETH/USDT": "ETH-USD", "SOL/USDT": "SOL-USD"},
    "cryptocom": {"BTC/USDT": "BTC_USDT", "ETH/USDT": "ETH_USDT", "SOL/USDT": "SOL_USDT"},
    "kraken": {"BTC/USDT": "XBTUSDT", "ETH/USDT": "ETHUSDT", "SOL/USDT": "SOLUSDT"},
}

# Интервалы по биржам: наш код -> нативный формат.
_INTERVALS: Dict[str, Dict[str, str]] = {
    "bingx": {"15m": "15m", "1h": "1h"},
    "bitget": {"15m": "15min", "1h": "1h"},
    "mexc": {"15m": "15m", "1h": "60m"},
    "coinbase": {"15m": "900", "1h": "3600"},
    "cryptocom": {"15m": "M15", "1h": "H1"},
    "kraken": {"15m": "15", "1h": "60"},
}


def _http_json(url: str, params: Dict[str, object] | None = None, timeout: float = TIMEOUT):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _candle(ts, open_, high, low, close, volume) -> Dict[str, float]:
    return {
        "ts": int(float(ts)),
        "open": float(open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume),
    }


def _norm(candles: List[Dict[str, float]]) -> List[Dict[str, float]]:
    return sorted(candles, key=lambda item: item["ts"])


def fetch_bingx(pair: str, interval: str, limit: int) -> List[Dict[str, float]]:
    symbol = _SYMBOLS["bingx"].get(pair)
    if not symbol:
        return []
    data = _http_json(
        "https://open-api.bingx.com/openApi/swap/v2/quote/klines",
        {"symbol": symbol, "interval": _INTERVALS["bingx"][interval], "limit": limit},
    )
    return _norm([_candle(c["time"], c["open"], c["high"], c["low"], c["close"], c["volume"]) for c in data.get("data") or []])


def fetch_bitget(pair: str, interval: str, limit: int) -> List[Dict[str, float]]:
    symbol = _SYMBOLS["bitget"].get(pair)
    if not symbol:
        return []
    data = _http_json(
        "https://api.bitget.com/api/v2/spot/market/candles",
        {"symbol": symbol, "granularity": _INTERVALS["bitget"][interval], "limit": limit},
    )
    rows = data.get("data") or []
    return _norm([_candle(row[0], row[1], row[2], row[3], row[4], row[5]) for row in rows])


def fetch_mexc(pair: str, interval: str, limit: int) -> List[Dict[str, float]]:
    symbol = _SYMBOLS["mexc"].get(pair)
    if not symbol:
        return []
    rows = _http_json(
        "https://api.mexc.com/api/v3/klines",
        {"symbol": symbol, "interval": _INTERVALS["mexc"][interval], "limit": limit},
    )
    return _norm([_candle(row[0], row[1], row[2], row[3], row[4], row[5]) for row in rows])


def fetch_coinbase(pair: str, interval: str, limit: int) -> List[Dict[str, float]]:
    symbol = _SYMBOLS["coinbase"].get(pair)
    if not symbol:
        return []
    rows = _http_json(
        "https://api.exchange.coinbase.com/products/%s/candles" % symbol,
        {"granularity": _INTERVALS["coinbase"][interval]},
    )
    # Coinbase: [ts, low, high, open, close, volume], новые сверху.
    return _norm([_candle(row[0], row[3], row[2], row[1], row[4], row[5]) for row in rows])[-limit:]


def fetch_cryptocom(pair: str, interval: str, limit: int) -> List[Dict[str, float]]:
    symbol = _SYMBOLS["cryptocom"].get(pair)
    if not symbol:
        return []
    data = _http_json(
        "https://api.crypto.com/exchange/v1/public/get-candlestick",
        {"instrument_name": symbol, "timeframe": _INTERVALS["cryptocom"][interval], "count": limit},
    )
    rows = (data.get("result") or {}).get("data") or []
    return _norm([_candle(row["t"], row["o"], row["h"], row["l"], row["c"], row["v"]) for row in rows])


def fetch_kraken(pair: str, interval: str, limit: int) -> List[Dict[str, float]]:
    symbol = _SYMBOLS["kraken"].get(pair)
    if not symbol:
        return []
    # Kraken из GitHub Actions/ряда сетей отвечает медленно — короткий таймаут,
    # чтобы не тормозить весь запуск сигналов.
    data = _http_json(
        "https://api.kraken.com/0/public/OHLC",
        {"pair": symbol, "interval": _INTERVALS["kraken"][interval]},
        timeout=5.0,
    )
    result = data.get("result") or {}
    rows = next((value for key, value in result.items() if key != "last"), []) or []
    return _norm([_candle(row[0] * 1000, row[1], row[2], row[3], row[4], row[6]) for row in rows])[-limit:]


ADAPTERS = {
    "bingx": fetch_bingx,
    "bitget": fetch_bitget,
    "mexc": fetch_mexc,
    "coinbase": fetch_coinbase,
    "cryptocom": fetch_cryptocom,
    "kraken": fetch_kraken,
}


def available_exchanges() -> List[str]:
    return sorted(ADAPTERS)


def fetch_candles(exchange: str, pair: str, interval: str = "15m", limit: int = 300) -> List[Dict[str, float]]:
    """Свечи одной биржи; [] при любой ошибке (биржу пропускаем)."""
    fetch = ADAPTERS.get(exchange)
    if fetch is None:
        return []
    try:
        candles = fetch(pair, interval, limit)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, KeyError) as exc:
        LOGGER.warning("market: %s %s %s недоступна: %s", exchange, pair, interval, exc)
        return []
    return candles[-limit:]
