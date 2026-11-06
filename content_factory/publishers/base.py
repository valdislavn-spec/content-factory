"""Базовый интерфейс публикаторов и общие помощники.

Публикатор получает готовый пост (Telegram HTML) и настройки канала, а
возвращает PublishResult. Наружу публикаторы не бросают исключений: любая
ошибка сети/API превращается в PublishResult(ok=False, error="...").

Здесь же лежит разбиение длинного HTML-поста на части: Telegram принимает
сообщения не длиннее 4096 символов, а теги нельзя разрывать посередине —
иначе parse_mode=HTML вернёт ошибку и пост не опубликуется.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Iterator, List, Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult

# Ограничение Telegram Bot API на длину текста одного сообщения.
TELEGRAM_MESSAGE_LIMIT = 4096
# Ограничение ВКонтакте на длину сообщения стены (с запасом).
VK_MESSAGE_LIMIT = 16000

# Разметка Telegram: тег либо HTML-сущность (её тоже нельзя разрезать).
_HTML_TOKEN_RE = re.compile(
    r"(<[^>]*>|&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);)"
)
_TAG_NAME_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9-]*)")
# void-теги не имеют закрывающей пары
_VOID_TAGS = frozenset({"br", "hr", "img", "wbr"})


class Publisher(ABC):
    """Интерфейс публикатора: одна соцсеть/канал."""

    name: str = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        """Публикует пост и возвращает результат (не бросает исключений)."""

    @abstractmethod
    def check(self) -> Tuple[bool, str]:
        """Проверяет готовность публикатора: (ok, понятное сообщение)."""

    # ------------------------------------------------------------------
    # Вспомогательные методы для наследников
    # ------------------------------------------------------------------
    def dry_run_publisher(self) -> "Publisher":
        """Публикатор dry-run: используется при settings.dry_run и для предпросмотра."""
        from .dryrun import DryRunPublisher

        return DryRunPublisher(self.settings)

    def _result(
        self,
        post: GeneratedPost,
        channel: ChannelConfig,
        *,
        ok: bool,
        external_id: str = "",
        url: str = "",
        error: str = "",
        dry_run: bool = False,
    ) -> PublishResult:
        return PublishResult(
            channel_id=channel.id,
            post_id=post.id,
            publisher=self.name,
            ok=ok,
            external_id=external_id,
            url=url,
            error=error,
            dry_run=dry_run,
        )


def _parse_tag(token: str) -> Tuple[str, bool, bool]:
    """Возвращает (имя, закрывающий?, одиночный?) для HTML-тега."""
    match = _TAG_NAME_RE.match(token)
    if not match:
        return "", False, True
    name = match.group(2).lower()
    closing = match.group(1) == "/"
    self_closing = token.rstrip().endswith("/>") or name in _VOID_TAGS
    return name, closing, self_closing


def _html_tokens(fragment: str) -> Iterator[Tuple[str, str]]:
    """Разбивает фрагмент на ('text'|'tag'|'entity', кусок), ничего не теряя."""
    position = 0
    for match in _HTML_TOKEN_RE.finditer(fragment):
        if match.start() > position:
            yield "text", fragment[position : match.start()]
        token = match.group(1)
        yield ("tag" if token.startswith("<") else "entity"), token
        position = match.end()
    if position < len(fragment):
        yield "text", fragment[position:]


def _safe_cut(piece: str, available: int) -> int:
    """Ищет границу разреза внутри available символов (абзац/слово, потом жёстко)."""
    if available <= 0:
        return 0
    if available >= len(piece):
        return len(piece)
    floor = max(1, int(available * 0.5))
    newline = piece.rfind("\n", 0, available + 1)
    if newline >= floor:
        return newline + 1
    space = piece.rfind(" ", 0, available + 1)
    if space >= floor:
        return space + 1
    return available


def split_html_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> List[str]:
    """Делит HTML-пост на части <= limit, не разрывая теги и HTML-сущности.

    Каждая часть — самостоятельный корректный HTML: открытые в конце теги
    закрываются, а в начале следующей части открываются снова. Пустые части
    отбрасываются.
    """
    text = text or ""
    if limit <= 0:
        limit = TELEGRAM_MESSAGE_LIMIT
    if len(text) <= limit:
        return [text] if text else []

    chunks: List[str] = []
    body: List[str] = []
    # стек открытых тегов: (имя, исходный открывающий тег)
    open_tags: List[Tuple[str, str]] = []

    def closing_tags() -> str:
        return "".join("</{}>".format(name) for name, _ in reversed(open_tags))

    def opening_tags() -> str:
        return "".join(raw for _, raw in open_tags)

    def body_length() -> int:
        return sum(len(part) for part in body)

    def has_content() -> bool:
        return body_length() > len(opening_tags())

    def flush() -> None:
        nonlocal body
        chunk = "".join(body) + closing_tags()
        if chunk.strip():
            chunks.append(chunk)
        # новая часть начинается с повторного открытия незакрытых тегов
        body = [opening_tags()] if open_tags else []

    def append_atomic(piece: str) -> None:
        """Добавляет неделимый кусок (сущность, тег) целиком."""
        available = limit - body_length() - len(closing_tags())
        if len(piece) > available and has_content():
            flush()
        body.append(piece)

    def append_text(piece: str) -> None:
        rest = piece
        while rest:
            available = limit - body_length() - len(closing_tags())
            if available <= 0:
                if has_content():
                    flush()
                    continue
                # крайне длинные открывающие теги: вынужденная жёсткая нарезка
                chunks.append(rest[:limit])
                rest = rest[limit:]
                continue
            if len(rest) <= available:
                body.append(rest)
                return
            cut = _safe_cut(rest, available)
            if cut <= 0:
                cut = min(available, len(rest))
            body.append(rest[:cut])
            rest = rest[cut:].lstrip()
            flush()

    for kind, value in _html_tokens(text):
        if kind == "text":
            append_text(value)
            continue
        if kind == "entity":
            append_atomic(value)
            continue

        name, closing, self_closing = _parse_tag(value)
        if closing and name:
            # закрывающий тег уже учтён в зарезервированном closing_tags()
            body.append(value)
            for index in range(len(open_tags) - 1, -1, -1):
                if open_tags[index][0] == name:
                    del open_tags[index]
                    break
        elif self_closing or not name:
            append_atomic(value)
        else:
            reserve = len(value) + len("</{}>".format(name))
            available = limit - body_length() - len(closing_tags()) - reserve
            if available < 0 and has_content():
                flush()
            body.append(value)
            open_tags.append((name, value))

    if body or chunks:
        flush()
    return [chunk for chunk in chunks if chunk.strip()]
