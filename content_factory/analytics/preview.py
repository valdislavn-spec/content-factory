"""Публичное превью Telegram-канала (t.me/s/<username>) — без Telethon.

Страница ``t.me/s/…`` отдаётся Telegram без авторизации и содержит всё, что
нужно для ежедневной аналитики роста:

* число подписчиков канала;
* последние ~20 постов: просмотры, реакции, дата, текст, ссылка;
* название и описание канала.

Модуль сознательно использует только стандартную библиотеку Python и
регулярные выражения: HTML превью стабилен годами, а полноценный парсер
тянул бы лишнюю зависимость. Любая ошибка сети/разметки не должна ронять
отчёт — она превращается в исключение :class:`PreviewError`, которое
вызывающий код обрабатывает сам.
"""
from __future__ import annotations

import html as html_lib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULT_TIMEOUT = 20.0

# Cloudflare перед telegram-proxy пропускает только «браузерный» User-Agent;
# для самого t.me он тоже безопаснее, чем urllib по умолчанию.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_COUNT_RE = re.compile(r"^([0-9][0-9 ,.]*?)([KMBkmb])?$")
_TITLE_RE = re.compile(
    r'tgme_channel_info_header_title"><span dir="auto">(.*?)</span>', re.DOTALL
)
_USERNAME_RE = re.compile(
    r'tgme_channel_info_header_username"><a href="https://t\.me/([^"]+)"'
)
_DESCRIPTION_RE = re.compile(
    r'tgme_channel_info_description">(.*?)</div>', re.DOTALL
)
_COUNTER_RE = re.compile(
    r'tgme_channel_info_counter"><span class="counter_value">([^<]+)</span>'
    r'\s*<span class="counter_type">([^<]+)</span>'
)
_DATAPOST_RE = re.compile(r'data-post="([^"]+)"')
_VIEWS_RE = re.compile(r'tgme_widget_message_views">([^<]+)</span>')
_TIME_RE = re.compile(r'<time datetime="([^"]+)"')
_TEXT_RE = re.compile(
    r'tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL
)
_REACTION_RE = re.compile(r'<span class="tgme_reaction">(.*?)</span>', re.DOTALL)
_REACTION_COUNT_RE = re.compile(r"([0-9][0-9,\s.]*)\s*$")
_SPONSORED_RE = re.compile(r"(?i)^[^\w]*sponsored\b")

_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


class PreviewError(RuntimeError):
    """Превью канала недоступно: сеть, HTTP-ошибка или сменившаяся разметка."""


@dataclass
class PreviewPost:
    """Один пост из публичного превью канала."""

    message_id: int
    post_url: str
    published_at: Optional[str] = None  # ISO 8601, UTC
    views: Optional[int] = None
    reactions: int = 0
    reactions_detail: Dict[str, int] = field(default_factory=dict)
    text: str = ""
    is_sponsored: bool = False

    @property
    def snippet(self) -> str:
        """Первая строка текста поста без разметки (для отчётов)."""
        for line in (self.text or "").splitlines():
            line = line.strip()
            if line:
                return line[:120]
        return ""


@dataclass
class PreviewChannel:
    """Снимок публичного превью канала."""

    username: str
    title: str = ""
    description: str = ""
    subscribers: Optional[int] = None
    posts: List[PreviewPost] = field(default_factory=list)

    def engagement_rate(self, *, limit: int = 20) -> Optional[float]:
        """Реакции / просмотры по последним постам (0..1). None без данных."""
        views = [post.views for post in self.posts[-limit:] if post.views]
        if not views:
            return None
        reactions = sum(post.reactions for post in self.posts[-limit:])
        return reactions / sum(views)


def normalize_username(value: str) -> str:
    """``@name`` / ``https://t.me/name`` / ``name`` → ``name``."""
    text = (value or "").strip()
    text = re.sub(r"^(?:https?://)?(?:t\.me|telegram\.me)/", "", text)
    return text.lstrip("@").strip().strip("/")


def parse_count(value: Optional[str]) -> Optional[int]:
    """«3.67K» → 3670, «202» → 202, «1,2M» → 1200000. Мусор → None."""
    if value is None:
        return None
    text = str(value).strip().replace("\u00a0", " ").replace("\u202f", " ")
    match = _COUNT_RE.match(text)
    if not match:
        return None
    number_text, suffix = match.group(1), match.group(2)
    number_text = number_text.replace(" ", "").replace(",", ".")
    try:
        number = float(number_text)
    except ValueError:
        return None
    if suffix:
        number *= _MULTIPLIERS[suffix.lower()]
    return int(round(number))


