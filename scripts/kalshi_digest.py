#!/usr/bin/env python3
"""Kalshi prediction-market digest -> Telegram channels.

Public market data only (no API key needed). Dry-run by default; ``--live``
publishes to Telegram. Config: ``config/kalshi.yaml``.

Env:
    TELEGRAM_BOT_TOKEN            bot that posts to the channels
    TELEGRAM_API_BASE             optional (proxy), default api.telegram.org
    TELEGRAM_CHAT_ID_<CHANNEL>    optional override for channel ids
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.kalshi import (  # noqa: E402
    KalshiClient,
    KalshiError,
    PUBLIC_BASE,
    build_digest,
    select_markets,
)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_channel_ids() -> dict:
    """id -> telegram_chat_id from config/channels.*.yaml (inline ids win)."""
    ids = {}
    for name in ("channels.en.yaml", "channels.es.yaml"):
        path = ROOT / "config" / name
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        for channel in data.get("channels") or []:
            channel_id = str(channel.get("id") or "").strip()
            chat = str(channel.get("telegram_chat_id") or "").strip()
            if channel_id and chat:
                ids[channel_id] = chat
    return ids


def resolve_chat_id(channel: str, entry: dict, channel_ids: dict) -> str:
    explicit = str(entry.get("chat_id") or "").strip()
    if explicit:
        return explicit
    env_name = "TELEGRAM_CHAT_ID_" + channel.upper().replace("-", "_")
    value = env(env_name)
    if value:
        return value
    return channel_ids.get(channel, "")


def affiliate_line(config: dict, language: str, now_utc=None) -> str:
    """Daily affiliate/referral line (once per day, only in the configured UTC hour)."""
    from datetime import datetime, timezone

    block = (config or {}).get("affiliate") or {}
    if not isinstance(block, dict) or not block.get("enabled"):
        return ""
    url = str(block.get("url") or "").strip()
    if not url:
        return ""
    now = now_utc or datetime.now(timezone.utc)
    if block.get("once_per_day", True):
        try:
            hour = int(block.get("daily_hour_utc", 12))
        except (TypeError, ValueError):
            hour = 12
        if now.hour != hour:
            return ""
    disclosure = str(block.get("disclosure") or "Ad")
    template = block.get("text_es") if str(language).lower().startswith("es") else block.get("text_en")
    template = str(template or "🔗 {url} · {disclosure}")
    return template.format(url=url, disclosure=disclosure)


def send_message(token: str, api_base: str, chat_id: str, text: str) -> tuple:
    base = (api_base or "https://api.telegram.org").rstrip("/")
    url = base + "/bot" + token + "/sendMessage"
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        return bool(data.get("ok")), str(data.get("description") or "")[:200]
    except urllib.error.HTTPError as error:
        return False, "HTTP %s: %s" % (error.code, error.read()[:200])
    except Exception as error:  # noqa: BLE001
        return False, "%s: %s" % (type(error).__name__, str(error)[:200])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kalshi digest for Telegram channels")
    parser.add_argument("--config", default=str(ROOT / "config" / "kalshi.yaml"))
    parser.add_argument("--live", action="store_true", help="publish (default: dry-run)")
    parser.add_argument("--channel", default="", help="only this channel id")
    parser.add_argument("--discover", default="", help="print series for a category and exit")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    base_url = env("KALSHI_API_BASE", str(config.get("base_url") or PUBLIC_BASE))
    client = KalshiClient(base_url=base_url)

    if args.discover:
        series = client.series_list(category=args.discover if args.discover != "all" else "")
        print("series found: %d" % len(series))
        for entry in series[:120]:
            print("%-30s | %-45s | %s" % (
                entry.get("ticker"), str(entry.get("title") or "")[:45], entry.get("category")))
        return 0
    token = env("TELEGRAM_BOT_TOKEN")
    api_base = env("TELEGRAM_API_BASE")
    channel_ids = load_channel_ids()

    markets = None
    failures = 0
    for entry in config.get("digests") or []:
        channel = str(entry.get("channel") or "").strip()
        if not channel or (args.channel and channel != args.channel):
            continue
        try:
            if markets is None:
                markets = client.markets(
                    status=str(config.get("status") or "open"),
                    limit=int(config.get("limit") or 200),
                    mve_filter=str(config.get("mve_filter") or "exclude"),
                )
                print("Kalshi: fetched %d open markets" % len(markets))
            series_tickers = [str(t).strip() for t in (entry.get("series_tickers") or config.get("series_tickers") or []) if str(t).strip()]
            if series_tickers:
                series_markets = []
                for ticker in series_tickers:
                    try:
                        series_markets.extend(client.markets(
                            status=str(config.get("status") or "open"),
                            limit=100,
                            series_ticker=ticker,
                            mve_filter=str(config.get("mve_filter") or "exclude"),
                        ))
                    except KalshiError as error:
                        print("  series %s: %s" % (ticker, error))
                print("Kalshi: %d markets in configured series (%s)" % (
                    len(series_markets), ", ".join(series_tickers)))
                if series_markets:
                    markets = series_markets
            selected = select_markets(
                markets,
                keywords=entry.get("keywords") or [],
                min_volume=float(entry.get("min_volume") or 0),
                max_items=int(entry.get("max_items") or 4),
            )
            if not selected and entry.get("fallback_top", True) and markets:
                # Keyword/volume filters may miss everything (Kalshi titles vary);
                # still publish the most liquid markets.
                selected = select_markets(markets, keywords=[], min_volume=0,
                                          max_items=int(entry.get("max_items") or 4))
                print("%s: keyword filter matched nothing — fallback to top by volume" % channel)
            if not selected:
                print("%s: no markets match the filter — skip" % channel)
                continue
            text = build_digest(
                selected,
                title=str(entry.get("title") or "Prediction markets"),
                language=str(entry.get("language") or "en"),
                max_items=int(entry.get("max_items") or 4),
                affiliate_url=str(entry.get("affiliate_url") or ""),
            )
            daily_affiliate = affiliate_line(config, str(entry.get("language") or "en"))
            if daily_affiliate:
                text = text.rstrip() + "\n\n" + daily_affiliate
            chat_id = resolve_chat_id(channel, entry, channel_ids)
            if not args.live:
                print("--- %s (dry-run, chat=%s) ---" % (channel, chat_id or "—"))
                print(text)
                continue
            if not token:
                failures += 1
                print("%s: TELEGRAM_BOT_TOKEN is not set" % channel)
                continue
            if not chat_id:
                failures += 1
                print("%s: chat id is not configured" % channel)
                continue
            ok, error = send_message(token, api_base, chat_id, text)
            print("%s: %s %s" % (channel, "ok" if ok else "FAIL", error))
            if not ok:
                failures += 1
        except KalshiError as error:
            failures += 1
            print("%s: Kalshi error: %s" % (channel, error))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
