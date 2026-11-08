"""Лендинг каналов для поискового трафика (GitHub Pages / Cloudflare Pages).

Генерирует статические страницы только для живых каналов (EN/ES), не для RU:
    exports/landing/<channel>.html
    exports/landing/index.html
    exports/landing/sitemap.xml

Каждая страница: описание канала, кнопка «Открыть в Telegram», темы, хэштеги.
Деплой — залить папку в GitHub Pages; затем пинг IndexNow (см. integrations/indexnow.py).
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..models import ChannelConfig
from ..publishers.social import channel_link

_HANDLE_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{3,31})")


def public_url(channel: ChannelConfig) -> str:
    """Публичный адрес канала: env TELEGRAM_CHANNEL_URL_<CHANNEL>, иначе @username."""
    link = channel_link(channel)
    if link:
        return link
    match = _HANDLE_RE.search(str(getattr(channel, "description", "") or ""))
    if match:
        return f"https://t.me/{match.group(1)}"
    return ""


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def gtag_snippet(measurement_id: str) -> str:
    """Google tag (gtag.js) для GA4; пустая строка, если ID не задан."""
    mid = str(measurement_id or "").strip()
    if not mid.startswith("G-"):
        return ""
    return (
        '<script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>\n'
        '<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}'
        "gtag('js',new Date());gtag('config','{mid}');</script>"
    ).format(mid=mid)


_PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Telegram</title>
<meta name="description" content="{description}">
<style>
:root {{ color-scheme: light dark; --bg:#f6f7fb; --card:#fff; --text:#18202c; --muted:#5a6572; --accent:#2b6cb0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f141b; --card:#18202b; --text:#e8edf5; --muted:#9aa7b8; --accent:#7fb3e8; }} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font:16px/1.6 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; background:var(--bg); color:var(--text); }}
.wrap {{ max-width:720px; margin:0 auto; padding:48px 16px; }}
.card {{ background:var(--card); border-radius:16px; padding:32px; box-shadow:0 6px 28px rgba(15,25,40,.08); }}
h1 {{ margin:0 0 8px; font-size:30px; }}
p {{ color:var(--muted); }}
.cta {{ display:inline-block; margin:20px 0 8px; padding:14px 26px; border-radius:12px; background:var(--accent); color:#fff; text-decoration:none; font-weight:700; }}
.topics {{ color:var(--muted); font-size:14px; }}
footer {{ color:var(--muted); font-size:13px; margin-top:28px; }}
a {{ color:var(--accent); }}
</style>
{gtag}
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>{title}</h1>
    <p>{description}</p>
    <a class="cta" href="{url}" rel="noopener">Открыть в Telegram</a>
    <p class="topics">Темы: {topics}</p>
    {tags}
    <footer>content-factory · {handle}</footer>
  </div>
  {back}
</div>
</body>
</html>
"""


def build_channel_page(
    channel: ChannelConfig, *, back: str = "", measurement_id: str = ""
) -> str:
    url = public_url(channel)
    topics = ", ".join(str(t) for t in (channel.topics or [])[:10])
    tags = ""
    if channel.hashtags:
        tags = "<p class=\"topics\">" + " ".join(
            f"<span>{_esc(tag)}</span>" for tag in channel.hashtags[:8]
        ) + "</p>"
    handle = _HANDLE_RE.search(str(channel.description or ""))
    handle_text = f"@{handle.group(1)}" if handle else ""
    back_html = f'<footer><a href="{_esc(back)}">Все каналы</a></footer>' if back else ""
    return _PAGE.format(
        lang=_esc(channel.language or "en"),
        title=_esc(channel.title),
        description=_esc(channel.description or ""),
        topics=_esc(topics),
        tags=tags,
        url=_esc(url or "#"),
        handle=_esc(handle_text),
        back=back_html,
        gtag=gtag_snippet(measurement_id),
    )


_INDEX = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{site} — Telegram channels</title>
<meta name="description" content="{site}: бесплатные Telegram-каналы — {list}">
<style>
body {{ margin:0; font:16px/1.6 -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
       background:#f6f7fb; color:#18202c; }}
.wrap {{ max-width:820px; margin:0 auto; padding:48px 16px; }}
h1 {{ font-size:28px; margin:0 0 4px; }}
p {{ color:#5a6572; }}
ul {{ list-style:none; padding:0; }}
li {{ background:#fff; border-radius:12px; padding:16px 18px; margin:10px 0;
      box-shadow:0 4px 18px rgba(15,25,40,.06); }}
a {{ color:#2b6cb0; text-decoration:none; font-weight:700; }}
.desc {{ color:#5a6572; font-size:14px; margin-top:4px; }}
</style>
{gtag}
</head>
<body>
<div class="wrap">
  <h1>{site}</h1>
  <p>Бесплатные Telegram-каналы: новости, разборы и дайджесты.</p>
  <ul>
  {items}
  </ul>
</div>
</body>
</html>
"""


def build_index_page(
    channels: Sequence[ChannelConfig],
    site: str = "Content Factory",
    measurement_id: str = "",
) -> str:
    items = []
    for channel in channels:
        url = public_url(channel)
        if not url:
            continue
        items.append(
            "<li><a href=\"{href}\">{title}</a><div class=\"desc\">{desc}</div></li>".format(
                href=_esc(url),
                title=_esc(channel.title),
                desc=_esc(channel.description or ""),
            )
        )
    return _INDEX.format(
        lang="en",
        site=_esc(site),
        list=_esc(", ".join(c.title for c in channels[:10])),
        items="\n  ".join(items),
        gtag=gtag_snippet(measurement_id),
    )


def build_sitemap(channels: Sequence[ChannelConfig], base_url: str) -> str:
    base = str(base_url or "").rstrip("/")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for channel in channels:
        loc = f"{base}/{channel.id}.html"
        lines.append(f"  <url><loc>{_esc(loc)}</loc></url>")
    lines.append(f"  <url><loc>{_esc(base + '/index.html')}</loc></url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def build_landing(
    channels: Sequence[ChannelConfig],
    out_dir: Path,
    base_url: str = "",
    site: str = "Content Factory",
    measurement_id: str = "",
) -> Dict[str, List[Path]]:
    """Пишет страницы каналов, index.html и sitemap.xml; возвращает пути.

    ``measurement_id`` — GA4 Measurement ID (``G-...``); если пусто, берётся из
    переменной окружения ``GA4_MEASUREMENT_ID`` (иначе тег не добавляется).
    """
    if not measurement_id:
        from ..utils import env

        measurement_id = (env("GA4_MEASUREMENT_ID", "") or "").strip()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages: List[Path] = []
    for channel in channels:
        if not public_url(channel):
            continue
        page = out / f"{channel.id}.html"
        page.write_text(
            build_channel_page(channel, back="index.html", measurement_id=measurement_id),
            encoding="utf-8",
        )
        pages.append(page)
    index = out / "index.html"
    index.write_text(
        build_index_page(channels, site=site, measurement_id=measurement_id),
        encoding="utf-8",
    )
    sitemap = out / "sitemap.xml"
    sitemap.write_text(build_sitemap(channels, base_url or "https://example.com"), encoding="utf-8")
    return {"pages": pages, "index": [index], "sitemap": [sitemap]}


__all__ = [
    "build_channel_page",
    "build_index_page",
    "build_landing",
    "build_sitemap",
    "public_url",
]
