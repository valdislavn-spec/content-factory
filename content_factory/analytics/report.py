"""Аналитический отчёт: данные, самодостаточный HTML и Markdown.

HTML-отчёт не использует интернет: CSS встроен в <style>, картинок и внешних
скриптов нет, поэтому файл открывается в браузере офлайн и в России без VPN.
Отчёт строится и на пустой базе (нулевые значения + подсказка про demo).

Основной файл: data/reports/report.html, рядом — report.md.
"""
from __future__ import annotations

import html as html_lib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..config import Settings
from ..models import ChannelConfig, utcnow
from ..storage import Storage
from ..utils import (
    atomic_write_text,
    ensure_dir,
    format_iso,
    format_local,
    html_escape,
    parse_datetime,
)
from .collector import top_sources_from_posts, top_terms_from_posts

logger = logging.getLogger(__name__)

_FORMAT_LABELS = {
    "story": "Сюжет",
    "digest": "Дайджест",
    "analysis": "Анализ",
}
_LLM_LABELS = {
    "extractive": "Встроенная суммаризация (extractive, без LLM)",
    "ollama": "Ollama — локальная языковая модель",
    "openai_compatible": "OpenAI-совместимый локальный сервер",
    "gigachat": "GigaChat (Сбер)",
    "yandexgpt": "YandexGPT",
    "dify": "Dify Cloud (приложение)",
}

_REPORT_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f3f5f9; --card: #ffffff; --text: #1b2430; --muted: #5d6a7a;
  --accent: #2563a8; --accent-soft: #dbe8f7; --border: #dde3ec;
  --track: #e8edf4; --ok: #1d7a4d; --err: #b3261e; --warn-bg: #fff3d1;
  --warn-text: #745000;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f141c; --card: #19212e; --text: #e7edf6; --muted: #9aa9bc;
    --accent: #7fb3ea; --accent-soft: #22344c; --border: #2a3548;
    --track: #263247; --ok: #5fd39a; --err: #ff8f86; --warn-bg: #3a2f12;
    --warn-text: #ffd479;
  }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 28px 14px 40px; background: var(--bg); color: var(--text);
       font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, "Noto Sans", sans-serif; }
.wrap { max-width: 1120px; margin: 0 auto; }
header { margin-bottom: 18px; }
h1 { font-size: 26px; margin: 0 0 6px; line-height: 1.25; }
h2 { font-size: 18px; margin: 30px 0 12px; color: var(--accent); }
.meta { color: var(--muted); font-size: 13.5px; margin: 2px 0; }
.mode { display: inline-block; margin-top: 8px; padding: 5px 12px; border-radius: 999px;
        font-size: 12.5px; font-weight: 700; letter-spacing: .03em;
        background: var(--accent-soft); color: var(--accent); }
.warn { margin: 14px 0; padding: 13px 16px; border-radius: 10px;
        background: var(--warn-bg); color: var(--warn-text); font-weight: 600; }
.hint { margin: 14px 0; padding: 14px 16px; border-radius: 10px;
        border: 1px dashed var(--accent); background: var(--accent-soft);
        color: var(--text); }
.hint code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
             background: var(--card); padding: 1px 5px; border-radius: 5px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
        padding: 14px 16px; box-shadow: 0 1px 4px rgba(20, 30, 45, .05); }
.card .label { color: var(--muted); font-size: 12.5px; text-transform: uppercase;
               letter-spacing: .04em; }
.card .num { font-size: 26px; font-weight: 700; margin-top: 4px; line-height: 1.15; }
.card .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
.table-wrap { overflow-x: auto; background: var(--card); border: 1px solid var(--border);
              border-radius: 12px; }
table { width: 100%; border-collapse: collapse; min-width: 560px; }
th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--border);
         font-size: 14px; vertical-align: top; }
th { color: var(--muted); font-size: 12.5px; text-transform: uppercase; letter-spacing: .03em;
     font-weight: 600; background: var(--accent-soft); }
tbody tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; white-space: nowrap; }
.bars { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
        padding: 16px; }
.bar-row { display: grid; grid-template-columns: 150px 1fr 52px; gap: 10px;
           align-items: center; margin: 8px 0; }
