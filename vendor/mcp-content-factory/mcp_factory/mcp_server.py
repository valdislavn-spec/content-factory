"""Демо MCP-сервер контент-завода (stdio, JSON-RPC 2.0).

Инструменты:
* fetch_rss      — получить RSS/Atom (включая sample:// для офлайн-демо);
* list_channels  — список каналов;
* save_draft     — сохранить черновик в out/drafts;
* publish_telegram — dry-run или реальная публикация (если разрешено);
* get_metrics    — простая статистика;
* health         — проверка живости.

Сервер поддерживает modern MCP 2026-07-28 (stateless, _meta в каждом
запросе) и legacy 2025-11-25 (initialize handshake), чтобы его можно было
подключить и к новым, и к старым MCP-хостам.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .rendering import render_post
from .utils import slugify, strip_html, truncate

MODERN_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"
LEGACY_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

LOGGER = logging.getLogger("mcp_factory.server")


class ToolError(RuntimeError):
    """Ошибка исполнения инструмента (возвращается с isError=true)."""


# ---------------------------------------------------------------------------
# Инструменты
# ---------------------------------------------------------------------------


class ContentTools:
    """Локальные инструменты контент-завода."""

    def __init__(self, root: Path, allow_publish: bool = False):
        self.root = Path(root).resolve()
        self.allow_publish = bool(allow_publish)
        self.samples = Path(__file__).resolve().parent.parent / "samples"
        self.drafts_dir = self.root / "drafts"
        self.outbox_dir = self.root / "outbox"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    # -- schema -----------------------------------------------------------

    def definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "fetch_rss",
                "title": "Fetch RSS/Atom feed",
                "description": (
                    "Скачать RSS/Atom-ленту и вернуть список новостей. "
                    "Для офлайн-демо поддерживаются sample://ai-news и "
                    "sample://business-news."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL ленты или sample://..."},
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 10,
                        },
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "list_channels",
                "title": "List channels",
                "description": "Вернуть список каналов контент-завода.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "save_draft",
                "title": "Save draft",
                "description": (
                    "Сохранить готовый пост в out/drafts. Принимает заголовок, "
                    "тело и список источников; сам добавляет блок источников."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "url": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": ["channel", "title", "body"],
                },
            },
            {
                "name": "publish_telegram",
                "title": "Publish to Telegram",
                "description": (
                    "Опубликовать текст в Telegram. По умолчанию dry-run: "
                    "пишет файл в out/outbox. Реальная отправка — только если "
                    "сервер запущен с --allow-publish и задан TELEGRAM_BOT_TOKEN."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["chat_id", "text"],
                },
            },
            {
                "name": "get_metrics",
                "title": "Get metrics",
                "description": "Простая статистика по черновикам и outbox.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "health",
                "title": "Health check",
                "description": "Проверка, что сервер и каталоги доступны.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        handlers = {
            "fetch_rss": self.fetch_rss,
            "list_channels": self.list_channels,
            "save_draft": self.save_draft,
            "publish_telegram": self.publish_telegram,
            "get_metrics": self.get_metrics,
            "health": self.health,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ToolError("неизвестный инструмент: {}".format(name))
        if not isinstance(arguments, dict):
            raise ToolError("arguments должен быть объектом")
        return handler(arguments)

    # -- tools ------------------------------------------------------------

    def fetch_rss(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        url = str(arguments.get("url") or "").strip()
        if not url:
            raise ToolError("url обязателен")
        try:
            limit = int(arguments.get("limit", 10))
        except (TypeError, ValueError):
            raise ToolError("limit должен быть числом")
        limit = max(1, min(limit, 50))

        if url.startswith("sample://"):
            name = url.split("://", 1)[1]
            if not re.match(r"^[a-z0-9-]+$", name):
                raise ToolError("некорректное имя sample-ленты")
            path = self.samples / (name + ".xml")
            if not path.exists():
                raise ToolError("sample-лента не найдена: {}".format(url))
            raw = path.read_bytes()
            source_label = "sample:" + name
        else:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise ToolError("разрешены только http(s):// и sample://")
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "MCPContentFactory/1.0 (+local demo)",
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    raw = response.read(2_000_001)
            except urllib.error.HTTPError as exc:
                raise ToolError("HTTP {} при загрузке {}".format(exc.code, url))
            except urllib.error.URLError as exc:
                raise ToolError("сеть: {}".format(exc.reason))
            if len(raw) > 2_000_000:
                raise ToolError("лента больше 2 МБ — отказ")
            source_label = parsed.netloc

        items = self._parse_feed(raw, limit=limit)
        if not items:
            raise ToolError("в ленте не найдено ни одной новости")
        return {"source": url, "label": source_label, "count": len(items), "items": items}

    def list_channels(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "channels": [
                {"id": "tech-ai", "title": "Технологии и ИИ"},
                {"id": "business-finance", "title": "Бизнес и финансы"},
                {"id": "science-health", "title": "Наука и здоровье"},
                {"id": "auto", "title": "Авто и транспорт"},
                {"id": "travel", "title": "Путешествия"},
                {"id": "culture", "title": "Культура"},
            ]
        }

    def save_draft(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        channel = slugify(str(arguments.get("channel") or "tech-ai"), "tech-ai")
        title = str(arguments.get("title") or "").strip()
        body = str(arguments.get("body") or "").strip()
        sources = arguments.get("sources") or []
        if not title:
            raise ToolError("title обязателен")
        if not body:
            raise ToolError("body обязателен")
        if not isinstance(sources, list):
            raise ToolError("sources должен быть списком")

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        filename = "{}-{}.md".format(channel, stamp)
        path = self.drafts_dir / filename
        markdown = render_post(title, body, sources)
        path.write_text(markdown, encoding="utf-8")

        sidecar = path.with_suffix(".json")
        sidecar.write_text(
            json.dumps(
                {
                    "channel": channel,
                    "title": title,
                    "body": body,
                    "sources": sources,
                    "created_at": stamp,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "path": str(path),
            "bytes": len(markdown.encode("utf-8")),
            "channel": channel,
            "title": title,
        }

    def publish_telegram(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        chat_id = str(arguments.get("chat_id") or "").strip()
        text = str(arguments.get("text") or "").strip()
        if not chat_id:
            raise ToolError("chat_id обязателен")
        if not text:
            raise ToolError("text обязателен")
        if len(text) > 4096:
            text = text[:4092] + "…"

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

        if not self.allow_publish or not token:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = self.outbox_dir / "telegram-{}.txt".format(stamp)
            path.write_text(text, encoding="utf-8")
            reason = "allow_publish=false" if not self.allow_publish else "нет TELEGRAM_BOT_TOKEN"
            return {"status": "dry_run", "reason": reason, "path": str(path)}

        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.telegram.org/bot{}/sendMessage".format(token),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raise ToolError("Telegram HTTP {}: публикация не удалась".format(exc.code))
        except urllib.error.URLError as exc:
            raise ToolError("Telegram: сеть {}".format(exc.reason))
        if not data.get("ok"):
            raise ToolError("Telegram: {}".format(data.get("description") or "ошибка"))
        return {"status": "published", "message_id": (data.get("result") or {}).get("message_id")}

    def get_metrics(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        drafts = list(self.drafts_dir.glob("*.md"))
        outbox = list(self.outbox_dir.glob("*.txt"))
        return {
            "drafts": len(drafts),
            "outbox": len(outbox),
            "root": str(self.root),
        }

    def health(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ok",
            "root": str(self.root),
            "allow_publish": self.allow_publish,
            "samples": str(self.samples),
        }

    # -- feed parsing -----------------------------------------------------

    def _parse_feed(self, raw: bytes, limit: int) -> List[Dict[str, str]]:
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ToolError("не удалось разобрать XML: {}".format(exc))
        items: List[Dict[str, str]] = []
        for element in root.iter():
            tag = self._localname(element.tag)
            if tag not in ("item", "entry"):
                continue
            title = self._child_text(element, "title")
            if not title:
                continue
            link = self._link(element)
            summary = self._child_text(element, "description") or self._child_text(
                element, "summary"
            )
            if not summary:
                summary = self._child_text(element, "content")
            published = (
                self._child_text(element, "pubDate")
                or self._child_text(element, "published")
                or self._child_text(element, "updated")
                or self._child_text(element, "date")
            )
            items.append(
                {
                    "title": " ".join(title.split()),
                    "link": link,
                    "summary": truncate(strip_html(summary), 500),
                    "published": self._normalize_date(published),
                }
            )
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _localname(tag: str) -> str:
        return tag.split("}", 1)[1].lower() if "}" in tag else tag.lower()

    @staticmethod
    def _child_text(element: ET.Element, name: str) -> str:
        for child in list(element):
            if ContentTools._localname(child.tag) == name:
                return "".join(child.itertext()).strip()
        return ""

    @staticmethod
    def _link(element: ET.Element) -> str:
        for child in list(element):
            if ContentTools._localname(child.tag) != "link":
                continue
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
        return ""

    @staticmethod
    def _normalize_date(value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed.astimezone(datetime.timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed.astimezone(datetime.timezone.utc).isoformat()
        except ValueError:
            return value


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------


class MCPServer:
    """JSON-RPC 2.0 поверх stdio."""

    def __init__(self, tools: ContentTools, name: str = "content-tools", version: str = "1.0.0"):
        self.tools = tools
        self.server_info = {"name": name, "version": version}
        self.legacy = False
        self._tools_cache: Optional[List[Dict[str, Any]]] = None

    # -- public -----------------------------------------------------------

    def serve(self) -> None:
        LOGGER.info("MCP-сервер запущен, root=%s", self.tools.root)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self._write_error(None, -32700, "Parse error")
                continue
            if isinstance(message, list):
                self._write_error(None, -32600, "Batch requests не поддерживаются")
                continue
            if not isinstance(message, dict):
                self._write_error(None, -32600, "Invalid Request")
                continue
            try:
                self._handle_message(message)
            except Exception as exc:  # noqa: BLE001 — сервер не должен падать
                LOGGER.exception("необработанная ошибка")
                request_id = message.get("id")
                if request_id is not None:
                    self._write_error(request_id, -32603, "Internal error: {}".format(exc))
        LOGGER.info("stdin закрыт — сервер завершает работу")

    # -- dispatch ---------------------------------------------------------

    def _handle_message(self, message: Dict[str, Any]) -> None:
        if message.get("jsonrpc") != "2.0":
            self._write_error(message.get("id"), -32600, "Invalid Request: jsonrpc")
            return
        method = message.get("method")
        if not isinstance(method, str):
            self._write_error(message.get("id"), -32600, "Invalid Request: method")
            return
        request_id = message.get("id")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        if request_id is None:
            # Уведомление: ответа быть не должно.
            if method == "notifications/initialized":
                self.legacy = True
            return

        if method == "initialize":
            self._handle_legacy_initialize(request_id, params)
            return

        if self.legacy:
            self._handle_legacy(request_id, method, params)
            return

        self._handle_modern(request_id, method, params)

    # -- modern -----------------------------------------------------------

    def _handle_modern(self, request_id: Any, method: str, params: Dict[str, Any]) -> None:
        meta = params.get("_meta")
        if not isinstance(meta, dict):
            self._write_error(request_id, -32602, "Missing _meta with protocol fields")
            return
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        if not isinstance(version, str):
            self._write_error(request_id, -32602, "Missing protocolVersion in _meta")
            return
        if version != MODERN_VERSION:
            self._write_error(
                request_id,
                -32022,
                "Unsupported protocol version",
                data={"supported": [MODERN_VERSION], "requested": version},
            )
            return
        capabilities = meta.get("io.modelcontextprotocol/clientCapabilities")
        if not isinstance(capabilities, dict):
            self._write_error(request_id, -32602, "Missing clientCapabilities in _meta")
            return

        if method == "server/discover":
            self._result(
                request_id,
                {
                    "supportedVersions": [MODERN_VERSION, LEGACY_VERSION],
                    "capabilities": {"tools": {"listChanged": False}},
                    "instructions": (
                        "Инструменты контент-завода: fetch_rss, list_channels, "
                        "save_draft, publish_telegram, get_metrics, health."
                    ),
                    "ttlMs": 60000,
                    "cacheScope": "public",
                },
                modern=True,
            )
            return
        if method == "tools/list":
            self._result(
                request_id,
                {
                    "tools": self._tools(),
                    "ttlMs": 60000,
                    "cacheScope": "public",
                },
                modern=True,
            )
            return
        if method == "tools/call":
            self._handle_tools_call(request_id, params, modern=True)
            return
        self._write_error(request_id, -32601, "Method not found: {}".format(method))

    # -- legacy -----------------------------------------------------------

    def _handle_legacy_initialize(self, request_id: Any, params: Dict[str, Any]) -> None:
        requested = str(params.get("protocolVersion") or "")
        chosen = requested if requested in LEGACY_VERSIONS else LEGACY_VERSION
        self.legacy = True
        self._write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": chosen,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": self.server_info,
                },
            }
        )

    def _handle_legacy(self, request_id: Any, method: str, params: Dict[str, Any]) -> None:
        if method == "tools/list":
            self._result(request_id, {"tools": self._tools()}, modern=False)
            return
        if method == "tools/call":
            self._handle_tools_call(request_id, params, modern=False)
            return
        if method == "ping":
            self._result(request_id, {}, modern=False)
            return
        self._write_error(request_id, -32601, "Method not found: {}".format(method))

    # -- tools ------------------------------------------------------------

    def _tools(self) -> List[Dict[str, Any]]:
        if self._tools_cache is None:
            self._tools_cache = self.tools.definitions()
        return self._tools_cache

    def _handle_tools_call(self, request_id: Any, params: Dict[str, Any], modern: bool) -> None:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            self._write_error(request_id, -32602, "name обязателен")
            return
        if not isinstance(arguments, dict):
            self._write_error(request_id, -32602, "arguments должен быть объектом")
            return
        known = {tool["name"] for tool in self._tools()}
        if name not in known:
            self._write_error(request_id, -32602, "Unknown tool: {}".format(name))
            return
        try:
            payload = self.tools.call(name, arguments)
        except ToolError as exc:
            self._result(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
                modern=modern,
            )
            return
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("инструмент %s упал", name)
            self._result(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": "внутренняя ошибка: {}".format(exc)}
                    ],
                    "isError": True,
                },
                modern=modern,
            )
            return

        text = json.dumps(payload, ensure_ascii=False)
        result: Dict[str, Any] = {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }
        if isinstance(payload, (dict, list)):
            result["structuredContent"] = payload
        self._result(request_id, result, modern=modern)

    # -- wire -------------------------------------------------------------

    def _result(self, request_id: Any, result: Dict[str, Any], modern: bool) -> None:
        if modern:
            result = dict(result)
            result.setdefault("resultType", "complete")
            meta = dict(result.get("_meta") or {})
            meta["io.modelcontextprotocol/serverInfo"] = self.server_info
            result["_meta"] = meta
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _write_error(
        self, request_id: Any, code: int, message: str, data: Any = None
    ) -> None:
        error: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._write({"jsonrpc": "2.0", "id": request_id, "error": error})

    @staticmethod
    def _write(message: Dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp_factory.mcp_server",
        description="MCP-сервер контент-завода (stdio)",
    )
    parser.add_argument(
        "--root",
        default="out",
        help="каталог для drafts/outbox (по умолчанию out)",
    )
    parser.add_argument(
        "--allow-publish",
        action="store_true",
        help="разрешить реальную публикацию в Telegram (нужен TELEGRAM_BOT_TOKEN)",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="уровень логов в stderr",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )
    tools = ContentTools(Path(args.root), allow_publish=args.allow_publish)
    server = MCPServer(tools)
    server.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
