#!/usr/bin/env python3
"""Дайджест прогнозных рынков Polymarket -> Telegram-каналы.

Один пост каждые 2 часа, каналы идут по кругу (см. ``config/polymarket.yaml``).
Данные — публичная Gamma API (без ключа). Партнёрская (реферальная) ссылка
берётся из ``affiliate.url`` или Secret ``POLYMARKET_AFFILIATE_URL`` и
добавляется в каждый пост вместе с пометкой рекламы.

Запуск:
    python scripts/polymarket_digest.py --dry-run            # канал по ротации
    python scripts/polymarket_digest.py --channel crypto-news --dry-run
    python scripts/polymarket_digest.py --live               # отправить в Telegram
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.prediction.market import fetch_polymarket  # noqa: E402

MAX_QUESTION_CHARS = 90
MAX_TEXT_CHARS = 3800


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_channel_ids() -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for name in ("channels.en.yaml", "channels.es.yaml"):
        path = ROOT / "config" / name
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        for channel in data.get("channels") or []:
            channel_id = str(channel.get("id") or "").strip()
            chat = str(channel.get("telegram_chat_id") or "").strip()
            if channel_id and chat:
                ids[channel_id] = chat
    return ids


def resolve_chat_id(channel: str, entry: dict, channel_ids: Dict[str, str]) -> str:
    explicit = str(entry.get("chat_id") or "").strip()
    if explicit:
        return explicit
    env_name = "TELEGRAM_CHAT_ID_" + channel.upper().replace("-", "_")
    value = env(env_name)
    if value:
        return value
    return channel_ids.get(channel, "")


def load_config(path: Path) -> Dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _pct(probability) -> str:
    try:
        value = max(0.0, min(1.0, float(probability)))
    except (TypeError, ValueError):
        return ""
    if value < 0.01:
        return "<1%"
    if value > 0.99:
        return ">99%"
    return "%d%%" % int(round(value * 100))


def _shorten(text: str, limit: int = MAX_QUESTION_CHARS) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—-")
    return (cut or text[:limit]).rstrip() + "…"


def _matches(question: str, keywords: Sequence[str]) -> bool:
    haystack = str(question or "").lower()
    for keyword in keywords:
        token = str(keyword or "").lower()
        # Не strip-им пробелы: токены вида " fc " нужны, чтобы отсечь клубы
        # ("FC Lorient"), не задевая US-команды.
        if len(token) >= 3 and token in haystack:
            return True
    return False


def select_markets(
    markets: List[dict],
    keywords: Sequence[str],
    max_items: int,
    min_volume: float,
    fallback_top: bool,
    exclude: Sequence[str] = (),
    require_keywords: bool = True,
    must_include: Sequence[str] = (),
) -> List[dict]:
    pool: List[dict] = []
    for market in markets:
        if not isinstance(market, dict) or market.get("probability") is None:
            continue
        try:
            volume = float(market.get("volume_24h") or 0)
        except (TypeError, ValueError):
            continue
        if volume < min_volume:
            continue
        question = str(market.get("question") or "").strip()
        if not question:
            continue
        if exclude and _matches(question, exclude):
            continue
        if must_include and not _matches(question, must_include):
            continue
        if require_keywords and keywords and not _matches(question, keywords):
            continue
        probability = float(market.get("probability") or 0.0)
        interesting = 1 if 0.03 <= probability <= 0.97 else 0
        pool.append({"volume": volume, "interesting": interesting, "market": market})
    if not pool and fallback_top:
        for market in markets:
            if not isinstance(market, dict) or market.get("probability") is None:
                continue
            try:
                volume = float(market.get("volume_24h") or 0)
            except (TypeError, ValueError):
                continue
            if volume < min_volume:
                continue
            question = str(market.get("question") or "").strip()
            if not question:
                continue
            if exclude and _matches(question, exclude):
                continue
            probability = float(market.get("probability") or 0.0)
            pool.append({
                "volume": volume,
                "interesting": 1 if 0.03 <= probability <= 0.97 else 0,
                "market": market,
            })
    pool.sort(key=lambda item: (item["interesting"], item["volume"]), reverse=True)
    return [item["market"] for item in pool[: max(1, int(max_items))]]


def affiliate_line(config: Dict, language: str) -> str:
    block = (config or {}).get("affiliate") or {}
    if not isinstance(block, dict) or not block.get("enabled"):
        return ""
    url = env("POLYMARKET_AFFILIATE_URL") or str(block.get("url") or "").strip()
    if not url:
        return ""
    disclosure = str(block.get("disclosure") or "Ad")
    template = block.get("text_es") if str(language).lower().startswith("es") else block.get("text_en")
    template = str(template or "🔗 {url} · {disclosure}")
    return template.format(url=html.escape(url), disclosure=html.escape(disclosure))


def build_digest(entry: dict, markets: List[dict], config: Dict) -> str:
    language = str(entry.get("language") or "en")
    spanish = language.lower().startswith("es")
    title = str(entry.get("title") or ("Mercados de predicción" if spanish else "Prediction markets"))
    max_items = int(entry.get("max_items") or config.get("max_items") or 3)
    min_volume = float(entry.get("min_volume_24h") or config.get("min_volume_24h") or 0)
    selected = select_markets(
        markets,
        [str(k) for k in (entry.get("keywords") or [])],
        max_items,
        min_volume,
        bool(entry.get("fallback_top", config.get("fallback_top", True))),
        [str(x) for x in (entry.get("exclude") or [])],
        bool(entry.get("require_keywords", True)),
        [str(x) for x in (entry.get("must_include") or [])],
    )
    if not selected:
        return ""
    yes = "Sí" if spanish else "Yes"
    lines = ["<b>%s</b>" % html.escape(title), ""]
    for market in selected:
        question = _shorten(market.get("question", ""))
        url = str(market.get("url") or "").strip()
        probability = _pct(market.get("probability"))
        if not question or not url.startswith("https://polymarket.com/") or not probability:
            continue
        lines.append('• <a href="%s">%s</a> — %s %s' % (
            html.escape(url, quote=True), html.escape(question), yes, probability))
    if len(lines) <= 2:
        return ""
    footer = config.get("footer_es") if spanish else config.get("footer_en")
    if footer:
        lines += ["", str(footer)]
    text = "\n".join(lines).rstrip()
    affiliate = affiliate_line(config, language)
    if affiliate:
        text += "\n\n" + affiliate
    while len(text) > MAX_TEXT_CHARS and len(lines) > 3:
        lines.pop(-3)
        text = "\n".join(lines).rstrip()
        if affiliate:
            text += "\n\n" + affiliate
    return text


def send_message(token: str, api_base: str, chat_id: str, text: str) -> tuple:
    base = (api_base or "https://api.telegram.org").rstrip("/")
    url = base + "/bot" + token + "/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        return bool(data.get("ok")), str(data.get("description") or "")[:200]
    except urllib.error.HTTPError as error:
        return False, "HTTP %s: %s" % (error.code, error.read()[:200])
    except Exception as error:  # noqa: BLE001
        return False, "%s: %s" % (type(error).__name__, str(error)[:200])


def pick_entries(config: Dict, args) -> List[dict]:
    digests = [entry for entry in (config.get("digests") or []) if isinstance(entry, dict)]
    if args.channel:
        return [entry for entry in digests if str(entry.get("channel") or "") == args.channel]
    if not args.rotate:
        return digests
    if not digests:
        return []
    now = args.now or datetime.now(timezone.utc)
    index = (now.hour // 2) % len(digests)
    return [digests[index]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Polymarket digest for Telegram channels")
    parser.add_argument("--config", default=str(ROOT / "config" / "polymarket.yaml"))
    parser.add_argument("--rotate", action="store_true", help="канал по кругу (UTC-час // 2)")
    parser.add_argument("--channel", default="", help="конкретный канал")
    parser.add_argument("--live", action="store_true", help="публиковать (по умолчанию dry-run)")
    parser.add_argument("--now", default=None, help="ISO-время для теста ротации")
    args = parser.parse_args(argv)

    config = load_config(Path(args.config))
    if args.now:
        try:
            args.now = datetime.fromisoformat(args.now.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            print("неверный --now", file=sys.stderr)
            return 2
    entries = pick_entries(config, args)
    if not entries:
        print("нет подходящих дайджестов", file=sys.stderr)
        return 2

    markets = fetch_polymarket(
        limit=int(config.get("limit") or 100), pages=int(config.get("pages") or 3))
    print("polymarket markets: %d" % len(markets), file=sys.stderr)
    if not markets:
        print("Polymarket API недоступен", file=sys.stderr)
        return 1

    token = env("TELEGRAM_BOT_TOKEN")
    api_base = env("TELEGRAM_API_BASE")
    channel_ids = load_channel_ids()
    failures = 0
    for entry in entries:
        channel = str(entry.get("channel") or "").strip()
        text = build_digest(entry, markets, config)
        chat_id = resolve_chat_id(channel, entry, channel_ids)
        if not text:
            print("%s: нет подходящих рынков — пропуск" % channel, file=sys.stderr)
            continue
        if not args.live:
            print("--- %s (dry-run, chat=%s) ---" % (channel, chat_id or "—"))
            print(text)
            print()
            continue
        if not token or not chat_id:
            print("%s: нет TELEGRAM_BOT_TOKEN или chat_id — пропуск" % channel, file=sys.stderr)
            failures += 1
            continue
        ok, detail = send_message(token, api_base, chat_id, text)
        print("%s: %s (chat=%s) %s" % (channel, "ok" if ok else "fail", chat_id, detail), file=sys.stderr)
        if not ok:
            failures += 1
        time.sleep(1.0)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
