"""Выделение ключевых терминов из текстов новостей.

Реализация на чистом Python: лёгкая нормализация русских словоформ,
частотность с весом TF-IDF по документам, стоп-слова из :data:`utils.STOPWORDS_RU`.
Для английских и испанских текстов язык определяется автоматически (или
передаётся явно): используются :data:`utils.STOPWORDS_EN` /
:data:`utils.STOPWORDS_ES`, а русская морфология не применяется — только
частотность и TF-IDF. Никаких моделей и словарей не скачивается — модуль
работает офлайн.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

from ..utils import STOPWORDS_EN, STOPWORDS_ES, STOPWORDS_RU, detect_text_language

_CYRILLIC_LETTER_RE = re.compile(r"[А-Яа-яЁё]")

# Слово: буква в начале, дальше буквы/цифры/дефис. Дефис нужен для «IT-рынок»;
# испанская диакритика сохраняется, чтобы термин не терял буквы.
_WORD_RE = re.compile(
    r"[A-Za-zА-Яа-яЁёÁÉÍÓÚÜÑáéíóúüñ]"
    r"[A-Za-zА-Яа-яЁё0-9ÁÉÍÓÚÜÑáéíóúüñ\-]*"
)
_MIN_TOKEN_LEN = 3
_MAX_TOKEN_LEN = 40

# Короткие аббревиатуры, которые нельзя терять из-за минимальной длины.
_SHORT_ACRONYMS = frozenset(
    {
        "ии",
        "ввп",
        "днк",
        "цб",
        "ес",
        "сша",
        "оон",
        "фрс",
        "мрот",
        "ит",
        "ai",
        "ml",
        "it",
        "vr",
        "ar",
        "gpt",
        "llm",
        "api",
        "ios",
        "pci",
        "soc",
        # Испанские аббревиатуры.
        "ee",
        "uu",
        "onu",
        "otan",
        "bce",
        "pib",
        "ipc",
        "eeuu",
        "ue",
    }
)

# Общие слова, которые не несут темы сюжета и только засоряют ключевые термины.
_EXTRA_STOPWORDS = frozenset(
    """
    который которая которое которые которых которым которого когда потому поэтому
    также только уже даже если чтобы пока против вокруг между почти около более менее
    сегодня вчера завтра сейчас теперь очень будет были было есть нет можно нужно надо
    сообщает сообщил сообщила сообщили пишет пишут заявил заявила заявили рассказал
    рассказала рассказали появился появилась появилось стало стал стала стали
    новый новая новое новые нового новых крупный крупнейший главный первый второй
    третий последний текущий данный данные случай событие новость новости агентство
    источник источники компания компании эксперт эксперты фото видео подробности
    читайте смотрите подписывайтесь комментарий комментарии название объявил объявила
    представил представила представили рассказали года году году день дня дней время
    раза раз числе связи рамках результате области сфере мира мир
    """.split()
)

# Окончания сортируются от длинных к коротким, чтобы «-ения» срезалось раньше «-я».
_ENDINGS: Tuple[str, ...] = tuple(
    sorted(
        {
            "изациями",
            "изация",
            "ования",
            "ование",
            "ениями",
            "ациями",
            "ностями",
            "ировать",
            "ировал",
            "ировала",
            "ировали",
            "ируется",
            "ируются",
            "ающий",
            "ящий",
            "ующий",
            "ющий",
            "ический",
            "ическая",
            "ическое",
            "ические",
            "овской",
            "евской",
            "овский",
            "евский",
            "аться",
            "яться",
            "иться",
            "еться",
            "уться",
            "ение",
            "ание",
            "ация",
            "аций",
            "ации",
            "ацию",
            "ацией",
            "ением",
            "анием",
            "ения",
            "ению",
            "ность",
            "ости",
            "ость",
            "есть",
            "ать",
            "ять",
            "ить",
            "еть",
            "уть",
            "ыть",
            "ами",
            "ями",
            "ах",
            "ях",
            "ов",
            "ев",
            "ий",
            "ый",
            "ой",
            "ая",
            "ое",
            "ые",
            "ым",
            "им",
            "ых",
            "их",
            "ую",
            "юю",
            "ого",
            "его",
            "ому",
            "ему",
            "ыми",
            "ими",
            "иями",
            "ями",
            "а",
            "я",
            "о",
            "е",
            "у",
            "ю",
            "ы",
            "и",
            "ь",
        },
        key=len,
        reverse=True,
    )
)

_ALL_STOPWORDS = STOPWORDS_RU | _EXTRA_STOPWORDS

# Английская «новостная вода»: формальные слова и речевые обороты прессы.
_EXTRA_STOPWORDS_EN = frozenset(
    """
    monday tuesday wednesday thursday friday saturday sunday
    january february march april june july august september october november december
    told according reportedly source sources official officials people person
    said says saying statement statement said added noted notes wrote write
    more most much many few less least well back even still yet already
    first second third second next last latest previous early late
    up down out off away over under again further forward now today yesterday
    million billion trillion thousand hundred percent percentage
    year years month months week weeks day days hour hours minute minutes
    company companies firm firms business businesses market markets
    including includes included amid among across around us uk eu
    tech technology technologies global world international national local
    report reports reported reporting news update updates updated
    announcement announced unveils unveiled launches launched release released
    rise rises rising rose grow grows growing growth increase increased
    """.split()
)

_ALL_STOPWORDS_EN = STOPWORDS_EN | _EXTRA_STOPWORDS_EN | frozenset(
    word for word in STOPWORDS_RU if word.isascii()
)

# Испанская «новостная вода»: формальные обороты прессы и календарь.
_EXTRA_STOPWORDS_ES = frozenset(
    """
    lunes martes miércoles jueves viernes sábado domingo
    enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre
    según informó informaron declaró declararon anunció anunciaron dijo dijeron
    señaló señalaron explicó explicaron aseguró aseguraron añadió añadieron
    destacó destacaron reportó reportaron publicó publicaron presentó presentaron
    reveló revelaron confirmó confirmaron indicó indicaron agregó agregaron
    sostuvo sostuvieron noticia noticias informe informes fuente fuentes agencia
    agencias medio medios periódico diario revista portal gobierno presidente
    ministro empresa empresas compañía compañías país países ciudad ciudades
    región regiones estado estados mundo nacional internacional global millones
    mil miles porcentaje cifra cifras dato datos caso casos parte partes
    nuevo nueva nuevos nuevas primer primera primeros primeras último última
    últimos últimas gran grandes mayor mayores mejor mejores principal principales
    así también además entonces mientras durante mediante aunque porque
    """.split()
)

_ALL_STOPWORDS_ES = STOPWORDS_ES | _EXTRA_STOPWORDS_ES | frozenset(
    word for word in STOPWORDS_RU if word.isascii()
)


def _stem(word: str) -> str:
    """Очень лёгкая нормализация: срезает частые окончания, не трогая корень."""
    word = word.lower().replace("ё", "е")
    if len(word) <= 4:
        return word
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: -len(ending)]
    return word


def _is_candidate(raw: str) -> bool:
    token = raw.strip()
    if not token or len(token) > _MAX_TOKEN_LEN:
        return False
    lowered = token.lower().replace("ё", "е")
    if lowered in _ALL_STOPWORDS:
        return False
    # Числа и токены без букв не являются терминами.
    if not any(ch.isalpha() for ch in token):
        return False
    if lowered in {"ru", "http", "https", "www", "com", "html", "php", "rss"}:
        return False
    if len(lowered) < _MIN_TOKEN_LEN and lowered not in _SHORT_ACRONYMS:
        return False
    return True


def _surface_form(forms: Counter) -> str:
    """Выбирает самую частую словоформу и приводит её к аккуратному виду."""
    if not forms:
        return ""
    best = forms.most_common(1)[0][0]
    if best.isupper() and len(best) >= 2:
        return best
    # Бренды и смешанный регистр (OpenAI, ChatGPT, YouTube) сохраняем как есть.
    if re.search(r"[A-Za-z]", best) and re.search(r"[A-Z]", best[1:]):
        return best
    return best.lower()


def _normalize_language(value: Optional[str]) -> Optional[str]:
    """Приводит язык к ``ru``/``en``/``es``; ``None`` — автоопределение."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text.startswith(("en", "англ")):
        return "en"
    if text.startswith(("ru", "рус")):
        return "ru"
    if text.startswith(("es", "исп")):
        return "es"
    return None


