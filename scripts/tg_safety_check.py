#!/usr/bin/env python3
"""Проверка безопасности Telegram-актива: чтобы аккаунт/бот не попали под блокировки.

Что проверяет:
    1. бот живой (getMe) и его админ-права в наших каналах (минимум лишнего);
    2. частоту публикаций (не спамим: >5 постов/час — предупреждение);
    3. рискованные файлы пользовательской сессии Telethon (userbot) — предупреждение;
    4. наличие раскрытия «реклама» в affiliate-конфиге;
    5. следы запрещённых практик в коде (массовые сообщения, поиск/вступление по MTProto).

Запуск (нужен доступ к Bot API; локально — через VPN-прокси):
    ./.venv/bin/python scripts/tg_safety_check.py
    ./.venv/bin/python scripts/tg_safety_check.py --proxy http://127.0.0.1:1081
    ./.venv/bin/python scripts/tg_safety_check.py --json

Секреты не печатаются. Скрипт ничего не меняет — только читает и предупреждает.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.utils import load_dotenv  # noqa: E402

RISKY_PATTERNS = (
    r"contacts\.search",
    r"channels\.searchPosts",
    r"messages\.search",
    r"send_message\(.*@",
    r"join_channel|JoinChannelRequest",
    r"invite.?member|add.?member",
    r"mass.?message|массов",
)


def _load_env() -> Dict[str, str]:
    load_dotenv(ROOT / ".env")
    return dict(os.environ)


def _api(token: str, method: str, payload: Optional[Dict[str, Any]] = None, proxy: str = "") -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {"Content-Type": "application/json"}
    if payload:
        data = json.dumps(payload).encode()
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return {"ok": False, "description": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "description": str(exc)[:120]}
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {"ok": False, "description": "не JSON"}


def _channels() -> List[Dict[str, str]]:
    """Каналы из configs (EN/ES) с username/ссылкой."""
    try:
        from content_factory.config import Settings, load_channels, NETWORK_CHANNEL_FILES

        settings = Settings.load()
        result: List[Dict[str, str]] = []
        seen = set()
        for path in [settings.channels_path] + [
            settings.root / name for name in NETWORK_CHANNEL_FILES
        ]:
            try:
                channels = load_channels(settings, path=path)
            except Exception:
                continue
            for channel in channels:
                if channel.id in seen:
                    continue
                seen.add(channel.id)
                username = ""
                link = str(getattr(channel, "public_url", "") or "")
                match = re.search(r"t\.me/([A-Za-z0-9_]+)", link)
                if match:
                    username = match.group(1)
                result.append({"id": channel.id, "username": username, "chat_id": channel.telegram_chat_id})
        return result
    except Exception:
        return []


def _posting_rate() -> Dict[str, int]:
    try:
        from content_factory.config import Settings
        from content_factory.storage import Storage

        settings = Settings.load()
        with Storage(settings.db_path) as storage:
            day = storage.conn.execute(
                "SELECT COUNT(*) c FROM publishes WHERE date(published_at)=date('now')"
            ).fetchone()["c"]
            hour = storage.conn.execute(
                "SELECT COUNT(*) c FROM publishes WHERE published_at >= datetime('now','-1 hour')"
            ).fetchone()["c"]
        return {"last_day": int(day), "last_hour": int(hour)}
    except Exception:
        return {"last_day": -1, "last_hour": -1}


def _risky_files() -> List[str]:
    findings: List[str] = []
    for path in (ROOT / "data").glob("*.session"):
        findings.append(f"user-сессия Telethon: {path.name}")
    for path in (ROOT / "data").glob("*.session-journal"):
        findings.append(f"journal пользовательской сессии: {path.name}")
    for script in (ROOT / "scripts").glob("*.py"):
        if script.name == "tg_safety_check.py":
            continue
        try:
            text = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in RISKY_PATTERNS:
            if re.search(pattern, text):
                findings.append(f"{script.name}: похоже на '{pattern}'")
                break
    return findings


def _affiliate_disclosure() -> Dict[str, Any]:
    path = ROOT / "config" / "affiliates.yaml"
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        disclosures = data.get("disclosure") or {}
        every = (data.get("rules") or {}).get("affiliate_every", 0)
        ok = bool(disclosures.get("en")) and bool(disclosures.get("es"))
        return {"ok": ok, "affiliate_every": every}
    except Exception:
        return {"ok": False, "affiliate_every": 0}


def run(proxy: str = "") -> Dict[str, Any]:
    env = _load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    warnings: List[str] = []
    info: Dict[str, Any] = {"bot": None, "channels": [], "warnings": warnings}

    if not token:
        warnings.append("TELEGRAM_BOT_TOKEN не задан — проверить бота нельзя")
    else:
        me = _api(token, "getMe", proxy=proxy)
        result = me.get("result") or {}
        info["bot"] = {"ok": bool(me.get("ok")), "username": result.get("username"), "id": result.get("id")}
        if not me.get("ok"):
            warnings.append(f"getMe: {me.get('description')} (нет доступа к Bot API? включите VPN)")
        else:
            for channel in _channels():
                chat = "@" + channel["username"] if channel["username"] else channel["chat_id"]
                rights = _api(token, "getChatMember", {"chat_id": chat, "user_id": result.get("id")}, proxy=proxy)
                member = rights.get("result") or {}
                status = member.get("status", "")
                item = {
                    "channel": channel["id"],
                    "chat": chat,
                    "status": status,
                    "can_post": bool(member.get("can_post_messages")),
                    "can_edit": bool(member.get("can_edit_messages")),
                    "can_invite": bool(member.get("can_invite_users")),
                    "can_restrict": bool(member.get("can_restrict_members")),
                    "can_delete": bool(member.get("can_delete_messages")),
                }
                info["channels"].append(item)
                if status not in ("administrator", "creator"):
                    warnings.append(f"{channel['id']}: бот не админ ({status or 'нет данных'})")
                elif not member.get("can_post_messages"):
                    warnings.append(f"{channel['id']}: бот админ, но без права публикации")
                if member.get("can_restrict_members") or member.get("can_delete_messages"):
                    warnings.append(
                        f"{channel['id']}: у бота есть лишние права (restrict/delete) — "
                        "можно ограничить правами post/edit/invite"
                    )

    rate = _posting_rate()
    info["posting"] = rate
    if rate["last_hour"] > 5:
        warnings.append(f"слишком часто: {rate['last_hour']} публикаций за час (риск спам-фильтров)")
    if rate["last_day"] > 40:
        warnings.append(f"много публикаций за сутки: {rate['last_day']}")

    risky = _risky_files()
    info["risky"] = risky
    for finding in risky:
        warnings.append(f"проверить: {finding}")

    aff = _affiliate_disclosure()
    info["affiliate"] = aff
    if not aff["ok"]:
        warnings.append("в affiliate-конфиге нет раскрытия «реклама» (EN/ES)")
    if not aff.get("affiliate_every"):
        warnings.append("не задано правило частоты affiliate-постов (affiliate_every)")

    info["ok"] = info.get("bot", {}).get("ok", False) and not any(
        "не админ" in w or "без права публикации" in w for w in warnings
    )
    return info


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Безопасность Telegram-актива")
    parser.add_argument("--proxy", default=os.environ.get("TG_PROXY", "http://127.0.0.1:1081"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(proxy=args.proxy)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        bot = report.get("bot") or {}
        print("=== Telegram safety ===")
        print(f"бот: {bot.get('username')} | ok: {bot.get('ok')}")
        print(f"публикации: за час {report['posting'].get('last_hour')}, за сутки {report['posting'].get('last_day')}")
        print(f"affiliate-раскрытие: {'есть' if report['affiliate'].get('ok') else 'НЕТ'}")
        for item in report.get("channels", []):
            print(
                f"  {item['channel']:12} {item['status']:12} post={item['can_post']} "
                f"edit={item['can_edit']} invite={item['can_invite']} restrict={item['can_restrict']}"
            )
        if report["warnings"]:
            print("\n⚠️ Предупреждения:")
            for warning in report["warnings"]:
                print("  •", warning)
        else:
            print("\n✅ проблем не найдено")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
