#!/usr/bin/env python3
"""Замер экономии токенов LLM: baseline vs optimized на демо-данных.

Скрипт прогоняет анализ сюжета и генерацию поста на локальной модели
(настройки из config/settings.yaml) в двух режимах:

* baseline  — прежние промпты: 2 запроса на анализ (резюме и тезисы отдельно)
              + заголовок по 4000 символов исходного текста;
* optimized — объединённый анализ (резюме+тезисы одним запросом) + заголовок
              по готовому резюме (флаги llm.optimize);
* cached    — optimized + кэш ответов: повторный прогон того же сюжета
              не тратит токены вовсе.

Токены берутся из реальных ответов провайдера (Ollama: prompt_eval_count и
eval_count). Печатается таблица «было/стало», экономия в процентах и проверка
качества: валидаторы поста/анализа и близость резюме baseline и optimized.

Запуск (нужна запущенная Ollama с моделью):
    ./.venv/bin/python scripts/token_economy_check.py
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_channels  # noqa: E402
from content_factory.nlp.analyzer import analyze_cluster  # noqa: E402
from content_factory.nlp.generator import generate_post  # noqa: E402
from content_factory.nlp.llm import get_llm  # noqa: E402
from content_factory.nlp.tokens import get_tracker  # noqa: E402
from content_factory.pipeline import (  # noqa: E402
    _demo_articles,
    build_clusters,
    collect_channel_articles,
    quality_issues,
)
from content_factory.storage import Storage  # noqa: E402
from content_factory.models import utcnow  # noqa: E402
from content_factory.utils import strip_html, token_set  # noqa: E402

CHANNEL_ID = "tech-ai"


def _settings(data_dir: Path, optimize: bool, cache: bool) -> Settings:
    base = Settings.load(load_env=False)
    raw = copy.deepcopy(base.raw)
    raw.setdefault("llm", {})
    raw["llm"]["optimize"] = {
        "combined_analysis": optimize,
        "compact_headline": optimize,
    }
    raw["llm"]["cache"] = cache
    raw["llm"]["daily_request_limit"] = 0
    raw["llm"]["daily_token_limit"] = 0
    raw.setdefault("app", {})["data_dir"] = str(data_dir)
    raw["app"]["db_path"] = str(data_dir / "factory.sqlite3")
    raw["app"]["outbox_dir"] = str(data_dir / "outbox")
    raw["app"]["reports_dir"] = str(data_dir / "reports")
    raw["app"]["logs_dir"] = str(data_dir / "logs")
    raw["app"]["channels_file"] = "config/channels.yaml"   # русские каналы из демо-данных
    settings = Settings(
        root=base.root,
        raw=raw,
        settings_path=base.settings_path,
        channels_path=base.root / "config" / "channels.yaml",
    )
    settings.ensure_dirs()
    return settings


def _cluster(settings: Settings):
    channels = load_channels(settings)
    channel = next((item for item in channels if item.id == CHANNEL_ID), channels[0])
    articles = []
    try:
        with Storage(settings.db_path) as storage:
            articles, _errors = collect_channel_articles(channel, settings, storage)
    except Exception as exc:  # нет сети/источники недоступны — работаем на демо-данных
        print(f"Не удалось собрать RSS ({exc}); беру демо-данные")
    if not articles:
        articles = _demo_articles(settings).get(channel.id, [])
    clusters = build_clusters(channel, articles, settings, now=utcnow())
    if not clusters:
        raise SystemExit(f"Не удалось собрать сюжеты для канала {channel.id}")
    # Для честного замера берём самый «длинный» реальный сюжет: экономия
    # промптов проявляется именно на статьях в тысячи символов.
    long_clusters = [c for c in clusters if len((c.combined_text or "").strip()) >= 2000]
    return channel, (max(long_clusters or clusters, key=lambda c: len(c.combined_text or "")))


def _enrich_cluster(cluster, settings: Settings):
    """Догружает полный текст статей (как production-источник с full_text).

    В RSS-лентах текст часто пустой/короткий, а экономия промптов проявляется
    именно на статьях в тысячи символов: анализ получает до 6000 символов.
    """
    try:
        from content_factory.sources.rss import RSSAdapter
    except Exception:
        return cluster
    adapter = RSSAdapter()
    for article in list(cluster.articles)[:3]:
        try:
            text = adapter._fetch_article_text(article.url, settings)  # noqa: SLF001
        except Exception:
            text = ""
        if text and len(text) > len(getattr(article, "text", "") or ""):
            article.text = text
    return cluster


def _run_once(settings: Settings, channel, cluster, times: int = 1) -> dict:
    llm = get_llm(settings)
    analysis = None
    post = None
    for _ in range(times):
        analysis = analyze_cluster(cluster, settings, llm=llm, language=channel.language)
        post = generate_post(cluster, analysis, channel, settings, fmt="story", llm=llm)
    tracker = get_tracker()
    today = tracker.today() if tracker is not None else {}
    issues = quality_issues(post, channel, settings)
    headline = ""
    if post is not None:
        first_line = strip_html(post.text).splitlines()[0] if post.text else ""
        headline = first_line.strip()
    return {
        "tokens": today,
        "report": tracker.describe() if tracker is not None else "",
        "analysis": analysis,
        "post": post,
        "issues": issues,
        "headline": headline,
    }


def _summary(run: dict) -> str:
    analysis = run.get("analysis")
    return getattr(analysis, "summary", "") if analysis is not None else ""


def _jaccard(left: str, right: str) -> float:
    a, b = token_set(left), token_set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="cf-token-economy-"))
    channel_base, cluster_base = _cluster(_settings(workdir / "probe", True, False))

    cluster_base = _enrich_cluster(cluster_base, _settings(workdir / "enrich", True, False))
    print(f"Текст сюжета для замера: {len(cluster_base.combined_text or '')} символов")
    baseline = _run_once(
        _settings(workdir / "baseline", optimize=False, cache=False),
        channel_base,
        cluster_base,
    )
    optimized = _run_once(
        _settings(workdir / "optimized", optimize=True, cache=False),
        channel_base,
        cluster_base,
    )
    # Кэш: первый прогон считает токены, второй — должен взять всё из кэша.
    cached = _run_once(
        _settings(workdir / "cached", optimize=True, cache=True),
        channel_base,
        cluster_base,
        times=2,
    )

    def totals(run: dict) -> tuple[int, int, int]:
        data = run.get("tokens") or {}
        return (
            int(data.get("calls") or 0),
            int(data.get("prompt_tokens") or 0),
            int(data.get("completion_tokens") or 0),
        )

    b_calls, b_prompt, b_completion = totals(baseline)
    o_calls, o_prompt, o_completion = totals(optimized)
    b_total = b_prompt + b_completion
    o_total = o_prompt + o_completion
    saved = 100.0 * (b_total - o_total) / b_total if b_total else 0.0

    print("=" * 74)
    print("Экономия токенов LLM: baseline vs optimized (реальные токены Ollama)")
    print("=" * 74)
    print(f"Сюжет: {cluster_base.title[:70]}")
    print()
    print(f"{'Режим':<12}{'запросов':>10}{'промпт':>10}{'ответ':>9}{'всего':>10}")
    print("-" * 52)
    print(f"{'baseline':<12}{b_calls:>10}{b_prompt:>10}{b_completion:>9}{b_total:>10}")
    print(f"{'optimized':<12}{o_calls:>10}{o_prompt:>10}{o_completion:>9}{o_total:>10}")
    print("-" * 52)
    print(f"Экономия: {saved:.0f}% токенов ({b_total} → {o_total}), запросов {b_calls} → {o_calls}")
    print()
    cache_tokens = cached.get("tokens") or {}
    print(
        "Кэш (два одинаковых прогона optimized): "
        f"запросов к модели {cache_tokens.get('calls', 0)}, "
        f"попаданий в кэш {cache_tokens.get('cache_hits', 0)}, "
        f"сэкономлено {cache_tokens.get('cache_saved_tokens', 0)} токенов"
    )
    print()
    print("Проверка качества:")
    for name, run in (("baseline", baseline), ("optimized", optimized)):
        analysis = run.get("analysis")
        issues = run.get("issues") or []
        print(
            f"  {name:<10} валидаторы: {'OK' if not issues else issues}; "
            f"резюме {len(_summary(run))} симв., тезисов {len(getattr(analysis, 'bullets', []))}; "
            f"пост {len(run.get('post').text or '') if run.get('post') else 0} симв."
        )
    print(f"  близость резюме baseline/optimized (Jaccard): {_jaccard(_summary(baseline), _summary(optimized)):.2f}")
    print()
    print("Резюме baseline: " + _summary(baseline)[:220])
    print("Резюме optimized: " + _summary(optimized)[:220])
    print("Заголовок baseline: " + str(baseline.get("headline"))[:160])
    print("Заголовок optimized: " + str(optimized.get("headline"))[:160])
    print()
    print("Рабочая папка замера:", workdir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
