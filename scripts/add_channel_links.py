#!/usr/bin/env python3
"""Добавляет в контентные страницы блок ссылок на Telegram-каналы.

Внутренняя перелинковка: travel-гиды, туры и перелёты ведут на каналы сети,
а не только друг на друга. Идемпотентно — повторный запуск ничего не меняет.

    python scripts/add_channel_links.py
    python scripts/add_channel_links.py --dry-run
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MARKER = "<!-- channel-links -->"

CHANNELS = [
    ("https://t.me/HOOPY0007", "Crypto &amp; Blockchain"),
    ("https://t.me/AINEWS0007", "AI News"),
    ("https://t.me/SPORTNews0007", "US Sports"),
    ("https://t.me/WORLDNews0007", "IA en español"),
    ("https://t.me/TechnologiesNews01", "Cripto en español"),
    ("https://t.me/SPORTSAnalytics007", "Deporte"),
]

BLOCK = (
    MARKER
    + '\n<p style="font-size:14px;color:#374151;margin-top:18px">Our Telegram channels: '
    + " · ".join(
        f'<a href="{url}" style="color:#2563eb;text-decoration:none">{name}</a>'
        for url, name in CHANNELS
    )
    + ".</p>\n"
)


def targets() -> list[Path]:
    files: list[Path] = []
    for folder in ("travel", "flights", "tours", "channels"):
        files.extend(sorted((DOCS / folder).glob("*.html")))
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed = skipped = 0
    for path in targets():
        html = path.read_text(encoding="utf-8")
        if MARKER in html:
            skipped += 1
            continue
        anchor = '<p style="font-size:13px;color:#6b7280;margin-top:22px">© Content Factory'
        if anchor not in html:
            print("— нет подвала, пропуск:", path.relative_to(DOCS))
            skipped += 1
            continue
        if not args.dry_run:
            path.write_text(html.replace(anchor, BLOCK + anchor, 1), encoding="utf-8")
        changed += 1
        print(("· " if args.dry_run else "✓ ") + str(path.relative_to(DOCS)))
    print(f"\nобновлено: {changed} · пропущено: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
