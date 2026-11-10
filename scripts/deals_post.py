#!/usr/bin/env python3
"""Сборка deals-постов для товарных партнёрок (проект «Deals Factory»).

Читает очередь `data/deals/queue.yaml`, рендерит посты по шаблонам A/B/C
(см. docs/monetization/deals-templates.md), подставляет UTM и короткие ссылки
(через `content_factory.integrations.shortlink`, fallback — исходный URL).

Примеры:
    python scripts/deals_post.py
    python scripts/deals_post.py --channel futbol-es
    python scripts/deals_post.py --no-shorten --out data/reports/deals.md
    python scripts/deals_post.py --json-out data/reports/deals.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from content_factory.integrations.shortlink import shorten_url  # noqa: E402

DEFAULT_QUEUE = ROOT / "data" / "deals" / "queue.yaml"
DEFAULT_OUT_DIR = ROOT / "data" / "reports"

# Шаблоны: {channel_slug} не нужен — UTM уже вшит в ссылку.
TEMPLATES = {
    "A": {
        "es": (
            "🛒 {title}\n\n"
            "{price_line}{extra}\n\n"
            "👉 {link}\n\n"
            "⚠️ Enlace de afiliado. Precio al momento de la publicación."
        ),
        "en": (
            "🛒 {title}\n\n"
            "{price_line}{extra}\n\n"
            "👉 {link}\n\n"
            "⚠️ Affiliate link. Price at time of posting."
        ),
    },
    "B": {
        "es": (
            "🔥 {title}\n\n"
            "{items}\n\n"
            "⚠️ Enlaces de afiliado. Precios pueden cambiar."
        ),
        "en": (
            "🔥 {title}\n\n"
            "{items}\n\n"
            "⚠️ Affiliate links. Prices may change."
        ),
    },
    "C": {
        "es": (
            "👕 {title}: {price} vía agente\n\n"
            "• Cómo pedir: {steps}\n"
            "• Plazo/entrega: {delivery}\n"
            "• Precio del producto, envío se calcula aparte\n\n"
            "👉 {link}\n\n"
            "⚠️ Enlace de afiliado."
        ),
        "en": (
            "👕 {title}: {price} via agent\n\n"
            "• How to order: {steps}\n"
            "• Delivery: {delivery}\n"
            "• Product price only, shipping calculated separately\n\n"
            "👉 {link}\n\n"
            "⚠️ Affiliate link."
        ),
    },
}

CHANNEL_LANG = {
    "futbol-es": "es",
    "tech-ai-es": "es",
    "crypto-es": "es",
    "ai-news": "en",
    "sport-news": "en",
    "crypto-news": "en",
}


def _num(value: Any) -> Optional[float]:
    """Достаёт число из цены вида «15 €» / «$9.99»."""
    if value is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", str(value).replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def discount_percent(old_price: Any, price: Any) -> Optional[int]:
    old, new = _num(old_price), _num(price)
    if not old or not new or new >= old:
        return None
    return int(round((1 - new / old) * 100))


def with_utm(link: str, channel: str, program: str) -> str:
    if not link:
        return ""
    parts = urllib.parse.urlsplit(link)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query.update(
        {
            "utm_source": "tg_" + channel.replace("-", "_"),
            "utm_medium": "telegram",
            "utm_campaign": program,
        }
    )
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def price_line(item: Dict[str, Any], lang: str) -> str:
    old = item.get("old_price")
    price = item.get("price") or ""
    percent = discount_percent(old, price)
    if old and price:
        if percent:
            return (
                f"Precio: {old} → {price} ({percent}%)\n" if lang == "es" else f"Price: {old} → {price} ({percent}%)\n"
            )
        return f"Precio: {old} → {price}\n" if lang == "es" else f"Price: {old} → {price}\n"
    if price:
        return f"Precio: {price}\n" if lang == "es" else f"Price: {price}\n"
    return ""


def render_item(item: Dict[str, Any], program: Dict[str, Any], shorten: bool = True) -> Optional[str]:
    """Рендерит один пост; None — если размещать пока нельзя (pending/нет ссылки)."""
    if str(item.get("status", "ready")) != "ready":
        return None
    channel = str(item.get("channel") or "")
    lang = str(item.get("lang") or CHANNEL_LANG.get(channel, "es"))
    fmt = str(item.get("format") or "A").upper()
    template = TEMPLATES.get(fmt, TEMPLATES["A"]).get(lang, TEMPLATES["A"]["es"])

    base_link = str(program.get("link") or "") or str(item.get("url") or "")
    if not base_link:
        return None
    link = with_utm(base_link, channel, str(program.get("utm_campaign") or "deals"))
    if shorten:
        link = shorten_url(link)

    extra = ""
    hook = str(item.get("hook") or "").strip()
    if hook:
        extra = f"\n{hook}" if fmt == "A" else ""
    if fmt == "A":
        return template.format(
            title=item.get("title", ""),
            price_line=price_line(item, lang),
            extra=extra,
            link=link,
        ).strip()
    if fmt == "B":
        rows = item.get("rows") or []
        items = "\n".join(
            f"{idx}. {row.get('title', '')} — {row.get('price', '')} → {shorten_url(with_utm(row.get('url', ''), channel, str(program.get('utm_campaign') or 'deals'))) if shorten else with_utm(row.get('url', ''), channel, str(program.get('utm_campaign') or 'deals'))}"
            for idx, row in enumerate(rows, start=1)
        )
        return template.format(title=item.get("title", ""), items=items).strip()
    # C
    return template.format(
        title=item.get("title", ""),
        price=item.get("price", ""),
        steps=item.get("steps", ""),
        delivery=item.get("delivery", ""),
        link=link,
    ).strip()


def build_report(queue: Dict[str, Any], shorten: bool = True, channel: Optional[str] = None) -> Dict[str, Any]:
    programs = queue.get("programs") or {}
    posts: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    for item in queue.get("items") or []:
        channel_id = str(item.get("channel") or "")
        if channel and channel_id != channel:
            continue
        program_id = str(item.get("program") or "")
        program = programs.get(program_id) or {}
        text = render_item(item, program, shorten=shorten)
        if not text:
            reason = "pending" if str(item.get("status", "ready")) != "ready" else "нет ссылки программы"
            skipped.append({"id": str(item.get("id", "")), "reason": reason})
            continue
        posts.append(
            {
                "id": item.get("id", ""),
                "channel": channel_id,
                "lang": item.get("lang") or CHANNEL_LANG.get(channel_id, "es"),
                "program": program_id,
                "format": item.get("format", "A"),
                "text": text,
            }
        )
    return {"posts": posts, "skipped": skipped}


def to_markdown(report: Dict[str, Any], source: Path) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Deals-посты — черновики",
        "",
        f"Сгенерировано: {now} · очередь: `{source}`",
        "",
        "Перед публикацией: сверить цены в кабинете программы, при необходимости заменить ссылку.",
        "",
    ]
    by_channel: Dict[str, List[Dict[str, Any]]] = {}
    for post in report["posts"]:
        by_channel.setdefault(post["channel"], []).append(post)
    for channel_id, posts in by_channel.items():
        lines.append(f"## {channel_id}")
        lines.append("")
        for post in posts:
            lines.append(f"### {post['id']} · {post['program']} · формат {post['format']}")
            lines.append("")
            lines.append("```")
            lines.append(post["text"])
            lines.append("```")
            lines.append("")
    if report["skipped"]:
        lines.append("## Пропущено")
        lines.append("")
        for row in report["skipped"]:
            lines.append(f"- `{row['id']}` — {row['reason']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Генератор deals-постов (товарные партнёрки)")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE), help="путь к queue.yaml")
    parser.add_argument("--out", default="", help="путь к md-файлу отчёта")
    parser.add_argument("--json-out", default="", help="путь к json-файлу")
    parser.add_argument("--channel", default="", help="только один канал, например futbol-es")
    parser.add_argument("--no-shorten", action="store_true", help="не сокращать ссылки")
    args = parser.parse_args(argv)

    queue_path = Path(args.queue)
    if not queue_path.exists():
        print(f"Нет файла очереди: {queue_path}", file=sys.stderr)
        return 2
    queue = yaml.safe_load(queue_path.read_text(encoding="utf-8")) or {}
    report = build_report(queue, shorten=not args.no_shorten, channel=args.channel or None)
    if not report["posts"]:
        print("Нечего рендерить: все товары pending или нет ссылок.", file=sys.stderr)
    markdown = to_markdown(report, queue_path)
    out_path = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"deals-posts-{datetime.now().strftime('%Y-%m-%d')}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Готово: {len(report['posts'])} постов → {out_path}")
    if report["skipped"]:
        print("Пропущено: " + ", ".join(f"{row['id']} ({row['reason']})" for row in report["skipped"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