def _is_candidate_en(raw: str) -> bool:
    """Кандидат-термин для английского текста (без русской морфологии)."""
    token = raw.strip()
    if not token or len(token) > _MAX_TOKEN_LEN:
        return False
    lowered = token.lower()
    if lowered in _ALL_STOPWORDS_EN:
        return False
    if not any(ch.isalpha() for ch in token):
        return False
    # В английских ключевых терминах не должно быть кириллицы.
    if _CYRILLIC_LETTER_RE.search(token):
        return False
    if lowered in {"http", "https", "www", "com", "html", "php", "rss", "amp"}:
        return False
    if len(lowered) < _MIN_TOKEN_LEN and lowered not in _SHORT_ACRONYMS:
        return False
    return True


def _is_candidate_es(raw: str) -> bool:
    """Кандидат-термин для испанского текста (без русской морфологии)."""
    token = raw.strip()
    if not token or len(token) > _MAX_TOKEN_LEN:
        return False
    lowered = token.lower()
    if lowered in _ALL_STOPWORDS_ES:
        return False
    if not any(ch.isalpha() for ch in token):
        return False
    # В испанских ключевых терминах не должно быть кириллицы.
    if _CYRILLIC_LETTER_RE.search(token):
        return False
    if lowered in {"http", "https", "www", "com", "html", "php", "rss", "amp"}:
        return False
    if len(lowered) < _MIN_TOKEN_LEN and lowered not in _SHORT_ACRONYMS:
        return False
    return True


