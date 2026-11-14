"""Общие утилиты контент-завода: HTTP без внешних зависимостей, текст, время, файлы.

Модуль сознательно использует только стандартную библиотеку Python, чтобы
проект работал «из коробки» в России без платных API и тяжёлых зависимостей.
"""
from __future__ import annotations

import gzip
import hashlib
import html as html_lib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import MSK

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; ContentFactory/1.0; +https://github.com/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_WHITESPACE_RE = re.compile(r"\s+")
# Буквы с диакритикой нужны испанскому языку: «más», «año», «información».
_WORD_RE = re.compile(r"[а-яёa-z0-9áéíóúüñ]+", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+(?=[А-ЯЁA-Z«\"(¿¡])")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_META_CHARSET_RE = re.compile(rb"<meta[^>]+charset=[\"']?([a-zA-Z0-9_\-]+)", re.IGNORECASE)
_URL_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "_openstat")


class FetchError(RuntimeError):
    """Ошибка загрузки источника (сеть, HTTP-статус, кодировка)."""


class ConfigError(RuntimeError):
    """Ошибка в конфигурации проекта."""


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _decompress(data: bytes, encoding: str) -> bytes:
    encoding = (encoding or "").lower().strip()
    if encoding == "gzip":
        try:
            return gzip.decompress(data)
        except OSError:
            return zlib.decompress(data, 16 + zlib.MAX_WBITS)
    if encoding == "deflate":
        try:
            return zlib.decompress(data)
        except zlib.error:
            return zlib.decompress(data, -zlib.MAX_WBITS)
    return data


def _detect_charset(data: bytes, content_type: str = "") -> str:
    match = re.search(r"charset=([a-zA-Z0-9_\-]+)", content_type or "", re.IGNORECASE)
    if match:
        return match.group(1)
    meta = _META_CHARSET_RE.search(data[:4096])
    if meta:
        try:
            return meta.group(1).decode("ascii")
        except UnicodeDecodeError:
            pass
    # win-1251 — самый частый случай для старых русских сайтов и RSS.
    if data.count(b"\xd0") + data.count(b"\xd1") > 3:
        return "utf-8"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1251"


def http_get(
    url: str,
    timeout: float = 20.0,
    user_agent: str = DEFAULT_USER_AGENT,
    headers: Optional[Dict[str, str]] = None,
    retries: int = 2,
    backoff: float = 2.0,
) -> bytes:
    """GET-запрос с повторами, распаковкой gzip и понятной ошибкой FetchError."""
    if not url:
        raise FetchError("Пустой URL")
    request_headers = {
        "User-Agent": user_agent,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
    }
    if headers:
        request_headers.update(headers)

    last_error: Optional[Exception] = None
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=request_headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                raw = _decompress(raw, response.headers.get("Content-Encoding", ""))
                return raw
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 4xx повторять бессмысленно, кроме 429.
            if 400 <= exc.code < 500 and exc.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
        if attempt < attempts - 1:
            time.sleep(backoff * (attempt + 1))
    raise FetchError(f"Не удалось загрузить {url}: {last_error}")


def http_get_text(
    url: str,
    timeout: float = 20.0,
    user_agent: str = DEFAULT_USER_AGENT,
    headers: Optional[Dict[str, str]] = None,
    retries: int = 2,
    encoding: Optional[str] = None,
) -> str:
    """GET-запрос, возвращающий строку с автоопределением кодировки."""
    raw = http_get(url, timeout=timeout, user_agent=user_agent, headers=headers, retries=retries)
    charset = encoding or _detect_charset(raw)
    for candidate in (charset, "utf-8", "cp1251"):
        try:
            return raw.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_url(url: str) -> str:
    """Убирает UTM-метки, якоря и лишние слэши для дедупликации."""
    if not url:
        return ""
    url = url.strip()
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    query = [(k, v) for k, v in query if not k.lower().startswith(_URL_TRACKING_PREFIXES)]
    path = re.sub(r"/+$", "", parsed.path) or "/"
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def url_hash(url: str) -> str:
    return stable_id(normalize_url(url))


# ---------------------------------------------------------------------------
# HTML / текст
# ---------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    """Вытаскивает видимый текст из HTML, пропуская script/style."""

    BLOCK_TAGS = {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "td",
        "th",
        "blockquote",
        "section",
        "article",
        "header",
        "footer",
        "figcaption",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def strip_html(fragment: str) -> str:
    """Удаляет теги и нормализует пробелы. Безопасно для неполного HTML."""
    if not fragment:
        return ""
    if "<" in fragment and ">" in fragment:
        parser = _TextExtractor()
        try:
            parser.feed(fragment)
            parser.close()
            text = parser.text()
        except Exception:  # pragma: no cover - защита от битого HTML
            text = _HTML_TAG_RE.sub(" ", fragment)
    else:
        text = fragment
    text = html_lib.unescape(text)
    return normalize_space(text)


def normalize_space(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("\u200b", "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def html_escape(text: str) -> str:
    return html_lib.escape(text or "", quote=False)


def split_sentences(text: str) -> List[str]:
    """Простое, но устойчивое разбиение русского/английского текста на предложения."""
    if not text:
        return []
    text = normalize_space(text)
    parts = _SENTENCE_RE.split(text)
    result: List[str] = []
    for part in parts:
        part = part.strip(" \n\t-—•")
        if len(part) < 5:
            continue
        result.append(part)
    return result


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Обрезает по границе слова/предложения, не разрывая HTML-тег."""
    text = text or ""
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[: max(1, limit - len(suffix))]
    for sep in (". ", "! ", "? ", "; ", ", ", " "):
        pos = cut.rfind(sep)
        if pos > limit * 0.6:
            cut = cut[: pos + (1 if sep.startswith((".", "!", "?")) else 0)]
            break
    return cut.rstrip() + suffix


STOPWORDS_RU = frozenset(
    """
    и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
    только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли
    если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя
    ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без
    будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой
    совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех
    никогда можно при наконец два об другой хоть после над больше тот через эти нас
    про всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда
    лучше чуть том нельзя такой им более всегда конечно всю между это как-то также
    который которые которая которых котором этом эта эти всё ещё является стал стала
    могут может быть своих своей своих этот эта
    the a an and or but if in on at to of for with from by as is are was were be
    been being this that these those it its he she they we you i not no do does did
    has have had will would can could should may might must about into over after
    before between during without within than then there their our your his her
    """.split()
)

_RU_STOP = STOPWORDS_RU

# Английские стоп-слова: служебные слова, вспомогательные глаголы и
# «новостная вода». Применяются только к английскому тексту (явный язык или
# автоопределение), поэтому русская токенизация не меняется.
STOPWORDS_EN = frozenset(
    """
    a an the this that these those it its it's he she they we you i me my mine our ours
    your yours his her hers their theirs them us him himself herself itself themselves
    myself yourself ourselves is am are was were be been being have has had having
    do does did doing done will would shall should can could may might must
    and or but if while whereas because although though unless yet so nor not no never
    neither either both each every all any some such own same other another
    in on at to of for with from by as into over after before between during without
    within than then there here about against amid among around across along behind
    below beneath beside besides beyond down except inside near off onto out outside
    since through throughout till toward towards under until up upon via per
    who whom whose which what when where why how whether
    also just only very more most less least too much many few little
    now today yesterday tomorrow soon later once twice again already still even ever
    however therefore thus hence meanwhile instead rather quite almost enough
    said says say saying told tells tell according reports report reported
    announcement announced announces announce new news latest update updates updated
    breaking live watch read follow subscribe click share photo video image
    week weeks month months year years day days time times hour hours minute minutes
    morning evening night first second third last next
    company companies firm firms group inc ltd corp corporation co business
    including included include includes
    percent percentage million billion trillion thousand
    get got make made makes take takes took give gives gave come comes came
    go goes went going want wants wanted use uses used using find finds found
    know knows knew think thinks thought see sees saw seen look looks looked
    feel feels felt become becomes became leave leaves left put puts keep keeps kept
    let lets begin begins began seem seems seemed help helps helped show shows showed
    hear hears heard play plays played run runs ran move moves moved live lives lived
    believe believes believed bring brings brought happen happens happened write writes
    wrote stand stands stood lose loses lost pay pays paid meet meets met lead leads led
    monday tuesday wednesday thursday friday saturday sunday
    january february march april may june july august september october november december
    """.split()
)

# Испанские стоп-слова: служебные слова, местоимения, календарь и
# «новостная вода» испанской прессы. Применяются только к es-тексту, поэтому
# русская и английская токенизация не меняется. Морфология испанского здесь
# не моделируется — только список частых слов.
STOPWORDS_ES = frozenset(
    """
    el la los las un una unos unas de del al a en y o u e que qué quien quién
    quienes como cómo cuando cuándo donde dónde porque por qué para por con sin
    sobre entre hasta desde durante contra según ante bajo tras hacia mediante
    aunque pero sino mas más menos muy tan tanto también tampoco además así ya
    aún todavía entonces luego mientras pues si sí no ni nada nadie algo alguien
    alguno alguna algunos algunas ninguno ninguna otro otra otros otras mismo misma
    mismos mismas todo toda todos todas cada cual cuales cuyo cuya este esta estos
    estas ese esa esos esas esto eso aquel aquella aquellos aquellas mi mis tu tus
    su sus nuestro nuestra nuestros nuestras vuestro vuestra vuestros vuestras le
    les lo se me te nos os yo tú él ella ellos ellas usted ustedes nosotros
    nosotras vosotros vosotras ser es son era eran fue fueron ha han hay había
    habían he hemos tiene tienen tenía tenían puede pueden poder hacer hace hacen
    hizo dicho dice dijo está están estaba estaban estar sido siendo va van iba ir
    viene vienen vino debe deben deber hoy ayer mañana ahora antes después siempre
    nunca jamás vez veces año años mes meses semana semanas día días hora horas
    minuto minutos momento momentos informó informaron declaró declararon anunció
    anunciaron dijo dijeron señaló señalaron explicó explicaron aseguró aseguraron
    añadió añadieron destacó destacaron reportó reportaron publicó publicaron
    presentó presentaron reveló revelaron confirmó confirmaron indicó indicaron
    agregó agregaron sostuvo sostuvieron lunes martes miércoles jueves viernes
    sábado domingo enero febrero marzo abril mayo junio julio agosto septiembre
    octubre noviembre diciembre
    """.split()
)

_CYRILLIC_LETTER_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
# Испанские буквы вне базовой латиницы — сильный признак языка текста.
_SPANISH_SPECIAL_RE = re.compile(r"[ñÑ¿¡]")
_SPANISH_ACCENTED_WORD_RE = re.compile(r"[a-záéíóúüñ]*[áéíóúü][a-záéíóúüñ]*", re.IGNORECASE)
# Служебные слова и «новостная вода» — по их доле в латинском тексте
# отличаем испанский от английского (алфавита для этого недостаточно).
_SPANISH_MARKERS = frozenset(
    """
    de del que en por para con como más pero sus porque entre cuando muy sobre
    también hasta donde desde durante contra según aunque mientras además entonces
    así ahora hoy ayer mañana todo toda todos todas otro otra otros otras este esta
    estos estas ese esa esos esas esto eso aquel aquella aquellos aquellas quien
    quienes cual cuales cuyo cuya mismo misma mismos mismas cada alguno alguna algunos
    algunas ninguno ninguna nada nadie algo alguien siempre nunca jamás vez veces
    año años mes meses semana semanas día días hora horas minuto minutos momento
    momentos hoy ayer mañana gobierno presidente ministro empresa empresas compañía
    compañías país países ciudad ciudades región regiones estado estados mundo
    nacional internacional global millones mil miles porcentaje cifra cifras dato
    datos caso casos parte partes noticia noticias informe informes fuente fuentes
    agencia agencias medio medios periódico diario revista portal informó informaron
    declaró declararon anunció anunciaron dijo dijeron señaló señalaron explicó
    explicaron aseguró aseguraron añadió añadieron destacó destacaron reportó
    reportaron publicó publicaron presentó presentaron reveló revelaron confirmó
    confirmaron indicó indicaron agregó agregaron sostuvo sostuvieron según
    lunes martes miércoles jueves viernes sábado domingo enero febrero marzo abril
    mayo junio julio agosto septiembre octubre noviembre diciembre
    """.split()
)


def detect_text_language(texts: Any, default: str = "ru") -> str:
    """Определяет язык текстов по алфавиту и служебным словам.

    Возвращает ``ru``, ``en`` или ``es``. Русский определяется по кириллице.
    Для латиницы однозначно различить английский и испанский по алфавиту
    нельзя, поэтому используется осторожная эвристика: доля испанских
    служебных слов, буквы «ñ»/«¿»/«¡» и диакритика. Если признаков мало,
    возвращается ``en`` (прежнее поведение для латинского текста).
    """
    if isinstance(texts, str):
        documents = [texts]
    else:
        documents = [str(text) for text in (texts or []) if text and str(text).strip()]
    sample = " ".join(documents)[:20000]
    cyrillic = len(_CYRILLIC_LETTER_RE.findall(sample))
    latin = len(_LATIN_LETTER_RE.findall(sample))
    if latin >= 20 and cyrillic <= 2:
        if _looks_spanish(sample):
            return "es"
        return "en"
    code = str(default or "ru").strip().lower()
    if code.startswith("en"):
        return "en"
    if code.startswith("es"):
        return "es"
    return "ru"


def _looks_spanish(sample: str) -> bool:
    """Эвристика испанского для латинского текста (без кириллицы)."""
    lowered = sample.lower()
    if _SPANISH_SPECIAL_RE.search(lowered):
        # «ñ», «¿», «¡» практически однозначны.
        return True
    tokens = _WORD_RE.findall(lowered)
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in _SPANISH_MARKERS)
    ratio = hits / float(len(tokens))
    accented = len(_SPANISH_ACCENTED_WORD_RE.findall(lowered))
    if hits >= 5 and ratio >= 0.15:
        return True
    if hits >= 3 and ratio >= 0.30:
        return True
    if hits >= 2 and ratio >= 0.20 and accented >= 1:
        return True
    return False


def tokenize(
    text: str,
    min_len: int = 2,
    remove_stopwords: bool = True,
    language: Optional[str] = None,
) -> List[str]:
    """Токенизация с приведением к нижнему регистру и фильтром стоп-слов.

    ``language=None`` сохраняет прежнее русское поведение. ``language="en"``
    (или ``"english"``) переключает набор стоп-слов на английский,
    ``language="es"`` (или ``"español"``) — на испанский.
    """
    if not text:
        return []
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    if language is None:
        stopwords = _RU_STOP
    else:
        code = str(language).strip().lower()
        if code.startswith(("en", "англ")):
            stopwords = STOPWORDS_EN
        elif code.startswith(("es", "исп")):
            stopwords = STOPWORDS_ES
        else:
            stopwords = _RU_STOP
    result = []
    for token in tokens:
        if len(token) < min_len:
            continue
        if remove_stopwords and token in stopwords:
            continue
        result.append(token)
    return result


def token_set(text: str, language: Optional[str] = None) -> set:
    return set(tokenize(text, language=language))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def stable_id(*parts: Any) -> str:
    """Детерминированный короткий id (sha1) для URL/текста."""
    payload = "|".join(str(p) for p in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def extract_numbers(text: str, limit: int = 8) -> List[str]:
    """Вытаскивает числа с единицами измерения/процентами/валютами."""
    pattern = re.compile(
        r"(?<![\w])(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+(?:[.,]\d+)?)"
        r"\s*(?:%|₽|руб(?:\.|лей|ля|ль)?|долл(?:ар\w*)?|\$|€|млн|млрд|трлн|тыс\.?|"
        r"млрд|км|кг|м|г|лет|год\w*|мес\w*|дн\w*|человек|чел\.?)(?![\w])",
        re.IGNORECASE,
    )
    found: List[str] = []
    for match in pattern.finditer(text or ""):
        value = normalize_space(match.group(0))
        if value not in found:
            found.append(value)
        if len(found) >= limit:
            break
    return found


# ---------------------------------------------------------------------------
# Даты
# ---------------------------------------------------------------------------


def parse_datetime(value: Any) -> Optional[datetime]:
    """Парсит RFC-822 (RSS), ISO-8601 и распространённые варианты дат."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    iso = raw.replace("Z", "+00:00")
    iso = re.sub(r"(\.\d{3})\d+", r"\1", iso)
    for candidate in (iso, iso.replace(" ", "T")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    for fmt in (
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def localize(dt: Optional[datetime], offset_hours: int = 3) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=offset_hours)))


def format_local(dt: Optional[datetime], offset_hours: int = 3, with_time: bool = True) -> str:
    """Форматирует дату в местном поясе (по умолчанию МСК): 18.10.2026 09:00."""
    if dt is None:
        return ""
    local = localize(dt, offset_hours)
    assert local is not None
    return local.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


def format_iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def msk_now() -> datetime:
    return datetime.now(MSK)


def parse_hhmm(value: str) -> Tuple[int, int]:
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", str(value))
    if not match:
        raise ValueError(f"Некорректное время в расписании: {value!r} (ожидается HH:MM)")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Некорректное время в расписании: {value!r}")
    return hour, minute


# ---------------------------------------------------------------------------
# Файлы
# ---------------------------------------------------------------------------


def ensure_dir(path: Any) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def atomic_write_text(path: Any, content: str) -> Path:
    """Запись через временный файл — защита от недописанных отчётов/постов."""
    p = Path(path)
    ensure_dir(p.parent)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, p)
    return p


def read_json(path: Any, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Any, data: Any) -> Path:
    return atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_text(path: Any, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return default


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on", "да")


def load_dotenv(path: Any = ".env") -> None:
    """Минимальный загрузчик .env (без зависимостей); не перетирает окружение."""
    file_path = Path(path)
    if not file_path.exists():
        return
    for line in file_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Признаки того, что аккаунт в fediverse-сети недоступен (страйк, блокировка,
# протухший токен): это состояние конфигурации/модерации, а не сбой пайплайна.
UNAVAILABLE_MARKERS = (
    "disabled",
    "suspended",
    "http 401",
    "http 403",
    "unauthorized",
    "forbidden",
    "invalid access token",
)


def account_unavailable(text: Any) -> bool:
    """True, если ошибка публикации означает «аккаунт/токен недоступен»."""
    low = str(text or "").lower()
    return bool(low) and any(marker in low for marker in UNAVAILABLE_MARKERS)


def chunks(sequence: Sequence[Any], size: int) -> List[Sequence[Any]]:
    return [sequence[i : i + size] for i in range(0, len(sequence), max(1, size))]
