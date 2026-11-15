#!/usr/bin/env python3
"""Рассылка брендированного дайджеста подписчикам (список — D1 через воркер links-tracker).

Возможности:
  --dry-run            собрать письма в .local/email/outbox/*.eml, ничего не отправлять
  --to you@example.com отправить одно тестовое письмо
  --limit N            ограничить число получателей
  --lang ru|en|all     фильтр по языку подписчика

SMTP берётся из listmonk/.env (LISTMONK_SMTP_PASSWORD) + smtp-relay.brevo.com:587.
Brevo требует, чтобы IP отправителя был авторизован в аккаунте: при ошибке
«Unauthorized IP address» нужно либо добавить IP в Brevo, либо задать BREVO_API_KEY
и использовать HTTP API (тогда раскомментируй отправку через API).
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
WS = CF.parent
sys.path.insert(0, str(CF / "scripts"))
from brand_email import build  # noqa: E402

TRACKER = "https://links-tracker.valdislav-n.workers.dev"
FROM_EMAIL = "valdislav.n@gmail.com"
FROM_NAME = "Незабываемое путешествие · Travelata"
SUBJECT = {
    "ru": "Куда поехать в декабре: 12 стран, от 18 473 ₽ за двоих",
    "en": "Where to go in December: 12 countries from 18 473 ₽ per couple",
}


def env_from(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


def settings() -> dict:
    return {
        "host": env_from(CF.parent / "listmonk" / ".env", "LISTMONK_SMTP_HOST") or "smtp-relay.brevo.com",
        "port": int(env_from(CF.parent / "listmonk" / ".env", "LISTMONK_SMTP_PORT") or 587),
        "user": env_from(CF.parent / "listmonk" / ".env", "LISTMONK_SMTP_USER") or "bff1ba001@smtp-brevo.com",
        "password": env_from(CF.parent / "listmonk" / ".env", "LISTMONK_SMTP_PASSWORD"),
        "admin": env_from(CF / ".env", "LINK_TRACKER_ADMIN_TOKEN"),
    }


def subscribers(cfg: dict) -> list[dict]:
    url = f"{TRACKER}/admin/subscribers?token={cfg['admin']}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data.get("subscribers", [])


def write_eml(email: str, lang: str, outdir: Path) -> Path:
    msg = EmailMessage()
    msg["From"] = formataddr((FROM_NAME, FROM_EMAIL))
    msg["To"] = email
    msg["Subject"] = SUBJECT[lang]
    msg["List-Unsubscribe"] = f"<{TRACKER}/unsubscribe?e={email}>"
    msg.set_content("HTML-письмо: откройте в почтовом клиенте с поддержкой HTML.")
    msg.add_alternative(build(lang, email), subtype="html")
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"digest-{lang}-{email.replace('@', '_at_')}.eml"
    path.write_bytes(html_to_eml_bytes(msg))
    return path


def html_to_eml_bytes(msg: EmailMessage) -> bytes:
    return msg.as_bytes()


def send_one(cfg: dict, email: str, lang: str) -> str:
    msg = EmailMessage()
    msg["From"] = formataddr((FROM_NAME, FROM_EMAIL))
    msg["To"] = email
    msg["Subject"] = SUBJECT[lang]
    msg["List-Unsubscribe"] = f"<{TRACKER}/unsubscribe?e={email}>"
    msg.set_content("HTML-письмо: откройте в почтовом клиенте с поддержкой HTML.")
    msg.add_alternative(build(lang, email), subtype="html")
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(cfg["user"], cfg["password"])
        server.send_message(msg)
    return "sent"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--lang", choices=["ru", "en", "all"], default="all")
    args = parser.parse_args()

    cfg = settings()
    outdir = WS / ".local" / "email" / "outbox"

    if not cfg["password"]:
        print("нет LISTMONK_SMTP_PASSWORD в listmonk/.env")
        return 2

    if args.to:
        if args.dry_run:
            print(f"dry-run: {write_eml(args.to, 'ru', outdir)}")
        else:
            try:
                print(f"test -> {args.to}: {send_one(cfg, args.to, 'ru')}")
            except smtplib.SMTPAuthenticationError as error:
                print(f"SMTP auth failed: {error}. Brevo требует авторизованный IP "
                      f"(добавь IP в Brevo → SMTP & API → Authorized IPs) или BREVO_API_KEY.")
                return 3
            except Exception as error:  # noqa: BLE001
                print(f"send error: {type(error).__name__}: {error}")
                return 3
        return 0

    people = subscribers(cfg)
    if args.lang != "all":
        people = [p for p in people if p.get("lang") == args.lang]
    if args.limit:
        people = people[: args.limit]
    print(f"подписчиков: {len(people)}")

    sent = failed = 0
    for person in people:
        email = person["email"]
        lang = person.get("lang") if person.get("lang") in ("ru", "en") else "ru"
        if args.dry_run:
            write_eml(email, lang, outdir)
            sent += 1
            continue
        try:
            send_one(cfg, email, lang)
            sent += 1
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"  {email}: {type(error).__name__}: {str(error)[:120]}")
    mode = "dry-run" if args.dry_run else "send"
    print(f"{mode}: ok={sent}, failed={failed}, outbox={outdir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
