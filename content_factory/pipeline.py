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
from .publishers import get_publisher
from .sources import get_adapter
from .storage import Storage
from .utils import (
    normalize_space,
    stable_id,
    strip_html,
    url_hash,
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
    result.sort(
        key=lambda a: (float(a.meta.get("relevance", 0.0)), a.published_at or now),
        reverse=True,
    )
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
        last = cluster.last_published or now
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
    if len(plain) < min_chars:
        issues.append(f"слишком короткий текст ({len(plain)} < {min_chars} символов)")
    if len(post.text) > channel.max_post_chars * 1.35:
        issues.append("текст значительно длиннее лимита канала")
    lowered = plain.lower()
    for bad in settings.pipeline.get("banned_words") or []:
        if bad and str(bad).lower() in lowered:
            issues.append(f"стоп-слово: {bad}")
    if not post.sources:
        issues.append("нет ссылок на источники")
    if "http" in lowered and "<a href" not in post.text:
        issues.append("ссылки в тексте не оформлены как HTML-ссылки")
    return issues


# ---------------------------------------------------------------------------
# Публикация
# ---------------------------------------------------------------------------


def publish_post(
    post: GeneratedPost,
    channel: ChannelConfig,
    settings: Settings,
    storage: Storage,
    effective_dry_run: bool,
) -> List[PublishResult]:
    """Публикует пост во все соцсети канала; ошибки фиксируются в результате."""
    names = ["dryrun"] if effective_dry_run else list(channel.publisher_ids)
    results: List[PublishResult] = []
    for name in names:
        try:
            publisher = get_publisher(name, settings)
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


def generate_posts(
    channel: ChannelConfig,
    clusters: Sequence[StoryCluster],
    settings: Settings,
    storage: Storage,
    llm: Any,
    max_posts: int,
) -> Tuple[List[GeneratedPost], List[str]]:
    """Генерирует посты по лучшим сюжетам с ротацией форматов."""
    errors: List[str] = []
    posts: List[GeneratedPost] = []
    if not clusters:
        return posts, errors
    # Готовые посты из Dify workflow-приложения (research + SEO внутри).
    dify_generator = build_post_generator(settings)

    formats = list(channel.formats) or ["story"]
    rotation = _today_posts(storage, channel.id) % len(formats)
    fmt = formats[rotation]
    min_chars = int(settings.pipeline.get("min_cluster_chars", 200))

    # Дайджест — один пост сразу по нескольким сюжетам.
    digest_clusters = [
        cluster for cluster in clusters
        if len((cluster.combined_text or "").strip()) >= min_chars
    ]
    if dify_generator is None and fmt == "digest" and len(digest_clusters) >= 2:
        try:
            digest_items = [
                (cluster, analyze_cluster(cluster, settings, llm, language=channel.language))
                for cluster in digest_clusters[: min(5, len(digest_clusters))]
            ]
            digest = generate_digest(digest_items, channel, settings, llm=llm)
            if digest_items:
                _attach_image(digest, digest_items[0][0])
            posts.append(digest)
            return posts, errors
        except Exception as exc:
            errors.append(f"дайджест: {exc}")
            log.exception("Не удалось собрать дайджест для %s", channel.id)

    duplicate_window = float(settings.pipeline.get("post_duplicate_window_hours", 72))
    recent_titles = storage.recent_post_titles(channel.id, hours=duplicate_window)
    recent_plain = [strip_html(text) for text in recent_titles]
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
            if is_duplicate_title(cluster.title, recent_plain, threshold=0.55):
                log.info("Пропуск повтора сюжета: %s", cluster.title)
                continue
            if dify_generator is not None:
                dify_post = dify_generator.generate(channel, cluster)
                if dify_post is not None:
                    _attach_image(dify_post, cluster)
                    posts.append(dify_post)
                    continue
            analysis = analyze_cluster(
                cluster, settings, llm, language=channel.language
            )
            post = generate_post(cluster, analysis, channel, settings, fmt=current_fmt, llm=llm)
            _attach_image(post, cluster)
            issues = quality_issues(post, channel, settings)
            if issues:
                post.meta["quality_issues"] = issues
                errors.append(
                    f"пост по «{cluster.title[:60]}» отклонён: {'; '.join(issues)}"
                )
                log.warning("Пост отклонён проверками: %s", issues)
                continue
            posts.append(post)
        except Exception as exc:
            errors.append(f"сюжет «{cluster.title[:60]}»: {exc}")
            log.exception("Ошибка генерации поста по сюжету %s", cluster.title)
    return posts, errors


# ---------------------------------------------------------------------------
# Запуск канала
# ---------------------------------------------------------------------------


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
        if not articles:
            logger.info("Нет новых релевантных статей — канал пропущен")
            result.finish()
            storage.save_run(result)
            return result

        clusters = build_clusters(channel, articles, settings, now=now)
        result.clusters = len(clusters)
        if not clusters:
            logger.info("Не удалось собрать сюжеты")
            result.finish()
            storage.save_run(result)
            return result

        llm = get_llm(settings)
        logger.info(
            "Сюжетов: %d; LLM: %s (%s)",
            len(clusters),
            llm.name,
            "доступна" if llm.available else "fallback на extractive",
        )
        # Не публикуем больше, чем канал планирует за день: при 3 слотах и
        # 3 постах/день на слот приходится ровно один пост (защита от спама,
        # особенно при catch-up первого запуска демона).
        per_run_cap = max(1, int(channel.posts_per_day) // max(1, len(channel.schedule)))
        configured = int(settings.pipeline.get("max_posts_per_run", 2))
        limit = int(max_posts or min(configured, per_run_cap))
        posts, generate_errors = generate_posts(
            channel, clusters, settings, storage, llm, limit
        )
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
    llm = get_llm(settings)
    posts: List[GeneratedPost] = []
    for cluster in clusters[: max(1, limit)]:
        try:
            analysis = analyze_cluster(
                cluster, settings, llm, language=channel.language
            )
            posts.append(generate_post(cluster, analysis, channel, settings, fmt="story", llm=llm))
        except Exception as exc:
            errors.append(f"{cluster.title[:60]}: {exc}")
    return posts, errors


# ---------------------------------------------------------------------------
# Демо-режим: офлайн, без сети и токенов
# ---------------------------------------------------------------------------


def demo_settings(settings: Settings) -> Settings:
    """Отдельные каталоги демо-режима, чтобы не засорять рабочие данные."""
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
