#!/usr/bin/env python3
"""Записать ключ World News API в content-factory/.env и проверить его.

Запуск:
    python3 scripts/set_worldnews_key.py

Ключ вводится скрыто (getpass), проверяется запросом search-news, показывается
остаток дневной квоты. В chat/лог значение ключа не выводится.

Бесплатный тариф: 50 points/сутки; запрос стоит 1 point + 0.01 за результат,
сброс квоты в 00:00 UTC. Ключ: https://worldnewsapi.com/console
"""
from __future__ import annotations

import getpass
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV_FILE = pathlib.Path(".env")
ENV_NAME = "WORLD_NEWS_API_KEY"
SEARCH_URL = "https://api.worldnewsapi.com/search-news"


def read_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                env[name.strip()] = value.strip()
    return env


def write_env(name: str, value: str) -> None:
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
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


def validate(key: str) -> tuple[bool, str]:
    url = SEARCH_URL + "?" + urllib.parse.urlencode(
        {"text": "technology", "number": 1, "language": "en"}
    )
    request = urllib.request.Request(
        url,
        headers={"x-api-key": key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        if exc.code == 401:
            return False, "ключ не принят (HTTP 401). Проверь его в консоли World News API."
        if exc.code == 402:
            return False, "дневная квота уже исчерпана (HTTP 402), попробуй после 00:00 UTC."
        return False, "HTTP {}: {}".format(exc.code, body.strip())
    except Exception as exc:
        return False, "сеть: {}: {}".format(type(exc).__name__, exc)
    try:
        data = json.loads(raw)
    except ValueError:
        return False, "ответ не JSON"
    count = len(data.get("news") or []) if isinstance(data, dict) else 0
    used = headers.get("x-api-quota-used", "?")
    left = headers.get("x-api-quota-left", "?")
    cost = headers.get("x-api-quota-request", "?")
    return True, "ключ рабочий (тест вернул {} новостей; квота: использовано {}, осталось {}, запрос стоил {})".format(
        count, used, left, cost
    )


def main() -> int:
    if not ENV_FILE.exists():
        print("Не найден .env — скопируйте .env.example в .env", file=sys.stderr)
        return 2
    try:
        key = getpass.getpass("Вставь API-ключ World News API (ввод скрыт): ").strip()
    except EOFError:
        key = ""
    if not key:
        print("Пустой ввод.", file=sys.stderr)
        return 1
    ok, detail = validate(key)
    print(detail)
    if not ok:
        print("Ключ не записан.", file=sys.stderr)
        return 1
    write_env(ENV_NAME, key)
    print(f"{ENV_NAME} записан в .env (значение не выводится).")
    print("Дальше: python3 -m content_factory sources check --channel tech-ai")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
