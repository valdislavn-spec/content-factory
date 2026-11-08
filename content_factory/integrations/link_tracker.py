"""Клиент трекера коротких ссылок (Cloudflare Worker, KV).

Worker: https://links-tracker.valdislav-n.workers.dev (см. docs/monetization/link-tracker.md)
Эндпоинты:
    POST /admin/links   {code, target, channel?, network?, label?} + x-token: ADMIN
    GET  /admin/links   список ссылок
    GET  /r/{code}      302 на target + запись клика (день/канал)
    GET  /stats?token=STATS[&code=]  статистика

Env:
    LINK_TRACKER_BASE          — базовый URL воркера
    LINK_TRACKER_ADMIN_TOKEN   — для создания/списка ссылок
    LINK_TRACKER_STATS_TOKEN   — для чтения статистики
    AFFILIATE_LINK[_CHANNEL]   — опциональный override прямой ссылки (без трекинга)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_TIMEOUT = 20.0


class LinkTrackerError(RuntimeError):
    """Ошибка трекера ссылок."""


class LinkTrackerClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        admin_token: Optional[str] = None,
        stats_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or os.environ.get("LINK_TRACKER_BASE", "") or "").strip().rstrip("/")
        self.admin_token = (admin_token or os.environ.get("LINK_TRACKER_ADMIN_TOKEN", "") or "").strip()
        self.stats_token = (stats_token or os.environ.get("LINK_TRACKER_STATS_TOKEN", "") or "").strip()
        self.timeout = float(timeout)

    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, *, token: str = "", payload: Optional[Dict[str, Any]] = None) -> Any:
        if not self.base_url:
            raise LinkTrackerError("LINK_TRACKER_BASE не задан")
        url = self.base_url + path
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json", "User-Agent": "ContentFactory/1.0"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["x-token"] = token
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:  # noqa: BLE001
                pass
            raise LinkTrackerError("Link tracker HTTP {}: {}".format(exc.code, detail)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LinkTrackerError("Link tracker недоступен: {}".format(exc)) from exc
        try:
            data = json.loads(raw.decode("utf-8", errors="replace")) if raw else {}
        except ValueError as exc:
            raise LinkTrackerError("Link tracker вернул не JSON") from exc
        if isinstance(data, dict) and data.get("ok") is False:
            raise LinkTrackerError("Link tracker: {}".format(data.get("error") or "unknown error"))
        return data

    # ------------------------------------------------------------------
    def create_link(
        self,
        code: str,
        target: str,
        *,
        channel: str = "",
        network: str = "",
        label: str = "",
        active: bool = True,
    ) -> Dict[str, Any]:
        data = self._request(
            "POST",
            "/admin/links",
            token=self.admin_token,
            payload={
                "code": code,
                "target": target,
                "channel": channel,
                "network": network,
                "label": label,
                "active": active,
            },
        )
        return (data or {}).get("record") or {}

    def list_links(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/admin/links", token=self.admin_token)
        return list((data or {}).get("links") or [])

    def stats(self, code: str = "") -> Dict[str, Any]:
        path = "/stats?token={}".format(self.stats_token)
        if code:
            path += "&code={}".format(code)
        return self._request("GET", path, token=self.stats_token) or {}

    def short_url(self, code: str) -> str:
        if not self.base_url:
            raise LinkTrackerError("LINK_TRACKER_BASE не задан")
        return "{}/r/{}".format(self.base_url, code)
