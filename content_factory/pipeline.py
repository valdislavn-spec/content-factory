"""Конвейер контент-завода.

Поток одного канала:
    источники → фильтр темы/свежести → дедупликация и кластеризация сюжетов →
    суммаризация и анализ → генерация поста → проверки качества →
    публикация (Bot API / VK / dry-run) → запись в SQLite → аналитика.

Каждый шаг изолирован: сбой одного источника или поста не останавливает канал.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import Settings, load_channels
from .dedup import cluster_articles, is_duplicate_title
from .trends import collect_trends
from .models import (
    Article,
    Analysis,
    ChannelConfig,
    GeneratedPost,
    PublishResult,
    RunResult,
    StoryCluster,
    utcnow,
)
from .nlp.analyzer import analyze_cluster
from .nlp.generator import generate_digest, generate_post
from .nlp.llm import get_llm
from .integrations.dify_posts import build_post_generator
from .publishers import Publisher, get_publisher
from .sources import get_adapter
from .storage import Storage
from .utils import (
    tokenize,
    normalize_space,
    stable_id,
    strip_html,
    url_hash,
    detect_text_language,
)

log = logging.getLogger("content_factory.pipeline")


# ---------------------------------------------------------------------------
# Отбор и фильтрация статей
# ---------------------------------------------------------------------------


def _keyword_pattern(keyword: str) -> Optional[re.Pattern]:
    keyword = normalize_space(keyword).lower()
    if not keyword:
        return None
    # Короткие слова (ИИ, тур) ищем только целиком, чтобы не ловить «России».
    if len(keyword) <= 2 or keyword.isdigit():
        return re.compile(
            r"(?<![а-яёa-z0-9])" + re.escape(keyword) + r"(?![а-яёa-z0-9])",
            re.IGNORECASE,
        )
    return None


def match_keyword(keyword: str, haystack: str) -> bool:
    """Проверяет ключевое слово темы: подстрокой (стемы) или по границам (короткие)."""
    keyword = keyword.strip().lower()
    if not keyword or not haystack:
        return False
    pattern = _keyword_pattern(keyword)
    if pattern is not None:
        return pattern.search(haystack) is not None
    return keyword in haystack.lower()


def score_article(article: Article, channel: ChannelConfig) -> Tuple[float, List[str]]:
    """Релевантность статьи теме канала: 0..1 + сработавшие ключевые слова.

    Совпадение в заголовке весит больше, чем в тексте. Три «очка» = максимум.
    """
    title = (article.title or "").lower()
    body = (article.content_for_analysis or "").lower()
    for bad in channel.exclude_keywords:
        if bad and (bad in title or bad in body):
            return 0.0, []
    points = 0.0
    matched: List[str] = []
    for keyword in channel.topics:
        if match_keyword(keyword, title):
            points += 2.0
            matched.append(keyword)
        elif match_keyword(keyword, body):
            points += 0.5
            matched.append(keyword)
    return min(1.0, points / 3.0), matched


def post_language_ok(text: str, language: str) -> bool:
    """Пост написан на языке канала?

    Эвристика по алфавиту/служебным словам ненадёжна на коротких текстах,
    поэтому короче 120 символов не проверяем. Для ``ru`` проверку не включаем:
    текущая сеть работает на ``en``/``es``.
    """
    lang = str(language or "").strip().lower()
    if lang not in ("en", "es"):
        return True
    plain = normalize_space(strip_html(text or ""))
    if len(plain) < 120:
        return True
    return detect_text_language([plain], default=lang) == lang


def _published_url_hashes(
    storage: Storage, channel: ChannelConfig, hours: float = 72
) -> set:
    """Хэши URL уже опубликованных источников — чтобы не повторять сюжеты."""
    try:
        urls = storage.recent_post_sources(channel.id, hours=hours)
    except Exception:  # noqa: BLE001 - дедуп не должен ронять канал
        log.debug("Не удалось получить URL последних постов %s", channel.id, exc_info=True)
        return set()
    return {url_hash(url) for url in urls if url}


def _cluster_published(cluster: StoryCluster, published_hashes: set) -> bool:
    """Сюжет уже публиковался, если хотя бы одна его статья есть в постах."""
    if not published_hashes:
        return False
    for article in cluster.articles:
        url = str(getattr(article, "url", "") or "")
        if url and url_hash(url) in published_hashes:
            return True
    return False


def filter_articles(
    channel: ChannelConfig,
    articles: Sequence[Article],
    settings: Settings,
    now: Optional[datetime] = None,
) -> List[Article]:
    """Фильтрует по свежести и теме, убирает точные дубли URL/заголовков."""
    now = now or utcnow()
    lookback = timedelta(hours=float(settings.pipeline.get("lookback_hours", 30)))
    min_relevance = float(channel.min_relevance)
    # Источники с options.trust: true тематические (например, N+1 для науки):
    # им доверяем без жёсткого фильтра по ключевым словам, но стоп-слова
    # канала всё равно действуют. Это спасает узкие темы от пустых выпусков.
    trusted_sources = {
        source.id
        for source in channel.sources
        if source.enabled and bool(source.options.get("trust"))
    }
    strict_topics = bool(getattr(channel, "strict_topics", False))
    seen_urls: set = set()
    seen_titles: List[str] = []
    result: List[Article] = []
    for article in articles:
        if not article.title or not article.url:
            continue
        published = article.published_at
        if published is not None:
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published > now + timedelta(hours=2):
                continue
            if published < now - lookback:
                continue
        url_key = url_hash(article.url)
        if url_key in seen_urls:
            continue
        relevance, matched = score_article(article, channel)
        title_and_body = ((article.title or "") + " " + (article.content_for_analysis or "")).lower()
        excluded = any(bad and bad in title_and_body for bad in channel.exclude_keywords)
        if article.source_id in trusted_sources and not excluded:
            if not strict_topics:
                relevance = max(relevance, 0.5)
                matched = matched or ["тематический источник"]
        if relevance < min_relevance:
            continue
        if is_duplicate_title(article.title, seen_titles, threshold=0.72):
            continue
        seen_urls.add(url_key)
        seen_titles.append(article.title)
        article.meta["relevance"] = round(relevance, 4)
        article.meta["matched_topics"] = matched
        article.meta.setdefault("url_hash", url_key)
        result.append(article)
    def _sort_key(article: Article) -> Tuple[float, datetime]:
        published = article.published_at or now
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return (float(article.meta.get("relevance", 0.0)), published)

    result.sort(key=_sort_key, reverse=True)
    limit = int(settings.pipeline.get("max_articles_per_channel", 150))
    return result[:limit]


def collect_channel_articles(
    channel: ChannelConfig,
    settings: Settings,
    storage: Storage,
    now: Optional[datetime] = None,
) -> Tuple[List[Article], List[str]]:
    """Скачивает источники канала и возвращает только новые релевантные статьи."""
    errors: List[str] = []
    collected: List[Article] = []
    for source in channel.sources:
        if not source.enabled:
            continue
        try:
            adapter = get_adapter(source.type)
            items = adapter.fetch(source, settings) or []
            collected.extend(items)
            log.info(
                "Источник %s (%s): %d статей", source.name, source.type, len(items)
            )
        except Exception as exc:  # источники не должны ронять канал
            message = f"{source.id} ({source.url}): {exc}"
            errors.append(message)
            log.warning("Ошибка источника %s", message)
    filtered = filter_articles(channel, collected, settings, now=now)
    new_articles = storage.filter_new_articles(channel.id, filtered)
    storage.save_articles(channel.id, new_articles)
    return new_articles, errors


# ---------------------------------------------------------------------------
# Кластеризация и оценка сюжетов
# ---------------------------------------------------------------------------


def build_clusters(
    channel: ChannelConfig,
    articles: Sequence[Article],
    settings: Settings,
    now: Optional[datetime] = None,
) -> List[StoryCluster]:
    """Склеивает статьи об одном событии и ранжирует сюжеты для публикации."""
    now = now or utcnow()
    threshold = float(settings.pipeline.get("cluster_similarity", 0.34))
    min_sources = int(settings.pipeline.get("min_cluster_sources", 1))
    clusters = cluster_articles(list(articles), threshold=threshold, min_sources=min_sources)
    for cluster in clusters:
        cluster.channel_id = channel.id
        relevance = max(float(a.meta.get("relevance", 0.0)) for a in cluster.articles)
        cluster.relevance = relevance
        # Свежесть: 1.0 для только что вышедших, 0.0 к концу окна.
        # Источники иногда отдают naive datetime — приводим к UTC.
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        last = cluster.last_published or now
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now - last).total_seconds() / 3600.0)
        freshness = max(0.0, 1.0 - age_hours / max(6.0, float(settings.pipeline.get("lookback_hours", 30))))
        coverage = 0.3 if cluster.coverage <= 1 else min(1.0, 0.5 + 0.25 * (cluster.coverage - 2))
        cluster.score = round(0.55 * relevance + 0.25 * coverage + 0.20 * freshness, 4)
    clusters.sort(key=lambda c: c.score, reverse=True)
    return clusters


# ---------------------------------------------------------------------------
# Проверка качества поста
# ---------------------------------------------------------------------------


def quality_issues(post: GeneratedPost, channel: ChannelConfig, settings: Settings) -> List[str]:
    """Проверки перед публикацией. Непустой список = пост не публикуем."""
    issues: List[str] = []
    plain = post.plain_text
    min_chars = int(settings.pipeline.get("min_post_chars", 300))
    # Сводка за период может состоять из 1–2 новостей: заголовок + строка +
    # ссылка. Для неё минимальная длина ниже, иначе слот будет теряться.
    if str(post.format or "").lower() == "digest" and str(
        settings.pipeline.get("post_mode") or ""
    ).lower() == "digest":
        min_chars = min(min_chars, 140)
    if len(plain) < min_chars:
        issues.append(f"слишком короткий текст ({len(plain)} < {min_chars} символов)")
    if len(post.text) > channel.max_post_chars * 1.35:
        issues.append("текст значительно длиннее лимита канала")
    lowered = plain.lower()
    for bad in settings.pipeline.get("banned_words") or []:
        if bad and str(bad).lower() in lowered:
            issues.append(f"стоп-слово: {bad}")
    if not post_language_ok(post.text, channel.language):
        issues.append(f"язык поста не совпадает с языком канала ({channel.language})")
    if not post.sources:
        issues.append("нет ссылок на источники")
    if "http" in lowered and "<a href" not in post.text:
        issues.append("ссылки в тексте не оформлены как HTML-ссылки")
    return issues


# ---------------------------------------------------------------------------
# Публикация
# ---------------------------------------------------------------------------


def _publisher_ready(publisher: Publisher, channel: ChannelConfig):
    """(ok, причина) для опциональных публикаторов: check(channel) или check()."""
    try:
        return publisher.check(channel)  # type: ignore[call-arg]
    except TypeError:
        return publisher.check()


def publish_post(
    post: GeneratedPost,
    channel: ChannelConfig,
    settings: Settings,
    storage: Storage,
    effective_dry_run: bool,
) -> List[PublishResult]:
    """Публикует пост во все соцсети канала; ошибки фиксируются в результате."""
    # Живая строка рынка для крипто-каналов: BTC/ETH + опционально Kalshi.
    try:
        market_line_config = getattr(channel, "market_line", None)
        if isinstance(market_line_config, dict) and market_line_config.get("enabled"):
            from .integrations.marketline import build_market_line, insert_before_hashtags

            line = build_market_line(market_line_config)
            if line:
                post.text = insert_before_hashtags(post.text, line)
                post.meta["market_line"] = line
    except Exception:  # noqa: BLE001 - market line не должна мешать публикации
        log.debug("Не удалось добавить строку рынка для %s", channel.id, exc_info=True)
    # Реферальная строка (например, BingX): 1 раз в N постов, с маркировкой.
    try:
        affiliate_config = getattr(channel, "affiliate", None)
        if isinstance(affiliate_config, dict) and affiliate_config.get("enabled"):
            from .integrations.affiliate import (
                build_affiliate_line,
                insert_line as insert_affiliate_line,
                should_show,
            )

            every_n = int(affiliate_config.get("every_n_posts") or 3)
            index = max(0, _today_posts(storage, channel.id) - 1)
            if should_show(index, every_n):
                line = build_affiliate_line(
                    affiliate_config, language=channel.language, channel_id=channel.id
                )
                if line:
                    post.text = insert_affiliate_line(post.text, line)
                    post.meta["affiliate"] = line
    except Exception:  # noqa: BLE001 - рефералка не должна мешать публикации
        log.debug("Не удалось добавить реферальную строку для %s", channel.id, exc_info=True)
    names = ["dryrun"] if effective_dry_run else list(channel.publisher_ids)
    results: List[PublishResult] = []
    for name in names:
        try:
            publisher = get_publisher(name, settings)
            # Опциональные соцсети (Tumblr и будущие) без кредов — просто пропуск.
            if not effective_dry_run and getattr(publisher, "optional", False):
                ready, reason = _publisher_ready(publisher, channel)
                if not ready:
                    log.info("Публикатор %s для «%s» не настроен — пропуск (%s)", name, channel.id, reason)
                    continue
            result = publisher.publish(post, channel, settings)
        except Exception as exc:  # публикатор не должен ронять конвейер
            result = PublishResult(
                channel_id=channel.id,
                post_id=post.id,
                publisher=name,
                ok=False,
                error=str(exc),
                dry_run=effective_dry_run,
            )
        if result.ok and not result.dry_run:
            storage.mark_post_status(post.id, "published", result.url)
        storage.save_publish(result)
        results.append(result)
        if result.ok:
            log.info(
                "Пост %s опубликован (%s%s)",
                post.id,
                name,
                ", dry-run" if result.dry_run else "",
            )
        else:
            log.error("Не удалось опубликовать %s через %s: %s", post.id, name, result.error)
    return results


# ---------------------------------------------------------------------------
# Генерация постов
# ---------------------------------------------------------------------------


def _today_posts(storage: Storage, channel_id: str) -> int:
    try:
        return len(storage.get_posts(channel_id, days=1, limit=200))
    except Exception:
        return 0


def _attach_image(post: GeneratedPost, cluster: StoryCluster) -> None:
    """Подставляет картинку статьи в пост (для sendPhoto в Telegram).

    Берём первое валидное http(s)-изображение из meta статей кластера
    (World News API присылает ``meta["image"]``). Уже выставленную картинку
    (например, из Dify-приложения) не перезаписываем.
    """
    if post is None or cluster is None:
        return
    meta = post.meta if isinstance(post.meta, dict) else {}
    if str(meta.get("image_url") or "").strip():
        return
    for article in getattr(cluster, "articles", []) or []:
        article_meta = getattr(article, "meta", None) or {}
        image = str(article_meta.get("image") or article_meta.get("image_url") or "").strip()
        if image.startswith(("http://", "https://")):
            meta["image_url"] = image
            post.meta = meta
            return


def _attach_card(
    post: GeneratedPost,
    channel: ChannelConfig,
    settings: Settings,
    cluster: Optional[StoryCluster] = None,
) -> None:
    """Рисует фирменную фото-карточку поста (Playfair Display + Inter).

    Карточка сохраняется в ``data/outbox/cards/<post>.png``, путь кладётся в
    ``post.meta["card_path"]``; Telegram-публикатор отправит её через sendPhoto.
    Любая ошибка рендера не должна ломать публикацию — только логируется.
    """
    try:
        config = settings.publishers.get("telegram", {})
        card_config = config.get("photo_card", {}) if isinstance(config, dict) else {}
        if isinstance(card_config, dict) and not card_config.get("enabled", True):
            return
        from .cards import render_post_card

        headline = str(getattr(cluster, "title", "") or "").strip() if cluster is not None else None
        path = render_post_card(
            post,
            channel,
            settings,
            headline=headline or None,
            width=int((card_config or {}).get("width", 1080)),
            height=int((card_config or {}).get("height", 1350)),
            body_chars=int((card_config or {}).get("body_chars", 640)),
        )
        if path and isinstance(post.meta, dict):
            post.meta["card_path"] = str(path)
    except Exception:  # noqa: BLE001 - карточка не должна ломать публикацию
        log.debug("Не удалось нарисовать карточку для %s", channel.id, exc_info=True)


# ---------------------------------------------------------------------------
# Пиковое время: ночной/дневной режим, микс форматов, тренды
# ---------------------------------------------------------------------------
def _parse_hhmm(value: str) -> Optional[Tuple[int, int]]:
    try:
        hour, minute = str(value).strip().split(":")
        hour, minute = int(hour), int(minute)
    except (TypeError, ValueError):
        return None
    if 0 <= hour < 24 and 0 <= minute < 60:
        return hour, minute
    return None


def slot_is_night(channel: ChannelConfig, slot: str) -> bool:
    """Ночной ли слот по локальному времени канала (окно night_window)."""
    parsed = _parse_hhmm(slot)
    if parsed is None:
        return False
    window = str(getattr(channel, "night_window", "23:00-07:00") or "23:00-07:00")
    if "-" not in window:
        return False
    start_s, end_s = window.split("-", 1)
    start, end = _parse_hhmm(start_s), _parse_hhmm(end_s)
    if start is None or end is None:
        return False
    current = parsed[0] * 60 + parsed[1]
    start_min = start[0] * 60 + start[1]
    end_min = end[0] * 60 + end[1]
    if start_min == end_min:
        return False
    if start_min < end_min:
        return start_min <= current < end_min
    return current >= start_min or current < end_min


def _window_contains(window: str, slot: str) -> bool:
    if "-" not in str(window):
        return False
    parsed = _parse_hhmm(slot)
    start_text, end_text = str(window).split("-", 1)
    start, end = _parse_hhmm(start_text), _parse_hhmm(end_text)
    if parsed is None or start is None or end is None:
        return False
    current = parsed[0] * 60 + parsed[1]
    start_min = start[0] * 60 + start[1]
    end_min = end[0] * 60 + end[1]
    if start_min == end_min:
        return False
    if start_min < end_min:
        return start_min <= current < end_min
    return current >= start_min or current < end_min


def slot_phase(channel: ChannelConfig, slot: str) -> str:
    """Фаза слота: night / peak / day (по статистике активности Telegram)."""
    if slot_is_night(channel, slot):
        return "night"
    for window in getattr(channel, "peak_windows", None) or []:
        if _window_contains(window, slot):
            return "peak"
    return "day"


def day_formats(channel: ChannelConfig, phase: str = "day") -> List[str]:
    """Взвешенный микс форматов: в пик — больше analysis/interactive."""
    mix = (
        getattr(channel, "content_mix_peak", None)
        if phase == "peak"
        else getattr(channel, "content_mix", None)
    ) or {}
    order = ("story", "analysis", "interactive")
    weights = {name: max(0, int(mix.get(name, 0) or 0)) for name in order}
    formats: List[str] = []
    if any(weights.values()):
        # чередуем форматы, сохраняя пропорции 30/40/30
        for index in range(max(weights.values())):
            for name in order:
                if index < weights[name]:
                    formats.append(name)
    if not formats:
        formats = [
            str(item).lower()
            for item in (getattr(channel, "formats", None) or [])
            if str(item).lower() != "digest"
        ] or ["story"]
    return formats


def _detect_trends(articles: Sequence[Any], channel: ChannelConfig, limit: int = 3) -> List[str]:
    """Простые тренды: частые слова/фразы в заголовках свежих статей канала."""
    counts: Dict[str, int] = {}
    for article in articles or []:
        title = str(getattr(article, "title", "") or "")
        if not title:
            continue
        for token in tokenize(title.lower(), language=str(getattr(channel, "language", "ru"))):
            token = str(token).strip()
            if len(token) < 4 or token.isdigit():
                continue
            counts[token] = counts.get(token, 0) + 1
    if not counts:
        return []
    trending = [term for term, count in sorted(counts.items(), key=lambda item: -item[1]) if count >= 2]
    if not trending:
        return []
    # только термины, связанные с тематикой канала (или самые частые)
    lowered_topics = [str(topic).lower() for topic in (channel.topics or [])]
    related = [term for term in trending if any(term in topic or topic in term for topic in lowered_topics)]
    return (related or trending)[:limit]


def _tag_slot_meta(post: GeneratedPost, slot: str, night: bool, max_chars: int, phase: str = "day") -> None:
    if not isinstance(post.meta, dict):
        post.meta = {}
    post.meta["slot_local"] = slot
    post.meta["slot_mode"] = "night" if night else ("peak" if phase == "peak" else "day")
    post.meta["max_chars_target"] = int(max_chars)
    post.meta.setdefault("content_type", str(post.format or "story"))


def digest_window_clusters(
    clusters: Sequence[StoryCluster],
    last_post: Optional[datetime],
    overlap_minutes: float = 15.0,
) -> List[StoryCluster]:
    """Сюжеты, появившиеся после последнего поста канала (для сводки за период).

    ``last_post=None`` — первый запуск: берём все сюжеты (их ограничит лимит).
    Перекрытие компенсирует расхождение часов источника и времени публикации.
    """
    if last_post is None:
        return list(clusters)
    cutoff = last_post - timedelta(minutes=max(0.0, overlap_minutes))
    result: List[StoryCluster] = []
    for cluster in clusters:
        last_published = getattr(cluster, "last_published", None)
        if last_published is None:
            dates = [a.published_at for a in cluster.articles if a.published_at is not None]
            last_published = max(dates) if dates else None
        if last_published is None:
            continue
        if last_published.tzinfo is None:
            last_published = last_published.replace(tzinfo=timezone.utc)
        if last_published >= cutoff:
            result.append(cluster)
    return result


def order_digest_clusters(
    clusters: Sequence[StoryCluster], trend_terms: Sequence[str]
) -> List[StoryCluster]:
    """Сортировка сводки: сначала трендовые новости, затем свежие.

    Трендовая = в заголовке/тексте есть термин из блока трендов канала
    (Google Trends / CoinGecko / GitHub / HN и т.п. — см. content_factory.trends).
    Внутри каждой группы — от новых к старым.
    """
    terms = [str(term).strip().lower() for term in (trend_terms or []) if str(term).strip()]

    def sort_key(cluster: StoryCluster) -> Tuple[int, float]:
        haystack = (
            str(getattr(cluster, "title", "") or "") + " " + str(cluster.combined_text or "")
        )[:2000].lower()
        trending = 0 if terms and any(term in haystack for term in terms) else 1
        published = getattr(cluster, "last_published", None)
        if published is None:
            published = utcnow()
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return (trending, -published.timestamp())

    return sorted(clusters, key=sort_key)


def _build_window_digest(
    channel: ChannelConfig,
    clusters: Sequence[StoryCluster],
    settings: Settings,
    storage: Storage,
    llm: Any,
    slot: str,
    max_chars: int,
) -> Tuple[Optional[GeneratedPost], List[str]]:
    """Один пост = сводка новостей за период с предыдущего поста канала."""
    errors: List[str] = []
    if not clusters:
        return None, errors
    overlap = float(settings.pipeline.get("digest_window_overlap_minutes", 15) or 15)
    last_post = None
    try:
        last_post = storage.last_post_time(channel.id)
    except Exception:  # noqa: BLE001 - не роняем канал из-за истории
        log.debug("Не удалось получить время последнего поста %s", channel.id, exc_info=True)
    window = digest_window_clusters(list(clusters), last_post, overlap)
    if not window:
        errors.append("дайджест: нет новых сюжетов с прошлого поста")
        return None, errors

    duplicate_window = float(settings.pipeline.get("post_duplicate_window_hours", 72))
    try:
        recent = [strip_html(text) for text in storage.recent_post_titles(channel.id, hours=duplicate_window)]
    except Exception:  # noqa: BLE001
        recent = []
    published_hashes = _published_url_hashes(storage, channel, duplicate_window)
    # Сюжеты, чьи источники уже были в постах, повторно не публикуем.
    window = [cluster for cluster in window if not _cluster_published(cluster, published_hashes)]
    fresh = [cluster for cluster in window if not is_duplicate_title(cluster.title, recent, threshold=0.55)]
    if not fresh:
        errors.append("дайджест: все сюжеты уже публиковались")
        return None, errors
    window = fresh

    min_chars = int(
        getattr(channel, "min_cluster_chars", 0)
        or settings.pipeline.get("min_cluster_chars", 200)
    )
    long_enough = [
        cluster for cluster in window
        if len((cluster.combined_text or "").strip()) >= min_chars
    ]
    window = long_enough or window
    # Сначала трендовые новости (совпадение с блоком трендов канала), потом свежие.
    trend_terms = collect_trends(channel, settings, window)
    window = order_digest_clusters(window, trend_terms)

    cap = int(settings.pipeline.get("digest_max_items", 10) or 10)
    if max_chars:
        cap = min(cap, max(2, int(max_chars) // 220))
    window = window[: max(1, cap)]
    llm_items = int(settings.pipeline.get("digest_llm_items", 3) or 0)

    items: List[Tuple[StoryCluster, Any]] = []
    for index, cluster in enumerate(window):
        try:
            analysis = analyze_cluster(
                cluster, settings, llm if index < llm_items else None, language=channel.language
            )
            items.append((cluster, analysis))
        except Exception as exc:  # noqa: BLE001 - один сюжет не должен ронять сводку
            errors.append(f"сводка, сюжет «{cluster.title[:60]}»: {exc}")
            log.exception("Ошибка анализа сюжета для сводки: %s", cluster.title)
    if not items:
        return None, errors

    try:
        digest = generate_digest(
            items, channel, settings, llm=llm,
            max_chars=max_chars or None, trends=trend_terms,
        )
        _attach_image(digest, items[0][0])
        issues = quality_issues(digest, channel, settings)
        if issues:
            errors.append(f"сводка отклонена: {'; '.join(issues)}")
            return None, errors
        _attach_card(digest, channel, settings, None)
        night = slot_phase(channel, slot) == "night"
        _tag_slot_meta(digest, slot, night, max_chars, slot_phase(channel, slot))
        digest.meta["digest_window"] = {
            "since": last_post.isoformat() if last_post else None,
            "items": len(items),
        }
        return digest, errors
    except Exception as exc:  # noqa: BLE001
        errors.append(f"сводка: {exc}")
        log.exception("Не удалось собрать сводку за период для %s", channel.id)
        return None, errors


def generate_posts(
    channel: ChannelConfig,
    clusters: Sequence[StoryCluster],
    settings: Settings,
    storage: Storage,
    llm: Any,
    max_posts: int,
    slot: str = "",
    recap: bool = False,
    analysis_llm: Any = None,
) -> Tuple[List[GeneratedPost], List[str]]:
    """Генерирует посты по лучшим сюжетам с ротацией форматов.

    Ночью — только короткий дайджест (night_max_chars), днём — взвешенный
    микс форматов (story/analysis/interactive). В пиковые часы в начало поста
    ставится блок трендов, а сюжеты с трендами идут первыми.

    ``llm`` — клиент для генерации, ``analysis_llm`` — для анализа (этап
    ``analysis``); если не задан, используется тот же клиент.
    """
    errors: List[str] = []
    posts: List[GeneratedPost] = []
    if not clusters:
        return posts, errors
    analysis_llm = analysis_llm if analysis_llm is not None else llm
    # Готовые посты из Dify workflow-приложения (research + SEO внутри).
    dify_generator = build_post_generator(settings)

    phase = slot_phase(channel, slot)
    night_mode = phase == "night"
    fallback_min = int(settings.pipeline.get("fallback_min_cluster_chars", 80))
    max_chars = int(getattr(channel, "night_max_chars", 900) or 900) if night_mode else int(channel.max_post_chars)
    if night_mode or recap:
        formats = ["digest"]
    else:
        formats = day_formats(channel, phase)
    rotation = _today_posts(storage, channel.id) % len(formats)
    fmt = formats[rotation]
    min_chars = int(
        getattr(channel, "min_cluster_chars", 0)
        or settings.pipeline.get("min_cluster_chars", 200)
    )
    if recap:
        min_chars = min(min_chars, fallback_min)
    trends = [] if night_mode else collect_trends(channel, settings, clusters)

    # Режим «сводка за период»: один пост = все новости с прошлого поста канала.
    post_mode = str(settings.pipeline.get("post_mode") or "").strip().lower()
    if post_mode == "digest" and not recap:
        digest, digest_errors = _build_window_digest(
            channel, clusters, settings, storage, llm, slot, max_chars
        )
        errors.extend(digest_errors)
        if digest is not None:
            posts.append(digest)
            return posts, errors

    duplicate_window = float(settings.pipeline.get("post_duplicate_window_hours", 72))
    try:
        recent_plain = [
            strip_html(text)
            for text in storage.recent_post_titles(channel.id, hours=duplicate_window)
        ]
    except Exception:  # noqa: BLE001
        recent_plain = []
    published_hashes = _published_url_hashes(storage, channel, duplicate_window)

    # Дайджест — один пост сразу по нескольким сюжетам.
    digest_clusters = [
        cluster for cluster in clusters
        if len((cluster.combined_text or "").strip()) >= min_chars
        and not _cluster_published(cluster, published_hashes)
        and not is_duplicate_title(cluster.title, recent_plain, threshold=0.55)
    ]
    if dify_generator is None and fmt == "digest" and (len(digest_clusters) >= 2 or (recap and digest_clusters)):
        try:
            digest_items = [
                (cluster, analyze_cluster(cluster, settings, analysis_llm, language=channel.language))
                for cluster in digest_clusters[: min(5, len(digest_clusters))]
            ]
            digest = generate_digest(
                digest_items, channel, settings, llm=llm, max_chars=max_chars, trends=trends
            )
            if digest_items:
                _attach_image(digest, digest_items[0][0])
                # у дайджеста заголовок — его собственная шапка, а не 1-й сюжет
                _attach_card(digest, channel, settings, None)
            _tag_slot_meta(digest, slot, night_mode, max_chars, phase)
            if not post_language_ok(digest.text, channel.language):
                errors.append(f"дайджест отклонён: язык не {channel.language}")
            else:
                posts.append(digest)
                return posts, errors
        except Exception as exc:
            errors.append(f"дайджест: {exc}")
            log.exception("Не удалось собрать дайджест для %s", channel.id)

    if trends:
        trend_terms = [term.lower() for term in trends]

        def _trend_rank(cluster: StoryCluster) -> int:
            haystack = (str(cluster.title or "") + " " + str(cluster.combined_text or ""))[:1500].lower()
            return 0 if any(term in haystack for term in trend_terms) else 1

        clusters = sorted(list(clusters), key=_trend_rank)

    target_posts = max(1, max_posts)
    attempted = 0
    # Идём по всем сюжетам, пока не наберём нужное число постов: первый сюжет
    # может быть слишком коротким/дублем — при автопостинге нельзя терять слот.
    for cluster in clusters:
        if len(posts) >= target_posts:
            break
        if len((cluster.combined_text or "").strip()) < min_chars:
            log.info("Пропуск сюжета без достаточного текста: %s", cluster.title)
            continue
        current_fmt = formats[(rotation + attempted) % len(formats)]
        attempted += 1
        if current_fmt == "digest":
            current_fmt = "story"  # одиночный сюжет дайджестом не публикуем
        try:
            if _cluster_published(cluster, published_hashes):
                log.info("Пропуск уже опубликованного сюжета: %s", cluster.title)
                continue
            if not recap and is_duplicate_title(cluster.title, recent_plain, threshold=0.55):
                log.info("Пропуск повтора сюжета: %s", cluster.title)
                continue
            if dify_generator is not None:
                dify_post = dify_generator.generate(channel, cluster)
                if dify_post is not None and not post_language_ok(dify_post.text, channel.language):
                    errors.append(f"пост Dify отклонён: язык не {channel.language}")
                    continue
                if dify_post is not None:
                    _attach_image(dify_post, cluster)
                    _attach_card(dify_post, channel, settings, cluster)
                    posts.append(dify_post)
                    continue
            analysis = analyze_cluster(
                cluster, settings, analysis_llm, language=channel.language
            )
            post = generate_post(
                cluster, analysis, channel, settings, fmt=current_fmt, llm=llm,
                max_chars=max_chars, trends=trends,
            )
            _attach_image(post, cluster)
            issues = quality_issues(post, channel, settings)
            if issues:
                post.meta["quality_issues"] = issues
                errors.append(
                    f"пост по «{cluster.title[:60]}» отклонён: {'; '.join(issues)}"
                )
                log.warning("Пост отклонён проверками: %s", issues)
                continue
            _attach_card(post, channel, settings, cluster)
            _tag_slot_meta(post, slot, night_mode, max_chars, phase)
            posts.append(post)
        except Exception as exc:
            errors.append(f"сюжет «{cluster.title[:60]}»: {exc}")
            log.exception("Ошибка генерации поста по сюжету %s", cluster.title)
    return posts, errors


# ---------------------------------------------------------------------------
# Запуск канала
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fallback: публиковать каждый слот, даже если свежих статей нет
# ---------------------------------------------------------------------------
def _recent_articles(storage: Storage, channel: ChannelConfig, hours: float) -> List[Article]:
    try:
        return storage.recent_articles(channel.id, hours=hours)
    except Exception:  # noqa: BLE001
        log.debug("Не удалось взять статьи из истории для %s", channel.id, exc_info=True)
        return []


def _recap_emoji(channel: ChannelConfig) -> str:
    haystack = f"{channel.id} {channel.title} {' '.join(channel.topics)}".lower()
    if any(word in haystack for word in ("crypto", "cripto", "blockchain", "bitcoin", "ethereum")):
        return "🪙"
    if any(word in haystack for word in ("futbol", "fútbol", "soccer", "la liga", "liga mx", "deporte")):
        return "⚽"
    if any(word in haystack for word in ("sport", "nfl", "nba", "mlb", "nhl")):
        return "🏆"
    if any(word in haystack for word in (" ai", " ai ", "ia ", "tech", "tecnolog", "inteligencia artificial")):
        return "🤖"
    return "📰"


def _recap_from_posts(
    channel: ChannelConfig,
    storage: Storage,
    settings: Settings,
    slot: str = "",
) -> Optional[GeneratedPost]:
    """Дайджест из последних постов канала — гарантирует пост в каждом слоте."""
    try:
        cooldown = float(settings.pipeline.get("fallback_recap_cooldown_hours", 10) or 10)
        last_recap = storage.last_fallback_post_time(channel.id)
        if last_recap is not None:
            age_hours = (utcnow() - last_recap).total_seconds() / 3600.0
            if age_hours < cooldown:
                log.info(
                    "Рекап пропущен: предыдущий рекап %.1f ч назад (кулдаун %.0f ч)",
                    age_hours,
                    cooldown,
                )
                return None
        hours = float(settings.pipeline.get("fallback_from_posts_hours", 72))
        rows = storage.get_posts(channel.id, days=hours / 24, limit=40)
        if not rows:
            return None
        rotation = _today_posts(storage, channel.id) % len(rows)
        rows = rows[rotation:] + rows[:rotation]
        sentences: List[str] = []
        seen_prefixes = set()
        for row in rows:
            plain = strip_html(row.get("text") or "")
            for candidate in re.split(r"(?<=[.!?])\s+", plain):
                candidate = normalize_space(candidate)
                if not (40 <= len(candidate) <= 300):
                    continue
                lowered = candidate.lower()
                # Рекап не должен повторять офтоп: только тематические фразы.
                if any(bad and bad in lowered for bad in channel.exclude_keywords):
                    continue
                if channel.topics and not any(
                    match_keyword(str(topic), lowered) for topic in channel.topics
                ):
                    continue
                key = lowered[:60]
                if key in seen_prefixes:
                    continue
                seen_prefixes.add(key)
                sentences.append(candidate)
                break
            if len(sentences) >= 3:
                break
        if not sentences:
            return None
        lang = str(channel.language or "en")
        if lang == "en":
            headline = f"What's moving in {channel.title} right now"
        elif lang == "es":
            headline = f"Lo que se mueve ahora en {channel.title}"
        else:
            headline = f"Главное в «{channel.title}» сейчас"
        from html import escape as html_escape
        paragraphs = "\n\n".join(html_escape(sentence) for sentence in sentences)
        text = f"{_recap_emoji(channel)} <b>{html_escape(headline)}</b>\n\n{paragraphs}"
        if channel.hashtags:
            text += "\n\n" + " ".join(channel.hashtags)
        if not post_language_ok(text, channel.language):
            log.info("Рекап пропущен: язык не %s", channel.language)
            return None
        post = GeneratedPost(
            id=stable_id(channel.id, "recap", slot or utcnow().isoformat(), str(rotation)),
            channel_id=channel.id,
            cluster_id="recap",
            format="digest",
            text=text,
            hashtags=list(channel.hashtags),
            sources=[],
            score=0.0,
            meta={
                "format": "digest",
                "fallback": True,
                "generator": "recap",
                "slot_local": slot,
                "seo_keywords": [str(tag).lstrip("#") for tag in channel.hashtags][:5],
            },
        )
        _attach_card(post, channel, settings, None)
        return post
    except Exception:  # noqa: BLE001 - fallback не должен ронять канал
        log.exception("Не удалось собрать рекап для %s", channel.id)
        return None


def run_channel(
    channel: ChannelConfig,
    settings: Settings,
    storage: Storage,
    dry_run: Optional[bool] = None,
    now: Optional[datetime] = None,
    max_posts: Optional[int] = None,
    slot: str = "",
) -> RunResult:
    """Полный цикл одного канала. Никогда не бросает исключения наружу."""
    effective_dry_run = settings.dry_run if dry_run is None else bool(dry_run)
    result = RunResult(channel_id=channel.id, dry_run=effective_dry_run)
    logger = logging.getLogger(f"content_factory.pipeline.{channel.id}")
    logger.info(
        "Старт канала «%s» (dry_run=%s%s)",
        channel.title,
        effective_dry_run,
        f", слот {slot}" if slot else "",
    )
    try:
        articles, fetch_errors = collect_channel_articles(channel, settings, storage, now=now)
        result.articles_fetched = len(articles)
        result.articles_new = len(articles)
        result.errors.extend(fetch_errors)

        recap_mode = False
        if not articles:
            fallback_hours = float(settings.pipeline.get("fallback_recap_hours", 48))
            recent = _recent_articles(storage, channel, fallback_hours)
            if recent:
                articles = recent
                recap_mode = True
                logger.info(
                    "Рекап: свежих статей нет — беру %d статей из истории (%.0f ч)",
                    len(recent),
                    fallback_hours,
                )

        clusters = build_clusters(channel, articles, settings, now=now) if articles else []
        result.clusters = len(clusters)
        analysis_llm = get_llm(settings, stage="analysis")
        generation_llm = get_llm(settings, stage="generation")
        logger.info(
            "Сюжетов: %d; LLM анализ: %s (%s), генерация: %s (%s)",
            len(clusters),
            analysis_llm.name,
            "доступна" if analysis_llm.available else "extractive",
            generation_llm.name,
            "доступна" if generation_llm.available else "extractive",
        )
        if clusters:
            # Не публикуем больше, чем канал планирует за день: при 3 слотах и
            # 3 постах/день на слот приходится ровно один пост (защита от спама,
            # особенно при catch-up первого запуска демона).
            per_run_cap = max(1, int(channel.posts_per_day) // max(1, len(channel.schedule)))
            configured = int(settings.pipeline.get("max_posts_per_run", 2))
            limit = int(max_posts or min(configured, per_run_cap))
            posts, generate_errors = generate_posts(
                channel,
                clusters,
                settings,
                storage,
                generation_llm,
                limit,
                slot=slot,
                recap=recap_mode,
                analysis_llm=analysis_llm,
            )
        else:
            posts, generate_errors = [], []
        if not posts:
            recap_post = _recap_from_posts(channel, storage, settings, slot=slot)
            if recap_post is not None:
                logger.info("Рекап: публикую дайджест из последних постов канала")
                posts = [recap_post]
        result.errors.extend(generate_errors)
        result.posts_generated = len(posts)

        for post in posts:
            if not storage.save_post(post, status="generated"):
                logger.info("Пост %s уже существует — пропуск", post.id)
                continue
            publish_results = publish_post(
                post, channel, settings, storage, effective_dry_run
            )
            result.results.extend(publish_results)
            if any(item.ok for item in publish_results):
                result.posts_published += 1
            for item in publish_results:
                if not item.ok and item.error:
                    result.errors.append(f"публикация {item.publisher}: {item.error}")
    except Exception as exc:  # защитная сетка: один канал не должен ронять демон
        logger.exception("Критическая ошибка канала %s", channel.id)
        result.errors.append(f"критическая ошибка: {exc}")
    finally:
        result.finish()
        try:
            storage.save_run(result)
        except Exception:
            logger.exception("Не удалось сохранить статистику запуска")
        logger.info(
            "Итог «%s»: статей %d, сюжетов %d, постов %d, опубликовано %d, ошибок %d (%.1f c)",
            channel.title,
            result.articles_new,
            result.clusters,
            result.posts_generated,
            result.posts_published,
            len(result.errors),
            result.duration_sec,
        )
    return result


def select_channels(
    settings: Settings, channel_ids: Optional[Iterable[str]] = None
) -> List[ChannelConfig]:
    channels = load_channels(settings)
    requested = {str(c).strip() for c in channel_ids} if channel_ids else set()
    if requested and "all" not in requested:
        unknown = requested - {c.id for c in channels}
        if unknown:
            raise ValueError(f"Неизвестные каналы: {', '.join(sorted(unknown))}")
        channels = [c for c in channels if c.id in requested]
    return [c for c in channels if c.enabled]


def run_channels(
    settings: Settings,
    channel_ids: Optional[Iterable[str]] = None,
    dry_run: Optional[bool] = None,
    now: Optional[datetime] = None,
    max_posts: Optional[int] = None,
    slot: str = "",
) -> List[RunResult]:
    """Запускает один или несколько каналов (одноразовый прогон)."""
    channels = select_channels(settings, channel_ids)
    if not channels:
        log.warning("Нет включённых каналов")
        return []
    results: List[RunResult] = []
    with Storage(settings.db_path) as storage:
        for channel in channels:
            results.append(
                run_channel(
                    channel,
                    settings,
                    storage,
                    dry_run=dry_run,
                    now=now,
                    max_posts=max_posts,
                    slot=slot,
                )
            )
    try:
        from .nlp.tokens import get_tracker

        tracker = get_tracker()
        if tracker is not None:
            log.info("Токены LLM за прогон: %s", tracker.describe())
    except Exception:  # pragma: no cover - статистика не должна ломать прогон
        pass
    return results


# ---------------------------------------------------------------------------
# Предпросмотр без сохранения постов
# ---------------------------------------------------------------------------


def preview_channel(
    channel: ChannelConfig,
    settings: Settings,
    storage: Storage,
    limit: int = 3,
    now: Optional[datetime] = None,
) -> Tuple[List[GeneratedPost], List[str]]:
    """Показывает, что было бы опубликовано, но не публикует и не сохраняет посты."""
    errors: List[str] = []
    articles, fetch_errors = collect_channel_articles(channel, settings, storage, now=now)
    errors.extend(fetch_errors)
    if not articles:
        return [], errors
    clusters = build_clusters(channel, articles, settings, now=now)
    analysis_llm = get_llm(settings, stage="analysis")
    generation_llm = get_llm(settings, stage="generation")
    posts: List[GeneratedPost] = []
    for cluster in clusters[: max(1, limit)]:
        try:
            analysis = analyze_cluster(
                cluster, settings, analysis_llm, language=channel.language
            )
            posts.append(generate_post(cluster, analysis, channel, settings, fmt="story", llm=generation_llm))
        except Exception as exc:
            errors.append(f"{cluster.title[:60]}: {exc}")
    return posts, errors


# ---------------------------------------------------------------------------
# Демо-режим: офлайн, без сети и токенов
# ---------------------------------------------------------------------------


def demo_settings(settings: Settings) -> Settings:
    """Отдельные каталоги демо-режима, чтобы не засорять рабочие данные.

    Демо обязано быть полностью офлайн: принудительно extractive и без
    stage_routes/provider_limits, чтобы не уйти в облачные модели.
    """
    raw = copy.deepcopy(settings.raw)
    raw.setdefault("app", {})
    raw["app"].update(
        {
            "data_dir": "data/demo",
            "db_path": "data/demo/demo.sqlite3",
            "outbox_dir": "samples/demo/outbox",
            "reports_dir": "samples/demo/reports",
            "logs_dir": "data/demo/logs",
            "dry_run": True,
        }
    )
    llm_section = raw.setdefault("llm", {})
    llm_section["provider"] = "extractive"
    llm_section["fallback"] = []
    llm_section["stage_routes"] = {}
    llm_section["provider_limits"] = {}
    llm_section["daily_request_limit"] = 0
    llm_section["daily_token_limit"] = 0
    return Settings(
        root=settings.root,
        raw=raw,
        settings_path=settings.settings_path,
        channels_path=settings.channels_path,
    )


def _demo_articles(settings: Settings) -> Dict[str, List[Article]]:
    path = settings.root / "samples" / "demo_articles.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Нет демо-данных: {path}. Запустите demo из корня проекта."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    now = utcnow()
    result: Dict[str, List[Article]] = {}
    for item in payload.get("articles", []):
        channel_id = str(item["channel_id"])
        published = now - timedelta(hours=float(item.get("hours_ago", 3)))
        url = str(item["url"])
        article = Article(
            id=stable_id(url, channel_id, item["title"]),
            title=str(item["title"]),
            url=url,
            source_id=str(item.get("source_id", "demo")),
            source_name=str(item.get("source_name", "Демо-источник")),
            published_at=published,
            text=str(item.get("text", "")),
            summary=str(item.get("summary", "")),
            fetched_at=now,
            weighted_source_score=float(item.get("weight", 1.0)),
            meta={"url_hash": url_hash(url), "relevance": 1.0, "demo": True},
        )
        result.setdefault(channel_id, []).append(article)
    return result


def run_demo(settings: Settings, reset: bool = True) -> Dict[str, Any]:
    """Полный офлайн-прогон на демо-данных: посты в samples/demo/outbox + отчёт."""
    demo = demo_settings(settings)
    demo.ensure_dirs()
    if reset:
        for directory in (demo.data_dir, demo.outbox_dir, demo.reports_dir):
            if directory.exists():
                shutil.rmtree(directory)
        demo.ensure_dirs()
    channels = [c for c in load_channels(demo) if c.enabled]
    articles_by_channel = _demo_articles(settings)
    llm = get_llm(demo)
    total_posts = 0
    total_published = 0
    with Storage(demo.db_path) as storage:
        for channel in channels:
            items = articles_by_channel.get(channel.id, [])
            if not items:
                continue
            storage.save_articles(channel.id, items)
            clusters = build_clusters(channel, items, demo, now=utcnow())
            if not clusters:
                continue
            digest_ok = False
            story_ok = False
            # 1) дайджест по двум лучшим сюжетам (демонстрация формата)
            try:
                digest_items = [
                    (
                        cluster,
                        analyze_cluster(cluster, demo, llm, language=channel.language),
                    )
                    for cluster in clusters[:2]
                ]
                digest = generate_digest(digest_items, channel, demo, llm=llm)
                if storage.save_post(digest, status="generated"):
                    results = publish_post(digest, channel, demo, storage, effective_dry_run=True)
                    digest_ok = any(r.ok for r in results)
                    total_posts += 1
                    total_published += 1 if digest_ok else 0
            except Exception as exc:
                log.warning("Демо: дайджест %s не собрался: %s", channel.id, exc)
            # 2) обычный пост по главному сюжету
            try:
                analysis = analyze_cluster(
                    clusters[0], demo, llm, language=channel.language
                )
                post = generate_post(clusters[0], analysis, channel, demo, fmt="story", llm=llm)
                if storage.save_post(post, status="generated"):
                    results = publish_post(post, channel, demo, storage, effective_dry_run=True)
                    story_ok = any(r.ok for r in results)
                    total_posts += 1
                    total_published += 1 if story_ok else 0
            except Exception as exc:
                log.warning("Демо: пост %s не собрался: %s", channel.id, exc)
            channel_posts = (1 if digest_ok else 0) + (1 if story_ok else 0)
            storage.save_run(
                RunResult(
                    channel_id=channel.id,
                    articles_fetched=len(items),
                    articles_new=len(items),
                    clusters=len(clusters),
                    posts_generated=channel_posts,
                    posts_published=channel_posts,
                    dry_run=True,
                ).finish()
            )
        # Метрики и отчёт
        try:
            from .analytics.collector import collect_all

            collect_all(channels, demo, storage)
        except Exception as exc:
            log.warning("Демо: метрики не собраны: %s", exc)
        try:
            from .nlp.tokens import get_tracker

            tracker = get_tracker()
            if tracker is not None:
                log.info("Демо: токены LLM — %s", tracker.describe())
        except Exception:  # pragma: no cover - статистика не должна ломать демо
            pass
        report_paths: Dict[str, str] = {}
        try:
            from .analytics.report import save_report

            report_paths = save_report(demo, storage, channels, days=30)
        except Exception as exc:
            log.exception("Демо: отчёт не собран: %s", exc)
    return {
        "channels": len(channels),
        "posts": total_posts,
        "published": total_published,
        "outbox": str(demo.outbox_dir),
        "reports": report_paths,
       
    }
