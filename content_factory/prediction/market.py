"""Публичные данные прогнозных рынков (без ключей).

Источники:
* Polymarket — Gamma API (`gamma-api.polymarket.com/markets`), есть
  ``oneDayPriceChange``, объём и ликвидность.
* Kalshi — Trade API v2 (`api.elections.kalshi.com`), цены в центах.
  С российских IP отдаёт 403 (Cloudflare); с GitHub-раннеров (US) обычно ок.
* Manifold — ``api.manifold.markets/v0/markets`` (best-effort).
* Metaculus — требует бесплатный API-токен (env ``METACULUS_TOKEN``);
  без токена источник просто пропускается.

Все адаптеры возвращают нормализованные словари:
``{source, id, question, url, probability, delta_24h, volume_24h, liquidity, end_date}``.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List

LOGGER = logging.getLogger(__name__)

TIMEOUT = 15.0
UA = "Mozilla/5.0 (compatible; content-factory-prediction/1.0)"


def _json(url: str, params: Dict[str, object] | None = None, timeout: float = TIMEOUT):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_polymarket(limit: int = 100, pages: int = 3) -> List[dict]:
    """Активные рынки Polymarket с движениями вероятности за 24ч."""
    markets: List[dict] = []
    for page in range(max(1, pages)):
        try:
            data = _json(
                "https://gamma-api.polymarket.com/markets",
                {
                    "closed": "false",
                    "limit": limit,
                    "offset": page * limit,
                    "order": "volume24hr",
                    "ascending": "false",
                },
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            LOGGER.warning("polymarket: страница %d недоступна: %s", page, exc)
            break
        if not isinstance(data, list) or not data:
            break
        markets.extend(data)
    normalized: List[dict] = []
    for market in markets:
        prices = market.get("outcomePrices")
        probability = None
        try:
            if isinstance(prices, str):
                prices = json.loads(prices)
            if isinstance(prices, list) and prices:
                probability = _float(prices[0])
        except (ValueError, TypeError):
            probability = None
        slug = str(market.get("slug") or "")
        normalized.append(
            {
                "source": "polymarket",
                "id": str(market.get("id") or slug),
                "question": str(market.get("question") or ""),
                "url": ("https://polymarket.com/market/" + slug) if slug else "https://polymarket.com",
                "probability": probability,
                "delta_24h": _float(market.get("oneDayPriceChange")),
                "volume_24h": _float(market.get("volume24hr")),
                "liquidity": _float(market.get("liquidityNum") or market.get("liquidity")),
                "end_date": str(market.get("endDate") or ""),
            }
        )
    return normalized


def fetch_kalshi(limit: int = 200) -> List[dict]:
    """Открытые рынки Kalshi (цены в центах → вероятность 0..1)."""
    try:
        data = _json(
            "https://api.elections.kalshi.com/trade-api/v2/markets",
            {"status": "open", "limit": limit},
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        LOGGER.warning("kalshi: недоступен (403 = гео-блок): %s", exc)
        return []
    markets = (data or {}).get("markets") or []
    normalized: List[dict] = []
    for market in markets:
        last = _float(market.get("last_price"))
        previous = _float(market.get("previous_price"))
        probability = (last / 100.0) if last is not None else None
        delta = ((last - previous) / 100.0) if (last is not None and previous is not None) else None
        ticker = str(market.get("ticker") or "")
        normalized.append(
            {
                "source": "kalshi",
                "id": ticker,
                "question": str(market.get("title") or ""),
                "url": ("https://kalshi.com/markets/" + ticker) if ticker else "https://kalshi.com",
                "probability": probability,
                "delta_24h": delta,
                "volume_24h": _float(market.get("volume")),
                "liquidity": _float(market.get("open_interest")),
                "end_date": str(market.get("close_time") or ""),
            }
        )
    return normalized


def fetch_manifold(limit: int = 200) -> List[dict]:
    """Best-effort Manifold: рынки с вероятностью (может быть недоступен из РФ)."""
    try:
        data = _json("https://api.manifold.markets/v0/markets", {"limit": limit})
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        LOGGER.warning("manifold: недоступен: %s", exc)
        return []
    normalized: List[dict] = []
    for market in data or []:
        probability = _float(market.get("probability"))
        url = str(market.get("url") or "")
        normalized.append(
            {
                "source": "manifold",
                "id": str(market.get("id") or ""),
                "question": str(market.get("question") or ""),
                "url": url or "https://manifold.markets",
                "probability": probability,
                "delta_24h": None,
                "volume_24h": _float(market.get("volume24Hours")),
                "liquidity": _float(market.get("totalLiquidity")),
                "end_date": "",
            }
        )
    return normalized


def fetch_metaculus(limit: int = 100) -> List[dict]:
    """Metaculus требует бесплатный API-токен (METACULUS_TOKEN)."""
    token = (os.environ.get("METACULUS_TOKEN") or "").strip()
    if not token:
        return []
    try:
        request = urllib.request.Request(
            "https://www.metaculus.com/api2/questions/?limit=%d" % limit,
            headers={"Authorization": "Token " + token, "User-Agent": UA},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        LOGGER.warning("metaculus: недоступен: %s", exc)
        return []
    results = (data or {}).get("results") or []
    normalized: List[dict] = []
    for question in results:
        normalized.append(
            {
                "source": "metaculus",
                "id": str(question.get("id") or ""),
                "question": str(question.get("title") or ""),
                "url": str(question.get("url") or "https://www.metaculus.com"),
                "probability": None,
                "delta_24h": None,
                "volume_24h": None,
                "liquidity": None,
                "end_date": str(question.get("close_time") or ""),
            }
        )
    return normalized


FETCHERS = {
    "polymarket": fetch_polymarket,
    "kalshi": fetch_kalshi,
    "manifold": fetch_manifold,
    "metaculus": fetch_metaculus,
}


def fetch_markets(config: dict) -> List[dict]:
    markets: List[dict] = []
    for source in config.get("sources") or []:
        fetcher = FETCHERS.get(str(source))
        if not fetcher:
            continue
        try:
            markets.extend(fetcher())
        except Exception as exc:  # noqa: BLE001 - источник не должен ронять остальные
            LOGGER.warning("prediction: источник %s упал: %s", source, exc)
    return markets
