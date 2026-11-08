"""Добровольная поддержка проекта: donate/tip-ссылка в постах (не paywall).

Пользователь просил монетизацию «только на добровольной основе», поэтому
модуль НЕ закрывает контент и НЕ продаёт доступ: он добавляет одну необязательную
строку с ссылкой на добровольную поддержку (Tribute-донат, Boosty-донат,
DonationAlerts и т.п.). Посты остаются бесплатными; блок можно выключить,
ограничить каналами или показывать не в каждом посте.

Конфиг: ``config/support.yaml`` (или env ``SUPPORT_URL``); UTM-метки
проставляются автоматически по каналу — это и есть учёт переходов в аналитике
платформы/лендинга.

Пример:

    enabled: true
    mode: voluntary
    url: "https://tribute.tg/.../donate"
    channels: []          # пусто = все каналы
    frequency: 1          # 1 = каждый пост; 2/3 = детерминированно реже
    text_ru: "❤️ Поддержать проект добровольно: {link}"
    text_en: "❤️ Support the project voluntarily: {link}"
    text_es: "❤️ Apoya el proyecto de forma voluntaria: {link}"
    utm:
      source: telegram
      medium: post
      campaign: voluntary_support
"""
from __future__ import annotations

import html
import logging
import os
import urllib.parse
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = "config/support.yaml"
DEFAULT_TEXTS = {
    "ru": "❤️ Поддержать проект добровольно: {link}",
    "en": "❤️ Support the project voluntarily: {link}",
    "es": "❤️ Apoya el proyecto de forma voluntaria: {link}",
}
DEFAULT_LABELS = {"ru": "по ссылке", "en": "here", "es": "aquí"}
DEFAULT_UTM = {
    "source": "telegram",
    "medium": "post",
    "campaign": "voluntary_support",
}


def load_support_config(settings: Any = None) -> Dict[str, Any]:
    """Прочитать config/support.yaml; пустой dict, если файла/конфига нет."""
    try:
        root = Path(getattr(settings, "root", Path.cwd()))
    except (TypeError, AttributeError):
        root = Path.cwd()
    path = root / CONFIG_PATH
    data: Dict[str, Any] = {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if isinstance(raw, dict):
            data = dict(raw)
    except (OSError, ValueError) as exc:
        logger.warning("support.yaml не прочитан: %s", exc)
        data = {}
    # env позволяет включить поддержку в CI/на сервере без правки файла
    env_url = str(os.environ.get("SUPPORT_URL", "") or "").strip()
    if env_url and not str(data.get("url") or "").strip():
        data["url"] = env_url
    return data


def _language(channel: Any, lang: Optional[str] = None) -> str:
    value = str(lang or getattr(channel, "language", "ru") or "ru").strip().lower()
    if value.startswith("es"):
        return "es"
    if value.startswith("en"):
        return "en"
    return "ru"


def _with_utm(url: str, channel: Any, config: Dict[str, Any], lang: str) -> str:
    """Добавить UTM-метки (source/medium/campaign/content/term) к ссылке."""
    value = str(url or "").strip()
    if not value:
        return ""
    parts = urllib.parse.urlsplit(value)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    utm = dict(DEFAULT_UTM)
    utm.update(
        {str(key): str(val) for key, val in (config.get("utm") or {}).items() if val}
    )
    channel_id = str(getattr(channel, "id", "") or "")
    for key in ("source", "medium", "campaign"):
        raw = str(utm.get(key) or "")
        if not raw:
            continue
        value_fmt = raw.format(channel=channel_id, language=lang) if "{" in raw else raw
        query.setdefault("utm_" + key, value_fmt)
    query.setdefault("utm_content", channel_id)
    query.setdefault("utm_term", lang)
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def support_link(
    channel: Any,
    settings: Any = None,
    lang: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """Готовая ссылка на добровольную поддержку с UTM (или "")."""
    cfg = dict(config) if config is not None else load_support_config(settings)
    if not bool(cfg.get("enabled", False)):
        return ""
    if str(cfg.get("mode") or "voluntary").strip().lower() not in (
        "voluntary",
        "donation",
        "donate",
    ):
        return ""
    channels = [str(item) for item in (cfg.get("channels") or []) if str(item).strip()]
    channel_id = str(getattr(channel, "id", "") or "")
    if channels and channel_id not in channels:
        return ""
    url = str(cfg.get("url") or "").strip()
    if not url:
        return ""
    try:
        frequency = max(1, int(cfg.get("frequency") or 1))
    except (TypeError, ValueError):
        frequency = 1
    if frequency > 1:
        seed = str(getattr(channel, "id", "")) + ":" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if zlib.crc32(seed.encode("utf-8")) % frequency != 0:
            return ""
    return _with_utm(url, channel, cfg, _language(channel, lang))


def _render_template(template: str, link_html: str, lang: str) -> str:
    text = str(template or "")
    if "{link}" in text:
        before, after = text.split("{link}", 1)
        return "<i>{}{}{}</i>".format(
            html.escape(before, quote=False), link_html, html.escape(after, quote=False)
        )
    return "<i>{} {}</i>".format(html.escape(text, quote=False), link_html)


def voluntary_support_block(
    channel: Any,
    settings: Any = None,
    lang: Optional[str] = None,
    seed: str = "",
) -> str:
    """HTML-блок с добровольной поддержкой (пустая строка, если выключено).

    ``seed`` (обычно заголовок поста) позволяет показывать блок не в каждом
    посте детерминированно — без состояния и без лишних записей в БД.
    """
    cfg = load_support_config(settings)
    if not bool(cfg.get("enabled", False)):
        return ""
    channels = [str(item) for item in (cfg.get("channels") or []) if str(item).strip()]
    channel_id = str(getattr(channel, "id", "") or "")
    if channels and channel_id not in channels:
        return ""
    url = str(cfg.get("url") or "").strip()
    if not url:
        return ""
    try:
        frequency = max(1, int(cfg.get("frequency") or 1))
    except (TypeError, ValueError):
        frequency = 1
    if frequency > 1:
        value = "{}:{}:{}".format(
            channel_id,
            seed or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        if zlib.crc32(value.encode("utf-8")) % frequency != 0:
            return ""
    target_lang = _language(channel, lang)
    link_url = _with_utm(url, channel, cfg, target_lang)
    if not link_url:
        return ""
    label = str(
        cfg.get("link_label_{}".format(target_lang))
        or DEFAULT_LABELS[target_lang]
        or DEFAULT_LABELS["ru"]
    )
    link_html = '<a href="{}">{}</a>'.format(
        html.escape(link_url, quote=True), html.escape(label, quote=False)
    )
    template = str(
        cfg.get("text_{}".format(target_lang)) or DEFAULT_TEXTS[target_lang]
    )
    return _render_template(template, link_html, target_lang)
