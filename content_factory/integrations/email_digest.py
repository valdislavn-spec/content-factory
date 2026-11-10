"""Еженедельный email-дайджест: сбор постов, HTML-письмо и отправка через Brevo.

Данные берутся в таком порядке:
1. ``telegram_posts`` — посты с просмотрами (если запускался telegram-metrics);
2. ``posts`` — опубликованные посты из SQLite (без просмотров);
3. публичное превью ``t.me/s/<channel>`` — если БД пустая (нужна сеть).

Отправка — Brevo Campaigns API (бесплатный тариф: 300 писем/день).
Без явного ``send=True`` ничего не отправляется: письмо пишется в файл.
"""
from __future__ import annotations

import html
import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import Settings, load_network_channels
from ..dedup import is_duplicate_title
import yaml

from ..models import utcnow
from ..utils import normalize_space, strip_html

BREVO_API = "https://api.brevo.com/v3"
_LINKS_PATH = Path(__file__).resolve().parents[2] / "config" / "channel_links.yaml"
_LINKS: Dict[str, str] = {}


def _channel_links() -> Dict[str, str]:
    global _LINKS
    if not _LINKS:
        try:
            data = yaml.safe_load(_LINKS_PATH.read_text(encoding="utf-8")) or {}
            _LINKS = {str(key): str(value) for key, value in data.items()}
        except Exception:  # noqa: BLE001 - ссылки не должны ронять дайджест
            _LINKS = {}
    return _LINKS

_LOCALE = {
    "en": {
        "badge": "Weekly email digest",
        "title": "Crypto, AI and US sports — one email a week",
        "intro": "Five stories worth your time: crypto, AI and US sports, with links to the Telegram channels. No spam, no paid signals.",
        "section": {"crypto-news": "Crypto & Blockchain", "ai-news": "AI News", "sport-news": "US Sports News"},
        "read": "Read in Telegram",
        "digest_title": "Weekly digest",
        "subject": "{n} stories this week: crypto, AI & sports",
        "footer_why": "You receive this email because you subscribed to the weekly digest.",
        "unsubscribe": "Unsubscribe",
        "preferences": "Change preferences",
        "all_channels": "All Telegram channels",
        "views": "views",
        "empty": "No published posts for the last week yet.",
    },
    "es": {
        "badge": "Resumen semanal por email",
        "title": "Cripto, IA y deporte — un email a la semana",
        "intro": "Cinco historias que merecen tu tiempo: cripto, IA y deporte, con enlaces a los canales de Telegram. Sin spam, sin señales pagadas.",
        "section": {"crypto-es": "ES Crypto & Blockchain", "tech-ai-es": "ES AI News", "futbol-es": "ES Sports News"},
        "read": "Leer en Telegram",
        "digest_title": "Resumen semanal",
        "subject": "{n} historias de la semana: cripto, IA y deporte",
        "footer_why": "Recibes este email porque te suscribiste al resumen semanal.",
        "unsubscribe": "Darse de baja",
        "preferences": "Cambiar preferencias",
        "all_channels": "Todos los canales de Telegram",
        "views": "vistas",
        "empty": "Todavía no hay publicaciones de la última semana.",
    },
}


@dataclass
class DigestItem:
    """Одна новость в письме."""

    channel_id: str
    channel_title: str
    channel_url: str
    title: str
    snippet: str
    url: str
    views: Optional[int] = None
    published_at: Optional[str] = None


@dataclass
class Digest:
    """Готовое письмо."""

    language: str
    subject: str
    html: str
    text: str
    items: List[DigestItem] = field(default_factory=list)
    period_start: str = ""
    period_end: str = ""


def _locale(language: str) -> Dict[str, Any]:
    return _LOCALE.get(language, _LOCALE["en"])


def _first_sentence(text: str, limit: int = 110) -> str:
    plain = normalize_space(strip_html(text or ""))
    if not plain:
        return ""
    match = re.split(r"(?<=[.!?])\s+", plain, maxsplit=1)
    sentence = match[0] if match else plain
    if len(sentence) > limit:
        sentence = sentence[: limit - 1].rstrip() + "…"
    return sentence


