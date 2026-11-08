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
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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


def build_post(config: Dict[str, Any], topic: str, index: int) -> str:
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
    if topic == "crypto":
        headlines = config.get("crypto_headlines") or ["Crypto markets update."]
        values["headline"] = headlines[index % len(headlines)]
        values["market_line"] = market_line()
    if topic == "ai":
        angles = config.get("ai_angles") or ["AI and trading are converging."]
        values["ai_angle"] = angles[index % len(angles)]
    return template.format(**values)


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
            text = build_post(config, topic, index + step)
        except (ValueError, KeyError) as exc:
            print("build error:", exc)
            return 1
        print("--- {} ---\n{}\n".format(topic, text))
        if args.dry_run:
            continue
        try:
            result = publish(text)
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
