#!/usr/bin/env python3
"""Проверяет лог прогона: были ли слоты и были ли реально публикации.

Запускается в workflow после тиков (только для live). Если были слоты,
но ни одного поста в Telegram, или были ошибки публикации — завершается
кодом 1, и workflow падает (срабатывает алерт в Telegram).
"""
from __future__ import annotations

import json
import re
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
}


def analyze(text: str) -> dict:
    """Разбирает хвост лога в счётчики. Вынесено для тестов."""
    tail = text[-400_000:]
    slots = sum(int(m.group(1)) for m in PATTERNS["slots"].finditer(tail))
    published = len(PATTERNS["published"].findall(tail))
    error_lines = [m.group(0) for m in PATTERNS["publish_errors"].finditer(tail)]
    source_errors = len(PATTERNS["run_errors"].findall(tail))
    return {
        "slots": slots,
        "published": published,
        "publish_errors": len(error_lines),
        "publish_error_samples": list(dict.fromkeys(error_lines))[:5],
        "source_errors": source_errors,
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
    for line in llm_quota_lines():
        print("health:", line)
    if stats["publish_errors"] > 0:
        print("health: есть ошибки публикации — падаем для алерта")
        return 1
    if stats["slots"] >= 2 and stats["published"] == 0:
        print("health: слоты были, но публикаций нет — падаем для алерта")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
