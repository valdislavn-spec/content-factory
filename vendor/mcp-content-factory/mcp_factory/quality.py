"""Детерминированные проверки черновика — качество без лишних вызовов LLM.

Проверки дешёвые и быстрые: ловят то, что можно проверить кодом, а не моделью —
неподтверждённые цифры/годы, длину поста, банворды, пустой или слишком длинный
заголовок. Найденные замечания добавляются к ответу критика, после чего
редактор переписывает пост (или граф сразу отправляет черновик в редактуру).

Проверки не заменяют критика: они страхуют от типовых ошибок и стоят ~0 мс.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# Значимые числа: годы, проценты, суммы, крупные числа и единицы измерения.
# Мелкие числа без единиц (1–2–3 в тексте) не проверяем — слишком много
# ложных срабатываний, а реальные факты почти всегда с процентом/единицей.
_NUMBER_PATTERNS = (
    re.compile(r"\b(?:19|20)\d{2}\b"),  # годы
    re.compile(r"\d+(?:[.,]\d+)?\s?%"),  # проценты
    re.compile(r"[$€₽]\s?\d[\d\s.,]*"),  # суммы
    re.compile(r"\d+(?:[.,]\d+)?\s?(?:млн|млрд|трлн|тыс|тысяч|ГБ|ТБ)"),  # единицы
    re.compile(r"\b\d{1,3}(?:[ \u00a0,]\d{3})+\b"),  # 1 234 / 1,234
)


def _canonical(token: str) -> str:
    """Привести число к сравнимому виду: без пробелов, запятая → точка."""
    text = (token or "").lower().replace("\u00a0", " ")
    text = re.sub(r"\s+", "", text).replace(",", ".")
    return text.strip(".")


def extract_significant_numbers(text: str) -> List[str]:
    """Вытащить из текста числа, которые стоит сверить с источниками."""
    found: List[str] = []
    for pattern in _NUMBER_PATTERNS:
        found.extend(match.group(0) for match in pattern.finditer(text or ""))
    return sorted({_canonical(item) for item in found if _canonical(item)})


def _source_corpus(research: Dict[str, Any], articles: List[Any]) -> str:
    """Нормализованный текст источников: факты исследования + статьи."""
    parts: List[str] = []
    for key in ("facts", "numbers", "angles"):
        for item in research.get(key) or []:
            parts.append(str(item))
    for article in articles:
        parts.append(str(getattr(article, "title", "") or ""))
        parts.append(str(getattr(article, "summary", "") or ""))
    return _canonical("\n".join(parts))


def deterministic_issues(
    title: str,
    body: str,
    research: Dict[str, Any],
    articles: List[Any],
    pipeline: Dict[str, Any],
) -> List[str]:
    """Список замечаний к черновику (пустой список — всё чисто)."""
    if pipeline.get("checks_enabled", True) is False:
        return []
    issues: List[str] = []
    title = (title or "").strip()
    body = (body or "").strip()
    text = title + "\n\n" + body

    title_min = int(pipeline.get("title_min_chars", 15))
    title_max = int(pipeline.get("title_max_chars", 110))
    if not title:
        issues.append("нет заголовка")
    elif len(title) < title_min:
        issues.append("заголовок короче {} знаков".format(title_min))
    elif len(title) > title_max:
        issues.append("заголовок длиннее {} знаков".format(title_max))

    body_min = int(pipeline.get("min_post_chars", 220))
    body_max = int(pipeline.get("max_post_chars", 1800))
    if len(body) < body_min:
        issues.append("текст короче {} знаков".format(body_min))
    elif body_max and len(body) > body_max:
        issues.append("текст длиннее {} знаков".format(body_max))

    for banned in pipeline.get("banned_words") or []:
        word = str(banned or "").strip()
        if word and word.lower() in text.lower():
            issues.append("запрещённая формулировка: «{}»".format(word))

    corpus = _source_corpus(research, articles)
    missing = [
        number
        for number in extract_significant_numbers(text)
        if number not in corpus
    ]
    if missing:
        issues.append(
            "цифры/годы не найдены в источниках: {}".format(", ".join(missing[:6]))
        )
    return issues
