"""Адаптер RSS 2.0 / RSS 1.0 (RDF) / Atom-лент.

Парсинг полностью на стандартной библиотеке (``xml.etree.ElementTree``):
учитываются пространства имён, CDATA, относительные ссылки, RFC-822 и
ISO-8601 даты, битые XML (частичное «лечение» типовых ошибок) и старые
кодировки вроде windows-1251. Если лента не содержит элементов — это не
ошибка: возвращается пустой список.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from ..config import Settings
from ..models import Article, SourceConfig
from ..utils import FetchError, http_get_text, normalize_url, parse_datetime, strip_html
from .base import (
    SourceAdapter,
    absolute_url,
    build_article,
    clean_title,
    extract_paragraphs,
    make_summary,
    max_text_chars,
    request_params,
)

# Сколько элементов ленты забирать по умолчанию.
DEFAULT_MAX_ITEMS = 30

_INVALID_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_NAMED_ENTITY_RE = re.compile(r"&([a-zA-Z][a-zA-Z0-9]{1,31});")
_BARE_AMP_RE = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#x[0-9a-fA-F]{1,6});)")

# Именованные HTML-сущности, которые часто встречаются в RSS вне CDATA.
# XML знает только amp/lt/gt/apos/quot, поэтому остальные заменяем символами.
_HTML_ENTITIES: Dict[str, str] = {
    "nbsp": "\u00a0",
    "mdash": "\u2014",
    "ndash": "\u2013",
    "hellip": "\u2026",
    "laquo": "\u00ab",
    "raquo": "\u00bb",
    "lsquo": "\u2018",
    "rsquo": "\u2019",
    "ldquo": "\u201c",
    "rdquo": "\u201d",
    "copy": "\u00a9",
    "reg": "\u00ae",
    "trade": "\u2122",
    "bull": "\u2022",
    "middot": "\u00b7",
    "deg": "\u00b0",
    "euro": "\u20ac",
    "pound": "\u00a3",
    "yen": "\u00a5",
    "times": "\u00d7",
    "plusmn": "\u00b1",
}

# Локальные имена тегов (без namespace) в порядке приоритета.
_TITLE_TAGS = ("title",)
_DATE_TAGS = {"pubdate", "published", "updated", "date", "created", "modified", "issued"}
_DESCRIPTION_TAGS = ("description", "summary", "content", "encoded", "subtitle")
_AUTHOR_TAGS = ("author", "creator", "contributor")


def _local_name(tag: Any) -> str:
    """Имя тега без пространства имён в нижнем регистре."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _first_child(element: ET.Element, names: Tuple[str, ...]) -> Optional[ET.Element]:
    wanted = set(names)
    for child in element:
        if _local_name(child.tag) in wanted:
            return child
    return None


def _children(element: ET.Element, names: Tuple[str, ...]) -> List[ET.Element]:
    wanted = set(names)
    return [child for child in element if _local_name(child.tag) in wanted]


def _element_text(element: Optional[ET.Element]) -> str:
    """Весь текст элемента (включая вложенные теги), без HTML-обёрток."""
    if element is None:
        return ""
    try:
        raw = "".join(element.itertext())
    except (RecursionError, TypeError):  # pragma: no cover - защита от мусора
        raw = element.text or ""
    return strip_html(raw)


