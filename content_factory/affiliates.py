"""Партнёрские (affiliate) ссылки: реестр, UTM, блоки для постов, план вставок.

Зачем: affiliate-документы в проекте уже были, но ссылки жили только в markdown.
Этот модуль — единый источник правды:

    * ``config/affiliates.yaml`` — программы, статусы, привязка к каналам;
    * ``build_tracked_link`` — реф-ссылка + UTM (канал/кампания);
    * ``render_block`` — готовый Telegram-блок «Партнёры» с раскрытием «реклама»;
    * ``AffiliateRotator`` — правило «1 партнёрский блок на N обычных постов»;
    * ``log_block`` — учёт показов в ``growth_events`` (CLI ``growth``).

Безопасность: в блоки попадают только программы со статусом ``ready`` и валидным
http(s)-URL. Ссылки с плейсхолдерами/пустые отбрасываются при загрузке.
"""
from __future__ import annotations

import html as html_module
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

STATUSES = ("ready", "pending", "awaiting_login", "blocked")
_DISCLOSURE_DEFAULT = {
    "en": "Advertising / affiliate link. We may earn a commission if you sign up.",
    "es": "Publicidad / enlace de afiliado. Podemos recibir una comisión si te registras.",
}


class AffiliateError(RuntimeError):
    """Ошибка конфигурации/ссылок affiliate-реестра."""


@dataclass
class Program:
    id: str
    title: str
    url: str = ""
    status: str = "pending"
    kind: str = "affiliate"
    commission: str = ""
    note: str = ""
    age_restricted: bool = False

    @property
    def ready(self) -> bool:
        return self.status == "ready" and bool(self.url)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "status": self.status,
            "kind": self.kind,
            "commission": self.commission,
            "age_restricted": self.age_restricted,
            "note": self.note,
        }


@dataclass
class ChannelAffiliates:
    id: str
    language: str = "en"
    utm_source: str = ""
    programs: List[str] = field(default_factory=list)
    age_restricted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "language": self.language,
            "utm_source": self.utm_source,
            "programs": self.programs,
            "age_restricted": self.age_restricted,
        }


@dataclass
class AffiliateRegistry:
    programs: Dict[str, Program]
    channels: Dict[str, ChannelAffiliates]
    disclosures: Dict[str, str]
    affiliate_every: int = 5

    def channel(self, channel_id: str) -> ChannelAffiliates:
        try:
            return self.channels[channel_id]
        except KeyError as exc:
            raise AffiliateError(
                f"канал {channel_id!r} не найден в config/affiliates.yaml; "
                f"доступны: {', '.join(sorted(self.channels))}"
            ) from exc

    def ready_programs(self, channel_id: str) -> List[Program]:
        channel = self.channel(channel_id)
        return [
            self.programs[program_id]
            for program_id in channel.programs
            if program_id in self.programs and self.programs[program_id].ready
        ]

    def disclosure(self, channel_id: str, language: Optional[str] = None) -> str:
        channel = self.channel(channel_id)
        lang = (language or channel.language or "en").lower()
        text = self.disclosures.get(lang) or _DISCLOSURE_DEFAULT.get(lang) or _DISCLOSURE_DEFAULT["en"]
        if channel.age_restricted and self.disclosures.get("age_18", "18+") not in text:
            text = f"{self.disclosures.get('age_18', '18+')}. {text}"
        return text


# ---------------------------------------------------------------------------
# Загрузка/валидация
# ---------------------------------------------------------------------------


