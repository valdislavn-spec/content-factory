#!/usr/bin/env python3
"""Записывает секрет в GitHub Actions (libsodium sealed box).

    GITHUB_TOKEN=... python scripts/set_github_secret.py \
        --repo owner/name --name DISCORD_WEBHOOK_URL --value "https://..."

Нужен пакет pynacl и токен с правами на секреты репозитория.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request

try:
    from nacl import encoding, public
except ImportError:  # pragma: no cover
    print("нужен pynacl: pip install pynacl")
    raise SystemExit(2)


def api(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "content-factory-secrets",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read().decode("utf-8", "replace")
        return json.loads(body) if body.strip() else {}


def encrypt(public_key: str, value: str) -> str:
    key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(key).encrypt(value.encode("utf-8"))
    return base64.b64encode(sealed).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--name", required=True, help="имя секрета")
    parser.add_argument("--value", required=True)
    args = parser.parse_args()

    token = (os.environ.get("GITHUB_TOKEN", "") or "").strip()
    if not token:
        print("нет GITHUB_TOKEN")
        return 2

    key_info = api(f"https://api.github.com/repos/{args.repo}/actions/secrets/public-key", token)
    encrypted = encrypt(key_info["key"], args.value)
    api(
        f"https://api.github.com/repos/{args.repo}/actions/secrets/{args.name}",
        token, "PUT", {"encrypted_value": encrypted, "key_id": key_info["key_id"]},
    )
    print(f"секрет {args.name} записан в {args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
