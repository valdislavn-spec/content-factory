"""Клиент APILayer (api.apilayer.net): курсы валют и рейсы.

Бесплатные планы (100 запросов/мес каждый):
    * Exchange Rate  — GET /exchangerate/v1/latest (база фиксирована EUR);
    * Aviationstack — GET /aviationstack/v1/flights (только real-time).

Ключ: один на аккаунт (APILAYER_KEY). Пути к API — через шлюз
``api.apilayer.net``, не ``.com``.

Важно про доступ: Cloudflare на api.apilayer.net отдаёт 403 части
домашних/дата-центровых IP (наш локальный Mac, CF Worker), но
GitHub Actions-раннеры проходят. Локально можно указать
``APILAYER_SOCKS_PROXY=socks5h://127.0.0.1:1080`` — тогда клиент
ходит через ``curl`` и локальный Xray-прокси.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

GATEWAY = "https://api.apilayer.net"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class ApiLayerError(RuntimeError):
    pass


class ApiLayerClient:
    """Минимальный клиент APILayer для FX и статусов рейсов."""

    def __init__(self, api_key: str = "", socks_proxy: str | None = None, timeout: float = 30.0):
        self.api_key = (api_key or env("APILAYER_KEY")).strip()
        if socks_proxy is None:
            socks_proxy = env("APILAYER_SOCKS_PROXY")
        self.socks_proxy = str(socks_proxy or "").strip()
        self.timeout = timeout

    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict) -> dict:
        if not self.api_key:
            raise ApiLayerError("APILAYER_KEY не задан")
        query = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        query["access_key"] = self.api_key
        url = GATEWAY + path + "?" + urllib.parse.urlencode(query)
        if self.socks_proxy:
            proxy = self.socks_proxy.replace("socks5h://", "").replace("socks5://", "")
            last = ""
            for attempt in range(2):
                proc = subprocess.run(
                    ["curl", "-sS", "-m", str(int(self.timeout)), "--socks5-hostname", proxy, url],
                    capture_output=True,
                    text=True,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return json.loads(proc.stdout)
                last = proc.stderr or proc.stdout or "пустой ответ"
                time.sleep(1.5 * (attempt + 1))
            raise ApiLayerError("curl: " + last[:200])
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "content-factory-apilayer/1.0"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))

    def latest_rates(self, symbols: str = "USD,EUR,RUB,GBP") -> dict:
        """Курсы к EUR (бесплатный план не даёт менять base)."""
        data = self._get("/exchangerate/v1/latest", {"symbols": symbols})
        if not data.get("success"):
            raise ApiLayerError(str(data.get("error") or data)[:300])
        return data

    def usd_to_eur(self, usd: float) -> float | None:
        try:
            usd_per_eur = float((self.latest_rates("USD").get("rates") or {}).get("USD") or 0)
        except (ApiLayerError, TypeError, ValueError):
            return None
        if usd_per_eur <= 0:
            return None
        return round(float(usd) / usd_per_eur, 2)

    def flights(self, limit: int = 10, **filters) -> dict:
        """Список рейсов (Aviationstack). Фильтры: dep_iata, arr_iata, flight_status и т.п."""
        params = {"limit": limit}
        params.update({k: v for k, v in filters.items() if v})
        data = self._get("/aviationstack/v1/flights", params)
        if data.get("error"):
            raise ApiLayerError(str(data["error"])[:300])
        return data
