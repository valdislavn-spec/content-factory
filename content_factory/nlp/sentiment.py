"""Лексиконная тональность русского, английского и испанского текста.

Без ML-моделей: словари позитивных/негативных основ, отрицания
(«не», «not», «no», «sin», «nunca»), усилители («резко», «significantly»,
«muy») и нормировка в диапазон -1..1. Этого достаточно, чтобы отличать
хорошие и плохие новости и не путать их с нейтральными сообщениями.

Морфология испанского не моделируется: словари хранят основы без диакритики,
а входящие слова перед сравнением приводятся к нижнему регистру и теряют
диакритику (á→a, ñ→n) — так «creció» и «crecimiento» попадают в одну основу.
Русское и английское поведение при этом не меняется.
"""
from __future__ import annotations

import re
from typing import List, Tuple

_WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-zÁÉÍÓÚÜÑáéíóúüñ][А-Яа-яЁёA-Za-zÁÉÍÓÚÜÑáéíóúüñ\-]*")

# Диакритика не мешает сравнению основ: «pérdida» → «perdida».
_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")

# Основы (не полные слова) — так ловятся все падежи и спряжения.
_POSITIVE_STEMS: Tuple[str, ...] = (
    "рост",
    "растет",
    "растёт",
    "вырос",
    "увелич",
    "улучш",
    "успех",
    "рекорд",
    "прибыл",
    "достиж",
    "прорыв",
    "выигр",
    "побед",
    "поддерж",
    "польз",
    "выгод",
    "прогресс",
    "развит",
    "инновац",
    "одобр",
    "позитив",
    "хорош",
    "лучш",
    "эффектив",
    "стабильн",
    "надежн",
    "надёжн",
    "перспектив",
    "спасен",
    "спасён",
    "восстанов",
    "компенсац",
    "субсиди",
    "льгот",
    "доходн",
    "привлекательн",
    "укреп",
    "снижен",
    "замедлен",
    "growth",
    "grow",
    "success",
    "record",
    "profit",
    "gain",
    "win",
    "wins",
    "improve",
    "positive",
    "strong",
    "recovery",
    "boost",
    # Испанские основы: рост, успех, рекорд, прибыль, победа, улучшение...
    "crec",
    "aument",
    "mejor",
    "exito",
    "logr",
    "record",
    "ganan",
    "gana",
    "victor",
    "impuls",
    "fortalec",
    "recuper",
    "progres",
    "innovac",
    "aproba",
    "aprueba",
    "benefici",
    "estabil",
    "positiv",
    "optimis",
    "avanz",
    "desarroll",
    "inversion",
    "rentab",
    "subvencion",
)

_NEGATIVE_STEMS: Tuple[str, ...] = (
    "падени",
    "падает",
    "упал",
    "упадут",
    "снизил",
    "сократил",
    "провал",
    "убыт",
    "потер",
    "авар",
    "катастроф",
    "кризис",
    "риск",
    "угроз",
    "опасн",
    "проблем",
    "сбой",
    "ошибк",
    "утечк",
    "взлом",
    "мошен",
    "санкц",
    "запрет",
    "штраф",
    "иск",
    "банкрот",
    "безработ",
    "инфляц",
    "коррупц",
    "скандал",
    "критик",
    "негатив",
    "плох",
    "худш",
    "смерт",
    "болезн",
    "вирус",
    "пандеми",
    "воен",
    "конфликт",
    "войн",
    "теракт",
    "дефицит",
    "долг",
    "обвал",
    "отказ",
    "задерж",
    "расследован",
    "обвинен",
    "обвинён",
    "судебн",
    "fail",
    "loss",
    "crash",
    "decline",
    "drop",
    "risk",
    "threat",
    "crisis",
    "problem",
    "error",
    "breach",
    "hack",
    "fraud",
    "war",
    "attack",
    "negative",
    "weak",
    "down",
    "layoff",
    "lawsuit",
    # Испанские основы: падение, потеря, убыток, кризис, риск, угроза...
    "caid",
    "cae",
    "cayeron",
    "baj",
    "desciend",
    "descend",
    "perdid",
    "perder",
    "perdio",
    "perdieron",
    "crisis",
    "riesg",
    "amenaz",
    "peligr",
    "problema",
    "fall",
    "fallo",
    "error",
    "escandal",
    "corrupcion",
    "sancion",
    "prohib",
    "multa",
    "quiebra",
    "desemple",
    "inflacion",
    "deficit",
    "deuda",
    "conflict",
    "guerra",
    "ataque",
    "victima",
    "muerte",
    "enfermedad",
    "pandem",
    "critic",
    "negativ",
    "debil",
    "mal",
    "peor",
    "investigacion",
    "acusa",
)