def _snippet(text: str, title: str, limit: int = 240) -> str:
    plain = normalize_space(strip_html(text or ""))
    if not plain:
        return ""
    if plain.startswith(title):
        plain = plain[len(title) :].strip()
    if len(plain) <= limit:
        return plain
    cut = plain[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def _iso(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _channel_public_url(channel: Any) -> str:
    link = _channel_links().get(str(getattr(channel, "id", "")), "")
    if link:
        return link
    return str(getattr(channel, "public_url", "") or "")


def _from_telegram_posts(rows: Sequence[Dict[str, Any]], channel: Any) -> List[DigestItem]:
    items: List[DigestItem] = []
    fallback_url = _channel_public_url(channel)
    for row in rows:
        text = str(row.get("text_preview") or "").strip()
        if not text:
            continue
        title = _first_sentence(text)
        if not title:
            continue
        items.append(
            DigestItem(
                channel_id=str(getattr(channel, "id", "")),
                channel_title=str(getattr(channel, "title", "")),
                channel_url=fallback_url,
                title=title,
                snippet=_snippet(text, title),
                url=str(row.get("url") or fallback_url),
                views=row.get("views"),
                published_at=_iso(row.get("posted_at")),
            )
        )
    return items


def _from_posts(rows: Sequence[Dict[str, Any]], channel: Any) -> List[DigestItem]:
    items: List[DigestItem] = []
    fallback_url = _channel_public_url(channel)
    for row in rows:
        if str(row.get("status") or "") != "published":
            continue
        text = str(row.get("text") or "").strip()
        title = _first_sentence(text)
        if not title:
            continue
        items.append(
            DigestItem(
                channel_id=str(getattr(channel, "id", "")),
                channel_title=str(getattr(channel, "title", "")),
                channel_url=fallback_url,
                title=title,
                snippet=_snippet(text, title),
                url=fallback_url,
                published_at=_iso(row.get("created_at")),
            )
        )
    return items


def _from_preview(channel: Any) -> List[DigestItem]:
    """Fallback: публичное превью t.me/s (если БД пустая)."""
    try:
        from ..analytics.preview import fetch_preview, normalize_username

        username = normalize_username(_channel_public_url(channel))
        if not username:
            return []
        preview = fetch_preview(username, timeout=15, limit=20)
    except Exception:  # noqa: BLE001 - сеть не должна ронять дайджест
        return []
    items: List[DigestItem] = []
    fallback_url = _channel_public_url(channel)
    for post in preview.posts:
        if getattr(post, "is_sponsored", False):
            continue
        text = str(getattr(post, "text", "") or "").strip()
        title = _first_sentence(text)
        if not title:
            continue
        items.append(
            DigestItem(
                channel_id=str(getattr(channel, "id", "")),
                channel_title=str(getattr(channel, "title", "")),
                channel_url=fallback_url,
                title=title,
                snippet=_snippet(text, title),
                url=str(getattr(post, "post_url", "") or fallback_url),
                views=getattr(post, "views", None),
                published_at=getattr(post, "published_at", None),
            )
        )
    return items


def _channel_items(storage: Any, channel: Any, days: float, allow_preview: bool = True) -> List[DigestItem]:
    items: List[DigestItem] = []
    try:
        rows = storage.telegram_posts(str(channel.id), days=days, limit=12)
    except Exception:  # noqa: BLE001
        rows = []
    if rows:
        items = _from_telegram_posts(rows, channel)
    if not items:
        try:
            posts = storage.get_posts(str(channel.id), days=days, limit=40)
        except Exception:  # noqa: BLE001
            posts = []
        items = _from_posts(posts, channel)
    if not items and allow_preview:
        items = _from_preview(channel)
    return items


def collect_items(
    settings: Settings,
    storage: Any,
    language: str,
    *,
    days: float = 7,
    per_channel: int = 2,
    max_items: int = 6,
    allow_preview: bool = True,
) -> List[DigestItem]:
    """Собирает и ранжирует новости для письма по языку каналов."""
    channels = [
        channel
        for channel in load_network_channels(settings)
        if str(getattr(channel, "language", "en")) == language
    ]
    selected: List[DigestItem] = []
    for channel in channels:
        items = _channel_items(storage, channel, days, allow_preview=allow_preview)
        if not items:
            continue
        items.sort(
            key=lambda item: (
                int(item.views or 0),
                item.published_at or "",
            ),
            reverse=True,
        )
        selected.extend(items[:per_channel])
    # Дедуп по заголовкам (внутри письма) и ограничение объёма.
    unique: List[DigestItem] = []
    seen: List[str] = []
    for item in selected:
        if is_duplicate_title(item.title, seen, threshold=0.72):
            continue
        unique.append(item)
        seen.append(item.title)
    return unique[:max_items]


def render(
    items: Sequence[DigestItem],
    settings: Settings,
    language: str,
    *,
    now: Optional[datetime] = None,
) -> Digest:
    """Рендерит HTML/plain-text письмо и тему."""
    locale = _locale(language)
    now = now or utcnow()
    start = (now - timedelta(days=7)).strftime("%d.%m")
    end = now.strftime("%d.%m.%Y")
    channels = [
        channel
        for channel in load_network_channels(settings)
        if str(getattr(channel, "language", "en")) == language
    ]
    by_channel: Dict[str, List[DigestItem]] = {}
    for item in items:
        by_channel.setdefault(item.channel_id, []).append(item)

    sections: List[str] = []
    for channel_id, channel_items in by_channel.items():
        heading = locale["section"].get(channel_id) or locale["section"].get(
            channel_items[0].channel_title, channel_items[0].channel_title
        )
        rows: List[str] = []
        for item in channel_items:
            meta = ""
            if item.views:
                meta = (
                    '<div style="color:#8a94a6;font-size:12px;margin-top:4px;">'
                    f'{int(item.views)} {locale["views"]}</div>'
                )
            rows.append(
                '<tr><td style="padding:14px 0;border-bottom:1px solid #e8ecf3;">'
                '<a href="' + html.escape(item.url) + '" style="color:#1a5fb4;text-decoration:none;'
                'font-size:16px;font-weight:700;line-height:1.35;">'
                + html.escape(item.title)
                + "</a>"
                '<div style="color:#4a5568;font-size:14px;line-height:1.5;margin-top:6px;">'
                + html.escape(item.snippet)
                + "</div>"
                + meta
                + '<div style="margin-top:8px;"><a href="'
                + html.escape(item.url)
                + '" style="color:#1a5fb4;font-size:13px;font-weight:600;text-decoration:none;">'
                + html.escape(locale["read"])
                + " →</a></div>"
                "</td></tr>"
            )
        sections.append(
            '<h2 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;'
            'color:#8a94a6;margin:30px 0 6px;">'
            + html.escape(heading)
            + "</h2><table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
            + "".join(rows)
            + "</table>"
        )

    all_links = "".join(
        '<a href="' + html.escape(_channel_public_url(channel)) + '" '
        'style="color:#1a5fb4;text-decoration:none;font-weight:600;margin-right:14px;">'
        + html.escape(str(channel.title))
        + "</a>"
        for channel in channels
    )
    body_sections = "".join(sections) if items else (
        '<p style="color:#4a5568;">' + html.escape(locale["empty"]) + "</p>"
    )
    html_text = f"""<!doctype html>
<html lang="{language}"><body style="margin:0;padding:0;background:#f4f6fa;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fa;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:14px;padding:28px 26px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1c2430;">
<tr><td>
<div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8a94a6;">{html.escape(locale["badge"])} · {html.escape(start)}–{html.escape(end)}</div>
<h1 style="font-size:26px;line-height:1.25;margin:10px 0 8px;">{html.escape(locale["title"])}</h1>
<p style="color:#4a5568;font-size:15px;line-height:1.55;margin:0 0 6px;">{html.escape(locale["intro"])}</p>
{body_sections}
<div style="margin-top:30px;padding-top:16px;border-top:1px solid #e8ecf3;font-size:13px;color:#8a94a6;line-height:1.6;">
<div style="margin-bottom:8px;">{html.escape(locale["footer_why"])}</div>
<div style="margin-bottom:8px;">{all_links}</div>
<a href="{{unsubscribe}}" style="color:#1a5fb4;">{html.escape(locale["unsubscribe"])}</a>
&nbsp;·&nbsp;<a href="{{unsubscribe}}" style="color:#1a5fb4;">{html.escape(locale["preferences"])}</a>
</div>
</td></tr></table>
</td></tr></table>
</body></html>"""

    plain_lines = [
        f"{locale['digest_title']} · {start}–{end}",
        "",
    ]
    for item in items:
        plain_lines += [f"• {item.title}", item.snippet, item.url, ""]
    plain_lines += [
        locale["all_channels"] + ": " + ", ".join(str(channel.title) for channel in channels),
        locale["unsubscribe"] + ": {{unsubscribe}}",
    ]
    subject = locale["subject"].format(n=len(items) or 5)
    return Digest(
        language=language,
        subject=subject,
        html=html_text,
        text="\n".join(plain_lines),
        items=list(items),
        period_start=start,
        period_end=end,
    )


def build_brevo_payload(
    digest: Digest,
    *,
    sender_email: str,
    sender_name: str,
    list_id: int,
    campaign_name: str = "",
) -> Dict[str, Any]:
    """Тело запроса POST /v3/emailCampaigns."""
    return {
        "name": campaign_name or f"Weekly digest {digest.language} {digest.period_end}",
        "subject": digest.subject,
        "sender": {"name": sender_name or "Content Factory", "email": sender_email},
        "type": "classic",
        "htmlContent": digest.html,
        "recipients": {"listIds": [int(list_id)]},
        # replyTo intentionally omitted: on the free plan Brevo rejects
        # reply-to addresses outside an authenticated domain with
        # ``invalid_parameter: ReplyTo email should be valid``. Replies go to
        # the verified sender (EMAIL_FROM) by default.
    }


def _post_json(url: str, payload: Dict[str, Any], api_key: str, method: str = "POST") -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "content-factory-email-digest",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def send_brevo_campaign(
    digest: Digest,
    *,
    api_key: str,
    sender_email: str,
    sender_name: str,
    list_id: int,
    campaign_name: str = "",
) -> Dict[str, Any]:
    """Создаёт и сразу отправляет кампанию в Brevo. Возвращает ответ API."""
    payload = build_brevo_payload(
        digest,
        sender_email=sender_email,
        sender_name=sender_name,
        list_id=list_id,
        campaign_name=campaign_name,
    )
    created = _post_json(f"{BREVO_API}/emailCampaigns", payload, api_key)
    campaign_id = created.get("id")
    if not campaign_id:
        raise RuntimeError(f"Brevo не вернул id кампании: {created}")
    result = _post_json(
        f"{BREVO_API}/emailCampaigns/{campaign_id}/sendNow", {}, api_key
    )
    return {"id": campaign_id, "send": result}
