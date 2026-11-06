#!/usr/bin/env python3
"""Настроить публикацию в Telegram: токен бота, id 6 каналов, выключить dry-run.

Запуск:
    python3 scripts/set_telegram_env.py

Что делает:
1. Скрыто спрашивает токен бота (получить у @BotFather → /newbot).
2. Проверяет токен через Bot API getMe и показывает имя бота.
3. Спрашивает Telegram-id каналов (@username или -100…); Enter — оставить как есть.
4. Пишет значения в content-factory/.env.
5. Спрашивает подтверждение и, если да, выключает dry_run
   (.env: CONTENT_FACTORY_DRY_RUN=false, settings.yaml: app.dry_run: false).

Бот должен быть администратором каждого канала с правом «Публикация».
"""
from __future__ import annotations

import getpass
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

ENV_FILE = pathlib.Path(".env")
SETTINGS_FILE = pathlib.Path("config/settings.yaml")
CHANNELS = [
    ("TELEGRAM_CHAT_ID_TECH_AI", "Tech & AI"),
    ("TELEGRAM_CHAT_ID_BUSINESS_FINANCE", "Business & Finance"),
    ("TELEGRAM_CHAT_ID_SCIENCE_HEALTH", "Science & Health"),
    ("TELEGRAM_CHAT_ID_AUTO", "Autos & Mobility"),
    ("TELEGRAM_CHAT_ID_TRAVEL", "Travel"),
    ("TELEGRAM_CHAT_ID_CULTURE", "Culture & Entertainment"),
]


def read_env() -> dict:
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            env[name.strip()] = value.strip()
    return env


def update_env(values: dict) -> None:
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    for name, value in values.items():
        line = f"{name}={value}"
        if re.search(rf"(?m)^{re.escape(name)}=.*$", text):
            text = re.sub(rf"(?m)^{re.escape(name)}=.*$", lambda _m: line, text, count=1)
        else:
            text = text.rstrip("\n") + "\n\n" + line + "\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


def api(token: str, method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {"Accept": "application/json"}
    if params:
        data = json.dumps(params).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"сеть: {type(exc).__name__}: {exc}") from exc


def ask_token() -> str:
    raw = getpass.getpass("Токен бота от @BotFather (скрыто): ").strip()
    return raw


def main() -> int:
    if not ENV_FILE.exists():
        print("Не найден .env — скопируйте .env.example в .env", file=sys.stderr)
        return 2
    env = read_env()

    token = ask_token()
    if not token:
        print("Токен не введён.", file=sys.stderr)
        return 1
    try:
        me = api(token, "getMe")
        username = (me.get("result") or {}).get("username") or "?"
        print(f"Бот: @{username} — токен рабочий")
    except RuntimeError as exc:
        print(f"Токен не прошёл проверку: {exc}", file=sys.stderr)
        return 1

    print("\nTelegram-id каналов (@username или -1001234567890).")
    print("Enter — оставить текущее значение из .env.")
    updates = {"TELEGRAM_BOT_TOKEN": token}
    for var, title in CHANNELS:
        current = env.get(var, "")
        suffix = f" [{current}]" if current else ""
        value = input(f"{title} ({var}){suffix}: ").strip()
        if value:
            updates[var] = value
        elif current:
            updates[var] = current
        else:
            print(f"  {var} пуст — канал будет пропущен (dry-run) до заполнения")
    update_env(updates)
    print("\nЗаписано в .env.")

    # Проверяем, что бот видит каналы (не критично: getChat может быть недоступен).
    print("\nПроверка доступа бота к каналам:")
    for var, title in CHANNELS:
        chat_id = updates.get(var, "")
        if not chat_id:
            continue
        try:
            data = api(token, "getChat", {"chat_id": chat_id})
            chat_title = (data.get("result") or {}).get("title") or chat_id
            print(f"  ок: {title} → {chat_title}")
        except RuntimeError as exc:
            print(f"  внимание: {title} ({chat_id}) — {exc}")
            print("    добавьте бота администратором канала с правом «Публикация»")

    answer = input(
        "\nВключить реальную публикацию (выключить dry_run)? [y/N]: "
    ).strip().lower()
    if answer in ("y", "yes", "д", "да"):
        env_text = ENV_FILE.read_text(encoding="utf-8")
        if "CONTENT_FACTORY_DRY_RUN=" in env_text:
            env_text = re.sub(
                r"(?m)^CONTENT_FACTORY_DRY_RUN=.*$",
                "CONTENT_FACTORY_DRY_RUN=false",
                env_text,
                count=1,
            )
            ENV_FILE.write_text(env_text, encoding="utf-8")
        settings = SETTINGS_FILE.read_text(encoding="utf-8")
        settings = re.sub(r"(?m)^(\s*)dry_run:\s*true\s*$", r"\1dry_run: false", settings)
        SETTINGS_FILE.write_text(settings, encoding="utf-8")
        print("dry_run выключен: посты будут уходить в Telegram.")
    else:
        print("dry_run оставлен включённым — посты пишутся в data/outbox.")

    print("\nДальше:")
    print("  python3 -m content_factory run --channel tech-ai   # тестовая публикация")
    print("  python3 -m content_factory daemon                  # работа по расписанию (каждый час)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