.bar-track { height: 12px; border-radius: 6px; background: var(--track); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 6px; background: var(--accent); }
.chips { line-height: 2.1; }
.chip { display: inline-block; margin: 0 6px 4px 0; padding: 4px 11px; border-radius: 999px;
        border: 1px solid var(--border); background: var(--card); font-size: 13px; }
.chip b { color: var(--accent); }
.ok { color: var(--ok); font-weight: 600; }
.err { color: var(--err); font-weight: 600; }
.muted { color: var(--muted); }
a { color: var(--accent); overflow-wrap: anywhere; }
.empty { color: var(--muted); font-style: italic; padding: 10px 14px; }
footer { margin-top: 34px; color: var(--muted); font-size: 12px; text-align: center; }
@media (max-width: 560px) {
  h1 { font-size: 22px; }
  .bar-row { grid-template-columns: 110px 1fr 44px; }
  th, td { padding: 8px 9px; font-size: 13px; }
}
"""


# ---------------------------------------------------------------------------
# форматирование
# ---------------------------------------------------------------------------
def _e(value: Any) -> str:
    """Экранирование текста для HTML."""
    return html_escape("" if value is None else str(value))


def _ea(value: Any) -> str:
    """Экранирование значения для HTML-атрибута."""
    return html_lib.escape("" if value is None else str(value), quote=True)


def _fmt_int(value: Any, empty: str = "0") -> str:
    if value is None:
        return empty
    try:
        return "{:,}".format(int(value)).replace(",", " ")
    except (TypeError, ValueError):
        return empty


def _fmt_float(value: Any) -> str:
    try:
        return "{:,.1f}".format(float(value)).replace(",", " ")
    except (TypeError, ValueError):
        return "0,0"


def _bar_width(value: int, maximum: int) -> int:
    if maximum <= 0 or value <= 0:
        return 0
    return max(3, int(round(100.0 * value / maximum)))


def _local(iso_value: Any, offset_hours: int = 3, with_time: bool = True) -> str:
    parsed = parse_datetime(iso_value)
    if parsed is None:
        return "—"
    return format_local(parsed, offset_hours, with_time=with_time) or "—"


def _tz_label(offset: int) -> str:
    if offset == 3:
        return "МСК (UTC+3)"
    sign = "+" if offset >= 0 else "−"
    return "UTC{}{}".format(sign, abs(offset))


def _format_label(key: str) -> str:
    return _FORMAT_LABELS.get(str(key).lower(), str(key))


def _publish_status(ok: bool, dry_run: bool) -> str:
    if dry_run:
        return "dry-run"
    return "успешно" if ok else "ошибка"


def _llm_info(settings: Settings) -> Dict[str, str]:
    provider = str(settings.llm.get("provider") or "extractive")
    model = ""
    section = settings.llm.get(provider)
    if isinstance(section, dict):
        model = str(section.get("model") or "")
    label = _LLM_LABELS.get(provider, provider)
    return {"provider": provider, "label": label, "model": model}


def _run_errors(run: Dict[str, Any]) -> List[str]:
    errors = run.get("errors") or []
    if isinstance(errors, str):
        return [errors] if errors else []
    return [str(item) for item in errors if str(item).strip()]


def _last_run_info(last_run: Optional[Dict[str, Any]], offset: int) -> Optional[Dict[str, Any]]:
    if not last_run:
        return None
    return {
        "started_at_local": _local(last_run.get("started_at"), offset),
        "duration_sec": float(last_run.get("duration_sec") or 0.0),
        "articles_new": int(last_run.get("articles_new") or 0),
        "posts_generated": int(last_run.get("posts_generated") or 0),
        "posts_published": int(last_run.get("posts_published") or 0),
        "errors": len(_run_errors(last_run)),
        "dry_run": bool(last_run.get("dry_run")),
    }


# ---------------------------------------------------------------------------
# сбор данных
# ---------------------------------------------------------------------------
def build_report(
    settings: Settings,
    storage: Storage,
    channels: Sequence[ChannelConfig],
    days: int = 7,
) -> Dict[str, Any]:
    """Собирает все данные для отчёта в один словарь (удобно тестировать)."""
    days = max(1, int(days))
    channels = list(channels)
    offset = settings.timezone_offset
    now = utcnow()

    per_channel: List[Dict[str, Any]] = []
    formats_total: Dict[str, int] = {}
    terms_counts: Dict[str, int] = {}
    errors: List[Dict[str, str]] = []

    totals_articles = totals_posts = 0
    publishes_total = {"total": 0, "ok": 0, "failed": 0, "dry_run": 0}
    subscribers_sum = 0
    subscribers_known = 0
    chars_weighted = 0.0
    channels_with_data = 0

    for channel in channels:
        stats: Dict[str, Any] = {}
        posts: List[Dict[str, Any]] = []
        latest: Optional[Dict[str, Any]] = None
        try:
            stats = storage.channel_stats(channel.id, days=days)
            posts = storage.get_posts(channel.id, days=days)
            latest = storage.latest_metrics(channel.id)
        except Exception as exc:  # noqa: BLE001 - один канал не должен ломать отчёт
            logger.exception("Отчёт: не удалось прочитать данные канала %s: %s", channel.id, exc)

        publishes = dict(stats.get("publishes") or {})
        channel_publishes = {
            "total": int(publishes.get("total") or 0),
            "ok": int(publishes.get("ok") or 0),
            "failed": int(publishes.get("failed") or 0),
            "dry_run": int(publishes.get("dry_run") or 0),
        }
        post_count = int(stats.get("posts") or 0)
        article_count = int(stats.get("articles") or 0)
        avg_chars = float(stats.get("avg_post_chars") or 0.0)
        channel_formats = {
            _format_label(str(key)): int(value)
            for key, value in (stats.get("formats") or {}).items()
        }
        for label, count in channel_formats.items():
            formats_total[label] = formats_total.get(label, 0) + count

        payload = (latest or {}).get("payload") or {}
        channel_terms = payload.get("top_terms") or top_terms_from_posts(posts)
        channel_sources = payload.get("top_sources") or top_sources_from_posts(posts)
        for item in channel_terms:
            term = str(item.get("term") or "").strip()
            if not term:
                continue
            terms_counts[term] = terms_counts.get(term, 0) + int(item.get("count") or 0)

        subscribers = (latest or {}).get("subscribers")
        subscribers_value: Optional[int] = None
        if isinstance(subscribers, int) and not isinstance(subscribers, bool):
            subscribers_value = int(subscribers)
            subscribers_sum += subscribers_value
            subscribers_known += 1

        last_run = _last_run_info(stats.get("last_run"), channel.timezone_offset)
        if last_run and last_run["errors"]:
            for message in _run_errors(stats["last_run"]):
                errors.append(
                    {
                        "channel_id": channel.id,
                        "channel_title": channel.title,
                        "when_local": last_run["started_at_local"],
                        "message": message,
                    }
                )

        if post_count or article_count:
            channels_with_data += 1
        totals_articles += article_count
        totals_posts += post_count
        for key in publishes_total:
            publishes_total[key] += channel_publishes[key]
        chars_weighted += avg_chars * post_count

        per_channel.append(
            {
                "id": channel.id,
                "title": channel.title,
                "description": channel.description,
                "enabled": channel.enabled,
                "schedule": "{} ({})".format(
                    ", ".join(channel.schedule), _tz_label(channel.timezone_offset)
                ),
                "timezone_offset": channel.timezone_offset,
                "articles": article_count,
                "posts": post_count,
                "avg_post_chars": round(avg_chars, 1),
                "publishes": channel_publishes,
                "subscribers": subscribers_value,
                "formats": channel_formats,
                "top_terms": channel_terms,
                "top_sources": channel_sources,
                "last_run": last_run,
            }
        )

    # Публикации и запуски (последние, по всем каналам)
    channel_titles = {channel.id: channel.title for channel in channels}
    publications: List[Dict[str, Any]] = []
    try:
        for row in storage.recent_publishes(days=days, limit=20):
            publications.append(
                {
                    "channel_id": row.get("channel_id", ""),
                    "channel_title": channel_titles.get(
                        str(row.get("channel_id", "")), str(row.get("channel_id", ""))
                    ),
                    "post_id": row.get("post_id", ""),
                    "publisher": row.get("publisher", ""),
                    "ok": bool(row.get("ok")),
                    "dry_run": bool(row.get("dry_run")),
                    "url": str(row.get("url") or ""),
                    "error": str(row.get("error") or ""),
                    "published_at_local": _local(row.get("published_at"), offset),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Отчёт: не удалось прочитать публикации: %s", exc)

    runs: List[Dict[str, Any]] = []
    try:
        for row in storage.recent_runs(days=days, limit=20):
            runs.append(
                {
                    "channel_id": row.get("channel_id", ""),
                    "channel_title": channel_titles.get(
                        str(row.get("channel_id", "")), str(row.get("channel_id", ""))
                    ),
                    "started_at_local": _local(row.get("started_at"), offset),
                    "duration_sec": float(row.get("duration_sec") or 0.0),
                    "articles_new": int(row.get("articles_new") or 0),
                    "posts_generated": int(row.get("posts_generated") or 0),
                    "posts_published": int(row.get("posts_published") or 0),
                    "errors": _run_errors(row),
                    "dry_run": bool(row.get("dry_run")),
                }
            )
            for message in _run_errors(row):
                errors.append(
                    {
                        "channel_id": str(row.get("channel_id", "")),
                        "channel_title": channel_titles.get(
                            str(row.get("channel_id", "")), str(row.get("channel_id", ""))
                        ),
                        "when_local": _local(row.get("started_at"), offset),
                        "message": message,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Отчёт: не удалось прочитать запуски: %s", exc)

    # Ошибки публикаций тоже попадают в отдельный блок.
    for publication in publications:
        if not publication["ok"] and publication["error"]:
            errors.append(
                {
                    "channel_id": publication["channel_id"],
                    "channel_title": publication["channel_title"],
                    "when_local": publication["published_at_local"],
                    "message": "публикация {}: {}".format(
                        publication["publisher"], publication["error"]
                    ),
                }
            )

    sources: List[Dict[str, Any]] = []
    try:
        sources = [
            {"source_name": str(row.get("source_name") or ""), "count": int(row.get("count") or 0)}
            for row in storage.article_sources(days=days, limit=15)
        ]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Отчёт: не удалось прочитать источники: %s", exc)

    top_terms = [
        {"term": term, "count": count}
        for term, count in sorted(terms_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:12]
    ]
    formats = dict(sorted(formats_total.items(), key=lambda pair: (-pair[1], pair[0])))
    publishes_totals = publishes_total
    total_posts = totals_posts
    avg_post_chars = round(chars_weighted / total_posts, 1) if total_posts else 0.0
    has_data = bool(totals_articles or total_posts or publishes_totals["total"])
    hint = ""
    if not has_data:
        hint = (
            "Данных пока нет. Запустите офлайн-демонстрацию: "
            "python -m content_factory demo — она создаст посты в data/outbox и этот отчёт "
            "без сети и токенов. Затем заполните .env и выполните "
            "python -m content_factory run --channel all."
        )

    return {
        "title": str(settings.analytics.get("report_title") or "Контент-завод: аналитика"),
        "generated_at": format_iso(now),
        "generated_at_local": format_local(now, offset),
        "days": days,
        "dry_run": settings.dry_run,
        "llm": _llm_info(settings),
        "totals": {
            "channels": len(channels),
            "channels_enabled": sum(1 for channel in channels if channel.enabled),
            "channels_with_data": channels_with_data,
            "articles": totals_articles,
            "posts": total_posts,
            "publishes": publishes_totals,
            "subscribers": subscribers_sum if subscribers_known else None,
            "subscribers_known_channels": subscribers_known,
            "avg_post_chars": avg_post_chars,
        },
        "per_channel": per_channel,
        "sources": sources,
        "formats": formats,
        "top_terms": top_terms,
        "publications": publications,
        "runs": runs,
        "errors": errors[:20],
        "has_data": has_data,
        "hint": hint,
    }


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def _summary_cards(data: Dict[str, Any]) -> str:
    totals = data["totals"]
    publishes = totals["publishes"]
    subscribers = totals["subscribers"]
    cards = [
        ("Каналы", _fmt_int(totals["channels"]), "включено: {}".format(totals["channels_enabled"])),
        ("Статьи", _fmt_int(totals["articles"]), "за {} дн.".format(data["days"])),
        ("Посты", _fmt_int(totals["posts"]), "средняя длина: {} симв.".format(_fmt_float(totals["avg_post_chars"]))),
        (
            "Публикации",
            _fmt_int(publishes["total"]),
            "успешно: {}, ошибок: {}, dry-run: {}".format(
                _fmt_int(publishes["ok"]), _fmt_int(publishes["failed"]), _fmt_int(publishes["dry_run"])
            ),
        ),
        (
            "Подписчики",
            _fmt_int(subscribers, "—") if subscribers is not None else "—",
            "каналов с данными: {}".format(totals["subscribers_known_channels"]),
        ),
    ]
    blocks = []
    for label, value, sub in cards:
        blocks.append(
            '<div class="card"><div class="label">{}</div>'
            '<div class="num">{}</div><div class="sub">{}</div></div>'.format(
                _e(label), _e(value), _e(sub)
            )
        )
    return '<div class="cards">{}</div>'.format("".join(blocks))


def _channels_table(data: Dict[str, Any]) -> str:
    rows = []
    for channel in data["per_channel"]:
        formats = ", ".join(
            "{}: {}".format(_e(name), _e(count)) for name, count in channel["formats"].items()
        ) or "—"
        last_run = channel["last_run"]
        if last_run:
            run_cell = "{} · постов: {}".format(
                _e(last_run["started_at_local"]), _e(last_run["posts_generated"])
            )
            if last_run["errors"]:
                run_cell += ' · <span class="err">ошибок: {}</span>'.format(
                    _e(last_run["errors"])
                )
        else:
            run_cell = "—"
        subscribers = channel["subscribers"]
        rows.append(
            "<tr>"
            "<td><b>{title}</b><div class=\"muted\">{cid}</div>{desc}</td>"
            '<td class="num">{articles}</td>'
            '<td class="num">{posts}</td>'
            '<td class="num">{publishes}</td>'
            '<td class="num">{subs}</td>'
            "<td>{formats}</td>"
            '<td class="num">{avg}</td>'
            "<td><div>{schedule}</div><div class=\"muted\">{run}</div></td>"
            "</tr>".format(
                title=_e(channel["title"]),
                cid=_e(channel["id"]),
                desc=(
                    '<div class="muted">{}</div>'.format(_e(channel["description"]))
                    if channel["description"]
                    else ""
                ),
                articles=_fmt_int(channel["articles"]),
                posts=_fmt_int(channel["posts"]),
                publishes=_fmt_int(channel["publishes"]["ok"]),
                subs=_fmt_int(subscribers, "—") if subscribers is not None else "—",
                formats=formats,
                avg=_fmt_float(channel["avg_post_chars"]),
                schedule=_e(channel["schedule"]),
                run=run_cell,
            )
        )
    if not rows:
        rows.append('<tr><td colspan="8" class="empty">Каналы не настроены</td></tr>')
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Канал</th><th class=\"num\">Статьи</th><th class=\"num\">Посты</th>"
        "<th class=\"num\">Публикации</th><th class=\"num\">Подписчики</th>"
        "<th>Форматы</th><th class=\"num\">Символов</th><th>Расписание и запуск</th>"
        "</tr></thead><tbody>{}</tbody></table></div>".format("".join(rows))
    )


def _formats_bars(data: Dict[str, Any]) -> str:
    formats = data["formats"]
    if not formats:
        return '<p class="empty">Постов пока нет — форматы появятся после первого запуска.</p>'
    maximum = max(formats.values()) if formats else 0
    rows = []
    for name, count in formats.items():
        width = _bar_width(int(count), int(maximum))
        rows.append(
            '<div class="bar-row"><div>{name}</div>'
            '<div class="bar-track"><div class="bar-fill" style="width:{width}%"></div></div>'
            '<div class="num">{count}</div></div>'.format(
                name=_e(name), width=width, count=_e(_fmt_int(count))
            )
        )
    return '<div class="bars">{}</div>'.format("".join(rows))


def _top_terms(data: Dict[str, Any]) -> str:
    terms = data["top_terms"]
    if not terms:
        return '<p class="empty">Топ-темы появятся, когда в базе будут посты.</p>'
    chips = "".join(
        '<span class="chip">{term} <b>×{count}</b></span>'.format(
            term=_e(item["term"]), count=_e(item["count"])
        )
        for item in terms
    )
    return '<div class="chips">{}</div>'.format(chips)


def _sources_table(data: Dict[str, Any]) -> str:
    sources = data["sources"]
    if not sources:
        return '<p class="empty">Статей пока нет — источники появятся после сбора новостей.</p>'
    rows = "".join(
        "<tr><td>{}</td><td class=\"num\">{}</td></tr>".format(
            _e(item["source_name"]), _e(_fmt_int(item["count"]))
        )
        for item in sources
    )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Источник</th><th class=\"num\">Статей</th>"
        "</tr></thead><tbody>{}</tbody></table></div>".format(rows)
    )


def _publications_table(data: Dict[str, Any]) -> str:
    publications = data["publications"]
    if not publications:
        return '<p class="empty">Публикаций пока нет. В dry-run они появятся в data/outbox.</p>'
    rows = []
    for item in publications:
        status = (
            '<span class="ok">успешно</span>'
            if item["ok"] and not item["dry_run"]
            else ('<span class="muted">dry-run</span>' if item["dry_run"] else '<span class="err">ошибка</span>')
        )
        url = item["url"]
        if url.startswith(("http://", "https://")):
            link = '<a href="{href}">{label}</a>'.format(
                href=_ea(url), label=_e("открыть")
            )
        else:
            link = '<span class="muted">{}</span>'.format(_e(url or "—"))
        error = '<div class="err">{}</div>'.format(_e(item["error"])) if item["error"] else ""
        rows.append(
            "<tr><td>{channel}</td><td>{post}</td><td>{publisher}</td>"
            "<td>{status}</td><td>{when}</td><td>{link}{error}</td></tr>".format(
                channel=_e(item["channel_title"]),
                post=_e(item["post_id"]),
                publisher=_e(item["publisher"]),
                status=status,
                when=_e(item["published_at_local"]),
                link=link,
                error=error,
            )
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Канал</th><th>Пост</th><th>Публикатор</th><th>Статус</th>"
        "<th>Когда</th><th>Ссылка</th>"
        "</tr></thead><tbody>{}</tbody></table></div>".format("".join(rows))
    )


def _runs_table(data: Dict[str, Any]) -> str:
    runs = data["runs"]
    if not runs:
        return '<p class="empty">Запусков пока не было.</p>'
    rows = []
    for run in runs:
        errors = (
            '<span class="err">{}</span>'.format(_e("; ".join(run["errors"])))
            if run["errors"]
            else '<span class="ok">нет</span>'
        )
        rows.append(
            "<tr><td>{channel}</td><td>{when}</td>"
            '<td class="num">{articles}</td><td class="num">{generated}</td>'
            '<td class="num">{published}</td><td>{dry}</td><td>{errors}</td></tr>'.format(
                channel=_e(run["channel_title"]),
                when=_e(run["started_at_local"]),
                articles=_e(_fmt_int(run["articles_new"])),
                generated=_e(_fmt_int(run["posts_generated"])),
                published=_e(_fmt_int(run["posts_published"])),
                dry="да" if run["dry_run"] else "нет",
                errors=errors,
            )
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Канал</th><th>Когда</th><th class=\"num\">Новых статей</th>"
        "<th class=\"num\">Постов</th><th class=\"num\">Опубликовано</th>"
        "<th>Dry-run</th><th>Ошибки</th>"
        "</tr></thead><tbody>{}</tbody></table></div>".format("".join(rows))
    )


def _errors_block(data: Dict[str, Any]) -> str:
    errors = data["errors"]
    if not errors:
        return '<p class="empty">Ошибок за период не зафиксировано.</p>'
    items = "".join(
        "<li><b>{channel}</b> · {when} — {message}</li>".format(
            channel=_e(item["channel_title"]),
            when=_e(item["when_local"]),
            message=_e(item["message"]),
        )
        for item in errors
    )
    return '<ul class="errors">{}</ul>'.format(items)


def render_html(data: Dict[str, Any]) -> str:
    """Самодостаточный HTML-отчёт (inline CSS, без CDN/интернета)."""
    llm = data.get("llm") or {}
    llm_text = str(llm.get("label") or "—")
    if llm.get("model"):
        llm_text += ", модель: {}".format(llm["model"])

    warning = ""
    if data.get("dry_run"):
        warning = (
            '<div class="warn">DRY RUN: реальная публикация отключена, '
            "посты сохраняются в data/outbox, а цифры подписчиков недоступны.</div>"
        )
    hint = ""
    if data.get("hint"):
        hint = '<div class="hint">{}</div>'.format(_e(data["hint"]))

    mode = "DRY RUN" if data.get("dry_run") else "Боевой режим"
    return """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{title}</h1>
  <p class="meta">Период: последние {days} дн. · Сформирован: {generated}</p>
  <p class="meta">LLM: {llm}</p>
  <span class="mode">{mode}</span>
