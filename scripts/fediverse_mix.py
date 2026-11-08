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
import sys
import time
import urllib.error
import urllib.request
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


def build_post(config: Dict[str, Any], topic: str, index: int) -> Tuple[str, Dict[str, Any]]:
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
        values["headline"] = headlines[index % len(headlines)]
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
        values["ai_angle"] = angles[index % len(angles)]
        meta["angle"] = values["ai_angle"]
    return template.format(**values), meta


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
            text, meta = build_post(config, topic, index + step)
        except (ValueError, KeyError) as exc:
            print("build error:", exc)
            return 1
        print("--- {} ---\n{}\n".format(topic, text))
        if args.dry_run:
            continue
        try:
            image = build_card(
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
