#!/usr/bin/env python3
"""Недельный отчёт по Fediverse: Mastodon + Akkoma + трекер ссылок.

Примеры:
    python scripts/fediverse_stats.py                 # markdown-отчёт в data/reports/
    python scripts/fediverse_stats.py --json          # JSON в stdout
    python scripts/fediverse_stats.py --limit 30      # больше постов на анализ

Источники: MASTODON_BASE_URL/MASTODON_TOKEN, AKKOMA_BASE_URL/AKKOMA_TOKEN,
LINK_TRACKER_BASE/LINK_TRACKER_STATS_TOKEN (все опциональны).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.utils import load_dotenv  # noqa: E402

UA = {"User-Agent": "content-factory-stats/1.0", "Accept": "application/json"}
DEFAULT_LIMIT = 20


def strip_html(text: str) -> str:
    value = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _get(url: str, token: str = "", timeout: float = 25.0) -> Any:
    headers = dict(UA)
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError("HTTP {}: {}".format(exc.code, detail)) from exc


def _fediverse_account(base: str, token: str) -> Optional[Dict[str, Any]]:
    if not base or not token:
        return None
    base = base.rstrip("/")
    try:
        account = _get(base + "/api/v1/accounts/verify_credentials", token)
        statuses = _get(
            base + "/api/v1/accounts/{}/statuses?limit={}&exclude_replies=false".format(
                account.get("id", ""), DEFAULT_LIMIT
            ),
            token,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    if not isinstance(statuses, list):
        statuses = []
    posts: List[Dict[str, Any]] = []
    for status in statuses:
        if status.get("reblog"):
            continue
        posts.append(
            {
                "id": status.get("id"),
                "url": status.get("url") or status.get("uri"),
                "created_at": status.get("created_at"),
                "text": strip_html(status.get("content") or "")[:300],
                "favourites": int(status.get("favourites_count") or 0),
                "reblogs": int(status.get("reblogs_count") or 0),
                "replies": int(status.get("replies_count") or 0),
            }
        )
    posts.sort(key=lambda item: item["favourites"] + item["reblogs"] + item["replies"], reverse=True)
    return {
        "base": base,
        "acct": account.get("acct"),
        "display_name": account.get("display_name"),
        "followers": int(account.get("followers_count") or 0),
        "following": int(account.get("following_count") or 0),
        "statuses": int(account.get("statuses_count") or 0),
        "posts": posts,
    }


def _tracker_stats(base: str, token: str) -> Optional[Dict[str, Any]]:
    if not base or not token:
        return None
    base = base.rstrip("/")
    try:
        data = _get(base + "/stats?token=" + urllib.parse.quote(token))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    links = data.get("links") or []
    total = sum(int(link.get("total") or 0) for link in links)
    return {"base": base, "links": links, "total_clicks": total}


def build_report(
    mastodon: Optional[Dict[str, Any]],
    akkoma: Optional[Dict[str, Any]],
    tracker: Optional[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    lines = ["# Fediverse: недельный отчёт ({})".format(now.strftime("%Y-%m-%d")), ""]
    lines.append("## Аккаунты")
    lines.append("")
    lines.append("| Аккаунт | Подписчики | Подписки | Постов |")
    lines.append("|---|---:|---:|---:|")
    for label, data in (("Mastodon", mastodon), ("Akkoma", akkoma)):
        if not data:
            lines.append("| {} | — | — | — |".format(label))
            continue
        if data.get("error"):
            lines.append("| {} | ошибка: {} | | |".format(label, str(data["error"])[:80]))
            continue
        lines.append(
            "| {} (@{}) | {} | {} | {} |".format(
                label, data.get("acct", ""), data.get("followers", 0), data.get("following", 0), data.get("statuses", 0)
            )
        )
    lines.append("")
    for label, data in (("Mastodon", mastodon), ("Akkoma", akkoma)):
        if not data or data.get("error") or not data.get("posts"):
            continue
        lines.append("## Топ постов: {}".format(label))
        lines.append("")
        lines.append("| Пост | ❤ | 🔁 | 💬 | Сумма |")
        lines.append("|---|---:|---:|---:|---:|")
        for post in data["posts"][:5]:
            score = post["favourites"] + post["reblogs"] + post["replies"]
            url = post.get("url") or ""
            label_text = (post.get("text") or "").replace("|", "/")[:70]
            lines.append(
                "| [{}]({}) | {} | {} | {} | {} |".format(
                    label_text, url, post["favourites"], post["reblogs"], post["replies"], score
                )
            )
        lines.append("")
    if tracker and not tracker.get("error"):
        lines.append("## Клики по трекаемым ссылкам")
        lines.append("")
        lines.append("| Код | Сеть | Клики |")
        lines.append("|---|---|---:|")
        for link in sorted(tracker.get("links") or [], key=lambda item: int(item.get("total") or 0), reverse=True):
            lines.append(
                "| {} | {} | {} |".format(link.get("code", ""), link.get("network", ""), link.get("total", 0))
            )
        lines.append("")
        lines.append("Всего кликов: **{}**".format(tracker.get("total_clicks", 0)))
        lines.append("")
    lines.append("_Сгенерировано автоматически: scripts/fediverse_stats.py_")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fediverse stats (Mastodon + Akkoma + tracker)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--out", default="")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    load_dotenv(ROOT / ".env")
    mastodon = _fediverse_account(
        os.environ.get("MASTODON_BASE_URL", ""), os.environ.get("MASTODON_TOKEN", "")
    )
    akkoma = _fediverse_account(
        os.environ.get("AKKOMA_BASE_URL", ""), os.environ.get("AKKOMA_TOKEN", "")
    )
    tracker = _tracker_stats(
        os.environ.get("LINK_TRACKER_BASE", ""), os.environ.get("LINK_TRACKER_STATS_TOKEN", "")
    )
    now = datetime.now(timezone.utc)
    report = build_report(mastodon, akkoma, tracker, now=now)
    if args.json:
        payload = {"generated_at": now.isoformat(), "mastodon": mastodon, "akkoma": akkoma, "tracker": tracker}
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 0
    out = Path(args.out) if args.out else ROOT / "data" / "reports" / "fediverse-stats-{}.md".format(now.strftime("%Y-%m-%d"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print("saved:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
