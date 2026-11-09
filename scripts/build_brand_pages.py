#!/usr/bin/env python3
"""Брендовые пины и OG-превью для GitHub Pages.

    # пины Pinterest (PNG+JSON в docs/assets/pins/brand/) + манифест URL
    python scripts/build_brand_pages.py --pins
    # OG-превью (PNG в docs/assets/og/) + meta-теги в HTML страницах
    python scripts/build_brand_pages.py --og
    # всё сразу (используется в workflow pins-generate)
    python scripts/build_brand_pages.py --all

Требует Pillow + segno (в Actions есть; локально — DSH-python + /tmp/segno).
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAGES_BASE = "https://valdislavn-spec.github.io/content-factory"
BOARDS_FILE = ROOT / "config" / "pinterest_boards.yaml"
PINS_DIR = ROOT / "docs" / "assets" / "pins" / "brand"
OG_DIR = ROOT / "docs" / "assets" / "og"
MANIFEST = ROOT / "config" / "pinterest_brand_urls.yaml"

CHANNEL_PAGES = {
    "ai-news": "docs/channels/ai-news-telegram-us.html",
    "crypto-news": "docs/channels/us-crypto-news-telegram.html",
    "sport-news": "docs/channels/us-sports-news-telegram.html",
    "tech-ai-es": "docs/channels/noticias-ia-telegram.html",
    "crypto-es": "docs/channels/noticias-cripto-telegram.html",
    "futbol-es": "docs/channels/futbol-deportes-telegram.html",
}

TOPIC_BY_CHANNEL = {
    "ai-news": "ai", "tech-ai-es": "ai",
    "crypto-news": "crypto", "crypto-es": "crypto",
    "sport-news": "sports", "futbol-es": "sports",
}


def _channels(settings) -> Dict[str, Any]:
    from content_factory.config import load_channels

    result: Dict[str, Any] = {}
    for path in ("config/channels.en.yaml", "config/channels.es.yaml"):
        try:
            for channel in load_channels(settings, path=str(ROOT / path)):
                result[channel.id] = channel
        except Exception:  # noqa: BLE001
            continue
    return result


def channel_boards() -> Dict[str, str]:
    """channel_id → board_id Pinterest (config/pinterest_boards.yaml)."""
    import yaml

    try:
        data = yaml.safe_load(BOARDS_FILE.read_text(encoding="utf-8")) or {}
        raw = data.get("channels") or {}
        return {str(key): str(value) for key, value in raw.items() if str(value).strip()}
    except Exception:  # noqa: BLE001
        return {}


def _ready_partners() -> List[Dict[str, Any]]:
    import yaml

    raw = yaml.safe_load((ROOT / "config" / "affiliates.yaml").read_text(encoding="utf-8")) or {}
    result = []
    for key, program in (raw.get("programs") or {}).items():
        if str(program.get("status")) != "ready" or not str(program.get("url") or ""):
            continue
        result.append({"key": key, "title": str(program.get("title") or key),
                       "url": str(program["url"]),
                       "age_restricted": bool(program.get("age_restricted"))})
    return result


def channel_partner(channel: Any, index: int = 0) -> Optional[Dict[str, Any]]:
    """Партнёр канала: affiliate-ссылка канала → ready-программа по ротации."""
    from content_factory.brand.runtime import partner_from_url

    config = getattr(channel, "affiliate", None) or {}
    if isinstance(config, dict) and config.get("enabled"):
        direct = str(config.get("link") or "").strip()
        tracked = str(config.get("tracked_url") or "").strip()
        # бренд определяем по прямой ссылке (bingxdao.com → BingX),
        # а в QR/pin кладём трекаемую ссылку, если она есть
        if direct.startswith(("http://", "https://")) or tracked.startswith(("http://", "https://")):
            partner = partner_from_url(direct or tracked)
            partner["url"] = tracked or direct
            partner["age_restricted"] = bool(config.get("age_restricted"))
            return partner
    partners = _ready_partners()
    if not partners:
        return None
    return partners[index % len(partners)]


def recent_headline(storage, channel_id: str) -> str:
    try:
        posts = storage.get_posts(channel_id, days=14, limit=10)
    except Exception:  # noqa: BLE001
        return ""
    from content_factory.brand.runtime import headline_from_post, subtitle_from_post

    for post in posts:
        if post.get("status") not in {"published", "generated"}:
            continue
        headline = headline_from_post(str(post.get("text") or ""))
        if headline:
            return headline
    return ""


def build_pins() -> int:
    from content_factory.brand import templates
    from content_factory.config import Settings
    from content_factory.storage import Storage

    settings = Settings.load()
    channels = _channels(settings)
    brand_config = templates.load_config()
    PINS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, str] = {}
    boards = channel_boards()
    with Storage(settings.db_path) as storage:
        for index, (channel_id, channel) in enumerate(sorted(channels.items())):
            topic = TOPIC_BY_CHANNEL.get(channel_id, "ai")
            partner = channel_partner(channel, index)
            headline = recent_headline(storage, channel_id) or ""
            topic_cfg = brand_config["topics"].get(topic) or {}
            spec = templates.plan(
                brand_config, "pinterest_pin", topic, "",
                headline=headline or topic_cfg.get("headline") or "",
                subtitle=topic_cfg.get("subtitle") or "",
                cta=topic_cfg.get("cta") or "",
            )
            if partner:
                spec["partner"] = {**partner, "commission": ""}
            spec["disclosure"] = "Advertising / affiliate link."
            filename = f"{channel_id}-{topic}" + (f"-{partner['key']}" if partner else "")
            path = templates.render(spec, PINS_DIR)
            # стабильное имя
            stable = PINS_DIR / f"{filename}.png"
            if Path(path) != stable:
                Path(path).replace(stable)
            image_url = f"{PAGES_BASE}/assets/pins/brand/{stable.name}"
            pin_title = " ".join(str(headline or topic_cfg.get("headline") or channel_id).split())
            description = (topic_cfg.get("subtitle") or "") + (
                " Advertising / affiliate link." if partner else "") + " Telegram: " + str(
                getattr(channel, "description", "") or "")
            board_id = boards.get(channel_id) or "<BOARD_ID>"
            payload = {
                "image_url": image_url,
                "file": str(stable.relative_to(ROOT)),
                "niche": topic,
                "affiliate": bool(partner),
                "disclosure": "Advertising / affiliate link.",
                "pin": {
                    "board_id": board_id,
                    "title": pin_title,
                    "description": description[:500],
                    "alt_text": pin_title,
                    "media_source": {"source_type": "image_url", "url": image_url},
                },
            }
            (PINS_DIR / f"{filename}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest[channel_id] = image_url
            print(f"pin: {image_url}")
    MANIFEST.write_text(
        "# Брендовые пины для Pinterest (GitHub Pages). Автогенерация build_brand_pages.py\n"
        "channels:\n"
        + "".join(f"  {channel_id}: {url!r}\n" for channel_id, url in manifest.items())
        + "boards:\n"
        + "".join(f"  {channel_id}: {boards.get(channel_id, '')!r}\n" for channel_id in manifest),
        encoding="utf-8",
    )
    return 0


def _page_language(path: Path) -> str:
    text = path.read_text(encoding="utf-8")[:500].lower()
    return "es" if 'lang="es"' in text else "en"


def _patch_og_meta(path: Path, image_url: str) -> bool:
    """Добавляет og:image/twitter:image, если их ещё нет."""
    text = path.read_text(encoding="utf-8")
    if 'property="og:image"' in text:
        return False
    if 'name="twitter:card" content="summary"' in text:
        text = text.replace('name="twitter:card" content="summary"',
                            'name="twitter:card" content="summary_large_image"')
    elif 'name="twitter:card"' not in text:
        text = text.replace("</title>", '</title>\n<meta name="twitter:card" content="summary_large_image">', 1)
    tags = (
        f'\n<meta property="og:image" content="{image_url}">'
        f'\n<meta property="og:image:width" content="1200">'
        f'\n<meta property="og:image:height" content="630">'
        f'\n<meta name="twitter:image" content="{image_url}">'
    )
    if "</head>" not in text:
        return False
    text = text.replace("</head>", tags + "\n</head>", 1)
    path.write_text(text, encoding="utf-8")
    return True


def build_og() -> int:
    from content_factory.brand import templates

    brand_config = templates.load_config()
    OG_DIR.mkdir(parents=True, exist_ok=True)
    pages: List[Path] = []
    hub = ROOT / "docs" / "index.html"
    if hub.is_file():
        pages.append(hub)
    channels_index = ROOT / "docs" / "channels" / "index.html"
    if channels_index.is_file():
        pages.append(channels_index)
    for relative in CHANNEL_PAGES.values():
        page = ROOT / relative
        if page.is_file():
            pages.append(page)

    for page in pages:
        text = page.read_text(encoding="utf-8")
        title_match = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
        desc_match = re.search(r'name="description" content="([^"]*)"', text, re.I)
        headline = html_module.unescape(title_match.group(1)).strip() if title_match else page.stem
        subtitle = html_module.unescape(desc_match.group(1)).strip() if desc_match else ""
        language = _page_language(page)
        slug = page.relative_to(ROOT / "docs").with_suffix("").as_posix().replace("/", "-")
        topic = "ai"
        for key, relative in CHANNEL_PAGES.items():
            if page.as_posix().endswith(relative):
                topic = TOPIC_BY_CHANNEL.get(key, "ai")
                break
        spec = templates.plan(
            brand_config, "og_image", topic, "",
            headline=headline[:95], subtitle=subtitle[:150],
            cta="Read the channel" if "channels/" in page.as_posix() else "",
        )
        spec["partner"] = None  # OG-превью без партнёрского блока и QR
        spec["disclosure"] = ""
        spec["label"] = "TELEGRAM CHANNELS"
        if "channels/" not in page.as_posix():
            spec["cta"] = "Read the channels"
        path = templates.render(spec, OG_DIR)
        stable = OG_DIR / f"{slug}.png"
        if Path(path) != stable:
            Path(path).replace(stable)
        image_url = f"{PAGES_BASE}/assets/og/{stable.name}"
        patched = _patch_og_meta(page, image_url)
        print(f"og: {image_url} (meta {'added' if patched else 'already'}, lang={language})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pins", action="store_true", help="только брендовые Pinterest-пины")
    parser.add_argument("--og", action="store_true", help="только OG-превью + meta")
    parser.add_argument("--all", action="store_true", help="пины + OG")
    args = parser.parse_args()
    if args.all or (not args.pins and not args.og):
        build_pins()
        build_og()
        return 0
    if args.pins:
        return build_pins()
    return build_og()


if __name__ == "__main__":
    raise SystemExit(main())
