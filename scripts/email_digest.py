#!/usr/bin/env python3
"""Email-дайджест постов контент-фабрики через бесплатный SMTP.

Без зависимостей: smtplib + EmailMessage из stdlib.

    python scripts/email_digest.py                 # dry-run: .eml в data/outbox/email
    python scripts/email_digest.py --send          # отправить через SMTP
    python scripts/email_digest.py --send --days 3 --to a@b.c,d@e.f

Env (бесплатные варианты):
    Gmail SMTP:      EMAIL_SMTP_HOST=smtp.gmail.com  PORT=587
                     EMAIL_SMTP_USER=you@gmail.com  EMAIL_SMTP_PASSWORD=<app password>
    Brevo (300/день): EMAIL_SMTP_HOST=smtp-relay.brevo.com PORT=587
    Mailjet (200/день): EMAIL_SMTP_HOST=in-v3.mailjet.com PORT=587
Общие: EMAIL_FROM, EMAIL_TO (через запятую), EMAIL_SUBJECT_PREFIX.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.storage import Storage  # noqa: E402
from content_factory.utils import strip_html  # noqa: E402

OUT_DIR = ROOT / "data" / "outbox" / "email"


def _env(name: str) -> str:
    return (os.environ.get(name, "") or "").strip()


def _plain(text: str, limit: int = 320) -> str:
    text = strip_html(text or "")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_digest(posts: List[Dict[str, Any]], days: int = 7) -> Dict[str, str]:
    """Собирает HTML и plain-text версии дайджеста из постов storage."""
    by_channel: Dict[str, List[Dict[str, Any]]] = {}
    for post in posts:
        by_channel.setdefault(str(post.get("channel_id") or "?"), []).append(post)

    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    subject = f"Content Factory Digest — {today}"

    html_parts = [
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{subject}</title></head>",
        "<body style='margin:0;padding:0;background:#0b1220;color:#e8f4ff;"
        "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif'>",
        "<div style='max-width:640px;margin:0 auto;padding:24px'>",
        "<div style='font-size:13px;letter-spacing:2px;color:#38e8ff;text-transform:uppercase'>"
        "Content Factory</div>",
        f"<h1 style='font-size:26px;margin:8px 0 4px'>Дайджест за {days} дн.</h1>",
        "<p style='color:#8fb3c9;margin:0 0 20px'>AI · Crypto · Sports — коротко и по делу.</p>",
    ]
    text_parts = [f"Content Factory Digest — {today}", f"Посты за {days} дн.", ""]

    for channel_id, channel_posts in sorted(by_channel.items()):
        html_parts.append(
            f"<h2 style='font-size:15px;color:#38e8ff;text-transform:uppercase;"
            f"letter-spacing:1px;margin:22px 0 8px'>{html.escape(channel_id)}</h2>"
        )
        text_parts.append(f"== {channel_id} ==")
        for post in channel_posts[:6]:
            body = _plain(post.get("text") or "")
            created = str(post.get("created_at") or "")[:16].replace("T", " ")
            meta = str(post.get("format") or "post")
            html_parts.append(
                "<div style='background:#121c2e;border:1px solid #1f3350;border-radius:10px;"
                "padding:12px 14px;margin:8px 0'>"
                f"<div style='font-size:11px;color:#6f8da6'>{html.escape(meta)} · {html.escape(created)}</div>"
                f"<div style='font-size:14px;line-height:1.45;margin-top:4px'>{html.escape(body)}</div></div>"
            )
            text_parts.append(f"- [{meta}] {body}")
        text_parts.append("")

    html_parts.append(
        "<p style='color:#6f8da6;font-size:12px;margin-top:24px'>Вы получили письмо, потому что "
        "подписаны на дайджест Content Factory. Отписаться ответом на письмо.</p>"
        "</div></body></html>"
    )
    text_parts.append("Отписаться — ответом на письмо.")
    return {"subject": subject, "html": "".join(html_parts), "text": "\n".join(text_parts)}


def make_message(digest: Dict[str, str], sender: str, recipients: List[str]) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = _env("EMAIL_SUBJECT_PREFIX") + digest["subject"]
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(digest["text"])
    message.add_alternative(digest["html"], subtype="html")
    return message


def save_eml(message: EmailMessage, suffix: str = "digest") -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = OUT_DIR / f"{suffix}-{stamp}.eml"
    path.write_bytes(message.as_bytes())
    return path


def send_message(message: EmailMessage, host: str, port: int, user: str, password: str,
                 use_tls: bool = True, timeout: int = 30) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP(host, int(port), timeout=timeout) as server:
        if use_tls:
            server.starttls(context=context)
        if user:
            server.login(user, password)
        server.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--to", default="", help="через запятую; по умолчанию EMAIL_TO")
    parser.add_argument("--send", action="store_true", help="реально отправить через SMTP")
    args = parser.parse_args()

    settings = Settings.load()
    with Storage(settings.db_path) as storage:
        posts = storage.get_posts(days=args.days, limit=args.limit)
    posts = [post for post in posts if post.get("status") in {"published", "generated", "ok"}]
    if not posts:
        print("Нет постов для дайджеста — выходим.")
        return 0

    digest = build_digest(posts, days=args.days)
    sender = _env("EMAIL_FROM") or _env("EMAIL_SMTP_USER")
    recipients = [value.strip() for value in (args.to or _env("EMAIL_TO")).split(",") if value.strip()]
    if not sender or not recipients:
        print("Укажите EMAIL_FROM и EMAIL_TO (или --to).")
        return 2
    message = make_message(digest, sender, recipients)

    if not args.send:
        path = save_eml(message)
        print(json.dumps({"dry_run": True, "eml": str(path), "recipients": recipients,
                          "subject": digest["subject"], "posts": len(posts)},
                         ensure_ascii=False, indent=2))
        return 0

    host = _env("EMAIL_SMTP_HOST")
    port = int(_env("EMAIL_SMTP_PORT") or 587)
    user = _env("EMAIL_SMTP_USER")
    password = _env("EMAIL_SMTP_PASSWORD")
    if not host or not user or not password:
        print("SMTP не настроен: EMAIL_SMTP_HOST/EMAIL_SMTP_USER/EMAIL_SMTP_PASSWORD (см. docs/email.md).")
        return 2
    try:
        send_message(message, host, port, user, password)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка отправки: {exc}")
        return 1
    print(json.dumps({"sent": True, "host": host, "recipients": recipients,
                      "subject": digest["subject"], "posts": len(posts)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
