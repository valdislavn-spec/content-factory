#!/usr/bin/env python3
"""Сигналы с прогнозных рынков → Telegram (SIGNAL CRYPTO).

Сейчас основной источник — Polymarket (публичная Gamma API): ловим рынки,
где вероятность сдвинулась за 24 часа на ≥ ``min_abs_change`` при достаточном
объёме/ликвидности. Kalshi/Manifold/Metaculus подключены, но зависят от
доступности API (Kalshi гео-блок, Metaculus — токен).

Запуск:
    python scripts/prediction_signals.py --dry-run
    python scripts/prediction_signals.py --publish
    python scripts/prediction_signals.py --test
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.prediction.market import fetch_markets  # noqa: E402

LOGGER = logging.getLogger("prediction_signals")
TELEGRAM_BASE = (os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")


def _load_config(path: Path) -> Dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_state(path: Path) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(path: Path, state: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _crypto_regex(config: Dict) -> "re.Pattern[str] | None":
    if not config.get("crypto_only", True):
        return None
    keywords = [str(item) for item in (config.get("crypto_keywords") or []) if str(item).strip()]
    if not keywords:
        return None
    pattern = r"\b(" + "|".join(re.escape(word) for word in keywords) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return "${:.1f}M".format(value / 1_000_000)
    if value >= 1_000:
        return "${:.1f}K".format(value / 1_000)
    return "${:.0f}".format(value)


def _fmt_date(value: str) -> str:
    text = str(value or "")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _format_signal(market: Dict, config: Dict) -> str:
    source = {"polymarket": "Polymarket", "kalshi": "Kalshi", "manifold": "Manifold", "metaculus": "Metaculus"}.get(
        market["source"], market["source"]
    )
    probability = market.get("probability")
    delta = market.get("delta_24h")
    direction = "📈" if (delta or 0) > 0 else "📉"
    lines = [
        "🔮 <b>PRONÓSTICO · %s</b>" % source,
        "<i>%s</i>" % html.escape(str(market.get("question") or "")),
    ]
    if probability is not None:
        lines.append("Probabilidad: <b>%.0f%%</b> (%s%.1f p.p. en 24 h)" % (probability * 100, "+" if (delta or 0) > 0 else "", (delta or 0) * 100))
    else:
        lines.append("%s" % direction)
    details = []
    if market.get("volume_24h"):
        details.append("volumen 24 h " + _fmt_money(market["volume_24h"]))
    if market.get("liquidity"):
        details.append("liquidez " + _fmt_money(market["liquidity"]))
    if details:
        lines.append(" · ".join(details))
    if market.get("end_date"):
        lines.append("Fecha límite: %s" % _fmt_date(market["end_date"]))
    lines.append('🔗 <a href="%s">Abrir mercado</a>' % html.escape(str(market.get("url") or ""), quote=True))
    lines.append("")
    lines.append("<i>%s</i>" % html.escape(str(config.get("disclaimer") or "Not financial advice.")))
    return "\n".join(lines)


def _send(token: str, chat_id: str, text: str, timeout: float = 20.0) -> bool:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    request = urllib.request.Request(
        "%s/bot%s/sendMessage" % (TELEGRAM_BASE, token),
        data=urllib.parse.urlencode(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            if data.get("ok"):
                return True
            LOGGER.warning("telegram: %s", json.dumps(data.get("description") or data)[:200])
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            LOGGER.warning("telegram: попытка %d: %s", attempt + 1, exc)
        time.sleep(2 * (attempt + 1))
    return False


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Сигналы прогнозных рынков → Telegram")
    parser.add_argument("--config", default=str(ROOT / "config" / "prediction.yaml"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args(argv)

    config = _load_config(Path(args.config))
    if not config.get("enabled", True):
        print("prediction: выключено в конфиге")
        return 0
    state_path = ROOT / str(config.get("state_path") or "data/prediction_state.json")
    state = _load_state(state_path)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get(str(config.get("channel_env") or "TELEGRAM_CHAT_ID_CRYPTO_SIGNALS"), "")

    if args.test:
        if not (token and chat_id):
            print("test: нет TELEGRAM_BOT_TOKEN / chat_id")
            return 2
        ok = _send(token, chat_id, "🔮 <b>Mercados de pronóstico conectados</b>\nLas señales de Polymarket/Kalshi aparecerán aquí.")
        print("test message:", "sent" if ok else "failed")
        return 0 if ok else 1

    markets = fetch_markets(config)
    from collections import Counter

    by_source = Counter(market.get("source") for market in markets)
    print("prediction: рынков %d %s" % (len(markets), dict(by_source)))

    crypto_pattern = _crypto_regex(config)
    min_abs = float(config.get("min_abs_change") or 0.07)
    min_volume = float(config.get("min_volume_24h") or 0)
    min_liquidity = float(config.get("min_liquidity") or 0)
    max_per_run = int(config.get("max_signals_per_run") or 2)
    cooldown = int(config.get("cooldown_hours") or 12) * 3600
    now = datetime.now(timezone.utc).timestamp()
    recent = state.get("recent") or {}

    candidates: List[Dict] = []
    for market in markets:
        delta = market.get("delta_24h")
        probability = market.get("probability")
        if delta is None or probability is None:
            continue
        if abs(delta) < min_abs:
            continue
        if (market.get("volume_24h") or 0) < min_volume:
            continue
        if (market.get("liquidity") or 0) < min_liquidity:
            continue
        if probability <= 0.02 or probability >= 0.98:
            continue
        question = str(market.get("question") or "")
        if crypto_pattern is not None and not crypto_pattern.search(question):
            continue
        key = "%s:%s:%s" % (market["source"], market["id"], "up" if delta > 0 else "down")
        if now - float(recent.get(key) or 0) < cooldown:
            continue
        candidates.append(market)
        if len(candidates) >= max_per_run:
            break

    published = 0
    for market in candidates:
        text = _format_signal(market, config)
        if args.publish and token and chat_id:
            if not _send(token, chat_id, text):
                print("publish FAILED:", market.get("source"), market.get("id"))
                continue
            published += 1
            key = "%s:%s:%s" % (market["source"], market["id"], "up" if (market.get("delta_24h") or 0) > 0 else "down")
            recent[key] = now
            print("published:", market["source"], "-", str(market.get("question"))[:80])
        else:
            print("--- signal ---")
            print(text)

    if args.publish and recent != state.get("recent"):
        state["recent"] = recent
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state_path, state)
    print("done: published=%d candidates=%d (dry_run=%s)" % (published, len(candidates), not args.publish))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
