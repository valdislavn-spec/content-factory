#!/usr/bin/env python3
"""Inbound-воронка ВП: читает сообщения боту и отвечает предложением обмена.

Бот не может писать первым — поэтому владельцы каналов сами пишут боту
(@Novyi0007Bot), а скрипт ловит /start, «вп», «реклама», «ad exchange» и т.п.
и отвечает условиями ВП, сохраняя заявки в data/vp_leads.jsonl.

Запускается workflow vp-bot-inbox.yml (каждые 10 минут), состояние offset —
в data/vp_bot_state.json (кэш Actions).

    python scripts/vp_bot_inbox.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "vp_bot_state.json"
LEADS = ROOT / "data" / "vp_leads.jsonl"

TRIGGERS = (
    "/start",
    "вп",
    "реклам",
    "обмен",
    "сотруднич",
    "advert",
    "ad exchange",
    "cross",
    "promo",
    "publicidad",
    "intercambio",
    "colaboraci",
)

REPLIES = {
    "ru": (
        "Привет 👋 Это сеть Telegram-каналов (US-спорт, ИИ, крипто + ES-ветка).\n\n"
        "Мы открыты к ВП и обмену рекламой: нативный пост 24–48 ч, 1:1 или 2:1 "
        "по охвату, без казино и скама. Крипто-канал: ~3.7k подписчиков, "
        "~165 просмотров/пост.\n\n"
        "Напиши, пожалуйста: название канала, ссылку, тему и средние просмотры — "
        "предложим условия. Сеть: @HOOPY0007 (EN), @SPORTSAnalytics007 (ES, 18+)."
    ),
    "en": (
        "Hi 👋 This is a Telegram network (US sports, AI, crypto + ES branch).\n\n"
        "We're open to cross-promo/ad exchange: native post 24–48h, 1:1 or 2:1 by "
        "reach, no casino/scam. Crypto channel: ~3.7k subscribers, ~165 views/post.\n\n"
        "Please share: channel name, link, topic and average views — we'll propose "
        "terms. Network: @HOOPY0007 (EN), @SPORTSAnalytics007 (ES, 18+)."
    ),
    "es": (
        "Hola 👋 Somos una red de canales de Telegram (deportes US, IA, cripto + "
        "rama ES).\n\n"
        "Estamos abiertos a intercambio de publicidad: post nativo 24–48 h, 1:1 o "
        "2:1 según alcance, sin casino ni estafas. Canal cripto: ~3.7k suscriptores, "
        "~165 vistas/post.\n\n"
        "Cuéntanos: nombre del canal, enlace, temática y vistas medias — te "
        "proponemos condiciones. Red: @HOOPY0007 (EN), @SPORTSAnalytics007 (ES, 18+)."
    ),
}


def detect_lang(text: str) -> str:
    if re.search(r"[а-яё]", text, re.IGNORECASE):
        return "ru"
    if re.search(r"[ñáéíóúü¿¡]|\b(hola|publicidad|intercambio|canal|gracias)\b", text, re.IGNORECASE):
        return "es"
    return "en"


def api(method: str, token: str, base: str, payload: dict | None = None) -> dict:
    url = f"{base.rstrip('/')}/bot{token}/{method}"
    data = urllib.parse.urlencode(payload or {}).encode()
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"offset": 0}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="только показать ответы, не отправлять")
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    base = (os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org").strip()
    if not token:
        print("Нет TELEGRAM_BOT_TOKEN", file=sys.stderr)
        return 2
    state = load_state()
    updates = api("getUpdates", token, base, {
        "offset": state.get("offset", 0),
        "timeout": 1,
        "limit": 50,
        "allowed_updates": json.dumps(["message", "edited_message"]),
    })
    if not updates.get("ok"):
        print("getUpdates error:", updates, file=sys.stderr)
        return 1
    leads = []
    for update in updates.get("result") or []:
        state["offset"] = max(state.get("offset", 0), update["update_id"] + 1)
        message = update.get("message") or update.get("edited_message") or {}
        text = (message.get("text") or "").strip()
        chat = message.get("chat") or {}
        if not text:
            continue
        lowered = text.lower()
        if not any(trigger in lowered for trigger in TRIGGERS):
            continue
        lang = detect_lang(text)
        lead = {
            "time": datetime.now(timezone.utc).isoformat(),
            "user_id": (message.get("from") or {}).get("id"),
            "username": (message.get("from") or {}).get("username"),
            "chat_id": chat.get("id"),
            "text": text[:500],
            "lang": lang,
        }
        leads.append(lead)
        reply = REPLIES[lang]
        print(f"[{lang}] from @{lead['username']} ({lead['user_id']}): {text[:80]}")
        if args.dry_run:
            print("  → ответ:", reply[:100].replace("\n", " "), "...")
            continue
        try:
            api("sendMessage", token, base, {"chat_id": lead["chat_id"], "text": reply})
            print("  → ответ отправлен")
        except Exception as exc:  # noqa: BLE001
            print("  → ошибка отправки:", exc, file=sys.stderr)
    if leads:
        LEADS.parent.mkdir(parents=True, exist_ok=True)
        with LEADS.open("a", encoding="utf-8") as fh:
            for lead in leads:
                fh.write(json.dumps(lead, ensure_ascii=False) + "\n")
    save_state(state)
    print(f"обработано новых заявок: {len(leads)}; offset={state['offset']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
