"""Аналитика роста каналов: снимки публичного превью, дельты, отчёты.

Идея: раз в сутки снимаем публичную страницу каждого канала
(``t.me/s/<username>`` — см. :mod:`.preview`), сохраняем снимок в
``data/analytics/growth/history.jsonl`` и сравниваем с предыдущим:
подписчики, просмотры на пост, ER (реакции/просмотры), посты за 24 часа.

Модуль не делает сетевых запросов сам — данные передаются готовыми
(:class:`~content_factory.analytics.preview.PreviewChannel`), поэтому
логика тестируется без сети. Сеть — в ``scripts/growth_report.py``.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..config import Settings
from ..models import ChannelConfig
from .preview import PreviewChannel

GROWTH_SUBDIR = ("analytics", "growth")
HISTORY_FILE = "history.jsonl"
USERNAMES_FILE = "usernames.json"
WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# Хранилище снимков
# ---------------------------------------------------------------------------


def growth_dir(settings: Settings) -> Path:
    return settings.data_dir.joinpath(*GROWTH_SUBDIR)


def history_path(settings: Settings) -> Path:
    return growth_dir(settings) / HISTORY_FILE


def usernames_path(settings: Settings) -> Path:
    """Кэш «канал → @username» (IDs в конфиге числовые, превью — по username)."""
    return growth_dir(settings) / USERNAMES_FILE


def load_previous_snapshot(path: Path) -> Optional[Dict[str, Any]]:
    """Последний снимок из истории (JSONL) или None, если истории нет/битая."""
    if not path.is_file():
        return None
    last: Optional[Dict[str, Any]] = None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    last = parsed
    except OSError:
        return None
    return last


def append_snapshot(path: Path, snapshot: Dict[str, Any]) -> None:
    """Дописывает снимок в JSONL-историю (создаёт каталоги)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def load_username_cache(path: Path) -> Dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if value}


