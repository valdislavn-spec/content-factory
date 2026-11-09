"""Инструменты операционного агента: компактные, безопасные, без LLM-вызовов.

Каждый инструмент возвращает небольшой dict/list — агент платит токенами
только за сжатые факты. Внешние действия (постинг, промо) не выполняются:
агент только читает и предлагает, отправка сводки — отдельный шаг runner'а.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..analytics.preview import PreviewError, fetch_preview
from ..config import Settings, load_network_channels
from ..utils import env

ROOT = Path(__file__).resolve().parents[2]


def _mask(value: str) -> str:
    return (value or "")[:6] + "…" if value else ""


def _usernames() -> Dict[str, str]:
    path = ROOT / "data" / "analytics" / "growth" / "usernames.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError):
        return {}


def tool_channels(_args: Dict[str, Any]) -> List[Dict[str, Any]]:
    settings = Settings.load()
    usernames = _usernames()
    rows = []
    for channel in load_network_channels(settings):
        if not channel.enabled:
            continue
        chat_id = str(channel.telegram_chat_id or "").strip()
        username = (
            chat_id.lstrip("@") if chat_id.startswith("@") else usernames.get(chat_id, "")
        ) or ""
        rows.append(
            {
                "id": channel.id,
                "title": channel.title,
                "lang": channel.language,
                "per_day": channel.posts_per_day,
                "username": username,
            }
        )
    return rows


def tool_growth(args: Dict[str, Any]) -> Dict[str, Any]:
    """Запускает growth_report без отправки и отдаёт последние строки сводки."""
    limit = int(args.get("limit") or 10)
    cmd = [sys.executable, str(ROOT / "scripts" / "growth_report.py"), "--quiet", "--limit", str(limit)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": type(exc).__name__}
    summary = (result.stderr or "").strip().splitlines()
    return {"ok": result.returncode == 0, "summary": "\n".join(summary[-14:])[:1400]}


def tool_channel_preview(args: Dict[str, Any]) -> Dict[str, Any]:
    username = str(args.get("username") or "").strip()
    if not username:
        return {"error": "username required"}
    try:
        preview = fetch_preview(username, timeout=20, limit=5)
    except PreviewError as exc:
        return {"error": str(exc)[:160]}
    return {
        "title": preview.title,
        "subscribers": preview.subscribers,
        "posts": [
            {"views": post.views, "reactions": post.reactions, "date": post.published_at}
            for post in preview.posts[-3:]
        ],
    }


def tool_health(_args: Dict[str, Any]) -> Dict[str, Any]:
    import urllib.request

    token = env("GITHUB_TOKEN", "") or env("GH_TOKEN", "") or ""
    if not token:
        return {"error": "no GitHub token"}
    url = "https://api.github.com/repos/valdislavn-spec/content-factory/actions/runs?per_page=6"
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + token, "User-Agent": "content-factory-ops-agent"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            runs = json.load(response).get("workflow_runs") or []
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}
    return [
        {"name": run.get("name"), "status": run.get("conclusion") or run.get("status"),
         "at": (run.get("created_at") or "")[:16]}
        for run in runs[:6]
    ]


def tool_budget(_args: Dict[str, Any]) -> Dict[str, Any]:
    usage: Dict[str, Any] = {}
    for path in sorted((ROOT / "data").glob("llm_usage*.json")):
        try:
            usage[path.stem.replace("llm_usage_", "") or "total"] = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
    try:
        tokens = json.loads((ROOT / "data" / "llm_tokens.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tokens = {}
    return {"usage": usage, "tokens": tokens}


DISTRIBUTION_WORKFLOWS = (
    ("mastodon-daily", "Mastodon"),
    ("fediverse-mix", "Fediverse"),
    ("reddit-digest", "Reddit"),
    ("tumblr-digest", "Tumblr"),
    ("pins-generate", "Pinterest"),
    ("vp-outreach", "ВП-аутрич"),
)


def tool_distribution(_args: Dict[str, Any]) -> Dict[str, Any]:
    """Статус бесплатных площадок дистрибуции по последним запускам Actions."""
    import urllib.request

    token = env("GITHUB_TOKEN", "") or env("GH_TOKEN", "") or ""
    if not token:
        return {"error": "no GitHub token"}
    base = "https://api.github.com/repos/valdislavn-spec/content-factory/actions/workflows/"
    rows: List[Dict[str, Any]] = []
    for filename, platform in DISTRIBUTION_WORKFLOWS:
        url = base + filename + ".yml/runs?per_page=3"
        request = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer " + token, "User-Agent": "content-factory-ops-agent"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                runs = json.load(response).get("workflow_runs") or []
        except Exception as exc:  # noqa: BLE001
            rows.append({"platform": platform, "last": "error:" + type(exc).__name__})
            continue
        if not runs:
            rows.append({"platform": platform, "last": "no runs"})
            continue
        last = runs[0]
        rows.append(
            {
                "platform": platform,
                "last": last.get("conclusion") or last.get("status"),
                "at": (last.get("created_at") or "")[5:16],
                "ok_of_3": sum(1 for run in runs if run.get("conclusion") == "success"),
            }
        )
    healthy = ("success", "queued", "in_progress", "waiting", "requested", None)
    failing = [row["platform"] for row in rows if row.get("last") not in healthy]
    return {"platforms": rows, "failing": failing}


def tool_promo(_args: Dict[str, Any]) -> Dict[str, Any]:
    path = ROOT / "docs" / "promo" / "outreach-tracker.csv"
    rows: List[Dict[str, str]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        pass
    statuses: Dict[str, int] = {}
    for row in rows:
        key = (row.get("status") or "unknown").strip().lower()
        statuses[key] = statuses.get(key, 0) + 1
    catalog = ROOT / "docs" / "promo" / "catalog-package.md"
    return {
        "outreach_rows": len(rows),
        "statuses": statuses,
        "catalog_package": catalog.is_file(),
        "vp_guide": (ROOT / "docs" / "promo" / "vp-outreach.md").is_file(),
    }


def tool_notes_search(args: Dict[str, Any]) -> List[str]:
    query = str(args.get("query") or "").strip().lower()
    if len(query) < 3:
        return []
    hits: List[str] = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        if path.name.startswith(("huggingface", "free-cloud")):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            if query in line.lower():
                hits.append("%s:%s %s" % (path.relative_to(ROOT), number, line.strip()[:130]))
                if len(hits) >= 8:
                    return hits
    return hits


TOOLS: Dict[str, Dict[str, Any]] = {
    "channels": {
        "fn": tool_channels,
        "desc": "Список каналов сети: id, title, lang, постов/день, @username.",
    },
    "growth": {
        "fn": tool_growth,
        "desc": "Свежие метрики роста: подписчики, просмотры/пост, ER, посты. args: {limit}.",
    },
    "preview": {
        "fn": tool_channel_preview,
        "desc": "Публичное превью канала: подписчики и последние 3 поста. args: {username}.",
    },
    "health": {
        "fn": tool_health,
        "desc": "Последние запуски GitHub Actions контент-завода.",
    },
    "budget": {
        "fn": tool_budget,
        "desc": "Расход LLM-запросов/токенов за сутки по провайдерам.",
    },
    "promo": {
        "fn": tool_promo,
        "desc": "Статус ВП-трекера и пакета каталогов.",
    },
    "distribution": {
        "fn": tool_distribution,
        "desc": "Статус бесплатных площадок (Mastodon/Reddit/Tumblr/Pinterest/ВП): последние запуски.",
    },
    "notes": {
        "fn": tool_notes_search,
        "desc": "Поиск по документации репозитория. args: {query}.",
    },
}


def call_tool(name: str, args: Dict[str, Any] | None = None) -> Any:
    tool = TOOLS.get(name)
    if not tool:
        return {"error": "unknown tool: %s" % name}
    try:
        return tool["fn"](args or {})
    except Exception as exc:  # noqa: BLE001 - агент должен продолжать работу
        return {"error": type(exc).__name__ + ": " + str(exc)[:120]}


def tools_prompt() -> str:
    return "\n".join("- %s: %s" % (name, item["desc"]) for name, item in TOOLS.items())
