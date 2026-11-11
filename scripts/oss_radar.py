#!/usr/bin/env python3
"""OSS Radar: собрать «свежие релизы open-source» и подготовить Telegram-посты.

Примеры:
    ./.venv/bin/python scripts/oss_radar.py --channel ai-news --hours 24
    ./.venv/bin/python scripts/oss_radar.py --channel tech-ai-es --hours 48 --json
    ./.venv/bin/python scripts/oss_radar.py --channel all --out data/reports/oss-radar

Источники (см. config/oss_radar.yaml):
    * github        — бесплатно, без ключа (60 запросов/час; с GITHUB_TOKEN — 5000/час);
    * libraries_io  — нужен бесплатный ключ LIBRARIES_IO_API_KEY (OAuth GitHub);
    * all           — github + libraries.io (если ключ задан).

Пост не публикуется: скрипт печатает/сохраняет готовый HTML/plain-текст.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.oss_radar import (  # noqa: E402
    GitHubClient,
    LibrariesIOClient,
    OSSRadarError,
    Release,
    channel_config,
    github_items_to_releases,
    libraries_io_releases,
    load_config,
    render_digest,
    select_recent,
)

logger = logging.getLogger("oss_radar")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OSS Radar: свежие open-source релизы")
    parser.add_argument("--config", default="config/oss_radar.yaml", help="YAML-конфиг рубрики")
    parser.add_argument("--channel", default="all", help="id канала, несколько через запятую или all")
    parser.add_argument("--hours", type=float, default=24, help="Окно в часах (по умолчанию 24)")
    parser.add_argument("--limit", type=int, default=0, help="Максимум релизов в посте (0 = из конфига)")
    parser.add_argument(
        "--source",
        default="github",
        choices=["github", "libraries_io", "all"],
        help="Источник релизов (по умолчанию github)",
    )
    parser.add_argument("--json", action="store_true", help="Машинный вывод (JSON)")
    parser.add_argument("--out", default="", help="Каталог/файл для сохранения HTML+plain")
    parser.add_argument("--refresh", action="store_true", help="Игнорировать кэш API")
    parser.add_argument("--include-prereleases", action="store_true", help="Включать prerelease/draft")
    return parser.parse_args(argv)


def _collect_github(
    repos: List[str],
    client: GitHubClient,
    per_page: int,
    refresh: bool,
    shared: Dict[str, List[Release]],
) -> List[Release]:
    """Собирает релизы репозиториев; каждый repo тянется один раз за запуск."""
    collected: List[Release] = []
    for repo in repos:
        if repo not in shared:
            items = client.releases(repo, per_page=per_page, refresh=refresh)
            shared[repo] = github_items_to_releases(repo, items)
        collected.extend(shared[repo])
    return collected


def _collect_libraries_io(
    client: LibrariesIOClient,
    queries: List[str],
    platforms: List[str],
    allowed_licenses: List[str],
    refresh: bool,
) -> List[Release]:
    collected: List[Release] = []
    for query in queries:
        items = client.search(query, platforms=platforms, refresh=refresh)
        collected.extend(libraries_io_releases(items, allowed_licenses=allowed_licenses))
    return collected


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings.load()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(settings.root) / config_path
    try:
        config = load_config(config_path)
    except OSSRadarError as exc:
        print(f"OSS Radar: {exc}")
        return 2

    channel_ids = (
        sorted(config.get("channels", {}))
        if str(args.channel).strip().lower() in ("all", "")
        else [part.strip() for part in str(args.channel).split(",") if part.strip()]
    )
    cache_dir = Path(settings.data_dir) / "cache" / "oss_radar"
    github_client: Optional[GitHubClient] = None
    libraries_client: Optional[LibrariesIOClient] = None
    if args.source in ("github", "all"):
        github_client = GitHubClient(cache_dir=cache_dir)
    if args.source in ("libraries_io", "all"):
        libraries_client = LibrariesIOClient(cache_dir=cache_dir)

    shared_github: Dict[str, List[Release]] = {}
    results: List[Dict[str, Any]] = []
    any_error = False
    for channel_id in channel_ids:
        try:
            channel = channel_config(config, channel_id)
        except OSSRadarError as exc:
            print(f"OSS Radar: {exc}")
            any_error = True
            continue
        releases: List[Release] = []
        if github_client is not None:
            releases.extend(
                _collect_github(
                    [str(repo) for repo in channel["repos"]],
                    github_client,
                    per_page=20,
                    refresh=args.refresh,
                    shared=shared_github,
                )
            )
        if libraries_client is not None:
            if not libraries_client.api_key:
                if args.source == "libraries_io":
                    print(
                        "OSS Radar: LIBRARIES_IO_API_KEY не задан — ключ бесплатный, "
                        "вход через GitHub: libraries.io → Account → API key"
                    )
                    return 2
                logger.warning("OSS Radar: LIBRARIES_IO_API_KEY не задан — пропускаю libraries.io")
            else:
                try:
                    releases.extend(
                        _collect_libraries_io(
                            libraries_client,
                            [str(query) for query in channel.get("queries") or []],
                            [str(platform) for platform in channel.get("platforms") or []],
                            [str(license) for license in channel.get("allowed_licenses") or []],
                            refresh=args.refresh,
                        )
                    )
                except OSSRadarError as exc:
                    logger.warning("OSS Radar: libraries.io — %s", exc)
                    any_error = True
        limit = args.limit or int(channel.get("max_items") or 10)
        selected = select_recent(
            releases,
            hours=args.hours,
            max_items=limit,
            include_prereleases=bool(args.include_prereleases)
            or bool(channel.get("include_prereleases", False)),
            per_repo=int(channel.get("per_repo", 1)),
        )
        digest = render_digest(
            selected,
            channel_id=channel_id,
            hours=args.hours,
            language=str(channel.get("language") or "en"),
            max_items=limit,
        )
        results.append(
            {
                "channel": channel_id,
                "language": digest["language"],
                "items": digest["items"],
                "html": digest["html"],
                "plain": digest["plain"],
                "releases": [release.to_dict() for release in selected],
            }
        )
        if args.out:
            out_dir = Path(args.out)
            if not out_dir.is_absolute():
                out_dir = Path(settings.root) / out_dir
            if out_dir.suffix:
                out_dir = out_dir.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
            (out_dir / f"{channel_id}-{stamp}.html").write_text(digest["html"] + "\n", encoding="utf-8")
            (out_dir / f"{channel_id}-{stamp}.txt").write_text(digest["plain"] + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"channels": results, "hours": args.hours}, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"=== {item['channel']} ({item['language']}): {item['items']} релизов ===")
            print(item["plain"])
            print()
    if github_client is not None and github_client.remaining is not None:
        mode = "с токеном" if github_client.token else "анонимно"
        print(f"GitHub API: осталось запросов {github_client.remaining} ({mode})")
    if args.source == "libraries_io" and not (libraries_client and libraries_client.api_key):
        print("OSS Radar: librares.io без ключа не работает — укажите LIBRARIES_IO_API_KEY.")
        return 2
    if any_error and not results:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
