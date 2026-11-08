#!/usr/bin/env python3
"""OAuth-помощник Mastodon: регистрация приложения, получение токена, проверка.

Шаги:
  1) python scripts/mastodon_auth.py register
     → создаёт OAuth-приложение (без аккаунта) и печатает ссылку авторизации;
  2) зарегистрируйтесь на https://mastodon.social/start (email + пароль);
  3) откройте ссылку авторизации под своим аккаунтом → Authorize → скопируйте код;
  4) python scripts/mastodon_auth.py token --code ВАШ_КОД --write-env
     → обменивает код на access token и записывает MASTODON_BASE_URL/TOKEN в .env;
  5) python scripts/mastodon_auth.py check
     → проверяет токен (verify_credentials).

Приложение хранится в data/mastodon_app.json (gitignored). Права: read:accounts,
write:statuses — ничего лишнего.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
APP_FILE = ROOT / "data" / "mastodon_app.json"
DEFAULT_INSTANCE = "https://mastodon.social"
DEFAULT_SCOPES = "read:accounts write:statuses"
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


class MastodonAuthError(RuntimeError):
    """Ошибка OAuth/API Mastodon."""


def _post(url: str, payload: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "factory-mastodon-auth/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise MastodonAuthError(f"HTTP {exc.code} от {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise MastodonAuthError(f"сеть недоступна: {exc}") from exc


def _get(url: str, token: str, timeout: int = 30) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json",
                 "User-Agent": "factory-mastodon-auth/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise MastodonAuthError(f"HTTP {exc.code} от {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise MastodonAuthError(f"сеть недоступна: {exc}") from exc


def register_app(instance: str = DEFAULT_INSTANCE, name: str = "content-factory",
                 scopes: str = DEFAULT_SCOPES, website: str = "") -> Dict[str, Any]:
    payload = {"client_name": name, "redirect_uris": REDIRECT_URI, "scopes": scopes}
    if website:
        payload["website"] = website
    app = _post(instance.rstrip("/") + "/api/v1/apps", payload)
    for field in ("client_id", "client_secret"):
        if not app.get(field):
            raise MastodonAuthError(f"инстанс не вернул {field}")
    app.update({"instance": instance.rstrip("/"), "scopes": scopes})
    APP_FILE.parent.mkdir(parents=True, exist_ok=True)
    APP_FILE.write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    return app


def authorization_url(app: Dict[str, Any]) -> str:
    instance = app["instance"].rstrip("/")
    query = urllib.parse.urlencode(
        {
            "client_id": app["client_id"],
            "redirect_uri": app.get("redirect_uri") or REDIRECT_URI,
            "response_type": "code",
            "scope": app.get("scopes") or DEFAULT_SCOPES,
        }
    )
    return f"{instance}/oauth/authorize?{query}"


def exchange_code(app: Dict[str, Any], code: str) -> Dict[str, Any]:
    data = _post(
        app["instance"].rstrip("/") + "/oauth/token",
        {
            "grant_type": "authorization_code",
            "code": str(code).strip(),
            "client_id": app["client_id"],
            "client_secret": app["client_secret"],
            "redirect_uri": app.get("redirect_uri") or REDIRECT_URI,
            "scope": app.get("scopes") or DEFAULT_SCOPES,
        },
    )
    if not data.get("access_token"):
        raise MastodonAuthError(f"нет access_token в ответе: {str(data)[:200]}")
    return data


def verify_credentials(instance: str, token: str) -> Dict[str, Any]:
    return _get(instance.rstrip("/") + "/api/v1/accounts/verify_credentials", token)


def write_env(base: str, token: str, env_path: Optional[Path] = None) -> Path:
    path = env_path or (ROOT / ".env")
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    updates = {"MASTODON_BASE_URL": base.rstrip("/"), "MASTODON_TOKEN": token}
    seen = set()
    result = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if key in updates:
            result.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            result.append(line)
    for key, value in updates.items():
        if key not in seen:
            result.append(f"{key}={value}")
    path.write_text("\n".join(result) + "\n", encoding="utf-8")
    return path


def load_app() -> Dict[str, Any]:
    if not APP_FILE.is_file():
        raise MastodonAuthError(
            "нет data/mastodon_app.json — сначала: python scripts/mastodon_auth.py register"
        )
    return json.loads(APP_FILE.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["register", "token", "check"])
    parser.add_argument("--instance", default=DEFAULT_INSTANCE)
    parser.add_argument("--name", default="content-factory")
    parser.add_argument("--website", default="")
    parser.add_argument("--code", default="", help="код из окна Authorize")
    parser.add_argument("--write-env", action="store_true", help="записать MASTODON_* в .env")
    args = parser.parse_args()
    try:
        if args.command == "register":
            app = register_app(args.instance, args.name, DEFAULT_SCOPES, args.website)
            print(f"Приложение создано: {app['instance']} (client_id={app['client_id'][:8]}…)")
            print(f"Файл: {APP_FILE}")
            print("\nСсылка для авторизации (после регистрации аккаунта):\n" + authorization_url(app))
            return 0
        if args.command == "token":
            app = load_app()
            if not args.code:
                print("Нужен --code из окна Authorize.")
                return 2
            data = exchange_code(app, args.code)
            token = data["access_token"]
            if args.write_env:
                path = write_env(app["instance"], token)
                print(f"Токен записан в {path}")
            else:
                print("access_token:", token)
                print("Добавьте в .env: MASTODON_BASE_URL / MASTODON_TOKEN или запустите с --write-env")
            return 0
        if args.command == "check":
            app = load_app()
            # токен: из .env (приоритет) или из data/mastodon_app.json, если сохранён
            env_path = ROOT / ".env"
            base, token = app["instance"], str(app.get("access_token") or "")
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("MASTODON_BASE_URL="):
                        base = line.split("=", 1)[1].strip()
                    elif line.startswith("MASTODON_TOKEN="):
                        token = line.split("=", 1)[1].strip()
            if not token:
                print("Токен не найден: получите его командой token --code … --write-env")
                return 2
            account = verify_credentials(base, token)
            print(f"OK: @{account.get('username')} ({account.get('acct')}) на {base}")
            print(f"followers={account.get('followers_count')} statuses={account.get('statuses_count')}")
            return 0
    except MastodonAuthError as exc:
        print(f"Ошибка: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
