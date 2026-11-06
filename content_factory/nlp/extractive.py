"""Экстрактивная суммаризация на чистом Python (TextRank).

Модуль не требует ни моделей, ни сети: предложения ранжируются по
центральности в графе лексических пересечений, похожие предложения
склеиваются, итог собирается в исходном порядке текста. Это обязательный
режим работы контент-завода, когда LLM недоступна.

Модуль одинаково работает для русского, английского и испанского текста:
язык влияет на набор стоп-слов при сравнении предложений и на защиту
сокращений («e.g.», «U.S.», «Sr.», «EE. UU.») от ложного разбиения на
предложения. По умолчанию поведение прежнее — русское.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, List, Optional, Sequence, Tuple

from ..utils import detect_text_language, normalize_space, truncate, token_set

# Разбиваем по знакам конца предложения и по переводам строк.
_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")
_LEADING_JUNK_RE = re.compile(r"^\s*(?:[-—–•*·|]+\s*|\d{1,2}[.)]\s+)+")
_TRAILING_JUNK_RE = re.compile(r"[\s|·-]+$")
_SENTENCE_END = ".!?…»)\"'"
_MAX_SENTENCE_CHARS = 420
_MIN_SENTENCE_CHARS = 12
# В испанском короткие реплики/вопросы — норма: «¿Qué pasó?» (11 символов).
_MIN_SENTENCE_CHARS_ES = 8
_MAX_SOURCE_CHARS = 8000
_DEDUP_THRESHOLD = 0.72
_DAMPING = 0.85
_ITERATIONS = 40

# Английские сокращения с точкой не должны разбивать предложение.
_EN_ABBREVIATION_RE = re.compile(
    r"\b(?:e\.g|i\.e|etc|vs|cf|approx|dept|fig|vol|pp|al|"
    r"u\.s|u\.k|u\.n|e\.u|"
    r"dr|mr|mrs|ms|prof|sr|jr|inc|ltd|corp|llc|plc|co|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec|"
    r"mon|tue|wed|thu|fri|sat|sun|"
    r"a\.m|p\.m)\.",
    re.IGNORECASE,
)
# Испанские сокращения: «Sr.», «Sra.», «Ud.», «EE. UU.», «p. ej.» и т.п.
_ES_ABBREVIATION_RE = re.compile(
    r"\b(?:sr|sra|srta|sres|dr|dra|ud|uds|dpto|gob|pág|núm|aprox|etc|vs|fig|vol|pp|"
    r"p\.\s*ej|ee\.\s*uu|ee\.uu|a\.\s*c|d\.\s*c)\.",
    re.IGNORECASE,
)
_SENTENCE_DOT = "\u0001"  # временная замена точки внутри сокращения


def _language_hint(text: str) -> Optional[str]:
    """``en``/``es`` для латинского текста, ``None`` — прежний русский путь."""
    code = detect_text_language([text])
    return code if code in ("en", "es") else None


def _mask_abbreviations(text: str) -> str:
    def mask(match: re.Match) -> str:
        # Внутренние точки «EE. UU.» тоже прячем, иначе текст разобьётся.
        return match.group(0).replace(".", _SENTENCE_DOT)

    text = _EN_ABBREVIATION_RE.sub(mask, text)
    return _ES_ABBREVIATION_RE.sub(mask, text)


def _unmask_abbreviations(text: str) -> str:
    return text.replace(_SENTENCE_DOT, ".")


def _clean_sentence(sentence: str) -> str:
    sentence = _LEADING_JUNK_RE.sub("", sentence or "")
    sentence = _TRAILING_JUNK_RE.sub("", sentence)
    sentence = normalize_space(sentence)
    return sentence


def split_sentences(text: str) -> List[str]:
    """Разбивает текст на пригодные для анализа предложения.

    Слишком короткие обрывки и пустые строки отбрасываются. Если текст не
    содержит знаков препинания (заголовок, сырая выдача), возвращается одна
    длинная «фраза», чтобы суммаризатор не остался с пустым результатом.
    Для латинского текста точки в сокращениях («e.g.», «U.S.», «Sr.»,
    «EE. UU.») не считаются концом предложения, а для испанского порог
    минимальной длины ниже — вопросы и восклицания там обычно короткие.
    """
    if not text or not str(text).strip():
        return []
    raw_text = str(text)[:_MAX_SOURCE_CHARS]
    hint = _language_hint(raw_text)
    mask_abbreviations = hint is not None
    if mask_abbreviations:
        raw_text = _mask_abbreviations(raw_text)
    min_chars = _MIN_SENTENCE_CHARS_ES if hint == "es" else _MIN_SENTENCE_CHARS
    parts = _SPLIT_RE.split(raw_text)
    sentences: List[str] = []
    for part in parts:
        if mask_abbreviations:
            part = _unmask_abbreviations(part)
        cleaned = _clean_sentence(part)
        if not cleaned:
            continue
        if len(cleaned) < min_chars:
            continue
        if len(cleaned) > 900:
            cleaned = truncate(cleaned, 700, suffix="…")
        sentences.append(cleaned)
    if sentences:
        return sentences
    fallback = normalize_space(_unmask_abbreviations(raw_text) if mask_abbreviations else raw_text)
    return [truncate(fallback, _MAX_SENTENCE_CHARS, suffix="…")] if fallback else []



def _sentence_tokens(sentence: str, language: Optional[str] = None) -> set:
    return token_set(sentence, language=language)


def _jaccard_sets(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe_sentences(
    sentences: Sequence[str],
    threshold: float = _DEDUP_THRESHOLD,
    language: Optional[str] = None,
) -> List[str]:
    """Убирает повторы и почти одинаковые предложения, сохраняя порядок.

    ``language="en"``/``"es"`` переключает сравнение на стоп-слова этого
    языка; ``None`` сохраняет прежнее русское поведение.
    """
    kept: List[str] = []
    kept_norms: List[str] = []
    kept_tokens: List[set] = []
    for sentence in sentences or []:
        cleaned = _clean_sentence(sentence)
        if not cleaned:
            continue
        norm = re.sub(r"[^0-9a-zа-яёáéíóúüñ]+", "", cleaned.lower().replace("ё", "е"))
        if not norm:
            continue
        if norm in kept_norms:
            continue
        tokens = _sentence_tokens(cleaned, language)
        if any(_jaccard_sets(tokens, previous) >= threshold for previous in kept_tokens):
            continue
        kept.append(cleaned)
        kept_norms.append(norm)
        kept_tokens.append(tokens)
    return kept


def _similarity(a: set, b: set) -> float:
    """Косинус на бинарных векторах слов — устойчивее к длине, чем Жаккар."""
    if not a or not b:
        return 0.0
    common = len(a & b)
    if not common:
        return 0.0
    return common / math.sqrt(len(a) * len(b))


def _rank_scores(sentences: Sequence[str], language: Optional[str] = None) -> List[float]:
    """TextRank: веса PageRank по матрице похожести предложений."""
    size = len(sentences)
    if size == 0:
        return []
    if size == 1:
        return [1.0]

    tokens = [_sentence_tokens(sentence, language) for sentence in sentences]
    matrix: List[List[float]] = [[0.0] * size for _ in range(size)]
    has_edges = False
    for i in range(size):
        for j in range(i + 1, size):
            weight = _similarity(tokens[i], tokens[j])
            matrix[i][j] = weight
            matrix[j][i] = weight
            if weight > 0:
                has_edges = True

    if not has_edges:
        # Общих слов нет (короткие заголовки, цитаты): веса по позиции.
        return [1.0 / (1.0 + index * 1.15) for index in range(size)]

    weights: List[float] = [1.0 / size] * size
    for _ in range(_ITERATIONS):
        updated: List[float] = []
        for i in range(size):
            incoming = 0.0
            for j in range(size):
                if i == j:
                    continue
                row_sum = sum(matrix[j])
                if row_sum > 0:
                    incoming += matrix[j][i] / row_sum * weights[j]
            updated.append((1.0 - _DAMPING) / size + _DAMPING * incoming)
        total = sum(updated)
        if total <= 0:
            break
        weights = [value / total for value in updated]
    return weights


def rank_sentences(
    sentences: Sequence[str],
    top_n: int = 3,
    language: Optional[str] = None,
) -> List[str]:
    """Возвращает до ``top_n`` самых центральных предложений.

    Результат сохраняет порядок исходного текста: так резюме читается как
    связный фрагмент, а не как случайный набор строк.
    """
    try:
        limit = int(top_n)
    except (TypeError, ValueError):
        limit = 3
    if limit <= 0:
        return []
    unique = dedupe_sentences(sentences, language=language)
    if not unique:
        return []
    if len(unique) <= limit:
        return unique
    scores = _rank_scores(unique, language)
    order = sorted(range(len(unique)), key=lambda index: (-scores[index], index))
    chosen = sorted(order[:limit])
    return [unique[index] for index in chosen]


def _cap_sentence(sentence: str) -> str:
    sentence = _clean_sentence(sentence)
    if not sentence:
        return ""
    if len(sentence) > _MAX_SENTENCE_CHARS:
        sentence = truncate(sentence, _MAX_SENTENCE_CHARS, suffix="…")
    if sentence and sentence[-1] not in _SENTENCE_END:
        sentence += "."
    return sentence


def summarize_sentences(
    sentences: Sequence[str],
    max_sentences: int = 3,
    language: Optional[str] = None,
) -> str:
    """Собирает резюме из готовых предложений в исходном порядке."""
    try:
        limit = max(1, int(max_sentences))
    except (TypeError, ValueError):
        limit = 3
    selected = rank_sentences(sentences, limit, language=language)
    parts = [part for part in (_cap_sentence(sentence) for sentence in selected) if part]
    if not parts:
        return ""
    return normalize_space(" ".join(parts))


def summarize_texts(
    texts: Iterable[str],
    max_sentences: int = 5,
    language: Optional[str] = None,
) -> str:
    """Резюмирует набор текстов (например, несколько статей об одном событии).

    Предложения всех текстов объединяются, дубликаты и пересказы склеиваются,
    затем выбираются самые центральные. ``language="en"``/``"es"`` включает
    стоп-слова этого языка при сравнении; ``None`` сохраняет прежнее
    поведение. При пустом вводе возвращается "".
    """
    try:
        limit = max(1, int(max_sentences))
    except (TypeError, ValueError):
        limit = 5
    collected: List[Tuple[int, str]] = []
    for text in texts or []:
        if not text or not str(text).strip():
            continue
        for sentence in split_sentences(str(text)):
            collected.append((len(collected), sentence))
    if not collected:
        return ""
    ordered = [sentence for _index, sentence in collected]
    return summarize_sentences(ordered, limit, language=language)
