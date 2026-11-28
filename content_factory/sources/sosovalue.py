"""SoSoValue daily themes as a regular pipeline source.

Every hour the adapter returns at most one "article" per theme whose UTC hour
has come (flows 07, sectors 09, macro 11, sentiment 14, derivatives 16,
ecosystems 18). Article text is the deterministic fact block with all numbers;
the pipeline then generates the post as usual (template + optional LLM headline,
numbers validated against the source text).

Options:
    themes: auto | [flows, sectors, ...]   (auto = due by hour)
    hours: {flows: 7, ...}                 (override the default map)
    language: en | es | ru
    symbols, country_code, top_sectors
    cache_ttl: 1800                        (seconds, shared digest cache)
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..config import Settings
from ..models import Article, SourceConfig, utcnow
from ..sosovalue import build_digest, render, render_summary
from ..utils import FetchError, stable_id
from .base import SourceAdapter

DEFAULT_HOURS = {
    "flows": 7,
    "sectors": 9,
    "macro": 11,
    "sentiment": 14,
    "derivatives": 16,
    "ecosystems": 18,
}
_TAG_RE = re.compile(r"<[^>]+>")


def _plain(fragment: str) -> str:
    text = _TAG_RE.sub("", fragment or "")
    return html_lib.unescape(text).strip()


class SosoValueAdapter(SourceAdapter):
    type = "sosovalue"

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        options = source.options or {}
        if bool(options.get("summary", True)):
            return self._summary_article(source, options, settings)
        themes = self._due_themes(options)
        if not themes:
            return []
        digest = self._digest(options, settings)
        language = str(options.get("language") or "en").lower()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        articles: List[Article] = []
        for theme in themes:
            footer = options.get("footer") or {
                "en": "SoSoValue data · not investment advice",
                "es": "Datos de SoSoValue · no es asesoramiento financiero",
                "ru": "Данные SoSoValue · не инвестиционная рекомендация",
            }.get(language, "")
            body_html = render(theme, digest, lang=language, footer=footer)
            lines = [line.strip() for line in _plain(body_html).splitlines() if line.strip()]
            # No date in the title: two themes on the same day must not look
            # like duplicates to the title-similarity dedupe (threshold 0.72).
            title = (lines[0].split(" · ")[0] if lines else theme).strip()
            # The pipeline works with sentences, not with the compact layout:
            # join the fact lines so the digest template does not glue them.
            body = ". ".join(line.rstrip(".") for line in lines[1:])
            if body and not body.endswith("."):
                body += "."
            articles.append(Article(
                id="soso-%s-%s" % (day, theme),
                title=title,
                # Unique per day AND theme: url_hash drops fragments, and identical
                # URLs would collapse all six themes into one article.
                url="https://sosovalue.com/ru/developer/docs?theme=%s&d=%s" % (theme, day),
                source_id=source.id,
                source_name=source.name,
                published_at=utcnow(),
                text=body,
                summary=body[:300],
                language=language,
                tags=["sosovalue", theme],
                weighted_source_score=float(getattr(source, "weight", 1.0) or 1.0),
                meta={"theme": theme, "sosovalue": True, "prewritten_html": body_html},
            ))
        return articles

    def _summary_article(self, source: SourceConfig, options: Dict[str, Any],
                         settings: Settings) -> List[Article]:
        # SOSO_FORCE_HOUR is a test hook: run the daily post at any hour.
        hour = int(os.environ.get("SOSO_FORCE_HOUR") or options.get("hour_utc", 7))
        if datetime.now(timezone.utc).hour != hour:
            return []
        digest = self._digest(options, settings)
        language = str(options.get("language") or "en").lower()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        footer = options.get("footer") or {
            "en": "SoSoValue data · not investment advice",
            "es": "Datos de SoSoValue · no es asesoramiento financiero",
            "ru": "Данные SoSoValue · не инвестиционная рекомендация",
        }.get(language, "")
        body_html = render_summary(digest, lang=language, footer=footer)
        plain = _plain(body_html)
        lines = [line.strip() for line in plain.splitlines() if line.strip()]
        title = (lines[0].split(" · ")[0] if lines else "Crypto daily").strip()
        body = ". ".join(line.rstrip(".") for line in lines[1:])
        if body and not body.endswith("."):
            body += "."
        return [Article(
            id="soso-summary-%s" % day,
            title=title,
            url="https://sosovalue.com/ru/developer/docs?digest=%s" % day,
            source_id=source.id,
            source_name=source.name,
            published_at=utcnow(),
            text=body,
            summary=body[:300],
            language=language,
            tags=["sosovalue", "digest"],
            weighted_source_score=float(getattr(source, "weight", 1.0) or 1.0),
            meta={"theme": "summary", "sosovalue": True, "prewritten_html": body_html},
        )]

    def _due_themes(self, options: Dict[str, Any]) -> List[str]:
        configured = options.get("themes") or "auto"
        if isinstance(configured, str):
            if configured.lower() != "auto":
                return [t.strip() for t in configured.split(",") if t.strip()]
            hours = dict(DEFAULT_HOURS)
            hours.update({str(k): int(v) for k, v in (options.get("hours") or {}).items()})
            hour = datetime.now(timezone.utc).hour
            return [theme for theme, value in hours.items() if int(value) == hour]
        return [str(t) for t in configured if str(t) in DEFAULT_HOURS]

    def _digest(self, options: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
        if not os.environ.get("SOSO_API_KEY"):
            raise FetchError("SOSO_API_KEY is not set")
        data_dir = Path(getattr(settings, "data_dir", "data"))
        cache_path = data_dir / "sosovalue_digest_cache.json"
        ttl = int(options.get("cache_ttl") or 1800)
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("ts") or 0) < ttl:
                return cached["digest"]
        except (OSError, ValueError, KeyError):
            pass
        digest = build_digest(
            symbols=options.get("symbols") or ["BTC", "ETH"],
            country_code=options.get("country_code") or "US",
            top_sectors=int(options.get("top_sectors") or 3),
        )
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"ts": time.time(), "digest": digest}, ensure_ascii=False),
                                  encoding="utf-8")
        except OSError:
            pass
        return digest
