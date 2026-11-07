#!/usr/bin/env python3
"""Проверка Cohere: ключ, доступные модели и Chat через Compatibility API.

Cohere отдаёт OpenAI-совместимый endpoint, поэтому фабрика работает с ним как
с ``openai_compatible``-провайдером (``config/settings.yaml`` → ``llm.providers.cohere``).

Важно: из РФ ``api.cohere.ai`` отдаёт HTTP 403 (гео-блок Cloudflare), поэтому
локальный запуск может не пройти — проверяйте из GitHub Actions (workflow
``cohere-check``) или через VPN. Ключ никогда не печатается.

Запуск::

    ./.venv/bin/python scripts/cohere_check.py
    ./.venv/bin/python scripts/cohere_check.py --models command-a-03-2025,command-r7b-12-2024
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content_factory.utils import env, load_dotenv  # noqa: E402

BASE = "https://api.cohere.ai"
COMPAT = BASE + "/compatibility/v1"
USER_AGENT = (
    "Mozilla/5.0 (compatible; ContentFactory/1.0; +https://t.me/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"
)
DEFAULT_MODELS = [
    "command-a-plus-05-2026",
    "command-a-03-2025",
    "command-r-plus-08-2024",
    "command-r7b-12-2024",
    "command-r-08-2024",
]
NON_CHAT_PREFIXES = ("embed", "rerank", "parse", "cohere-transcribe")


def api(method: str, url: str, payload=None, key: str = "", timeout: float = 30.0):
    """HTTP-запрос с JSON. Возвращает (status, data) или бросает HTTPError."""
    headers = {
        "Authorization": "Bearer " + key,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
        try:
            return response.status, json.loads(body or "{}")
        except ValueError:
            return response.status, {"raw": body[:500]}


def mask(key: str) -> str:
    if not key:
        return "—"
    if len(key) <= 12:
        return key[:4] + "…"
    return "{}…{}".format(key[:9], key[-4:])


def list_models(key: str) -> bool:
    """Показать модели, доступные ключу. True, если список получен."""
    for path in ("/v1/models", "/compatibility/v1/models"):
        url = BASE + path
        try:
            status, data = api("GET", url, key=key)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            print("GET {} -> HTTP {} {}".format(path, exc.code, detail.replace("\n", " ")))
            continue
        except Exception as exc:  # noqa: BLE001
            print("GET {} -> ОШИБКА {}: {}".format(path, type(exc).__name__, exc))
            continue
        names = [str(item.get("name") or "") for item in (data.get("models") or [])]
        chat = [name for name in names if name and not name.startswith(NON_CHAT_PREFIXES)]
        print("GET {} -> {}".format(path, status))
        print("  всего моделей: {}, чат-моделей: {}".format(len(names), len(chat)))
        for name in chat:
            print("  - {}".format(name))
        return True
    return False


def probe_models(key: str, models) -> int:
    """Минимальный Chat-запрос к каждой модели. Возвращает число рабочих."""
    ok = 0
    for model in models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Ответь одним словом: ОК"}],
            "max_tokens": 8,
            "temperature": 0,
        }
        try:
            status, data = api(
                "POST", COMPAT + "/chat/completions", payload=payload, key=key
            )
            choices = data.get("choices") or []
            text = ""
            if choices:
                text = str((choices[0].get("message") or {}).get("content") or "")
            print("chat {:<26} -> {} | «{}»".format(model, status, text.strip()[:80]))
            ok += 1
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            print(
                "chat {:<26} -> HTTP {} {}".format(
                    model, exc.code, detail.replace("\n", " ")
                )
            )
        except Exception as exc:  # noqa: BLE001
            print("chat {:<26} -> ОШИБКА {}: {}".format(model, type(exc).__name__, exc))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        default=os.environ.get("COHERE_MODELS", ""),
        help="модели через запятую (по умолчанию — список кандидатов)",
    )
    args = parser.parse_args()

    load_dotenv()
    key = env("COHERE_API_KEY", "")
    print("Cohere check | ключ: {}".format(mask(key)))
    if not key:
        print("COHERE_API_KEY не задан: добавьте его в .env или GitHub Secrets.")
        return 1

    models = [item.strip() for item in (args.models or "").split(",") if item.strip()]
    models = models or DEFAULT_MODELS

    listed = list_models(key)
    ok = probe_models(key, models)
    if ok:
        print("\nИтог: Cohere доступен, рабочих моделей: {}.".format(ok))
        return 0
    if not listed:
        print(
            "\nИтог: API недоступен. Если это локальный запуск из РФ — "
            "это ожидаемо (403 гео-блок), запустите workflow cohere-check."
        )
    else:
        print("\nИтог: модели не ответили — проверьте доступ модели по ключу.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
