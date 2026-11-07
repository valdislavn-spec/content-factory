#!/usr/bin/env python3
"""Read-only MCP-сервер фабрики (stdio JSON-RPC 2.0).

Тулы:
  • factory_status — каналы, последние посты и последние запуски;
  • factory_query  — read-only SQL по data/factory.sqlite3 (SELECT/PRAGMA/CTE);
  • trends_now     — актуальные тренды (Google Trends RSS + наши провайдеры);
  • factory_schema — таблицы и колонки БД;
  • hackernews_top — топ Hacker News;
  • web_search     — поиск через Tavily (если задан TAVILY_API_KEY).

Подключение к DSH: см. docs/mcp-plugins.md. Сервер ничего не пишет в БД и
не публикует посты — только чтение и внешние GET/POST-запросы.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "factory-mcp", "version": "1.0.0"}
DB_PATH = Path(os.environ.get("FACTORY_DB") or ROOT / "data" / "factory.sqlite3")
MAX_ROWS = 200

_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|vacuum|reindex|replace|truncate)\b",
    re.IGNORECASE,
)
_ALLOWED_START = re.compile(r"^\s*(select|with|pragma|explain)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# данные
# ---------------------------------------------------------------------------
def _load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise RuntimeError(f"База не найдена: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _channels() -> List[Dict[str, Any]]:
    from content_factory.config import Settings, load_channels

    settings = Settings.load()
    result: List[Dict[str, Any]] = []
    for path in ("config/channels.en.yaml", "config/channels.es.yaml"):
        try:
            for channel in load_channels(settings, path=path):
                result.append(
                    {
                        "id": channel.id,
                        "title": channel.title,
                        "language": channel.language,
                        "timezone_offset": channel.timezone_offset,
                        "slots": len(channel.schedule),
                        "enabled": channel.enabled,
                        "chat_id_set": bool(channel.telegram_chat_id),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            result.append({"path": path, "error": str(exc)})
    return result


def tool_factory_status() -> Dict[str, Any]:
    payload: Dict[str, Any] = {"db": str(DB_PATH), "channels": _channels()}
    try:
        conn = _connect()
        try:
            posts = conn.execute(
                """SELECT channel_id, format, created_at, status
                   FROM posts ORDER BY created_at DESC LIMIT 12"""
            ).fetchall()
            runs = conn.execute(
                """SELECT channel_id, status, started_at, posts_published
                   FROM runs ORDER BY started_at DESC LIMIT 10"""
            ).fetchall()
            payload["latest_posts"] = [dict(row) for row in posts]
            payload["latest_runs"] = [dict(row) for row in runs]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        payload["db_error"] = str(exc)
    return payload


def tool_factory_query(sql: str) -> Dict[str, Any]:
    query = str(sql or "").strip()
    if not query:
        raise ValueError("пустой SQL")
    if not _ALLOWED_START.match(query):
        raise ValueError("разрешены только SELECT / WITH / PRAGMA / EXPLAIN")
    if _FORBIDDEN_SQL.search(query):
        raise ValueError("запрос изменяет данные — сервер только для чтения")
    if ";" in query.rstrip(";"):
        raise ValueError("разрешён один SQL-запрос")
    conn = _connect()
    try:
        cursor = conn.execute(query)
        rows = cursor.fetchmany(MAX_ROWS)
        columns = [description[0] for description in cursor.description or []]
        return {
            "columns": columns,
            "rows": [dict(zip(columns, row)) for row in rows],
            "count": len(rows),
            "limited": len(rows) >= MAX_ROWS,
        }
    finally:
        conn.close()


def tool_trends_now(channel_id: str = "ai-news", language: str = "en") -> Dict[str, Any]:
    from types import SimpleNamespace

    from content_factory.trends import collect_trends

    channel = SimpleNamespace(
        id=channel_id,
        language=language,
        topics=["ai", "openai", "tech"] if language != "es" else ["ia", "tecnología", "cripto"],
    )
    return {"channel_id": channel_id, "trends": collect_trends(channel, None, [])}


def _tavily_key() -> str:
    _load_env_file()
    return (
        os.environ.get("TAVILY_API_KEY", "").strip()
        or os.environ.get("TAVILY_API_KEY_2", "").strip()
    )


def _google_news_search(query: str, max_results: int) -> Dict[str, Any]:
    """Безключевой fallback: Bing News RSS (доступен из РФ)."""
    import urllib.parse
    import xml.etree.ElementTree as ET

    params = urllib.parse.urlencode(
        {"q": str(query), "format": "RSS", "mkt": "en-US"}
    )
    url = f"https://www.bing.com/news/search?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "factory-mcp/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())
    results = []
    for item in root.findall(".//item")[:max_results]:
        results.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "url": (item.findtext("link") or "").strip(),
                "published": (item.findtext("pubDate") or "").strip(),
                "source": (item.findtext("source") or "").strip(),
            }
        )
    return {"query": query, "provider": "bing_news_rss", "results": results}


def tool_web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    limit = max(1, min(10, int(max_results)))
    key = _tavily_key()
    if key:
        body = json.dumps(
            {"api_key": key, "query": str(query), "max_results": limit}
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "factory-mcp/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            return {
                "query": query,
                "provider": "tavily",
                "answer": data.get("answer"),
                "results": [
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "content": (item.get("content") or "")[:400],
                    }
                    for item in (data.get("results") or [])
                ],
            }
        except Exception as exc:  # noqa: BLE001 - из РФ Tavily отдаёт 403, идём в RSS
            fallback = _google_news_search(query, limit)
            fallback["tavily_error"] = str(exc)
            return fallback
    return _google_news_search(query, limit)


def tool_factory_schema() -> Dict[str, Any]:
    """Список таблиц и колонок БД (аналог describe_table из SQLite MCP)."""
    conn = _connect()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        schema: Dict[str, List[Dict[str, Any]]] = {}
        for (table,) in [(row[0],) for row in tables][:30]:
            columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            schema[table] = [
                {"name": row[1], "type": row[2], "notnull": bool(row[3]), "pk": bool(row[5])}
                for row in columns
            ]
        return {"db": str(DB_PATH), "tables": schema}
    finally:
        conn.close()


def tool_hackernews_top(limit: int = 5) -> Dict[str, Any]:
    """Топ Hacker News (аналог mcp-hackernews, без ключа)."""
    count = max(1, min(20, int(limit)))
    url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={}".format(count)
    request = urllib.request.Request(url, headers={"User-Agent": "factory-mcp/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    hits = []
    for item in (data.get("hits") or [])[:count]:
        hits.append(
            {
                "title": item.get("title"),
                "url": item.get("url") or "https://news.ycombinator.com/item?id={}".format(item.get("objectID")),
                "points": item.get("points"),
                "comments": item.get("num_comments"),
                "created_at": item.get("created_at"),
            }
        )
    return {"provider": "hackernews", "items": hits}


# ---------------------------------------------------------------------------
# MCP (stdio JSON-RPC)
# ---------------------------------------------------------------------------
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "factory_status",
        "description": "Статус контент-фабрики: каналы, последние посты и запуски.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "factory_query",
        "description": "Read-only SQL (SELECT/WITH/PRAGMA) по базе фабрики.",
        "inputSchema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
    {
        "name": "trends_now",
        "description": "Актуальные тренды для канала (Google Trends RSS, CoinGecko, GitHub, HN).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string"},
                "language": {"type": "string", "enum": ["en", "es"]},
            },
        },
    },
    {
        "name": "factory_schema",
        "description": "Таблицы и колонки базы фабрики (read-only).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "hackernews_top",
        "description": "Топ Hacker News (front page) без API-ключа.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
        },
    },
    {
        "name": "web_search",
        "description": "Поиск в вебе через Tavily.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
]


def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
    if name == "factory_status":
        return tool_factory_status()
    if name == "factory_query":
        return tool_factory_query(arguments.get("sql", ""))
    if name == "factory_schema":
        return tool_factory_schema()
    if name == "hackernews_top":
        return tool_hackernews_top(arguments.get("limit") or 5)
    if name == "trends_now":
        return tool_trends_now(
            arguments.get("channel_id") or "ai-news",
            arguments.get("language") or "en",
        )
    if name == "web_search":
        return tool_web_search(arguments.get("query", ""), arguments.get("max_results") or 5)
    raise ValueError(f"неизвестный инструмент: {name}")


def _response(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: Dict[str, Any]) -> Dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return _response(
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
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(str(name), arguments if isinstance(arguments, dict) else {})
            return _response(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
                    ],
                    "isError": False,
                },
            )
        except Exception as exc:  # noqa: BLE001 - ошибка инструмента уходит клиенту
            return _response(
                request_id,
                {
                    "content": [{"type": "text", "text": f"Ошибка: {exc}"}],
                    "isError": True,
                },
            )
    return _error(request_id, -32601, f"метод не поддерживается: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(_error(None, -32700, "invalid JSON")) + "\n")
            sys.stdout.flush()
            continue
        try:
            result = handle(message)
        except Exception as exc:  # noqa: BLE001
            result = _error(message.get("id"), -32603, f"внутренняя ошибка: {exc}")
        if result is not None:
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
