#!/usr/bin/env python3
"""Прописывает партнёрскую ссылку в config/affiliates.yaml и включает программу.

    python scripts/affiliate_set_link.py --program bitget --url https://...
    python scripts/affiliate_set_link.py --program mexc --url https://... --price "40%"

Проверяет, что ссылка http(s), и переводит status в ready.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "affiliates.yaml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--commission", default="")
    parser.add_argument("--config", default=str(CONFIG))
    args = parser.parse_args()

    if not re.match(r"^https?://", args.url):
        print("url должен начинаться с http:// или https://")
        return 2
    config_path = Path(args.config)
    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(^  {re.escape(args.program)}:\n(?:    .*\n)*?    url: )\"\"", re.M)
    if not pattern.search(text):
        print(f"программа {args.program} не найдена или url уже заполнен")
        return 1
    text = pattern.sub(lambda m: m.group(1) + f'"{args.url}"', text, count=1)
    text = re.sub(
        rf"(^  {re.escape(args.program)}:\n(?:    .*\n)*?    status: )\w+",
        lambda m: m.group(1) + "ready", text, count=1, flags=re.M,
    )
    if args.commission:
        text = re.sub(
            rf"(^  {re.escape(args.program)}:\n(?:    .*\n)*?    commission: )\"[^\"]*\"",
            lambda m: m.group(1) + f'"{args.commission}"', text, count=1, flags=re.M,
        )
    config_path.write_text(text, encoding="utf-8")
    print(f"{args.program}: ссылка записана, status=ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