def _validate_url(value: str) -> bool:
    if not value or "{{" in value or "}}" in value:
        return False
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def load_registry(path: Path) -> AffiliateRegistry:
    """Читает YAML и проверяет структуру; ошибки → AffiliateError."""
    import yaml

    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise AffiliateError(f"не удалось прочитать {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AffiliateError(f"конфиг {path}: ожидался объект")
    programs_raw = raw.get("programs")
    channels_raw = raw.get("channels")
    if not isinstance(programs_raw, dict) or not programs_raw:
        raise AffiliateError("конфиг: нет секции programs")
    if not isinstance(channels_raw, dict) or not channels_raw:
        raise AffiliateError("конфиг: нет секции channels")

    programs: Dict[str, Program] = {}
    for program_id, data in programs_raw.items():
        if not isinstance(data, dict):
            raise AffiliateError(f"программа {program_id}: ожидался объект")
        status = str(data.get("status") or "pending").strip().lower()
        if status not in STATUSES:
            raise AffiliateError(f"программа {program_id}: неизвестный статус {status!r}")
        url = str(data.get("url") or "").strip()
        if url and not _validate_url(url):
            raise AffiliateError(f"программа {program_id}: некорректный url {url!r}")
        program = Program(
            id=str(program_id),
            title=str(data.get("title") or program_id),
            url=url,
            status=status,
            kind=str(data.get("kind") or "affiliate"),
            commission=str(data.get("commission") or ""),
            note=str(data.get("note") or ""),
            age_restricted=bool(data.get("age_restricted", False)),
        )
        if program.status == "ready" and not program.url:
            raise AffiliateError(f"программа {program_id}: status=ready без url")
        programs[program.id] = program

    channels: Dict[str, ChannelAffiliates] = {}
    for channel_id, data in channels_raw.items():
        if not isinstance(data, dict):
            raise AffiliateError(f"канал {channel_id}: ожидался объект")
        assigned = data.get("programs") or []
        if not isinstance(assigned, list) or not assigned:
            raise AffiliateError(f"канал {channel_id}: пустой список programs")
        unknown = [str(item) for item in assigned if str(item) not in programs]
        if unknown:
            raise AffiliateError(
                f"канал {channel_id}: неизвестные программы {', '.join(unknown)}"
            )
        language = str(data.get("language") or "en").strip().lower()
        if language not in ("en", "es"):
            raise AffiliateError(f"канал {channel_id}: язык должен быть en/es")
        channels[str(channel_id)] = ChannelAffiliates(
            id=str(channel_id),
            language=language,
            utm_source=str(data.get("utm_source") or f"tg_{channel_id}"),
            programs=[str(item) for item in assigned],
            age_restricted=bool(data.get("age_restricted", False)),
        )

    disclosure_raw = raw.get("disclosure") or {}
    disclosures = {
        str(key): str(value)
        for key, value in (disclosure_raw.items() if isinstance(disclosure_raw, dict) else [])
    }
    rules = raw.get("rules") or {}
    every = int(rules.get("affiliate_every", 5) or 5) if isinstance(rules, dict) else 5
    if every < 1:
        raise AffiliateError("rules.affiliate_every должен быть >= 1")
    return AffiliateRegistry(
        programs=programs,
        channels=channels,
        disclosures=disclosures,
        affiliate_every=every,
    )


def validate_registry(registry: AffiliateRegistry) -> List[str]:
    """Предупреждения (не ошибки): что мешает запуску прямо сейчас."""
    warnings: List[str] = []
    for channel in registry.channels.values():
        ready = registry.ready_programs(channel.id)
        if not ready:
            warnings.append(f"{channel.id}: нет ни одной программы со статусом ready")
        for program_id in channel.programs:
            program = registry.programs[program_id]
            if not program.ready:
                warnings.append(
                    f"{channel.id}: программа {program_id} в статусе {program.status} — в блоки не попадёт"
                )
        if not channel.utm_source.startswith("tg_"):
            warnings.append(f"{channel.id}: utm_source лучше начинать с 'tg_' ({channel.utm_source})")
        if channel.age_restricted and "18+" not in registry.disclosure(channel.id):
            warnings.append(f"{channel.id}: 18+ канал без пометки 18+ в раскрытии")
    return warnings


# ---------------------------------------------------------------------------
# UTM и блоки
# ---------------------------------------------------------------------------


def build_utm(
    url: str,
    source: str,
    medium: str = "telegram",
    campaign: str = "partners",
    content: str = "",
) -> str:
    """Добавляет utm_* к ссылке, сохраняя существующие параметры (code, ref и т.п.)."""
    if not _validate_url(url):
        raise AffiliateError(f"некорректная партнёрская ссылка: {url!r}")
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    utm = {
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
    }
    if content:
        utm["utm_content"] = content
    for key, value in utm.items():
        query[key] = [value]
    encoded = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=encoded))