def _rank_terms(scored: List[Tuple[float, int, str, str]], limit: int) -> List[str]:
    """Сортирует термины по весу и убирает дубли словоформ."""
    scored.sort(key=lambda item: (-item[0], -item[1], item[2].lower(), item[3]))
    result: List[str] = []
    used_stems = set()
    used_lower = set()
    for _score, _df, surface, stem in scored:
        key = surface.lower().replace("ё", "е")
        if stem in used_stems or key in used_lower:
            continue
        used_stems.add(stem)
        used_lower.add(key)
        result.append(surface)
        if len(result) >= limit:
            break
    return result


def _extract_ru_terms(documents: List[str], limit: int) -> List[str]:
    """Русские термины: лёгкая нормализация словоформ + TF-IDF (как раньше)."""
    # stem -> счётчик исходных словоформ; нужен для выбора представителя.
    forms: Dict[str, Counter] = {}
    tf: Counter = Counter()
    df: Counter = Counter()

    for document in documents:
        seen_in_doc = set()
        for match in _WORD_RE.finditer(document):
            raw = match.group(0)
            if not _is_candidate(raw):
                continue
            stem = _stem(raw)
            if not stem:
                continue
            tf[stem] += 1
            forms.setdefault(stem, Counter())[raw.strip()] += 1
            if stem not in seen_in_doc:
                df[stem] += 1
                seen_in_doc.add(stem)

    if not tf:
        return []

    total_docs = len(documents)
    scored: List[Tuple[float, int, str, str]] = []
    for stem, frequency in tf.items():
        surface = _surface_form(forms.get(stem, Counter()))
        if not surface:
            continue
        # Сглаженный IDF: термин из одного документа не обнуляется, но весит меньше.
        idf = math.log((total_docs + 1) / (df.get(stem, 1) + 1)) + 1.0
        # Небольшой бонус за длину: короткие обрывки реже бывают содержательными.
        length_bonus = 1.0 + min(0.15, max(0, len(surface) - 3) * 0.01)
        score = frequency * idf * length_bonus
        scored.append((score, df.get(stem, 1), surface, stem))

    return _rank_terms(scored, limit)


