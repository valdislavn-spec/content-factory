"""Kalshi prediction-markets integration.

Public market data needs no authentication (Kalshi docs, 2026-11):
    GET https://external-api.kalshi.com/trade-api/v2/markets

Authenticated endpoints (portfolio/orders) need an API key. Each request is
signed over ``timestamp + METHOD + path`` (query string excluded) and sent as:

    KALSHI-ACCESS-KEY        key id
    KALSHI-ACCESS-TIMESTAMP  ms since epoch
    KALSHI-ACCESS-SIGNATURE  base64 signature (Ed25519 or RSA-PSS/SHA-256)

Uses the standard library only; signed requests need the optional
``cryptography`` package.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

PUBLIC_BASE = "https://external-api.kalshi.com"
DEMO_BASE = "https://external-api.demo.kalshi.co"
TRADE_API = "/trade-api/v2"
USER_AGENT = "content-factory-kalshi/1.0 (+https://github.com/valdislavn-spec/content-factory)"


class KalshiError(RuntimeError):
    """Kalshi API/network error."""


def fetch_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 20.0) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise KalshiError("HTTP %s: %s" % (error.code, detail)) from error
    except Exception as error:  # noqa: BLE001 - network failures become KalshiError
        raise KalshiError("%s: %s" % (type(error).__name__, error)) from error


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def yes_price_cents(market: Dict[str, Any]) -> Optional[int]:
    """YES price in cents from new dollar fields or legacy cent fields."""
    for key in ("yes_bid_dollars", "last_price_dollars", "yes_ask_dollars"):
        value = market.get(key)
        if value not in (None, ""):
            return int(round(_as_float(value) * 100))
    for key in ("yes_bid", "last_price", "yes_ask"):
        value = market.get(key)
        if value not in (None, ""):
            return int(round(_as_float(value)))
    return None


def market_volume(market: Dict[str, Any]) -> float:
    for key in ("volume_24h_fp", "volume_24h", "volume_fp", "volume"):
        value = market.get(key)
        if value not in (None, ""):
            return _as_float(value)
    return 0.0


def close_date(market: Dict[str, Any]) -> str:
    raw = str(market.get("close_time") or market.get("expiration_time") or "")
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%d %b")
    except ValueError:
        return raw[:10]


def market_url(market: Dict[str, Any]) -> str:
    series = str(market.get("series_ticker") or "").strip().lower()
    return "https://kalshi.com/markets/%s" % series if series else "https://kalshi.com/markets"


def select_markets(
    markets: Iterable[Dict[str, Any]],
    keywords: Sequence[str] = (),
    min_volume: float = 0.0,
    max_items: int = 4,
) -> List[Dict[str, Any]]:
    """Filter by keywords/volume and return the most liquid markets first."""
    needles = [str(word).strip().lower() for word in keywords if str(word).strip()]
    selected: List[Dict[str, Any]] = []
    for market in markets:
        title = str(market.get("title") or market.get("yes_sub_title") or "")
        haystack = (title + " " + str(market.get("ticker") or "")).lower()
        if needles and not any(word in haystack for word in needles):
            continue
        if market_volume(market) < min_volume:
            continue
        if not title:
            continue
        selected.append(market)
    selected.sort(key=market_volume, reverse=True)
    return selected[: max(0, int(max_items))]


FOOTERS = {
    "en": "Prediction-market odds via Kalshi. Not investment advice.",
    "es": "Cuotas de mercados de predicción vía Kalshi. No es consejo de inversión.",
}


def build_digest(
    markets: Sequence[Dict[str, Any]],
    title: str,
    language: str = "en",
    max_items: int = 4,
    affiliate_url: str = "",
) -> str:
    """Render a compact Telegram post with the most liquid markets."""
    lines = [str(title).strip()]
    for market in markets[:max_items]:
        price = yes_price_cents(market)
        volume = market_volume(market)
        close = close_date(market)
        question = str(market.get("title") or market.get("yes_sub_title") or "").strip()
        if len(question) > 140:
            question = question[:137].rstrip() + "…"
        parts = []
        if price is not None:
            parts.append("YES %d¢" % price)
        if volume:
            parts.append("vol %s" % ("{:,.0f}".format(volume)))
        if close:
            parts.append("closes %s" % close)
        lines.append("• %s — %s" % (question, " · ".join(parts)))
    footer = FOOTERS.get(str(language).lower(), FOOTERS["en"])
    footer += "\nAd · " + affiliate_url if affiliate_url else "\nhttps://kalshi.com/markets"
    lines.extend(["", footer])
    return "\n".join(lines)


class KalshiClient:
    """Minimal Kalshi REST client (public data, optional signed requests)."""

    def __init__(
        self,
        base_url: str = PUBLIC_BASE,
        key_id: str = "",
        private_key_pem: str = "",
        timeout: float = 20.0,
        fetcher=fetch_json,
    ) -> None:
        self.base_url = (base_url or PUBLIC_BASE).rstrip("/")
        self.key_id = (key_id or "").strip()
        self.private_key_pem = private_key_pem or ""
        self.timeout = timeout
        self._fetch = fetcher
        self._private_key = None

    def _load_private_key(self):
        if self._private_key is None:
            try:
                from cryptography.hazmat.primitives import serialization
            except ImportError as error:  # pragma: no cover - optional dependency
                raise KalshiError("cryptography is required for signed requests") from error
            self._private_key = serialization.load_pem_private_key(
                self.private_key_pem.encode("utf-8"), password=None
            )
        return self._private_key

    def sign(self, timestamp_ms: str, method: str, path: str) -> str:
        """Base64 signature over ``timestamp + METHOD + path`` (no query)."""
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError as error:  # pragma: no cover - optional dependency
            raise KalshiError("cryptography is required for signed requests") from error
        message = ("%s%s%s" % (timestamp_ms, method.upper(), path.split("?")[0])).encode("utf-8")
        key = self._load_private_key()
        if isinstance(key, Ed25519PrivateKey):
            signature = key.sign(message)
        else:
            signature = key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH,
                ),
                hashes.SHA256(),
            )
        return base64.b64encode(signature).decode("ascii")

    def _signed_headers(self, method: str, path: str) -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": self.sign(timestamp, method, path),
        }

    def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        headers = self._signed_headers(method, path) if self.key_id else {}
        return self._fetch(url, headers, self.timeout)

    def markets(
        self,
        status: str = "open",
        limit: int = 200,
        series_ticker: str = "",
        mve_filter: str = "exclude",
    ) -> List[Dict[str, Any]]:
        """Open markets. ``mve_filter="exclude"`` hides multivariate (parlay) markets."""
        data = self.request(
            "GET",
            TRADE_API + "/markets",
            {
                "status": status,
                "limit": limit,
                "series_ticker": series_ticker or None,
                "mve_filter": mve_filter or None,
            },
        )
        return list(data.get("markets") or [])

    def series(self, ticker: str) -> Dict[str, Any]:
        return (self.request("GET", TRADE_API + "/series/" + ticker) or {}).get("series") or {}

    def series_list(self, category: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        """Browse series templates, optionally filtered by category."""
        data = self.request(
            "GET",
            TRADE_API + "/series",
            {"category": category or None, "limit": limit},
        )
        return list(data.get("series") or data.get("series_list") or [])

    def event(self, ticker: str) -> Dict[str, Any]:
        return (self.request("GET", TRADE_API + "/events/" + ticker) or {}).get("event") or {}

    def exchange_status(self) -> Dict[str, Any]:
        return self.request("GET", TRADE_API + "/exchange/status")
