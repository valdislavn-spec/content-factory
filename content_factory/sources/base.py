"""Базовый контракт адаптеров источников и общие помощники.

Адаптер источника — это класс с атрибутом ``type`` и двумя методами:
``fetch`` (получить статьи) и ``check`` (быстро проверить доступность).
Все адаптеры возвращают только модели из ``content_factory.models``, чтобы
конвейер не зависел от формата конкретного источника (RSS/HTML/Telegram).
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

from ..config import Settings
from ..models import Article, SourceConfig, utcnow
from ..utils import (
    DEFAULT_USER_AGENT,
    FetchError,
    normalize_space,
    normalize_url,
    strip_html,
    url_hash,
)

# Абзацы новостной страницы, которые имеет смысл склеивать в текст статьи.
_PARAGRAPH_TAGS = {"p", "h1", "h2", "h3", "blockquote", "li", "figcaption"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "form", "nav", "footer", "header"}


class SourceAdapter:
    """Базовый класс адаптера источника.

    Наследники обязаны задать ``type`` и реализовать ``fetch``. Метод
    ``check`` по умолчанию загружает источник с минимальным лимитом элементов,
    поэтому наследникам достаточно переопределить ``_probe_options``, если
    лимит задаётся не через ``options.max_items``.
    """

    type: str = "base"

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        """Загружает статьи источника. Ошибки сети/формата — ``FetchError``."""
        raise NotImplementedError(f"Адаптер {type(self).__name__} не реализует fetch()")

    def check(self, source: SourceConfig, settings: Settings) -> Tuple[bool, str]:
        """Быстрая проверка доступности: не бросает исключений."""
        try:
            probe = replace(source, options={**source.options, **self._probe_options()})
            articles = self.fetch(probe, settings)
        except FetchError as exc:
            return False, str(exc)[:500]
        except Exception as exc:  # pragma: no cover - защита от неожиданных ошибок
            return False, f"Ошибка проверки источника {source.id}: {type(exc).__name__}: {exc}"[:500]
        if not articles:
            return True, "Источник доступен, но элементов не найдено"
        return True, f"Источник доступен, получено статей: {len(articles)}"

    def _probe_options(self) -> Dict[str, Any]:
        """Опции, которые ``check`` подмешивает к source.options."""
        return {"max_items": 2}


# ---------------------------------------------------------------------------
# Общие помощники: настройки запроса, ссылки, язык, сборка Article
# ---------------------------------------------------------------------------


def source_budget(source: SourceConfig, settings: Settings) -> Any:
    """Суточный лимит запросов к API-источнику (``options.daily_limit``).

    Квота общая на аккаунт, поэтому счётчик хранится по типу источника
    (``data/source_<type>_usage.json``), а не по каналу. ``None`` — лимит не задан.
    """
    try:
        limit = int((source.options or {}).get("daily_limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        return None
    try:
        data_dir = getattr(settings, "data_dir")
    except Exception:  # pragma: no cover - нестандартные настройки
        return None
    from ..nlp.budget import DailyBudget

    return DailyBudget(data_dir / "source_{}_usage.json".format(source.type), limit)


def request_params(settings: Settings) -> Dict[str, Any]:
    """Параметры HTTP-запроса из настроек (таймаут, повторы, User-Agent)."""
    timeout = getattr(settings, "request_timeout", 20.0)
    retries = getattr(settings, "request_retries", 2)
    user_agent = getattr(settings, "user_agent", "") or DEFAULT_USER_AGENT
    try:
        timeout_value = float(timeout) if timeout else 20.0
    except (TypeError, ValueError):
        timeout_value = 20.0
    try:
        retries_value = max(0, int(retries))
    except (TypeError, ValueError):
        retries_value = 2
    return {"timeout": timeout_value, "retries": retries_value, "user_agent": str(user_agent)}


def language_of(settings: Settings) -> str:
    """Язык материалов проекта (по умолчанию русский)."""
    try:
        app = settings.app
    except Exception:  # pragma: no cover - на случай нестандартных настроек
        return "ru"
    if isinstance(app, dict):
        return str(app.get("language") or "ru")
    return "ru"


def max_text_chars(settings: Settings) -> int:
    """Сколько символов текста статьи отдавать в анализ."""
    try:
        pipeline = settings.pipeline
    except Exception:  # pragma: no cover
        return 15000
    if isinstance(pipeline, dict):
        try:
            return max(1000, int(pipeline.get("max_text_chars", 15000)))
        except (TypeError, ValueError):
            return 15000
    return 15000


def absolute_url(base_url: str, link: str) -> str:
    """Превращает относительную ссылку в абсолютную; мусор -> пустая строка."""
    link = (link or "").strip()
    if not link:
        return ""
    try:
        resolved = urllib.parse.urljoin(base_url or "", link)
        parsed = urllib.parse.urlsplit(resolved)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return resolved


def _host(url: str) -> str:
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return re.sub(r"^www\.", "", host)


def same_domain(base_url: str, url: str) -> bool:
    """Совпадает ли домен ссылки с доменом источника (поддомены разрешены)."""
    base_host = _host(base_url)
    host = _host(url)
    if not base_host or not host:
        return False
    if base_host == host:
        return True
    return host.endswith("." + base_host)


def build_article(
    source: SourceConfig,
    settings: Settings,
    url: str,
    title: str,
    published_at: Any = None,
    text: str = "",
    summary: str = "",
    tags: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[Article]:
    """Собирает Article с корректными id/url_hash/весом источника.

    Возвращает ``None``, если URL невалиден — такую запись нельзя
    дедуплицировать и сохранять.
    """
    if not url:
        return None
    key = url_hash(url)
    title = normalize_space(strip_html(title)) or "Без заголовка"
    payload: Dict[str, Any] = {
        "url_hash": key,
        "source_type": source.type,
        "feed_url": source.url,
    }
    if meta:
        payload.update(meta)
    return Article(
        id=key,
        title=title,
        url=url,
        source_id=source.id,
        source_name=source.name,
        published_at=published_at or utcnow(),
        text=normalize_space(text),
        summary=normalize_space(summary),
        language=language_of(settings),
        tags=[t for t in (tags or []) if t][:10],
        weighted_source_score=float(source.weight or 1.0),
        meta=payload,
    )


# ---------------------------------------------------------------------------
# Извлечение текста статьи из HTML (для options.full_text)
# ---------------------------------------------------------------------------


class _ParagraphParser(HTMLParser):
    """Собирает текст абзацев страницы, пропуская script/style/nav и т.п."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: List[str] = []
        self._buffer: List[str] = []
        self._in_paragraph = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _PARAGRAPH_TAGS:
            self._flush()
            self._in_paragraph = True
        elif tag == "br" and self._in_paragraph:
            self._buffer.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _PARAGRAPH_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_paragraph and not self._skip_depth:
            self._buffer.append(data)

    def _flush(self) -> None:
        if not self._in_paragraph:
            return
        text = normalize_space("".join(self._buffer))
        self._buffer = []
        self._in_paragraph = False
        if len(text) >= 15:
            self.paragraphs.append(text)

    def result(self) -> List[str]:
        self._flush()
        return self.paragraphs


