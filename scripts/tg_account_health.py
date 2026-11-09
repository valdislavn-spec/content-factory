#!/usr/bin/env python3
"""Здоровье Telegram-аккаунта: @SpamBot, активные сессии, 2FA, админ-каналы, скор.

Два режима:
    bot  — только Bot API (без входа в аккаунт): права бота, частота постов, affiliate;
    user — официальный Telethon с НАШЕЙ сессией (TG_SESSION_STRING или .session):
           @SpamBot /start, account.GetAuthorizations, 2FA, администрируемые каналы.
           Только чтение + один /start для @SpamBot. Без массовых действий.

Запуск:
    ./.venv/bin/python scripts/tg_account_health.py                 # auto: bot + user если есть сессия
    ./.venv/bin/python scripts/tg_account_health.py --mode bot
    ./.venv/bin/python scripts/tg_account_health.py --mode user --json
    ./.venv/bin/python scripts/tg_account_health.py --mode user --socks 127.0.0.1:1080

Секреты не печатаются; IP сессий маскируются; телефон маскируется.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.tg_health import (  # noqa: E402
    TgHealthError,
    extract_retry_after,
    looks_like_session_string,
    mask_ip,
    normalize_ref,
    parse_spambot_reply,
    score_account,
    sessions_report,
)
from content_factory.utils import load_dotenv  # noqa: E402


def _bot_mode(proxy: str) -> Dict[str, Any]:
    try:
        from scripts.tg_safety_check import run as run_bot_check

        return run_bot_check(proxy=proxy or "http://127.0.0.1:1081")
    except Exception as exc:  # noqa: BLE001
        return {"error": f"bot-режим недоступен: {exc}"}


def _session_source(env: Dict[str, str]) -> Dict[str, Any]:
    string = (env.get("TG_SESSION_STRING") or "").strip()
    raw = (env.get("TG_SESSION") or "").strip() or "content_factory"
    if string and looks_like_session_string(string):
        return {"type": "string", "value": string}
    if looks_like_session_string(raw):
        return {"type": "string", "value": raw}
    candidates = [Path(raw)]
    if not Path(raw).is_absolute():
        candidates = [ROOT / "data" / f"{raw}.session", ROOT / f"{raw}.session", Path(raw)]
    for path in candidates:
        if path.is_file():
            return {"type": "file", "value": str(path)}
    raise TgHealthError(
        "нет Telethon-сессии: задайте TG_SESSION_STRING (StringSession) или "
        "положите файл data/content_factory.session. Сессию можно создать "
        "workflow .github/workflows/tg-session.yml на GitHub Actions (там Telegram доступен)."
    )


def _socks_proxy(value: str):
    """socks5://host:port → кортеж для Telethon (нужен PySocks)."""
    if not value:
        return None
    try:
        import socks  # type: ignore
    except ImportError as exc:
        raise TgHealthError(
            "для --socks нужен PySocks: pip install pysocks (или запускайте на VPS/Actions, "
            "где Telegram доступен напрямую)"
        ) from exc
    text = value.replace("socks5h://", "").replace("socks5://", "")
    host, _, port = text.rpartition(":")
    if not host or not port.isdigit():
        raise TgHealthError(f"некорректный --socks: {value}")
    proxy_type = getattr(socks, "SOCKS5", 2)
    return (proxy_type, host, int(port), True, None, None)


