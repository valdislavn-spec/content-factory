#!/usr/bin/env python3
"""MCP-сервер Reclaim.ai (stdio JSON-RPC 2.0, только stdlib).

Даёт агенту управление задачами и календарём Reclaim.ai: задачи (список,
создание, завершение), события календаря, текущий пользователь.

Авторизация: переменная окружения RECLAIM_API_KEY (токен из
https://app.reclaim.ai/settings/developer).
Все вызовы идут в https://api.app.reclaim.ai/api с заголовком
`Authorization: Bearer <key>`.

Запуск:  RECLAIM_API_KEY=... python tools/reclaim_mcp.py
Документация и подключение к DSH: docs/reclaim.md.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "reclaim-mcp", "version": "1.0.0"}
BASE_URL = "https://api.app.reclaim.ai/api"
CHUNK_MINUTES = 15  # Reclaim планирует блоками по 15 минут


class ReclaimError(RuntimeError):
    """Ошибка Reclaim API с деталями ответа."""


def _api_key() -> str:
    import os

    return os.environ.get("RECLAIM_API_KEY", "").strip()


def _request(
    method: str,
    path: str,
    payload: Optional[Any] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Any:
    key = _api_key()
    if not key:
        raise ReclaimError(
            "RECLAIM_API_KEY не задан. Получите токен: "
            "https://app.reclaim.ai/settings/developer"
        )
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "factory-reclaim-mcp/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ReclaimError(f"Reclaim API {method} {path}: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise ReclaimError(f"Reclaim API недоступен: {exc}") from exc


# ---------------------------------------------------------------------------
# операции
# ---------------------------------------------------------------------------
def whoami() -> Dict[str, Any]:
    user = _request("GET", "/users/current") or {}
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name") or user.get("firstName"),
        "edition": user.get("edition"),
    }


def list_tasks(include_completed: bool = False) -> Dict[str, Any]:
    tasks: List[Dict[str, Any]] = _request("GET", "/tasks") or []
    result = []
    for task in tasks:
        status = str(task.get("status") or "")
        if not include_completed and status in {"COMPLETE", "ARCHIVED", "CANCELLED"}:
            continue
        if task.get("deleted"):
            continue
        result.append(
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "status": status,
                "priority": task.get("priority"),
                "due": task.get("due"),
                "chunks_required": task.get("timeChunksRequired"),
                "chunks_remaining": task.get("timeChunksRemaining"),
                "notes": (task.get("notes") or "")[:200],
            }
        )
    return {"count": len(result), "tasks": result}


def create_task(
    title: str,
    notes: str = "",
    minutes: int = 30,
    priority: str = "P3",
    due: str = "",
) -> Dict[str, Any]:
    title = str(title or "").strip()
    if not title:
        raise ReclaimError("title обязателен")
    chunks = max(1, int(minutes) // CHUNK_MINUTES)
    payload: Dict[str, Any] = {
        "title": title,
        "notes": str(notes or ""),
        "eventCategory": "WORK",
        "timeChunksRequired": chunks,
        "minChunkSize": 1,
        "maxChunkSize": min(chunks, 8),
        "priority": str(priority or "P3").upper(),
    }
    if due:
        payload["due"] = str(due)
    task = _request("POST", "/tasks", payload) or {}
    return {
        "id": task.get("id"),
        "title": task.get("title", title),
        "status": task.get("status"),
        "priority": task.get("priority", payload["priority"]),
        "due": task.get("due"),
        "chunks_required": task.get("timeChunksRequired", chunks),
    }


def complete_task(task_id: int) -> Dict[str, Any]:
    _request("POST", f"/planner/done/task/{int(task_id)}")
    return {"task_id": int(task_id), "completed": True}


def list_events(start: str = "", end: str = "") -> Dict[str, Any]:
    events: List[Dict[str, Any]] = _request(
        "GET", "/events", params={"start": start, "end": end}
    ) or []
    result = []
    for event in events:
        result.append(
            {
                "id": event.get("id"),
                "title": event.get("title"),
                "event_type": event.get("eventType"),
                "start": event.get("start"),
                "end": event.get("end"),
                "category": event.get("eventCategory"),
            }
        )
    return {"count": len(result), "events": result}


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "reclaim_whoami",
        "description": "Проверка токена Reclaim.ai: кто авторизован.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "reclaim_list_tasks",
        "description": "Активные задачи Reclaim (можно включить завершённые).",
        "inputSchema": {
            "type": "object",
            "properties": {"include_completed": {"type": "boolean"}},
        },
    },
    {
        "name": "reclaim_create_task",
        "description": "Создать задачу в Reclaim (авто-планирование времени).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "minutes": {"type": "integer", "minimum": 15, "maximum": 480},
                "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                "due": {"type": "string", "description": "ISO datetime или YYYY-MM-DD"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "reclaim_complete_task",
        "description": "Завершить задачу Reclaim по id.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "reclaim_list_events",
        "description": "События календаря Reclaim (даты YYYY-MM-DD).",
        "inputSchema": {
            "type": "object",
            "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
        },
    },
]


def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
    if name == "reclaim_whoami":
        return whoami()
    if name == "reclaim_list_tasks":
        return list_tasks(bool(arguments.get("include_completed")))
    if name == "reclaim_create_task":
        return create_task(
            arguments.get("title", ""),
            arguments.get("notes", ""),
            int(arguments.get("minutes") or 30),
            arguments.get("priority") or "P3",
            arguments.get("due") or "",
        )
    if name == "reclaim_complete_task":
        return complete_task(int(arguments.get("task_id") or 0))
    if name == "reclaim_list_events":
        return list_events(arguments.get("start") or "", arguments.get("end") or "")
    raise ReclaimError(f"неизвестный инструмент: {name}")


def _ok(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return _ok(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return _ok(request_id, {})
    if method == "tools/list":
        return _ok(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(str(params.get("name", "")), arguments if isinstance(arguments, dict) else {})
            return _ok(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
                    ],
                    "isError": False,
                },
            )
        except Exception as exc:  # noqa: BLE001 - ошибка уходит клиенту
            return _ok(
                request_id,
                {"content": [{"type": "text", "text": f"Ошибка: {exc}"}], "isError": True},
            )
    return _err(request_id, -32601, f"метод не поддерживается: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(_err(None, -32700, "invalid JSON")) + "\n")
            sys.stdout.flush()
            continue
        try:
            result = handle(message)
        except Exception as exc:  # noqa: BLE001
            result = _err(message.get("id"), -32603, f"внутренняя ошибка: {exc}")
        if result is not None:
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
