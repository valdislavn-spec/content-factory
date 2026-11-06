#!/usr/bin/env python3
"""Записать API-ключи Dify-приложений (новости, тренды, SEO) в content-factory/.env.

Запуск:
    python3 scripts/set_dify_app_keys.py

Ключи вводятся скрыто (getpass), проверяются через GET /v1/info и показываются
как имя приложения + тип. Пустой ввод (Enter) пропускает приложение.
Скрипт идемпотентен: повторный запуск заменяет ключи в .env.

Ключи приложений Dify берутся внутри приложения: Access Point → API Keys →
Create new API key. Ключ одного приложения НЕ подходит к другому.
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

# (переменная в .env, человекочитаемое назначение)
APPS = [
    ("DIFY_POSTS_API_KEY", "готовые посты (Six-Channel Editorial News Draft Factory)"),
    ("DIFY_NEWS_API_KEY", "новостной агрегатор / research (Tavily, Currents API)"),
    ("DIFY_TRENDS_API_KEY", "поиск трендов"),
    ("DIFY_SEO_API_KEY", "SEO-оптимизация постов"),
]


def read_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                env[name.strip()] = value.strip()
    return env


def base_url(env: dict) -> str:
    return (env.get("DIFY_BASE_URL") or "https://api.dify.ai/v1").rstrip("/")


def ask_key(env: dict, label: str) -> str:
    try:
        raw = getpass.getpass(f"Ключ «{label}» (Enter — пропустить): ")
    except EOFError:
        raw = ""
    value = "".join(raw.split())
    for quote in ('"', "'"):
        value = value.strip(quote)
    # Частая ошибка: Cmd+V дважды → app-xxxapp-xxx
    if value.count("app-") > 1 and len(value) % 2 == 0:
        half = len(value) // 2
        if value[:half] == value[half:]:
            value = value[:half]
            print("  (двойная вставка — исправил)")
    return value


def validate(env: dict, key: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        base_url(env) + "/info", headers={"Authorization": "Bearer " + key}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        name = data.get("name") or "?"
        mode = data.get("mode") or "?"
        return True, f"«{name}», тип: {mode}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        return False, f"HTTP {exc.code}: {body}"
    except Exception as exc:  # сеть недоступна — не теряем ключ
        return True, f"проверить не удалось ({type(exc).__name__}), записываю как есть"


def write_env(values: dict) -> None:
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    for name, value in values.items():
        line = f"{name}={value}"
        if re.search(rf"(?m)^{re.escape(name)}=.*$", text):
            text = re.sub(
                rf"(?m)^{re.escape(name)}=.*$", lambda _m, line=line: line, text, count=1
            )
        else:
            text = text.rstrip("\n") + "\n\n" + line + "\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


def main() -> int:
    env = read_env()
    if not ENV_FILE.exists():
        print("Не найден .env — скопируйте .env.example в .env", file=sys.stderr)
        return 2
    updates = {}
    print(
        "Ключи Dify-приложений: каждое приложение → Access Point → API Keys →\n"
        "Create new API key. Enter без ввода = пропустить.\n"
    )
    for name, label in APPS:
        key = ask_key(env, label)
        if not key:
            print(f"  {name}: пропущено")
            continue
        ok, detail = validate(env, key)
        if not ok:
            print(f"  {name}: Dify отклонил ключ — {detail}. Не записан.")
            continue
        updates[name] = key
        print(f"  {name}: ок — {detail}")
    if not updates:
        print("\nНичего не записано.")
        return 1
    write_env(updates)
    print(f"\nЗаписано в .env: {', '.join(updates)}")
    print("Дальше сообщи агенту «ключи вписал» — он проверит входы/выходы приложений.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
