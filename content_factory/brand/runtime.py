"""Автоподстановка брендовых карточек в публикации.

Партнёрский пост (``post.meta["affiliate"]``) получает брендовую карточку
из ``config/brand_templates.yaml``: тема канала, заголовок поста, партнёрский
чип, QR-код и disclosure. При любой ошибке (нет PIL/segno, битый конфиг)
остаётся прежняя карточка — публикация не ломается.

Точка входа: ``maybe_attach_affiliate_card(post, channel, settings)``
вызывается из ``pipeline.publish_post`` после вставки affiliate-строки.
"""
from __future__ import annotations

import hashlib
import html as html_module
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("content_factory.brand.runtime")

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "brand_templates.yaml"

_TOPIC_BY_CHANNEL = {
    "ai-news": "ai",
    "tech-ai-es": "ai",
    "crypto-news": "crypto",
    "crypto-es": "crypto",
    "sport-news": "sports",
    "futbol-es": "sports",
}

_BRAND_BY_HOST = {
    "bingx": "BingX",
    "bingxdao": "BingX",
    "bitget": "Bitget",
    "mexc": "MEXC",
    "kraken": "Kraken",
    "1xbet": "1xBet",
    "onexbet": "1xBet",
    "n1partners": "N1 Partners",
    "hotmart": "Hotmart",
    "mylead": "MyLead",
    "collaborator": "Collaborator.pro",
}


def enabled(settings: Any) -> bool:
    """Глобальный выключатель: настройки + env BRAND_CARDS."""
    if str(os.environ.get("BRAND_CARDS", "") or "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    try:
        config = settings.publishers.get("brand_cards", {})
    except Exception:  # noqa: BLE001
        config = {}
    if isinstance(config, dict) and config.get("enabled") is False:
        return False
    return CONFIG_PATH.is_file()


def topic_for(channel_id: str, language: str = "en") -> str:
    return _TOPIC_BY_CHANNEL.get(str(channel_id), "ai" if "ai" in str(channel_id) else "crypto")


def _strip_html(text: str) -> str:
    text = html_module.unescape(str(text or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def headline_from_post(text: str, cluster_title: str = "") -> str:
    if cluster_title.strip():
        return cluster_title.strip()
    plain = _strip_html(text)
    lines = [line.strip() for line in plain.splitlines() if line.strip()]
    if not lines:
        return ""
    first = lines[0]
    first = re.sub(r"^[\w\W]{0,3}?\s*", "", first, count=1) if False else first
    return first[:90].rstrip(".")


def subtitle_from_post(text: str, limit: int = 140) -> str:
    plain = _strip_html(text)
    lines = [line.strip() for line in plain.splitlines() if line.strip()]
    body = " ".join(lines[1:]) if len(lines) > 1 else plain
    body = " ".join(body.split())
    return body[: limit - 1].rstrip() + "…" if len(body) > limit else body


def partner_from_url(url: str, title: str = "") -> Dict[str, Any]:
    host = ""
    try:
        host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0])
    except Exception:  # noqa: BLE001
        host = ""
    brand = title or ""
    if not brand:
        for key, name in _BRAND_BY_HOST.items():
            if key in host:
                brand = name
                break
    if not brand:
        brand = host.split(".")[0].capitalize() if host else "Partner"
    return {"key": brand.lower().replace(" ", "-"), "title": brand, "url": url,
            "age_restricted": False, "commission": ""}


def affiliate_link(post: Any, channel: Any) -> str:
    line = str((post.meta or {}).get("affiliate") or "")
    match = re.search(r"https?://[^\s<>\"']+", line)
    if match:
        return match.group(0).rstrip(".,)")
    config = getattr(channel, "affiliate", None) or {}
    if isinstance(config, dict):
        for key in ("link", "tracked_url"):
            value = str(config.get(key) or "").strip()
            if value.startswith(("http://", "https://")):
                return value
    return ""


def _cache_path(post_id: str) -> Path:
    directory = ROOT / "data" / "outbox" / "cards"
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(post_id).encode()).hexdigest()[:12]
    return directory / f"brand-{digest}.png"


def maybe_attach_affiliate_card(post: Any, channel: Any, settings: Any) -> Optional[str]:
    """Рисует брендовую карточку для партнёрского поста; возвращает путь или None."""
    try:
        if not enabled(settings):
            return None
        if not str((post.meta or {}).get("affiliate") or "").strip():
            return None
        if str((post.meta or {}).get("brand_card") or "").strip():
            return None
        link = affiliate_link(post, channel)
        if not link:
            return None
        from . import templates

        config = templates.load_config()
        topic = topic_for(str(getattr(channel, "id", "")))
        partner = partner_from_url(link)
        headline = headline_from_post(str(getattr(post, "text", "") or ""))
        subtitle = subtitle_from_post(str(getattr(post, "text", "") or ""))
        spec = templates.plan(
            config,
            "telegram_post",
            topic,
            "",
            headline=headline or None or "",
            subtitle=subtitle or "",
        )
        spec["partner"] = partner
        target = _cache_path(str(getattr(post, "id", "post")))
        path = templates.render(spec, target.parent)
        # templates.render формирует имя по спеке — переименуем в стабильный кэш
        final = target
        try:
            Path(path).replace(final)
        except OSError:
            final = Path(path)
        post.meta["brand_card"] = str(final)
        post.meta["card_path"] = str(final)  # Telegram отправит брендовую карточку
        post.meta["affiliate_program"] = partner["title"]
        return str(final)
    except Exception as exc:  # noqa: BLE001 - карточка не должна ломать публикацию
        log.debug("Брендовая карточка для %s не создана: %s", getattr(post, "id", "?"), exc)
        return None
