#!/usr/bin/env python3
"""Сканирование каналов-кандидатов для ВП по публичному t.me/s.

Запускать там, где доступен t.me (GitHub Actions); локально будет PreviewError.
Критерии по умолчанию: просмотры/пост 100–800, ≥1 пост/24ч, последний пост не
старше 72 ч, без явных признаков накрутки реакций.

Примеры:
    python scripts/partner_scan.py --file docs/promo/partner-candidates.txt
    python scripts/partner_scan.py --users @chan1,@chan2 --min-views 100 --max-views 800

Пишет data/reports/partner-scan-YYYY-MM-DD.md и .json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.analytics.growth import _parse_dt
from content_factory.analytics.preview import PreviewError, fetch_preview, normalize_username


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Скан каналов-кандидатов для ВП/партнёрств")
    parser.add_argument("--file", default="", help="файл со списком @username (по одному в строке)")
    parser.add_argument("--users", default="", help="список каналов через запятую")
    parser.add_argument("--min-views", type=int, default=100, help="мин. средние просмотры/пост")
    parser.add_argument("--max-views", type=int, default=800, help="макс. средние просмотры/пост")
    parser.add_argument("--min-posts-24h", type=int, default=1, help="мин. постов за 24 ч")
    parser.add_argument("--max-age-hours", type=float, default=72.0, help="макс. возраст последнего поста")
    parser.add_argument("--timeout", type=float, default=20.0, help="таймаут запросов, сек")
    parser.add_argument("--out-dir", default="", help="каталог отчётов (по умолчанию data/reports)")
    return parser.parse_args(argv)


def load_candidates(args: argparse.Namespace) -> List[str]:
    names: List[str] = []
    if args.users:
        names += [part.strip() for part in args.users.split(",")]
    if args.file:
        path = Path(args.file)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    names.append(line)
        else:
            print("Файл не найден: %s" % path, file=sys.stderr)
    seen = set()
    result: List[str] = []
    for name in names:
        username = normalize_username(name)
        if username and username.lower() not in seen:
            seen.add(username.lower())
            result.append(username)
    return result


def scan(username: str, timeout: float) -> Dict[str, Any]:
    preview = fetch_preview(username, timeout=timeout, limit=30)
    now = datetime.now(timezone.utc)
    dated: List[Tuple[Any, datetime]] = []
    for post in preview.posts:
        moment = _parse_dt(post.published_at)
        if moment is not None and post.views is not None:
            dated.append((post, moment))
    dated.sort(key=lambda pair: pair[1])
    recent = [(post, moment) for post, moment in dated if (now - moment).total_seconds() <= 86400]
    sample = recent if len(recent) >= 3 else dated[-30:]
    views = [post.views for post, _ in sample]
    reactions = [post.reactions for post, _ in sample]
    single = sum(
        1
        for post, _ in sample
        if len([e for e, c in (post.reactions_detail or {}).items() if c]) == 1
        and post.reactions >= 20
    )
    avg = statistics.mean(views) if views else None
    er = (sum(reactions) / sum(views)) if views and sum(views) else None
    last_hours = (now - dated[-1][1]).total_seconds() / 3600 if dated else None
    return {
        "username": preview.username or username,
        "title": preview.title,
        "subscribers": preview.subscribers,
        "posts_in_preview": len(dated),
        "posts_24h": len(recent),
        "avg_views": round(avg) if avg is not None else None,
        "er": round(er, 3) if er is not None else None,
        "single_emoji_share": round(single / len(sample), 2) if sample else None,
        "last_post_age_hours": round(last_hours, 1) if last_hours is not None else None,
    }


def verdict(row: Dict[str, Any], args: argparse.Namespace) -> Tuple[bool, str]:
    if row.get("avg_views") is None:
        return False, "нет данных о просмотрах"
    if not (args.min_views <= row["avg_views"] <= args.max_views):
        return False, "просмотры %s вне %d–%d" % (row["avg_views"], args.min_views, args.max_views)
    if row["posts_24h"] < args.min_posts_24h:
        return False, "мало постов/24ч (%s)" % row["posts_24h"]
    age = row.get("last_post_age_hours")
    if age is None or age > args.max_age_hours:
        return False, "канал неактивен"
    if row.get("single_emoji_share") and row["single_emoji_share"] >= 0.8:
        return False, "похоже на накрутку реакций"
    return True, ""


def render_markdown(
    passed: List[Dict[str, Any]], rejected: List[Dict[str, Any]], args: argparse.Namespace
) -> str:
    lines = [
        "# Скан каналов-кандидатов для ВП — %s" % datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
        "",
        "Критерии: просмотры/пост %d–%d, ≥%d постов/24ч, последний пост не старше %d ч."
        % (args.min_views, args.max_views, args.min_posts_24h, int(args.max_age_hours)),
        "",
        "| Канал | @ | Подписчики | Просм/пост | ER | Постов/24ч | Пост, ч назад |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in passed:
        er = "%d%%" % round((row["er"] or 0) * 100)
        lines.append(
            "| %s | @%s | %s | %s | %s | %s | %s |"
            % (
                row.get("title") or "—",
                row["username"],
                row.get("subscribers") if row.get("subscribers") is not None else "—",
                row["avg_views"],
                er,
                row["posts_24h"],
                row.get("last_post_age_hours"),
            )
        )
    lines.append("")
    if rejected:
        lines.append("## Отсеяны")
        for item in rejected:
            lines.append("- @%s — %s" % (item["username"], item["reason"]))
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    candidates = load_candidates(args)
    if not candidates:
        print("Нет кандидатов: передайте --users или --file", file=sys.stderr)
        return 2
    passed: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for username in candidates:
        try:
            row = scan(username, args.timeout)
        except PreviewError as exc:
            rejected.append({"username": username, "reason": "превью недоступно: %s" % exc})
            continue
        ok, reason = verdict(row, args)
        if ok:
            passed.append(row)
        else:
            row["reason"] = reason
            rejected.append(row)
    passed.sort(key=lambda row: -(row.get("avg_views") or 0))
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "data" / "reports"
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    markdown = render_markdown(passed, rejected, args)
    (out_dir / ("partner-scan-%s.md" % stamp)).write_text(markdown, encoding="utf-8")
    (out_dir / ("partner-scan-%s.json" % stamp)).write_text(
        json.dumps({"passed": passed, "rejected": rejected}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(markdown)
    print("Кандидатов прошло: %d, отсеяно: %d" % (len(passed), len(rejected)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
