"""Travelata.ru partners API client (package tours).

Docs: support.travelpayouts.com article "API от Travelata" (new API since 2026-06-05).

Base: https://api-gateway.travelata.ru
Auth: HTTP Basic (login/password issued individually by Travelata to Travelpayouts partners)
All paths are prefixed with /partners. Responses: {"success": true, "result": ...}

Endpoints used here:
    GET /partners/directory/countries
    GET /partners/directory/resorts?country[]=92&limit=&offset=
    GET /partners/directory/hotels?resort[]=1
    GET /partners/directory/hotelCategories
    GET /partners/directory/meals
    GET /partners/directory/departureCities
    GET /partners/statistic/cheapestTours
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

BASE_URL = "https://api-gateway.travelata.ru"
USER_AGENT = "content-factory-travelata/1.0"


class TravelataError(RuntimeError):
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class TravelataClient:
    login: str
    password: str
    base_url: str = BASE_URL
    timeout: float = 30.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "TravelataClient":
        return cls(
            login=env("TRAVELATA_LOGIN") or env("TRAVELATA_API_LOGIN"),
            password=env("TRAVELATA_PASSWORD") or env("TRAVELATA_API_PASSWORD"),
        )

    def configured(self) -> bool:
        return bool(self.login and self.password)

    def _auth_header(self) -> str:
        token = base64.b64encode(("%s:%s" % (self.login, self.password)).encode("utf-8")).decode("ascii")
        return "Basic " + token

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.configured():
            raise TravelataError("TRAVELATA_LOGIN / TRAVELATA_PASSWORD are not set")
        query = encode_params(params or {})
        url = self.base_url.rstrip("/") + path + (("?" + query) if query else "")
        request = urllib.request.Request(
            url,
            headers={"Authorization": self._auth_header(), "Accept": "application/json", "User-Agent": USER_AGENT},
        )
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8", "replace"))
                if not payload.get("success", False):
                    error = payload.get("error") or {}
                    message = error.get("message") if isinstance(error, dict) else str(error)
                    raise TravelataError("Travelata API error: %s" % (message or payload)[:300])
                return payload.get("result")
            except urllib.error.HTTPError as error:
                body = error.read()[:300].decode("utf-8", "replace")
                if error.code == 429 and attempt < self.max_retries:
                    wait = 2 + attempt * 2
                    try:
                        wait = max(1, int(error.headers.get("X-RateLimit-Reset") or wait))
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(min(wait, 30))
                    last_error = TravelataError("429 Too Many Requests")
                    continue
                raise TravelataError("HTTP %s: %s" % (error.code, body)) from error
            except Exception as error:  # noqa: BLE001
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(2)
                    continue
                raise TravelataError("%s: %s" % (type(error).__name__, error)) from error
        raise TravelataError(str(last_error or "request failed"))

    # --- directories -----------------------------------------------------
    def countries(self) -> List[Dict[str, Any]]:
        return list(self._request("/partners/directory/countries") or [])

    def resorts(self, country_ids: Optional[Iterable[int]] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if country_ids:
            params["country[]"] = [int(x) for x in country_ids]
        return list(self._request("/partners/directory/resorts", params) or [])

    def hotels(self, resort_ids: Optional[Iterable[int]] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if resort_ids:
            params["resort[]"] = [int(x) for x in resort_ids]
        return list(self._request("/partners/directory/hotels", params) or [])

    def hotel_categories(self) -> List[Dict[str, Any]]:
        return list(self._request("/partners/directory/hotelCategories") or [])

    def meals(self) -> List[Dict[str, Any]]:
        return list(self._request("/partners/directory/meals") or [])

    def departure_cities(self) -> List[Dict[str, Any]]:
        return list(self._request("/partners/directory/departureCities") or [])

    # --- cheapest tours --------------------------------------------------
    def cheapest_tours(
        self,
        countries: Iterable[int],
        departure_city: int,
        adults: int,
        checkin_from: str,
        checkin_to: str,
        nights_from: Optional[int] = None,
        nights_to: Optional[int] = None,
        resorts: Optional[Iterable[int]] = None,
        meals: Optional[Iterable[int]] = None,
        hotel_categories: Optional[Iterable[int]] = None,
        kids: int = 0,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "countries[]": [int(x) for x in countries],
            "departureCity": int(departure_city),
            "touristGroup[adults]": int(adults),
            "touristGroup[kids]": int(kids),
            "checkInDateRange[from]": checkin_from,
            "checkInDateRange[to]": checkin_to,
        }
        if nights_from is not None:
            params["nightRange[from]"] = int(nights_from)
        if nights_to is not None:
            params["nightRange[to]"] = int(nights_to)
        if resorts:
            params["resorts[]"] = [int(x) for x in resorts]
        if meals:
            params["meals[]"] = [int(x) for x in meals]
        if hotel_categories:
            params["hotelCategories[]"] = [int(x) for x in hotel_categories]
        return list(self._request("/partners/statistic/cheapestTours", params) or [])


def encode_params(params: Dict[str, Any]) -> str:
    """Encode params the Travelata way: arrays as key[]=v1&key[]=v2."""
    pairs: List[tuple] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                pairs.append((key, str(item)))
        else:
            pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs, safe="[]")


def parse_feed(csv_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse the weekly Travelata popular-tours feed (UTF-16, tab-separated).

    Columns: Страна, Курорт, Название отеля, Средняя цена, Среднее кол-во взрослых,
    Среднее кол-во ночей, Ссылка на отель.
    """
    text: Optional[str] = None
    for encoding in ("utf-16", "utf-16-le", "utf-8-sig", "cp1251"):
        try:
            candidate = csv_bytes.decode(encoding)
        except Exception:  # noqa: BLE001
            continue
        if "Страна" in candidate or "Курорт" in candidate:
            text = candidate
            break
    if text is None:
        raise TravelataError("unrecognized feed encoding")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = [part.strip() for part in lines[0].split("\t")]
    rows: List[Dict[str, Any]] = []
    for line in lines[1:]:
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < len(header):
            parts += [""] * (len(header) - len(parts))
        row = dict(zip(header, parts))
        try:
            row["price"] = int(float(row.get("Средняя цена", "0").replace(" ", "").replace("\xa0", "")))
        except Exception:  # noqa: BLE001
            row["price"] = 0
        rows.append(row)
    return rows
