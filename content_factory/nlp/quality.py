"""Детерминированный рубрикатор качества постов (без сети и без LLM).

Модуль оценивает готовый пост по набору правил: хук/первая строка, структура
абзацев, длина относительно лимита канала, ссылки на источники и валидность
Telegram-HTML, число хэштегов, наличие CTA, повторы предложений, капс,
читабельность, насыщенность фактами, кликбейт (RU/EN/ES), эмодзи и утечки
markdown. Все проверки — регулярные выражения и подсчёты по тексту, поэтому
оценка воспроизводима: один и тот же пост всегда получает один и тот же балл.

Публичный API:

* :class:`QualityIssue` — одна проблема: код, важность, сообщение, штраф.
* :class:`QualityReport` — score 0..100, список issues и metrics.
* :func:`score_post` — оценка поста (``GeneratedPost`` или строка).

Балл считается штрафами от 100: ``score = max(0, 100 - sum(penalties))``.
Проблемы уровня ``blocker`` — то, из-за чего пост нельзя публиковать
(пустой текст, короче минимума, нет источников, битый HTML). Остальные
(``major``/``minor``) — предупреждения: они снижают балл, но сами по себе
не блокируют публикацию, если не включён гейт ``pipeline.quality_gate``
(см. :func:`content_factory.pipeline.quality_issues` и docs/post-quality.md).

Модуль используют конвейер (метрики в ``post.meta`` и опциональный гейт) и
тесты; он не зависит от генератора, чтобы его можно было применять и к
постам из внешних генераторов (Dify и т.п.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..utils import normalize_space, split_sentences, strip_html
from .lang import language_code

# ---------------------------------------------------------------------------
# Важность проблем и пороги рубрики
# ---------------------------------------------------------------------------

BLOCKER = "blocker"
MAJOR = "major"
MINOR = "minor"
SEVERITIES = (BLOCKER, MAJOR, MINOR)

# Пороговые значения подобраны под новостные Telegram-каналы завода.
HOOK_TARGET = 90          # целевая длина хука (первой строки), символов
HOOK_MAX = 120            # длина, после которой хук считается «полотном»
HASHTAG_MIN = 2
HASHTAG_MAX = 5
LONG_PARAGRAPH_CHARS = 700
LONG_SENTENCE_WORDS = 45
AVG_SENTENCE_WORDS_WARN = 24
AVG_SENTENCE_WORDS_BAD = 30
EMOJI_MAX = 8
EMOJI_HARD_MAX = 12
FACT_DENSITY_MIN = 1.0    # фактов на 1000 символов: ниже — major
FACT_DENSITY_WARN = 2.5   # ниже — minor
DUPLICATE_SIMILARITY = 0.85

_ALLOWED_TAGS = frozenset(
    {"b", "i", "a", "code", "u", "s", "blockquote", "pre", "em", "strong", "br"}
)
_SAFE_SCHEMES = ("http://", "https://", "tg://", "mailto:")


# ---------------------------------------------------------------------------
# Структуры данных
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualityIssue:
    """Одна проблема качества поста.

    ``code`` — машиночитаемый код (``too_short``, ``clickbait``, ...),
    ``severity`` — ``blocker``/``major``/``minor``, ``penalty`` — сколько
    баллов снимается со 100, ``dimension`` — измерение рубрики.
    """

    code: str
    severity: str
    message: str
    penalty: int = 0
    dimension: str = ""

    @property
    def is_blocker(self) -> bool:
        return self.severity == BLOCKER

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "penalty": int(self.penalty),
            "dimension": self.dimension,
        }

    def __str__(self) -> str:  # pragma: no cover - удобно в логах
        return self.message


@dataclass
class QualityReport:
    """Результат оценки поста.

    ``score`` — целое 0..100, ``issues`` — найденные проблемы,
    ``metrics`` — измеримые характеристики текста (для графиков и отладки).
    """

    score: int = 0
    issues: List[QualityIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    channel_id: str = ""
    language: str = "ru"
    format: str = ""

    @property
    def blockers(self) -> List[QualityIssue]:
        return [issue for issue in self.issues if issue.is_blocker]

    @property
    def warnings(self) -> List[QualityIssue]:
        return [issue for issue in self.issues if not issue.is_blocker]

    @property
    def majors(self) -> List[QualityIssue]:
        return [issue for issue in self.issues if issue.severity == MAJOR]

    @property
    def minors(self) -> List[QualityIssue]:
        return [issue for issue in self.issues if issue.severity == MINOR]

    @property
    def ok(self) -> bool:
        """Нет блокирующих проблем (предупреждения допустимы)."""
        return not self.blockers

    @property
    def penalty(self) -> int:
        return sum(int(issue.penalty or 0) for issue in self.issues)

    def has_blockers(self) -> bool:
        return bool(self.blockers)

    def codes(self) -> List[str]:
        return [issue.code for issue in self.issues]

    def messages(self, severity: Optional[str] = None) -> List[str]:
        return [
            issue.message
            for issue in self.issues
            if severity is None or issue.severity == severity
        ]

    def as_dict(self) -> Dict[str, Any]:
        """JSON-совместимое представление — кладётся в ``post.meta``."""
        return {
            "score": int(self.score),
            "channel_id": self.channel_id,
            "language": self.language,
            "format": self.format,
            "issues": [issue.as_dict() for issue in self.issues],
            "metrics": dict(self.metrics),
        }

    def summary(self) -> str:  # pragma: no cover - для логов/convenience
        parts = ", ".join(issue.code for issue in self.issues[:5]) or "ok"
        return f"quality score={self.score} ({parts})"


# ---------------------------------------------------------------------------
# Вспомогательные функции: настройки и текст
# ---------------------------------------------------------------------------


def _setting(settings: Any, dotted: str, default: Any) -> Any:
    """Читает настройку из Settings/FakeSettings/словаря без падений."""
    if settings is None:
        return default
    getter = getattr(settings, "get", None)
    if callable(getter):
        try:
            value = getter(dotted, default)
        except Exception:  # noqa: BLE001 - нестандартный Settings не должен ломать оценку
            value = default
        return default if value is None else value
    if isinstance(settings, Mapping):
        node: Any = settings
        for part in dotted.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return default
            node = node[part]
        return default if node is None else node
    return default


def _channel_attr(channel: Any, name: str, default: Any) -> Any:
    if channel is None:
        return default
    if isinstance(channel, Mapping):
        value = channel.get(name, default)
    else:
        value = getattr(channel, name, default)
    return default if value is None else value


def _post_fields(post: Any) -> Tuple[str, List[Dict[str, Any]], List[str], str, Dict[str, Any]]:
    """Достаёт text/sources/hashtags/format/meta из GeneratedPost, dict или строки."""
    if isinstance(post, str):
        return post, [], [], "", {}
    if isinstance(post, Mapping):
        text = str(post.get("text") or "")
        sources = [dict(item) for item in (post.get("sources") or []) if isinstance(item, Mapping)]
        hashtags = [str(tag) for tag in (post.get("hashtags") or []) if str(tag).strip()]
        fmt = str(post.get("format") or "")
        meta = dict(post.get("meta") or {})
        return text, sources, hashtags, fmt, meta
    text = str(getattr(post, "text", "") or "")
    sources = [
        dict(item)
        for item in (getattr(post, "sources", None) or [])
        if isinstance(item, Mapping)
    ]
    hashtags = [
        str(tag) for tag in (getattr(post, "hashtags", None) or []) if str(tag).strip()
    ]
    fmt = str(getattr(post, "format", "") or "")
    meta = getattr(post, "meta", None)
    meta = dict(meta) if isinstance(meta, Mapping) else {}
    return text, sources, hashtags, fmt, meta


def _add(
    issues: List[QualityIssue],
    code: str,
    severity: str,
    message: str,
    penalty: int,
    dimension: str,
) -> None:
    issues.append(
        QualityIssue(
            code=code,
            severity=severity,
            message=message,
            penalty=int(penalty),
            dimension=dimension,
        )
    )


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _tokens(text: str) -> List[str]:
    return re.findall(r"[\w-]+", normalize_space(str(text or "")).lower())


def _similarity(a: str, b: str) -> float:
    left = normalize_space(str(a or "")).lower().strip(" .,!?…:;—-")
    right = normalize_space(str(b or "")).lower().strip(" .,!?…:;—-")
    if not left or not right:
        return 0.0
    ratio = SequenceMatcher(None, left, right).ratio()
    overlap = _jaccard(_tokens(left), _tokens(right))
    return max(ratio, overlap)


# ---------------------------------------------------------------------------
# HTML, ссылки, хэштеги, эмодзи
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9-]*)([^>]*)>")
_ANCHOR_RE = re.compile(
    r"<a\s[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_ENTITY_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_HASHTAG_RE = re.compile(r"(?<!\w)#([0-9A-Za-zА-Яа-яЁё_ÁÉÍÓÚÜÑáéíóúüñ]{2,})")
_BR_RE = re.compile(r"(?i)<br\s*/?>")
_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")


def _plain_with_lines(fragment: str) -> str:
    """Текст поста без тегов, но с сохранёнными абзацами (пустая строка между ними).

    ``strip_html`` схлопывает переводы строк в пробелы, а рубрика оценивает
    структуру и хук — поэтому абзацы восстанавливаем по пустым строкам HTML.
    """
    text = str(fragment or "")
    if not text:
        return ""
    text = _BR_RE.sub("\n", text)
    blocks: List[str] = []
    for raw in _BLOCK_SPLIT_RE.split(text):
        cleaned = normalize_space(strip_html(raw))
        if cleaned:
            blocks.append(cleaned)
    return "\n\n".join(blocks)


def _html_health(fragment: str) -> Dict[str, Any]:
    """Проверяет балансировку Telegram-HTML: теги, стеки, «сырые» угловые скобки."""
    stack: List[str] = []
    unknown: List[str] = []
    malformed = False
    used = 0
    for match in _TAG_RE.finditer(fragment or ""):
        closing, raw_name = match.group(1), match.group(2)
        name = raw_name.lower()
        used += len(match.group(0))
        if name not in _ALLOWED_TAGS:
            if name not in unknown:
                unknown.append(name)
            continue
        if closing:
            if not stack:
                malformed = True
            elif stack[-1] != name:
                malformed = True
                # Пытаемся восстановить стек, чтобы не считать каскад ошибок.
                for index in range(len(stack) - 1, -1, -1):
                    if stack[index] == name:
                        del stack[index]
                        break
            else:
                stack.pop()
        elif not match.group(0).rstrip().endswith("/>"):
            stack.append(name)
    remainder = _TAG_RE.sub("", fragment or "")
    leftover_angles = ("<" in remainder) or (">" in remainder)
    entities = len(_ENTITY_RE.findall(remainder))
    return {
        "balanced": not stack and not malformed,
        "unknown_tags": unknown,
        "stray_angles": leftover_angles,
        "bad_entities": entities,
    }


def _extract_links(fragment: str) -> List[str]:
    return [match.group(1).strip() for match in _ANCHOR_RE.finditer(fragment or "")]


def _hashtags(fragment: str, plain: str) -> List[str]:
    tags = [match.group(0) for match in _HASHTAG_RE.finditer(plain or "")]
    tags.extend(match.group(0) for match in _HASHTAG_RE.finditer(fragment or ""))
    unique: List[str] = []
    seen = set()
    for tag in tags:
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(tag)
    return unique


def _hashtag_occurrences(plain: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for match in _HASHTAG_RE.finditer(plain or ""):
        key = match.group(0).lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


# Эмодзи определяем по блокам Unicode: этого достаточно и это детерминированно.
_EMOJI_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x1F300, 0x1FAFF),  # пиктограммы, транспорт, флаги, лица
    (0x1F1E6, 0x1F1FF),  # региональные индикаторы (флаги)
    (0x2600, 0x27BF),    # символы и дингбаты (☀️, ❤️, ➡️)
    (0x2B00, 0x2BFF),    # стрелки/звёзды
    (0x2300, 0x23FF),    # ⌚⏰
)
_EMOJI_SKIP = {0xFE0E, 0xFE0F, 0x200D}


def _is_emoji(char: str) -> bool:
    codepoint = ord(char)
    if codepoint in _EMOJI_SKIP:
        return False
    return any(start <= codepoint <= end for start, end in _EMOJI_RANGES)


def _emoji_chars(text: str) -> List[str]:
    return [char for char in (text or "") if _is_emoji(char)]


# ---------------------------------------------------------------------------
# Факты, капс, кликбейт, markdown
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"\d+(?:[.,]\d+)?(?:\s*(?:%|млн|млрд|трлн|тыс|тысяч|million|billion|bn|mln))?",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
_MONTH_RE = re.compile(
    r"\b(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|"
    r"декабр|january|february|march|april|may|june|july|august|september|october|"
    r"november|december|enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)",
    re.IGNORECASE,
)
_ORG_RE = re.compile(
    r"(?:\b(?:Inc|Corp|Corporation|Ltd|LLC|GmbH|Company|Bank|Ministry|Agency|"
    r"Government|Gobierno|Banco|Agencia|Ministerio|Universidad|University)\b|"
    r"(?:компани|банк|корпораци|министерств|агентств|правительств|университет)\w*)",
    re.IGNORECASE,
)
_CAPS_RE = re.compile(r"[A-ZА-ЯЁ]{4,}")
_CAPS_ALLOWLIST = {
    "OPENAI", "GOOGLE", "APPLE", "MICROSOFT", "NVIDIA", "TESLA", "AMAZON", "META",
    "ANTHROPIC", "NASA", "NATO", "UNESCO", "COVID", "США", "СССР", "ВВП", "ООН",
    "ЕС", "ЕЭС", "ЦБ", "ЕЦБ", "ФРС", "РЖД", "МЧС", "ГИБДД", "СБЕР", "ВТБ",
}

# Кликбейт — только явные маркеры, а не обычные новостные слова.
_CLICKBAIT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("ru", r"вы не поверите"),
    ("ru", r"просто шок"),
    ("ru", r"это шок"),
    ("ru", r"шокирующ\w*"),
    ("ru", r"сенсационн\w*"),
    ("ru", r"жми(?:те)? (?:сюда|по ссылке)"),
    ("ru", r"успей(?:те)?\b"),
    ("ru", r"только сейчас"),
    ("ru", r"не пропусти(?:те)?"),
    ("ru", r"кликни(?:те)?"),
    ("en", r"you won[’']t believe"),
    ("en", r"shocking"),
    ("en", r"mind[- ]blowing"),
    ("en", r"click here"),
    ("en", r"act now"),
    ("en", r"limited time"),
    ("en", r"this one trick"),
    ("en", r"must[- ]see"),
    ("es", r"no (?:te lo )?vas a creer"),
    ("es", r"no creer[áa]s"),
    ("es", r"incre[íi]ble"),
    ("es", r"impactante"),
    ("es", r"esc[áa]ndalo"),
    ("es", r"haz clic aqu[íi]"),
    ("es", r"[úu]ltima oportunidad"),
    ("es", r"solo por hoy"),
    ("es", r"no te lo pierdas"),
    ("es", r"esto lo cambia todo"),
)
_CLICKBAIT_RE = tuple(
    (lang, re.compile(pattern, re.IGNORECASE)) for lang, pattern in _CLICKBAIT_PATTERNS
)

_MARKDOWN_PATTERNS = (
    re.compile(r"\*\*[^*\n]{1,120}\*\*"),
    re.compile(r"__[^_\n]{1,120}__"),
    re.compile(r"```"),
    re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S"),
    re.compile(r"\[[^\]\n]{1,80}\]\(\s*(?:https?://|/)[^)\n]+\)"),
)
_PLACEHOLDER_RE = re.compile(
    r"\{\{|\}\}|<%|%>|\bTODO\b|\bFIXME\b|lorem ipsum|\bundefined\b|\bNaN\b"
)
_WEAK_FACT_RE = re.compile(
    r"(?:фигурирующ\w*\s+цифр|the figures involved|las cifras que aparecen|"
    r"цифры:|numbers:|cifras:)",
    re.IGNORECASE,
)

_CTA_PATTERNS = {
    "ru": (
        "подписывайтесь", "подпишись", "подписаться", "больше разборов",
        "читайте", "сохраняйте", "делитесь", "присоединяйтесь", "в нашем канале",
        "оставляйте",
    ),
    "en": (
        "follow the channel", "subscribe", "follow us", "read more", "stay tuned",
        "let us know", "what do you think", "share", "more news",
    ),
    "es": (
        "síganos", "siguenos", "suscríbase", "suscribete", "suscribirse",
        "lee nuestro", "comparte", "qué opina", "que opina", "déjanos", "dejanos",
    ),
}


# ---------------------------------------------------------------------------
# Отдельные измерения рубрики
# ---------------------------------------------------------------------------


def _check_text_presence(plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]) -> bool:
    if not plain:
        _add(issues, "empty_text", BLOCKER, "пустой текст поста", 100, "content")
        return False
    return True


def _check_length(
    plain: str,
    text: str,
    channel: Any,
    settings: Any,
    fmt: str,
    issues: List[QualityIssue],
    metrics: Dict[str, Any],
) -> None:
    min_chars = int(_setting(settings, "pipeline.min_post_chars", 300) or 300)
    # Сводка за период может состоять из 1–2 новостей: порог ниже (как в pipeline).
    if str(fmt or "").lower() == "digest" and str(
        _setting(settings, "pipeline.post_mode", "") or ""
    ).lower() == "digest":
        min_chars = min(min_chars, 140)
    max_chars = int(_channel_attr(channel, "max_post_chars", 3500) or 3500)
    metrics["min_chars"] = min_chars
    metrics["max_chars"] = max_chars
    if len(plain) < min_chars:
        _add(
            issues,
            "too_short",
            BLOCKER,
            f"текст короче минимума ({len(plain)} < {min_chars} символов)",
            35,
            "length",
        )
    if len(text) > max_chars * 1.35:
        _add(
            issues,
            "too_long",
            BLOCKER,
            f"текст значительно длиннее лимита канала ({len(text)} > {max_chars})",
            35,
            "length",
        )
    elif len(text) > max_chars:
        _add(
            issues,
            "over_limit",
            MAJOR,
            f"текст длиннее лимита канала ({len(text)} > {max_chars})",
            8,
            "length",
        )


_BULLET_RE = re.compile(r"(?:^|\s)(?:[-—•▪◦·*]\ufe0f?|\d{1,2}[.)])\s+\S")


def _check_structure(
    html: str, plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    blocks = [block for block in re.split(r"\n\s*\n", plain) if block.strip()]
    paragraphs = len(blocks)
    bullets = len(_BULLET_RE.findall(plain))
    metrics["paragraphs"] = paragraphs
    metrics["bullets"] = bullets
    longest = max((len(block) for block in blocks), default=0)
    metrics["longest_paragraph_chars"] = longest
    # Структурой считаются и абзацы, и маркированный список (2+ пункта).
    if paragraphs < 2 and bullets < 2:
        _add(
            issues,
            "no_structure",
            MAJOR,
            "нет структуры: весь текст одним блоком",
            8,
            "structure",
        )
    if longest > LONG_PARAGRAPH_CHARS:
        _add(
            issues,
            "long_paragraph",
            MINOR,
            f"слишком длинный абзац ({longest} символов)",
            3,
            "structure",
        )


def _check_hook(
    plain: str,
    fmt: str,
    issues: List[QualityIssue],
    metrics: Dict[str, Any],
) -> None:
    lines = [normalize_space(line) for line in plain.splitlines() if line.strip()]
    hook = lines[0] if lines else ""
    # «Снимаем» ведущие эмодзи/значки, чтобы мерить именно текст хука.
    match = re.search(r"[0-9A-Za-zА-Яа-яЁёÁÉÍÓÚÜÑáéíóúüñ]", hook)
    hook_text = hook[match.start():] if match else hook
    metrics["hook"] = hook_text[:160]
    metrics["hook_chars"] = len(hook_text)
    is_digest = str(fmt or "").lower() == "digest"
    if not is_digest:
        if len(hook_text) > HOOK_MAX:
            _add(
                issues,
                "weak_hook",
                MAJOR,
                f"слабый хук: {len(hook_text)} символов (цель ≤ {HOOK_TARGET})",
                6,
                "hook",
            )
        elif len(hook_text) > HOOK_TARGET:
            _add(
                issues,
                "hook_long",
                MINOR,
                f"хук длиннее цели ({len(hook_text)} > {HOOK_TARGET} символов)",
                3,
                "hook",
            )
        if hook_text.rstrip().endswith(("…", "...")):
            _add(
                issues,
                "hook_ellipsis",
                MINOR,
                "хук обрезан многоточием",
                2,
                "hook",
            )
        if hook_text.strip().lower() in {"новость", "news", "noticia"}:
            _add(
                issues,
                "weak_hook",
                MAJOR,
                "заголовок-заглушка вместо хука",
                6,
                "hook",
            )
    # Лид не должен дословно повторять хук.
    if len(lines) > 1:
        first_body = lines[1]
        body_sentences = split_sentences(first_body)
        lead = normalize_space(body_sentences[0] if body_sentences else first_body)
        if len(lead) >= 20 and _similarity(lead, hook_text) >= 0.7:
            _add(
                issues,
                "hook_echo",
                MAJOR,
                "первое предложение лида повторяет заголовок",
                5,
                "hook",
            )


def _check_html_and_sources(
    text: str,
    plain: str,
    sources: Sequence[Dict[str, Any]],
    issues: List[QualityIssue],
    metrics: Dict[str, Any],
    *,
    expects_sources: bool = True,
) -> None:
    health = _html_health(text)
    links = _extract_links(text)
    metrics["html_balanced"] = bool(health["balanced"])
    metrics["links"] = len(links)
    metrics["sources"] = len(sources)
    if not health["balanced"]:
        _add(issues, "broken_html", BLOCKER, "невалидный или несбалансированный HTML", 30, "html")
    if health["unknown_tags"]:
        _add(
            issues,
            "unsupported_tags",
            MAJOR,
            "неподдерживаемые Telegram-теги: " + ", ".join(health["unknown_tags"][:3]),
            6,
            "html",
        )
    if health["stray_angles"]:
        _add(issues, "stray_angles", MINOR, "неэкранированные угловые скобки в тексте", 3, "html")
    if health["bad_entities"]:
        _add(issues, "bad_entities", MINOR, "битые HTML-сущности (& без ;)", 2, "html")
    bad_schemes = [
        link for link in links if not link.lower().startswith(_SAFE_SCHEMES)
    ]
    if bad_schemes:
        _add(
            issues,
            "bad_link_scheme",
            MINOR,
            "ссылка с нестандартной схемой: " + bad_schemes[0][:60],
            3,
            "sources",
        )
    # Отсутствие источников — блокер: пост без ссылок не публикуем.
    if expects_sources and not sources:
        _add(issues, "no_sources", BLOCKER, "нет ссылок на источники", 25, "sources")
    elif sources and not links:
        _add(
            issues,
            "missing_source_links",
            MAJOR,
            "источники есть, но в тексте нет HTML-ссылок",
            10,
            "sources",
        )
    if "http" in plain.lower() and not links:
        _add(
            issues,
            "plain_url",
            BLOCKER,
            "ссылки в тексте не оформлены как HTML-ссылки",
            20,
            "sources",
        )
    if len(links) > 8:
        _add(issues, "link_spam", MINOR, f"слишком много ссылок ({len(links)})", 2, "sources")


def _check_hashtags(
    text: str, plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    tags = _hashtags(text, plain)
    occurrences = _hashtag_occurrences(plain)
    metrics["hashtags"] = len(tags)
    metrics["hashtags_list"] = tags[:10]
    count = len(tags)
    if count == 0:
        _add(
            issues,
            "hashtags_missing",
            MAJOR,
            f"нет хэштегов (нужно {HASHTAG_MIN}–{HASHTAG_MAX})",
            8,
            "hashtags",
        )
    elif count < HASHTAG_MIN:
        _add(
            issues,
            "hashtags_low",
            MINOR,
            f"мало хэштегов ({count}, нужно {HASHTAG_MIN}–{HASHTAG_MAX})",
            3,
            "hashtags",
        )
    elif count > HASHTAG_MAX:
        severity = MAJOR if count > 8 else MINOR
        _add(
            issues,
            "hashtags_high",
            severity,
            f"слишком много хэштегов ({count}, нужно {HASHTAG_MIN}–{HASHTAG_MAX})",
            10 if severity == MAJOR else min(8, 2 * (count - HASHTAG_MAX)),
            "hashtags",
        )
    duplicated = [tag for tag, times in occurrences.items() if times > 1]
    if duplicated:
        _add(issues, "hashtags_duplicate", MINOR, "повторяющиеся хэштеги", 2, "hashtags")


def _check_cta(
    plain: str,
    channel: Any,
    settings: Any,
    lang: str,
    issues: List[QualityIssue],
    metrics: Dict[str, Any],
) -> None:
    expected = str(_channel_attr(channel, "cta", "") or "").strip()
    if not expected:
        expected = str(_setting(settings, "pipeline.cta", "") or "").strip()
    lowered = plain.lower()
    present = False
    if expected:
        needle = normalize_space(expected).lower().strip(" .,!?…")
        present = bool(needle) and needle in lowered
        if not present:
            _add(
                issues,
                "cta_missing",
                MAJOR,
                "в посте нет CTA канала",
                8,
                "cta",
            )
    else:
        patterns = _CTA_PATTERNS.get(lang, _CTA_PATTERNS["ru"])
        present = any(pattern in lowered for pattern in patterns)
        # Вовлекающий вопрос в конце — тоже CTA (interactive-формат).
        if not present:
            tail = normalize_space(plain[-120:])
            present = tail.endswith("?")
        if not present:
            _add(
                issues,
                "cta_missing",
                MINOR,
                "нет призыва к действию (CTA)",
                3,
                "cta",
            )
    metrics["cta_expected"] = bool(expected)
    metrics["cta_present"] = bool(present)


def _check_duplicates(
    plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    sentences: List[str] = []
    # Делим сначала по абзацам: последнее предложение абзаца может не иметь
    # точки, и без этого граница склеила бы соседние блоки.
    for block in re.split(r"\n\s*\n", plain):
        for sentence in split_sentences(block):
            cleaned = normalize_space(sentence)
            if len(cleaned) >= 25:
                sentences.append(cleaned)
    metrics["sentences"] = len(sentences)
    duplicated: List[Tuple[str, str]] = []
    for index, left in enumerate(sentences):
        left_tokens = _tokens(left)
        if len(left_tokens) < 5:
            continue
        for right in sentences[index + 1:]:
            if _jaccard(left_tokens, _tokens(right)) >= DUPLICATE_SIMILARITY:
                duplicated.append((left, right))
                break
        if len(duplicated) >= 3:
            break
    metrics["duplicate_sentences"] = len(duplicated)
    if duplicated:
        _add(
            issues,
            "duplicate_sentences",
            MAJOR,
            f"повторяющиеся предложения ({len(duplicated)})",
            8,
            "duplicates",
        )


def _check_caps(
    plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    words = re.findall(r"[\w-]+", plain)
    caps = [
        word
        for word in _CAPS_RE.findall(plain)
        if word.replace("Ё", "Е") not in _CAPS_ALLOWLIST
    ]
    # Проверяем границы слова: «iPhone» и «GPT-5» не считаются капсом.
    caps = [word for word in caps if re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", plain)]
    ratio = len(caps) / max(1, len(words))
    metrics["caps_words"] = len(caps)
    metrics["caps_ratio"] = round(ratio, 3)
    if len(caps) >= 2 and ratio >= 0.08:
        _add(
            issues,
            "all_caps",
            MAJOR,
            f"капс-крик ({len(caps)} слов заглавными)",
            10,
            "tone",
        )
    elif caps:
        _add(issues, "all_caps", MINOR, "слово капсом в тексте", 3, "tone")


def _check_readability(
    plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    sentences = [s for s in split_sentences(plain) if len(s) >= 15]
    total_words = len(re.findall(r"[\w-]+", plain))
    metrics["sentences_total"] = len(sentences)
    if not sentences:
        if len(plain) > 400:
            _add(
                issues,
                "no_sentence_breaks",
                MAJOR,
                "длинный текст без знаков конца предложения",
                6,
                "readability",
            )
        return
    avg = total_words / len(sentences)
    metrics["avg_sentence_words"] = round(avg, 1)
    longest = max(len(re.findall(r"[\w-]+", sentence)) for sentence in sentences)
    metrics["max_sentence_words"] = longest
    if avg > AVG_SENTENCE_WORDS_BAD:
        _add(
            issues,
            "readability",
            MAJOR,
            f"предложения слишком длинные (в среднем {avg:.0f} слов)",
            6,
            "readability",
        )
    elif avg > AVG_SENTENCE_WORDS_WARN:
        _add(
            issues,
            "readability",
            MINOR,
            f"длинноватые предложения (в среднем {avg:.0f} слов)",
            3,
            "readability",
        )
    if longest > LONG_SENTENCE_WORDS:
        _add(
            issues,
            "long_sentence",
            MINOR,
            f"предложение длиннее {LONG_SENTENCE_WORDS} слов ({longest})",
            3,
            "readability",
        )


def _count_facts(plain: str) -> int:
    return (
        len(_NUMBER_RE.findall(plain))
        + len(_DATE_RE.findall(plain))
        + len(_MONTH_RE.findall(plain))
        + len(_ORG_RE.findall(plain))
    )


def _check_fact_density(
    plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    facts = _count_facts(plain)
    metrics["facts"] = facts
    if len(plain) < 120:
        return
    density = facts / (len(plain) / 1000.0)
    metrics["fact_density"] = round(density, 2)
    if density < FACT_DENSITY_MIN:
        _add(
            issues,
            "fact_density",
            MAJOR,
            f"мало конкретных фактов ({density:.1f} на 1000 символов)",
            6,
            "facts",
        )
    elif density < FACT_DENSITY_WARN:
        _add(
            issues,
            "fact_density",
            MINOR,
            f"низкая плотность фактов ({density:.1f} на 1000 символов)",
            3,
            "facts",
        )


def _check_clickbait(
    plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    hits: List[str] = []
    for _lang, pattern in _CLICKBAIT_RE:
        for match in pattern.finditer(plain):
            phrase = normalize_space(match.group(0)).lower()
            if phrase and phrase not in hits:
                hits.append(phrase)
    metrics["clickbait_hits"] = len(hits)
    if hits:
        _add(
            issues,
            "clickbait",
            MAJOR,
            "кликбейт: " + ", ".join(hits[:4]),
            min(24, 10 * len(hits)),
            "tone",
        )
    shouts = re.findall(r"[!?]{3,}", plain)
    if shouts:
        _add(
            issues,
            "punctuation_shout",
            MINOR,
            "кричащая пунктуация (!!! или ???)",
            3,
            "tone",
        )


def _check_markdown_and_placeholders(
    plain: str, issues: List[QualityIssue], metrics: Dict[str, Any]
) -> None:
    leaks = [
        pattern.pattern
        for pattern in _MARKDOWN_PATTERNS
        if pattern.search(plain)
    ]
    metrics["markdown_leaks"] = len(leaks)
    if leaks:
        _add(issues, "markdown_leak", MAJOR, "в тексте остался markdown", 10, "markup")
    if _PLACEHOLDER_RE.search(plain):
        _add(
            issues,
            "placeholder_text",
            BLOCKER,
            "в тексте служебная заглушка ({{}}, TODO, undefined)",
            40,
            "markup",
        )
    if _WEAK_FACT_RE.search(plain):
        _add(
            issues,
            "weak_fact_style",
            MINOR,
            "цифры поданы служебной строкой вместо факта",
            3,
            "facts",
        )


def _check_emoji(
    text: str,
    plain: str,
    channel: Any,
    issues: List[QualityIssue],
    metrics: Dict[str, Any],
) -> None:
    emojis = _emoji_chars(plain) or _emoji_chars(text)
    metrics["emoji"] = len(emojis)
    allows_emoji = bool(_channel_attr(channel, "emoji", True))
    if not allows_emoji and emojis:
        _add(
            issues,
            "emoji_policy",
            MAJOR,
            f"эмодзи в канале без эмодзи ({len(emojis)})",
            6,
            "emoji",
        )
    elif allows_emoji and len(emojis) > EMOJI_HARD_MAX:
        _add(
            issues,
            "emoji_policy",
            MAJOR,
            f"слишком много эмодзи ({len(emojis)})",
            6,
            "emoji",
        )
    elif allows_emoji and len(emojis) > EMOJI_MAX:
        _add(
            issues,
            "emoji_policy",
            MINOR,
            f"много эмодзи ({len(emojis)})",
            4,
            "emoji",
        )
    elif allows_emoji and not emojis and len(plain) > 200:
        _add(issues, "emoji_policy", MINOR, "в канале с эмодзи их нет", 1, "emoji")


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def score_post(
    post: Any,
    channel: Any = None,
    settings: Any = None,
) -> QualityReport:
    """Оценивает пост по детерминированной рубрике.

    ``post`` — :class:`~content_factory.models.GeneratedPost` (или совместимый
    объект/словарь) либо готовая строка текста. Для строки проверки ссылок на
    источники пропускаются: списка источников у строки нет.

    ``channel`` — :class:`~content_factory.models.ChannelConfig` (или словарь):
    из него берутся лимит символов, флаг эмодзи, CTA и язык.

    ``settings`` — :class:`~content_factory.config.Settings` (или объект с
    ``.get(dotted, default)``): оттуда берутся ``pipeline.min_post_chars``,
    ``pipeline.post_mode``, ``pipeline.cta``.

    Возвращает :class:`QualityReport`; функция ничего не пишет в ``post.meta`` —
    это делает конвейер (см. ``pipeline.quality_issues``).
    """
    text, sources, hashtags, fmt, meta = _post_fields(post)
    plain = _plain_with_lines(text)
    channel_language = _channel_attr(channel, "language", "")
    lang = language_code(
        channel_language or meta.get("language") or "ru"
    )
    report = QualityReport(
        score=100,
        issues=[],
        metrics={
            "plain_chars": len(plain),
            "html_chars": len(text),
            "language": lang,
            "format": str(fmt or ""),
            "hashtags_from_post": list(hashtags)[:10],
        },
        channel_id=str(_channel_attr(channel, "id", "") or ""),
        language=lang,
        format=str(fmt or ""),
    )
    issues = report.issues
    metrics = report.metrics
    if not _check_text_presence(plain, issues, metrics):
        report.score = 0
        return report

    _check_length(plain, text, channel, settings, fmt, issues, metrics)
    _check_structure(text, plain, issues, metrics)
    _check_hook(plain, fmt, issues, metrics)
    _check_html_and_sources(
        text,
        plain,
        sources,
        issues,
        metrics,
        expects_sources=not isinstance(post, str),
    )
    _check_hashtags(text, plain, issues, metrics)
    _check_cta(plain, channel, settings, lang, issues, metrics)
    _check_duplicates(plain, issues, metrics)
    _check_caps(plain, issues, metrics)
    _check_readability(plain, issues, metrics)
    _check_fact_density(plain, issues, metrics)
    _check_clickbait(plain, issues, metrics)
    _check_markdown_and_placeholders(plain, issues, metrics)
    _check_emoji(text, plain, channel, issues, metrics)

    total_penalty = sum(int(issue.penalty or 0) for issue in issues)
    report.score = max(0, min(100, 100 - total_penalty))
    metrics["penalty"] = total_penalty
    metrics["blockers"] = len(report.blockers)
    metrics["warnings"] = len(report.warnings)
    # Предупреждения без баллов не бывает: штраф ≥ 1 держит монотонность.
    return report


def is_blocking(report: QualityReport) -> bool:
    """Есть ли в отчёте блокирующие проблемы."""
    return report.has_blockers()


__all__ = [
    "BLOCKER",
    "MAJOR",
    "MINOR",
    "SEVERITIES",
    "QualityIssue",
    "QualityReport",
    "score_post",
    "is_blocking",
]
