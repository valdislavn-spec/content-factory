#!/usr/bin/env python3
"""Отчёт по кликам партнёрских ссылок из link-tracker (Cloudflare Worker).

    ./.venv/bin/python scripts/affiliate_report.py                 # markdown в stdout
    ./.venv/bin/python scripts/affiliate_report.py --json
    ./.venv/bin/python scripts/affiliate_report.py --days 7 --out docs/reports/affiliate-clicks.md

Данные берутся из нашего трекера (`LINK_TRACKER_BASE` + `LINK_TRACKER_STATS_TOKEN`),
секреты не печатаются. Это «замер» для affiliate-плана: клики по каналам/сетям,
последний клик и лучшие ссылки. Конверсии (регистрации/покупки) — из кабинетов программ.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def tracker_config() -> tuple[str, str]:
    base = (os.environ.get("LINK_TRACKER_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("LINK_TRACKER_STATS_TOKEN") or "").strip()
    if not base or not token:
        raise RuntimeError(
            "Нужны LINK_TRACKER_BASE и LINK_TRACKER_STATS_TOKEN в .env "
            "(см. docs/monetization/link-tracker.md)"
        )
    return base, token


def fetch_stats(timeout: float = 20.0) -> Dict[str, Any]:
    base, token = tracker_config()
    url = f"{base}/stats?" + urllib.parse.urlencode({"token": token})
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "ContentFactory/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout))) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"link-tracker HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"link-tracker недоступен: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise RuntimeError("link-tracker вернул не JSON") from exc
    if not isinstance(data, dict) or not data.get("ok"):
        raise RuntimeError(f"link-tracker error: {str(data)[:200]}")
    return data


def _cutoff(days: Optional[int]) -> Optional[str]:
    if not days or days <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).date().isoformat()


def _sum_days(days: Dict[str, int], cutoff: Optional[str]) -> int:
    total = 0
    for day, count in (days or {}).items():
        if cutoff is None or str(day) >= cutoff:
            total += int(count or 0)
    return total


def build_report(data: Dict[str, Any], days: Optional[int] = None, min_clicks: int = 0) -> Dict[str, Any]:
    """Агрегирует stats: по сетям, каналам, ссылкам и дням."""
    cutoff = _cutoff(days)
    links: List[Dict[str, Any]] = []
    by_network: Dict[str, int] = {}
    by_channel: Dict[str, int] = {}
    by_day: Dict[str, int] = {}
    total = 0
    for item in data.get("links") or []:
        if not isinstance(item, dict):
            continue
        clicks = _sum_days(item.get("days") or {}, cutoff)
        if clicks < int(min_clicks):
            continue
        total += clicks
        network = str(item.get("network") or "unknown")
        channel = str(item.get("channel") or "—")
        by_network[network] = by_network.get(network, 0) + clicks
        by_channel[channel] = by_channel.get(channel, 0) + clicks
        for day, count in (item.get("days") or {}).items():
            if cutoff is None or str(day) >= cutoff:
                by_day[str(day)] = by_day.get(str(day), 0) + int(count or 0)
        links.append(
            {
                "code": item.get("code"),
                "channel": channel,
                "network": network,
                "label": item.get("label") or "",
                "target": item.get("target") or "",
                "clicks": clicks,
                "last_click": item.get("last_click") or "",
            }
        )
    links.sort(key=lambda entry: (-entry["clicks"], str(entry["code"])))
    return {
        "days": days,
        "total_clicks": total,
        "links": links,
        "by_network": dict(sorted(by_network.items(), key=lambda kv: -kv[1])),
        "by_channel": dict(sorted(by_channel.items(), key=lambda kv: -kv[1])),
        "by_day": dict(sorted(by_day.items())),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def render_markdown(report: Dict[str, Any]) -> str:
    period = f"за {report['days']} дн." if report.get("days") else "за всё время"
    lines = [
        f"# Клики по партнёрским ссылкам {period}",
        "",
        f"Всего кликов: **{report['total_clicks']}** · ссылок: {len(report['links'])} · "
        f"отчёт: {report['generated_at']}",
        "",
    ]
    if report.get("by_network"):
        lines.append("## По сетям")
        lines.append("")
        lines.append("| Сеть | Клики |")
        lines.append("|---|---|")
        for network, clicks in report["by_network"].items():
            lines.append(f"| {network} | {clicks} |")
        lines.append("")
    if report.get("by_channel"):
        lines.append("## По каналам")
        lines.append("")
        lines.append("| Канал | Клики |")
        lines.append("|---|---|")
        for channel, clicks in report["by_channel"].items():
            lines.append(f"| {channel} | {clicks} |")
        lines.append("")
    if report.get("links"):
        lines.append("## Ссылки")
        lines.append("")
        lines.append("| Код | Канал | Сеть | Клики | Последний клик |")
        lines.append("|---|---|---|---|---|")
        for link in report["links"]:
            lines.append(
                f"| {link['code']} | {link['channel']} | {link['network']} | "
                f"{link['clicks']} | {link['last_click'] or '—'} |"
            )
        lines.append("")
    else:
        lines.append("Нет кликов за выбранный период.")
        lines.append("")
    lines.append(
        "> Клики — только переходы по нашим ссылкам. Регистрации/депозиты/покупки и комиссии "
        "брать в кабинетах программ (BingX/Travelpayouts/MyLead и т.д.), тут их нет."
    )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    from content_factory.utils import load_dotenv

    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Отчёт по кликам партнёрских ссылок")
    parser.add_argument("--days", type=int, default=0, help="Период в днях (0 = всё время)")
    parser.add_argument("--json", action="store_true", help="JSON вместо markdown")
    parser.add_argument("--out", default="", help="Файл для markdown/JSON")
    parser.add_argument("--min-clicks", type=int, default=0, help="Скрыть ссылки с меньшим числом кликов")
    args = parser.parse_args(argv)
    try:
        data = fetch_stats()
        report = build_report(data, days=args.days or None, min_clicks=args.min_clicks)
    except RuntimeError as exc:
        print(f"Affiliate report: {exc}")
        return 1
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_markdown(report)
    if args.out:
        path = Path(args.out)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        print(f"Сохранено: {path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