_NEGATIONS = frozenset(
    {
        "не",
        "нет",
        "ни",
        "без",
        "никогда",
        "отнюдь",
        "вовсе",
        "not",
        "no",
        "never",
        "without",
        "cannot",
        "cant",
        "don't",
        "doesn't",
        # Испанские отрицания.
        "sin",
        "nunca",
        "jamas",
        "tampoco",
        "ningun",
        "ninguna",
        "ninguno",
    }
)

_INTENSIFIERS = frozenset(
    {
        "очень",
        "весьма",
        "крайне",
        "значительно",
        "резко",
        "серьёзно",
        "серьезно",
        "сильно",
        "максимально",
        "существенно",
        "highly",
        "very",
        "extremely",
        "significantly",
        "sharply",
        # Испанские усилители.
        "muy",
        "significativamente",
        "considerablemente",
        "extremadamente",
        "especialmente",
        "bastante",
        "sumamente",
    }
)

_POSITIVE_WEIGHT = 1.0
_NEGATIVE_WEIGHT = 1.0
_INTENSIFIER_FACTOR = 1.5
_NEGATION_FACTOR = -0.8


def _matches(word: str, stems: Tuple[str, ...]) -> bool:
    for stem in stems:
        if word.startswith(stem):
            return True
    return False


def _normalize_word(token: str) -> str:
    """Нижний регистр, «ё»→«е», испанская диакритика → базовая латиница."""
    return token.lower().replace("ё", "е").translate(_ACCENTS)


def _sentiment_words(tokens: List[str]) -> Tuple[float, int]:
    """Считает суммарный вес тональных слов с учётом отрицаний."""
    total = 0.0
    hits = 0
    pending_negation = 0
    pending_intensity = 1.0
    for token in tokens:
        word = _normalize_word(token)
        if word in _NEGATIONS:
            pending_negation = 3
            continue
        if word in _INTENSIFIERS:
            pending_intensity = _INTENSIFIER_FACTOR
            continue

        weight = 0.0
        if _matches(word, _POSITIVE_STEMS):
            weight = _POSITIVE_WEIGHT
        elif _matches(word, _NEGATIVE_STEMS):
            weight = -_NEGATIVE_WEIGHT
        if weight == 0.0:
            if pending_negation > 0:
                pending_negation -= 1
            pending_intensity = 1.0
            continue

        if pending_negation > 0:
            # «не вырос» — это скорее негативный сигнал, но слабее прямого «упал».
            weight = weight * _NEGATION_FACTOR
            pending_negation = 0
        total += weight * pending_intensity
        hits += 1
        pending_intensity = 1.0
    return total, hits


def detect_sentiment(text: str) -> Tuple[str, float]:
    """Возвращает ``(label, score)``: label — positive/neutral/negative.

    ``score`` лежит в диапазоне -1..1. Пустой текст — нейтральный с нулём.
    """
    if not text or not text.strip():
        return "neutral", 0.0
    tokens = _WORD_RE.findall(text)
    if not tokens:
        return "neutral", 0.0

    total, hits = _sentiment_words(tokens)
    if hits == 0:
        return "neutral", 0.0

    # Делим на корень из числа тональных слов: одно яркое слово в короткой
    # заметке не должно давать максимальный накал.
    normalized = total / max(1.0, hits**0.5)
    # Учитываем насыщенность текста: длинные тексты с редкими эмоциями — нейтральнее.
    density = min(1.0, hits / max(4.0, len(tokens) / 6.0))
    score = normalized * (0.55 + 0.45 * density)
    score = max(-1.0, min(1.0, score))
    score = round(score, 2)

    if score >= 0.15:
        return "positive", score
    if score <= -0.15:
        return "negative", score
    return "neutral", score
