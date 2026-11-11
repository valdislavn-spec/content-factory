#!/usr/bin/env python3
"""Настройка Telegram-бота через Bot API: что можно автоматизировать без BotFather.

BotFather нужен только для создания бота и ручных настроек (inline mode, права в
каналах). Всё остальное — имя, описания, команды, кнопка меню — настраивается
официальным Bot API. Скрипт делает это одной командой и печатает чек-лист BotFather.

    ./.venv/bin/python scripts/bot_setup.py --check   # что уже настроено
    ./.venv/bin/python scripts/bot_setup.py --dry-run # показать вызовы, не отправлять
    ./.venv/bin/python scripts/bot_setup.py --apply   # применить настройки

Требуется TELEGRAM_BOT_TOKEN в .env. Webhook/inline/payments — только через BotFather
(чек-лист печатается в конце).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.utils import env  # noqa: E402

API_BASE = "https://api.telegram.org"

SHORT_DESCRIPTION = (
    "Реклама в наших Telegram-каналах: выберите канал и тариф, оплата в ⭐ Stars. "
    "Публикация после модерации."
)
DESCRIPTION = (
    "Бот размещения рекламы в наших Telegram-каналах (US/LatAm).\n\n"
    "1. Выберите канал и тариф.\n"
    "2. Оплатите публикацию в ⭐ Telegram Stars.\n"
    "3. Пришлите текст поста — после модерации он выйдет в канале.\n\n"
    "Поддержка: напишите сюда, если нужен счёт или возврат."
)
COMMANDS = [
    {"command": "start", "description": "Выбрать канал и тариф"},
    {"command": "buy", "description": "Показать тарифы"},
    {"command": "orders", "description": "Мои заказы (для админа)"},
    {"command": "help", "description": "Как это работает"},
]


def build_setup_calls() -> List[Dict[str, Any]]:
    """Готовит список вызовов Bot API для настройки бота."""
    return [
        {
            "method": "setMyCommands",
            "payload": {"commands": COMMANDS, "scope": {"type": "default"}},
        },
        {
            "method": "setMyDescription",
            "payload": {"description": DESCRIPTION[:512]},
        },
        {
            "method": "setMyShortDescription",
            "payload": {"short_description": SHORT_DESCRIPTION[:120]},
        },
        {
            "method": "setChatMenuButton",
            "payload": {"menu_button": {"type": "commands"}},
        },
    ]


def botfather_checklist() -> List[str]:
    """Что нельзя сделать через Bot API — только через @BotFather."""
    return [
        "/setinline — включить inline mode (нужно для growth-бота и кнопок «Поделиться»)",
        "/setjoingroups — разрешить/запретить добавление в группы",
        "/setprivacy — privacy mode для групп (если бот работает в чатах)",
        "/setcommands — альтернатива setMyCommands; можно не делать, скрипт настраивает сам",
        "/setuserpic — аватар бота (опционально)",
        "Платёжный провайдер НЕ нужен: оплата в Stars (XTR) идёт без провайдера",
        "Добавить бота админом в каналы с правом «Публикация сообщений»",
        "Получить chat_id для TELEGRAM_ADMIN_CHAT_ID: написать боту /start и посмотреть getUpdates",
    ]


def _api(token: str, method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{API_BASE}/bot{token}/{method}"
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"{method}: HTTP {exc.code}: {detail}") from exc
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def check_bot(token: str) -> Dict[str, Any]:
    """Текущее состояние бота: getMe, getMyCommands, getMyShortDescription."""
    info = _api(token, "getMe").get("result") or {}
    commands = _api(token, "getMyCommands").get("result") or []
    short = _api(token, "getMyShortDescription").get("result") or {}
    return {
        "username": info.get("username"),
        "first_name": info.get("first_name"),
        "commands": [item.get("command") for item in commands if isinstance(item, dict)],
        "short_description": short.get("short_description", ""),
    }


def apply_setup(token: str, dry_run: bool = False) -> List[str]:
    """Применяет настройки; возвращает список выполненных методов."""
    applied: List[str] = []
    for call in build_setup_calls():
        if dry_run:
            applied.append(f"[dry-run] {call['method']}: {json.dumps(call['payload'], ensure_ascii=False)[:160]}")
            continue
        data = _api(token, call["method"], call["payload"])
        if not data.get("ok", False):
            raise RuntimeError(f"{call['method']}: {data.get('description') or 'ok=false'}")
        applied.append(call["method"])
    return applied


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Настройка Telegram-бота через Bot API")
    parser.add_argument("--check", action="store_true", help="Показать текущие настройки")
    parser.add_argument("--apply", action="store_true", help="Применить настройки")
    parser.add_argument("--dry-run", action="store_true", help="Показать вызовы без отправки")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    # Settings.load() подхватывает .env в os.environ (utils.env читает только env)
    from content_factory.config import Settings

    Settings.load()
    token = env("TELEGRAM_BOT_TOKEN", "") or ""
    if not token:
        print("Нужен TELEGRAM_BOT_TOKEN в .env")
        return 2
    if args.check:
        try:
            data = check_bot(token)
        except RuntimeError as exc:
            print(f"Bot API: {exc}")
            return 1
        print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.apply or args.dry_run:
        try:
            applied = apply_setup(token, dry_run=bool(args.dry_run))
        except RuntimeError as exc:
            print(f"Bot API: {exc}")
            return 1
        for line in applied:
            print(line)
    if not (args.check or args.apply or args.dry_run):
        print("Укажите --check, --dry-run или --apply")
        return 2
    print("\nЧек-лист BotFather (вручную):")
    for line in botfather_checklist():
        print(f"  • {line}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