def tracked_link(registry: AffiliateRegistry, channel_id: str, program_id: str) -> str:
    channel = registry.channel(channel_id)
    program = registry.programs.get(program_id)
    if program is None:
        raise AffiliateError(f"программа {program_id!r} не найдена")
    if not program.ready:
        raise AffiliateError(
            f"{program_id}: статус {program.status} — ссылку ещё нельзя ставить"
        )
    return build_utm(program.url, channel.utm_source)


def _escape(value: Any) -> str:
    return html_module.escape(str(value or ""), quote=True)


def render_block(
    registry: AffiliateRegistry,
    channel_id: str,
    program_id: Optional[str] = None,
    *,
    language: Optional[str] = None,
) -> Dict[str, str]:
    """Готовый блок «Партнёры»: HTML для Telegram + plain для соцсетей."""
    channel = registry.channel(channel_id)
    ready = registry.ready_programs(channel_id)
    if not ready:
        raise AffiliateError(f"{channel_id}: нет программ со статусом ready")
    if program_id:
        program = registry.programs.get(program_id)
        if program is None or not program.ready:
            raise AffiliateError(f"{program_id}: программа не готова к размещению")
        if program_id not in channel.programs:
            raise AffiliateError(f"{program_id}: программа не назначена каналу {channel_id}")
    else:
        program = ready[0]
    link = tracked_link(registry, channel_id, program.id)
    disclosure = registry.disclosure(channel_id, language)
    title = "🤝 Партнёры" if (language or channel.language) == "es" else "🤝 Partners"
    commission = f" — {program.commission}" if program.commission else ""
    html = (
        f"<b>{title}</b>\n"
        f"• <a href=\"{_escape(link)}\">{_escape(program.title)}</a>{_escape(commission)}\n"
        f"\n<i>{_escape(disclosure)}</i>"
    )
    plain = (
        f"{title}\n"
        f"• {program.title}{commission}: {link}\n"
        f"\n{disclosure}"
    )
    return {
        "channel": channel_id,
        "language": channel.language if language is None else str(language),
        "program": program.id,
        "html": html,
        "plain": plain,
        "url": link,
        "disclosure": disclosure,
    }


# ---------------------------------------------------------------------------
# План вставок (правило 1:N)
# ---------------------------------------------------------------------------


class AffiliateRotator:
    """Детерминированная ротация программ: каждый N-й пост получает блок."""

    def __init__(self, registry: AffiliateRegistry, channel_id: str, every: Optional[int] = None) -> None:
        self.registry = registry
        self.channel_id = channel_id
        self.every = max(1, int(every if every is not None else registry.affiliate_every))
        self._ready = registry.ready_programs(channel_id)

    def for_post(self, post_index: int) -> Optional[Program]:
        """post_index с 1; None — пост без партнёрского блока."""
        if self.every < 1 or not self._ready or post_index % self.every != 0:
            return None
        position = (post_index // self.every - 1) % len(self._ready)
        return self._ready[position]

    def plan(self, posts: int) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        for index in range(1, max(0, int(posts)) + 1):
            program = self.for_post(index)
            if program is not None:
                plan.append(
                    {
                        "post": index,
                        "channel": self.channel_id,
                        "program": program.id,
                        "url": tracked_link(self.registry, self.channel_id, program.id),
                    }
                )
        return plan


# ---------------------------------------------------------------------------
# Учёт показов
# ---------------------------------------------------------------------------


def log_block(
    storage: Any,
    channel_id: str,
    program_id: str,
    *,
    event: str = "affiliate_block",
) -> None:
    """Фиксирует показ партнёрского блока в growth_events (для отчёта `growth`)."""
    storage.save_growth_event(
        event,
        channel_id=channel_id,
        payload=program_id,
        source="affiliate",
    )
