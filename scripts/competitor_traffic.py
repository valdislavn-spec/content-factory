#!/usr/bin/env python3
"""Отчёт «Конкуренты» по бесплатному endpoint Similarweb (без ключей/подписки).

Берёт оценки трафика сайтов-конкурентов из публичного endpoint, который
использует Chrome-расширение Similarweb (см. ``content_factory/integrations/
similarweb.py``), и собирает Markdown-отчёт: визиты в месяц, глобальный ранг,
отказы, глубина просмотра, время на сайте, категория.

Запуск:
    python scripts/competitor_traffic.py                  # ai + crypto + sports
    python scripts/competitor_traffic.py --group crypto
    python scripts/competitor_traffic.py --domains cointelegraph.com,decrypt.co
    python scripts/competitor_traffic.py --send           # ещё и сводку в Telegram
    python scripts/competitor_traffic.py --json-out data/reports/competitors.json

Почему в GitHub Actions: из РФ endpoint отдаёт 403 (CloudFront geo-block),
а на раннерах Actions он доступен без прокси.

Переменные окружения:
* ``TELEGRAM_ALERT_CHAT_ID`` — чат для ``--send`` (скрипт ``notify_telegram.py``);
* ``SIMILARWEB_DELAY`` — пауза между запросами, по умолчанию 2.5 с.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings
from content_factory.integrations.similarweb import (
    DEFAULT_COMPETITORS,
    fetch_many,
    format_markdown,
    format_telegram,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Конкуренты: трафик сайтов (Similarweb, без ключей)")
    parser.add_argument(
        "--group",
        choices=["ai", "crypto", "sports", "all"],
        default="all",
        help="Группа конкурентов из DEFAULT_COMPETITORS (по умолчанию all)",
    )
    parser.add_argument("--domains", default="", help="Свои домены через запятую (переопределяет --group)")
    parser.add_argument("--limit", type=int, default=0, help="Максимум доменов в группе (0 — все)")
    parser.add_argument("--delay", type=float, default=float(os.environ.get("SIMILARWEB_DELAY", "2.5")))
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--send", action="store_true", help="Отправить сводку в Telegram (TELEGRAM_ALERT_CHAT_ID)")
    return parser.parse_args(argv)


def collect_domains(args: argparse.Namespace) -> List[str]:
    if args.domains.strip():
        return [item.strip() for item in args.domains.split(",") if item.strip()]
    groups = list(DEFAULT_COMPETITORS) if args.group == "all" else [args.group]
    domains: List[str] = []
    for group in groups:
        subset = DEFAULT_COMPETITORS.get(group, [])
        if args.limit and args.limit > 0:
            subset = subset[: args.limit]
        domains.extend(subset)
    # убираем дубли, сохраняя порядок
    seen = set()
    unique: List[str] = []
    for domain in domains:
        if domain not in seen:
            seen.add(domain)
            unique.append(domain)
    return unique


def write_report(text: str, output_dir: Optional[str]) -> Path:
    if output_dir:
        base = Path(output_dir)
    else:
        try:
            base = Settings.load().root / "data" / "reports"
        except Exception:  # noqa: BLE001 — отчёт важнее настроек
            base = ROOT / "data" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = base / f"competitors-{stamp}.md"
    path.write_text(text, encoding="utf-8")
    return path


def send_telegram(text: str) -> int:
    script = Path(__file__).resolve().parent / "notify_telegram.py"
    return subprocess.call([sys.executable, str(script), text])


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    domains = collect_domains(args)
    if not domains:
        print("Нет доменов для проверки", file=sys.stderr)
        return 2
    print(f"Similarweb: проверяю {len(domains)} доменов (пауза {args.delay} c)…", file=sys.stderr)
    rows: List[Dict[str, Any]] = fetch_many(domains, delay=args.delay, timeout=args.timeout)

    ok = [row for row in rows if not row.get("error")]
    print(f"получено {len(ok)} из {len(rows)}", file=sys.stderr)

    markdown = format_markdown(rows)
    print(markdown)
    path = write_report(markdown, args.output_dir or None)
    print(f"отчёт: {path}", file=sys.stderr)

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"json: {json_path}", file=sys.stderr)

    if args.send:
        return send_telegram(format_telegram(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
