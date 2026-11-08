"""BingX announcements source (notice center / listing announcements).

BingX publishes exchange announcements (listings, delistings, maintenance,
product updates) in a server-rendered notice center:

    https://bingx.com/en/support/notice-center/<section_id>

Sections used by default: Latest Announcements, Spot Listing, Futures Listing.
Each section page contains up to ~20 articles; article pages expose the full
body inside an ``article-body-part`` block (server-rendered), so the adapter can
fetch real text when ``options.full_text: true``.

Options:
    sections: [latest, spot-listing, futures-listing]  # ids/aliases
    max_items: 6          # total articles returned
    full_text: true       # fetch article body (one request per article)
    trust: true           # pipeline: trust this thematic source
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import Settings
from ..models import Article, SourceConfig, utcnow
from ..utils import FetchError, http_get_text, normalize_space, normalize_url, strip_html
from .base import SourceAdapter, build_article

DEFAULT_SECTIONS: Tuple[str, ...] = ("latest", "spot-listing", "futures-listing")
SECTION_IDS: Dict[str, str] = {
    "latest": "360004917494",
    "spot-listing": "11257060005007",
    "futures-listing": "11257015822991",
    "innovation-listing": "13117025062927",
    "product-updates": "11256997796495",
    "asset-maintenance": "11257016265487",
    "system-maintenance": "11523620946319",
}
BASE_URL = "https://bingx.com/en/support/notice-center/"
USER_AGENT = "content-factory-bingx-news/1.0"

_ITEM_RE = re.compile(
    r'<li[^>]*class="[^"]*article-item[^"]*"[^>]*>\s*<a href="([^"]+)"[^>]*>([\s\S]*?)</a>',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r'<div[^>]*class="[^"]*article-title[^"]*"[^>]*>([\s\S]*?)</div>', re.IGNORECASE)
_TIME_RE = re.compile(r'<div[^>]*class="[^"]*article-publish-time[^"]*"[^>]*>([\s\S]*?)</div>', re.IGNORECASE)


def _clean(fragment: str) -> str:
    return normalize_space(unescape(strip_html(fragment or "")))


def _section_id(name: str) -> str:
    key = str(name or "").strip().lower()
    return SECTION_IDS.get(key, key if key.isdigit() else "")


def _parse_date(value: str) -> Any:
    text = _clean(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M"):
        try:
            from datetime import datetime

            return datetime.strptime(text[:10] if len(text) >= 10 else text, fmt.split(" ")[0])
        except ValueError:
            continue
    return utcnow()


def _article_text(page: str) -> str:
    """Extract announcement body text from an article page (best effort)."""
    marker = page.find("article-body-part")
    if marker < 0:
        return ""
    segment = page[marker:marker + 20000]
    segment = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", segment, flags=re.I)
    text = strip_html(segment)
    return normalize_space(text)[:4000]


class BingXAnnouncementsAdapter(SourceAdapter):
    """Собирает анонсы BingX из notice-center."""

    type = "bingx"

    def _sections(self, source: SourceConfig) -> List[str]:
        raw = (source.options or {}).get("sections") or list(DEFAULT_SECTIONS)
        if isinstance(raw, str):
            raw = [raw]
        result: List[str] = []
        for item in raw:
            section_id = _section_id(str(item))
            if section_id and section_id not in result:
                result.append(section_id)
        return result or [SECTION_IDS["latest"]]

    def _fetch_section(self, section_id: str, timeout: float = 20.0) -> str:
        url = BASE_URL + section_id
        try:
            return http_get_text(url, timeout=timeout, user_agent=USER_AGENT)
        except Exception as exc:  # noqa: BLE001 - sources must not crash the pipeline
            raise FetchError(f"BingX notice-center {section_id}: {exc}") from exc

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        options = source.options or {}
        try:
            max_items = max(1, min(40, int(options.get("max_items") or 6)))
        except (TypeError, ValueError):
            max_items = 6
        full_text = bool(options.get("full_text", True))
        articles: List[Article] = []
        seen: set = set()
        for section_id in self._sections(source):
            try:
                page = self._fetch_section(section_id)
            except FetchError:
                if articles:  # одна секция упала — остальные всё равно нужны
                    continue
                raise
            for match in _ITEM_RE.finditer(page):
                href, body = match.group(1), match.group(2)
                title_match = _TITLE_RE.search(body)
                title = _clean(title_match.group(1)) if title_match else ""
                if not title:
                    continue
                url = normalize_url(href if href.startswith("http") else "https://bingx.com" + href)
                if url in seen:
                    continue
                seen.add(url)
                time_match = _TIME_RE.search(body)
                published = _parse_date(time_match.group(1)) if time_match else utcnow()
                text = ""
                if full_text:
                    try:
                        article_page = http_get_text(url, timeout=20.0, user_agent=USER_AGENT)
                        text = _article_text(article_page)
                    except Exception:  # noqa: BLE001 - текст опционален
                        text = ""
                article = build_article(
                    source,
                    settings,
                    url=url,
                    title=title,
                    published_at=published,
                    text=text or title,
                    summary=title,
                    tags=["bingx", section_id],
                    meta={"section_id": section_id, "exchange": "bingx", "short_ok": True},
                )
                if article is not None:
                    articles.append(article)
                if len(articles) >= max_items:
                    return articles
        return articles
