#!/usr/bin/env python3
"""Оформление каналов: название, описание, аватар — из config/channel_branding.yaml.

    ./.venv/bin/python scripts/telegram_branding.py --dry-run
    ./.venv/bin/python scripts/telegram_branding.py --only signals
    ./.venv/bin/python scripts/telegram_branding.py            # применить всё

Нужен TELEGRAM_BOT_TOKEN и права администратора с «Менять информацию».
Chat id берётся из config/channels.{en,es}.yaml либо из переменной окружения,
указанной в поле chat_env.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from content_factory.utils import env, load_dotenv  # noqa: E402

BRANDING = ROOT / "config" / "channel_branding.yaml"
USER_AGENT = (
    "Mozilla/5.0 (compatible; ContentFactory/1.0; +https://t.me/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"
)
DESCRIPTION_LIMIT = 255
TITLE_LIMIT = 128


def api_base() -> str:
    return (env("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")


def call(token: str, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST application/x-www-form-urlencoded (title/description)."""
    import urllib.error
    import urllib.parse
    import urllib.request

    body = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode()
    request = urllib.request.Request(
        f"{api_base()}/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if "is not modified" in detail:
            # Значение уже такое — Telegram отвечает 400. Для нас это успех.
            return {"ok": True, "result": True, "unchanged": True}
        raise RuntimeError(f"{method}: HTTP {exc.code} {detail}") from exc


def call_photo(token: str, chat_id: str, photo: Path) -> Dict[str, Any]:
    """POST multipart/form-data для setChatPhoto."""
    import urllib.error
    import urllib.request

    boundary = "----CF" + uuid.uuid4().hex
    parts: List[bytes] = []
    for name, value in (("chat_id", chat_id),):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    mime = mimetypes.guess_type(photo.name)[0] or "image/png"
    parts.append(
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
            f"filename=\"{photo.name}\"\r\nContent-Type: {mime}\r\n\r\n"
        ).encode()
    )
    parts.append(photo.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request = urllib.request.Request(
        f"{api_base()}/bot{token}/setChatPhoto",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": USER_AGENT,
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"setChatPhoto: HTTP {exc.code} {detail}") from exc


def config_chat_ids() -> Dict[str, str]:
    """id → chat_id из конфигов каналов (EN и ES)."""
    out: Dict[str, str] = {}
    for name in ("channels.en.yaml", "channels.es.yaml"):
        path = ROOT / "config" / name
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for channel in data.get("channels") or []:
            if not isinstance(channel, dict):
                continue
            chat_id = str(channel.get("telegram_chat_id") or "").strip()
            if chat_id:
                out[str(channel.get("id"))] = chat_id
    return out


def load_branding() -> List[Dict[str, Any]]:
    data = yaml.safe_load(BRANDING.read_text(encoding="utf-8")) or {}
    channels = [c for c in (data.get("channels") or []) if isinstance(c, dict)]
    if not channels:
        raise SystemExit("config/channel_branding.yaml: пустой список channels")
    return channels


def resolve_chat_id(entry: Dict[str, Any], known: Dict[str, str]) -> str:
    known_id = known.get(str(entry.get("id")) or "")
    if known_id:
        return known_id
    chat_env = str(entry.get("chat_env") or "").strip()
    return (os.environ.get(chat_env, "") if chat_env else "").strip()


def validate(entry: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    title = str(entry.get("title") or "")
    description = str(entry.get("description") or "").strip()
    if not title:
        problems.append("пустой title")
    if len(title) > TITLE_LIMIT:
        problems.append(f"title {len(title)} > {TITLE_LIMIT}")
    if not description:
        problems.append("пустое description")
    if len(description) > DESCRIPTION_LIMIT:
        problems.append(f"description {len(description)} > {DESCRIPTION_LIMIT}")
    photo = entry.get("photo")
    if photo and not (ROOT / str(photo)).exists():
        problems.append(f"нет файла аватара: {photo}")
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Оформление Telegram-каналов")
    parser.add_argument("--dry-run", action="store_true", help="только показать план")
    parser.add_argument("--only", default="", help="id канала (по умолчанию все)")
    parser.add_argument("--skip-photo", action="store_true")
    parser.add_argument("--skip-title", action="store_true")
    parser.add_argument("--verify", action="store_true", help="только прочитать текущее оформление (getChat)")
    parser.add_argument("--dump-photos", default="", help="скачать текущие аватары в папку")
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")
    token = (env("TELEGRAM_BOT_TOKEN", "") or "").strip()
    known = config_chat_ids()
    entries = load_branding()
    if args.only:
        entries = [e for e in entries if str(e.get("id")) == args.only]
        if not entries:
            print(f"канал {args.only} не найден в реестре")
            return 2

    problems = {str(e.get("id")): validate(e) for e in entries}
    broken = {k: v for k, v in problems.items() if v}
    for channel_id, issues in broken.items():
        print(f"✗ {channel_id}: " + "; ".join(issues))
    if broken:
        return 2
    if not token and not args.dry_run:
        print("TELEGRAM_BOT_TOKEN не задан")
        return 1

    if args.dump_photos:
        import hashlib

        out_dir = ROOT / args.dump_photos
        out_dir.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            channel_id = str(entry.get("id"))
            chat_id = resolve_chat_id(entry, known)
            if not chat_id:
                print(f"— {channel_id}: нет chat_id")
                continue
            try:
                chat = (call(token, "getChat", {"chat_id": chat_id}) or {}).get("result") or {}
                photo = chat.get("photo") or {}
                file_id = photo.get("big_file_id") or ""
                if not file_id:
                    print(f"— {channel_id}: аватара нет")
                    continue
                info = (call(token, "getFile", {"file_id": file_id}) or {}).get("result") or {}
                path = str(info.get("file_path") or "")
                base = api_base()
                raw = urllib.request.urlopen(
                    f"{base}/file/bot{token}/{path}", timeout=60,
                    context=__import__("ssl").create_default_context(),
                ).read()
                target = out_dir / f"{channel_id}.jpg"
                target.write_bytes(raw)
                print(
                    f"· {channel_id}: {photo.get('width')}x{photo.get('height')} "
                    f"{len(raw)} байт sha256={hashlib.sha256(raw).hexdigest()[:16]} → {target.name}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"✗ {channel_id}: {exc}")
        return 0

    if args.verify:
        for entry in entries:
            channel_id = str(entry.get("id"))
            chat_id = resolve_chat_id(entry, known)
            if not chat_id:
                print(f"— {channel_id}: нет chat_id — пропуск")
                continue
            try:
                data = call(token, "getChat", {"chat_id": chat_id}) or {}
                chat = data.get("result") or {}
                has_photo = bool((chat.get("photo") or {}).get("big_file_id"))
                desc = str(chat.get("description") or "")
                print(
                    f"· {channel_id}: title={chat.get('title')!r} "
                    f"photo={'есть' if has_photo else 'нет'} "
                    f"desc={len(desc)} симв. {desc[:60]!r}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"✗ {channel_id}: {exc}")
        return 0

    applied = skipped = failed = 0
    for entry in entries:
        channel_id = str(entry.get("id"))
        title = str(entry.get("title") or "").strip()
        description = str(entry.get("description") or "").strip()
        photo = ROOT / str(entry.get("photo") or "") if entry.get("photo") else None
        chat_id = resolve_chat_id(entry, known)

        if not chat_id:
            hint = entry.get("chat_env") or "config/channels.*.yaml"
            print(f"— {channel_id}: нет chat_id ({hint}) — пропуск")
            skipped += 1
            continue

        if args.dry_run:
            print(
                f"· {channel_id} ({chat_id}): title={title!r} "
                f"desc={len(description)} симв., photo={photo.name if photo else '—'}"
            )
            continue

        steps = []
        if not args.skip_title:
            steps.append(("title", lambda: call(token, "setChatTitle", {"chat_id": chat_id, "title": title})))
        steps.append(("description", lambda: call(token, "setChatDescription", {"chat_id": chat_id, "description": description})))
        if photo and not args.skip_photo:
            steps.append(("photo", lambda: call_photo(token, chat_id, photo)))

        done: List[str] = []
        errors: List[str] = []
        for name, action in steps:
            for attempt in range(1, 4):
                try:
                    action()
                    done.append(name)
                    break
                except Exception as exc:  # noqa: BLE001
                    text = str(exc)
                    transient = "Connection reset" in text or "timed out" in text or "HTTP 5" in text
                    if attempt < 3 and transient:
                        time.sleep(3 * attempt)
                        continue
                    errors.append(f"{name}: {text[:150]}")
                    break

        if errors:
            print(f"✗ {channel_id} ({chat_id}): " + " | ".join(errors) + (f" · сделано: {', '.join(done)}" if done else ""))
            failed += 1
        else:
            print(f"✓ {channel_id} ({chat_id}): {', '.join(done)}")
            applied += 1

    print(f"\nобновлено: {applied} · пропущено: {skipped} · ошибок: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
