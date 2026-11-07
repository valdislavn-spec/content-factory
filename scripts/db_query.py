#!/usr/bin/env python3
"""Быстрый read-only SQL по базе фабрики (без MCP).

    python scripts/db_query.py "SELECT channel_id, status, COUNT(*) c FROM posts GROUP BY 1,2"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.factory_mcp import tool_factory_query  # noqa: E402


def main() -> int:
    sql = " ".join(sys.argv[1:]).strip()
    if not sql:
        print('usage: python scripts/db_query.py "SELECT ..."')
        return 2
    try:
        data = tool_factory_query(sql)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка: {exc}")
        return 1
    columns = data["columns"]
    if columns:
        print(" | ".join(columns))
        print("-+-".join("-" * len(name) for name in columns))
        for row in data["rows"]:
            print(" | ".join(str(row.get(name, "")) for name in columns))
    print(f"\nстрок: {data['count']}" + (" (обрезано)" if data["limited"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
