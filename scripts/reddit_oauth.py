#!/usr/bin/env python3
"""One-time OAuth для Reddit: получаем refresh_token (без хранения пароля).

Шаг 1 (URL):    python scripts/reddit_oauth.py --url
                (нужен REDDIT_CLIENT_ID)
Шаг 2: открой URL в браузере, войди в Reddit, разреши доступ.
       Браузер редиректнёт на http://localhost:8080/?state=...&code=XXXX —
       страница не откроется, но в адресной строке будет code.
Шаг 3 (обмен):  python scripts/reddit_oauth.py --code XXXX
                (нужны REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET)
       Скрипт сохранит refresh_token в data/reddit_refresh_token.txt и покажет
       маскированно. Дальше — GitHub Secret REDDIT_REFRESH_TOKEN.

Почему так: password-grant не работает с 2FA, а refresh-token можно отозвать
в любой момент (Reddit → Settings → Apps → revoke).
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.publishers.social import SocialAPIError, http_json  # noqa: E402

AUTH_URL = "https://www.reddit.com/api/v1/authorize"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDIRECT = "http://localhost:8080"
SCOPE = "submit,read,identity"
STATE = "contentfactory"
UA = "script:content-factory:1.0 (by /u/content-factory)"


def _env(name: str) -> str:
    value = os.environ.get(name, "") or ""
    if not value:
        print(f"Ошибка: {name} не задан", file=sys.stderr)
        raise SystemExit(2)
    return value


def auth_link() -> str:
    params = {
        "client_id": _env("REDDIT_CLIENT_ID"),
        "response_type": "code",
        "state": STATE,
        "redirect_uri": REDIRECT,
        "duration": "permanent",
        "scope": SCOPE,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def exchange(code: str) -> str:
    client_id = _env("REDDIT_CLIENT_ID")
    client_secret = _env("REDDIT_CLIENT_SECRET")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = http_json(
        TOKEN_URL,
        payload={
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": REDIRECT,
        },
        headers={"Authorization": f"Basic {basic}", "User-Agent": UA},
        form=True,
    )
    refresh = str(data.get("refresh_token") or "")
    if not refresh:
        raise SystemExit("Reddit не вернул refresh_token: {}".format(data))
    out = ROOT / "data" / "reddit_refresh_token.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(refresh, encoding="utf-8")
    print("refresh_token сохранён: {}".format(out))
    print("маскировано: {}…{}".format(refresh[:6], refresh[-4:]))
    print("Дальше: GitHub → Settings → Secrets → REDDIT_REFRESH_TOKEN")
    return refresh


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="store_true", help="напечатать ссылку авторизации")
    parser.add_argument("--code", default="", help="код из redirect-URL")
    args = parser.parse_args()
    if args.url:
        print("Открой в браузере (где залогинен Reddit):")
        print(auth_link())
        print(f"\nПосле «Allow» браузер уйдёт на {REDIRECT}/?state=…&code=…")
        print("Скопируй значение параметра code из адресной строки.")
        return 0
    if args.code:
        exchange(args.code)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
