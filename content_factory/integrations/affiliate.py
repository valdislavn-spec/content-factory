"""Referral/affiliate line for channel posts (config-driven, with disclosure).

Config block on a channel (``config/channels.*.yaml``)::

    affiliate:
      enabled: true
      link: "https://bingxdao.com/invite/WYYEGK/"
      every_n_posts: 3
      disclaimer: "Ad · affiliate link. Not available in the US, UK, Canada…"
      texts:                      # optional per-language overrides
        en: "🤝 Trade crypto on BingX (ad · affiliate link): {link}"

Link resolution order: ``AFFILIATE_LINK_<CHANNEL_ID>`` env var, then
``AFFILIATE_LINK``, then the YAML ``link``. This keeps the link out of git if
needed while allowing per-channel links.

The line is inserted once per ``every_n_posts`` posts (first post of the day
gets it), right before the trailing hashtag block, and is never added if the
link is missing/invalid — a broken link must not reach a post.
"""

from __future__ import annotations

import os
from typing import Any, Dict

DEFAULT_TEXTS: Dict[str, str] = {
    "en": "🤝 Trade crypto on BingX (ad · affiliate link): {link}",
    "es": "🤝 Opera con cripto en BingX (anuncio · enlace de afiliado): {link}",
    "ru": "🤝 Торгуйте криптой на BingX (реклама · партнёрская ссылка): {link}",
}


def _env_link(channel_id: str = "") -> str:
    """Env override: AFFILIATE_LINK_<CHANNEL_ID> → AFFILIATE_LINK → ""."""
    if channel_id:
        key = "AFFILIATE_LINK_" + str(channel_id).upper().replace("-", "_").replace(".", "_")
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return os.environ.get("AFFILIATE_LINK", "").strip()


def valid_link(link: str) -> bool:
    link = str(link or "").strip()
    return link.startswith(("http://", "https://")) and " " not in link and len(link) <= 500


def resolve_link(config: Dict[str, Any], channel_id: str = "") -> str:
    config = config if isinstance(config, dict) else {}
    link = _env_link(channel_id) or str(config.get("link") or "").strip()
    return link if valid_link(link) else ""


def build_affiliate_line(
    config: Dict[str, Any], language: str = "en", channel_id: str = ""
) -> str:
    """Returns the ready line, or "" when disabled/link missing."""
    config = config if isinstance(config, dict) else {}
    if not config.get("enabled"):
        return ""
    link = resolve_link(config, channel_id)
    if not link:
        return ""
    lang = str(language or "en").strip().lower() or "en"
    texts = config.get("texts") or {}
    template = (
        str(texts.get(lang) or "")
        or str(texts.get("en") or "")
        or DEFAULT_TEXTS.get(lang)
        or DEFAULT_TEXTS["en"]
    )
    try:
        line = template.format(link=link)
    except (KeyError, IndexError, ValueError):
        line = "{} {}".format(template, link)
    disclaimer = str(config.get("disclaimer") or "").strip()
    if disclaimer:
        line = "{}\n{}".format(line, disclaimer)
    return line


def should_show(index: int, every_n_posts: int) -> bool:
    """True when the post with 0-based ``index`` should carry the line."""
    try:
        every_n = int(every_n_posts or 1)
    except (TypeError, ValueError):
        every_n = 1
    if every_n <= 1:
        return True
    return int(index) % every_n == 0


def insert_line(text: str, line: str) -> str:
    """Insert before the trailing hashtag block (same helper as market line)."""
    if not line:
        return text
    from .marketline import insert_before_hashtags

    return insert_before_hashtags(text, line)