def _extract_en_terms(documents: List[str], limit: int) -> List[str]:
    """Английские термины: английские стоп-слова, без русской морфологии."""
    forms: Dict[str, Counter] = {}
    tf: Counter = Counter()
    df: Counter = Counter()

    for document in documents:
        seen_in_doc = set()
        for match in _WORD_RE.finditer(document):
            raw = match.group(0)
            if not _is_candidate_en(raw):
                continue
            stem = raw.strip().lower()
            if not stem:
                continue
            tf[stem] += 1
            forms.setdefault(stem, Counter())[raw.strip()] += 1
            if stem not in seen_in_doc:
                df[stem] += 1
                seen_in_doc.add(stem)

    if not tf:
        return []

    total_docs = len(documents)
    scored: List[Tuple[float, int, str, str]] = []
    for stem, frequency in tf.items():
        surface = _surface_form(forms.get(stem, Counter()))
        if not surface:
            continue
        idf = math.log((total_docs + 1) / (df.get(stem, 1) + 1)) + 1.0
        length_bonus = 1.0 + min(0.15, max(0, len(surface) - 3) * 0.01)
        scored.append((frequency * idf * length_bonus, df.get(stem, 1), surface, stem))

    return _rank_terms(scored, limit)


def _extract_es_terms(documents: List[str], limit: int) -> List[str]:
    """Испанские термины: испанские стоп-слова, без русской морфологии.

    Морфология испанского не моделируется: словоформы считаются разными
    терминами, пока не совпадут буквально. Этого достаточно для новостных
    текстов и не требует словарей.
    """
    forms: Dict[str, Counter] = {}
    tf: Counter = Counter()
    df: Counter = Counter()

    for document in documents:
        seen_in_doc = set()
        for match in _WORD_RE.finditer(document):
            raw = match.group(0)
            if not _is_candidate_es(raw):
                continue
            stem = raw.strip().lower()
            if not stem:
                continue
            tf[stem] += 1
            forms.setdefault(stem, Counter())[raw.strip()] += 1
            if stem not in seen_in_doc:
                df[stem] += 1
                seen_in_doc.add(stem)

    if not tf:
        return []

    total_docs = len(documents)
    scored: List[Tuple[float, int, str, str]] = []
    for stem, frequency in tf.items():
        surface = _surface_form(forms.get(stem, Counter()))
        if not surface:
            continue
        idf = math.log((total_docs + 1) / (df.get(stem, 1) + 1)) + 1.0
        length_bonus = 1.0 + min(0.15, max(0, len(surface) - 3) * 0.01)
        scored.append((frequency * idf * length_bonus, df.get(stem, 1), surface, stem))

    return _rank_terms(scored, limit)


def extract_key_terms(
    texts: Iterable[str],
    top_n: int = 8,
    language: Optional[str] = None,
) -> List[str]:
    """Возвращает до ``top_n`` ключевых терминов, отсортированных по важности.

    Используется TF-IDF по переданным документам: термин, встречающийся в
    нескольких текстах, получает больший вес, чем случайное слово из одного.
    Язык определяется по тексту, если не передан явно: для английских и
    испанских документов работают соответствующие стоп-слова и не
    применяется русская морфология. При пустом вводе возвращается пустой
    список.
    """
    try:
        limit = int(top_n)
    except (TypeError, ValueError):
        limit = 8
    if limit <= 0:
        return []

    documents = [str(text) for text in (texts or []) if text and str(text).strip()]
    if not documents:
        return []

    code = _normalize_language(language) or detect_text_language(documents)
    if code == "en":
        return _extract_en_terms(documents, limit)
    if code == "es":
        return _extract_es_terms(documents, limit)
    return _extract_ru_terms(documents, limit)

