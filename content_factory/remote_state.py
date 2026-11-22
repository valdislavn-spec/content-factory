"""Optional Cloudflare D1 client for durable scheduler state and retry queue.

The Worker `cloudflare/tg-cron.mjs` exposes a small authenticated JSON API
(`/api/v1/...`). When `CONTENT_FACTORY_STATE_URL` and
`CONTENT_FACTORY_STATE_TOKEN` are set, the pipeline mirrors its local SQLite
queue and scheduler state there. Without these variables everything falls back
to SQLite + the existing GitHub variable sync.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class RemoteStateError(RuntimeError):
    """Raised when the D1 API is unavailable or returns an error."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class RemoteState:
    def __init__(self, base_url: str = "", token: str = "", timeout: float = 12.0) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.token = str(token or "").strip()
        self.timeout = float(timeout)

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.token)

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.enabled:
            raise RemoteStateError("remote state is not configured")
        url = self.base_url + path
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            method=method,
            data=data,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/json",
                "Content-Type": "application/json",
                # Cloudflare bot protection blocks default Python-urllib UA.
                "User-Agent": "content-factory-state/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise RemoteStateError(f"HTTP {exc.code}: {body}", status=exc.code) from exc
        except Exception as exc:  # noqa: BLE001 - network errors are non-fatal for the caller
            raise RemoteStateError(f"{type(exc).__name__}: {exc}") from exc
        if not raw:
            return {}
        try:
            data_obj = json.loads(raw)
        except ValueError as exc:
            raise RemoteStateError("invalid JSON from state API") from exc
        if isinstance(data_obj, dict) and data_obj.get("ok") is False:
            raise RemoteStateError(str(data_obj.get("error") or "state API error"))
        return data_obj if isinstance(data_obj, dict) else {}

    def get_state(self, name: str) -> Optional[Dict[str, Any]]:
        encoded = urllib.parse.quote(str(name), safe="")
        try:
            data = self._request("GET", f"/api/v1/state/{encoded}")
        except RemoteStateError as exc:
            if exc.status == 404:
                return None
            raise
        state = data.get("state")
        return state if isinstance(state, dict) else None

    def put_state(self, name: str, state: Dict[str, Any]) -> None:
        encoded = urllib.parse.quote(str(name), safe="")
        self._request("PUT", f"/api/v1/state/{encoded}", {"state": state})

    def queue_put(self, row: Dict[str, Any]) -> None:
        payload = {
            "post_id": row.get("post_id", ""),
            "publisher": row.get("publisher", ""),
            "channel_id": row.get("channel_id", ""),
            "post_json": row.get("post_json", ""),
            "attempts": int(row.get("attempts") or 0),
            "next_attempt_at": row.get("next_attempt_at", ""),
            "last_error": row.get("last_error", ""),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }
        self._request("POST", "/api/v1/queue", payload)

    def queue_due(self, channel_id: str, limit: int = 20, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        moment = now or datetime.now(timezone.utc)
        stamp = moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        query = urllib.parse.urlencode(
            {"channel_id": channel_id, "limit": max(1, int(limit)), "now": stamp}
        )
        data = self._request("GET", f"/api/v1/queue/due?{query}")
        rows = data.get("rows")
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def queue_done(self, post_id: str, publisher: str) -> None:
        self._request("POST", "/api/v1/queue/done", {"post_id": post_id, "publisher": publisher})

    def health_tick(
        self,
        channel_id: str,
        last_tick_at: Optional[datetime] = None,
        last_post_at: Optional[datetime] = None,
        last_error: str = "",
    ) -> None:
        now = last_tick_at or datetime.now(timezone.utc)
        payload = {
            "channel_id": channel_id,
            "last_tick_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "last_error": str(last_error or "")[:1000],
        }
        if last_post_at is not None:
            payload["last_post_at"] = last_post_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        self._request("POST", "/api/v1/health/tick", payload)


def get_remote_state() -> RemoteState:
    """Build the client from environment; ``enabled`` is false when unset."""
    return RemoteState(
        base_url=os.environ.get("CONTENT_FACTORY_STATE_URL", ""),
        token=os.environ.get("CONTENT_FACTORY_STATE_TOKEN", ""),
        timeout=float(os.environ.get("CONTENT_FACTORY_STATE_TIMEOUT", "12") or 12),
    )
