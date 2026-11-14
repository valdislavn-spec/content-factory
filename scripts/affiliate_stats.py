#!/usr/bin/env python3
"""Клики по партнёрским ссылкам: отчёт из links-tracker (Cloudflare Worker).

    LINK_TRACKER_BASE=https://links-tracker.example.workers.dev \
    LINK_TRACKER_STATS_TOKEN=... python scripts/affiliate_stats.py

    python scripts/affiliate_stats.py --json      # машинный вывод
    python scripts/affiliate_stats.py --top 10    # только первые N

Токен: LINK_TRACKER_STATS_TOKEN или LINK_TRACKER_ADMIN_TOKEN.
Цифры — только клики; показы Telegram не отдаёт, поэтому CTR считаем как
клики в сутки и долю от всех кликов сети.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List, Optional


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def fetch_stats(base: str, token: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{base.rstrip('/')}/stats?token={urllib.parse.quote(token)}"
    request = urllib.request.Request(url, headers={"User-Agent": "content-factory-stats/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def summarize(links: List[Dict[str, Any]], days: int = 7) -> List[Dict[str, Any]]:
    today = date.today()
    window = [(today - timedelta(days=offset)).isoformat() for offset in range(days)]
    rows: List[Dict[str, Any]] = []
    for link in links:
        per_day = link.get("days") or {}
        recent = sum(int(per_day.get(day, 0)) for day in window)
        rows.append({
            "code": link.get("code", ""),
            "channel": link.get("channel", ""),
            "label": link.get("label", ""),
            "total": int(link.get("total") or 0),
            "last_24h": int(per_day.get(today.isoformat(), 0)),
            "last_7d": recent,
            "per_day": round(recent / days, 2),
            "last_click": link.get("last_click") or "",
        })
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Клики по партнёрским ссылкам")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)

    base = env("LINK_TRACKER_BASE") or "https://links-tracker.valdislav-n.workers.dev"
    token = env("LINK_TRACKER_STATS_TOKEN") or env("LINK_TRACKER_ADMIN_TOKEN")
    if not token:
        print("нет LINK_TRACKER_STATS_TOKEN / LINK_TRACKER_ADMIN_TOKEN")
        return 2

    try:
        data = fetch_stats(base, token)
    except urllib.error.HTTPError as exc:
        print(f"tracker: HTTP {exc.code} — проверь токен")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"tracker недоступен: {type(exc).__name__}: {exc}")
        return 1

    rows = summarize(data.get("links") or [], args.days)
    if args.top:
        rows = rows[: args.top]
    total = sum(row["total"] for row in rows)

    if args.json:
        print(json.dumps({"total_clicks": total, "links": rows}, ensure_ascii=False, indent=2))
        return 0

    print(f"клики по партнёрским ссылкам · всего {total} · окно {args.days} дн.\n")
    header = f"{'код':<28}{'канал':<14}{'всего':>7}{'24ч':>6}{'7д':>6}{'в день':>8}  последний"
    print(header)
    print("-" * len(header))
    for row in rows:
        share = f"{row['total'] / total * 100:.0f}%" if total else "—"
        print(
            f"{row['code'][:27]:<28}{row['channel'][:13]:<14}{row['total']:>7}"
            f"{row['last_24h']:>6}{row['last_7d']:>6}{row['per_day']:>8}  "
            f"{(row['last_click'] or '—')[:16]}  {share}"
        )
    if not rows:
        print("(пока нет данных: трекер не видел кликов)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
