"""Postman API: подключение аккаунта и работа с коллекциями/окружениями.

Зачем: Postman — удобный внешний клиент для ручных проверок и мониторингов
API контент-завода (Telegram Bot API, VK, Dify) и внешних данных (RSS, HF).
Ключ хранится в ``.env`` (``POSTMAN_API_KEY``, файл в ``.gitignore``); секреты
каналов в коллекцию не попадают — они живут в Postman Environment.

Официальный REST API: https://api.getpostman.com (заголовок ``X-Api-Key``).
Всё на стандартной библиотеке, без SDK.

CLI: ``python -m content_factory postman status|list|install|export``.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import env

LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.getpostman.com"
DEFAULT_TIMEOUT = 25.0
_ASSETS_SUBDIR = "postman"
COLLECTION_FILE = "content-factory.postman_collection.json"
ENVIRONMENT_FILE = "content-factory.postman_environment.json"


class PostmanError(RuntimeError):
    """Ошибка Postman API или конфигурации (не задан ключ и т.п.)."""


def _api_key(explicit: Optional[str] = None) -> str:
    key = (explicit or env("POSTMAN_API_KEY", "") or "").strip()
    if not key:
        raise PostmanError(
            "POSTMAN_API_KEY не задан. Добавьте ключ из "
            "https://valdislav-n-9477040.postman.co/settings/me/api-keys в .env"
        )
    return key


def _request(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    api_key: Optional[str] = None,
    query: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Запрос к Postman API; сетевые и HTTP-ошибки → :class:`PostmanError`."""
    key = _api_key(api_key)
    url = API_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v})
    body = None
    headers = {"X-Api-Key": key, "Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout))) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # pragma: no cover - защита от нечитаемого тела
            detail = ""
        raise PostmanError(f"HTTP {exc.code} от Postman: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise PostmanError(f"Postman API недоступен: {exc}") from exc
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise PostmanError("Postman API вернул не JSON") from exc
    if isinstance(data, dict) and data.get("error"):
        raise PostmanError(f"Ошибка Postman: {data.get('error')}")
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Публичные методы API
# ---------------------------------------------------------------------------


def me(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Профиль владельца ключа (username, email, team)."""
    return _request("GET", "/me", api_key=api_key).get("user", {})


def list_workspaces(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    data = _request("GET", "/workspaces", api_key=api_key)
    return list(data.get("workspaces") or [])


def list_collections(
    workspace_id: Optional[str] = None, api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    query = {"workspace": workspace_id} if workspace_id else None
    data = _request("GET", "/collections", api_key=api_key, query=query)
    return list(data.get("collections") or [])


def list_environments(
    workspace_id: Optional[str] = None, api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    query = {"workspace": workspace_id} if workspace_id else None
    data = _request("GET", "/environments", api_key=api_key, query=query)
    return list(data.get("environments") or [])


def list_monitors(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    data = _request("GET", "/monitors", api_key=api_key)
    return list(data.get("monitors") or [])


def get_collection(uid: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Коллекция в формате Postman Collection v2.1 (поле ``collection``)."""
    data = _request("GET", f"/collections/{urllib.parse.quote(uid)}", api_key=api_key)
    return dict(data.get("collection") or {})


def create_collection(
    collection: Dict[str, Any],
    workspace_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    query = {"workspace": workspace_id} if workspace_id else None
    data = _request(
        "POST", "/collections", payload={"collection": collection}, api_key=api_key, query=query
    )
    return dict(data.get("collection") or data)


def create_environment(
    environment: Dict[str, Any],
    workspace_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    query = {"workspace": workspace_id} if workspace_id else None
    data = _request(
        "POST", "/environments", payload={"environment": environment}, api_key=api_key, query=query
    )
    return dict(data.get("environment") or data)


def delete_environment(uid: str, api_key: Optional[str] = None) -> bool:
    data = _request("DELETE", f"/environments/{urllib.parse.quote(uid)}", api_key=api_key)
    return True if data else False


def default_workspace_id(api_key: Optional[str] = None) -> Optional[str]:
    workspaces = list_workspaces(api_key=api_key)
    return str(workspaces[0].get("id")) if workspaces else None


# ---------------------------------------------------------------------------
# Установка готовых ассетов проекта (коллекция + окружение)
# ---------------------------------------------------------------------------


def assets_dir(root: Path) -> Path:
    return Path(root) / _ASSETS_SUBDIR


def load_asset(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PostmanError(f"Не удалось прочитать {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PostmanError(f"Неверный формат ассета {path}")
    return data


def install_assets(
    root: Path,
    workspace_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Загружает коллекцию и окружение из ``postman/`` в рабочее пространство.

    Повторный вызов создаст дубликаты коллекций/окружений — поэтому возвращает
    id созданных объектов, чтобы их можно было удалить вручную в Postman.
    """
    directory = assets_dir(root)
    collection_file = directory / COLLECTION_FILE
    environment_file = directory / ENVIRONMENT_FILE
    collection = load_asset(collection_file)
    environment = load_asset(environment_file)
    workspace = workspace_id or default_workspace_id(api_key=api_key)
    created_collection = create_collection(collection, workspace_id=workspace, api_key=api_key)
    created_environment = create_environment(environment, workspace_id=workspace, api_key=api_key)
    LOGGER.info(
        "Postman: коллекция %s, окружение %s загружены в workspace %s",
        created_collection.get("uid"),
        created_environment.get("uid"),
        workspace,
    )
    return {
        "workspace": workspace,
        "collection_uid": created_collection.get("uid") or created_collection.get("id"),
        "collection_name": created_collection.get("name") or collection.get("info", {}).get("name"),
        "environment_uid": created_environment.get("uid") or created_environment.get("id"),
        "environment_name": created_environment.get("name") or environment.get("name"),
    }


def status(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Краткий статус подключения: профиль, workspace, коллекции, окружения."""
    user = me(api_key=api_key)
    workspaces = list_workspaces(api_key=api_key)
    workspace = workspaces[0] if workspaces else {}
    workspace_id = str(workspace.get("id")) if workspace.get("id") else None
    collections = list_collections(workspace_id=workspace_id, api_key=api_key)
    environments = list_environments(workspace_id=workspace_id, api_key=api_key)
    return {
        "username": user.get("username"),
        "email": user.get("email"),
        "full_name": user.get("fullName"),
        "workspaces": len(workspaces),
        "workspace_name": workspace.get("name"),
        "workspace_id": workspace_id,
        "collections": len(collections),
        "environments": len(environments),
        "collection_names": [c.get("name") for c in collections[:20]],
    }


__all__ = [
    "COLLECTION_FILE",
    "ENVIRONMENT_FILE",
    "PostmanError",
    "assets_dir",
    "create_collection",
    "create_environment",
    "default_workspace_id",
    "delete_environment",
    "get_collection",
    "install_assets",
    "list_collections",
    "list_environments",
    "list_monitors",
    "list_workspaces",
    "load_asset",
    "me",
    "status",
]
