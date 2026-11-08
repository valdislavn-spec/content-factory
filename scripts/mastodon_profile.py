#!/usr/bin/env python3
"""Оформление профиля Mastodon: аватар, шапка, био, ссылки, флаг бота.

    # токен с scope write:accounts (создаётся scripts/mastodon_auth.py register
    # с scopes read:accounts write:accounts read:statuses write:statuses)
    python scripts/mastodon_profile.py --dry-run
    python scripts/mastodon_profile.py

Токен берётся из data/mastodon_app_profile.json (access_token) или MASTODON_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PROFILE_APP = ROOT / "data" / "mastodon_app_profile.json"
AVATAR = ROOT / "assets" / "mastodon" / "avatar.png"
HEADER = ROOT / "assets" / "mastodon" / "header.png"

DISPLAY_NAME = "Content Factory"
NOTE = (
    "AI, crypto and sports news in short form — with context and sources. "
    "Telegram channels:\n"
    "AI: https://t.me/AINEWS0007\n"
    "Crypto: https://t.me/HOOPY0007\n"
    "Sports: https://t.me/SPORTNews0007\n"
    "ES: https://t.me/WORLDNews0007 · https://t.me/TechnologiesNews01"
)
# Mastodon разрешает максимум 4 поля в профиле — ES-каналы объединены в одно.
FIELDS = [
    ("AI News", "https://t.me/AINEWS0007"),
    ("Crypto", "https://t.me/HOOPY0007"),
    ("US Sports", "https://t.me/SPORTNews0007"),
    ("ES", "https://t.me/WORLDNews0007 · https://t.me/TechnologiesNews01 · https://t.me/SPORTSAnalytics007"),
]
EXTRA_FIELDS = {"bot": "true", "discoverable": "true", "indexable": "true"}


class ProfileError(RuntimeError):
    pass


def load_credentials() -> Tuple[str, str]:
    """(base, token) из profile-app или .env."""
    base, token = "", ""
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MASTODON_BASE_URL="):
                base = line.split("=", 1)[1].strip()
            elif line.startswith("MASTODON_TOKEN="):
                token = line.split("=", 1)[1].strip()
    if PROFILE_APP.is_file():
        app = json.loads(PROFILE_APP.read_text(encoding="utf-8"))
        base = app.get("instance") or base
        token = app.get("access_token") or token
    return base, token


def _multipart(fields: Dict[str, str], files: Dict[str, Path]) -> Tuple[bytes, str]:
    boundary = "----factory" + str(abs(hash(tuple(sorted(fields)) + tuple(sorted(files)))))
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    for name, path in files.items():
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        parts.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                f"filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n"
            ).encode()
            + path.read_bytes()
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _patch(base: str, token: str, fields: Dict[str, str], files: Optional[Dict[str, Path]] = None) -> Dict[str, Any]:
    body, content_type = _multipart(fields, files or {})
    request = urllib.request.Request(
        base.rstrip("/") + "/api/v1/accounts/update_credentials",
        data=body,
        method="PATCH",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "factory-mastodon-profile/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise ProfileError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProfileError(f"сеть недоступна: {exc}") from exc


def apply_profile(base: str, token: str, avatar: Path = AVATAR, header: Path = HEADER,
                  dry_run: bool = False) -> Dict[str, Any]:
    fields: Dict[str, str] = {"display_name": DISPLAY_NAME, "note": NOTE, **EXTRA_FIELDS}
    for index, (name, value) in enumerate(FIELDS):
        fields[f"fields_attributes[{index}][name]"] = name
        fields[f"fields_attributes[{index}][value]"] = value
    if dry_run:
        return {"dry_run": True, "fields": fields, "avatar": str(avatar), "header": str(header)}
    account = _patch(base, token, fields)
    for label, path in (("avatar", avatar), ("header", header)):
        if path.is_file():
            account = _patch(base, token, {}, {label: path})
    return {
        "url": account.get("url"),
        "display_name": account.get("display_name"),
        "note": account.get("note"),
        "bot": account.get("bot"),
        "fields": account.get("fields"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--avatar", default=str(AVATAR))
    parser.add_argument("--header", default=str(HEADER))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base, token = load_credentials()
    if not base:
        base = "https://mastodon.social"
    if not token and not args.dry_run:
        print("Нет токена: получите его через scripts/mastodon_auth.py и сохраните access_token "
              "в data/mastodon_app_profile.json")
        return 2
    try:
        result = apply_profile(base, token, Path(args.avatar), Path(args.header), args.dry_run)
    except ProfileError as exc:
        print(f"Ошибка профиля: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
