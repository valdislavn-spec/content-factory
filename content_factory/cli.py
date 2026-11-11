"""Командный интерфейс контент-завода.

Примеры:
    python -m content_factory demo
    python -m content_factory channels
    python -m content_factory sources check
    python -m content_factory run --channel all --dry-run
    python -m content_factory preview --channel tech-ai
    python -m content_factory daemon
    python -m content_factory ingest --dir data/inbox
    python -m content_factory report --days 7
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import Settings, load_channels, load_network_channels
from .logging_setup import setup_logging
from .models import GeneratedPost
from .pipeline import (
    preview_channel,
    run_channels,
    run_demo,
    select_channels,
)
from .storage import Storage
from .utils import ConfigError, ensure_dir

log = logging.getLogger("content_factory.cli")


# ---------------------------------------------------------------------------
# Вспомогательные функции вывода
# ---------------------------------------------------------------------------


def _print_channel_table(channels: list, settings: Settings) -> None:
    print(f"{'ID':<18} {'Тема':<26} {'Источники':>9} {'Расписание (МСК)':<24} Публикация")
    print("-" * 110)
    for channel in channels:
        enabled_sources = sum(1 for source in channel.sources if source.enabled)
        schedule = ", ".join(channel.schedule)
        if settings.dry_run:
            mode = "dry-run"
        elif channel.telegram_chat_id:
            mode = "Telegram"
        else:
            mode = "нет chat_id"
        print(
            f"{channel.id:<18} {channel.title[:24]:<26} {enabled_sources:>9} "
            f"{schedule:<24} {mode}"
        )
    print(f"\nВсего каналов: {len(channels)}. Публикация: {'DRY-RUN (безопасно)' if settings.dry_run else 'ВКЛЮЧЕНА'}")


def _print_post(post: GeneratedPost, index: int) -> None:
    print("=" * 78)
    print(f"ПОСТ #{index} | формат: {post.format} | канал: {post.channel_id} | {len(post.text)} символов")
    print("-" * 78)
    print(post.plain_text)
    print("-" * 78)
    if post.sources:
        print("Источники:")
        for source in post.sources:
            print(f"  • {source.get('source', '')}: {source.get('title', '')[:80]} — {source.get('url', '')}")
    if post.hashtags:
        print("Хештеги: " + " ".join(post.hashtags))
    print()


def _open_path(path: str) -> None:
    try:
        webbrowser.open(Path(path).resolve().as_uri())
    except Exception as exc:  # pragma: no cover - зависит от окружения
        print(f"Не удалось открыть в браузере: {exc}")


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace, settings: Settings) -> int:
    settings.ensure_dirs()
    env_file = settings.root / ".env"
    example = settings.root / ".env.example"
    if not env_file.exists() and example.exists():
        shutil.copyfile(str(example), str(env_file))
        print("Создан .env из .env.example — заполните TELEGRAM_BOT_TOKEN и ID каналов.")
    elif env_file.exists():
        print(".env уже существует — не трогаю.")
    else:
        print("Внимание: не найден .env.example — создайте .env вручную.")
    print("\nКаталоги готовы:", settings.data_dir)
    print("Следующие шаги:")
    print("  1) python -m content_factory demo          # посмотреть результат без токенов")
    print("  2) заполните .env (токен бота, chat_id каналов)")
    print("  3) python -m content_factory sources check # проверить источники")
    print("  4) python -m content_factory run --channel all --dry-run")
    print("  5) когда всё устраивает: CONTENT_FACTORY_DRY_RUN=false + python -m content_factory daemon")
    return 0


def cmd_channels(args: argparse.Namespace, settings: Settings) -> int:
    channels = load_channels(settings)
    _print_channel_table(channels, settings)
    return 0


def cmd_sources_check(args: argparse.Namespace, settings: Settings) -> int:
    try:
        from .sources import check_source
    except Exception as exc:
        print(f"Модуль источников недоступен: {exc}")
        return 1
    channels = select_channels(settings, _split_channels(args.channel))
    total = 0
    ok_count = 0
    for channel in channels:
        print(f"\n[{channel.id}] {channel.title}")
        for source in channel.sources:
            if not source.enabled:
                print(f"  - {source.name}: выключен")
                continue
            total += 1
            try:
                ok, message = check_source(source, settings)
            except Exception as exc:
                ok, message = False, str(exc)
            ok_count += 1 if ok else 0
            mark = "OK  " if ok else "FAIL"
            print(f"  {mark} {source.name} ({source.type}): {message}")
    print(f"\nПроверено источников: {total}, доступно: {ok_count}")
    return 0 if ok_count or total == 0 else 1


def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    dry_run = True if args.dry_run else (False if args.publish else None)
    if dry_run is None:
        dry_run = settings.dry_run
    # Публикаторы и Settings.dry_run смотрят на env-переменную (она приоритетнее
    # YAML), поэтому явные --publish/--dry-run должны переопределить и её,
    # иначе .env с CONTENT_FACTORY_DRY_RUN=true сделает --publish бесполезным.
    os.environ["CONTENT_FACTORY_DRY_RUN"] = "false" if not dry_run else "true"
    settings.raw.setdefault("app", {})["dry_run"] = bool(dry_run)
    print(f"Запуск: каналы={args.channel}, режим={'dry-run (без публикации)' if dry_run else 'ПУБЛИКАЦИЯ'}")
    results = run_channels(
        settings,
        channel_ids=_split_channels(args.channel),
        dry_run=dry_run,
        max_posts=args.max_posts,
    )
    if not results:
        print("Ни один канал не запущен.")
        return 1
    total_errors = 0
    for result in results:
        total_errors += len(result.errors)
        print(
            f"  {result.channel_id:<18} статей {result.articles_new:>3} | "
            f"сюжетов {result.clusters:>3} | постов {result.posts_generated:>2} | "
            f"опубликовано {result.posts_published:>2} | ошибок {len(result.errors):>2} "
            f"| {result.duration_sec:.1f} c"
        )
    if total_errors:
        print(f"\nПредупреждения/ошибки: {total_errors}. Подробности — в логе data/logs/factory.log")
    if dry_run:
        print(f"\nПосты сохранены в {settings.outbox_dir}")
    print("\nАналитика: python -m content_factory report")
    return 0


def cmd_preview(args: argparse.Namespace, settings: Settings) -> int:
    channels = select_channels(settings, _split_channels(args.channel))
    if not channels:
        print("Нет включённых каналов.")
        return 1
    posts_total = 0
    with Storage(settings.db_path) as storage:
        for channel in channels:
            print(f"\n### Канал: {channel.title} ({channel.id})")
            posts, errors = preview_channel(
                channel, settings, storage, limit=args.limit
            )
            if not posts:
                print("  (подходящих новых сюжетов нет)")
            for index, post in enumerate(posts, start=1):
                _print_post(post, index)
                posts_total += 1
            for error in errors:
                print(f"  ! {error}")
    print(
        f"Показано постов: {posts_total}. Посты не сохранены и не опубликованы "
        "(статьи учтены для дедупликации)."
    )
    return 0


def cmd_daemon(args: argparse.Namespace, settings: Settings) -> int:
    from .scheduler import Scheduler, daemon_loop

    settings.ensure_dirs()
    scheduler = Scheduler(settings)

    def channels_provider():
        return select_channels(settings)

    def callback(item) -> None:
        channels = {c.id: c for c in channels_provider()}
        channel = channels.get(item.channel_id)
        if channel is None:
            log.warning("Канал %s исчез из конфигурации, слот пропущен", item.channel_id)
            return
        with Storage(settings.db_path) as storage:
            from .pipeline import run_channel

            result = run_channel(channel, settings, storage, slot=item.slot)
        print(
            f"[{item.slot}] {channel.id}: статей {result.articles_new}, "
            f"постов {result.posts_generated}, опубликовано {result.posts_published}, "
            f"ошибок {len(result.errors)}"
        )

    print(
        "Демон запущен. Режим: "
        + ("DRY-RUN (файлы в data/outbox)" if settings.dry_run else "реальная публикация")
        + ". Остановка: Ctrl+C"
    )
    try:
        daemon_loop(
            settings,
            channels_provider=channels_provider,
            callback=callback,
            once=args.once,
            interval=args.interval,
        )
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
    return 0


def cmd_report(args: argparse.Namespace, settings: Settings) -> int:
    settings.ensure_dirs()
    with Storage(settings.db_path) as storage:
        if args.collect:
            try:
                from .analytics.collector import collect_all

                print("Собираю метрики каналов...")
                collect_all(load_channels(settings), settings, storage)
                from .analytics.telegram_metrics import collect_all_telegram_metrics

                collect_all_telegram_metrics(
                    load_network_channels(settings),
                    settings,
                    storage,
                    limit=int(settings.analytics.get("telegram_posts_limit", 30) or 30),
                )
            except Exception as exc:
                print(f"Метрики собраны не полностью: {exc}")
        try:
            from .analytics.report import save_report

            paths = save_report(settings, storage, load_channels(settings), days=args.days)
        except Exception as exc:
            print(f"Не удалось построить отчёт: {exc}")
            return 1
    print("Отчёт готов:")
    for fmt, path in paths.items():
        print(f"  {fmt}: {path}")
    if args.open and paths.get("html"):
        _open_path(paths["html"])
    return 0


def _print_telegram_summary(item: dict) -> None:
    subscribers = item.get("subscribers")
    growth = item.get("growth_subscribers")
    growth_text = "—" if growth is None else "{:+d}".format(int(growth))
    print(
        "  {:<18} подписчиков: {:>7} (рост {:>5}) постов: {:>3} "
        "ср. просмотры: {:>7} ER: {:>5}%".format(
            str(item.get("channel_id") or ""),
            subscribers if subscribers is not None else "—",
            growth_text,
            int(item.get("posts_analyzed") or 0),
            item.get("avg_views") or 0,
            item.get("er") or 0,
        )
    )


def cmd_telegram_metrics(args: argparse.Namespace, settings: Settings) -> int:
    from .analytics.telegram_metrics import collect_all_telegram_metrics

    channels = [channel for channel in load_network_channels(settings) if channel.enabled]
    requested = {str(item).strip() for item in _split_channels(args.channel)}
    if requested and "all" not in requested:
        unknown = requested - {channel.id for channel in channels}
        if unknown:
            print(f"Неизвестные каналы: {', '.join(sorted(unknown))}")
            return 1
        channels = [channel for channel in channels if channel.id in requested]
    with Storage(settings.db_path) as storage:
        summaries = collect_all_telegram_metrics(
            channels, settings, storage, limit=args.limit
        )
    print(f"Telegram-метрики: {len(summaries)} каналов")
    for item in summaries:
        _print_telegram_summary(item)
    if not any(int(item.get("posts_analyzed") or 0) for item in summaries):
        print(
            "\nПросмотры/реакции не собраны. Нужны: telethon, TG_API_ID, TG_API_HASH "
            "и user-аккаунт с доступом к каналам (TG_SESSION)."
        )
    print("\nОтчёт: python -m content_factory report")
    return 0


def cmd_metrics(args: argparse.Namespace, settings: Settings) -> int:
    from .analytics.collector import collect_all
    from .analytics.telegram_metrics import collect_all_telegram_metrics

    channels = load_channels(settings)
    network_channels = load_network_channels(settings)
    with Storage(settings.db_path) as storage:
        snapshots = collect_all(channels, settings, storage)
        telegram = collect_all_telegram_metrics(
            network_channels,
            settings,
            storage,
            limit=int(settings.analytics.get("telegram_posts_limit", 30) or 30),
        )
    print(f"Собрано срезов метрик: {len(snapshots)}")
    for snapshot in snapshots:
        print(
            f"  {snapshot.channel_id:<18} подписчиков: {snapshot.subscribers if snapshot.subscribers is not None else '—':>7} "
            f"постов: {snapshot.posts_total:>3} статей: {snapshot.articles_total:>3}"
        )
    if telegram:
        print(f"\nTelegram-метрики: {len(telegram)} каналов")
        for item in telegram:
            _print_telegram_summary(item)
        if not any(int(item.get("posts_analyzed") or 0) for item in telegram):
            print(
                "  Просмотры/реакции не собраны: установите telethon и задайте "
                "TG_API_ID/TG_API_HASH/TG_SESSION."
            )
    return 0


def cmd_demo(args: argparse.Namespace, settings: Settings) -> int:
    print("Демо-режим: без сети, без токенов, без публикации.")
    try:
        result = run_demo(settings, reset=not args.keep)
    except Exception as exc:
        print(f"Демо не удалось: {exc}")
        log.exception("Демо не удалось")
        return 1
    print(
        f"\nГотово: каналов {result['channels']}, постов {result['posts']} "
        f"(dry-run публикаций: {result['published']})."
    )
    print(f"Посты: {result['outbox']}")
    for fmt, path in (result.get("reports") or {}).items():
        print(f"Отчёт ({fmt}): {path}")
    html_path = (result.get("reports") or {}).get("html")
    if html_path:
        _open_path(html_path)
    print("\nДальше: заполните .env и запустите sources check / run.")
    return 0


def cmd_llm_test(args: argparse.Namespace, settings: Settings) -> int:
    from .nlp.llm import get_llm

    stage = getattr(args, "stage", None)
    llm = get_llm(settings, stage=stage)
    stage_note = f" | этап: {stage}" if stage else ""
    print(f"Провайдер: {settings.llm.get('provider')} | клиент: {llm.name}{stage_note}")
    describe = getattr(llm, "describe", None)
    if callable(describe):
        try:
            print(f"Настройки: {describe()}")
        except Exception:  # pragma: no cover - описание не должно ломать проверку
            pass
    print(f"Доступен: {'да' if llm.available else 'нет (будет использована локальная суммаризация)'}")
    if not llm.available:
        print("Проверьте настройки config/settings.yaml → llm и переменные окружения.")
        return 1
    prompt = (
        "Кратко, в 2 предложениях и без выдумок, перескажи: "
        "«Учёные обнаружили, что сон помогает мозгу очищаться от продуктов обмена веществ»."
    )
    text = llm.generate(prompt, system="Ты — аккуратный редактор новостей. Пиши по-русски.")
    if not text:
        print("Модель не вернула ответ. Проверьте, запущена ли она.")
        return 1
    print("\nОтвет модели:\n" + text.strip())
    try:
        from .nlp.tokens import get_tracker

        tracker = get_tracker()
        if tracker is not None:
            print("\n" + tracker.describe())
            print("Совет: повторный llm-test с тем же промптом придёт из кэша (0 токенов).")
    except Exception:  # pragma: no cover - статистика не должна ломать проверку
        pass
    return 0


def cmd_dify_apps(args: argparse.Namespace, settings: Settings) -> int:
    """Проверяет Dify workflow-приложения: имя, тип, входы и (опционально) запуск."""
    from .integrations import DifyWorkflowClient
    from .utils import env

    purposes = ["posts", "news", "trends", "seo"]
    if args.purpose and args.purpose != "all":
        purposes = [args.purpose]
    apps = ((settings.raw.get("integrations") or {}).get("dify_apps") or {})
    for purpose in purposes:
        cfg = apps.get(purpose) or {}
        key_env = str(cfg.get("api_key_env") or "")
        key = env(key_env, "") if key_env else ""
        print(f"== {purpose} ({key_env or 'api_key_env не задан'}) ==")
        if not key:
            print("  ключ не задан в .env — пропуск (см. docs/integrations.md)")
            continue
        client = DifyWorkflowClient(key, timeout=float(cfg.get("timeout", 120)))
        try:
            info = client.info()
            print(f"  приложение: {info.get('name')} | тип: {info.get('mode')}")
            variables = client.input_variables()
            print(f"  входы: {', '.join(variables) if variables else '(не объявлены)'}")
        except Exception as exc:
            print(f"  ошибка: {exc}")
            continue
        if args.run != purpose:
            continue
        inputs = {}
        for item in args.input or []:
            if "=" in str(item):
                name, value = str(item).split("=", 1)
                inputs[name.strip()] = value
        print(f"  тестовый запуск: {inputs}")
        try:
            data = client.run(inputs)
            status = (data.get("data") or {}).get("status")
            outputs = client.outputs(data)
            print(f"  status: {status}")
            print(f"  outputs: {json.dumps(outputs, ensure_ascii=False)[:1500]}")
        except Exception as exc:
            print(f"  ошибка запуска: {exc}")
    return 0


def cmd_ingest(args: argparse.Namespace, settings: Settings) -> int:
    """Конвертирует документы (PDF/Word/PPT/Excel/HTML) в Markdown для источников."""
    from .ingest import SUPPORTED_EXTENSIONS, convert_many

    targets: List[Path] = [Path(p).expanduser() for p in (args.paths or [])]
    if args.dir:
        base = Path(args.dir).expanduser()
        if not base.is_absolute():
            base = Path(settings.root) / base
        if not base.is_dir():
            print(f"Каталог не найден: {base}")
            return 2
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if any(part == ".markdown" for part in path.parts):
                continue
            targets.append(path)
    if not targets:
        print("Нечего конвертировать: передайте файлы или --dir.")
        return 2
    out_dir = Path(args.out).expanduser() if args.out else settings.data_dir / "inbox"
    if not out_dir.is_absolute():
        out_dir = Path(settings.root) / out_dir
    results = convert_many(targets, out_dir)
    ok = sum(1 for _src, md, error in results if md is not None and error is None)
    failed = len(results) - ok
    if args.json:
        payload = [
            {
                "source": str(src),
                "markdown": str(md) if md is not None else None,
                "error": error,
            }
            for src, md, error in results
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Конвертация: {ok} успешно, {failed} с ошибками. Каталог: {out_dir}")
        for src, md, error in results:
            if error:
                print(f"  ! {src.name}: {error}")
            else:
                print(f"  • {src.name} → {md.name}")
    return 0 if failed == 0 else 1


def _split_channels(value: Optional[str]) -> List[str]:
    if not value:
        return ["all"]
    return [part.strip() for part in str(value).split(",") if part.strip()]


# ---------------------------------------------------------------------------
# Парсер
# ---------------------------------------------------------------------------


def cmd_social_check(args: argparse.Namespace, settings: Settings) -> int:
    """Проверка соцсетей-публикаторов (Bluesky/Mastodon/Discord/Tumblr/Fediverse)."""
    from .config import load_network_channels
    from .publishers import get_publisher
    from .publishers.social import SocialPublisher

    channels = load_network_channels(settings)
    names = ["bluesky", "mastodon", "discord", "tumblr",
             "pleroma", "akkoma", "gotosocial", "friendica", "misskey"]
    ready_any = False
    for channel in channels:
        print(f"== {channel.id} ({channel.language}) ==")
        for name in names:
            publisher = get_publisher(name, settings)
            if not isinstance(publisher, SocialPublisher):
                continue
            try:
                ready, detail = publisher.check(channel)  # type: ignore[call-arg]
            except TypeError:
                ready, detail = publisher.check()
            except Exception as exc:  # noqa: BLE001
                ready, detail = False, str(exc)
            ready_any = ready_any or ready
            print(f"  {name:11} {'✓' if ready else '—'} {detail}")
    if not ready_any:
        print("\nНи одна соцсеть не настроена — добавьте креды в .env (docs/fediverse.md).")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content-factory",
        description="Автономный контент-завод для Telegram-каналов: сбор, анализ, публикация, аналитика.",
    )
    parser.add_argument("--root", default=None, help="Корень проекта (по умолчанию — каталог с config/)")
    parser.add_argument("--version", action="version", version=f"content-factory {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Создать каталоги и .env")
    p_init.set_defaults(func=cmd_init)

    p_channels = sub.add_parser("channels", help="Показать 6 каналов и расписание")
    p_channels.set_defaults(func=cmd_channels)

    p_sources = sub.add_parser("sources", help="Работа с источниками")
    sources_sub = p_sources.add_subparsers(dest="sources_command", required=True)
    p_check = sources_sub.add_parser("check", help="Проверить доступность источников")
    p_check.add_argument("--channel", default="all", help="id канала или all")
    p_check.set_defaults(func=cmd_sources_check)

    p_run = sub.add_parser("run", help="Один прогон сбора и публикации")
    p_run.add_argument("--channel", default="all", help="id канала, несколько через запятую или all")
    p_run.add_argument("--dry-run", action="store_true", help="Не публиковать, сохранить в data/outbox")
    p_run.add_argument("--publish", action="store_true", help="Опубликовать (переопределяет dry_run)")
    p_run.add_argument("--max-posts", type=int, default=None, help="Максимум постов на канал за прогон")
    p_run.set_defaults(func=cmd_run)

    p_preview = sub.add_parser("preview", help="Показать будущие посты, ничего не публикуя")
    p_preview.add_argument("--channel", default="all", help="id канала, несколько через запятую или all")
    p_preview.add_argument("--limit", type=int, default=3, help="Сколько сюжетов показать на канал")
    p_preview.set_defaults(func=cmd_preview)

    p_daemon = sub.add_parser("daemon", help="Автономная работа по расписанию")
    p_daemon.add_argument("--once", action="store_true", help="Одна проверка расписания и выход (для cron)")
    p_daemon.add_argument("--interval", type=int, default=None, help="Интервал проверки, секунды")
    p_daemon.set_defaults(func=cmd_daemon)

    p_report = sub.add_parser("report", help="Построить HTML и Markdown отчёт аналитики")
    p_report.add_argument("--days", type=int, default=7, help="Период отчёта в днях")
    p_report.add_argument("--no-collect", dest="collect", action="store_false", help="Не собирать метрики")
    p_report.add_argument("--open", action="store_true", help="Открыть HTML в браузере")
    p_report.set_defaults(func=cmd_report, collect=True)

    p_metrics = sub.add_parser("metrics", help="Собрать срез метрик каналов")
    p_metrics.set_defaults(func=cmd_metrics)

    p_tg = sub.add_parser(
        "telegram-metrics",
        help="Собрать подписчиков/просмотры/реакции Telegram (Bot API + Telethon)",
    )
    p_tg.add_argument("--channel", default="all", help="id канала, несколько через запятую или all")
    p_tg.add_argument("--limit", type=int, default=30, help="Сколько последних постов анализировать")
    p_tg.set_defaults(func=cmd_telegram_metrics)

    p_social = sub.add_parser(
        "social-check",
        help="Проверить соцсети-публикаторы (Bluesky/Mastodon/Discord/Fediverse)",
    )
    p_social.set_defaults(func=cmd_social_check)

    p_demo = sub.add_parser("demo", help="Офлайн-демо: посты и отчёт без сети и токенов")
    p_demo.add_argument("--keep", action="store_true", help="Не очищать прошлые демо-данные")
    p_demo.set_defaults(func=cmd_demo)

    p_llm = sub.add_parser("llm-test", help="Проверить выбранную LLM")
    p_llm.add_argument(
        "--stage",
        choices=["analysis", "generation"],
        default=None,
        help="Проверить маршрут этапа из llm.stage_routes (analysis/generation)",
    )
    p_llm.set_defaults(func=cmd_llm_test)

    p_apps = sub.add_parser(
        "dify-apps", help="Проверить Dify workflow-приложения (новости/тренды/SEO)"
    )
    p_apps.add_argument(
        "--purpose", default="all", choices=["all", "posts", "news", "trends", "seo"]
    )
    p_apps.add_argument(
        "--run", default="", choices=["", "posts", "news", "trends", "seo"],
        help="Какое приложение запустить с тестовыми входами",
    )
    p_apps.add_argument(
        "--input", action="append", default=[], help="key=value для тестового запуска"
    )
    p_apps.set_defaults(func=cmd_dify_apps)

    p_ingest = sub.add_parser(
        "ingest", help="Конвертировать PDF/Word/PPT/Excel/HTML в Markdown для источников"
    )
    p_ingest.add_argument("paths", nargs="*", help="Файлы документов")
    p_ingest.add_argument("--dir", default="", help="Каталог с документами (рекурсивно)")
    p_ingest.add_argument("--out", default="", help="Каталог для .md (по умолчанию data/inbox)")
    p_ingest.add_argument("--json", action="store_true", help="Машинный вывод результата")
    p_ingest.set_defaults(func=cmd_ingest)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = Settings.load(root=args.root)
        settings.ensure_dirs()
        setup_logging(settings)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}")
        return 2
    try:
        return int(args.func(args, settings) or 0)
    except KeyboardInterrupt:
        print("\nПрервано.")
        return 130
    except Exception as exc:  # pragma: no cover - верхняя защита CLI
        log.exception("Непредвиденная ошибка")
        print(f"Непредвиденная ошибка: {exc}. Подробности — data/logs/factory.log")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
