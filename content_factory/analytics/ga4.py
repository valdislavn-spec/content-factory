"""GA4 (Google Analytics 4) Data API — срез по лендингу для growth-отчёта.

Авторизация — сервисный аккаунт без внешних зависимостей: JWT (RS256)
подписывается через ``openssl``, меняется на access token и используется для
Data API. Работает и локально, и на раннерах GitHub Actions.

Ключи не хранятся в коде. Источники креда:
    GA4_SA_JSON  — JSON сервисного аккаунта одной строкой (GitHub Secret);
    GA4_SA_FILE  — путь к JSON-файлу сервисного аккаунта (локально).

Настройки:
    GA4_PROPERTY_ID      — числовой id ресурса (например 508543679);
    GA4_MEASUREMENT_ID   — Measurement ID потока (G-…), только для отчёта.

Если креда не заданы, :func:`landing_summary` возвращает ``{"configured": False}``
и growth-отчёт просто не добавляет секцию GA4 (ошибка не роняет отчёт).
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DATA_URL = "https://analyticsdata.googleapis.com/v1beta"
_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
_HTTP_TIMEOUT = 25.0

_TOKEN_CACHE: Dict[str, Any] = {"token": "", "expires_at": 0.0, "key": ""}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def service_account_info() -> Optional[Dict[str, Any]]:
    """JSON сервисного аккаунта из GA4_SA_JSON или GA4_SA_FILE (или None)."""
    raw = _env("GA4_SA_JSON")
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) and data.get("client_email") else None
    path = _env("GA4_SA_FILE")
    if not path:
        return None
    file_path = Path(path).expanduser()
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("client_email") else None


def property_id() -> str:
    return _env("GA4_PROPERTY_ID")


def configured() -> bool:
    return bool(service_account_info() and property_id())


def _jwt_assertion(info: Dict[str, Any]) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": str(info.get("client_email") or ""),
        "scope": _SCOPE,
        "aud": _TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode())
    )
    private_key = str(info.get("private_key") or "")
    if not private_key:
        raise RuntimeError("GA4: в сервисном аккаунте нет private_key")
    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / "key.pem"
        sig_path = Path(tmp) / "sig.bin"
        key_path.write_text(private_key, encoding="utf-8")
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key_path), "-out", str(sig_path)],
            input=signing_input.encode("ascii"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "GA4: не удалось подписать JWT (openssl): "
                + result.stderr.decode("utf-8", "replace")[:200]
            )
        signature = sig_path.read_bytes()
    return signing_input + "." + _b64url(signature)


def access_token(force: bool = False) -> str:
    """Access token сервисного аккаунта (кэш до истечения)."""
    info = service_account_info()
    if not info:
        raise RuntimeError("GA4: нет кредов (GA4_SA_JSON/GA4_SA_FILE)")
    cache_key = str(info.get("client_email") or "") + "|" + str(info.get("private_key_id") or "")
    now = time.time()
    if (
        not force
        and _TOKEN_CACHE.get("token")
        and _TOKEN_CACHE.get("key") == cache_key
        and float(_TOKEN_CACHE.get("expires_at") or 0) > now + 60
    ):
        return str(_TOKEN_CACHE["token"])
    assertion = _jwt_assertion(info)
    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
    ).encode()
    request = urllib.request.Request(
        _TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8") or "{}")
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("GA4: пустой access_token")
    _TOKEN_CACHE.update(
        {
            "token": token,
            "expires_at": now + float(payload.get("expires_in") or 3600),
            "key": cache_key,
        }
    )
    return token


def _data_post(endpoint: str, body: Dict[str, Any], timeout: float = _HTTP_TIMEOUT) -> Dict[str, Any]:
    url = f"{_DATA_URL}/properties/{property_id()}:{endpoint}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + access_token(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, timeout)) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # pragma: no cover - нечитаемое тело
            detail = ""
        raise RuntimeError(f"GA4 API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"GA4 API: {exc}") from exc


def _rows(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    headers = [str(h.get("name") or "") for h in payload.get("metricHeaders") or []]
    dim_headers = [str(h.get("name") or "") for h in payload.get("dimensionHeaders") or []]
    for row in payload.get("rows") or []:
        item: Dict[str, str] = {}
        for name, value in zip(dim_headers, row.get("dimensionValues") or []):
            item[name] = str(value.get("value") or "")
        for name, value in zip(headers, row.get("metricValues") or []):
            item[name] = str(value.get("value") or "")
        rows.append(item)
    return rows


def run_report(
    days: int = 7,
    dimensions: Optional[List[str]] = None,
    metrics: Optional[List[str]] = None,
    limit: int = 10,
) -> List[Dict[str, str]]:
    """Отчёт Data API за последние ``days`` дней (список строк-словарей)."""
    body: Dict[str, Any] = {
        "dateRanges": [{"startDate": f"{max(1, int(days))}daysAgo", "endDate": "today"}],
        "metrics": [{"name": name} for name in (metrics or ["activeUsers", "screenPageViews"])],
        "limit": max(1, int(limit)),
    }
    if dimensions:
        body["dimensions"] = [{"name": name} for name in dimensions]
    return _rows(_data_post("runReport", body))


def realtime_active_users() -> int:
    rows = _rows(
        _data_post(
            "runRealtimeReport",
            {"metrics": [{"name": "activeUsers"}], "dimensions": [{"name": "unifiedScreenName"}]},
        )
    )
    return sum(int(row.get("activeUsers") or 0) for row in rows)


def landing_summary(days: int = 7) -> Dict[str, Any]:
    """Сводка по GA4 для лендинга (без исключений наружу)."""
    measurement_id = _env("GA4_MEASUREMENT_ID")
    if not configured():
        return {"configured": False, "measurement_id": measurement_id}
    try:
        totals_rows = run_report(days=days, metrics=["activeUsers", "screenPageViews", "sessions"])
        bottom = totals_rows[0] if totals_rows else {}
        sources = run_report(
            days=days,
            dimensions=["sessionSource", "sessionMedium"],
            metrics=["sessions", "activeUsers"],
            limit=5,
        )
        pages = run_report(
            days=days,
            dimensions=["pagePath"],
            metrics=["screenPageViews", "activeUsers"],
            limit=5,
        )
        try:
            realtime = realtime_active_users()
        except Exception:  # realtime не критичен для отчёта
            realtime = -1
    except Exception as exc:
        return {"configured": True, "ok": False, "error": str(exc), "measurement_id": measurement_id}
    return {
        "configured": True,
        "ok": True,
        "property_id": property_id(),
        "measurement_id": measurement_id,
        "days": days,
        "active_users": int(bottom.get("activeUsers") or 0),
        "page_views": int(bottom.get("screenPageViews") or 0),
        "sessions": int(bottom.get("sessions") or 0),
        "top_sources": sources,
        "top_pages": pages,
        "realtime_active": realtime,
    }


def format_markdown_section(summary: Dict[str, Any]) -> str:
    """Markdown-секция GA4 для growth-отчёта ('' если GA4 не настроен)."""
    if not summary or not summary.get("configured"):
        return ""
    lines = ["", "## GA4 — лендинг (последние {} дн.)".format(summary.get("days") or 7), ""]
    if not summary.get("ok"):
        lines.append("GA4 недоступен: {}".format(summary.get("error") or "неизвестная ошибка"))
        return "\n".join(lines)
    lines.append(
        "- Пользователи: **{}**, просмотры: **{}**, сессии: **{}**".format(
            summary.get("active_users", 0),
            summary.get("page_views", 0),
            summary.get("sessions", 0),
        )
    )
    if summary.get("measurement_id"):
        lines.append("- Measurement ID: `{}`".format(summary["measurement_id"]))
    if summary.get("realtime_active", -1) >= 0:
        lines.append("- Сейчас на сайте: **{}**".format(summary["realtime_active"]))
    sources = summary.get("top_sources") or []
    if sources:
        lines.append("- Источники:")
        for row in sources:
            label = (row.get("sessionSource") or "?") + " / " + (row.get("sessionMedium") or "?")
            lines.append(
                "  - {} — сессий {}, польз. {}".format(
                    label, row.get("sessions", "0"), row.get("activeUsers", "0")
                )
            )
    pages = summary.get("top_pages") or []
    if pages:
        lines.append("- Страницы:")
        for row in pages:
            lines.append(
                "  - `{}` — просмотров {}, польз. {}".format(
                    row.get("pagePath") or "?", row.get("screenPageViews", "0"), row.get("activeUsers", "0")
                )
            )
    return "\n".join(lines)


def format_telegram_line(summary: Dict[str, Any]) -> str:
    """Короткая строка GA4 для Telegram-сводки ('' если нечего показывать)."""
    if not summary or not summary.get("configured") or not summary.get("ok"):
        return ""
    return "GA4 лендинг ({}д): {} польз., {} просмотров, {} сессий".format(
        summary.get("days") or 7,
        summary.get("active_users", 0),
        summary.get("page_views", 0),
        summary.get("sessions", 0),
    )