_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|avif)(?:[?#]|$)", re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img[^>]+src=[\"\']([^\"\']+)[\"\']", re.IGNORECASE)


def _attr_url(element: ET.Element) -> str:
    for name in ("url", "href", "src"):
        value = str(element.get(name) or "").strip()
        if value:
            return value
    return ""


def _entry_image(entry: ET.Element, base_url: str) -> str:
    """Картинка новости из enclosure/media:content/media:thumbnail/img в тексте."""
    candidates = []
    for child in entry.iter():
        name = _local_name(child.tag)
        if name in ("enclosure", "content", "thumbnail", "image"):
            url = _attr_url(child)
            if not url:
                continue
            element_type = str(child.get("type") or "").lower()
            candidates.append((url, element_type))
    for url, element_type in candidates:
        if "image" in element_type or _IMAGE_EXT_RE.search(url):
            resolved = absolute_url(base_url, url)
            if resolved:
                return resolved
    for tag in _DESCRIPTION_TAGS + ("content", "encoded"):
        element = _first_child(entry, (tag,))
        if element is None:
            continue
        html_text = "".join(element.itertext())
        match = _IMG_TAG_RE.search(html_text)
        if match:
            resolved = absolute_url(base_url, match.group(1))
            if resolved:
                return resolved
    return ""


def _sanitize_xml(text: str) -> str:
    """Лечит типовые ошибки RSS: голые «&», HTML-сущности, управляющие символы."""
    text = _INVALID_XML_CHARS_RE.sub("", text)

    def replace_entity(match: "re.Match[str]") -> str:
        name = match.group(1).lower()
        return _HTML_ENTITIES.get(name, match.group(0))

    text = _NAMED_ENTITY_RE.sub(replace_entity, text)
    text = _BARE_AMP_RE.sub("&amp;", text)
    return text


def _parse_xml(text: str) -> ET.Element:
    """Разбирает XML ленты; при типовых дефектах пробует «починить» его."""
    cleaned = (text or "").lstrip("\ufeff \t\r\n")
    if not cleaned:
        raise FetchError("Источник вернул пустой ответ вместо XML")
    try:
        return ET.fromstring(cleaned)
    except (ET.ParseError, ValueError) as first_error:
        recovered = _sanitize_xml(cleaned)
        if recovered != cleaned:
            try:
                return ET.fromstring(recovered)
            except (ET.ParseError, ValueError):
                pass
        raise FetchError(f"Не удалось разобрать XML источника: {first_error}") from first_error


def _entry_elements(root: ET.Element) -> List[ET.Element]:
    """Находит элементы item (RSS/RDF) или entry (Atom) на любом уровне."""
    entries: List[ET.Element] = []
    for element in root.iter():
        if _local_name(element.tag) in ("item", "entry"):
            entries.append(element)
    if entries:
        return entries
    # Иногда корень сам является item/entry (фрагмент ленты).
    return [root] if _local_name(root.tag) in ("item", "entry") else []


def _entry_link(entry: ET.Element, base_url: str) -> str:
    """Ссылка на материал: RSS <link>, Atom <link href>, guid/enclosure."""
    candidates: List[Tuple[str, str]] = []
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = (child.get("href") or (child.text or "")).strip()
        if not href:
            continue
        rel = (child.get("rel") or "").strip().lower()
        candidates.append((rel, href))

    for rel, href in candidates:
        if rel in ("", "alternate") and not href.lower().startswith(("mailto:", "javascript:")):
            resolved = absolute_url(base_url, href)
            if resolved:
                return resolved

    for fallback_name in ("guid", "id"):
        element = _first_child(entry, (fallback_name,))
        if element is not None:
            resolved = absolute_url(base_url, _element_text(element))
            if resolved:
                return resolved

    enclosure = _first_child(entry, ("enclosure",))
    if enclosure is not None:
        resolved = absolute_url(base_url, enclosure.get("url", ""))
        if resolved:
            return resolved

    for _rel, href in candidates:
        resolved = absolute_url(base_url, href)
        if resolved:
            return resolved
    return ""


def _entry_published(entry: ET.Element):
    """Дата публикации: RFC-822/ISO; первая успешно распознанная."""
    for child in entry:
        if _local_name(child.tag) not in _DATE_TAGS:
            continue
        parsed = parse_datetime(_element_text(child))
        if parsed is not None:
            return parsed
    return None


def _entry_author(entry: ET.Element) -> str:
    element = _first_child(entry, _AUTHOR_TAGS)
    if element is None:
        return ""
    name_element = _first_child(element, ("name",))
    value = _element_text(name_element) if name_element is not None else _element_text(element)
    return make_summary(value, 120)


def _entry_categories(entry: ET.Element) -> List[str]:
    tags: List[str] = []
    for child in entry:
        if _local_name(child.tag) != "category":
            continue
        value = child.get("term") or child.get("label") or _element_text(child)
        value = make_summary(value, 80)
        if value and value not in tags:
            tags.append(value)
    return tags


def _positive_int(value: Any, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


class RSSAdapter(SourceAdapter):
    """Адаптер RSS/Atom-лент.

    Поддерживаемые options:
      * ``max_items`` — сколько материалов забрать (по умолчанию 30);
      * ``full_text`` — true, чтобы дополнительно скачать страницу статьи
        и извлечь текст абзацев (по умолчанию false).
    """

    type = "rss"

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        options = source.options or {}
        max_items = _positive_int(options.get("max_items"), DEFAULT_MAX_ITEMS)
        full_text = bool(options.get("full_text", False))

        params = request_params(settings)
        try:
            text = http_get_text(
                source.url,
                timeout=params["timeout"],
                user_agent=params["user_agent"],
                retries=params["retries"],
            )
        except FetchError:
            raise
        except Exception as exc:  # pragma: no cover - http_get_text сам бросает FetchError
            raise FetchError(f"Ошибка загрузки RSS {source.url}: {exc}") from exc

        root = _parse_xml(text)
        entries = _entry_elements(root)
        if not entries:
            return []

        articles: List[Article] = []
        seen_urls: set = set()
        for entry in entries:
            if len(articles) >= max_items:
                break
            url = _entry_link(entry, source.url)
            if not url:
                continue
            url_key = normalize_url(url)
            if not url_key or url_key in seen_urls:
                continue
            seen_urls.add(url_key)

            title = clean_title(_element_text(_first_child(entry, _TITLE_TAGS)))

            # Описание и текст: у части лент <description> пустой, а материал
            # лежит в <content:encoded> (или наоборот). Собираем всех непустых
            # кандидатов: первый — для summary, самый длинный — как текст
            # статьи, если он достаточно содержательный.
            candidates: List[str] = []
            for child in entry:
                if _local_name(child.tag) not in _DESCRIPTION_TAGS:
                    continue
                value = strip_html("".join(child.itertext()))
                if value:
                    candidates.append(value)
            description = make_summary(candidates[0]) if candidates else ""
            article_text = ""
            if candidates:
                longest = max(candidates, key=len)
                if len(longest) >= 400:
                    article_text = longest[: max_text_chars(settings)]
            if not title:
                title = make_summary(description, 160)
            if not title:
                continue

            published_at = _entry_published(entry)
            if full_text:
                article_text = self._fetch_article_text(url, settings) or article_text
            summary = description or make_summary(article_text)

            tags = _entry_categories(entry)
            guid_element = _first_child(entry, ("guid", "id"))
            meta = {
                "guid": _element_text(guid_element),
                "author": _entry_author(entry),
                "categories": tags,
                "feed_url": source.url,
            }
            image = _entry_image(entry, source.url)
            if image:
                meta["image"] = image
            article = build_article(
                source=source,
                settings=settings,
                url=url,
                title=title,
                published_at=published_at,
                text=article_text,
                summary=summary,
                tags=tags,
                meta=meta,
            )
            if article is not None:
                articles.append(article)
        return articles

    def _fetch_article_text(self, url: str, settings: Settings) -> str:
        """Догружает страницу статьи и извлекает абзацы (для options.full_text)."""
        params = request_params(settings)
        try:
            page = http_get_text(
                url,
                timeout=params["timeout"],
                user_agent=params["user_agent"],
                retries=params["retries"],
            )
        except Exception:
            # Полный текст — необязательное обогащение, без него статья валидна.
            return ""
        return extract_paragraphs(page, limit=max_text_chars(settings))


__all__ = ["RSSAdapter", "DEFAULT_MAX_ITEMS"]
