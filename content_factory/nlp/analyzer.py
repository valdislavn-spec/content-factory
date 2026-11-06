"""Анализ кластера новостей: резюме, тезисы, тональность, ракурсы источников.

Основной режим — экстрактивный (TextRank + лексиконы), он обязателен и
работает офлайн. Если передан доступный LLM-клиент, резюме и тезисы
переписываются моделью по жёсткому промпту «только факты из текста».
Любой мусор от модели (markdown, выдуманные цифры, пустота, ответ не на
языке канала) отбрасывается и заменяется экстрактивным результатом —
конвейер не падает.

Язык анализа задаёт канал (``language: ru``/``en``/``es``, см.
:func:`content_factory.nlp.lang.resolve_language`): для английского и
испанского каналов промпты, проверки ответов LLM и шаблонные фразы
(coverage sentence, подписи) — на соответствующем языке. По умолчанию анализ
остаётся русским.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..models import Analysis, Article, StoryCluster
from ..utils import (
    STOPWORDS_EN,
    STOPWORDS_ES,
    STOPWORDS_RU,
    extract_numbers,
    jaccard,
    normalize_space,
    token_set,
    truncate,
)
from .extractive import dedupe_sentences, rank_sentences, split_sentences, summarize_texts
from .keywords import extract_key_terms
from .lang import language_code, resolve_language
from .llm import LLMClient, clean_llm_output
from .sentiment import detect_sentiment

LOGGER = logging.getLogger(__name__)

_MAX_ARTICLE_CHARS = 6000
_MAX_SUMMARY_SENTENCES = 5
_MAX_BULLETS = 5
_MIN_BULLETS = 3
_MAX_PERSPECTIVES = 6
_MAX_ENTITIES = 12

_SYSTEM_ANALYST_RU = (
    "Ты — редактор новостного Telegram-канала. Пиши по-русски, нейтрально и точно. "
    "Используй только факты из предоставленного текста. Запрещено добавлять события, "
    "цифры, даты, имена, цитаты и ссылки, которых нет в тексте. Без markdown, без "
    "заголовков и без вступлений вроде «Вот резюме»."
)
_SYSTEM_ANALYST_EN = (
    "You are an editor of a news Telegram channel. Write in English, neutrally and "
    "precisely. Use only facts from the provided text. Never add events, numbers, "
    "dates, names, quotes or links that are not in the text. No markdown, no "
    'headings and no introductions like "Here is a summary". Respond in English only.'
)
_SYSTEM_ANALYST_ES = (
    "Eres el editor de un canal de noticias de Telegram. Escribe en español "
    "neutro y preciso. Usa solo los hechos del texto proporcionado. Está prohibido "
    "añadir acontecimientos, cifras, fechas, nombres, citas o enlaces que no estén "
    "en el texto. Sin markdown, sin títulos y sin introducciones como «Aquí tienes "
    "un resumen». Responde solo en español."
)
# Прежнее имя оставлено для совместимости: по умолчанию анализ русский.
_SYSTEM_ANALYST = _SYSTEM_ANALYST_RU

_SUMMARY_PROMPT_RU = (
    "Напиши нейтральное резюме этой новости на русском языке: три–пять "
    "предложений, только факты из текста выше. Без ссылок, без списков и без "
    "выдуманных цифр. Верни только текст резюме."
)
_SUMMARY_PROMPT_EN = (
    "Write a neutral summary of this news story in English: three to five "
    "sentences, only facts from the text above. No links, no lists and no "
    "invented numbers. Return only the summary text."
)
_BULLETS_PROMPT_RU = (
    "Составь три–четыре коротких тезиса по этой новости на русском языке. "
    "Только факты из текста, без ссылок и выдуманных цифр. Каждый тезис — "
    "с новой строки, без нумерации и маркеров."
)
_BULLETS_PROMPT_EN = (
    "Write three or four short bullet points about this news story in English. "
    "Only facts from the text, no links and no invented numbers. Put each point "
    "on a new line, without numbering or bullet markers."
)
_SUMMARY_PROMPT_ES = (
    "Escribe un resumen neutral de esta noticia en español: de tres a cinco "
    "frases, solo hechos del texto anterior. Sin enlaces, sin listas y sin cifras "
    "inventadas. Devuelve solo el texto del resumen."
)
_BULLETS_PROMPT_ES = (
    "Redacta tres o cuatro puntos breves sobre esta noticia en español. Solo "
    "hechos del texto, sin enlaces ni cifras inventadas. Cada punto en una línea "
    "nueva, sin numeración ni viñetas."
)

_NUM_RE = re.compile(r"\d+")
_ENTITY_RE = re.compile(
    r"\b[А-ЯЁA-ZÁÉÍÓÚÜÑ][А-Яа-яЁёA-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\-]{1,29}\b"
)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")
_MONTHS_DAYS = frozenset(
    """
    январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь
    января февраля марта апреля мая июня июля августа сентября октября ноября декабря
    понедельник вторник среда четверг пятница суббота воскресенье
    """.split()
)
_GENERIC_CAPITALIZED = frozenset(
    """
    однако кроме также например это этот эта эти при по поэтому если когда что как
    но а в на с у от до после более менее только уже ещё еще новости новость компания
    компании эксперты эксперт источник источники фото видео подробности читайте смотрите
    подписывайтесь комментарий комментарии сегодня вчера завтра сейчас теперь
    """.split()
)
# Английские служебные слова и календарные названия не должны становиться
# сущностями, даже если стоят с заглавной буквы.
_MONTHS_DAYS_EN = frozenset(
    """
    january february march april may june july august september october november december
    monday tuesday wednesday thursday friday saturday sunday
    """.split()
)
_GENERIC_CAPITALIZED_EN = frozenset(
    """
    the a an this that these those there here it its he she they we you i
    however but and also then when where what who why how if while after before
    during since until about into over under between among according report reports
    reported said says new news company companies experts expert source sources
    photo video read subscribe today yesterday tomorrow now more most
    """.split()
)
# Испанские служебные слова и календарь — не сущности, даже с заглавной буквы.
_MONTHS_DAYS_ES = frozenset(
    """
    enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre
    lunes martes miércoles jueves viernes sábado domingo
    """.split()
)
_GENERIC_CAPITALIZED_ES = frozenset(
    """
    el la los las un una unos unas de del al en y o u que como cuando donde porque
    para por con sin sobre entre hasta desde durante según aunque pero sin embargo
    también además entonces mientras este esta estos estas ese esa esos esas
    esto eso aquel aquella sin embargo gobierno presidente empresa empresas país
    noticia noticias informe fuentes fuente hoy ayer mañana ahora después antes
    """.split()
)
# Служебные слова, которые не должны становиться ключевыми терминами EN-анализа.
_EN_TERM_STOPWORDS = STOPWORDS_EN | frozenset(word for word in STOPWORDS_RU if word.isascii())
# То же для испанского анализа.
_ES_TERM_STOPWORDS = STOPWORDS_ES | frozenset(word for word in STOPWORDS_RU if word.isascii())


def _setting(settings: Any, dotted: str, default: Any) -> Any:
    """Безопасно читает настройку; старые/неполные Settings не ломают анализ."""
    try:
        value = settings.get(dotted, default) if settings is not None else default
        return default if value is None else value
    except Exception:
        return default


def _plural(number: int, one: str, few: str, many: str) -> str:
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not (12 <= number % 100 <= 14):
        return few
    return many


def _plural_en(number: int, one: str, many: str) -> str:
    """Английское число: единственная форма только при 1."""
    return one if abs(int(number)) == 1 else many


def _plain_language(language: Any) -> str:
    """Целевой язык анализа: ``ru``/``en`` (неизвестное значение — ``ru``)."""
    return language_code(language)


def _end_sentence(sentence: str) -> str:
    sentence = normalize_space(sentence)
    if sentence and sentence[-1] not in ".!?…»)\"'":
        sentence += "."
    return sentence


def _article_text(article: Article, max_chars: int = _MAX_ARTICLE_CHARS) -> str:
    """Текст статьи для анализа: title + body/summary, аккуратно и без дублей."""
    title = normalize_space(getattr(article, "title", "") or "")
    content = normalize_space(getattr(article, "text", "") or "")
    if not content:
        content = normalize_space(getattr(article, "summary", "") or "")
    if title and content:
        prefix = title if title.endswith((".", "!", "?", "…")) else title + "."
        # Если описание уже начинается с того же заголовка, не дублируем его.
        if not content.lower().startswith(title.lower()[: max(10, len(title) // 2)]):
            content = prefix + " " + content
    elif title:
        content = title
    return content[:max_chars]


def _cluster_texts(cluster: StoryCluster, max_text_chars: int) -> List[str]:
    articles = [article for article in (cluster.articles or []) if article is not None]
    budget = max(1200, int(max_text_chars or 15000))
    texts: List[str] = []
    for article in articles:
        text = _article_text(article, min(_MAX_ARTICLE_CHARS, budget))
        if not text:
            continue
        texts.append(text)
        budget -= len(text)
        if budget <= 0:
            break
    if not texts:
        title = normalize_space(cluster.title or "")
        if title:
            texts = [title]
    return texts


def _similar_to_any(
    sentence: str,
    others: Sequence[str],
    threshold: float = 0.6,
    language: Optional[str] = None,
) -> bool:
    tokens = token_set(sentence, language=language)
    if not tokens:
        return True
    for other in others:
        if jaccard(tokens, token_set(other, language=language)) >= threshold:
            return True
    return False


def _shorten_sentence(sentence: str, limit: int = 180) -> str:
    sentence = normalize_space(sentence)
    if not sentence:
        return ""
    if len(sentence) > limit:
        sentence = truncate(sentence, limit, suffix="…")
    return sentence.rstrip(" ,;:—-")


def _coverage_sentence(source_count: int, source_names: Sequence[str], language: str = "ru") -> str:
    names = [name for name in source_names if name]
    code = _plain_language(language)
    if code == "en":
        names = [name for name in names if not _CYRILLIC_RE.search(name)]
        if len(names) <= 1:
            return f"Reported by {names[0]}." if names else ""
        label = _plural_en(len(names), "outlet", "outlets")
        return f"{len(names)} {label} reported this: {', '.join(names[:4])}."
    if code == "es":
        # Испанское «fuente» во множественном числе не меняется.
        names = [name for name in names if not _CYRILLIC_RE.search(name)]
        if source_count <= 1:
            return f"De esto informa {names[0]}." if names else ""
        if not names:
            return ""
        return f"De esto informan {source_count} fuentes: {', '.join(names[:4])}."
    if source_count <= 1:
        if names:
            return f"Об этом сообщает {names[0]}."
        return ""
    label = _plural(source_count, "источник", "источника", "источников")
    return f"Об этом сообщают {source_count} {label}: {', '.join(names[:4])}."


def _drop_echo_sentences(
    sentences: Sequence[str], language: Optional[str] = None
) -> List[str]:
    """Убирает короткие предложения-«эхо»: их слова уже есть в предыдущих.

    Так из резюме пропадают повторы вроде «OpenAI выпустила GPT-5.» после
    «OpenAI представила новую модель GPT-5.», даже если формулировки разные.
    """
    kept: List[str] = []
    covered: set = set()
    for sentence in sentences:
        words = token_set(sentence, language=language)
        if not words:
            continue
        if kept and len(sentence) < 90:
            overlap = len(words & covered) / len(words)
            if overlap >= 0.62:
                continue
        kept.append(sentence)
        covered |= words
    return kept


def _finalize_summary(
    summary: str,
    cluster: StoryCluster,
    key_terms: Sequence[str],
    numbers: Sequence[str],
    source_names: Sequence[str],
    language: str = "ru",
) -> str:
    """Приводит резюме к 3–6 предложениям, добавляя только факты о самом тексте."""
    code = _plain_language(language)
    sentences = _drop_echo_sentences(
        dedupe_sentences(split_sentences(summary)), language=code
    )
    foreign = code in ("en", "es")
    if foreign:
        # В en/es-резюме не должно оставаться русских предложений/фрагментов.
        sentences = [
            sentence for sentence in sentences if not _CYRILLIC_RE.search(sentence)
        ]
    extras: List[str] = []
    title = normalize_space(cluster.title or "")
    if title and not (foreign and _CYRILLIC_RE.search(title)):
        extras.append(_end_sentence(title))
    coverage = _coverage_sentence(len(source_names), source_names, code)
    if coverage:
        extras.append(coverage)
    if numbers:
        if code == "en":
            extras.append(f"The reports mention these figures: {', '.join(numbers[:5])}.")
        elif code == "es":
            extras.append(f"En los mensajes se mencionan estas cifras: {', '.join(numbers[:5])}.")
        else:
            extras.append(f"В сообщениях упоминаются цифры: {', '.join(numbers[:5])}.")
    if key_terms:
        if code == "en":
            extras.append(f"Key topics: {', '.join(key_terms[:5])}.")
        elif code == "es":
            extras.append(f"Temas clave: {', '.join(key_terms[:5])}.")
        else:
            extras.append(f"Ключевые темы: {', '.join(key_terms[:5])}.")

    for candidate in extras:
        if len(sentences) >= 4:
            break
        if not _similar_to_any(candidate, sentences, threshold=0.55, language=code):
            sentences.append(candidate)
    sentences = sentences[:6]
    return normalize_space(" ".join(_end_sentence(sentence) for sentence in sentences))


def _numbers_allowed(source_text: str) -> set:
    return set(_NUM_RE.findall(source_text or ""))


def _is_russian(text: str) -> bool:
    return len(re.findall(r"[А-Яа-яЁё]{2,}", text or "")) >= 5


def _is_english(text: str) -> bool:
    """Английский ответ: достаточно латиницы и ни одной кириллической буквы."""
    if not text or _CYRILLIC_RE.search(text):
        return False
    return len(_LATIN_WORD_RE.findall(text)) >= 5


def _is_latin_language(text: str) -> bool:
    """Текст на латинице без кириллицы (английский или испанский)."""
    if not text or _CYRILLIC_RE.search(text):
        return False
    return len(_LATIN_WORD_RE.findall(text)) >= 5


def _is_language(text: str, language: str) -> bool:
    """Соответствует ли текст целевому языку анализа (ru/en/es)."""
    code = _plain_language(language)
    if code == "en":
        return _is_english(text)
    if code == "es":
        return _is_latin_language(text)
    return _is_russian(text)


def _has_markup_artifacts(text: str) -> bool:
    """Отсекает JSON/HTML/markdown-мусор, который иногда возвращают модели."""
    return any(char in (text or "") for char in '{}[]<>`')


def _valid_llm_text(
    text: str,
    source_text: str,
    min_chars: int = 60,
    max_chars: int = 1400,
    language: str = "ru",
) -> str:
    """Проверяет ответ LLM и возвращает очищенный текст или "" при сомнении."""
    cleaned = clean_llm_output(text)
    if not cleaned or len(cleaned) < min_chars or len(cleaned) > max_chars:
        return ""
    lowered = cleaned.lower()
    if "```" in cleaned or "http://" in lowered or "https://" in lowered:
        return ""
    if "**" in cleaned or "##" in cleaned or "__" in cleaned:
        return ""
    if _has_markup_artifacts(cleaned):
        return ""
    if not _is_language(cleaned, language):
        return ""
    if not _numbers_allowed(cleaned) <= _numbers_allowed(source_text):
        # Модель придумала цифру, которой нет в источниках, — не доверяем тексту.
        return ""
    return cleaned


def _valid_llm_summary(text: str, source_text: str, language: str = "ru") -> str:
    cleaned = _valid_llm_text(
        text, source_text, min_chars=60, max_chars=1400, language=language
    )
    if not cleaned:
        return ""
    sentences = split_sentences(cleaned)
    if len(sentences) < 2 or len(sentences) > 8:
        return ""
    return cleaned


def _parse_llm_lines(text: str) -> List[str]:
    """Разбирает ответ модели в список тезисов (строки или нумерованный список)."""
    if not text:
        return []
    cleaned = str(text).strip()
    cleaned = re.sub(r"^```[A-Za-zА-Яа-я0-9_+-]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    lines: List[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\s*(?:[-—•*·]|\d{1,2}[.)])\s*", "", line)
        line = normalize_space(line).strip().strip("«»\"'")
        if len(line) >= 12:
            lines.append(line)
    return lines


def _valid_llm_bullets(text: str, source_text: str, language: str = "ru") -> List[str]:
    lines = _parse_llm_lines(text)
    if not 3 <= len(lines) <= 5:
        return []
    allowed = _numbers_allowed(source_text)
    code = _plain_language(language)
    result: List[str] = []
    for line in lines:
        if len(line) > 240:
            return []
        if "http://" in line.lower() or "https://" in line.lower() or "**" in line:
            return []
        if _has_markup_artifacts(line):
            return []
        if code in ("en", "es"):
            if _CYRILLIC_RE.search(line) or len(_LATIN_WORD_RE.findall(line)) < 3:
                return []
        elif len(re.findall(r"[А-Яа-яЁё]{2,}", line)) < 3:
            return []
        if not set(_NUM_RE.findall(line)) <= allowed:
            return []
        result.append(_shorten_sentence(line, 200))
    return [line for line in result if line]


def _llm_summary(
    cluster: StoryCluster, source_text: str, llm: LLMClient, language: str = "ru"
) -> str:
    code = _plain_language(language)
    if code == "en":
        prompt = (
            f"News: {normalize_space(cluster.title or '')}\n"
            f"Sources: {', '.join(cluster.source_names)}\n\n"
            f"Source text:\n{source_text[:6000]}\n\n"
            f"{_SUMMARY_PROMPT_EN}"
        )
        system = _SYSTEM_ANALYST_EN
    elif code == "es":
        prompt = (
            f"Noticia: {normalize_space(cluster.title or '')}\n"
            f"Fuentes: {', '.join(cluster.source_names)}\n\n"
            f"Texto de las fuentes:\n{source_text[:6000]}\n\n"
            f"{_SUMMARY_PROMPT_ES}"
        )
        system = _SYSTEM_ANALYST_ES
    else:
        prompt = (
            f"Новость: {normalize_space(cluster.title or '')}\n"
            f"Источники: {', '.join(cluster.source_names)}\n\n"
            f"Текст источников:\n{source_text[:6000]}\n\n"
            f"{_SUMMARY_PROMPT_RU}"
        )
        system = _SYSTEM_ANALYST_RU
    try:
        raw = llm.generate(prompt, system=system, max_tokens=420, temperature=0.2)
    except Exception as exc:  # контракт клиента — не бросать, но подстрахуемся
        LOGGER.warning("LLM не смогла написать резюме: %s", exc)
        return ""
    return _valid_llm_summary(raw, source_text, language=code)


def _llm_bullets(
    cluster: StoryCluster, source_text: str, llm: LLMClient, language: str = "ru"
) -> List[str]:
    code = _plain_language(language)
    if code == "en":
        prompt = (
            f"News: {normalize_space(cluster.title or '')}\n\n"
            f"Source text:\n{source_text[:6000]}\n\n"
            f"{_BULLETS_PROMPT_EN}"
        )
        system = _SYSTEM_ANALYST_EN
    elif code == "es":
        prompt = (
            f"Noticia: {normalize_space(cluster.title or '')}\n\n"
            f"Texto de las fuentes:\n{source_text[:6000]}\n\n"
            f"{_BULLETS_PROMPT_ES}"
        )
        system = _SYSTEM_ANALYST_ES
    else:
        prompt = (
            f"Новость: {normalize_space(cluster.title or '')}\n\n"
            f"Текст источников:\n{source_text[:6000]}\n\n"
            f"{_BULLETS_PROMPT_RU}"
        )
        system = _SYSTEM_ANALYST_RU
    try:
        raw = llm.generate(prompt, system=system, max_tokens=350, temperature=0.2)
    except Exception as exc:
        LOGGER.warning("LLM не смогла написать тезисы: %s", exc)
        return []
    return _valid_llm_bullets(raw, source_text, language=code)


_COMBINED_PROMPT_RU = (
    "Сделай строго по тексту выше две вещи:\n"
    "1) Резюме — 2–3 предложения на русском языке, только факты, без ссылок, "
    "без markdown и без вступлений.\n"
    "2) Тезисы — 3–5 коротких пунктов на русском (каждый до 200 символов), "
    "каждый с новой строки и с маркером «- ».\n\n"
    "Формат ответа ровно такой:\n"
    "РЕЗЮМЕ: <текст резюме>\n"
    "ТЕЗИСЫ:\n"
    "- <пункт 1>\n"
    "- <пункт 2>"
)
_COMBINED_PROMPT_EN = (
    "Do two things using only the text above:\n"
    "1) Summary — 2–3 sentences in English, facts only, no links, no markdown, "
    "no introductions.\n"
    "2) Bullets — 3–5 short points in English (up to 200 characters each), each "
    'on a new line starting with "- ".\n\n'
    "Response format exactly:\n"
    "SUMMARY: <summary text>\n"
    "BULLETS:\n"
    "- <point 1>\n"
    "- <point 2>"
)
_COMBINED_PROMPT_ES = (
    "Haz dos cosas usando solo el texto anterior:\n"
    "1) Resumen — 2–3 frases en español, solo hechos, sin enlaces, sin markdown "
    "y sin introducciones.\n"
    "2) Puntos clave — de 3 a 5 puntos breves en español (hasta 200 caracteres "
    "cada uno), cada uno en una línea nueva y empezando por «- ».\n\n"
    "Formato de respuesta exacto:\n"
    "RESUMEN: <texto del resumen>\n"
    "PUNTOS:\n"
    "- <punto 1>\n"
    "- <punto 2>"
)


def _split_combined(raw: str, code: str) -> Tuple[str, str]:
    """Делит ответ «резюме + тезисы» на две части по маркерам.

    Если модель проигнорировала формат и маркеров нет, весь ответ считается
    резюме (его проверят обычные валидаторы), а тезисы будут запрошены
    отдельно — это сохраняет качество на случай «строптивой» модели.
    """
    text = str(raw or "")
    lower = text.lower()
    if code == "en":
        summary_marker, bullets_marker = "summary:", "bullets:"
    elif code == "es":
        summary_marker, bullets_marker = "resumen:", "puntos:"
    else:
        summary_marker, bullets_marker = "резюме:", "тезисы:"
    summary_index = lower.find(summary_marker)
    bullets_index = lower.find(bullets_marker)
    if summary_index >= 0:
        end = bullets_index if bullets_index > summary_index else len(text)
        summary_text = text[summary_index + len(summary_marker):end]
    elif bullets_index > 0:
        summary_text = text[:bullets_index]
    else:
        summary_text = text
    bullets_text = text[bullets_index + len(bullets_marker):] if bullets_index >= 0 else ""
    return normalize_space(summary_text), bullets_text.strip()


def _llm_analysis(
    cluster: StoryCluster, source_text: str, llm: LLMClient, language: str = "ru"
) -> Tuple[str, List[str]]:
    """Один вызов вместо двух: и резюме, и тезисы.

    Экономия без потери качества: модель получает один и тот же исходный текст
    один раз (а не два), промпт и проверки ответа — те же. Если формат ответа
    нарушен, вызывающий код откатывается на прежнюю схему из двух запросов.
    """
    code = _plain_language(language)
    if code == "en":
        prompt = (
            f"News: {normalize_space(cluster.title or '')}\n"
            f"Sources: {', '.join(cluster.source_names)}\n\n"
            f"Source text:\n{source_text[:6000]}\n\n"
            f"{_COMBINED_PROMPT_EN}"
        )
        system = _SYSTEM_ANALYST_EN
    elif code == "es":
        prompt = (
            f"Noticia: {normalize_space(cluster.title or '')}\n"
            f"Fuentes: {', '.join(cluster.source_names)}\n\n"
            f"Texto de las fuentes:\n{source_text[:6000]}\n\n"
            f"{_COMBINED_PROMPT_ES}"
        )
        system = _SYSTEM_ANALYST_ES
    else:
        prompt = (
            f"Новость: {normalize_space(cluster.title or '')}\n"
            f"Источники: {', '.join(cluster.source_names)}\n\n"
            f"Текст источников:\n{source_text[:6000]}\n\n"
            f"{_COMBINED_PROMPT_RU}"
        )
        system = _SYSTEM_ANALYST_RU
    try:
        try:
            raw = llm.generate(
                prompt, system=system, max_tokens=700, temperature=0.2, keep_lines=True
            )
        except TypeError:  # моки/старые клиенты без параметра keep_lines
            raw = llm.generate(prompt, system=system, max_tokens=700, temperature=0.2)
    except Exception as exc:  # контракт клиента — не бросать, но подстрахуемся
        LOGGER.warning("LLM не смогла сделать резюме и тезисы одним запросом: %s", exc)
        return "", []
    summary_text, bullets_text = _split_combined(raw, code)
    summary = _valid_llm_summary(summary_text, source_text, language=code)
    bullets = _valid_llm_bullets(bullets_text, source_text, language=code) if bullets_text else []
    return summary, bullets


def _extractive_bullets(
    texts: Sequence[str],
    summary: str,
    key_terms: Sequence[str],
    numbers: Sequence[str],
    articles: Sequence[Article],
    language: str = "ru",
) -> List[str]:
    code = _plain_language(language)
    sentences: List[str] = []
    for text in texts:
        sentences.extend(split_sentences(text))
    foreign = code in ("en", "es")
    if foreign:
        # Тезисы en/es-поста не должны содержать русских предложений.
        sentences = [sentence for sentence in sentences if not _CYRILLIC_RE.search(sentence)]
    summary_sentences = split_sentences(summary)
    # Заголовки статей тоже попали в texts — в тезисы их берём только при нехватке фактов.
    title_sentences = [
        normalize_space(getattr(article, "title", "") or "") for article in articles
    ]
    title_sentences = [title for title in title_sentences if title]
    bullets: List[str] = []
    seen: List[str] = []
    for sentence in rank_sentences(sentences, 10, language=code):
        if _similar_to_any(sentence, summary_sentences, threshold=0.6, language=code):
            continue
        if _similar_to_any(sentence, title_sentences, threshold=0.65, language=code):
            continue
        shortened = _shorten_sentence(sentence, 180)
        if shortened and not _similar_to_any(shortened, seen, threshold=0.75, language=code):
            bullets.append(shortened)
            seen.append(shortened)
        if len(bullets) >= _MAX_BULLETS:
            break

    # Добираем тезисы из заголовков, если статья совсем короткая.
    if len(bullets) < _MIN_BULLETS:
        for article in articles:
            title = normalize_space(getattr(article, "title", "") or "")
            if not title or (foreign and _CYRILLIC_RE.search(title)):
                continue
            source = normalize_space(getattr(article, "source_name", "") or "")
            if foreign and _CYRILLIC_RE.search(source):
                source = ""
            candidate = f"{source}: {title}" if source else title
            candidate = _shorten_sentence(candidate, 190)
            if candidate and not _similar_to_any(candidate, seen, threshold=0.8, language=code):
                bullets.append(candidate)
                seen.append(candidate)
            if len(bullets) >= _MIN_BULLETS:
                break

    # Если фактов не хватило — лучше меньше тезисов, чем «список цифр»
    # или «ключевые темы материала». Генератор просто не выведет блок.
    return bullets[:_MAX_BULLETS]


def _perspectives(cluster: StoryCluster) -> List[Dict[str, str]]:
    """По одному ракурсу от каждого источника: цитата + опорный тезис."""
    perspectives: List[Dict[str, str]] = []
    seen_sources = set()
    for article in cluster.articles or []:
        source_key = getattr(article, "source_id", "") or getattr(article, "source_name", "")
        if not source_key or source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        title = normalize_space(getattr(article, "title", "") or "")
        content = _article_text(article, 4000)
        sentences = split_sentences(content)
        quote_candidates = [
            sentence
            for sentence in sentences
            if not title or not _similar_to_any(sentence, [title], threshold=0.7)
        ]
        if not quote_candidates:
            quote_candidates = sentences
        quote = ""
        if quote_candidates:
            # Предпочитаем предложение с цифрами — это обычно конкретика источника.
            ranked = sorted(
                enumerate(quote_candidates),
                key=lambda pair: (-len(extract_numbers(pair[1], limit=3)), pair[0]),
            )
            quote = _shorten_sentence(ranked[0][1], 240)
        if not quote:
            quote = _shorten_sentence(title, 240)
        angle = _shorten_sentence(title or (sentences[0] if sentences else ""), 140)
        if not quote and not angle:
            continue
        perspectives.append(
            {
                "source_name": normalize_space(getattr(article, "source_name", "") or source_key),
                "quote": quote,
                "angle": angle,
            }
        )
        if len(perspectives) >= _MAX_PERSPECTIVES:
            break
    return perspectives


def _entity_is_sentence_start(chunk: str, start: int) -> bool:
    """Слово стоит первым в предложении/строке — вероятна просто заглавная буква."""
    index = start - 1
    while index >= 0 and chunk[index] in " \t\r\n\u00a0":
        index -= 1
    if index < 0:
        return True
    return chunk[index] in ".!?…:;—–-«\"(["


def _collect_entities(titles: Sequence[str], texts: Sequence[str]) -> List[str]:
    """Простые сущности: имена, бренды, аббревиатуры из заголовков и текста.

    Слова, встречающиеся только в начале предложения, отбрасываются: это
    обычно обычные существительные с заглавной буквы, а не имена собственные.
    """
    counts: Dict[str, int] = {}
    order: Dict[str, int] = {}
    mid_sentence: Dict[str, int] = {}
    position = 0
    for chunk in list(titles) + list(texts):
        chunk = chunk or ""
        for match in _ENTITY_RE.finditer(chunk[:4000]):
            word = match.group(0).strip()
            lowered = word.lower().replace("ё", "е")
            if (
                len(word) < 2
                or lowered in STOPWORDS_RU
                or lowered in _GENERIC_CAPITALIZED
                or lowered in _GENERIC_CAPITALIZED_EN
                or lowered in _GENERIC_CAPITALIZED_ES
                or lowered in _MONTHS_DAYS_EN
                or lowered in _MONTHS_DAYS_ES
            ):
                continue
            if lowered in _MONTHS_DAYS or word.isdigit():
                continue
            counts[word] = counts.get(word, 0) + 1
            if not _entity_is_sentence_start(chunk, match.start()):
                mid_sentence[word] = mid_sentence.get(word, 0) + 1
            order.setdefault(word, position)
            position += 1

    def is_entity(word: str) -> bool:
        # Аббревиатуры, бренды со смешанным регистром и версии моделей — всегда сущности.
        if word.isupper() and len(word) >= 2:
            return True
        if re.search(r"[A-Za-z]", word) and re.search(r"[A-Z]", word[1:]):
            return True
        if re.search(r"\d", word):
            return True
        return mid_sentence.get(word, 0) > 0

    ranked = sorted(
        ((word, count) for word, count in counts.items() if is_entity(word)),
        key=lambda item: (-item[1], order.get(item[0], 0)),
    )
    return [word for word, _count in ranked[:_MAX_ENTITIES]]


def _confidence(
    source_count: int,
    combined_len: int,
    bullets_count: int,
    numbers_count: int,
    sentiment: str,
    summary_sentences: int,
) -> float:
    score = 0.3
    score += min(0.25, 0.09 * max(0, source_count - 1))
    score += min(0.2, combined_len / 6000.0 * 0.2)
    if bullets_count >= _MIN_BULLETS:
        score += 0.07
    if numbers_count:
        score += 0.07
    if sentiment == "neutral":
        score += 0.05
    if summary_sentences >= 3:
        score += 0.05
    if source_count <= 1 and combined_len < 500:
        score -= 0.1
    return round(max(0.05, min(0.95, score)), 2)


def analyze_cluster(
    cluster: StoryCluster,
    settings: Any,
    llm: Optional[LLMClient] = None,
    language: Optional[str] = None,
) -> Analysis:
    """Строит :class:`Analysis` по кластеру статей из разных источников.

    ``language`` — язык канала (``ru``/``en``). Если не задан, язык берётся из
    статей кластера или ``app.language`` в настройках; по умолчанию русский.
    """
    analysis = Analysis()
    if cluster is None:
        return analysis
    try:
        articles = [article for article in (cluster.articles or []) if article is not None]
        code = resolve_language(explicit=language, articles=articles, settings=settings)
        return _analyze(cluster, settings, llm, language=code)
    except Exception as exc:  # анализ не должен ронять конвейер
        LOGGER.exception("Ошибка анализа кластера %s: %s", getattr(cluster, "id", ""), exc)
        analysis.summary = normalize_space(getattr(cluster, "title", "") or "")
        analysis.source_names = list(cluster.source_names)
        analysis.source_count = cluster.coverage
        analysis.bullets = [analysis.summary] if analysis.summary else []
        analysis.confidence = 0.1
        return analysis


def _analyze(
    cluster: StoryCluster,
    settings: Any,
    llm: Optional[LLMClient],
    language: str = "ru",
) -> Analysis:
    code = _plain_language(language)
    analysis = Analysis()
    articles = [article for article in (cluster.articles or []) if article is not None]
    max_text_chars = int(_setting(settings, "pipeline.max_text_chars", 15000) or 15000)
    texts = _cluster_texts(cluster, max_text_chars)
    combined = "\n\n".join(texts)

    analysis.source_names = list(cluster.source_names)
    analysis.source_count = int(cluster.coverage)
    if not analysis.source_count and articles:
        analysis.source_count = len({getattr(a, "source_id", "") or getattr(a, "source_name", "") for a in articles})

    analysis.key_terms = []
    seen_terms = set()
    cluster_terms = [str(term) for term in (getattr(cluster, "key_terms", []) or [])]
    extracted_terms = extract_key_terms(texts, top_n=8, language=code)
    if code in ("en", "es"):
        # У en/es-кластера ключевые слова из дедупликатора могут быть основами
        # с русской нормализацией; ставим вперёд чистые термины целевого языка.
        candidates = extracted_terms + cluster_terms
    else:
        candidates = cluster_terms + extracted_terms
    for term in candidates:
        lowered = str(term).strip().lower().replace("ё", "е")
        if not lowered or lowered in seen_terms:
            continue
        if code == "en":
            if _CYRILLIC_RE.search(str(term)) or lowered in _EN_TERM_STOPWORDS:
                continue
        elif code == "es":
            if _CYRILLIC_RE.search(str(term)) or lowered in _ES_TERM_STOPWORDS:
                continue
        seen_terms.add(lowered)
        analysis.key_terms.append(str(term).strip())
    analysis.key_terms = analysis.key_terms[:10]

    analysis.numbers = extract_numbers(combined, limit=8)
    analysis.sentiment, analysis.sentiment_score = detect_sentiment(combined)

    llm_available = bool(llm is not None and getattr(llm, "available", False))
    summary = ""
    bullets: List[str] = []
    if llm_available and combined:
        combined_mode = bool(_setting(settings, "llm.optimize.combined_analysis", False))
        if combined_mode:
            summary, bullets = _llm_analysis(cluster, combined, llm, language=code)
        if not summary:
            # Формат combined не разобрался (или режим выключен) — безопасный
            # откат на прежнюю схему: два запроса, качество не теряется.
            summary = _llm_summary(cluster, combined, llm, language=code)
            if summary and not bullets:
                bullets = _llm_bullets(cluster, combined, llm, language=code)
        elif not bullets:
            bullets = _llm_bullets(cluster, combined, llm, language=code)
    if not summary:
        summary = summarize_texts(
            texts, max_sentences=_MAX_SUMMARY_SENTENCES, language=code
        )
    analysis.summary = _finalize_summary(
        summary,
        cluster,
        analysis.key_terms,
        analysis.numbers,
        analysis.source_names,
        language=code,
    )

    if not bullets:
        bullets = _extractive_bullets(
            texts,
            analysis.summary,
            analysis.key_terms,
            analysis.numbers,
            articles,
            language=code,
        )
    analysis.bullets = [bullet for bullet in bullets if bullet][:_MAX_BULLETS]

    analysis.perspectives = _perspectives(cluster)
    analysis.entities = _collect_entities(
        [getattr(article, "title", "") for article in articles],
        texts[:3],
    )
    if code in ("en", "es"):
        # Гарантия accept: в en/es-анализе не остаётся кириллицы, даже если в
        # кластер случайно попала русскоязычная статья или название.
        analysis.perspectives = [
            perspective
            for perspective in analysis.perspectives
            if not (
                _CYRILLIC_RE.search(perspective.get("quote", ""))
                or _CYRILLIC_RE.search(perspective.get("angle", ""))
            )
        ]
        analysis.entities = [
            entity for entity in analysis.entities if not _CYRILLIC_RE.search(entity)
        ]
    summary_sentences = len(split_sentences(analysis.summary))
    analysis.confidence = _confidence(
        analysis.source_count,
        len(combined),
        len(analysis.bullets),
        len(analysis.numbers),
        analysis.sentiment,
        summary_sentences,
    )
    return analysis
