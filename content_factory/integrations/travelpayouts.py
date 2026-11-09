"""Travelpayouts partner links API client.

Converts direct travel-brand URLs into affiliate links:
    POST https://api.travelpayouts.com/links/v1/create
    headers: X-Access-Token: <API token from Profile → API token>
    body: {trs, marker, shorten, links: [{url, sub_id}]}

Requirements (per Travelpayouts docs): a Travelpayouts account, a connected
brand program (e.g. Booking.com / GetYourGuide / Aviasales), API token,
project ID (trs) and Partner ID (marker, dashboard bottom-left).

Limits: 100 requests/min per marker, max 10 links per request.
Kiwi.com, HolidayTaxis, Ticketmaster, Priority Pass, Indrive are not supported
by the links API.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

API_URL = "https://api.travelpayouts.com/links/v1/create"
FINANCE_URL = "https://api.travelpayouts.com/finance/v2"
MAX_LINKS = 10


class TravelpayoutsError(RuntimeError):
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class TravelpayoutsClient:
    token: str
    marker: str
    trs: str
    timeout: float = 30.0
    api_url: str = API_URL

    @classmethod
    def from_env(cls) -> "TravelpayoutsClient":
        return cls(
            token=env("TRAVELPAYOUTS_TOKEN"),
            marker=env("TRAVELPAYOUTS_MARKER"),
            trs=env("TRAVELPAYOUTS_TRS"),
        )

    def configured(self) -> bool:
        return bool(self.token and self.marker and self.trs)

    def convert(self, links: Iterable[Dict[str, str]], shorten: bool = True) -> List[Dict[str, Any]]:
        """Convert brand URLs into partner URLs; returns one dict per input link."""
        items = [dict(item) for item in links if item.get("url")][:MAX_LINKS]
        if not items:
            return []
        if not self.configured():
            raise TravelpayoutsError(
                "Travelpayouts is not configured: TRAVELPAYOUTS_TOKEN / TRAVELPAYOUTS_MARKER / TRAVELPAYOUTS_TRS"
            )
        payload = json.dumps({"trs": int(self.trs), "marker": int(self.marker), "shorten": bool(shorten), "links": items}).encode()
        request = urllib.request.Request(
            self.api_url,
            data=payload,
            method="POST",
            headers={
                "X-Access-Token": self.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "content-factory-travelpayouts/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            raise TravelpayoutsError("HTTP %s: %s" % (error.code, error.read()[:300])) from error
        except Exception as error:  # noqa: BLE001
            raise TravelpayoutsError("%s: %s" % (type(error).__name__, error)) from error
        result = data.get("result") or {}
        return list(result.get("links") or [])


    # ------------------------------------------------------------------
    # Финансы: баланс, следующая выплата, история выплат
    # ------------------------------------------------------------------
    def _finance(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.token:
            raise TravelpayoutsError("Travelpayouts: нет API-токена")
        url = FINANCE_URL + "/" + method
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "X-Access-Token": self.token,
                "Accept": "application/json",
                "User-Agent": "content-factory-travelpayouts/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            raise TravelpayoutsError("HTTP %s: %s" % (error.code, error.read()[:300])) from error
        except Exception as error:  # noqa: BLE001
            raise TravelpayoutsError("%s: %s" % (type(error).__name__, error)) from error

    def balance(self) -> Dict[str, str]:
        """Текущий баланс: {"usd": "...", "eur": "...", "rub": "..."}."""
        return dict((self._finance("get_user_balance").get("balance") or {}))

    def next_payout(self) -> Dict[str, str]:
        """Сумма следующей выплаты по валютам."""
        return dict((self._finance("get_user_next_payout").get("next_payout") or {}))

    def payments(self, limit: int = 20) -> List[Dict[str, Any]]:
        """История выплат (список)."""
        data = self._finance("get_user_payments", {"limit": int(limit)})
        return list(data or [])


def partner_url(converted: Dict[str, Any], original: str) -> str:
    """Pick the partner URL from an API response item ("" when conversion failed)."""
    if str(converted.get("code") or "") == "success":
        return str(converted.get("partner_url") or "")
    return ""


def redirect_page(target: str, title: str = "Redirecting") -> str:
    """Minimal noindex redirect page used on the hub (/go/<slug>.html)."""
    safe = str(target).replace('"', "%22").replace("<", "%3C").replace(">", "%3E")
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"robots\" content=\"noindex,nofollow\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>%s</title>\n"
        "<script>location.replace(%s);</script>\n"
        "</head>\n<body style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;padding:40px\">\n"
        "<p>%s…</p>\n<p><a href=\"%s\">Continue to the partner site</a></p>\n"
        "<p style=\"color:#666;font-size:13px\">Ad · affiliate link</p>\n"
        "</body>\n</html>\n"
    ) % (title, json.dumps(safe), title, safe)
