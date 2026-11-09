#!/usr/bin/env python3
"""Авто-сигналы по крипте → отдельный Telegram-канал (SIGNAL CRYPTO).

Данные: публичные REST API бирж (BingX/Bitget/MEXC/Coinbase/Crypto.com/Kraken),
без API-ключей. Публикация: Telegram Bot API, chat_id из env
``TELEGRAM_CHAT_ID_CRYPTO_SIGNALS``.

Запуск:
    python scripts/crypto_signals.py --dry-run   # только показать сигналы
    python scripts/crypto_signals.py --publish   # отправить новые сигналы в канал
    python scripts/crypto_signals.py --test      # тестовое сообщение в канал
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
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

from content_factory.signals.engine import build_signals  # noqa: E402
from content_factory.signals.market import fetch_candles  # noqa: E402

LOGGER = logging.getLogger("crypto_signals")
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


def _fmt_price(value: float) -> str:
    if value >= 1000:
        return "{:,.1f}".format(value).replace(",", " ")
    if value >= 1:
        return "{:.3f}".format(value).rstrip("0").rstrip(".")
    return "{:.5f}".format(value).rstrip("0").rstrip(".")


def _fetch_data(config: Dict) -> Dict[str, Dict[str, Dict[str, List[dict]]]]:
    pairs = [str(item) for item in config.get("pairs") or []]
    exchanges = [str(item) for item in config.get("exchanges") or []]
    schema = config.get("timeframes") or {}
    entry_tf = str(schema.get("entry") or "15m")
    trend_tf = str(schema.get("trend") or "1h")
    limit = int(config.get("candles") or 300)
    data: Dict[str, Dict[str, Dict[str, List[dict]]]] = {}
    for pair in pairs:
        data[pair] = {}
        for exchange in exchanges:
            entry = fetch_candles(exchange, pair, entry_tf, limit)
            trend = fetch_candles(exchange, pair, trend_tf, limit)
            if entry and trend:
                data[pair][exchange] = {entry_tf: entry, trend_tf: trend}
    return data


def _format_signal(signal: Dict, config: Dict, affiliate: Dict | None) -> str:
    direction = "🟢 LONG" if signal["side"] == "LONG" else "🔴 SHORT"
    pair = html.escape(str(signal["pair"]))
    lines = [
        "⚡️ <b>%s · %s</b>" % (pair, direction),
        "Цена: <b>%s</b>" % _fmt_price(signal["entry"]),
        "Стоп: %s · Тейк: %s (R:R %.1f)" % (
            _fmt_price(signal["stop"]), _fmt_price(signal["take"]), signal["rr"]
        ),
        "Подтвердили биржи (%d): %s" % (
            len(signal["confirmations"]), html.escape(", ".join(signal["confirmations"]))
        ),
        "RSI: %.1f · объём ×%.2f" % (signal["rsi"], signal["volume_ratio"]),
    ]
    if affiliate and affiliate.get("url"):
        lines.append("")
        lines.append('➡️ <a href="%s">%s</a>' % (
            html.escape(str(affiliate["url"]), quote=True), html.escape(str(affiliate.get("name") or "Trade"))
        ))
        if affiliate.get("note"):
            lines.append("<i>%s</i>" % html.escape(str(affiliate["note"])))
    disclaimer = config.get("disclaimer") or "Not financial advice."
    lines.append("")
    lines.append("<i>🤖 %s</i>" % html.escape(str(disclaimer)))
    return "\n".join(lines)


def _send_message(token: str, chat_id: str, text: str, timeout: float = 20.0) -> bool:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    url = "%s/bot%s/sendMessage" % (TELEGRAM_BASE, token)
    request = urllib.request.Request(
        url,
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
            LOGGER.warning("telegram: попытка %d не удалась: %s", attempt + 1, exc)
        time.sleep(2 * (attempt + 1))
    return False


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Крипто-сигналы → Telegram-канал")
    parser.add_argument("--config", default=str(ROOT / "config" / "signals.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="только показать сигналы")
    parser.add_argument("--publish", action="store_true", help="опубликовать новые сигналы")
    parser.add_argument("--test", action="store_true", help="отправить тестовое сообщение в канал")
    args = parser.parse_args(argv)

    config = _load_config(Path(args.config))
    if not config.get("enabled", True):
        print("signals: выключены в конфиге")
        return 0
    state_path = ROOT / str(config.get("state_path") or "data/signals_state.json")
    state = _load_state(state_path)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get(str(config.get("channel_env") or "TELEGRAM_CHAT_ID_CRYPTO_SIGNALS"), "")

    if args.test:
        if not (token and chat_id):
            print("test: нет TELEGRAM_BOT_TOKEN / chat_id")
            return 2
        ok = _send_message(token, chat_id, "🔔 <b>SIGNAL CRYPTO</b>\nКанал подключён. Сигналы будут появляться автоматически.")
        print("test message:", "sent" if ok else "failed")
        return 0 if ok else 1

    data = _fetch_data(config)
    signals = build_signals(data, config)
    pairs_ok = sum(1 for pair in data if data[pair])
    print("market: пар с данными %d/%d, бирж в конфиге %d" % (pairs_ok, len(data), len(config.get("exchanges") or [])))
    print("signals: %d" % len(signals))

    now = datetime.now(timezone.utc)
    cooldown = int(config.get("cooldown_minutes") or 90) * 60
    recent = state.get("recent") or {}
    max_per_run = int(config.get("max_signals_per_run") or 2)
    fresh: List[Dict] = []
    for signal in signals:
        if len(fresh) >= max_per_run:
            break
        key = "%s|%s" % (signal["pair"], signal["side"])
        last = float(recent.get(key) or 0)
        if now.timestamp() - last < cooldown:
            continue
        fresh.append(signal)

    affiliate_index = int(state.get("affiliate_index") or 0)
    affiliates = config.get("affiliates") or []
    published = 0
    for signal in fresh:
        affiliate = None
        if affiliates:
            affiliate = affiliates[affiliate_index % len(affiliates)]
            affiliate_index += 1
        text = _format_signal(signal, config, affiliate)
        if args.publish and token and chat_id:
            ok = _send_message(token, chat_id, text)
            if not ok:
                print("publish FAILED:", signal["pair"], signal["side"])
                continue
            published += 1
            key = "%s|%s" % (signal["pair"], signal["side"])
            recent[key] = now.timestamp()
            print("published:", signal["pair"], signal["side"])
        else:
            print("--- signal ---")
            print(text)

    if state.get("recent") != recent or affiliate_index != int(state.get("affiliate_index") or 0):
        state["recent"] = recent
        state["affiliate_index"] = affiliate_index
        state["updated_at"] = now.isoformat()
        _save_state(state_path, state)
    print("done: published=%d (dry_run=%s)" % (published, not args.publish))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
