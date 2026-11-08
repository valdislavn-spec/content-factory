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
    "publish_errors": re.compile(r"Telegram: канал .*?ошибк|ОШИБКА отправки|паблишер.*ошибк", re.IGNORECASE),
    "run_errors": re.compile(r"Ошибка источника"),
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
    tail = text[-400_000:]
    slots = sum(int(m.group(1)) for m in PATTERNS["slots"].finditer(tail))
    published = len(PATTERNS["published"].findall(tail))
    publish_errors = len(PATTERNS["publish_errors"].findall(tail))
    source_errors = len(PATTERNS["run_errors"].findall(tail))
    print(
        f"health: слотов={slots}, опубликовано={published}, "
        f"ошибок публикации={publish_errors}, ошибок источников={source_errors}"
    )
    for line in llm_quota_lines():
        print("health:", line)
    if publish_errors > 0:
        print("health: есть ошибки публикации — падаем для алерта")
        return 1
    if slots >= 2 and published == 0:
        print("health: слоты были, но публикаций нет — падаем для алерта")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
