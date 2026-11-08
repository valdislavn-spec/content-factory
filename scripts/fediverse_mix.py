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


def build_post(config: Dict[str, Any], topic: str, index: int, article: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    templates = config.get("templates") or {}
    template = str(templates.get(topic) or "").strip()
    if not template:
        raise ValueError("no template for topic {!r}".format(topic))
    values: Dict[str, Any] = {
        "telegram_crypto": config.get("telegram_crypto", ""),
        "telegram_ai": config.get("telegram_ai", ""),
        "travel_link": config.get("travel_link", ""),
        "travel_disclosure": config.get("travel_disclosure", "Ad · partner link."),
    }
    meta: Dict[str, Any] = {}
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
            article = find_article(topic, config) if topic in ("crypto", "ai") else None
            if article:
                print("article:", article.get("title", "")[:90], "|", article.get("source", ""))
            text, meta = build_post(config, topic, index + step, article)
        except (ValueError, KeyError) as exc:
            print("build error:", exc)
            return 1
        print("--- {} ---\n{}\n".format(topic, text))
        if args.dry_run:
            continue
        try:
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
            result = publish(text, media_ids)
            print("published:", result.get("url") or result.get("id"))
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
