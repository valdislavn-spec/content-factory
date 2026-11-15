"""Аудит подключений каналов к публикаторам.

Проверяет только *включённые* в ``publisher_ids`` направления и не делает
сетевых запросов. Этого достаточно, чтобы поймать самую частую ошибку
облачного запуска: публикатор включён в канале, а его ключи не проброшены
в GitHub Actions.

Для сетевой проверки Telegram используйте ``scripts/telegram_check.py``,
для Discord — ``scripts/discord_probe.py``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import Settings
from .models import ChannelConfig
from .publishers import publisher_class, resolve_publisher_name
from .utils import env


@dataclass(frozen=True)
class PublisherConnection:
    """Состояние одного направления публикации у канала."""

    channel_id: str
    publisher: str
    ready: bool
    detail: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _check_publisher(publisher: Any, channel: ChannelConfig) -> Tuple[bool, str]:
    """Вызывает ``check(channel)`` с обратной совместимостью для ``check()``."""
    check = getattr(publisher, "check", None)
    if not callable(check):
        return True, "проверка не требуется"

    try:
        try:
            result = check(channel)
        except TypeError:
            # Часть старых публикаторов принимает только self.
            result = check()
    except Exception as exc:  # noqa: BLE001 - аудит не должен падать из-за одного канала
        return False, f"{type(exc).__name__}: {exc}"

    if isinstance(result, tuple) and len(result) >= 2:
        return bool(result[0]), str(result[1])
    return bool(result), "проверен"


def check_connection(
    channel: ChannelConfig, publisher_name: str, settings: Settings
) -> PublisherConnection:
    """Проверяет одно направление без сетевого запроса."""
    raw_name = str(publisher_name or "").strip()
    canonical = resolve_publisher_name(raw_name)
    if not canonical:
        return PublisherConnection(channel.id, raw_name, False, "пустое имя публикатора")

    publisher_cls = publisher_class(canonical)
    if publisher_cls is None:
        return PublisherConnection(
            channel.id,
            raw_name,
            False,
            f"неизвестный публикатор; доступны: см. `content_factory channels --all`",
        )

    if canonical == "telegram":
        token = (env("TELEGRAM_BOT_TOKEN", "") or "").strip()
        chat_id = str(channel.telegram_chat_id or "").strip()
        missing = []
        if not token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not chat_id:
            missing.append("telegram_chat_id")
        if missing:
            return PublisherConnection(
                channel.id, canonical, False, "не задано: " + ", ".join(missing)
            )
        return PublisherConnection(
            channel.id, canonical, True, f"бот и chat_id заданы ({chat_id})"
        )

    if canonical == "dryrun":
        return PublisherConnection(channel.id, canonical, True, "безопасный dry-run")

    try:
        publisher = publisher_cls(settings)
    except Exception as exc:  # noqa: BLE001
        return PublisherConnection(
            channel.id, canonical, False, f"не удалось создать публикатор: {exc}"
        )

    ready, detail = _check_publisher(publisher, channel)
    return PublisherConnection(channel.id, canonical, ready, detail)


def audit_channel(
    channel: ChannelConfig,
    settings: Settings,
    publisher_names: Optional[Iterable[str]] = None,
) -> List[PublisherConnection]:
    """Возвращает статусы направлений канала (по умолчанию из publisher_ids)."""
    names = channel.publisher_ids if publisher_names is None else publisher_names
    return [check_connection(channel, name, settings) for name in names]


def audit_channels(
    channels: Iterable[ChannelConfig], settings: Settings
) -> List[PublisherConnection]:
    """Возвращает плоский список статусов по всем каналам."""
    rows: List[PublisherConnection] = []
    for channel in channels:
        rows.extend(audit_channel(channel, settings))
    return rows


def all_supported_social_publishers() -> List[str]:
    """Имена публикаторов для режима ``social-check --all``."""
    from .publishers import available_publishers

    return [
        name
        for name in available_publishers()
        if name not in {"dryrun", "telegram"}
    ]


def summarize(rows: Iterable[PublisherConnection]) -> Dict[str, int]:
    """Сводка для JSON/консоли."""
    items = list(rows)
    ready = sum(1 for row in items if row.ready)
    return {
        "connections": len(items),
        "ready": ready,
        "missing": len(items) - ready,
    }


def format_connection(row: PublisherConnection) -> str:
    if row.ready:
        return f"  {row.publisher:12} ✓ настроено: {row.detail}"
    return f"  {row.publisher:12} ✗ не настроено: {row.detail}"
