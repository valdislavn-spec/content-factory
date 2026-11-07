"""Доменные модели контент-завода."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Article:
    """Новость, полученная из MCP-инструмента (RSS/API)."""

    index: int
    title: str
    url: str
    summary: str = ""
    source: str = ""
    published: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "source": self.source,
            "published": self.published,
        }

    def as_source(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
        }


@dataclass
class ToolCall:
    """Запись о вызове MCP-инструмента для run-лога."""

    server: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    ms: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "server": self.server,
            "name": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "ms": self.ms,
            "error": self.error,
        }
