"""Адаптер локальных документов: PDF/Word/PowerPoint/Excel/Markdown как источник.

Каталог задаётся в ``options.dir`` (по умолчанию ``data/inbox``); документы
конвертируются в Markdown автоматически и кэшируются в ``<dir>/.markdown``,
поэтому повторные прогоны не тратят время на конвертацию.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..config import Settings
from ..ingest import SUPPORTED_EXTENSIONS, IngestError, ensure_markdown
from ..models import Article, SourceConfig
from ..utils import FetchError
from .base import SourceAdapter, build_article

log = logging.getLogger("content_factory.sources.docs")

_HEADING_RE = re.compile(r"^#{1,2}\s+(.+?)\s*$", re.MULTILINE)
_CACHE_DIR_NAME = ".markdown"


def _extract_title(text: str, path: Path) -> str:
    """Заголовок документа: первый markdown-заголовок или первая строка."""
    match = _HEADING_RE.search(text)
    if match:
        return match.group(1).strip()[:200]
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


class DocsAdapter(SourceAdapter):
    """Читает локальные документы как статьи (тип источника ``docs``)."""

    type = "docs"

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        options: Dict[str, Any] = source.options or {}
        raw_dir = str(options.get("dir") or "data/inbox").strip()
        base = Path(raw_dir).expanduser()
        if not base.is_absolute():
            base = Path(settings.root) / base
        if not base.is_dir():
            raise FetchError(f"Каталог документов не найден: {base}")
        try:
            limit = max(int(options.get("max_items") or 30), 1)
        except (TypeError, ValueError):
            limit = 30
        extensions = {
            str(ext).lower() if str(ext).startswith(".") else "." + str(ext).lower()
            for ext in (options.get("extensions") or sorted(SUPPORTED_EXTENSIONS))
        }
        cache_dir = base / _CACHE_DIR_NAME
        articles: List[Article] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file() or _CACHE_DIR_NAME in path.parts:
                continue
            if path.suffix.lower() not in extensions:
                continue
            relative = path.relative_to(base)
            try:
                md_path, converted = ensure_markdown(path, cache_dir / relative.parent)
            except IngestError as exc:
                log.warning("Пропущен документ %s: %s", path, exc)
                continue
            try:
                text = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                log.warning("Не удалось прочитать %s: %s", md_path, exc)
                continue
            title = _extract_title(text, path)
            try:
                published_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                published_at = None
            article = build_article(
                source,
                settings,
                url="file://" + md_path.resolve().as_posix(),
                title=title,
                published_at=published_at,
                text=text,
                meta={
                    "document": str(path.resolve()),
                    "format": path.suffix.lower().lstrip("."),
                    "converted": converted,
                },
            )
            if article is not None:
                articles.append(article)
        articles.sort(key=lambda item: item.published_at, reverse=True)
        return articles[:limit]

    def _probe_options(self) -> Dict[str, Any]:
        return {"max_items": 2}
