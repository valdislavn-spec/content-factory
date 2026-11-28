#!/usr/bin/env python3
"""SoSoValue daily posts -> Telegram channels of the content factory.

Six themes: flows, sectors, macro, sentiment, derivatives, ecosystems.
Data: SoSoValue public API (x-soso-api-key) + DefiLlama for per-chain TVL.

Запуск:
    python scripts/sosovalue_digest.py --dry-run            # темы, положенные на текущий час
    python scripts/sosovalue_digest.py --all --dry-run       # все шесть тем
    python scripts/sosovalue_digest.py --theme flows --live  # отправить один пост
"""
from __future__ import annotations

import argparse
import json
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

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF))

from content_factory.sosovalue import build_digest, render  # noqa: E402

CONFIG = CF / "config" / "sosovalue.yaml"
STATE = CF / "data" / "sosovalue_state.json"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def channel_index() -> Dict[str, dict]:
    """id -> {chat_id, language} из channels.en.yaml / channels.es.yaml."""
    out: Dict[str, dict] = {}
    for name, lang in (("channels.en.yaml", "en"), ("channels.es.yaml", "es"), ("channels.yaml", "ru")):
        path = CF / "config" / name
        if not path.exists():
            continue
        for channel in (load_yaml(path).get("channels") or []):
            cid = str(channel.get("id") or "").strip()
            if not cid:
                continue
            chat = str(channel.get("telegram_chat_id") or "").strip()
            chat = env("TELEGRAM_CHAT_ID_" + cid.upper().replace("-", "_"), chat)
            out[cid] = {"chat_id": chat, "language": channel.get("language") or lang}
    return out


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_message(token: str, api_base: str, chat_id: str, text: str) -> tuple:
    url = api_base.rstrip("/") + "/bot" + token + "/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                          "disable_web_page_preview": True}).encode("utf-8")
    last = ""
    for attempt in range(3):
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                return True, "ok"
            last = body.get("description") or "not ok"
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except ValueError:
                body = {}
            last = body.get("description") or "HTTP %s" % exc.code
            retry_after = (body.get("parameters") or {}).get("retry_after")
            if exc.code == 429 or exc.code >= 500:
                time.sleep(float(retry_after) if retry_after else min(2 ** attempt, 8))
                continue
            return False, last
        except (urllib.error.URLError, TimeoutError) as exc:
            last = "network error: %s" % exc
            time.sleep(min(2 ** attempt, 8))
    return False, last


def affiliate_line(config: dict, lang: str, counter: int) -> str:
    aff = config.get("affiliate") or {}
    if not aff.get("enabled"):
        return ""
    every = int(aff.get("every_n_posts") or 0)
    if every and counter % every != 0:
        return ""
    url = env("SOSO_AFFILIATE_URL") or aff.get("url") or ""
    if not url:
        return ""
    text = (aff.get("text_es") if lang == "es" else aff.get("text_en")) or "{url}"
    line = text.format(url=url, disclosure=aff.get("disclosure", "Ad"))
    return line


def select_themes(config: dict, args) -> List[dict]:
    themes = config.get("themes") or []
    if args.theme:
        wanted = {t.strip() for t in args.theme.split(",") if t.strip()}
        return [t for t in themes if t.get("key") in wanted]
    if args.all:
        return themes
    hour = datetime.now(timezone.utc).hour
    return [t for t in themes if int(t.get("hour_utc", -1)) == hour]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="", help="flows,sectors,...")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--channel", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    config = load_yaml(CONFIG)
    if not config.get("enabled", True):
        print("sosovalue: disabled in config", file=sys.stderr)
        return 0

    themes = select_themes(config, args)
    if not themes:
        print("sosovalue: no theme due this hour", file=sys.stderr)
        return 0

    digest = build_digest(symbols=config.get("symbols") or ["BTC", "ETH"],
                          country_code=config.get("country_code") or "US",
                          top_sectors=int(config.get("top_sectors") or 3))
    if digest.get("errors"):
        print("sosovalue warnings: %s" % digest["errors"], file=sys.stderr)

    channels = channel_index()
    token = env("TELEGRAM_BOT_TOKEN")
    api_base = env("TELEGRAM_API_BASE", "https://api.telegram.org")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = load_state()
    posted = state.setdefault(today, {})
    failures = 0
    counter = sum(1 for key in posted if key.startswith("affiliate:"))
    live = args.live and not args.dry_run

    for theme in themes:
        key = theme.get("key")
        targets = theme.get("channels") or []
        if args.channel:
            targets = [c for c in targets if c == args.channel]
        for channel_id in targets:
            meta = channels.get(channel_id) or {}
            chat_id = meta.get("chat_id") or ""
            lang = meta.get("language") or "en"
            state_key = "%s:%s" % (channel_id, key)
            text = render(key, digest, lang=lang,
                          footer=config.get("footer_%s" % lang) or config.get("footer_en") or "",
                          affiliate=affiliate_line(config, lang, counter))
            if not chat_id and live:
                print("%s/%s: no chat_id (env TELEGRAM_CHAT_ID_%s)" % (
                    channel_id, key, channel_id.upper().replace("-", "_")), file=sys.stderr)
                continue
            if posted.get(state_key) and not args.force:
                print("skip %s %s: already posted" % (channel_id, key), file=sys.stderr)
                continue
            if not live:
                print("----- %s (%s, %s) -----" % (channel_id, key, lang))
                print(text)
                print()
                continue
            if not token:
                print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
                return 2
            ok, detail = send_message(token, api_base, chat_id, text)
            if ok:
                posted[state_key] = True
                counter += 1
                save_state(state)
                print("posted %s %s" % (channel_id, key), file=sys.stderr)
            else:
                failures += 1
                print("failed %s %s: %s" % (channel_id, key, detail), file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
