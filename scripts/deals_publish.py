#!/usr/bin/env python3
"""Публикация deals-постов в Telegram-каналы через Bot API.

Берёт JSON, сгенерированный `scripts/deals_post.py --json-out`, и отправляет
посты по одному с заданной паузой между каналами (чтобы не спамить канал).

    ./.venv/bin/python scripts/deals_publish.py --json data/reports/deals-posts-2026-11-09.json --dry-run
    ./.venv/bin/python scripts/deals_publish.py --json ... --delay 300 --publish

ID каналов берутся из .env: TELEGRAM_CHAT_ID_<CHANNEL>. API — TELEGRAM_API_BASE
(Cloudflare-прокси, т.к. api.telegram.org из РФ недоступен).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

CHANNEL_ENV = {
    "tech-ai-es": "TELEGRAM_CHAT_ID_TECH_AI_ES",
    "futbol-es": "TELEGRAM_CHAT_ID_FUTBOL_ES",
    "crypto-es": "TELEGRAM_CHAT_ID_CRYPTO_ES",
    "ai-news": "TELEGRAM_CHAT_ID_AI_NEWS",
    "sport-news": "TELEGRAM_CHAT_ID_SPORT_NEWS",
    "crypto-news": "TELEGRAM_CHAT_ID_CRYPTO_NEWS",
}


def load_env(path: Path = ENV_PATH) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def send_message(api_base: str, token: str, chat_id: str, text: str, timeout: float = 30.0) -> Dict[str, Any]:
    url = f"{api_base.rstrip('/')}/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/157.0 Safari/537.36",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Публикация deals-постов в Telegram")
    parser.add_argument("--json", required=True, help="JSON от scripts/deals_post.py")
    parser.add_argument("--publish", action="store_true", help="реальная отправка")
    parser.add_argument("--dry-run", action="store_true", help="только показать")
    parser.add_argument("--delay", type=float, default=300.0, help="пауза между постами, сек")
    parser.add_argument("--limit", type=int, default=0, help="ограничить число постов")
    parser.add_argument("--only", default="", help="только эти id постов через запятую")
    args = parser.parse_args(argv)

    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    api_base = env.get("TELEGRAM_API_BASE", "https://api.telegram.org")
    if not token:
        print("Нет TELEGRAM_BOT_TOKEN в .env", file=sys.stderr)
        return 2
    report = json.loads(Path(args.json).read_text(encoding="utf-8"))
    posts: List[Dict[str, Any]] = report.get("posts") or []
    if args.only:
        wanted = {part.strip() for part in args.only.split(",") if part.strip()}
        posts = [post for post in posts if post.get("id") in wanted]
    if args.limit:
        posts = posts[: args.limit]

    # чередуем каналы, чтобы не публиковать подряд в один и тот же
    by_channel: Dict[str, List[Dict[str, Any]]] = {}
    for post in posts:
        by_channel.setdefault(post["channel"], []).append(post)
    ordered: List[Dict[str, Any]] = []
    while any(by_channel.values()):
        for channel in list(by_channel):
            if by_channel[channel]:
                ordered.append(by_channel[channel].pop(0))

    log: List[Dict[str, Any]] = []
    for index, post in enumerate(ordered, start=1):
        channel = post["channel"]
        env_name = CHANNEL_ENV.get(channel, "")
        chat_id = env.get(env_name, "") if env_name else ""
        entry = {"id": post["id"], "channel": channel, "chat_id": chat_id, "status": "skipped", "error": ""}
        if not chat_id:
            entry["error"] = f"нет {env_name} в .env"
            print(f"[{index}/{len(ordered)}] {post['id']} ({channel}) — ПРОПУСК: {entry['error']}")
            log.append(entry)
            continue
        preview = post["text"].splitlines()[0][:70]
        if not args.publish:
            print(f"[{index}/{len(ordered)}] {post['id']} ({channel}, {chat_id}) → {preview}…")
            entry["status"] = "dry-run"
            log.append(entry)
            continue
        try:
            result = send_message(api_base, token, chat_id, post["text"])
            if result.get("ok"):
                entry["status"] = "published"
                entry["message_id"] = (result.get("result") or {}).get("message_id")
                print(f"[{index}/{len(ordered)}] {post['id']} ({channel}) — ✅ опубликовано (msg {entry['message_id']})")
            else:
                entry["error"] = str(result)[:300]
                print(f"[{index}/{len(ordered)}] {post['id']} ({channel}) — ❌ {entry['error']}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            entry["error"] = str(exc)[:300]
            print(f"[{index}/{len(ordered)}] {post['id']} ({channel}) — ❌ {entry['error']}")
        log.append(entry)
        if index < len(ordered) and args.delay > 0:
            time.sleep(args.delay)

    out_path = ROOT / "data" / "deals" / f"published-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"posts": log}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Лог: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
