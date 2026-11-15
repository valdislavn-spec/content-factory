#!/usr/bin/env python3
"""Клиент Kit (ConvertKit) API v3 + v4 с автоопределением кредов.

В .env:
  KIT_API_KEY=...        (Developer settings → API Key)
  KIT_API_SECRET=...     (Developer settings → API Secret; нужен для подписчиков и рассылок)

v3 — https://api.convertkit.com/v3 (api_key + api_secret в query/body).
v4 — https://api.kit.com/v4 (заголовок X-Kit-Api-Key, другие ключи).

Проверка:
  .venv/bin/python scripts/kit_client.py --check
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
V3 = "https://api.convertkit.com/v3"
V4 = "https://api.kit.com/v4"


def env(key: str, default: str = "") -> str:
    import os

    if os.environ.get(key):
        return os.environ[key]
    path = CF / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return default


class KitError(RuntimeError):
    pass


def _request(url: str, method: str = "GET", payload: dict | None = None,
             headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", UA)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body = response.read().decode() or "{}"
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"raw": body[:500]}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:400]
        raise KitError(f"HTTP {error.code}: {detail}") from error


class Kit:
    def __init__(self) -> None:
        self.key = env("KIT_API_KEY")
        self.secret = env("KIT_API_SECRET")
        if not self.key:
            raise KitError("KIT_API_KEY не задан в .env")

    # --- v3 (ключ + секрет) ---
    def v3(self, path: str, params: dict | None = None) -> dict:
        query = {"api_key": self.key}
        if self.secret:
            query["api_secret"] = self.secret
        query.update(params or {})
        return _request(f"{V3}{path}?{urllib.parse.urlencode(query)}")

    def v3_post(self, path: str, payload: dict | None = None) -> dict:
        body = {"api_key": self.key}
        if self.secret:
            body["api_secret"] = self.secret
        body.update(payload or {})
        return _request(f"{V3}{path}", method="POST", payload=body)

    # --- v4 (только ключ) ---
    def v4(self, path: str, params: dict | None = None) -> dict:
        query = urllib.parse.urlencode(params or {})
        suffix = f"?{query}" if query else ""
        return _request(f"{V4}{path}{suffix}", headers={"X-Kit-Api-Key": self.key})

    def v4_post(self, path: str, payload: dict) -> dict:
        return _request(f"{V4}{path}", method="POST", payload=payload,
                        headers={"X-Kit-Api-Key": self.key})

    def v3_delete(self, path: str) -> None:
        query = {"api_key": self.key}
        if self.secret:
            query["api_secret"] = self.secret
        _request(f"{V3}{path}?{urllib.parse.urlencode(query)}", method="DELETE")

    def delete_broadcast(self, broadcast_id: int | str) -> None:
        self.v3_delete(f"/broadcasts/{broadcast_id}")

    # --- высокоуровневые операции ---
    def account(self) -> dict:
        return self.v3("/account")

    def forms(self) -> list:
        return self.v3("/forms").get("forms", [])

    def tags(self) -> list:
        return self.v3("/tags").get("tags", [])

    def custom_fields(self) -> list:
        return self.v3("/custom_fields").get("custom_fields", [])

    def broadcasts(self) -> list:
        return self.v3("/broadcasts").get("broadcasts", [])

    def create_subscriber(self, email: str, first_name: str = "") -> dict:
        return self.v3_post("/subscribers", {"email": email, "first_name": first_name})

    def create_custom_field(self, label: str) -> dict:
        return self.v3_post("/custom_fields", {"label": label})

    def create_broadcast(self, subject: str, content: str, description: str = "") -> dict:
        return self.v3_post("/broadcasts", {
            "subject": subject, "content": content, "description": description,
            "public": False, "published_at": None})

    def check_secret(self) -> str:
        try:
            data = self.account()
            return f"секрет OK, аккаунт: {data.get('name') or data.get('email') or 'получен'}"
        except KitError as error:
            return f"секрет НЕ принят: {error}"


def report() -> None:
    kit = Kit()
    print(f"KIT_API_KEY: {kit.key[:6]}…{kit.key[-4:]} ({len(kit.key)} символов)")
    print(f"KIT_API_SECRET: {'задан' if kit.secret else 'НЕ задан'}"
          + (f" ({len(kit.secret)} символов)" if kit.secret else ""))
    for label, call in (("forms", kit.forms), ("tags", kit.tags),
                        ("custom_fields", kit.custom_fields), ("broadcasts", kit.broadcasts)):
        try:
            items = call()
            print(f"{label}: {len(items)} " + (str([i.get('name') or i.get('label') for i in items][:3]) if items else ""))
        except KitError as error:
            print(f"{label}: ошибка {error}")
    if kit.secret:
        print(kit.check_secret())
    else:
        print("подписчики/рассылки недоступны без KIT_API_SECRET (Developer settings → API Secret)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.check or not args.json:
        report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