def _strip_markup(fragment: str) -> str:
    """HTML-фрагмент → читаемый текст (переносы строк, эмодзи, entities)."""
    text = _BR_RE.sub("\n", fragment or "")
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    return "\n".join(_SPACE_RE.sub(" ", line).strip() for line in text.splitlines()).strip()


def parse_preview(html_text: str, *, username: str = "", limit: int = 20) -> PreviewChannel:
    """Разбирает страницу ``t.me/s/<username>`` в :class:`PreviewChannel`.

    ``limit`` ограничивает число постов (превью и так отдаёт ~20 последних).
    Никогда не бросает исключений: отсутствующие поля остаются пустыми/None,
    чтобы отчёт мог показать частичные данные.
    """
    result = PreviewChannel(username=normalize_username(username))

    title = _TITLE_RE.search(html_text)
    if title:
        result.title = _strip_markup(title.group(1))
    username_match = _USERNAME_RE.search(html_text)
    if username_match and not result.username:
        result.username = username_match.group(1)
    description = _DESCRIPTION_RE.search(html_text)
    if description:
        result.description = _strip_markup(description.group(1))

    for value, counter_type in _COUNTER_RE.findall(html_text):
        if counter_type.strip().lower() == "subscribers":
            result.subscribers = parse_count(value)
            break

    # Посты: превью режется по обёрткам сообщений, внутри — разметка поста.
    parts = re.split(r'(?=<div class="tgme_widget_message_wrap)', html_text)[1:]
    posts: List[PreviewPost] = []
    for part in parts:
        post = _parse_post(part)
        if post is not None:
            posts.append(post)
    result.posts = posts[-limit:] if limit else posts
    return result


def _parse_post(part: str) -> Optional[PreviewPost]:
    data_post = _DATAPOST_RE.search(part)
    if not data_post:
        return None  # служебные сообщения (смена названия/закрепа) без data-post
    slug = data_post.group(1).strip()
    message_id_text = slug.rsplit("/", 1)[-1]
    try:
        message_id = int(message_id_text)
    except ValueError:
        return None

    views_match = _VIEWS_RE.search(part)
    views = parse_count(views_match.group(1)) if views_match else None
    time_match = _TIME_RE.search(part)
    published_at = time_match.group(1).strip() if time_match else None

    text_match = _TEXT_RE.search(part)
    text = _strip_markup(text_match.group(1)) if text_match else ""

    reactions: Dict[str, int] = {}
    for reaction_html in _REACTION_RE.findall(part):
        reaction_text = _strip_markup(reaction_html)
        count_match = _REACTION_COUNT_RE.search(reaction_text)
        if not count_match:
            continue
        count = parse_count(count_match.group(1))
        emoji = reaction_text[: count_match.start()].strip()
        if count:
            reactions[emoji or "?"] = reactions.get(emoji or "?", 0) + count

    return PreviewPost(
        message_id=message_id,
        post_url="https://t.me/" + slug,
        published_at=published_at,
        views=views,
        reactions=sum(reactions.values()),
        reactions_detail=reactions,
        text=text,
        is_sponsored=_is_sponsored(text),
    )


def _is_sponsored(text: str) -> bool:
    """Пост помечен «Sponsored» — это официальная реклама Telegram Ads."""
    first_line = (text.splitlines() or [""])[0].strip()
    return bool(_SPONSORED_RE.match(first_line))


def fetch_preview(
    username: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = BROWSER_USER_AGENT,
    limit: int = 20,
) -> PreviewChannel:
    """Скачивает и разбирает публичное превью канала.

    Бросает :class:`PreviewError` при сетевой/HTTP-ошибке — вызывающий код
    решает, пропустить канал или показать ошибку в отчёте.
    """
    name = normalize_username(username)
    if not name:
        raise PreviewError("пустой username")
    url = "https://t.me/s/" + name
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raise PreviewError("t.me/s/%s: HTTP %s" % (name, exc.code)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PreviewError("t.me/s/%s недоступен: %s" % (name, exc)) from exc
    if status != 200:
        raise PreviewError("t.me/s/%s: HTTP %s" % (name, status))
    return parse_preview(raw.decode("utf-8", errors="replace"), username=name, limit=limit)