def extract_paragraphs(html: str, limit: int = 15000) -> str:
    """Достаёт читаемый текст из HTML страницы: абзацы через пустую строку."""
    if not html:
        return ""
    parser = _ParagraphParser()
    try:
        parser.feed(html)
        parser.close()
        paragraphs = parser.result()
    except Exception:  # pragma: no cover - защита от совсем битого HTML
        paragraphs = []
    if not paragraphs:
        plain = strip_html(html)
        return plain[:limit]
    text = "\n\n".join(paragraphs)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def clean_title(value: str, limit: int = 200) -> str:
    """Нормализует заголовок и обрезает по границе слова."""
    text = normalize_space(strip_html(value or ""))
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def make_summary(text: str, limit: int = 400) -> str:
    """Короткое описание статьи для анализа и дедупликации."""
    text = normalize_space(strip_html(text or ""))
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for separator in (". ", "! ", "? ", " "):
        position = cut.rfind(separator)
        if position > limit * 0.6:
            return cut[: position + (1 if separator[0] in ".!?" else 0)].rstrip() + "…"
    return cut.rstrip() + "…"


def normalized_source_url(source: SourceConfig) -> str:
    """URL источника без UTM-меток — для сравнений и логов."""
    return normalize_url(source.url or "")


__all__ = [
    "SourceAdapter",
    "absolute_url",
    "build_article",
    "clean_title",
    "extract_paragraphs",
    "language_of",
    "make_summary",
    "max_text_chars",
    "normalized_source_url",
    "request_params",
    "same_domain",
]