def save_username_cache(path: Path, cache: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Построение снимка
# ---------------------------------------------------------------------------


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _previous_by_id(previous: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    if not isinstance(previous, dict):
        return result
    for row in previous.get("channels") or []:
        if isinstance(row, dict) and row.get("id"):
            result[str(row["id"])] = row
    return result


def _mean(values: Iterable[float]) -> Optional[float]:
    values = [float(value) for value in values]
    if not values:
        return None
    return sum(values) / len(values)


def _channel_row(
    channel: ChannelConfig,
    preview: Optional[PreviewChannel],
    error: str,
    *,
    now: datetime,
    previous_row: Optional[Dict[str, Any]],
    limit: int,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": channel.id,
        "title": channel.title,
        "language": channel.language,
        "username": preview.username if preview else "",
        "status": "ok",
        "error": "",
        "subscribers": None,
        "subscribers_delta": None,
        "posts_shown": 0,
        "posts_24h": 0,
        "avg_views": None,
        "max_views": None,
        "reactions_per_post": None,
        "engagement_rate": None,
        "views_per_subscriber": None,
        "last_post_at": None,
        "top_post": None,
        # внутренние суммы нужны для сетевого ER; в снимок не попадают
        "_views_sum": 0.0,
        "_reactions_sum": 0.0,
        "_sample": 0,
    }
    if preview is None:
        row["status"] = "no_data"
        row["error"] = error or "нет данных превью"
        return row

    dated = [(post, _parse_dt(post.published_at)) for post in preview.posts]
    dated = [(post, moment) for post, moment in dated if post.views is not None and moment is not None]
    dated.sort(key=lambda pair: pair[1])
    row["posts_shown"] = len(dated)

    window_start = now - timedelta(hours=WINDOW_HOURS)
    recent = [(post, moment) for post, moment in dated if moment >= window_start]
    sample = recent if len(recent) >= 3 else dated[-limit:]
    row["posts_24h"] = len(recent)

    if preview.subscribers is not None:
        row["subscribers"] = preview.subscribers
        previous_subscribers = (previous_row or {}).get("subscribers")
        if isinstance(previous_subscribers, int) and previous_subscribers >= 0:
            row["subscribers_delta"] = preview.subscribers - previous_subscribers

    if sample:
        views = [post.views or 0 for post, _ in sample]
        reactions = [post.reactions for post, _ in sample]
        avg_views = _mean(views) or 0.0
        row["avg_views"] = int(round(avg_views))
        row["max_views"] = max(views)
        row["reactions_per_post"] = round(sum(reactions) / len(reactions), 1)
        total_views = sum(views)
        total_reactions = sum(reactions)
        row["_views_sum"] = float(total_views)
        row["_reactions_sum"] = float(total_reactions)
        row["_sample"] = len(sample)
        if total_views:
            row["engagement_rate"] = round(total_reactions / total_views, 4)
        if preview.subscribers:
            row["views_per_subscriber"] = round(avg_views / preview.subscribers, 4)
        row["last_post_at"] = sample[-1][1].isoformat()
        top_post, top_moment = max(sample, key=lambda pair: pair[0].views or 0)
        row["top_post"] = {
            "url": top_post.post_url,
            "views": top_post.views,
            "reactions": top_post.reactions,
            "date": top_moment.isoformat(),
            "text": top_post.snippet,
        }
    elif preview.subscribers is not None:
        previous_subscribers = (previous_row or {}).get("subscribers")
        if isinstance(previous_subscribers, int) and previous_subscribers >= 0:
            row["subscribers_delta"] = preview.subscribers - previous_subscribers
    return row


def build_snapshot(
    channels: Sequence[ChannelConfig],
    previews: Dict[str, PreviewChannel],
    *,
    now: Optional[datetime] = None,
    previous: Optional[Dict[str, Any]] = None,
    errors: Optional[Dict[str, str]] = None,
    subscribers: Optional[Dict[str, int]] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Собирает снимок роста по каналам и сравнивает с предыдущим.

    ``previews`` — словарь ``channel.id → PreviewChannel``; ``errors`` —
    ``channel.id → текст ошибки`` для каналов, у которых превью не получено;
    ``subscribers`` — точные значения из Bot API (перекрывают округлённые
    «3.67K» из превью и спасают отчёт, если t.me недоступен).
    """
    now = now or datetime.now(timezone.utc)
    errors = errors or {}
    subscribers = subscribers or {}
    previous_rows = _previous_by_id(previous)
    rows = [
        _channel_row(
            channel,
            previews.get(channel.id),
            errors.get(channel.id, ""),
            now=now,
            previous_row=previous_rows.get(channel.id),
            limit=limit,
        )
        for channel in channels
    ]
    # Точные подписчики из Bot API важнее округлённых из превью.
    for row in rows:
        override = subscribers.get(row["id"])
        if isinstance(override, int) and not isinstance(override, bool) and override >= 0:
            if row["subscribers"] != override:
                row["subscribers"] = override
                previous_subscribers = (previous_rows.get(row["id"]) or {}).get("subscribers")
                if isinstance(previous_subscribers, int) and previous_subscribers >= 0:
                    row["subscribers_delta"] = override - previous_subscribers
            if row["status"] == "no_data":
                row["status"] = "subscribers_only"

    subscribers = [row["subscribers"] for row in rows if isinstance(row["subscribers"], int)]
    deltas = [row["subscribers_delta"] for row in rows if isinstance(row["subscribers_delta"], int)]
    total_views = sum(row["_views_sum"] for row in rows)
    total_reactions = sum(row["_reactions_sum"] for row in rows)
    sample_size = sum(row["_sample"] for row in rows)
    if sample_size:
        totals_avg_views: Optional[int] = int(round(total_views / sample_size))
    else:
        totals_avg_views = None

    snapshot: Dict[str, Any] = {
        "generated_at": now.isoformat(),
        "generated_at_utc": now.strftime("%d.%m %H:%M") + " UTC",
        "previous_at": (previous or {}).get("generated_at"),
        "window_hours": WINDOW_HOURS,
        "channels": rows,
        "totals": {
            "channels": len(rows),
            "previewed": sum(1 for row in rows if row["status"] == "ok"),
            "subscribers": sum(subscribers) if subscribers else None,
            "subscribers_delta": sum(deltas) if deltas else None,
            "posts_24h": sum(row["posts_24h"] for row in rows),
            "avg_views": totals_avg_views,
            "engagement_rate": round(total_reactions / total_views, 4) if total_views else None,
        },
        "notes": [],
    }
    for row in rows:
        for key in ("_views_sum", "_reactions_sum", "_sample"):
            row.pop(key, None)
    unavailable = [row for row in rows if row["status"] != "ok"]
    if unavailable:
        snapshot["notes"].append(
            "нет превью (просмотры/ER): "
            + ", ".join(row["id"] for row in unavailable)
        )
    return snapshot


# ---------------------------------------------------------------------------
# Форматирование
# ---------------------------------------------------------------------------


def _num(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return "{:,}".format(int(value)).replace(",", "\u2009")


def _signed(value: Optional[int]) -> str:
    if value is None:
        return ""
    if value > 0:
        return " (+{})".format(_num(value))
    if value < 0:
        return " (−{})".format(_num(abs(value)))
    return " (+0)"


def _percent(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return "{:.0f}%".format(value * 100)


def _channel_handle(row: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    """@username канала: из превью или из резолва Bot API (snapshot["usernames"])."""
    username = row.get("username") or (snapshot.get("usernames") or {}).get(row["id"], "")
    return "@" + username if username else str(row["id"])


def _channel_at(row: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    """@username для таблицы отчёта или «—», если он неизвестен."""
    handle = _channel_handle(row, snapshot)
    return handle if handle.startswith("@") else "—"


def format_telegram(snapshot: Dict[str, Any], *, max_chars: int = 3900) -> str:
    """Короткое сообщение для Telegram: одна-две строки на канал."""
    totals = snapshot.get("totals") or {}
    lines: List[str] = [
        "📊 Рост каналов · {}".format(snapshot.get("generated_at_utc", "")),
        "Всего: {} подп.{} · {} постов/24ч · ER {}".format(
            _num(totals.get("subscribers")),
            _signed(totals.get("subscribers_delta")),
            _num(totals.get("posts_24h")),
            _percent(totals.get("engagement_rate")),
        ),
    ]
    for row in snapshot.get("channels") or []:
        handle = _channel_handle(row, snapshot)
        head = "• {} {} — {} подп.{}".format(
            row.get("title") or row["id"],
            handle,
            _num(row.get("subscribers")),
            _signed(row.get("subscribers_delta")),
        )
        if row.get("status") != "ok":
            if row.get("status") == "subscribers_only" and row.get("subscribers") is not None:
                lines.append(head + " · только подписчики (превью недоступно)")
            else:
                lines.append(head + " · нет данных")
            continue
        detail = "  просм ~{}/пост · ER {} · {} постов/24ч".format(
            _num(row.get("avg_views")),
            _percent(row.get("engagement_rate")),
            _num(row.get("posts_24h")),
        )
        lines.append(head + "\n" + detail)
    notes = snapshot.get("notes") or []
    if notes:
        lines.append("⚠ " + "; ".join(notes))
    text = "\n".join(lines)
    return text[:max_chars]


def format_markdown(snapshot: Dict[str, Any]) -> str:
    """Подробный Markdown-отчёт (сохраняется в data/reports)."""
    totals = snapshot.get("totals") or {}
    lines: List[str] = [
        "# Рост каналов — {}".format(snapshot.get("generated_at_utc", "")),
        "",
        "- Подписчики: **{}**{}".format(
            _num(totals.get("subscribers")), _signed(totals.get("subscribers_delta"))
        ),
        "- Постов за 24 часа: **{}**".format(_num(totals.get("posts_24h"))),
        "- Средние просмотры на пост: **{}**".format(_num(totals.get("avg_views"))),
        "- ER (реакции/просмотры): **{}**".format(_percent(totals.get("engagement_rate"))),
        "",
        "| Канал | @ | Подписчики | Δ сутки | Просм/пост | ER | Постов/24ч |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in snapshot.get("channels") or []:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                row.get("title") or row["id"],
                _channel_at(row, snapshot),
                _num(row.get("subscribers")),
                _signed(row.get("subscribers_delta")).strip() or "—",
                _num(row.get("avg_views")),
                _percent(row.get("engagement_rate")),
                _num(row.get("posts_24h")),
            )
        )
    lines.append("")
    lines.append("## Лучшие посты за окно")
    for row in snapshot.get("channels") or []:
        top = row.get("top_post")
        if not top:
            continue
        lines.append(
            "- **{}**: {} просм., {} реакц. — [{}]({})".format(
                row.get("title") or row["id"],
                _num(top.get("views")),
                _num(top.get("reactions")),
                top.get("text") or "пост",
                top.get("url") or "",
            )
        )
    notes = snapshot.get("notes") or []
    if notes:
        lines += ["", "## Замечания"] + ["- " + note for note in notes]
    lines += [
        "",
        "> Просмотры и реакции — с публичной страницы t.me/s; Telegram может",
        "> показывать их с задержкой. Bot API отдаёт только число подписчиков.",
    ]
    return "\n".join(lines) + "\n"
