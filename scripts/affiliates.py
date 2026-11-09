#!/usr/bin/env python3
"""Партнёрские ссылки: реестр, UTM, блоки для постов, план вставок.

    ./.venv/bin/python scripts/affiliates.py check
    ./.venv/bin/python scripts/affiliates.py list
    ./.venv/bin/python scripts/affiliates.py link --channel crypto-news --program mylead
    ./.venv/bin/python scripts/affiliates.py block --channel ai-news [--program mylead]
    ./.venv/bin/python scripts/affiliates.py pins                  # блоки для всех каналов
    ./.venv/bin/python scripts/affiliates.py plan --channel ai-news --posts 30
    ./.venv/bin/python scripts/affiliates.py block --channel ai-news --log   # + growth-событие

В блоки попадают только программы со статусом ready. Раскрытие «реклама» входит
в блок автоматически; для спортивных каналов добавляется 18+.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.affiliates import (  # noqa: E402
    AffiliateError,
    AffiliateRotator,
    load_registry,
    log_block,
    render_block,
    tracked_link,
    validate_registry,
)
from content_factory.config import Settings  # noqa: E402
from content_factory.storage import Storage  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Партнёрские ссылки и блоки")
    parser.add_argument("action", choices=["check", "list", "link", "block", "pins", "plan"])
    parser.add_argument("--config", default="config/affiliates.yaml")
    parser.add_argument("--channel", default="", help="id канала (для link/block/plan)")
    parser.add_argument("--program", default="", help="id программы (для link/block)")
    parser.add_argument("--lang", default="", help="язык блока en/es (по умолчанию — язык канала)")
    parser.add_argument("--json", action="store_true", help="Машинный вывод")
    parser.add_argument("--posts", type=int, default=30, help="Сколько постов в плане (plan)")
    parser.add_argument("--every", type=int, default=0, help="Свой шаг вставки (1 на N постов)")
    parser.add_argument("--log", action="store_true", help="Записать показ в growth_events")
    parser.add_argument("--strict", action="store_true", help="check: ненулевой код при предупреждениях")
    return parser.parse_args(argv)


def _channel_or_fail(registry, channel_id: str):
    if not channel_id:
        print("Укажите --channel")
        return None
    try:
        return registry.channel(channel_id)
    except AffiliateError as exc:
        print(f"Affiliate: {exc}")
        return None


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(settings.root) / config_path
    try:
        registry = load_registry(config_path)
    except AffiliateError as exc:
        print(f"Affiliate: {exc}")
        return 2

    if args.action == "check":
        warnings = validate_registry(registry)
        if args.json:
            print(json.dumps({"warnings": warnings, "channels": sorted(registry.channels)}, ensure_ascii=False, indent=2))
        else:
            print(f"Программ: {len(registry.programs)}, каналов: {len(registry.channels)}")
            ready = [program.id for program in registry.programs.values() if program.ready]
            print("Готовы к размещению: " + (", ".join(ready) if ready else "нет"))
            for warning in warnings:
                print(f"  ⚠️ {warning}")
            if not warnings:
                print("  ✅ проблем нет")
        return 0 if not warnings or not args.strict else 1

    if args.action == "list":
        data = []
        for channel in registry.channels.values():
            ready = [
                {
                    "program": program.id,
                    "title": program.title,
                    "url": tracked_link(registry, channel.id, program.id),
                    "commission": program.commission,
                }
                for program in registry.ready_programs(channel.id)
            ]
            pending = [
                {"program": registry.programs[program_id].id, "status": registry.programs[program_id].status}
                for program_id in channel.programs
                if not registry.programs[program_id].ready
            ]
            data.append(
                {
                    "channel": channel.id,
                    "language": channel.language,
                    "age_restricted": channel.age_restricted,
                    "utm_source": channel.utm_source,
                    "ready": ready,
                    "not_ready": pending,
                }
            )
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            for item in data:
                marker = " 18+" if item["age_restricted"] else ""
                print(f"{item['channel']} ({item['language']}){marker}:")
                if not item["ready"]:
                    print("  — нет готовых программ")
                for entry in item["ready"]:
                    print(f"  ✅ {entry['program']}: {entry['title']} → {entry['url']}")
                if item["not_ready"]:
                    print("  ⏳ " + ", ".join(f"{entry['program']}({entry['status']})" for entry in item["not_ready"]))
        return 0

    if args.action == "link":
        channel = _channel_or_fail(registry, args.channel)
        if channel is None:
            return 2
        if not args.program:
            print("Укажите --program")
            return 2
        try:
            link = tracked_link(registry, args.channel, args.program)
        except AffiliateError as exc:
            print(f"Affiliate: {exc}")
            return 1
        print(json.dumps({"channel": args.channel, "program": args.program, "url": link}, ensure_ascii=False) if args.json else link)
        return 0

    if args.action in ("block", "pins"):
        results = []
        channel_ids = [args.channel] if args.channel else sorted(registry.channels)
        for channel_id in channel_ids:
            channel = _channel_or_fail(registry, channel_id)
            if channel is None:
                continue
            try:
                block = render_block(
                    registry,
                    channel_id,
                    program_id=args.program or None,
                    language=args.lang or None,
                )
            except AffiliateError as exc:
                print(f"{channel_id}: {exc}")
                continue
            if args.log:
                try:
                    with Storage(settings.db_path) as storage:
                        log_block(storage, channel_id, block["program"])
                except Exception as exc:  # учёт не должен срывать вывод
                    print(f"{channel_id}: показ не записан: {exc}")
            results.append(block)
            if not args.json:
                print(f"=== {channel_id} ({block['language']}, программа {block['program']}) ===")
                print(block["html"])
                print()
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if args.action == "plan":
        channel = _channel_or_fail(registry, args.channel)
        if channel is None:
            return 2
        rotator = AffiliateRotator(
            registry, args.channel, every=args.every or None
        )
        plan = rotator.plan(args.posts)
        if args.json:
            print(json.dumps({"channel": args.channel, "every": rotator.every, "plan": plan}, ensure_ascii=False, indent=2))
        else:
            print(f"{args.channel}: 1 партнёрский блок на {rotator.every} постов")
            for item in plan:
                print(f"  пост #{item['post']}: {item['program']} → {item['url']}")
        return 0

    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
