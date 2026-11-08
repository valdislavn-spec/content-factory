"""IndexNow — бесплатная индексация страниц лендинга в Bing/Yandex/Seznam/Naver.

Протокол: POST https://api.indexnow.org/indexnow с JSON
    {"host": "...", "key": "...", "keyLocation": "...", "urlList": [...]}
Ключ — 8–128 символов (hex-подобный), должен лежать файлом ``<key>.txt`` в корне
сайта со своим содержимым.

Только для лендинга живых каналов (EN/ES): RU-каналы не участвуют.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

API_URL = "https://api.indexnow.org/indexnow"
_KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")


class IndexNowError(RuntimeError):
    """Ошибка протокола IndexNow (ключ, хост, сеть)."""


def validate_key(key: str) -> str:
    value = str(key or "").strip()
    if not _KEY_RE.match(value):
        raise IndexNowError("IndexNow key должен быть 8–128 символов [A-Za-z0-9-]")
    return value


def key_file_path(site_dir: Path, key: str) -> Path:
    return Path(site_dir) / f"{validate_key(key)}.txt"


def ensure_key_file(site_dir: Path, key: str) -> Path:
    """Создаёт ``<key>.txt`` с содержимым key, если его ещё нет."""
    path = key_file_path(site_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(validate_key(key), encoding="utf-8")
    return path


def sitemap_urls(site_dir: Path) -> List[str]:
    """URL из sitemap.xml (``<loc>...</loc>``)."""
    path = Path(site_dir) / "sitemap.xml"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)


def build_payload(
    host: str,
    key: str,
    urls: Sequence[str],
    key_location: Optional[str] = None,
) -> Dict[str, Any]:
    host_value = str(host or "").strip().strip("/")
    if not host_value:
        raise IndexNowError("не задан host лендинга (например example.github.io)")
    cleaned = [str(url).strip() for url in urls if str(url).strip()]
    if not cleaned:
        raise IndexNowError("нет URL для отправки")
    payload: Dict[str, Any] = {
        "host": host_value,
        "key": validate_key(key),
        "urlList": cleaned,
    }
    if key_location:
        payload["keyLocation"] = str(key_location)
    return payload


def ping(
    host: str,
    key: str,
    urls: Sequence[str],
    *,
    key_location: Optional[str] = None,
    timeout: float = 20.0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Отправляет URL в IndexNow; при ``dry_run`` возвращает payload без сети."""
    payload = build_payload(host, key, urls, key_location=key_location)
    if dry_run:
        return {"sent": False, "status": 0, "payload": payload}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout))) as response:
            status = int(getattr(response, "status", 0) or 0)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # pragma: no cover
            detail = ""
        raise IndexNowError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise IndexNowError(f"IndexNow недоступен: {exc}") from exc
    return {"sent": True, "status": status, "payload": payload, "response": raw[:200].decode("utf-8", errors="replace")}


__all__ = [
    "API_URL",
    "IndexNowError",
    "build_payload",
    "ensure_key_file",
    "key_file_path",
    "ping",
    "sitemap_urls",
    "validate_key",
]