def _user_mode(env: Dict[str, str], socks: str = "") -> Dict[str, Any]:
    try:
        from telethon import functions
        from telethon.sessions import StringSession
        from telethon.sync import TelegramClient
    except ImportError as exc:
        raise TgHealthError(
            "user-режим требует Telethon: pip install -r requirements-optional.txt"
        ) from exc
    api_id = env.get("TG_API_ID", "").strip()
    api_hash = env.get("TG_API_HASH", "").strip()
    if not api_id.isdigit() or not api_hash:
        raise TgHealthError("нужны TG_API_ID и TG_API_HASH (my.telegram.org)")
    source = _session_source(env)
    proxy = _socks_proxy(socks) if socks else None
    session = StringSession(source["value"]) if source["type"] == "string" else source["value"]

    client = TelegramClient(session, int(api_id), api_hash, proxy=proxy, timeout=20)
    report: Dict[str, Any] = {"mode": "user"}
    try:
        client.connect()
        if not client.is_user_authorized():
            raise TgHealthError("сессия не авторизована — нужна повторная авторизация в Actions/VPS")
        me = client.get_me()
        report["account"] = {
            "id": me.id,
            "username": me.username,
            "premium": bool(getattr(me, "premium", False)),
            "phone": (str(me.phone)[:2] + "…" + str(me.phone)[-2:]) if me.phone else "—",
        }
        auths = client(functions.account.GetAuthorizationsRequest())
        report["sessions"] = sessions_report(
            [
                {
                    "current": getattr(item, "current", False),
                    "date_active": getattr(item, "date_active", None),
                    "date_created": getattr(item, "date_created", None),
                    "app_name": getattr(item, "app_name", ""),
                    "device_model": getattr(item, "device_model", ""),
                    "platform": getattr(item, "platform", ""),
                    "country": getattr(item, "country", ""),
                    "ip": getattr(item, "ip", ""),
                }
                for item in auths.authorizations
            ]
        )
        password = client(functions.account.GetPasswordRequest())
        twofa = getattr(password, "has_password", None)
        if twofa is None:
            twofa = getattr(password, "current_password_set", None)
        report["twofa"] = twofa
        admined = client(functions.channels.GetAdminedPublicChannelsRequest())
        report["admin_channels"] = len(getattr(admined, "chats", []) or [])
        spambot_text = ""
        try:
            spambot = client.get_entity(normalize_ref("@SpamBot"))
            client.send_message(spambot, "/start")
            time.sleep(4)
            messages = client.get_messages(spambot, limit=1)
            if messages:
                spambot_text = str(getattr(messages[0], "message", "") or "")
        except Exception as exc:  # noqa: BLE001 - не должен ломать отчёт
            report["spambot_error"] = str(exc)[:200]
        report["spambot"] = parse_spambot_reply(spambot_text)
        report["spambot"]["text_preview"] = spambot_text[:500]
        report["score"] = score_account(
            spambot_status=report["spambot"]["status"],
            sessions=report["sessions"],
            twofa=twofa if isinstance(twofa, bool) else None,
            bot_ok=True,
        )
    finally:
        try:
            client.disconnect()
        except Exception:  # pragma: no cover
            pass
    return report


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = ["# Telegram: здоровье аккаунта", ""]
    bot = report.get("bot") or {}
    if bot:
        lines.append(f"## Бот\n@: {bot.get('bot', {}).get('username')} · ok: {(bot.get('bot') or {}).get('ok')}")
        posting = bot.get("posting") or {}
        lines.append(f"Публикации: за час {posting.get('last_hour')}, за сутки {posting.get('last_day')}")
        for warning in bot.get("warnings") or []:
            lines.append(f"- ⚠️ {warning}")
        lines.append("")
    user = report.get("user") or {}
    if user:
        if user.get("error"):
            lines += [f"## Аккаунт\n⚠️ {user['error']}", ""]
        else:
            account = user.get("account") or {}
            lines.append("## Аккаунт")
            lines.append(f"- @{account.get('username') or '—'} · premium: {account.get('premium')} · телефон: {account.get('phone')}")
            spambot = user.get("spambot") or {}
            lines.append(f"- @SpamBot: **{spambot.get('status')}** — {spambot.get('details', '')}")
            twofa = user.get("twofa")
            lines.append(f"- 2FA: {'да' if twofa else 'нет' if twofa is False else 'неизвестно'}")
            sessions = user.get("sessions") or {}
            lines.append(
                f"- Сессии: всего {sessions.get('total')}, текущая {sessions.get('current')}, "
                f"сторонних {sessions.get('other')}, подозрительных {sessions.get('suspicious')}"
            )
            for item in sessions.get("sessions") or []:
                mark = "✅" if item.get("current") else "•"
                lines.append(
                    f"  {mark} {item.get('app')} / {item.get('device')} / {item.get('country')} "
                    f"/ ip {item.get('ip')} / {item.get('days_ago')} дн. назад"
                )
            lines.append(f"- Админ-каналов: {user.get('admin_channels')}")
            score = user.get("score") or {}
            lines.append(f"\n**Скор: {score.get('score')}/100 ({score.get('grade')})**")
            for reason in score.get("reasons") or []:
                lines.append(f"- {reason}")
            lines.append("")
    lines.append("> Только чтение и официальный @SpamBot; без массовых действий. "
                 "IP замаскированы, телефон скрыт.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Здоровье Telegram-аккаунта")
    parser.add_argument("--mode", choices=["auto", "bot", "user"], default="auto")
    parser.add_argument("--proxy", default=os.environ.get("TG_PROXY", "http://127.0.0.1:1081"),
                        help="HTTP-прокси для Bot API (bot-режим)")
    parser.add_argument("--socks", default=os.environ.get("TG_SOCKS", ""),
                        help="SOCKS5 для Telethon (user-режим), например 127.0.0.1:1080")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    env = dict(os.environ)
    report: Dict[str, Any] = {}
    if args.mode in ("auto", "bot"):
        report["bot"] = _bot_mode(args.proxy)
    if args.mode in ("auto", "user"):
        if args.mode == "user" or _user_available(env):
            try:
                report["user"] = _user_mode(env, socks=args.socks)
            except TgHealthError as exc:
                report["user"] = {"error": str(exc)}
        else:
            report["user"] = {
                "error": "сессия не найдена: user-режим пропущен (нужен TG_SESSION_STRING или .session)"
            }
    report["ok"] = bool(report.get("bot", {}).get("bot", {}).get("ok")) and not (
        report.get("user", {}).get("spambot", {}).get("status") == "limited"
    )
    text = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
    if args.out:
        path = Path(args.out)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Сохранено: {path}")
    else:
        print(text)
    return 0 if report.get("ok") else 1


def _user_available(env: Dict[str, str]) -> bool:
    try:
        _session_source(env)
        return True
    except TgHealthError:
        return False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
