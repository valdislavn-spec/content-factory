"""Дедупликация и кластеризация новостей.

Задача модуля — из десятков статей за час собрать «сюжеты»: группы
материалов об одном событии из разных источников. Используется жадная
кластеризация по сходству заголовков (объединение транзитивное, union-find).
Сравнение устойчиво к русской морфологии: слова приводятся к псевдооснове
лёгким стеммером, затем считаются взвешенный Jaccard, пересечение
«длинных» слов, SequenceMatcher, совпадение чисел и собственных имён.

Дополнительно есть ``is_duplicate_title`` — защита от повторной публикации
поста или статьи с тем же заголовком.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .models import Article, StoryCluster, utcnow
from .utils import normalize_space, split_sentences, stable_id, strip_html, tokenize

logger = logging.getLogger(__name__)

# Слова, которые не помогают отличить один сюжет от другого.
GENERIC_TERMS = frozenset(
    """
    новость новости сообщает сообщил сообщила сообщили стало известн известно
    главн главное срочно важно сегодня вчера завтра теперь также кроме этого
    росси россия российск российский году году года лет время жизнь мир
    компании компания человек людей может могут будет будут есть
    """.split()
)

# Окончания для очень лёгкого стеммера: сравниваем основы, а не словоформы.
_ENDINGS: Tuple[str, ...] = tuple(
    sorted(
        """
        иями ями ами ией иям иях ов ев ий ый ой ей ая ое ые ых
        ам ям ах ях ом ем у ю ы и а я е о ь
        ия ии ую юю щими щем щего щей щих щим вшая вший вшее вшие
        ться тся ыла ыли ала ало али или ить ать ять еть ует уют
        л ла ли ло ет ут ют ит ат ят ем им ешь ишь ете ите ть ся сь
        """.split(),
        key=len,
        reverse=True,
    )
)

_WORD_WITH_CASE_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9-]*")
_CYRILLIC_RE = re.compile(r"[а-я]")
_SENTENCE_START_RE = re.compile(r"^[А-ЯЁ][а-яё]+$")


def _stem(token: str) -> str:
    """Лёгкая псевдооснова слова: «ставку/ставки/ставка» -> «ставк»."""
    token = (token or "").lower().replace("ё", "е")
    if not token:
        return ""
    if not _CYRILLIC_RE.search(token):
        # Латиница/аббревиатуры не стеммим, только мягкое множественное число.
        if token.isalpha() and len(token) > 4 and token.endswith("s"):
            return token[:-1]
        return token
    for ending in _ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 3:
            return token[: -len(ending)]
    return token


def _terms(text: str) -> List[str]:
    """Упорядоченный набор основ значимых слов текста."""
    return [_stem(token) for token in tokenize(text or "") if token]


def _proper_terms(title: str) -> Set[str]:
    """Собственные имена/аббревиатуры заголовка (по заглавным буквам)."""
    words = _WORD_WITH_CASE_RE.findall(title or "")
    result: Set[str] = set()
    for index, word in enumerate(words):
        if not word or not word[0].isupper():
            continue
        # Обычное заглавное слово в начале предложения — не имя собственное.
        if index == 0 and _SENTENCE_START_RE.match(word):
            continue
        for token in tokenize(word):
            stemmed = _stem(token)
            if stemmed:
                result.add(stemmed)
    return result


def _numbers(terms: Iterable[str]) -> Set[str]:
    return {term for term in terms if term.isdigit()}


def _pair_similarity(
    terms_a: List[str],
    terms_b: List[str],
    proper_a: Set[str],
    proper_b: Set[str],
    idf: Optional[Dict[str, float]] = None,
) -> float:
    """Сходство двух заголовков в диапазоне 0..1 по набору сигналов."""
    set_a, set_b = set(terms_a), set(terms_b)
    if not set_a or not set_b:
        return 0.0
    shared = set_a & set_b
    if not shared:
        return 0.0

    if idf:
        weight_shared = sum(idf.get(term, 1.0) for term in shared)
        weight_union = sum(idf.get(term, 1.0) for term in (set_a | set_b))
        overlap = weight_shared / weight_union if weight_union else 0.0
    else:
        overlap = len(shared) / len(set_a | set_b)

    long_a = {term for term in set_a if len(term) >= 5}
    long_b = {term for term in set_b if len(term) >= 5}
    long_overlap = 0.0
    if long_a and long_b:
        long_overlap = len(long_a & long_b) / len(long_a | long_b)

    containment = len(shared) / min(len(set_a), len(set_b))
    sequence = SequenceMatcher(None, " ".join(terms_a), " ".join(terms_b)).ratio()

    bonus = min(0.12, 0.06 * len(proper_a & proper_b))
    numbers_a, numbers_b = _numbers(set_a), _numbers(set_b)
    if numbers_a and numbers_b:
        bonus += 0.03 if numbers_a & numbers_b else -0.05

    similarity = 0.45 * overlap + 0.2 * long_overlap + 0.2 * containment + 0.15 * sequence + bonus
    return max(0.0, min(1.0, similarity))


def title_similarity(first: str, second: str) -> float:
    """Сходство двух заголовков без корпуса (0..1). Полезно для отладки/тестов."""
    terms_a, terms_b = _terms(first), _terms(second)
    return _pair_similarity(terms_a, terms_b, _proper_terms(first), _proper_terms(second))


def _article_terms(article: Article) -> Tuple[List[str], List[str]]:
    """Термы заголовка и тела: заголовок весит больше, тело помогает
    связать пересказы с разными формулировками."""
    title = _terms(article.title)
    body_text = article.summary or (article.text or "")[:700]
    body = [term for term in _terms(body_text) if term not in GENERIC_TERMS]
    return title, body


def _weighted_overlap(
    title_a: Set[str],
    body_a: Set[str],
    title_b: Set[str],
    body_b: Set[str],
    idf: Dict[str, float],
) -> float:
    """Взвешенный Jaccard: термин заголовка весит 3, термин тела — 1."""
    weights_a = {term: 3.0 for term in title_a}
    weights_a.update({term: 1.0 for term in body_a if term not in weights_a})
    weights_b = {term: 3.0 for term in title_b}
    weights_b.update({term: 1.0 for term in body_b if term not in weights_b})
    vocabulary = set(weights_a) | set(weights_b)
    shared = union = 0.0
    for term in vocabulary:
        weight_a = weights_a.get(term, 0.0) * idf.get(term, 1.0)
        weight_b = weights_b.get(term, 0.0) * idf.get(term, 1.0)
        shared += min(weight_a, weight_b)
        union += max(weight_a, weight_b)
    return shared / union if union else 0.0


def _article_similarity(
    title_a: List[str],
    body_a: List[str],
    title_b: List[str],
    body_b: List[str],
    proper_a: Set[str],
    proper_b: Set[str],
    idf: Dict[str, float],
    title_text_a: str,
    title_text_b: str,
) -> float:
    """Сходство статей для кластеризации: заголовок + тело + сущности/числа."""
    set_title_a, set_title_b = set(title_a), set(title_b)
    if not set_title_a or not set_title_b:
        return 0.0
    set_body_a, set_body_b = set(body_a), set(body_b)
    combined_a, combined_b = set_title_a | set_body_a, set_title_b | set_body_b
    shared = set_title_a & set_title_b
    if not shared:
        # Совпадение только в теле — разрешаем, но с меньшим весом.
        shared_body = set_body_a & set_body_b
        if not shared_body:
            return 0.0
    weighted = _weighted_overlap(
        set_title_a, set_body_a, set_title_b, set_body_b, idf
    )
    long_a = {term for term in combined_a if len(term) >= 5}
    long_b = {term for term in combined_b if len(term) >= 5}
    long_overlap = (
        len(long_a & long_b) / len(long_a | long_b) if long_a and long_b else 0.0
    )
    containment = len(shared) / min(len(set_title_a), len(set_title_b)) if shared else 0.0
    sequence = SequenceMatcher(None, " ".join(title_a), " ".join(title_b)).ratio()
    bonus = min(0.12, 0.06 * len(proper_a & proper_b))
    numbers_a, numbers_b = _numbers(set_title_a), _numbers(set_title_b)
    if numbers_a and numbers_b:
        bonus += 0.03 if numbers_a & numbers_b else -0.05
    # Штраф за явно разные сущности при общем общем слове:
    # "OpenAI GPT-5" и "OpenAI уволила сотрудников" не должны склеиваться.
    extra_proper_a = proper_a - proper_b
    extra_proper_b = proper_b - proper_a
    if extra_proper_a and extra_proper_b:
        bonus -= 0.04
    similarity = 0.4 * weighted + 0.2 * long_overlap + 0.2 * containment + 0.2 * sequence + bonus
    return max(0.0, min(1.0, similarity))


def _within_window(
    first: Article,
    second: Article,
    max_age_hours: float,
) -> bool:
    """Не склеиваем материалы, разнесённые по времени больше окна."""
    if max_age_hours <= 0:
        return True
    left = _as_utc(first.published_at)
    right = _as_utc(second.published_at)
    if left is None or right is None:
        return True
    return abs((left - right).total_seconds()) <= max_age_hours * 3600.0


# ---------------------------------------------------------------------------
# Кластеризация
# ---------------------------------------------------------------------------


class _UnionFind:
    """Система непересекающихся множеств с сжатием путей."""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, index: int) -> int:
        root = index
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[index] != root:
            self.parent[index], index = root, self.parent[index]
        return root

    def union(self, first: int, second: int) -> None:
        root_a, root_b = self.find(first), self.find(second)
        if root_a != root_b:
            self.parent[root_b] = root_a


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Приводит дату к timezone-aware UTC (наивные даты считаем UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _freshness(value: Optional[datetime], now: datetime) -> float:
    """Свежесть статьи: 1.0 для «сейчас», ~0.5 через сутки-полтора."""
    moment = _as_utc(value)
    if moment is None:
        return 0.5
    age_hours = max(0.0, (now - moment).total_seconds() / 3600.0)
    return math.exp(-age_hours / 30.0)


def _article_key(article: Article) -> str:
    """Ключ статьи для точного совпадения: url_hash, иначе URL."""
    meta = article.meta if isinstance(article.meta, dict) else {}
    return str(meta.get("url_hash") or article.url or article.id or "")


def _choose_cluster_title(articles: Sequence[Article], now: datetime) -> str:
    """Заголовок сюжета — у статьи с наибольшим весом источника и свежестью."""
    best_article: Optional[Article] = None
    best_rank = -1.0
    for article in articles:
        rank = float(article.weighted_source_score or 1.0) * (1.0 + _freshness(article.published_at, now))
        if rank > best_rank:
            best_rank = rank
            best_article = article
    if best_article is None:
        return ""
    return best_article.title


def _cluster_score(articles: Sequence[Article], now: datetime) -> float:
    """Оценка сюжета: охват источников, их вес и свежесть публикаций."""
    coverage = len({article.source_id for article in articles})
    coverage_score = min(1.0, coverage / 3.0)
    weights = [float(article.weighted_source_score or 1.0) for article in articles]
    weight_score = min(1.0, (sum(weights) / len(weights) if weights else 1.0) / 1.5)
    newest = max((_as_utc(article.published_at) for article in articles if article.published_at), default=None)
    freshness = _freshness(newest, now)
    return round(0.5 * coverage_score + 0.25 * weight_score + 0.25 * freshness, 4)


def _fallback_key_terms(articles: Sequence[Article], limit: int) -> List[str]:
    """Частотный алгоритм ключевых слов: учитывает число статей и повторы."""
    document_frequency: Dict[str, int] = {}
    term_frequency: Dict[str, int] = {}
    for article in articles:
        text_parts = [article.title or "", article.summary or "", (article.text or "")[:800]]
        stems = [
            _stem(token)
            for token in tokenize(" ".join(text_parts))
            if len(token) >= 4 and token not in GENERIC_TERMS
        ]
        stems = [stem for stem in stems if stem]
        for stem in set(stems):
            document_frequency[stem] = document_frequency.get(stem, 0) + 1
        for stem in stems:
            term_frequency[stem] = term_frequency.get(stem, 0) + 1
    ranked = sorted(
        document_frequency,
        key=lambda term: (
            -document_frequency[term],
            -term_frequency.get(term, 0),
            -len(term),
            term,
        ),
    )
    return ranked[:limit]


def _external_key_terms(articles: Sequence[Article], limit: int) -> List[str]:
    """Пробует взять ключевые слова из nlp.keywords, если модуль уже есть."""
    try:
        from .nlp.keywords import extract_key_terms  # type: ignore
    except Exception:
        return []
    combined = "\n".join(
        f"{article.title}. {article.summary or (article.text or '')[:600]}".strip()
        for article in articles
        if article.title
    ).strip()
    if not combined:
        return []
    attempts: List[Tuple[Tuple[Any, ...], Dict[str, Any]]] = [
        ((combined, limit), {}),
        ((combined,), {"limit": limit}),
        ((combined,), {"top_n": limit}),
        ((combined,), {}),
    ]
    for args, kwargs in attempts:
        try:
            result = extract_key_terms(*args, **kwargs)  # type: ignore
        except TypeError:
            continue
        except Exception as exc:  # pragma: no cover - чужой модуль не должен ломать дедуп
            logger.debug("nlp.keywords.extract_key_terms недоступен: %s", exc)
            return []
        if not isinstance(result, (list, tuple)):
            continue
        terms: List[str] = []
        for item in result:
            value = ""
            if isinstance(item, str):
                value = item
            elif isinstance(item, (tuple, list)) and item:
                value = str(item[0])
            elif isinstance(item, dict):
                value = str(item.get("term") or item.get("word") or "")
            value = normalize_space(value)
            if value and value not in terms:
                terms.append(value)
        if terms:
            return terms[:limit]
    return []


def _cluster_key_terms(articles: Sequence[Article], limit: int = 8) -> List[str]:
    """Ключевые слова сюжета: внешний NLP-модуль, иначе частотный алгоритм."""
    terms = _external_key_terms(articles, limit)
    if terms:
        return terms
    return _fallback_key_terms(articles, limit)


def _build_cluster(articles: List[Article], now: datetime) -> StoryCluster:
    ordered = sorted(
        articles,
        key=lambda article: (
            -(article.published_at.timestamp() if article.published_at else 0),
            -float(article.weighted_source_score or 1.0),
        ),
    )
    cluster = StoryCluster(
        id=stable_id("story", *sorted(article.id for article in ordered)),
        title=_choose_cluster_title(ordered, now),
        articles=ordered,
        score=_cluster_score(ordered, now),
        key_terms=_cluster_key_terms(ordered),
    )
    return cluster


def _verifier_candidates(
    similarities: List[List[float]],
    threshold: float,
    limit: int,
) -> List[Tuple[float, int, int]]:
    """Пары, где лексика неоднозначна: топ-2 соседа каждой статьи.

    Верхний порог не отсекаем: LLM может и подтвердить пропущенную
    формулировку, и отменить ложную склейку выше порога.
    """
    total = len(similarities)
    candidates: Dict[Tuple[int, int], float] = {}
    for first in range(total):
        neighbours = sorted(
            ((similarities[first][second], second) for second in range(total) if second != first),
            reverse=True,
        )
        for value, second in neighbours[:2]:
            if value < threshold * 0.6:
                break
            left, right = sorted((first, second))
            candidates[(left, right)] = max(candidates.get((left, right), 0.0), value)
    ordered = [
        (value, left, right) for (left, right), value in candidates.items()
    ]
    # Сначала самые неоднозначные: близко к порогу.
    ordered.sort(key=lambda item: (abs(item[0] - threshold), -item[0], item[1], item[2]))
    return ordered[: max(0, int(limit))]


def cluster_articles(
    articles: List[Article],
    threshold: float = 0.34,
    min_sources: int = 1,
    max_age_hours: float = 48.0,
    verifier: Any = None,
) -> List[StoryCluster]:
    """Группирует статьи об одном событии в сюжеты.

    В отличие от старого union-find по заголовкам, здесь:
    * учитывается тело статьи (summary/text) — пересказы с разными
      заголовками могут встретиться;
    * используется complete-linkage: сюжет не растёт транзитивно, если
      крайние статьи уже не похожи друг на друга;
    * статьи, разнесённые по времени больше ``max_age_hours``, не склеиваются.

    :param articles: статьи канала (могут быть из разных источников)
    :param threshold: порог сходства (0..1); по умолчанию 0.34
    :param min_sources: минимальное число разных source_id в сюжете
    :param max_age_hours: максимальное расстояние по времени внутри сюжета
    :return: сюжеты, отсортированные по убыванию оценки
    """
    items = [article for article in articles if article is not None]
    if not items:
        return []
    threshold = max(0.0, min(1.0, float(threshold)))
    min_sources = max(1, int(min_sources))
    max_age_hours = max(0.0, float(max_age_hours))
    now = utcnow()

    title_terms: List[List[str]] = []
    body_terms: List[List[str]] = []
    proper: List[Set[str]] = []
    title_text: List[str] = []
    for article in items:
        title, body = _article_terms(article)
        title_terms.append(title)
        body_terms.append(body)
        proper.append(_proper_terms(article.title))
        title_text.append(article.title or "")

    # IDF по заголовкам и телам: редкие сущности весят больше частых слов.
    document_frequency: Dict[str, int] = {}
    for index in range(len(items)):
        for term in set(title_terms[index]) | set(body_terms[index]):
            document_frequency[term] = document_frequency.get(term, 0) + 1
    total = len(items)
    idf = {
        term: math.log((total + 2.0) / (frequency + 1.0)) + 0.3
        for term, frequency in document_frequency.items()
    }

    # Матрица сходства; 0.0 для пар вне временного окна.
    similarities = [[0.0] * total for _ in range(total)]
    for first in range(total):
        for second in range(first + 1, total):
            if not title_terms[first] or not title_terms[second]:
                continue
            if not _within_window(items[first], items[second], max_age_hours):
                continue
            value = _article_similarity(
                title_terms[first],
                body_terms[first],
                title_terms[second],
                body_terms[second],
                proper[first],
                proper[second],
                idf,
                title_text[first],
                title_text[second],
            )
            similarities[first][second] = similarities[second][first] = value

    # Необязательный LLM-верификатор: только для нескольких неоднозначных
    # пар. None/ошибка = оставляем лексическое сходство без изменений.
    if verifier is not None and total > 1:
        max_calls = int(getattr(verifier, "max_calls", 10) or 0)
        for _, first, second in _verifier_candidates(similarities, threshold, max_calls):
            if _article_key(items[first]) and _article_key(items[first]) == _article_key(items[second]):
                continue
            verdict = verifier.same_event(items[first], items[second])
            if verdict is True:
                logger.debug("LLM подтвердил сюжет: %r ~ %r", items[first].title, items[second].title)
                similarities[first][second] = similarities[second][first] = 1.0
            elif verdict is False:
                logger.debug("LLM разделил сюжеты: %r !~ %r", items[first].title, items[second].title)
                similarities[first][second] = similarities[second][first] = 0.0

    # Точные дубли URL склеиваем безусловно (даже если заголовки разные).
    union_find = _UnionFind(total)
    by_key: Dict[str, int] = {}
    for index, article in enumerate(items):
        key = _article_key(article)
        if not key:
            continue
        if key in by_key:
            union_find.union(index, by_key[key])
        else:
            by_key[key] = index

    grouped: Dict[int, List[int]] = {}
    for index in range(total):
        grouped.setdefault(union_find.find(index), []).append(index)
    groups: List[List[int]] = list(grouped.values())

    # Complete linkage: пара групп сливается, только если ВСЕ статьи на
    # границе похожи не меньше порога. Это не даёт цепочке A~B~C склеить
    # A и C, которые друг на друга не похожи.
    while True:
        best_score = -1.0
        best_pair: Optional[Tuple[int, int]] = None
        for left in range(len(groups)):
            for right in range(left + 1, len(groups)):
                cross = [
                    similarities[a][b]
                    for a in groups[left]
                    for b in groups[right]
                ]
                if not cross:
                    continue
                score = min(cross)
                if score >= threshold and score > best_score:
                    best_score = score
                    best_pair = (left, right)
        if best_pair is None:
            break
        left, right = best_pair
        groups[left].extend(groups[right])
        del groups[right]

    clusters: List[StoryCluster] = []
    for group in groups:
        group_articles = [items[index] for index in group]
        coverage = len({article.source_id for article in group_articles})
        if coverage < min_sources:
            continue
        clusters.append(_build_cluster(group_articles, now))

    clusters.sort(
        key=lambda cluster: (
            -cluster.score,
            -(cluster.last_published.timestamp() if cluster.last_published else 0),
            cluster.id,
        )
    )
    return clusters

# ---------------------------------------------------------------------------
# Защита от повторных заголовков
# ---------------------------------------------------------------------------


def _first_line(text: str, limit: int = 240) -> str:
    """Первая непустая строка текста (обычно это заголовок поста)."""
    for line in str(text or "").splitlines():
        line = normalize_space(line)
        if line:
            return line[:limit]
    return normalize_space(text or "")[:limit]


def _candidate_variants(recent: str) -> List[str]:
    """Короткие фрагменты длинного текста, с которыми сравниваем заголовок."""
    text = normalize_space(recent)
    if not text:
        return []
    if len(text) <= 240:
        return [text]
    variants: List[str] = []
    for line in str(recent).splitlines():
        line = normalize_space(line)
        if line:
            variants.append(line[:240])
        if len(variants) >= 4:
            break
    variants.extend(sentence[:240] for sentence in split_sentences(text)[:4])
    if not variants:
        variants = [text[:240]]
    return variants


def is_duplicate_title(
    title: str,
    recent_texts: Iterable[str],
    threshold: float = 0.55,
) -> bool:
    """Похож ли заголовок на один из недавних текстов (статей/постов).

    :param title: проверяемый заголовок
    :param recent_texts: недавние заголовки или тексты постов
    :param threshold: порог сходства; 0.72 — дедуп статей, 0.55 — защита от
        повторной публикации поста
    """
    candidate = normalize_space(strip_html(str(title or "")))
    candidate_terms = _terms(candidate)
    if not candidate_terms:
        return False
    threshold = max(0.0, min(1.0, float(threshold)))
    candidate_proper = _proper_terms(candidate)
    candidate_set = set(candidate_terms)

    for recent in recent_texts or []:
        if recent is None:
            continue
        text = str(recent).strip()
        if not text:
            continue
        best = 0.0
        for variant in _candidate_variants(text):
            variant_terms = _terms(variant)
            if not variant_terms:
                continue
            similarity = _pair_similarity(
                candidate_terms,
                variant_terms,
                candidate_proper,
                _proper_terms(variant),
            )
            if similarity > best:
                best = similarity
            if best >= threshold:
                return True
        # Длинный текст поста содержит заголовок почти целиком — учитываем это,
        # но только для содержательных заголовков (4+ значимых слова).
        if len(text) >= 160 and len(candidate_set) >= 4:
            text_terms = set(_terms(text[:4000]))
            if text_terms:
                containment = len(candidate_set & text_terms) / len(candidate_set)
                if containment >= 0.85 and containment * 0.95 >= threshold:
                    return True
    return False


__all__ = [
    "cluster_articles",
    "is_duplicate_title",
    "title_similarity",
    "GENERIC_TERMS",
]
