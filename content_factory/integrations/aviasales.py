"""Aviasales data API (Travelpayouts) — cheap flight prices.

Docs: https://support.travelpayouts.com (API данных Aviasales).
Auth: X-Access-Token (Travelpayouts API token, profile → API token).

Endpoints used:
    GET /v1/city-directions?origin=MOW&currency=rub          — cheapest round trips
    GET /aviasales/v3/prices_for_dates?origin=&destination= — cheapest one-way for a date
    GET /aviasales/v3/grouped_prices?origin=&destination=   — daily cheapest for a month

Monetization: each search `link` is turned into a Travelpayouts partner link
(short tpk.ro) via the links API, marker + sub_id per destination.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

BASE_URL = "https://api.travelpayouts.com"
AVIASALES_SEARCH = "https://www.aviasales.ru"
USER_AGENT = "content-factory-aviasales/1.0"


class AviasalesError(RuntimeError):
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class AviasalesClient:
    token: str
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "AviasalesClient":
        return cls(token=env("TRAVELPAYOUTS_TOKEN") or env("AVIASALES_TOKEN"))

    def configured(self) -> bool:
        return bool(self.token)

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured():
            raise AviasalesError("TRAVELPAYOUTS_TOKEN is not set")
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            self.base_url + path + "?" + query,
            headers={"X-Access-Token": self.token, "Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            raise AviasalesError("HTTP %s: %s" % (error.code, error.read()[:200])) from error
        except Exception as error:  # noqa: BLE001
            raise AviasalesError("%s: %s" % (type(error).__name__, error)) from error
        if not payload.get("success", True):
            raise AviasalesError(str(payload.get("error") or payload)[:300])
        return payload

    base_url: str = BASE_URL

    def city_directions(self, origin: str = "MOW", currency: str = "rub") -> List[Dict[str, Any]]:
        data = self._get("/v1/city-directions", {"origin": origin.upper(), "currency": currency})
        rows = data.get("data") or {}
        if isinstance(rows, dict):
            rows = list(rows.values())
        return [dict(row) for row in rows]

    def prices_for_dates(
        self,
        origin: str,
        destination: str,
        departure_at: str,
        currency: str = "rub",
        one_way: bool = True,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        data = self._get("/aviasales/v3/prices_for_dates", {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_at": departure_at,
            "unique": "false",
            "sorting": "price",
            "direct": "false",
            "currency": currency,
            "limit": limit,
            "page": 1,
            "one_way": "true" if one_way else "false",
        })
        return list(data.get("data") or [])

    def grouped_prices(self, origin: str, destination: str, month: str, currency: str = "rub") -> Dict[str, Any]:
        data = self._get("/aviasales/v3/grouped_prices", {
            "origin": origin.upper(), "destination": destination.upper(),
            "departure_at": month, "currency": currency,
        })
        return dict(data.get("data") or {})


def search_path(link: str) -> str:
    """Turn an API `link` value into an absolute aviasales.ru search URL."""
    link = str(link or "").strip()
    if link.startswith("http"):
        return link
    if link.startswith("/"):
        return AVIASALES_SEARCH + link
    return AVIASALES_SEARCH + "/" + link
