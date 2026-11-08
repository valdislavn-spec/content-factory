"""Модели данных контент-завода.

Все модули обмениваются только этими структурами, поэтому контракты
зафиксированы здесь. Используются только средства стандартной библиотеки.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Россия с 2014 года не переходит на летнее время, поэтому фиксированный
# пояс UTC+3 корректен и не требует внешней базы часовых поясов.
MSK = timezone(timedelta(hours=3), name="MSK")


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Приводит дату к timezone-aware UTC (наивные даты считаем UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    """Текущее время в UTC (все даты внутри системы — timezone-aware UTC)."""
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    """Короткий уникальный идентификатор."""
    value = uuid.uuid4().hex[:16]
    return f"{prefix}{value}" if prefix else value


@dataclass
class SourceConfig:
    """Описание одного источника (RSS, веб-страница, Telegram-канал)."""

    id: str
    type: str = "rss"
    url: str = ""
    name: str = ""
    weight: float = 1.0
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        self.type = str(self.type or "rss").strip().lower()
        self.name = self.name or self.id
        self.weight = float(self.weight)


@dataclass
class ChannelConfig:
    """Настройки одного Telegram-канала (тема, источники, расписание)."""

    id: str
    title: str
    topics: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    sources: List[SourceConfig] = field(default_factory=list)
    schedule: List[str] = field(default_factory=lambda: ["09:00", "18:00"])
    timezone_offset: int = 3
    posts_per_day: int = 2
    tone: str = "expert"
    max_post_chars: int = 3500
    min_relevance: float = 0.25
    # Даже источники с options.trust проверять по темам канала: общие ленты
    # (Guardian/CBS и т.п.) иначе протаскивают чужие темы (крикет в US Sports).
    strict_topics: bool = False
    formats: List[str] = field(default_factory=lambda: ["digest", "story", "analysis"])
    # Пиковое время: ночью — только короткий дайджест, днём — микс форматов.
    content_mix: Dict[str, int] = field(
        default_factory=lambda: {"story": 30, "analysis": 40, "interactive": 30}
    )
    min_cluster_chars: int = 0  # 0 = взять глобальное значение из settings
    night_max_chars: int = 900
    night_window: str = "23:00-07:00"
    # Пиковые окна по локальному времени (статистика активности Telegram).
    peak_windows: List[str] = field(
        default_factory=lambda: ["08:00-10:00", "12:00-14:00", "18:00-23:00"]
    )
    content_mix_peak: Dict[str, int] = field(
        default_factory=lambda: {"story": 20, "analysis": 40, "interactive": 40}
    )
    hashtags: List[str] = field(default_factory=list)
    cta: str = ""
    # Живая строка рынка в конце поста (BTC/ETH/Kalshi), см. integrations/marketline.py
    market_line: Dict[str, Any] = field(default_factory=dict)
    # Реферальная строка (BingX и т.п.): link/enabled/every_n_posts/disclaimer
    affiliate: Dict[str, Any] = field(default_factory=dict)
    telegram_chat_id: str = ""
    publisher_ids: List[str] = field(default_factory=lambda: ["telegram"])
    enabled: bool = True
    emoji: bool = True
    language: str = "ru"
    description: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        self.title = str(self.title).strip() or self.id
        self.topics = [str(t).strip() for t in self.topics if str(t).strip()]
        self.exclude_keywords = [str(t).strip().lower() for t in self.exclude_keywords if str(t).strip()]
        self.schedule = [str(s).strip() for s in self.schedule]
        self.hashtags = [self._normalize_tag(t) for t in self.hashtags if str(t).strip()]
        self.formats = [str(f).strip().lower() for f in self.formats] or ["story"]
        self.publisher_ids = [str(p).strip().lower() for p in self.publisher_ids] or ["telegram"]
        self.posts_per_day = max(1, int(self.posts_per_day))
        self.max_post_chars = max(400, int(self.max_post_chars))
        mix: Dict[str, int] = {}
        for key, value in (self.content_mix or {}).items():
            try:
                mix[str(key).strip().lower()] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        self.content_mix = mix or {"story": 30, "analysis": 40, "interactive": 30}
        self.min_cluster_chars = max(0, int(self.min_cluster_chars))
        self.night_max_chars = max(300, int(self.night_max_chars))
        self.night_window = str(self.night_window or "23:00-07:00").strip()
        self.peak_windows = [str(value).strip() for value in (self.peak_windows or []) if str(value).strip()]
        peak_mix: Dict[str, int] = {}
        for key, value in (self.content_mix_peak or {}).items():
            try:
                peak_mix[str(key).strip().lower()] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        self.content_mix_peak = peak_mix or {"story": 20, "analysis": 40, "interactive": 40}
        self.min_relevance = float(self.min_relevance)
        self.timezone_offset = int(self.timezone_offset)

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        tag = str(tag).strip()
        return tag if tag.startswith("#") else "#" + tag.replace(" ", "_")

    @property
    def local_tz(self) -> timezone:
        return timezone(timedelta(hours=self.timezone_offset))


@dataclass
class Article:
    """Новость/пост, полученный из источника."""

    id: str
    title: str
    url: str
    source_id: str
    source_name: str
    published_at: datetime
    text: str = ""
    summary: str = ""
    language: str = "ru"
    fetched_at: datetime = field(default_factory=utcnow)
    tags: List[str] = field(default_factory=list)
    weighted_source_score: float = 1.0
    meta: Dict[str, Any] = field(default_factory=dict)

    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def content_for_analysis(self) -> str:
        """Текст, пригодный для анализа: description/summary, если нет полного."""
        return self.text or self.summary


@dataclass
class StoryCluster:
    """Группа статей об одном событии из разных источников."""

    id: str
    title: str
    articles: List[Article] = field(default_factory=list)
    score: float = 0.0
    key_terms: List[str] = field(default_factory=list)
    first_published: Optional[datetime] = None
    last_published: Optional[datetime] = None
    channel_id: str = ""
    relevance: float = 0.0

    def __post_init__(self) -> None:
        if not self.articles:
            return
        dates = [as_utc(a.published_at) for a in self.articles if a.published_at]
        if dates:
            self.first_published = as_utc(self.first_published) or min(dates)
            self.last_published = as_utc(self.last_published) or max(dates)

    @property
    def coverage(self) -> int:
        """Сколько разных источников написали об этом событии."""
        return len({a.source_id for a in self.articles})

    @property
    def source_names(self) -> List[str]:
        seen: List[str] = []
        for article in self.articles:
            if article.source_name not in seen:
                seen.append(article.source_name)
        return seen

    @property
    def combined_text(self) -> str:
        return "\n\n".join(a.content_for_analysis for a in self.articles if a.content_for_analysis)


@dataclass
class Analysis:
    """Результат аналитики по кластеру: резюме, факты, тональность, ракурсы."""

    summary: str = ""
    bullets: List[str] = field(default_factory=list)
    key_terms: List[str] = field(default_factory=list)
    sentiment: str = "neutral"  # positive | neutral | negative
    sentiment_score: float = 0.0
    numbers: List[str] = field(default_factory=list)
    perspectives: List[Dict[str, str]] = field(default_factory=list)
    source_count: int = 0
    source_names: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class GeneratedPost:
    """Готовый пост для публикации (text — версия для Telegram HTML)."""

    id: str
    channel_id: str
    cluster_id: str
    format: str
    text: str
    hashtags: List[str] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    score: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def plain_text(self) -> str:
        from .utils import strip_html

        return strip_html(self.text)


@dataclass
class PublishResult:
    """Результат публикации в одну соцсеть/канал."""

    channel_id: str
    post_id: str
    publisher: str
    ok: bool = False
    external_id: str = ""
    url: str = ""
    error: str = ""
    dry_run: bool = False
    published_at: datetime = field(default_factory=utcnow)


@dataclass
class RunResult:
    """Итог одного запуска конвейера по каналу."""

    channel_id: str
    started_at: datetime = field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    articles_fetched: int = 0
    articles_new: int = 0
    clusters: int = 0
    posts_generated: int = 0
    posts_published: int = 0
    errors: List[str] = field(default_factory=list)
    results: List[PublishResult] = field(default_factory=list)
    dry_run: bool = False

    def add_error(self, message: str) -> None:
        self.errors.append(str(message))

    def finish(self) -> "RunResult":
        self.finished_at = utcnow()
        return self

    @property
    def duration_sec(self) -> float:
        if not self.finished_at:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()


@dataclass
class MetricSnapshot:
    """Срез метрик канала для аналитики."""

    channel_id: str
    collected_at: datetime = field(default_factory=utcnow)
    subscribers: Optional[int] = None
    posts_total: int = 0
    posts_published: int = 0
    articles_total: int = 0
    clusters_total: int = 0
    avg_post_chars: float = 0.0
    top_sources: List[Dict[str, Any]] = field(default_factory=list)
    top_terms: List[Dict[str, Any]] = field(default_factory=list)
    formats: Dict[str, int] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)
