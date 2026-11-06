#!/usr/bin/env python3
"""Записать бесплатные API-ключи (LLM и новости) в content-factory/.env.

Запуск:
    python3 scripts/set_extra_keys.py

Ключи вводятся скрыто (getpass), по возможности проверяются запросом к API;
пустой ввод (Enter) пропускает пункт. Значения ключей в чат/лог не выводятся.

Что подключаем:
  Groq / OpenRouter / SambaNova / HuggingFace / OpenAI — LLM (цепочка fallback);
  newsdata.io / Currents API — дополнительные новостные источники;
  APITube / Trends API — записываются без проверки (эндпоинты могут отличаться).

Runway, IntelX, mem0 в контент-заводе не используются: это не новости/тренды/LLM
для текстовых постов.
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


def _get(url: str, headers: dict | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.status, response.read().decode("utf-8", "replace")[:500]
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # сеть недоступна — не блокируем запись
        return 0, f"{type(exc).__name__}: {exc}"


def validate_bearer(url: str):
    def check(key: str) -> tuple[bool, str]:
        status, _ = _get(url, {"Authorization": "Bearer " + key, "Accept": "application/json"})
        if status == 0:
            return True, "проверить не удалось (нет сети), записываю"
        if status in (200, 201):
            return True, "ключ рабочий"
        if status in (401, 403):
            return False, f"ключ не принят (HTTP {status})"
        if status == 429:
            return True, "ключ принят, но лимит запросов исчерпан (HTTP 429)"
        return True, f"HTTP {status}: записываю как есть"

    return check


def validate_query(template: str):
    def check(key: str) -> tuple[bool, str]:
        url = template.format(key=key)
        status, _ = _get(url, {"Accept": "application/json"})
        if status == 0:
            return True, "проверить не удалось (нет сети), записываю"
        if status in (200, 201):
            return True, "ключ рабочий"
        if status in (401, 403):
            return False, f"ключ не принят (HTTP {status})"
        if status == 429:
            return True, "ключ принят, но дневной лимит исчерпан (HTTP 429)"
        return True, f"HTTP {status}: записываю как есть"

    return check


def no_validation(label: str):
    def check(key: str) -> tuple[bool, str]:
        return True, "эндпоинт не проверяю, записываю как есть"

    return check


ITEMS = [
    ("GROQ_API_KEY", "Groq (LLM, бесплатный тариф)", validate_bearer("https://api.groq.com/openai/v1/models")),
    ("OPENROUTER_API_KEY", "OpenRouter (LLM, free-модели)", validate_bearer("https://openrouter.ai/api/v1/key")),
    ("SAMBANOVA_API_KEY", "SambaNova (LLM, free tier)", validate_bearer("https://api.sambanova.ai/v1/models")),
    ("HUGGINGFACE_API_KEY", "HuggingFace Inference (LLM, ПЛАТНО: у free 0 кредитов, PRO $2/мес)",
     validate_bearer("https://router.huggingface.co/v1/models")),
    ("OPENAI_API_KEY", "OpenAI (LLM, платный)", validate_bearer("https://api.openai.com/v1/models")),
    ("NEWSDATA_API_KEY", "newsdata.io (новости, free)", validate_query(
        "https://newsdata.io/api/1/latest?apikey={key}&language=en&size=1")),
    ("CURRENTS_API_KEY", "Currents API (новости, free)", validate_query(
        "https://api.currentsapi.services/v1/latest-news?apiKey={key}&language=en")),
    ("APITUBE_API_KEY", "APITube (новости)", no_validation("APITube")),
    ("TRENDS_API_KEY", "Trends API (тренды, если есть)", no_validation("Trends")),
]


def main() -> int:
    if not ENV_FILE.exists():
        print("Не найден .env — скопируйте .env.example в .env", file=sys.stderr)
        return 2
    env = read_env()
    saved = []
    print("Вставляй ключи по одному (ввод скрыт). Enter — пропустить.\n")
    for name, label, validator in ITEMS:
        current = "задан" if env.get(name) else "пусто"
        try:
            key = getpass.getpass(f"{label} [{name}, сейчас {current}]: ").strip()
        except EOFError:
            key = ""
        if not key:
            print("  пропущено\n")
            continue
        ok, detail = validator(key)
        print(f"  {detail}")
        if not ok:
            print("  ключ не записан\n")
            continue
        write_env(name, key)
        saved.append(name)
        print("  записан в .env\n")
    if saved:
        print("Готово:", ", ".join(saved))
        print("Дальше: ./.venv/bin/python -m content_factory llm-test")
    else:
        print("Ничего не записано.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
