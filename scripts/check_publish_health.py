#!/usr/bin/env python3
"""Проверяет лог прогона: были ли слоты и были ли реально публикации.

Запускается в workflow после тиков (только для live). Если были слоты,
но ни одного поста в Telegram, или были ошибки публикации — завершается
кодом 1, и workflow падает (срабатывает алерт в Telegram).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = Path("data/logs/factory.log")
PATTERNS = {
    "slots": re.compile(r"слотов обработано (\d+)"),
    "published": re.compile(r"опубликован \(telegram\)"),
    "publish_errors": re.compile(
        r"Telegram: канал .*?ошибк|ОШИБКА отправки|паблишер.*ошибк|"
        r"Не удалось опубликовать .*? через \w+",
        re.IGNORECASE,
    ),
    "run_errors": re.compile(r"Ошибка источника"),
    "channel_summary": re.compile(
        r"\[(?P<slot>[^\]]+)\]\s+(?P<channel>[A-Za-z0-9_-]+):\s+"
        r"статей\s+(?P<articles>\d+),\s+"
        r"постов\s+(?P<posts>\d+),\s+"
        r"опубликовано\s+(?P<published>\d+),\s+"
        r"ошибок\s+(?P<errors>\d+)"
    ),
}


def analyze(text: str) -> dict:
    """Разбирает хвост лога в счётчики. Вынесено для тестов."""
    tail = text[-400_000:]
    slots = sum(int(m.group(1)) for m in PATTERNS["slots"].finditer(tail))
    published = len(PATTERNS["published"].findall(tail))
    error_lines = [m.group(0) for m in PATTERNS["publish_errors"].finditer(tail)]
    source_errors = len(PATTERNS["run_errors"].findall(tail))
    channels: dict[str, dict[str, int]] = {}
    for match in PATTERNS["channel_summary"].finditer(tail):
        channel_id = match.group("channel")
        row = channels.setdefault(
            channel_id,
            {"slots": 0, "articles": 0, "posts": 0, "published": 0, "errors": 0},
        )
        row["slots"] += 1
        row["articles"] += int(match.group("articles"))
        row["posts"] += int(match.group("posts"))
        row["published"] += int(match.group("published"))
        row["errors"] += int(match.group("errors"))
    channel_problems: list[str] = []
    for channel_id, row in sorted(channels.items()):
        if row["errors"] > 0:
            channel_problems.append(
                f"{channel_id}: ошибок публикации {row['errors']} "
                f"(постов {row['posts']}, опубликовано {row['published']})"
            )
        elif row["posts"] > 0 and row["published"] == 0:
            channel_problems.append(
                f"{channel_id}: постов {row['posts']}, но опубликовано 0"
            )
    return {
        "slots": slots,
        "published": published,
        "publish_errors": len(error_lines),
        "publish_error_samples": list(dict.fromkeys(error_lines))[:5],
        "source_errors": source_errors,
        "channels": channels,
        "channel_problems": channel_problems,
    }



def llm_quota_lines() -> list[str]:
    """Краткий отчёт по лимитам LLM; предупреждение при >80% дневного лимита."""
    lines: list[str] = []
    try:
        from content_factory.config import Settings
        limits = (Settings.load().llm or {}).get("provider_limits") or {}
    except Exception as exc:  # noqa: BLE001
        return [f"llm: не удалось прочитать settings ({exc})"]
    for path in sorted(Path("data").glob("llm_usage_*.json")):
        provider = path.stem.removeprefix("llm_usage_")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            used = int(data.get("count") or 0)
            limit = int(limits.get(provider) or 0)
            if not limit:
                continue
            pct = used / limit * 100
            line = f"llm {provider}: {used}/{limit} ({pct:.0f}%)"
            lines.append(line)
            if pct >= 80:
                print(f"::warning::LLM quota {provider} {used}/{limit} ({pct:.0f}%)")
        except (OSError, ValueError):
            continue
    return lines


def retry_queue_depth() -> int | None:
    """Сколько постов ждёт повторной публикации в локальной SQLite."""
    path = Path("data/factory.sqlite3")
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM publish_retries").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def main() -> int:
    if not LOG.exists():
        print("health: лог не найден — пропуск")
        return 0
    text = LOG.read_text(encoding="utf-8", errors="replace")
    stats = analyze(text)
    print(
        f"health: слотов={stats['slots']}, опубликовано={stats['published']}, "
        f"ошибок публикации={stats['publish_errors']}, "
        f"ошибок источников={stats['source_errors']}"
    )
    for sample in stats["publish_error_samples"]:
        print(f"health: ошибка публикации: {sample[:240]}")
    for channel_id, row in sorted(stats["channels"].items()):
        print(
            f"health: канал {channel_id}: слотов={row['slots']}, "
            f"постов={row['posts']}, опубликовано={row['published']}, "
            f"ошибок={row['errors']}"
        )
    for problem in stats["channel_problems"]:
        print(f"health: проблема канала: {problem}")
    queue_depth = retry_queue_depth()
    if queue_depth is not None:
        print(f"health: очередь ретраев={queue_depth}")
    for line in llm_quota_lines():
        print("health:", line)
    if stats["publish_errors"] > 0:
        print("health: есть ошибки публикации — падаем для алерта")
        return 1
    if stats["channel_problems"]:
        print("health: есть проблемы каналов — падаем для алерта")
        return 1
    if stats["slots"] >= 2 and stats["published"] == 0:
        print("health: слоты были, но публикаций нет — падаем для алерта")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