</header>
{warning}
{hint}
<h2>Сводка</h2>
{cards}
<h2>Каналы</h2>
{channels}
<h2>Форматы постов</h2>
{formats}
<h2>Топ-темы</h2>
{terms}
<h2>Источники</h2>
{sources}
<h2>Последние публикации</h2>
{publications}
<h2>Последние запуски</h2>
{runs}
<h2>Ошибки</h2>
{errors}
<footer>Отчёт сформирован автоматически контент-заводом. Внешние ресурсы не используются.</footer>
</div>
</body>
</html>
""".format(
        title=_e(data.get("title") or "Контент-завод: аналитика"),
        css=_REPORT_CSS,
        days=_e(data.get("days")),
        generated=_e(data.get("generated_at_local")),
        llm=_e(llm_text),
        mode=_e(mode),
        warning=warning,
        hint=hint,
        cards=_summary_cards(data),
        channels=_channels_table(data),
        formats=_formats_bars(data),
        terms=_top_terms(data),
        sources=_sources_table(data),
        publications=_publications_table(data),
        runs=_runs_table(data),
        errors=_errors_block(data),
    )


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def _md_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def render_markdown(data: Dict[str, Any]) -> str:
    """Тот же отчёт в Markdown: удобно отправить в чат или положить в git."""
    totals = data["totals"]
    publishes = totals["publishes"]
    llm = data.get("llm") or {}
    llm_text = str(llm.get("label") or "—")
    if llm.get("model"):
        llm_text += ", модель: {}".format(llm["model"])
    mode = "DRY RUN (реальная публикация отключена)" if data.get("dry_run") else "боевой режим"

    lines: List[str] = [
        "# {}".format(data.get("title") or "Контент-завод: аналитика"),
        "",
        "- Период: последние {} дн.".format(data.get("days")),
        "- Сформирован: {}".format(data.get("generated_at_local")),
        "- Режим: {}".format(mode),
        "- LLM: {}".format(llm_text),
        "",
    ]
    if data.get("dry_run"):
        lines.extend([
            "> **DRY RUN:** реальная публикация отключена, посты лежат в `data/outbox`.",
            "",
        ])
    if data.get("hint"):
        lines.extend(["> {}".format(data["hint"]), ""])

    lines.extend(
        [
            "## Сводка",
            "",
            "| Показатель | Значение |",
            "| --- | --- |",
            "| Каналы | {} (включено: {}) |".format(
                _md_cell(totals["channels"]), _md_cell(totals["channels_enabled"])
            ),
            "| Статьи | {} |".format(_md_cell(totals["articles"])),
            "| Посты | {} |".format(_md_cell(totals["posts"])),
            "| Публикации | {} (успешно: {}, ошибок: {}, dry-run: {}) |".format(
                _md_cell(publishes["total"]),
                _md_cell(publishes["ok"]),
                _md_cell(publishes["failed"]),
                _md_cell(publishes["dry_run"]),
            ),
            "| Подписчики | {} |".format(
                _md_cell(totals["subscribers"]) if totals["subscribers"] is not None else "—"
            ),
            "| Средняя длина поста | {} символов |".format(_fmt_float(totals["avg_post_chars"])),
            "",
            "## Каналы",
            "",
            "| Канал | Статьи | Посты | Публикации | Подписчики | Форматы | Расписание |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for channel in data["per_channel"]:
        formats = ", ".join(
            "{}: {}".format(name, count) for name, count in channel["formats"].items()
        ) or "—"
        lines.append(
            "| {} ({}) | {} | {} | {} | {} | {} | {} |".format(
                _md_cell(channel["title"]),
                _md_cell(channel["id"]),
                _md_cell(channel["articles"]),
                _md_cell(channel["posts"]),
                _md_cell(channel["publishes"]["ok"]),
                _md_cell(channel["subscribers"]) if channel["subscribers"] is not None else "—",
                _md_cell(formats),
                _md_cell(channel["schedule"]),
            )
        )
    lines.extend(["", "## Форматы", ""])
    if data["formats"]:
        for name, count in data["formats"].items():
            lines.append("- {}: {}".format(name, count))
    else:
        lines.append("Постов пока нет.")
    lines.extend(["", "## Топ-темы", ""])
    if data["top_terms"]:
        lines.append(
            ", ".join("{} (×{})".format(item["term"], item["count"]) for item in data["top_terms"])
        )
    else:
        lines.append("Топ-темы появятся после первого запуска.")
    lines.extend(["", "## Источники", ""])
    if data["sources"]:
        lines.extend(["| Источник | Статей |", "| --- | ---: |"])
        for item in data["sources"]:
            lines.append("| {} | {} |".format(_md_cell(item["source_name"]), item["count"]))
    else:
        lines.append("Статей пока нет.")
    lines.extend(["", "## Последние публикации", ""])
    if data["publications"]:
        lines.extend(
            [
                "| Канал | Пост | Публикатор | Статус | Когда | Ссылка |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in data["publications"]:
            status = _publish_status(item["ok"], item["dry_run"])
            lines.append(
                "| {} | {} | {} | {} | {} | {} |".format(
                    _md_cell(item["channel_title"]),
                    _md_cell(item["post_id"]),
                    _md_cell(item["publisher"]),
                    status,
                    _md_cell(item["published_at_local"]),
                    _md_cell(item["url"] or "—"),
                )
            )
    else:
        lines.append("Публикаций пока нет.")
    lines.extend(["", "## Последние запуски", ""])
    if data["runs"]:
        lines.extend(
            [
                "| Канал | Когда | Новых статей | Постов | Опубликовано | Ошибки |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for run in data["runs"]:
            lines.append(
                "| {} | {} | {} | {} | {} | {} |".format(
                    _md_cell(run["channel_title"]),
                    _md_cell(run["started_at_local"]),
                    run["articles_new"],
                    run["posts_generated"],
                    run["posts_published"],
                    _md_cell("; ".join(run["errors"]) or "нет"),
                )
            )
    else:
        lines.append("Запусков пока не было.")
    lines.extend(["", "## Ошибки", ""])
    if data["errors"]:
        for item in data["errors"]:
            lines.append(
                "- {} · {} — {}".format(item["channel_title"], item["when_local"], item["message"])
            )
    else:
        lines.append("Ошибок за период не зафиксировано.")
    lines.extend(
        [
            "",
            "_Отчёт сформирован автоматически контент-заводом. Внешние ресурсы не используются._",
            "",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# сохранение
# ---------------------------------------------------------------------------
def save_report(
    settings: Settings,
    storage: Storage,
    channels: Sequence[ChannelConfig],
    days: int = 7,
) -> Dict[str, str]:
    """Строит отчёт и пишет data/reports/report.html и report.md.

    Возвращает {"html": абсолютный путь, "md": абсолютный путь}.
    """
    data = build_report(settings, storage, channels, days=days)
    reports_dir = ensure_dir(settings.reports_dir)
    html_path = Path(reports_dir) / "report.html"
    md_path = Path(reports_dir) / "report.md"
    atomic_write_text(html_path, render_html(data))
    atomic_write_text(md_path, render_markdown(data))
    logger.info("Отчёт сохранён: %s, %s", html_path, md_path)
    return {"html": str(html_path.resolve()), "md": str(md_path.resolve())}
