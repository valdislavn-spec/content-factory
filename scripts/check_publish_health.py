#!/usr/bin/env python3
"""Проверяет лог прогона: были ли слоты и были ли реально публикации.

Запускается в workflow после тиков (только для live). Если были слоты,
но ни одного поста в Telegram, или были ошибки публикации — завершается
кодом 1, и workflow падает (срабатывает алерт в Telegram).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LOG = Path("data/logs/factory.log")
PATTERNS = {
    "slots": re.compile(r"слотов обработано (\d+)"),
    "published": re.compile(r"опубликован \(telegram\)"),
    "publish_errors": re.compile(r"Telegram: канал .*?ошибк|ОШИБКА отправки|паблишер.*ошибк", re.IGNORECASE),
    "run_errors": re.compile(r"Ошибка источника"),
}


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
    if publish_errors > 0:
        print("health: есть ошибки публикации — падаем для алерта")
        return 1
    if slots >= 2 and published == 0:
        print("health: слоты были, но публикаций нет — падаем для алерта")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
