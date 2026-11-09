#!/usr/bin/env python3
"""Ротация постов для Fediverse (Akkoma): крипто → AI → travel-реклама.

Примеры:
    python scripts/fediverse_mix.py --dry-run          # показать следующий пост
    python scripts/fediverse_mix.py --once             # опубликовать следующий
    python scripts/fediverse_mix.py --sequence 3       # опубликовать 3 поста по кругу
    python scripts/fediverse_mix.py --topic ai         # внеочередной пост

Настройки — config/fediverse_mix.yaml. Аккаунт/токен — AKKOMA_BASE_URL/AKKOMA_TOKEN.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from content_factory.integrations.bingx import BingXClient  # noqa: E402
from content_factory.utils import load_dotenv  # noqa: E402

log = logging.getLogger("fediverse_mix")


def load_config(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def read_state(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def write_state(path: Path, state: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        log.warning("state save failed: %s", exc)


def market_line(client: Optional[BingXClient] = None) -> str:
    client = client or BingXClient()
    parts: List[str] = []
    for symbol in ("BTC/USDT", "ETH/USDT", "SOL/USDT"):
        try:
            t = client.ticker(symbol)
            price = float(t.get("price") or 0)
            change = float(t.get("percent_change") or 0)
            base = symbol.split("/")[0]
            text = "${:,.0f}".format(price) if price >= 1000 else "${:,.2f}".format(price)
            parts.append("{} {} ({:+.2f}%)".format(base, text, change))
        except Exception:  # noqa: BLE001
            continue
    return " · ".join(parts)


def _with_credit(text: str, article: Optional[Dict[str, Any]]) -> str:
    if not article:
        return text
    credit = "📷 Photo: {} — {}".format(article.get("source", ""), article.get("link", ""))
    parts = text.rstrip().split("\n\n#", 1)
    if len(parts) == 2:
        return parts[0].rstrip() + "\n\n" + credit + "\n\n#" + parts[1]
    return text.rstrip() + "\n\n" + credit


def build_post(config: Dict[str, Any], topic: str, index: int, article: Optional[Dict[str, Any]] = None, deal: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    templates = config.get("templates") or {}
    template = str(templates.get(topic) or "").strip()
    if not template:
        raise ValueError("no template for topic {!r}".format(topic))
    offers = [o for o in (config.get("travel_offers") or []) if isinstance(o, dict) and o.get("link")]
    offer = offers[index % len(offers)] if offers else {}
    travel_link = (os.environ.get("TRAVEL_AFFILIATE_URL", "") or "").strip() or offer.get("link") or config.get("travel_link", "")
    if deal:
        tracker_base = (os.environ.get("LINK_TRACKER_BASE", "") or "").strip().rstrip("/")
        code = str(deal.get("tracker_code") or "travel-deal")
        travel_link = (tracker_base + "/r/" + code) if tracker_base else str(deal.get("link") or travel_link)
    values: Dict[str, Any] = {
        "telegram_crypto": config.get("telegram_crypto", ""),
        "telegram_ai": config.get("telegram_ai", ""),
        "travel_link": travel_link,
        "travel_disclosure": config.get("travel_disclosure", "Ad · partner link."),
        "travel_headline": (article or {}).get("title") or (config.get("travel_headlines") or ["Travel season is back — flights, hotels and city breaks are moving fast."])[index % len(config.get("travel_headlines") or [1])],
        "travel_cta": str((deal or {}).get("cta") or offer.get("cta") or "Plan the next trip"),
    }
    meta: Dict[str, Any] = {}
    if topic == "travel" and deal:
        values["travel_headline"] = str(deal.get("headline") or values["travel_headline"])
    elif topic == "travel" and article:
        values["travel_headline"] = article.get("title") or values["travel_headline"]
    if topic == "crypto":
        headlines = config.get("crypto_headlines") or ["Crypto markets update."]
        values["headline"] = (article or {}).get("title") or headlines[index % len(headlines)]
        values["market_line"] = market_line()
        meta["headline"] = values["headline"]
        meta["market"] = values["market_line"]
        try:
            from content_factory.integrations.bingx import BingXClient
            meta["klines"] = BingXClient().klines("BTC/USDT", "1h", 24)
        except Exception:  # noqa: BLE001
            meta["klines"] = []
    if topic == "ai":
        angles = config.get("ai_angles") or ["AI and trading are converging."]
        values["ai_angle"] = (article or {}).get("title") or angles[index % len(angles)]
        meta["angle"] = values["ai_angle"]
    meta["article"] = article or {}
    meta["deal"] = deal or {}
    return _with_credit(template.format(**values), article), meta


def publish(status: str, timeout: float = 30.0) -> Dict[str, Any]:
    base = (os.environ.get("AKKOMA_BASE_URL", "") or "").strip().rstrip("/")
    token = (os.environ.get("AKKOMA_TOKEN", "") or "").strip()
    if not base or not token:
        raise RuntimeError("AKKOMA_BASE_URL/AKKOMA_TOKEN не заданы")
    request = urllib.request.Request(
        base + "/api/v1/statuses",
        data=json.dumps({"status": status, "visibility": "public", "language": "en"}).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "content-factory-fediverse/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace") or "{}")


BG = (16, 20, 28)
FG = (240, 244, 248)
MUTED = (150, 165, 180)
ACCENTS = {"crypto": (247, 147, 26), "ai": (99, 179, 237), "travel": (72, 187, 150)}
WIDTH, HEIGHT = 1200, 675


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    words = str(text or "").split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:5]


def _gradient(width: int, height: int, top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return img


def _footer(draw: ImageDraw.ImageDraw, width: int, height: int, text: str) -> None:
    font = _font(24)
    draw.text((60, height - 64), text, font=font, fill=MUTED)


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def _http_get(url: str, timeout: float = 15.0) -> Tuple[int, bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(), response.headers.get("content-type", "")


def _rss_items(xml_text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for node in root.iter():
        if node.tag.split("}")[-1] != "item" and node.tag.split("}")[-1] != "entry":
            continue
        raw = ET.tostring(node, encoding="unicode")
        data: Dict[str, str] = {"raw": raw}
        for child in node:
            name = child.tag.split("}")[-1]
            if name in ("title", "link", "pubDate", "published", "updated", "description", "summary"):
                text = (child.text or "").strip()
                if name == "link" and not text:
                    text = child.attrib.get("href", "")
                data.setdefault(name, text)
        items.append(data)
    return items


_IMAGE_RE = re.compile(r'(?:media:content|media:thumbnail|enclosure)[^>]*?url="([^"]+)"', re.I)
_IMG_TAG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_OG_IMAGE_RE = re.compile(r'<meta[^>]+(?:property|name)="(?:og:image|twitter:image)"[^>]+content="([^"]+)"', re.I)


def _item_image_url(item: Dict[str, str]) -> str:
    raw = item.get("raw", "")
    for match in _IMAGE_RE.finditer(raw):
        url = match.group(1)
        if re.search(r"\.(jpg|jpeg|png|webp|avif)(\?|$)", url, re.I):
            return url
    match = _IMG_TAG_RE.search(item.get("description", "") or raw)
    if match:
        return match.group(1)
    return ""


def _og_image(html: str) -> str:
    match = _OG_IMAGE_RE.search(html)
    return match.group(1) if match else ""


def _parse_pub(item: Dict[str, str]) -> Optional[datetime]:
    for key in ("pubDate", "published", "updated"):
        value = item.get(key)
        if not value:
            continue
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(value.replace("GMT", "+0000"), fmt)
            except ValueError:
                continue
    return None


def _download_image(url: str, max_bytes: int = 8 * 1024 * 1024) -> Optional[Image.Image]:
    try:
        status, data, content_type = _http_get(url, timeout=20.0)
        if status != 200 or len(data) > max_bytes:
            return None
        if content_type and "image" not in content_type and not url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
            return None
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def _cover(image: Image.Image, width: int = WIDTH, height: int = HEIGHT) -> Image.Image:
    ratio = max(width / image.width, height / image.height)
    resized = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _topic_feeds(topic: str, config: Dict[str, Any]) -> List[str]:
    article_config = config.get("article_images") or {}
    override = (article_config.get("feeds") or {}).get(topic) or []
    if override:
        return [str(u) for u in override if str(u).strip()]
    channel_ids = {"crypto": "crypto-news", "ai": "ai-news"}
    channel_id = channel_ids.get(topic)
    if not channel_id:
        return []
    path = Path(str(article_config.get("channels_config") or "config/channels.en.yaml"))
    if not path.is_absolute():
        path = ROOT / path
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return []
    channels = data.get("channels") if isinstance(data, dict) else []
    for channel in channels or []:
        if channel.get("id") != channel_id:
            continue
        feeds = []
        for source in channel.get("sources") or []:
            if str(source.get("type") or "").lower() != "rss":
                continue
            url = str(source.get("url") or "").strip()
            if url:
                feeds.append(url)
        limit = int(article_config.get("max_feeds") or 4)
        return feeds[:limit]
    return []


def find_article(topic: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Свежая статья с картинкой: {title, link, source, image}."""
    article_config = config.get("article_images") or {}
    if article_config.get("enabled") is False:
        return None
    max_age_hours = float(article_config.get("max_age_hours") or 48)
    max_candidates = int(article_config.get("max_candidates") or 6)
    now = datetime.now(timezone.utc)
    for feed in _topic_feeds(topic, config):
        try:
            _, body, _ = _http_get(feed, timeout=15.0)
            items = _rss_items(body.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            continue
        source = urllib.parse.urlparse(feed).netloc
        checked = 0
        for item in items:
            published = _parse_pub(item)
            if published is not None:
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if (now - published).total_seconds() > max_age_hours * 3600:
                    continue
            link = str(item.get("link") or "").strip()
            title = str(item.get("title") or "").strip()
            if not link or not title:
                continue
            image_url = _item_image_url(item)
            if not image_url:
                try:
                    _, page, _ = _http_get(link, timeout=25.0)
                    image_url = _og_image(page.decode("utf-8", "replace"))
                except Exception:  # noqa: BLE001
                    image_url = ""
            checked += 1
            if image_url:
                image = _download_image(image_url)
                if image is not None and image.width >= 500:
                    return {"title": title, "link": link, "source": source, "image": _cover(image)}
            if checked >= max_candidates:
                break
    return None


def make_crypto_card(headline: str, market: str, klines: Optional[List[Dict[str, Any]]] = None) -> Image.Image:
    img = _gradient(WIDTH, HEIGHT, (18, 24, 34), (10, 13, 18))
    draw = ImageDraw.Draw(img)
    accent = ACCENTS["crypto"]
    draw.rectangle([0, 0, 14, HEIGHT], fill=accent)
    title_font = _font(54, bold=True)
    y = 70
    for line in _wrap(headline, title_font, WIDTH - 140, draw):
        draw.text((60, y), line, font=title_font, fill=FG)
        y += 66
    # sparkline
    closes = [float(k.get("close") or 0) for k in (klines or []) if k.get("close")]
    if len(closes) >= 2:
        chart_top, chart_bottom = y + 30, HEIGHT - 215
        left, right = 70, WIDTH - 70
        lo, hi = min(closes), max(closes)
        span = max(hi - lo, 1e-9)
        points = []
        for i, value in enumerate(closes):
            x = left + (right - left) * i / (len(closes) - 1)
            yy = chart_bottom - (chart_bottom - chart_top) * (value - lo) / span
            points.append((x, yy))
        draw.line(points, fill=accent, width=6, joint="curve")
        draw.text((left, chart_bottom + 14), "BTC/USDT · 24h trend", font=_font(26), fill=MUTED)
    market_font = _font(34)
    y_market = HEIGHT - 140
    for line in _wrap(market, market_font, WIDTH - 140, draw):
        draw.text((60, y_market), line, font=market_font, fill=accent)
        y_market += 44
    _footer(draw, WIDTH, HEIGHT, "Crypto & Blockchain · t.me/HOOPY0007")
    return img


def make_ai_card(angle: str, footer: str = "AI + Crypto · t.me/AINEWS0007") -> Image.Image:
    img = _gradient(WIDTH, HEIGHT, (20, 30, 46), (12, 14, 24))
    draw = ImageDraw.Draw(img)
    accent = ACCENTS["ai"]
    draw.rectangle([0, 0, 14, HEIGHT], fill=accent)
    draw.text((60, 80), "AI × TRADING", font=_font(34, bold=True), fill=accent)
    draw.line([(60, 140), (260, 140)], fill=accent, width=4)
    _decor_ai(draw)
    title_font = _font(52, bold=True)
    y = 180
    for line in _wrap(angle, title_font, 700, draw):
        draw.text((60, y), line, font=title_font, fill=FG)
        y += 64
    draw.text((60, HEIGHT - 170), "AI adds speed — discipline still wins.", font=_font(32), fill=MUTED)
    _footer(draw, WIDTH, HEIGHT, footer)
    return img


def make_travel_card() -> Image.Image:
    img = _gradient(WIDTH, HEIGHT, (24, 60, 72), (18, 28, 30))
    draw = ImageDraw.Draw(img)
    accent = ACCENTS["travel"]
    draw.rectangle([0, 0, 14, HEIGHT], fill=accent)
    draw.text((60, 90), "TRAVEL DEALS", font=_font(36, bold=True), fill=accent)
    draw.line([(60, 150), (300, 150)], fill=accent, width=4)
    _decor_travel(draw)
    title_font = _font(56, bold=True)
    y = 200
    for line in _wrap("Flights, hotels and city breaks — plan the next trip.", title_font, 700, draw):
        draw.text((60, y), line, font=title_font, fill=FG)
        y += 70
    draw.text((60, HEIGHT - 160), "Ad · travel partner · prices vary", font=_font(28), fill=MUTED)
    _footer(draw, WIDTH, HEIGHT, "Travel partner · tracked link")
    return img


def _decor_ai(draw: ImageDraw.ImageDraw) -> None:
    """Нейросеть: узлы и связи справа."""
    import math
    nodes = [(980, 150), (1100, 230), (1010, 330), (1110, 430), (960, 480), (1080, 560)]
    for i, (x1, y1) in enumerate(nodes):
        for x2, y2 in nodes[i + 1:]:
            if math.dist((x1, y1), (x2, y2)) < 190:
                draw.line([(x1, y1), (x2, y2)], fill=(45, 70, 100), width=2)
    for x, y in nodes:
        draw.ellipse([x - 10, y - 10, x + 10, y + 10], fill=(99, 179, 237))


def _decor_travel(draw: ImageDraw.ImageDraw) -> None:
    """Солнце, горы и самолёт справа."""
    draw.ellipse([880, 90, 1040, 250], fill=(250, 200, 120))
    draw.polygon([(820, 560), (980, 330), (1140, 560)], fill=(38, 92, 100))
    draw.polygon([(960, 560), (1080, 400), (1200, 560)], fill=(30, 74, 82))
    draw.line([(860, 240), (1000, 300)], fill=(240, 244, 248), width=7)
    draw.polygon([(1000, 300), (940, 280), (960, 310)], fill=(240, 244, 248))


CITY_NAMES = {
    "ATL": "Atlanta", "ORL": "Orlando", "MIA": "Miami", "DFW": "Dallas", "DTT": "Detroit",
    "IST": "Istanbul", "LON": "London", "PAR": "Paris", "ROM": "Rome", "BCN": "Barcelona",
    "MAD": "Madrid", "LIS": "Lisbon", "BER": "Berlin", "AMS": "Amsterdam", "DXB": "Dubai",
    "BKK": "Bangkok", "TYO": "Tokyo", "SIN": "Singapore", "MEX": "Mexico City", "CUN": "Cancun",
    "BUE": "Buenos Aires", "SAO": "Sao Paulo", "BOG": "Bogota", "LIM": "Lima", "SCL": "Santiago",
    "LAX": "Los Angeles", "NYC": "New York", "ORD": "Chicago", "SFO": "San Francisco",
    "SEA": "Seattle", "BOS": "Boston", "DEN": "Denver", "LAS": "Las Vegas", "HNL": "Honolulu",
    "YTO": "Toronto", "YVR": "Vancouver", "MOW": "Moscow", "LED": "St. Petersburg",
}


def _http_json(url: str, timeout: float = 25.0) -> Optional[Dict[str, Any]]:
    try:
        _, body, _ = _http_get(url, timeout=timeout)
        data = json.loads(body.decode("utf-8", "replace"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def fetch_travel_deal(topic: str, config: Dict[str, Any], index: int = 0) -> Optional[Dict[str, Any]]:
    """Дешёвый билет из Travelpayouts prices API -> headline + deep link."""
    deal_cfg = config.get("travel_deals") or {}
    if deal_cfg.get("enabled") is False:
        return None
    token = (os.environ.get(str(deal_cfg.get("api_token_env") or "TRAVELPAYOUTS_TOKEN"), "") or "").strip()
    if not token:
        return None
    origins = [str(o) for o in (deal_cfg.get("origins_es" if topic.endswith("-es") else "origins") or deal_cfg.get("origins") or ["NYC"])]
    limit = int(deal_cfg.get("limit") or 30)
    max_days = int(deal_cfg.get("max_days_ahead") or 90)
    min_price = float(deal_cfg.get("min_price") or 40)
    currency = str(deal_cfg.get("currency") or "usd")
    now = datetime.now(timezone.utc)
    deals: List[Dict[str, Any]] = []
    for origin in origins:
        url = "https://api.travelpayouts.com/v2/prices/latest?" + urllib.parse.urlencode(
            {"origin": origin, "currency": currency, "limit": limit, "token": token}
        )
        data = _http_json(url)
        for item in (data or {}).get("data") or []:
            try:
                depart = datetime.strptime(str(item.get("depart_date")), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            days = (depart - now).days
            if days < 1 or days > max_days:
                continue
            value = float(item.get("value") or 0)
            dest = str(item.get("destination") or "")
            if value < min_price or not dest or dest == origin:
                continue
            deals.append({
                "origin": origin, "dest": dest,
                "origin_name": CITY_NAMES.get(origin, origin),
                "dest_name": CITY_NAMES.get(dest, dest),
                "price": int(round(value)), "currency": currency.upper(),
                "depart_date": item.get("depart_date"), "return_date": item.get("return_date"),
                "gate": item.get("gate") or "",
            })
        time.sleep(0.4)
    if not deals:
        return None
    deals.sort(key=lambda d: (d["price"], d["depart_date"]))
    chosen = deals[index % min(len(deals), 5)] if index else deals[0]
    try:
        depart = datetime.strptime(chosen["depart_date"], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None

    def _fmt(value: str) -> str:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").strftime("%b %-d")
        except (TypeError, ValueError):
            return str(value)

    route = "{}{}{}1".format(chosen["origin"], depart.strftime("%d%m"), chosen["dest"])
    marker = str(deal_cfg.get("marker") or "674170")
    chosen["link"] = "https://www.aviasales.com/search/{}?marker={}".format(route, marker)
    dates = _fmt(chosen.get("depart_date") or "")
    if chosen.get("return_date"):
        dates += "–" + _fmt(chosen["return_date"])
    chosen["headline"] = "{} → {} from ${} round trip · {}".format(
        chosen["origin_name"], chosen["dest_name"], chosen["price"], dates
    )
    chosen["cta"] = "Compare flights"
    chosen["tracker_code"] = str(deal_cfg.get("tracker_code") or "travel-deal")
    return chosen


def upsert_tracker_link(code: str, target: str, label: str) -> bool:
    base = (os.environ.get("LINK_TRACKER_BASE", "") or "").strip().rstrip("/")
    token = (os.environ.get("LINK_TRACKER_ADMIN_TOKEN", "") or "").strip()
    if not base or not token or not target:
        return False
    payload = json.dumps({
        "code": code, "target": target, "channel": "akkoma",
        "network": "travelpayouts", "label": label[:80],
    }).encode()
    request = urllib.request.Request(
        base + "/admin/links", data=payload,
        headers={"content-type": "application/json", "x-token": token, "User-Agent": "content-factory-fediverse/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200
    except Exception:  # noqa: BLE001
        return False


def make_deal_card(deal: Dict[str, Any]) -> Image.Image:
    img = _gradient(WIDTH, HEIGHT, (18, 52, 66), (12, 26, 30))
    draw = ImageDraw.Draw(img)
    accent = ACCENTS["travel"]
    draw.rectangle([0, 0, 14, HEIGHT], fill=accent)
    draw.text((60, 70), "FLIGHT DEAL", font=_font(34, bold=True), fill=accent)
    draw.line([(60, 128), (280, 128)], fill=accent, width=4)
    title_font = _font(64, bold=True)
    y = 180
    for line in _wrap("{} to {}".format(deal["origin_name"], deal["dest_name"]), title_font, WIDTH - 120, draw):
        draw.text((60, y), line, font=title_font, fill=FG)
        y += 78
    draw.text((60, y + 10), "from ${}".format(deal["price"]), font=_font(84, bold=True), fill=accent)
    dates = str(deal.get("depart_date") or "")
    if deal.get("return_date"):
        dates += " – " + str(deal.get("return_date"))
    draw.text((60, HEIGHT - 150), "Round trip · " + dates, font=_font(28), fill=MUTED)
    _footer(draw, WIDTH, HEIGHT, "Travel partner · tracked link")
    return img


def build_card(topic: str, config: Dict[str, Any], headline: str, market: str, angle: str, klines: Optional[List[Dict[str, Any]]] = None) -> Optional[Image.Image]:
    image_config = config.get("image") or {}
    if image_config.get("enabled") is False:
        return None
    if topic == "crypto":
        return make_crypto_card(headline, market, klines)
    if topic == "ai":
        return make_ai_card(angle)
    if topic == "travel":
        return make_travel_card()
    return None


def upload_media(image: Image.Image, timeout: float = 60.0) -> str:
    base = (os.environ.get("AKKOMA_BASE_URL", "") or "").strip().rstrip("/")
    token = (os.environ.get("AKKOMA_TOKEN", "") or "").strip()
    if not base or not token:
        raise RuntimeError("AKKOMA_BASE_URL/AKKOMA_TOKEN не заданы")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()
    boundary = "----contentfactory{}".format(int(time.time() * 1000))
    body = b"".join([
        ("--%s\r\n" % boundary).encode(),
        b'Content-Disposition: form-data; name="file"; filename="card.png"\r\n',
        b"Content-Type: image/png\r\n\r\n",
        payload,
        ("\r\n--%s--\r\n" % boundary).encode(),
    ])
    request = urllib.request.Request(
        base + "/api/v2/media",
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Accept": "application/json",
            "User-Agent": "content-factory-fediverse/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8", "replace") or "{}")
    return str(data.get("id") or "")


def publish(status: str, media_ids: Optional[List[str]] = None, timeout: float = 30.0) -> Dict[str, Any]:
    base = (os.environ.get("AKKOMA_BASE_URL", "") or "").strip().rstrip("/")
    token = (os.environ.get("AKKOMA_TOKEN", "") or "").strip()
    if not base or not token:
        raise RuntimeError("AKKOMA_BASE_URL/AKKOMA_TOKEN не заданы")
    payload: Dict[str, Any] = {"status": status, "visibility": "public", "language": "en"}
    if media_ids:
        payload["media_ids"] = media_ids
    request = urllib.request.Request(
        base + "/api/v1/statuses",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "content-factory-fediverse/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace") or "{}")


def _multipart_body(image: Image.Image, field: str = "file") -> Tuple[bytes, str]:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()
    boundary = "----contentfactory{}".format(int(time.time() * 1000))
    body = b"".join([
        ("--%s\r\n" % boundary).encode(),
        ('Content-Disposition: form-data; name="%s"; filename="card.png"\r\n' % field).encode(),
        b"Content-Type: image/png\r\n\r\n",
        payload,
        ("\r\n--%s--\r\n" % boundary).encode(),
    ])
    return body, boundary


def _strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+", "", text).rstrip()


def mastodon_publish(text: str, image: Optional[Image.Image] = None, timeout: float = 30.0, strip_links: Optional[bool] = None) -> Optional[str]:
    """Дублирует пост в Mastodon (если заданы MASTODON_BASE_URL/MASTODON_TOKEN)."""
    base = (os.environ.get("MASTODON_BASE_URL", "") or "").strip().rstrip("/")
    token = (os.environ.get("MASTODON_TOKEN", "") or "").strip()
    if not base or not token:
        return None
    body_text = text
    env_strip = str(os.environ.get("MASTODON_NO_LINKS", "") or "").strip().lower() in {"1", "true", "yes", "on"}
    should_strip = env_strip if strip_links is None else bool(strip_links)
    if should_strip:
        body_text = _strip_urls(body_text)
    media_ids: List[str] = []
    if image is not None:
        body, boundary = _multipart_body(image)
        request = urllib.request.Request(
            base + "/api/v2/media",
            data=body,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "multipart/form-data; boundary=" + boundary,
                "Accept": "application/json",
                "User-Agent": "content-factory-fediverse/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", "replace") or "{}")
            media_id = str(data.get("id") or "")
            if media_id:
                media_ids = [media_id]
        except Exception as exc:  # noqa: BLE001
            log.warning("Mastodon media upload failed: %s", exc)
    payload = {"status": body_text, "visibility": "public", "language": "en"}
    if media_ids:
        payload["media_ids"] = media_ids
    request = urllib.request.Request(
        base + "/api/v1/statuses",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "content-factory-fediverse/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace") or "{}")
        return str(data.get("url") or data.get("id") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("Mastodon publish failed: %s", exc)
        return None


def pixelfed_publish(text: str, image: Optional[Image.Image] = None, timeout: float = 90.0) -> Optional[str]:
    """Дублирует пост в Pixelfed (PIXELFED_BASE_URL/PIXELFED_TOKEN)."""
    base = (os.environ.get("PIXELFED_BASE_URL", "") or "").strip().rstrip("/")
    token = (os.environ.get("PIXELFED_TOKEN", "") or "").strip()
    if not base or not token:
        return None
    media_ids: List[str] = []
    if image is not None:
        # pixelfed.au: крупные картинки иногда обрывают обработку — пробуем
        # несколько уменьшений, пока один из вариантов не загрузится.
        max_width = int(os.environ.get("PIXELFED_MAX_WIDTH", "450") or 450)
        for width in (max_width, 320, 280):
            if width > max_width:
                continue
            width = min(width, image.width)
            resized = image.copy()
            if width < image.width:
                resized = image.resize((width, max(1, int(image.height * width / image.width))), Image.LANCZOS)
            buffer = io.BytesIO()
            resized.convert("RGB").save(buffer, format="JPEG", quality=80)
            payload = buffer.getvalue()
            for attempt in range(2):
                boundary = "----contentfactory{}".format(int(time.time() * 1000) + attempt)
                body = b"".join([
                    ("--%s\r\n" % boundary).encode(),
                    b'Content-Disposition: form-data; name="file"; filename="card.jpg"\r\n',
                    b"Content-Type: image/jpeg\r\n\r\n",
                    payload,
                    ("\r\n--%s--\r\n" % boundary).encode(),
                ])
                request = urllib.request.Request(
                    base + "/api/v1/media",
                    data=body,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "multipart/form-data; boundary=" + boundary,
                        "Accept": "application/json",
                        "User-Agent": "content-factory-fediverse/1.0",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=45.0) as response:
                        data = json.loads(response.read().decode("utf-8", "replace") or "{}")
                    if data.get("id"):
                        media_ids = [str(data["id"])]
                        break
                except Exception as exc:  # noqa: BLE001
                    log.warning("Pixelfed media upload failed (%dpx, try %d): %s", width, attempt + 1, exc)
            if media_ids:
                break
        if not media_ids:
            log.warning("Pixelfed: media upload failed at all sizes; skipping post")
            return None
    status_payload: Dict[str, Any] = {"status": text, "visibility": "public"}
    if media_ids:
        status_payload["media_ids"] = media_ids
    request = urllib.request.Request(
        base + "/api/v1/statuses",
        data=json.dumps(status_payload).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "content-factory-fediverse/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace") or "{}")
        return str(data.get("url") or data.get("uri") or data.get("id") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("Pixelfed publish failed: %s", exc)
        return None


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fediverse content mix (crypto/AI/travel)")
    parser.add_argument("--config", default="config/fediverse_mix.yaml")
    parser.add_argument("--state", default="")
    parser.add_argument("--once", action="store_true", help="опубликовать следующий пост")
    parser.add_argument("--sequence", type=int, default=0, help="опубликовать N постов по кругу")
    parser.add_argument("--topic", choices=("crypto", "ai", "travel"), default="", help="внеочередной пост")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=5.0)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv(ROOT / ".env")
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = load_config(config_path)
    if config.get("enabled") is False:
        print("fediverse mix disabled")
        return 0
    state_path = Path(args.state) if args.state else ROOT / str(config.get("state_path") or "data/fediverse_mix_state.json")
    state = read_state(state_path)
    rotation = [str(t).strip().lower() for t in (config.get("rotation") or ["crypto", "ai", "travel"]) if str(t).strip()]
    if not rotation:
        print("empty rotation")
        return 1
    index = int(state.get("index") or 0)
    total = args.sequence or (1 if args.once or args.topic else 1)
    for step in range(total):
        topic = args.topic or rotation[(index + step) % len(rotation)]
        try:
            deal = fetch_travel_deal(topic, config, index + step) if topic.startswith("travel") else None
            if deal:
                upsert_tracker_link(
                    str(deal.get("tracker_code") or "travel-deal"),
                    str(deal.get("link") or ""),
                    "{} → {} ${} {}".format(deal.get("origin_name"), deal.get("dest_name"), deal.get("price"), deal.get("depart_date")),
                )
                print("deal:", deal.get("headline"))
            article = find_article(topic, config) if not deal else None
            if article:
                print("article:", article.get("title", "")[:90], "|", article.get("source", ""))
            text, meta = build_post(config, topic, index + step, article, deal)
        except (ValueError, KeyError) as exc:
            print("build error:", exc)
            return 1
        print("--- {} ---\n{}\n".format(topic, text))
        if args.dry_run:
            continue
        try:
            deal_meta = meta.get("deal") or {}
            if deal_meta:
                image = make_deal_card(deal_meta)
            else:
                image = (meta.get("article") or {}).get("image") or build_card(
                    topic,
                    config,
                    meta.get("headline", ""),
                    meta.get("market", ""),
                    meta.get("angle", ""),
                    meta.get("klines"),
                )
            if image is not None:
                image_path = ROOT / "data" / "outbox" / "fediverse" / "card-{}.png".format(int(time.time()))
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(image_path)
                print("image:", image_path)
            media_ids: List[str] = []
            if image is not None:
                try:
                    media_id = upload_media(image)
                    if media_id:
                        media_ids = [media_id]
                        print("media uploaded:", media_id)
                except Exception as exc:  # noqa: BLE001
                    print("media upload failed (posting text only):", type(exc).__name__, exc)
            error = None
            pixelfed_done = False
            try:
                result = publish(text, media_ids)
                print("published (primary):", result.get("url") or result.get("id"))
            except Exception as exc:  # noqa: BLE001 - основной инстанс мог умереть
                error = exc
                print("primary publish failed:", type(exc).__name__, exc)
            if error is not None:
                # Аварийный путь: пост не должен теряться из-за мёртвого инстанса.
                px_url = pixelfed_publish(text, image)
                if px_url:
                    print("fallback pixelfed:", px_url)
                    pixelfed_done = True
                else:
                    mast_url = mastodon_publish(text, image)
                    if mast_url:
                        print("fallback mastodon:", mast_url)
                    else:
                        print("all publishers failed")
                        return 1
            crosspost_cfg = config.get("crosspost") or {}
            if crosspost_cfg.get("mastodon"):
                mast_url = mastodon_publish(
                    text,
                    image,
                    strip_links=crosspost_cfg.get("mastodon_strip_links"),
                )
                print("mastodon:", mast_url or "skipped/failed")
            if crosspost_cfg.get("pixelfed") and image is not None and not pixelfed_done:
                px_url = pixelfed_publish(text, image)
                print("pixelfed:", px_url or "skipped/failed")
        except Exception as exc:  # noqa: BLE001
            print("publish failed:", type(exc).__name__, exc)
            return 1
        time.sleep(max(1.0, float(args.delay)))
    if not args.dry_run:
        state["index"] = index + total
        state["last_topic"] = args.topic or rotation[(index + total - 1) % len(rotation)]
        write_state(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
