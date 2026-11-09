"""Canva Connect API: OAuth, список дизайнов, экспорт в PNG/JPEG.

Документация: https://www.canva.dev/docs/connect/
Требования Canva: в аккаунте включён пароль + MFA, в Developer Portal создан
auth client (Outside Canva → Start integrating), включены scopes.

Env:
    CANVA_CLIENT_ID, CANVA_CLIENT_SECRET
    CANVA_REDIRECT_URI (для public/private app, по умолчанию
                        http://127.0.0.1:8085/callback)
    CANVA_SCOPES (список через пробел; должны быть включены в приложении)

Токен хранится в data/canva_token.json (gitignored).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

API_BASE = "https://api.canva.com/rest/v1"
AUTH_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_PATH = Path(__file__).resolve().parents[2] / "data" / "canva_token.json"
DEFAULT_SCOPES = (
    "design:meta:read design:content:read design:content:write "
    "asset:read asset:write folder:read folder:write"
)


class CanvaError(RuntimeError):
    """Ошибка Canva API."""


def _env(name: str) -> str:
    return (os.environ.get(name, "") or "").strip()


def _client() -> tuple[str, str]:
    client_id, secret = _env("CANVA_CLIENT_ID"), _env("CANVA_CLIENT_SECRET")
    if not client_id or not secret:
        raise CanvaError(
            "CANVA_CLIENT_ID/CANVA_CLIENT_SECRET не заданы. Получите их в Canva "
            "Developer Portal (Outside Canva → Start integrating) после настройки MFA."
        )
    return client_id, secret


def _basic_auth() -> str:
    client_id, secret = _client()
    raw = f"{client_id}:{secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _http(method: str, url: str, payload: Optional[Dict[str, Any]] = None,
          headers: Optional[Dict[str, str]] = None, form: bool = False,
          timeout: int = 40) -> Any:
    headers = dict(headers or {})
    body = None
    if payload is not None:
        if form:
            body = urllib.parse.urlencode(payload).encode()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            body = json.dumps(payload).encode()
            headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode()) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise CanvaError(f"HTTP {exc.code} {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CanvaError(f"Canva недоступна: {exc}") from exc


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def authorization_url(state: str = "", scopes: str = "") -> tuple[str, str]:
    """Возвращает (url, code_verifier) для public/private app (PKCE)."""
    client_id, _ = _client()
    redirect_uri = _env("CANVA_REDIRECT_URI") or "http://127.0.0.1:8085/callback"
    verifier, challenge = pkce_pair()
    params = {
        "code_challenge": challenge,
        "code_challenge_method": "s256",
        "scope": scopes or _env("CANVA_SCOPES") or DEFAULT_SCOPES,
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if state:
        params["state"] = state
    return AUTH_URL + "?" + urllib.parse.urlencode(params), verifier


def exchange_code(code: str, verifier: str) -> Dict[str, Any]:
    client_id, _ = _client()
    redirect_uri = _env("CANVA_REDIRECT_URI") or "http://127.0.0.1:8085/callback"
    data = _http(
        "POST", API_BASE + "/oauth/token",
        payload={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        },
        headers={"Authorization": _basic_auth()},
        form=True,
    )
    _save_token(data)
    return data


def client_credentials_token() -> Dict[str, Any]:
    """Для Service app: токен от имени приложения."""
    data = _http(
        "POST", API_BASE + "/oauth/token",
        payload={"grant_type": "client_credentials"},
        headers={"Authorization": _basic_auth()},
        form=True,
    )
    _save_token(data)
    return data


def _save_token(data: Dict[str, Any]) -> Path:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    stored = dict(data)
    stored["expires_at"] = time.time() + int(data.get("expires_in") or 3600)
    TOKEN_PATH.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    return TOKEN_PATH


def _load_token() -> Dict[str, Any]:
    if not TOKEN_PATH.is_file():
        raise CanvaError("нет data/canva_token.json — сначала выполните scripts/canva_connect.py login")
    return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))


def ensure_token() -> str:
    token = _load_token()
    if float(token.get("expires_at") or 0) > time.time() + 60:
        return token["access_token"]
    if token.get("refresh_token"):
        data = _http(
            "POST", API_BASE + "/oauth/token",
            payload={"grant_type": "refresh_token", "refresh_token": token["refresh_token"]},
            headers={"Authorization": _basic_auth()},
            form=True,
        )
        _save_token(data)
        return data["access_token"]
    return client_credentials_token()["access_token"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def _api(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    return _http(
        method, API_BASE + path, payload=payload,
        headers={"Authorization": "Bearer " + ensure_token()},
    )


def profile() -> Dict[str, Any]:
    return _api("GET", "/users/me/profile")


def list_designs(limit: int = 20, continuation: str = "") -> Dict[str, Any]:
    params = {"limit": str(max(1, min(100, int(limit))))}
    if continuation:
        params["continuation"] = continuation
    return _api("GET", "/designs?" + urllib.parse.urlencode(params))


def get_design(design_id: str) -> Dict[str, Any]:
    return _api("GET", f"/designs/{urllib.parse.quote(design_id)}")


def export_design(design_id: str, format_type: str = "png",
                  out_dir: str = "", poll: bool = True,
                  timeout: int = 120) -> Dict[str, Any]:
    """Запускает экспорт дизайна, ждёт и скачивает файлы."""
    job_data = _api("POST", "/exports", payload={
        "design_id": design_id,
        "format": {"type": format_type},
    })
    job = job_data.get("job") or job_data
    job_id = job.get("id")
    if not job_id:
        raise CanvaError(f"Canva не вернула id job'а: {str(job_data)[:300]}")
    if not poll:
        return {"job_id": job_id, "status": job.get("status"), "urls": []}

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _api("GET", f"/exports/{job_id}")
        job = job.get("job") or job
        status = job.get("status")
        if status in {"success", "failed"}:
            break
        time.sleep(3)
    status = job.get("status")
    if status != "success":
        raise CanvaError(f"экспорт не удался: {status} {str(job.get('error'))[:200]}")
    urls: List[str] = job.get("urls") or []
    directory = Path(out_dir) if out_dir else Path(__file__).resolve().parents[2] / "assets" / "canva"
    directory.mkdir(parents=True, exist_ok=True)
    files: List[str] = []
    for index, url in enumerate(urls, start=1):
        suffix = ".png" if format_type == "png" else f".{format_type}"
        target = directory / f"canva-{design_id[:16]}-{index}{suffix}"
        with urllib.request.urlopen(url, timeout=60) as response:
            target.write_bytes(response.read())
        files.append(str(target))
    return {"job_id": job_id, "status": status, "files": files, "urls": urls}
