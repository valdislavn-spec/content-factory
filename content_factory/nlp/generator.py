"""Генерация постов для Telegram в трёх форматах: story, digest, analysis.

Текст собирается только из фактов, найденных в кластере (резюме, тезисы,
цифры, цитаты источников), и оборачивается в Telegram HTML (b/i/a/code).
Любая пользовательская строка экранируется, ссылки берутся только из
``cluster.articles``. Если LLM доступна, она аккуратно переписывает заголовок,
«почему это важно» или вывод; ответ валидируется (без markdown, ссылок и
выдуманных цифр), иначе используется шаблон.

Обязательный режим — без LLM: шаблонный генератор даёт осмысленный текст и
полностью удовлетворяет контракт :class:`GeneratedPost`.

Язык поста берётся у канала (``channel.language``): по умолчанию русский,
для ``en``-каналов переключаются системный промпт, LLM-промпты, подписи
стилей, шаблонный fallback, дата и валидация ответов модели. Русское
поведение при этом не меняется.
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import urllib.parse
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..models import Analysis, ChannelConfig, GeneratedPost, StoryCluster, utcnow
from ..utils import (
    format_local,
    html_escape,
    localize,
    normalize_space,
    stable_id,
    strip_html,
    token_set,
    truncate,
)
from .extractive import split_sentences
from .lang import language_code
from .llm import LLMClient, clean_llm_output

LOGGER = logging.getLogger(__name__)

_ALLOWED_FORMATS = ("story", "digest", "analysis")
_ALLOWED_TAGS = frozenset({"b", "i", "a", "code"})
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
_NUM_RE = re.compile(r"\d+")
# Служебные хвосты заголовков: «GPT-5: главное», «...: что известно».
_GENERIC_TITLE_TAIL_RE = re.compile(
    r"^(?:главное|что\s+(?:известно|важно|нужно\s+знать)|подробности|условия|"
    r"реакция\s+рынка|всё,?\s+что\s+известно|все,?\s+что\s+известно|самое\s+важное|"
    r"обзор|итоги)\b",
    re.IGNORECASE,
)
# То же для английских заголовков: «GPT-5: what we know», «...: main».
_GENERIC_TITLE_TAIL_RE_EN = re.compile(
    r"^(?:main|what\s+(?:is\s+known|we\s+know|to\s+know|matters)|details|"
    r"highlights|explainer|explained|overview|summary|key\s+takeaways|"
    r"everything\s+we\s+know|all\s+we\s+know|the\s+latest|latest|update|updates|"
    r"analysis|recap|context)\b",
    re.IGNORECASE,
)
# То же для испанских заголовков: «GPT-5: lo que sabemos», «...: última hora».
_GENERIC_TITLE_TAIL_RE_ES = re.compile(
    r"^(?:claves|lo\s+que\s+(?:sabemos|hay\s+que\s+saber|necesitas\s+saber|"
    r"debes\s+saber|se\s+sabe)|todo\s+lo\s+que\s+(?:necesitas|debes)\s+saber|"
    r"\u00faltima\s+hora|\u00faltimas\s+noticias|as\u00ed\s+te\s+lo\s+contamos|"
    r"as\u00ed\s+lo\s+contamos|detalles|resumen|an\u00e1lisis|contexto|puntos\s+clave|"
    r"lo\s+esencial|explicado|explicador|en\s+directo|qu\u00e9\s+(?:pas\u00f3|se\s+sabe|"
    r"ha\s+pasado|hay\s+que\s+saber)|todo\s+sobre|principales\s+claves)\b",
    re.IGNORECASE,
)
_MAX_HEADLINE = 140
_DIGIT_EMOJI = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")
_DIGEST_SEPARATOR = "———"

# Проверки целевого языка (ru — кириллица, en — латиница без кириллицы).
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_CYRILLIC_WORD_RE = re.compile(r"[А-Яа-яЁё]{2,}")
# Диакритика входит в латинские слова: «más», «español», «información».
_LATIN_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")
_LATIN_LETTER_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
_EN_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
# Испанские месяцы в нижнем регистре: «6 nov 2026».
_ES_MONTHS = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)
# Подпись, если заголовок уже содержит «Главное» / «Key points» / «Claves».
_SHORT_SUMMARY_LABEL = {"ru": "Коротко", "en": "In short", "es": "En breve"}
# Слова-маркеры «важности» для выбора факта в блок «Почему это важно».
_WHY_MARKERS = {
    "ru": ("важн",),
    "en": (
        "important",
        "significan",
        "key",
        "critical",
        "impact",
        "matter",
        "risk",
        "challenge",
    ),
    "es": (
        "importan",
        "clave",
        "crític",
        "critic",
        "impact",
        "riesg",
        "desaf",
        "significativ",
        "relevante",
        "consecuenc",
    ),
}

_SYSTEM_WRITER = (
    "Ты — редактор новостного Telegram-канала. Пиши по-русски живо, но точно и "
    "нейтрально. Используй только факты из предоставленного текста: не придумывай "
    "события, цифры, имена, цитаты и ссылки. Без markdown и без пояснений."
)
_SYSTEM_WRITER_EN = (
    "You are an editor of a news Telegram channel. Write in English: lively but "
    "precise and neutral. Use only the facts from the provided text: never invent "
    "events, numbers, names, quotes or links. No markdown and no explanations."
)
_SYSTEM_WRITER_ES = (
    "Eres el editor de un canal de noticias de Telegram. Escribe en español "
    "neutro: con viveza, pero de forma precisa y neutral. Usa solo los hechos del "
    "texto proporcionado: no inventes acontecimientos, cifras, nombres, citas ni "
    "enlaces. Sin markdown y sin explicaciones."
)

# Подписи и маркеры для разных тональностей канала.
_TONE_STYLES: Dict[str, Dict[str, str]] = {
    "expert": {
        "lead": "📊",
        "bullet": "▪️",
        "summary": "Главное",
        "why": "Почему это важно",
        "analysis": "Разбор",
        "digest": "Дайджест",
        "context": "Контекст",
        "perspectives": "Что пишут источники",
        "numbers": "Цифры",
        "conclusion": "Вывод",
        "sources": "Источники",
    },
    "science": {
        "lead": "🔬",
        "bullet": "🔹",
        "summary": "Суть",
        "why": "Почему это важно",
        "analysis": "Разбор исследования",
        "digest": "Дайджест",
        "context": "Контекст",
        "perspectives": "Что пишут источники",
        "numbers": "Цифры",
        "conclusion": "Вывод",
        "sources": "Источники",
    },
    "friendly": {
        "lead": "✨",
        "bullet": "•",
        "summary": "Коротко о главном",
        "why": "Почему стоит знать",
        "analysis": "Разбор",
        "digest": "Дайджест",
        "context": "Контекст",
        "perspectives": "Что пишут разные источники",
        "numbers": "Цифры",
        "conclusion": "Что в итоге",
        "sources": "Источники",
    },
}

# Английские подписи тех же трёх тональностей; русские выше не меняются.
_TONE_STYLES_EN: Dict[str, Dict[str, str]] = {
    "expert": {
        "lead": "📊",
        "bullet": "▪️",
        "summary": "Key points",
        "why": "Why it matters",
        "analysis": "Analysis",
        "digest": "Digest",
        "context": "Context",
        "perspectives": "What sources say",
        "numbers": "Numbers",
        "conclusion": "Bottom line",
        "sources": "Sources",
    },
    "science": {
        "lead": "🔬",
        "bullet": "🔹",
        "summary": "In short",
        "why": "Why it matters",
        "analysis": "Research breakdown",
        "digest": "Digest",
        "context": "Context",
        "perspectives": "What sources say",
        "numbers": "Numbers",
        "conclusion": "Bottom line",
        "sources": "Sources",
    },
    "friendly": {
        "lead": "✨",
        "bullet": "•",
        "summary": "The short version",
        "why": "Why you should care",
        "analysis": "Analysis",
        "digest": "Digest",
        "context": "Context",
        "perspectives": "What different sources say",
        "numbers": "Numbers",
        "conclusion": "The bottom line",
        "sources": "Sources",
    },
}

# Испанские подписи тех же трёх тональностей; русские и английские не меняются.
_TONE_STYLES_ES: Dict[str, Dict[str, str]] = {
    "expert": {
        "lead": "📊",
        "bullet": "▪️",
        "summary": "Claves",
        "why": "Por qué importa",
        "analysis": "Análisis",
        "digest": "Resumen",
        "context": "Contexto",
        "perspectives": "Qué dicen las fuentes",
        "numbers": "Cifras",
        "conclusion": "Conclusión",
        "sources": "Fuentes",
    },
    "science": {
        "lead": "🔬",
        "bullet": "🔹",
        "summary": "Lo principal",
        "why": "Por qué importa",
        "analysis": "Análisis del estudio",
        "digest": "Resumen",
        "context": "Contexto",
        "perspectives": "Qué dicen las fuentes",
        "numbers": "Cifras",
        "conclusion": "Conclusión",
        "sources": "Fuentes",
    },
    "friendly": {
        "lead": "✨",
        "bullet": "•",
        "summary": "En breve",
        "why": "Por qué deberías saberlo",
        "analysis": "Análisis",
        "digest": "Resumen",
        "context": "Contexto",
        "perspectives": "Qué dicen las distintas fuentes",
        "numbers": "Cifras",
        "conclusion": "En conclusión",
        "sources": "Fuentes",
    },
}

_TONE_STYLES_BY_LANGUAGE: Dict[str, Dict[str, Dict[str, str]]] = {
    "ru": _TONE_STYLES,
    "en": _TONE_STYLES_EN,
    "es": _TONE_STYLES_ES,
}

# Подписи источников-заглушек по языку.
_SOURCE_LABELS = {"ru": "Источник", "en": "Source", "es": "Fuente"}


# ---------------------------------------------------------------------------
# Настройки, экранирование, HTML
# ---------------------------------------------------------------------------


def _setting(settings: Any, dotted: str, default: Any) -> Any:
    try:
        value = settings.get(dotted, default) if settings is not None else default
        return default if value is None else value
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Язык канала и языковые проверки
# ---------------------------------------------------------------------------


def _channel_language(channel: Any, lang: Optional[str] = None) -> str:
    """Целевой язык канала: ``ru`` (по умолчанию), ``en`` или ``es``."""
    if lang:
        return language_code(lang)
    return language_code(getattr(channel, "language", "") or "ru")


def _is_en(lang: Any) -> bool:
    return language_code(lang) == "en"


def _is_es(lang: Any) -> bool:
    return language_code(lang) == "es"


def _has_cyrillic(text: Any) -> bool:
    return bool(_CYRILLIC_RE.search(str(text or "")))


def _fits_language(text: Any, lang: str) -> bool:
    """Можно ли показывать фрагмент в посте на целевом языке.

    Для ``en`` и ``es`` отбрасываются фрагменты с кириллицей (например,
    русские факты/ракурсы, попавшие в анализ), для ``ru`` фильтра нет —
    поведение прежнее.
    """
    if _is_en(lang) or _is_es(lang):
        return not _has_cyrillic(text)
    return True


def _system_prompt(lang: str) -> str:
    if _is_en(lang):
        return _SYSTEM_WRITER_EN
    if _is_es(lang):
        return _SYSTEM_WRITER_ES
    return _SYSTEM_WRITER


def _format_date(
    channel: ChannelConfig, lang: str, dt: Any = None, with_time: bool = False
) -> str:
    """Дата поста: ru ``18.10.2026``, en ``Oct 18, 2026``, es ``18 oct 2026``."""
    dt = dt or utcnow()
    offset = int(getattr(channel, "timezone_offset", 0) or 0)
    if not (_is_en(lang) or _is_es(lang)):
        return format_local(dt, offset, with_time=with_time)
    local = localize(dt, offset)
    if local is None:
        return ""
    if _is_es(lang):
        date = f"{local.day} {_ES_MONTHS[local.month - 1]} {local.year}"
    else:
        date = f"{_EN_MONTHS[local.month - 1]} {local.day}, {local.year}"
    if with_time:
        return f"{date} {local.hour:02d}:{local.minute:02d}"
    return date


def _quote(text: str, lang: str) -> str:
    """Кавычки под язык: «...» для ru/es, “...” для en (текст уже экранирован)."""
    if _is_en(lang):
        return f"“{text}”"
    return f"«{text}»"


def _style(channel: ChannelConfig, lang: Optional[str] = None) -> Dict[str, str]:
    lang = _channel_language(channel, lang)
    styles = _TONE_STYLES_BY_LANGUAGE.get(lang, _TONE_STYLES)
    style = dict(styles["expert"])
    tone = str(getattr(channel, "tone", "") or "expert").strip().lower()
    style.update(styles.get(tone, {}))
    if not bool(getattr(channel, "emoji", True)):
        style["lead"] = ""
        style["bullet"] = "•"
    return style


def _escape(text: str) -> str:
    return html_escape(normalize_space(str(text or "")))


def _escape_url(url: str) -> str:
    return html_lib.escape(str(url or "").strip(), quote=True)


def _valid_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _link(title: str, url: str) -> str:
    return f'<a href="{_escape_url(url)}">{_escape(title or url)}</a>'


def _truncate_html(text: str, limit: int) -> str:
    """Жёстко обрезает HTML по лимиту, не разрывая теги и сущности."""
    if not text:
        return ""
    limit = max(1, int(limit))
    if len(text) <= limit:
        return text

    tokens = _TAG_SPLIT_RE.split(text)
    out: List[str] = []
    stack: List[str] = []
    used = 0
    truncated = False

    for token in tokens:
        if not token:
            continue
        if token.startswith("<") and token.endswith(">"):
            if used + len(token) > limit:
                truncated = True
                break
            closing = re.match(r"</\s*([A-Za-z0-9]+)", token)
            opening = re.match(r"<\s*([A-Za-z0-9]+)", token)
            if closing:
                tag = closing.group(1).lower()
                for index in range(len(stack) - 1, -1, -1):
                    if stack[index] == tag:
                        del stack[index]
                        break
            elif opening and not token.rstrip().endswith("/>"):
                tag = opening.group(1).lower()
                if tag in _ALLOWED_TAGS:
                    stack.append(tag)
            out.append(token)
            used += len(token)
            continue

        reserve = 1 + sum(len(f"</{tag}>") for tag in stack)
        budget = limit - reserve - used
        if budget <= 0:
            truncated = True
            break
        if len(token) > budget:
            piece = token[:budget]
            cut = max(piece.rfind(" "), piece.rfind("\n"))
            if cut > budget * 0.5:
                piece = piece[:cut]
            # Не рвём HTML-сущность вида &amp;.
            amp = piece.rfind("&")
            if amp != -1 and ";" not in piece[amp:]:
                piece = piece[:amp]
            piece = piece.rstrip().rstrip("&<")
            out.append(piece)
            used += len(piece)
            truncated = True
            break
        out.append(token)
        used += len(token)

    result = "".join(out)
    if truncated:
        result = result.rstrip()
        result = re.sub(r"&[A-Za-z0-9#]*$", "", result)
        result += "…"
        for tag in reversed(stack):
            result += f"</{tag}>"
    if len(result) > limit:
        result = result[: limit - 1].rstrip() + "…"
    return result


def _join_blocks(blocks: Sequence[Dict[str, Any]]) -> str:
    parts = [str(block.get("text", "")).strip() for block in blocks]
    return "\n\n".join(part for part in parts if part).strip()


def _fit_blocks(blocks: Sequence[Dict[str, Any]], limit: int) -> str:
    """Собирает блоки в лимит канала: сначала убирает необязательные части."""
    current = [dict(block) for block in blocks if str(block.get("text", "")).strip()]
    if not current:
        return ""
    text = _join_blocks(current)
    if len(text) <= limit:
        return text
    drop_order = sorted(
        (index for index, block in enumerate(current) if block.get("optional")),
        key=lambda index: -int(current[index].get("drop_priority", 0)),
    )
    for index in drop_order:
        current[index]["text"] = ""
        text = _join_blocks(current)
        if len(text) <= limit:
            return text
    return _truncate_html(_join_blocks(current), limit)


def _section(style: Dict[str, str], key: str) -> str:
    return f"<i>{style.get(key, key)}:</i>"


# ---------------------------------------------------------------------------
# Источники, заголовки, хештеги
# ---------------------------------------------------------------------------


def _display_fallback_source(url: str, lang: str = "ru") -> str:
    """Подпись источника, если название на другом языке: домен URL."""
    try:
        netloc = urllib.parse.urlsplit(str(url or "").strip()).netloc
    except ValueError:
        netloc = ""
    return normalize_space(netloc) or _SOURCE_LABELS.get(language_code(lang), "Источник")


def _extract_sources(cluster: StoryCluster, lang: str = "ru") -> List[Dict[str, str]]:
    """Реальные ссылки из кластера: [{title, url, source}], без выдумок."""
    sources: List[Dict[str, str]] = []
    seen = set()
    # Для en/es-поста подписи ссылок не должны содержать кириллицу.
    foreign = _is_en(lang) or _is_es(lang)
    fallback_label = _SOURCE_LABELS.get(language_code(lang), "Источник")
    for article in cluster.articles or []:
        url = str(getattr(article, "url", "") or "").strip()
        if not _valid_url(url) or url in seen:
            continue
        seen.add(url)
        title = normalize_space(strip_html(getattr(article, "title", "") or ""))
        source = normalize_space(
            getattr(article, "source_name", "") or getattr(article, "source_id", "") or ""
        )
        if foreign:
            if not title or _has_cyrillic(title):
                title = (
                    source
                    if source and not _has_cyrillic(source)
                    else _display_fallback_source(url, lang)
                )
            if not source or _has_cyrillic(source):
                source = _display_fallback_source(url, lang)
        elif not title:
            title = fallback_label
        sources.append({"title": title, "url": url, "source": source or title})
    return sources


def _strip_display_tail(title: str, lang: str = "ru") -> str:
    """Убирает служебный хвост заголовка после двоеточия: «GPT-5: главное».

    В источнике остаётся оригинальный title, а в посте — короткий заголовок
    без канцелярских «: главное», «: что известно», «: lo que sabemos» и т.п.
    """
    if ":" not in title:
        return title
    head, tail = title.split(":", 1)
    if _is_en(lang):
        pattern = _GENERIC_TITLE_TAIL_RE_EN
    elif _is_es(lang):
        pattern = _GENERIC_TITLE_TAIL_RE_ES
    else:
        pattern = _GENERIC_TITLE_TAIL_RE
    if pattern.match(tail.strip()):
        candidate = head.strip(" .,;:—-|")
        if len(candidate) >= 6:
            return candidate
    return title


def _headline(cluster: StoryCluster, analysis: Optional[Analysis] = None, lang: str = "ru") -> str:
    if _is_en(lang):
        placeholder = "News"
    elif _is_es(lang):
        placeholder = "Noticia"
    else:
        placeholder = "Новость"
    candidates: List[str] = []
    if cluster.title:
        candidates.append(strip_html(cluster.title))
    for article in (cluster.articles or [])[:2]:
        if getattr(article, "title", ""):
            candidates.append(strip_html(article.title))
    if analysis and analysis.summary:
        sentences = split_sentences(analysis.summary)
        if sentences:
            candidates.append(sentences[0])
    title = next(
        (
            normalize_space(candidate)
            for candidate in candidates
            if normalize_space(candidate) and _fits_language(candidate, lang)
        ),
        "",
    )
    if not title:
        return placeholder

    # Убираем хвостовое название источника, если оно приклеено к заголовку.
    for article in cluster.articles or []:
        source_name = normalize_space(getattr(article, "source_name", "") or "")
        if not source_name:
            continue
        for suffix in (f" — {source_name}", f" - {source_name}", f" | {source_name}", f" :: {source_name}"):
            if title.lower().endswith(suffix.lower()):
                title = title[: -len(suffix)].strip()

    title = _strip_display_tail(title, lang)
    title = title.strip(" .,;:—-|")
    if not title:
        return placeholder
    if len(title) > _MAX_HEADLINE:
        title = truncate(title, _MAX_HEADLINE, suffix="…")
    return title[:1].upper() + title[1:]


def _post_hashtags(
    channel: ChannelConfig, analysis: Optional[Analysis], lang: Optional[str] = None
) -> List[str]:
    lang = _channel_language(channel, lang)
    tags = [
        str(tag).strip()
        for tag in (getattr(channel, "hashtags", None) or [])
        if str(tag).strip() and _fits_language(tag, lang)
    ]
    if not tags and analysis is not None:
        for term in analysis.key_terms[:3]:
            if not _fits_language(term, lang):
                continue
            # Диакритика важна для испанских хэштегов: #economía, #España.
            cleaned = re.sub(
                r"[^0-9A-Za-zА-Яа-яЁё_ÁÉÍÓÚÜÑáéíóúüñ]",
                "",
                str(term).replace(" ", "_"),
            )
            if len(cleaned) >= 3:
                tags.append("#" + cleaned)
    result: List[str] = []
    seen = set()
    for tag in tags:
        normalized = tag if tag.startswith("#") else "#" + tag.replace(" ", "_")
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _sources_block(sources: Sequence[Dict[str, str]], style: Dict[str, str]) -> str:
    if not sources:
        return ""
    links = " · ".join(_link(item["source"] or item["title"], item["url"]) for item in sources[:4])
    return f"{_section(style, 'sources')}\n{links}"


def _hashtags_block(hashtags: Sequence[str]) -> str:
    if not hashtags:
        return ""
    return " ".join(_escape(tag) for tag in hashtags)


def _cta_block(channel: ChannelConfig, settings: Any, lang: Optional[str] = None) -> str:
    cta = str(getattr(channel, "cta", "") or "").strip()
    if not cta:
        cta = str(_setting(settings, "pipeline.cta", "") or "").strip()
    if not cta:
        return ""
    # Призыв к действию на чужом языке в en/es-посте не показываем.
    target = _channel_language(channel, lang)
    if (_is_en(target) or _is_es(target)) and _has_cyrillic(cta):
        return ""
    return f"<i>{_escape(cta)}</i>"


def _shorten(text: str, limit: int) -> str:
    text = normalize_space(str(text or ""))
    if not text:
        return ""
    if len(text) > limit:
        text = truncate(text, limit, suffix="…")
    return text.rstrip(" ,;:—-")


def _similar(a: str, b: str, threshold: float = 0.6) -> bool:
    tokens_a, tokens_b = token_set(a), token_set(b)
    if not tokens_a or not tokens_b:
        return False
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b) >= threshold


# ---------------------------------------------------------------------------
# LLM-хелперы (все ошибки гасятся, вывод строго валидируется)
# ---------------------------------------------------------------------------


def _llm_available(llm: Optional[LLMClient]) -> bool:
    return bool(llm is not None and getattr(llm, "available", False))


def _safe_generate(
    llm: Optional[LLMClient],
    prompt: str,
    max_tokens: int,
    temperature: float = 0.3,
    system: Optional[str] = None,
) -> str:
    if not _llm_available(llm):
        return ""
    try:
        raw = llm.generate(  # type: ignore[union-attr]
            prompt,
            system=_SYSTEM_WRITER if system is None else system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:  # клиент не должен бросать, но подстрахуемся
        LOGGER.warning("LLM не смогла сгенерировать текст поста: %s", exc)
        return ""
    return clean_llm_output(raw)


def _clean_multiline_output(raw: Any) -> str:
    """Чистит многострочный ответ LLM, сохраняя переводы строк (дайджест).

    ``clean_llm_output`` схлопывает пробелы и переводы строк в один абзац —
    для списка строк дайджеста это недопустимо, поэтому чистим построчно.
    """
    lines: List[str] = []
    for line in str(raw or "").splitlines():
        cleaned = clean_llm_output(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _safe_generate_multiline(
    llm: Optional[LLMClient],
    prompt: str,
    max_tokens: int,
    temperature: float = 0.3,
    system: Optional[str] = None,
) -> str:
    """LLM-генерация списка строк (дайджест): переводы строк сохраняются."""
    if not _llm_available(llm):
        return ""
    try:
        raw = llm.generate(  # type: ignore[union-attr]
            prompt,
            system=_SYSTEM_WRITER if system is None else system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:  # клиент не должен бросать, но подстрахуемся
        LOGGER.warning("LLM не смогла сгенерировать строки дайджеста: %s", exc)
        return ""
    return _clean_multiline_output(raw)


def _allowed_numbers(text: str) -> set:
    return set(_NUM_RE.findall(text or ""))


def _has_markup_artifacts(text: str) -> bool:
    """JSON/HTML/markdown-мусор от модели не должен попадать в пост."""
    return any(char in (text or "") for char in '{}[]<>`')


def _headline_fits_language(text: str, lang: str) -> bool:
    """Языковая проверка заголовка: ru — кириллица, en/es — латиница без кириллицы."""
    if _is_en(lang) or _is_es(lang):
        if _has_cyrillic(text):
            return False
        return bool(_LATIN_WORD_RE.search(text)) and len(_LATIN_LETTER_RE.findall(text)) >= 3
    return len(_CYRILLIC_WORD_RE.findall(text)) >= 1 and len(_CYRILLIC_RE.findall(text)) >= 3


def _sentence_fits_language(text: str, lang: str) -> bool:
    """Языковая проверка предложения: ru — кириллица, en/es — латиница без кириллицы."""
    if _is_en(lang) or _is_es(lang):
        return not _has_cyrillic(text) and len(_LATIN_WORD_RE.findall(text)) >= 3
    return len(_CYRILLIC_WORD_RE.findall(text)) >= 3


def _valid_llm_headline(text: str, source_text: str, lang: str = "ru") -> str:
    cleaned = clean_llm_output(text).strip().strip("«»\"“”'").strip(" .,:;—-")
    cleaned = _strip_display_tail(cleaned, lang).strip(" .,:;—-")
    if not 12 <= len(cleaned) <= _MAX_HEADLINE:
        return ""
    lowered = cleaned.lower()
    if "http://" in lowered or "https://" in lowered or "**" in cleaned or "```" in cleaned:
        return ""
    if _has_markup_artifacts(cleaned):
        return ""
    if not _headline_fits_language(cleaned, lang):
        return ""
    if not _allowed_numbers(cleaned) <= _allowed_numbers(source_text):
        return ""
    return cleaned[:1].upper() + cleaned[1:]


def _valid_llm_sentence(
    text: str, source_text: str, min_len: int = 25, max_len: int = 300, lang: str = "ru"
) -> str:
    cleaned = clean_llm_output(text).strip().strip("«»\"“”'").strip()
    if not min_len <= len(cleaned) <= max_len:
        return ""
    lowered = cleaned.lower()
    if "http://" in lowered or "https://" in lowered or "**" in cleaned or "```" in cleaned:
        return ""
    if _has_markup_artifacts(cleaned):
        return ""
    if not _sentence_fits_language(cleaned, lang):
        return ""
    if not _allowed_numbers(cleaned) <= _allowed_numbers(source_text):
        return ""
    if cleaned[-1] not in ".!?…":
        cleaned += "."
    return cleaned


def _llm_headline(
    cluster: StoryCluster,
    analysis: Analysis,
    source_text: str,
    llm: Optional[LLMClient],
    lang: str = "ru",
    compact: bool = True,
) -> str:
    """Заголовок LLM.

    ``compact=True`` — в промпт идёт уже проверенное резюме (200–400 символов)
    вместо 4000 символов исходного текста: экономия токенов без потери качества,
    потому что резюме построено по тому же тексту и прошло валидацию фактов.
    Проверка заголовка по-прежнему сверяется с полным ``source_text``.
    """
    headline = _headline(cluster, analysis, lang)
    if compact:
        points = "; ".join(analysis.bullets[:4]) or analysis.summary
        if _is_en(lang):
            prompt = (
                f"News headline: {headline}\n"
                f"Summary: {analysis.summary}\n"
                f"Key points: {points}\n\n"
                "Rewrite this news headline so it is shorter and more precise, in "
                "English. Do not add facts, numbers or links that are not in the text. "
                "Return only the headline, without quotes and without a trailing period."
            )
        elif _is_es(lang):
            prompt = (
                f"Noticia: {headline}\n"
                f"Resumen: {analysis.summary}\n"
                f"Puntos clave: {points}\n\n"
                "Reescribe este titular de forma más breve y precisa, en español. "
                "No añadas hechos, cifras ni enlaces que no estén en el texto. "
                "Devuelve solo el titular, sin comillas y sin punto final."
            )
        else:
            prompt = (
                f"Новость: {headline}\n"
                f"Резюме: {analysis.summary}\n"
                f"Тезисы: {points}\n\n"
                "Перепиши заголовок этой новости короче и точнее, на русском языке. "
                "Не добавляй факты, цифры и ссылки, которых нет в тексте. Верни только "
                "заголовок без кавычек и без точки в конце."
            )
    elif _is_en(lang):
        prompt = (
            f"News headline: {headline}\n"
            f"Source text:\n{source_text[:4000]}\n\n"
            "Rewrite this news headline so it is shorter and more precise, in "
            "English. Do not add facts, numbers or links that are not in the text. "
            "Return only the headline, without quotes and without a trailing period."
        )
    elif _is_es(lang):
        prompt = (
            f"Noticia: {headline}\n"
            f"Texto de las fuentes:\n{source_text[:4000]}\n\n"
            "Reescribe este titular de forma más breve y precisa, en español. "
            "No añadas hechos, cifras ni enlaces que no estén en el texto. "
            "Devuelve solo el titular, sin comillas y sin punto final."
        )
    else:
        prompt = (
            f"Новость: {headline}\n"
            f"Текст источников:\n{source_text[:4000]}\n\n"
            "Перепиши заголовок этой новости короче и точнее, на русском языке. "
            "Не добавляй факты, цифры и ссылки, которых нет в тексте. Верни только "
            "заголовок без кавычек и без точки в конце."
        )
    raw = _safe_generate(
        llm, prompt, max_tokens=80, temperature=0.3, system=_system_prompt(lang)
    )
    return _valid_llm_headline(raw, source_text, lang)


def _llm_why(
    analysis: Analysis, source_text: str, llm: Optional[LLMClient], lang: str = "ru"
) -> str:
    if _is_en(lang):
        prompt = (
            f"News summary: {analysis.summary}\n"
            f"Key points: {'; '.join(analysis.bullets)}\n\n"
            "Write one short sentence in English explaining why this news matters. "
            "Use only the text above, without invented facts or numbers. Return only "
            "the sentence."
        )
    elif _is_es(lang):
        prompt = (
            f"Resumen de la noticia: {analysis.summary}\n"
            f"Puntos clave: {'; '.join(analysis.bullets)}\n\n"
            "Escribe una frase corta en español que explique por qué esta noticia "
            "importa. Usa solo el texto anterior, sin hechos ni cifras inventados. "
            "Devuelve solo la frase."
        )
    else:
        prompt = (
            f"Резюме новости: {analysis.summary}\n"
            f"Тезисы: {'; '.join(analysis.bullets)}\n\n"
            "Сформулируй одно короткое предложение на русском: почему эта новость "
            "важна. Опирайся только на текст выше, без выдуманных фактов и цифр. "
            "Верни только предложение."
        )
    raw = _safe_generate(
        llm, prompt, max_tokens=120, temperature=0.3, system=_system_prompt(lang)
    )
    return _valid_llm_sentence(raw, source_text, min_len=25, max_len=280, lang=lang)


def _llm_conclusion(
    analysis: Analysis, source_text: str, llm: Optional[LLMClient], lang: str = "ru"
) -> str:
    if _is_en(lang):
        numbers = ", ".join(analysis.numbers) or "none"
        prompt = (
            f"News summary: {analysis.summary}\n"
            f"Key points: {'; '.join(analysis.bullets)}\n"
            f"Numbers from the text: {numbers}\n\n"
            "Write one neutral conclusion sentence in English strictly based on "
            "these facts. No invented events, numbers or links. Return only the "
            "sentence."
        )
    elif _is_es(lang):
        numbers = ", ".join(analysis.numbers) or "ninguna"
        prompt = (
            f"Resumen de la noticia: {analysis.summary}\n"
            f"Puntos clave: {'; '.join(analysis.bullets)}\n"
            f"Cifras del texto: {numbers}\n\n"
            "Escribe una conclusión neutral en español basada estrictamente en estos "
            "hechos. Sin acontecimientos, cifras ni enlaces inventados. Devuelve solo "
            "la frase."
        )
    else:
        prompt = (
            f"Резюме новости: {analysis.summary}\n"
            f"Тезисы: {'; '.join(analysis.bullets)}\n"
            f"Цифры из текста: {', '.join(analysis.numbers) or 'нет'}\n\n"
            "Сформулируй один нейтральный вывод на русском языке строго по этим "
            "фактам. Без выдуманных событий, цифр и ссылок. Верни только предложение."
        )
    raw = _safe_generate(
        llm, prompt, max_tokens=140, temperature=0.25, system=_system_prompt(lang)
    )
    return _valid_llm_sentence(raw, source_text, min_len=30, max_len=320, lang=lang)


def _llm_digest_lines(
    items: Sequence[Tuple[StoryCluster, Analysis]],
    source_text: str,
    llm: Optional[LLMClient],
    lang: str = "ru",
) -> List[str]:
    if not _llm_available(llm) or not items:
        return []
    lines = []
    for index, (cluster, analysis) in enumerate(items, start=1):
        lead = _shorten(analysis.summary or "", 160)
        lines.append(f"{index}. {_headline(cluster, analysis, lang)} — {lead}")
    if _is_en(lang):
        prompt = (
            "Below is the list of news items for a digest:\n" + "\n".join(lines) + "\n\n"
            "Give one short line in English for each news item (up to 150 characters). "
            "Strictly based on the facts from the list, without links and without "
            f"invented numbers. Return exactly {len(items)} lines without numbering, "
            "in the same order."
        )
    elif _is_es(lang):
        prompt = (
            "Abajo tienes la lista de noticias para un resumen:\n"
            + "\n".join(lines)
            + "\n\n"
            "Da una línea corta en español para cada noticia (hasta 150 caracteres). "
            "Estrictamente basada en los hechos de la lista, sin enlaces y sin cifras "
            f"inventadas. Devuelve exactamente {len(items)} líneas sin numeración, "
            "en el mismo orden."
        )
    else:
        prompt = (
            "Ниже список новостей для дайджеста:\n" + "\n".join(lines) + "\n\n"
            "Дай для каждой новости одну короткую строку на русском (до 150 символов). "
            "Строго по фактам из списка, без ссылок, без выдуманных цифр. Верни ровно "
            f"{len(items)} строк без нумерации, в том же порядке."
        )
    raw = _safe_generate_multiline(
        llm,
        prompt,
        max_tokens=120 * max(1, len(items)) + 80,
        temperature=0.3,
        system=_system_prompt(lang),
    )
    if not raw:
        return []
    parsed = [
        normalize_space(re.sub(r"^\s*(?:[-—•*·]|\d{1,2}[.)])\s*", "", line))
        for line in raw.splitlines()
        if normalize_space(line)
    ]
    parsed = [line for line in parsed if line]
    if len(parsed) != len(items):
        return []
    allowed = _allowed_numbers(source_text)
    result: List[str] = []
    for line in parsed:
        if not 15 <= len(line) <= 200:
            return []
        if "http://" in line.lower() or "https://" in line.lower() or "**" in line:
            return []
        if _has_markup_artifacts(line):
            return []
        if not _sentence_fits_language(line, lang):
            return []
        if not set(_NUM_RE.findall(line)) <= allowed:
            return []
        result.append(_shorten(line, 180))
    return result


# ---------------------------------------------------------------------------
# Текстовые блоки форматов
# ---------------------------------------------------------------------------


def _echoes_headline(text: str, headline: str) -> bool:
    """Проверяет, пересказывает ли предложение заголовок (Jaccard + difflib)."""
    if not text or not headline:
        return False
    if _similar(text, headline, threshold=0.6):
        return True
    left = normalize_space(text).lower()
    right = normalize_space(headline).lower()
    if not left or not right:
        return False
    return SequenceMatcher(None, left, right).ratio() >= 0.6


def _story_bullets(analysis: Analysis, headline: str = "", lang: str = "ru") -> List[str]:
    """2–4 тезиса для story без пересказа самого заголовка."""
    original = [
        normalize_space(bullet)
        for bullet in analysis.bullets
        if normalize_space(bullet) and _fits_language(bullet, lang)
    ]
    filtered = [bullet for bullet in original if not _echoes_headline(bullet, headline)]
    # Если фильтр оставил слишком мало тезисов, добираем факты из резюме.
    if len(filtered) < 2 and analysis.summary:
        for sentence in split_sentences(analysis.summary):
            sentence = normalize_space(sentence)
            if not _fits_language(sentence, lang):
                continue
            if _echoes_headline(sentence, headline):
                continue
            if any(_similar(sentence, existing, 0.75) for existing in filtered):
                continue
            filtered.append(sentence)
            if len(filtered) >= 2:
                break
    bullets = filtered if filtered else original
    shortened: List[str] = []
    for bullet in bullets:
        bullet = _shorten(bullet, 190)
        if not bullet or _echoes_headline(bullet, headline):
            continue
        if any(_similar(bullet, previous, 0.75) for previous in shortened):
            continue
        shortened.append(bullet)
    # Гарантируем хотя бы два пункта: иначе story теряет смысл.
    if len(shortened) < 2:
        for bullet in original:
            bullet = _shorten(bullet, 190)
            if not bullet or any(_similar(bullet, previous, 0.75) for previous in shortened):
                continue
            shortened.append(bullet)
            if len(shortened) >= 2:
                break
    return shortened[:4]


def _template_why(analysis: Analysis, cluster: StoryCluster, lang: str = "ru") -> str:
    """«Почему это важно» без выдумок: факт из текста, не повторяющий заголовок."""
    headline = _headline(cluster, analysis, lang)
    candidates: List[str] = []
    for sentence in split_sentences(analysis.summary):
        if "[…]" in sentence:
            # обрезанный сниппет источника — не факт для блока «Почему это важно»
            continue
        if not _fits_language(sentence, lang):
            continue
        if any(_similar(sentence, bullet, 0.6) for bullet in analysis.bullets):
            continue
        if _echoes_headline(sentence, headline):
            continue
        candidates.append(sentence)
    markers = _WHY_MARKERS.get(language_code(lang), _WHY_MARKERS["ru"])
    for sentence in candidates:
        lowered = sentence.lower()
        if _NUM_RE.search(sentence) or any(item in lowered for item in markers):
            return _shorten(sentence, 260)
    if candidates:
        return _shorten(candidates[0], 260)
    return ""


def _template_conclusion(analysis: Analysis, cluster: StoryCluster, lang: str = "ru") -> str:
    headline = _headline(cluster, analysis, lang)
    sentences = split_sentences(analysis.summary)
    context = sentences[:2]
    for sentence in reversed(sentences):
        if not _fits_language(sentence, lang):
            continue
        if any(_similar(sentence, other, 0.6) for other in context):
            continue
        if _echoes_headline(sentence, headline):
            continue
        return _shorten(sentence, 280)
    parts: List[str] = []
    count = int(analysis.source_count or 0)
    if _is_en(lang):
        if count >= 2:
            parts.append(f"The picture emerges from reports by {count} sources.")
        elif count == 1:
            parts.append("The information is based on a single source.")
        terms = [term for term in analysis.key_terms[:4] if _fits_language(term, lang)]
        if terms:
            parts.append(f"Key topics: {', '.join(terms)}.")
        return " ".join(parts)
    if _is_es(lang):
        if count >= 2:
            parts.append(f"El panorama surge de los mensajes de {count} fuentes.")
        elif count == 1:
            parts.append("La información se basa en una sola fuente.")
        terms = [term for term in analysis.key_terms[:4] if _fits_language(term, lang)]
        if terms:
            parts.append(f"Temas clave: {', '.join(terms)}.")
        return " ".join(parts)
    if count >= 2:
        parts.append(f"Картина складывается из сообщений {count} источников.")
    elif count == 1:
        parts.append("Информация основана на одном источнике.")
    if analysis.key_terms:
        parts.append(f"Ключевые темы: {', '.join(analysis.key_terms[:4])}.")
    return " ".join(parts)


def _numbers_block(analysis: Analysis, style: Dict[str, str], lang: str = "ru") -> str:
    numbers = [number for number in analysis.numbers if _fits_language(number, lang)]
    if not numbers:
        return ""
    chips = " · ".join(f"<code>{_escape(number)}</code>" for number in numbers[:5])
    return f"{_section(style, 'numbers')} {chips}"


def _perspectives_block(
    analysis: Analysis, style: Dict[str, str], lang: str = "ru"
) -> str:
    if not analysis.perspectives:
        return ""
    lines: List[str] = []
    foreign = _is_en(lang) or _is_es(lang)
    fallback_label = _SOURCE_LABELS.get(language_code(lang), "Источник")
    for perspective in analysis.perspectives[:4]:
        source = normalize_space(perspective.get("source_name", "")) or fallback_label
        quote = _shorten(perspective.get("quote", ""), 220)
        angle = _shorten(perspective.get("angle", ""), 120)
        if not quote and not angle:
            continue
        if foreign and (
            _has_cyrillic(source) or _has_cyrillic(quote) or _has_cyrillic(angle)
        ):
            # В en/es-пост не должны попадать русские цитаты/ракурсы.
            continue
        line = f"{style.get('bullet', '•')} <b>{_escape(source)}:</b>"
        if quote:
            line += f" {_quote(_escape(quote), lang)}"
        if angle and not _similar(angle, quote, 0.8):
            line += f" — {_escape(angle)}"
        lines.append(line)
    if not lines:
        return ""
    return f"{_section(style, 'perspectives')}\n" + "\n".join(lines)


def _build_story(
    cluster: StoryCluster,
    analysis: Analysis,
    channel: ChannelConfig,
    settings: Any,
    llm: Optional[LLMClient],
    style: Dict[str, str],
    sources: Sequence[Dict[str, str]],
    hashtags: Sequence[str],
    source_text: str,
    lang: str = "ru",
) -> Tuple[List[Dict[str, Any]], bool]:
    llm_used = False
    compact_headline = bool(_setting(settings, "llm.optimize.compact_headline", False))
    title = (
        _llm_headline(
            cluster, analysis, source_text, llm, lang, compact=compact_headline
        )
        if _llm_available(llm)
        else ""
    )
    if title:
        llm_used = True
    else:
        title = _headline(cluster, analysis, lang)

    blocks: List[Dict[str, Any]] = [{"text": f"<b>{_escape(title)}</b>"}]
    bullets = _story_bullets(analysis, title, lang)
    if bullets:
        lines = "\n".join(f"{style.get('bullet', '•')} {_escape(bullet)}" for bullet in bullets)
        summary_label = style.get("summary", "Главное")
        if summary_label.lower() in title.lower():
            # Заголовок уже содержит «главное» — не дублируем подпись.
            summary_label = _SHORT_SUMMARY_LABEL.get(language_code(lang), "Коротко")
        blocks.append({"text": f"<i>{summary_label}:</i>\n{lines}"})

    why = _llm_why(analysis, source_text, llm, lang) if _llm_available(llm) else ""
    if why:
        llm_used = True
    else:
        why = _template_why(analysis, cluster, lang)
    # «Почему это важно» не должно повторять уже показанный тезис.
    if why and any(_similar(why, bullet, 0.5) for bullet in bullets):
        why = ""
    if why:
        blocks.append(
            {
                "text": f"<b>{style.get('why', 'Почему это важно')}:</b> {_escape(why)}",
                "optional": True,
                "drop_priority": 90,
            }
        )

    sources_text = _sources_block(sources, style)
    if sources_text:
        blocks.append({"text": sources_text, "optional": True, "drop_priority": 70})
    cta_text = _cta_block(channel, settings, lang)
    if cta_text:
        blocks.append({"text": cta_text, "optional": True, "drop_priority": 100})
    tags_text = _hashtags_block(hashtags)
    if tags_text:
        blocks.append({"text": tags_text, "optional": True, "drop_priority": 80})
    return blocks, llm_used


def _build_analysis(
    cluster: StoryCluster,
    analysis: Analysis,
    channel: ChannelConfig,
    settings: Any,
    llm: Optional[LLMClient],
    style: Dict[str, str],
    sources: Sequence[Dict[str, str]],
    hashtags: Sequence[str],
    source_text: str,
    lang: str = "ru",
) -> Tuple[List[Dict[str, Any]], bool]:
    llm_used = False
    compact_headline = bool(_setting(settings, "llm.optimize.compact_headline", False))
    title = (
        _llm_headline(
            cluster, analysis, source_text, llm, lang, compact=compact_headline
        )
        if _llm_available(llm)
        else ""
    )
    if title:
        llm_used = True
    else:
        title = _headline(cluster, analysis, lang)

    blocks: List[Dict[str, Any]] = [
        {"text": f"<b>{style.get('analysis', 'Разбор')}: {_escape(title)}</b>"}
    ]

    context_sentences = [
        sentence
        for sentence in split_sentences(analysis.summary)[:2]
        if _fits_language(sentence, lang)
    ]
    if context_sentences:
        context = " ".join(_shorten(sentence, 300) for sentence in context_sentences)
        blocks.append({"text": f"{_section(style, 'context')}\n{_escape(context)}"})

    perspectives_text = _perspectives_block(analysis, style, lang)
    if perspectives_text:
        blocks.append({"text": perspectives_text, "optional": True, "drop_priority": 65})

    numbers_text = _numbers_block(analysis, style, lang)
    if numbers_text:
        blocks.append({"text": numbers_text, "optional": True, "drop_priority": 60})

    conclusion = _llm_conclusion(analysis, source_text, llm, lang) if _llm_available(llm) else ""
    if conclusion:
        llm_used = True
    else:
        conclusion = _template_conclusion(analysis, cluster, lang)
    if conclusion:
        blocks.append(
            {
                "text": f"<b>{style.get('conclusion', 'Вывод')}:</b> {_escape(conclusion)}",
                "optional": True,
                "drop_priority": 75,
            }
        )

    sources_text = _sources_block(sources, style)
    if sources_text:
        blocks.append({"text": sources_text, "optional": True, "drop_priority": 70})
    cta_text = _cta_block(channel, settings, lang)
    if cta_text:
        blocks.append({"text": cta_text, "optional": True, "drop_priority": 100})
    tags_text = _hashtags_block(hashtags)
    if tags_text:
        blocks.append({"text": tags_text, "optional": True, "drop_priority": 80})
    return blocks, llm_used


def _build_single_digest(
    cluster: StoryCluster,
    analysis: Analysis,
    channel: ChannelConfig,
    settings: Any,
    style: Dict[str, str],
    sources: Sequence[Dict[str, str]],
    hashtags: Sequence[str],
    lang: str = "ru",
) -> Tuple[List[Dict[str, Any]], bool]:
    date = _format_date(
        channel, lang, cluster.last_published or utcnow(), with_time=False
    )
    header = f"<b>{style.get('digest', 'Дайджест')} · {_escape(date)}</b>"
    blocks: List[Dict[str, Any]] = [{"text": header}]
    title = _headline(cluster, analysis, lang)
    blocks.append({"text": f"<b>{_escape(title)}</b>"})

    # Короткий лид, чтобы одиночный дайджест не выглядел пустым.
    for sentence in split_sentences(analysis.summary):
        if not _fits_language(sentence, lang):
            continue
        if not _similar(sentence, title, 0.6):
            blocks.append({"text": _escape(_shorten(sentence, 260))})
            break

    lines: List[str] = []
    for bullet in _story_bullets(analysis, title, lang)[:3]:
        lines.append(f"{style.get('bullet', '•')} {_escape(_shorten(bullet, 170))}")
    if not lines and sources:
        lines.append(f"<b>{_link(sources[0]['source'], sources[0]['url'])}</b>")
    if lines:
        blocks.append({"text": "\n".join(lines)})

    sources_text = _sources_block(sources, style)
    if sources_text:
        blocks.append({"text": sources_text, "optional": True, "drop_priority": 70})
    cta_text = _cta_block(channel, settings, lang)
    if cta_text:
        blocks.append({"text": cta_text, "optional": True, "drop_priority": 100})
    tags_text = _hashtags_block(hashtags)
    if tags_text:
        blocks.append({"text": tags_text, "optional": True, "drop_priority": 80})
    return blocks, False


# ---------------------------------------------------------------------------
# Проверки качества
# ---------------------------------------------------------------------------


def _quality_issues(
    text: str,
    channel: ChannelConfig,
    settings: Any,
    sources: Sequence[Dict[str, str]],
    lang: Optional[str] = None,
) -> List[str]:
    lang = _channel_language(channel, lang)
    issues: List[str] = []
    plain = normalize_space(strip_html(text))
    min_chars = int(_setting(settings, "pipeline.min_post_chars", 300) or 300)
    if not plain:
        issues.append("пустой текст поста")
    elif len(plain) < min_chars:
        issues.append(f"текст короче минимума ({len(plain)} < {min_chars})")
    banned = _setting(settings, "pipeline.banned_words", []) or []
    lowered = plain.lower()
    for word in banned:
        needle = str(word).strip().lower()
        if needle and needle in lowered:
            issues.append(f"запрещённое слово: {word}")
    if not sources:
        issues.append("нет источников со ссылками")
    if (_is_en(lang) or _is_es(lang)) and _has_cyrillic(plain):
        # Защитный сигнал: в en/es-посте осталась кириллица (например, из источника).
        issues.append(f"в {language_code(lang)}-посте осталась кириллица")
    if not plain and not sources:
        issues.append("нечего публиковать")
    return issues


def _normalize_format(fmt: Optional[str], channel: ChannelConfig) -> str:
    explicit = str(fmt or "").strip().lower()
    if explicit in _ALLOWED_FORMATS:
        return explicit
    allowed = [str(value).strip().lower() for value in (getattr(channel, "formats", None) or [])]
    for value in allowed:
        if value in _ALLOWED_FORMATS:
            return value
    return "story"


def _make_post(
    *,
    post_id: str,
    channel: ChannelConfig,
    cluster_id: str,
    fmt: str,
    blocks: Sequence[Dict[str, Any]],
    hashtags: Sequence[str],
    sources: Sequence[Dict[str, str]],
    settings: Any,
    llm_used: bool,
    llm: Optional[LLMClient],
    score: float,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> GeneratedPost:
    text = _fit_blocks(blocks, int(channel.max_post_chars))
    quality = _quality_issues(text, channel, settings, sources)
    meta: Dict[str, Any] = {
        "format": fmt,
        "tone": channel.tone,
        "generator": "llm" if llm_used else "extractive",
        "char_count": len(text),
        "plain_chars": len(normalize_space(strip_html(text))),
        "quality_issues": quality,
        "language": channel.language,
        "llm_provider": getattr(llm, "name", "extractive") if llm_used else "extractive",
    }
    if extra_meta:
        meta.update(extra_meta)
    return GeneratedPost(
        id=post_id,
        channel_id=channel.id,
        cluster_id=cluster_id,
        format=fmt,
        text=text,
        hashtags=list(hashtags),
        sources=[dict(item) for item in sources],
        score=float(score or 0.0),
        meta=meta,
    )


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def generate_post(
    cluster: StoryCluster,
    analysis: Analysis,
    channel: ChannelConfig,
    settings: Any,
    fmt: Optional[str] = None,
    llm: Optional[LLMClient] = None,
) -> GeneratedPost:
    """Генерирует один пост (story / analysis / digest) по кластеру."""
    if cluster is None:
        raise ValueError("generate_post: cluster обязателен")
    if channel is None:
        raise ValueError("generate_post: channel обязателен")
    analysis = analysis or Analysis()
    fmt = _normalize_format(fmt, channel)
    lang = _channel_language(channel)
    sources = _extract_sources(cluster, lang)
    hashtags = _post_hashtags(channel, analysis, lang)
    style = _style(channel, lang)
    source_text = normalize_space(cluster.combined_text or " ".join([analysis.summary] + list(analysis.bullets)))
    llm_used = False

    if fmt == "analysis":
        blocks, llm_used = _build_analysis(
            cluster, analysis, channel, settings, llm, style, sources, hashtags, source_text, lang
        )
    elif fmt == "digest":
        blocks, llm_used = _build_single_digest(
            cluster, analysis, channel, settings, style, sources, hashtags, lang
        )
    else:
        fmt = "story"
        blocks, llm_used = _build_story(
            cluster, analysis, channel, settings, llm, style, sources, hashtags, source_text, lang
        )

    return _make_post(
        post_id=stable_id(channel.id, cluster.id or _headline(cluster, analysis, lang), fmt),
        channel=channel,
        cluster_id=cluster.id or stable_id(cluster.title),
        fmt=fmt,
        blocks=blocks,
        hashtags=hashtags,
        sources=sources,
        settings=settings,
        llm_used=llm_used,
        llm=llm,
        score=cluster.score,
        extra_meta={"source_count": len(cluster.source_names)},
    )


def generate_digest(
    items: List[Tuple[StoryCluster, Analysis]],
    channel: ChannelConfig,
    settings: Any,
    llm: Optional[LLMClient] = None,
) -> GeneratedPost:
    """Генерирует дайджест из 3–5 коротких новостей со ссылками на источники."""
    if channel is None:
        raise ValueError("generate_digest: channel обязателен")
    normalized: List[Tuple[StoryCluster, Analysis]] = []
    for item in items or []:
        cluster: Optional[StoryCluster] = None
        analysis: Optional[Analysis] = None
        if isinstance(item, tuple) and len(item) >= 2:
            cluster, analysis = item[0], item[1]
        if cluster is None:
            continue
        normalized.append((cluster, analysis or Analysis()))
    normalized = normalized[:5]

    lang = _channel_language(channel)
    style = _style(channel, lang)
    hashtags = _post_hashtags(channel, normalized[0][1] if normalized else None, lang)
    date_source = utcnow()
    for cluster, _analysis in normalized:
        if cluster.last_published and cluster.last_published > date_source:
            date_source = cluster.last_published
    date = _format_date(channel, lang, date_source, with_time=False)
    if _is_en(lang):
        default_digest_label = "Digest"
    elif _is_es(lang):
        default_digest_label = "Resumen"
    else:
        default_digest_label = "Дайджест"
    digest_label = style.get("digest", default_digest_label)

    sources: List[Dict[str, str]] = []
    seen_urls = set()
    for cluster, _analysis in normalized:
        for source in _extract_sources(cluster, lang):
            if source["url"] in seen_urls:
                continue
            seen_urls.add(source["url"])
            sources.append(source)

    cluster_id = (
        "digest-" + stable_id(*[source["url"] for source in sources])
        if sources
        else "digest-" + stable_id(*[cluster.id for cluster, _analysis in normalized])
    )
    if not normalized:
        post = _make_post(
            post_id=stable_id(channel.id, cluster_id, "digest"),
            channel=channel,
            cluster_id=cluster_id,
            fmt="digest",
            blocks=[{"text": f"<b>{digest_label} · {_escape(date)}</b>"}],
            hashtags=hashtags,
            sources=[],
            settings=settings,
            llm_used=False,
            llm=llm,
            score=0.0,
            extra_meta={"items_count": 0, "quality_issues_extra": ["нет новостей для дайджеста"]},
        )
        post.meta["quality_issues"].append("нет новостей для дайджеста")
        return post

    source_text = "\n\n".join(
        normalize_space(cluster.combined_text or analysis.summary)
        for cluster, analysis in normalized
    )
    llm_lines = (
        _llm_digest_lines(normalized, source_text, llm, lang) if _llm_available(llm) else []
    )
    llm_used = bool(llm_lines)

    if _is_en(lang):
        channel_title = channel.title if not _has_cyrillic(channel.title) else "News digest"
        header = f"<b>{digest_label} — {_escape(channel_title)}: {_escape(date)}</b>"
    elif _is_es(lang):
        channel_title = (
            channel.title if not _has_cyrillic(channel.title) else "Resumen de noticias"
        )
        header = f"<b>{digest_label} — {_escape(channel_title)}: {_escape(date)}</b>"
    else:
        header = f"<b>{digest_label} «{_escape(channel.title)}»: {_escape(date)}</b>"
    blocks: List[Dict[str, Any]] = [{"text": header}]
    for index, (cluster, analysis) in enumerate(normalized):
        title = _headline(cluster, analysis, lang)
        one_line = (
            llm_lines[index] if llm_used else _digest_fallback_line(analysis, title, lang)
        )
        marker = _DIGIT_EMOJI[index] if channel.emoji and index < len(_DIGIT_EMOJI) else f"{index + 1}."
        item_sources = _extract_sources(cluster, lang)
        link = ""
        if item_sources:
            # Ссылка на источник — жирная, чтобы пункт читался отдельно.
            if _is_en(lang):
                default_link_label = "source"
            elif _is_es(lang):
                default_link_label = "fuente"
            else:
                default_link_label = "источник"
            link_label = item_sources[0]["source"] or default_link_label
            link = " " + f"<b>{_link(link_label, item_sources[0]['url'])}</b>"
        # Разделитель внутри блока помогает и в Telegram, и в plain-тексте dry-run,
        # где strip_html схлопывает переводы строк.
        text = f"{_DIGEST_SEPARATOR}\n{marker} <b>{_escape(title)}</b> — {_escape(one_line)}{link}"
        blocks.append({"text": text})

    cta_text = _cta_block(channel, settings, lang)
    if cta_text:
        blocks.append({"text": cta_text, "optional": True, "drop_priority": 100})
    tags_text = _hashtags_block(hashtags)
    if tags_text:
        blocks.append({"text": tags_text, "optional": True, "drop_priority": 80})
    sources_text = _sources_block(sources, style)
    if sources_text:
        blocks.append({"text": sources_text, "optional": True, "drop_priority": 70})

    score = max((float(cluster.score or 0.0) for cluster, _analysis in normalized), default=0.0)
    return _make_post(
        post_id=stable_id(channel.id, cluster_id, "digest"),
        channel=channel,
        cluster_id=cluster_id,
        fmt="digest",
        blocks=blocks,
        hashtags=hashtags,
        sources=sources,
        settings=settings,
        llm_used=llm_used,
        llm=llm,
        score=score,
        extra_meta={"items_count": len(normalized)},
    )


def _digest_fallback_line(analysis: Analysis, title: str, lang: str = "ru") -> str:
    for sentence in split_sentences(analysis.summary):
        if not _fits_language(sentence, lang):
            continue
        if not _similar(sentence, title, 0.65):
            return _shorten(sentence, 170)
    if _is_en(lang):
        numbers = [number for number in analysis.numbers[:3] if _fits_language(number, lang)]
        if numbers:
            return f"The reports mention numbers: {', '.join(numbers)}."
        terms = [term for term in analysis.key_terms[:4] if _fits_language(term, lang)]
        if terms:
            return f"Key topics: {', '.join(terms)}."
        return "Details are in the source article."
    if _is_es(lang):
        numbers = [number for number in analysis.numbers[:3] if _fits_language(number, lang)]
        if numbers:
            return f"Los informes mencionan estas cifras: {', '.join(numbers)}."
        terms = [term for term in analysis.key_terms[:4] if _fits_language(term, lang)]
        if terms:
            return f"Temas clave: {', '.join(terms)}."
        return "Los detalles están en el artículo de la fuente."
    if analysis.numbers:
        return f"В сообщениях упоминаются цифры: {', '.join(analysis.numbers[:3])}."
    if analysis.key_terms:
        return f"Ключевые темы: {', '.join(analysis.key_terms[:4])}."
    return "Подробности — в материале источника."
