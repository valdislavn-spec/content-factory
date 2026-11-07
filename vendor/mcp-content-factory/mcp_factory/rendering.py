"""Форматирование итогового поста (общее для оркестратора и MCP-сервера)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def normalize_sources(sources: Iterable[Any]) -> List[Dict[str, str]]:
    """Привести источники к списку словарей title/url/source."""
    result: List[Dict[str, str]] = []
    for item in sources or []:
        if isinstance(item, str):
            result.append({"title": item, "url": "", "source": ""})
        elif isinstance(item, dict):
            result.append(
                {
                    "title": str(item.get("title") or item.get("url") or "источник"),
                    "url": str(item.get("url") or ""),
                    "source": str(item.get("source") or ""),
                }
            )
    return result


def render_post(title: str, body: str, sources: Iterable[Any]) -> str:
    """Собрать markdown-пост: заголовок, тело, блок источников."""
    title = " ".join((title or "").split()) or "Без заголовка"
    body = (body or "").strip()
    lines = ["# " + title, "", body, "", "---", "", "**Источники:**", ""]
    prepared = normalize_sources(sources)
    if not prepared:
        lines.append("_Источники не указаны._")
    else:
        for index, source in enumerate(prepared, start=1):
            label = source["title"].replace("[", "(").replace("]", ")")
            if source["url"]:
                line = "{}. [{}](<{}>)".format(index, label, source["url"])
            else:
                line = "{}. {}".format(index, label)
            if source["source"]:
                line += " — " + source["source"]
            lines.append(line)
    return "\n".join(lines).rstrip() + "\n"
