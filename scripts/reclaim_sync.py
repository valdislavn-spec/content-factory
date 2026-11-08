#!/usr/bin/env python3
"""Создаёт в Reclaim.ai рабочие задачи по контент-фабрике (идемпотентно).

Идея: Reclaim.ai сам находит время в календаре под задачи. Скрипт добавляет
повторяемые задачи сопровождения фабрики, помеченные префиксом [CF], и не
создаёт дубли, если активная задача с таким названием уже есть.

    export RECLAIM_API_KEY=...        # https://app.reclaim.ai/settings/developer
    python scripts/reclaim_sync.py          # dry-run: показать план
    python scripts/reclaim_sync.py --apply  # создать недостающие задачи
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.reclaim_mcp as API  # noqa: E402

MARKER = "[CF]"

# План задач сопровождения: (title, minutes, priority)
WORK_TASKS: List[Dict[str, Any]] = [
    {
        "title": f"{MARKER} Утренняя проверка системы",
        "notes": "Проверить: последние публикации во всех 6 каналах, ошибки в Actions, health-строку тика.",
        "minutes": 15,
        "priority": "P2",
    },
    {
        "title": f"{MARKER} Разбор аналитики каналов",
        "notes": "Просмотры/ER/подписчики, топ-посты, что зашло и что повторить.",
        "minutes": 45,
        "priority": "P3",
    },
    {
        "title": f"{MARKER} Ревью контент-плана на неделю",
        "notes": "Слоты, темы, источники, промо и кросс-промо; обновить расписание при необходимости.",
        "minutes": 60,
        "priority": "P3",
    },
]


def active_titles() -> List[str]:
    data = API.list_tasks(include_completed=False)
    return [str(task.get("title") or "") for task in data.get("tasks", [])]


def missing_tasks(existing: List[str]) -> List[Dict[str, Any]]:
    normalized = {title.strip().lower() for title in existing}
    return [task for task in WORK_TASKS if task["title"].strip().lower() not in normalized]


def run(dry_run: bool) -> Dict[str, Any]:
    import os

    if dry_run and not os.environ.get("RECLAIM_API_KEY", "").strip():
        return {
            "dry_run": True,
            "existing": 0,
            "planned": [task["title"] for task in WORK_TASKS],
            "created": [],
            "note": "RECLAIM_API_KEY не задан — показан только план. "
            "Токен: https://app.reclaim.ai/settings/developer",
        }
    existing = active_titles()
    todo = missing_tasks(existing)
    created: List[Dict[str, Any]] = []
    if not dry_run:
        for task in todo:
            created.append(
                API.create_task(
                    task["title"],
                    task["notes"],
                    task["minutes"],
                    task["priority"],
                )
            )
    return {
        "dry_run": dry_run,
        "existing": len(existing),
        "planned": [task["title"] for task in todo],
        "created": created,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="создать задачи (по умолчанию dry-run)")
    args = parser.parse_args()
    try:
        result = run(dry_run=not args.apply)
    except API.ReclaimError as exc:
        print(f"Ошибка Reclaim: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
