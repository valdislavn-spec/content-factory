#!/usr/bin/env python3
"""Провайдеры отправки email: один интерфейс, разные бэкенды.

Выбор: переменная окружения EMAIL_PROVIDER (smtp | resend | mailersend | sendgrid |
mailgun | postmark | unisender) или аргумент --provider в send_digest.py.

Ключи берутся из content-factory/.env:
  EMAIL_FROM=...                (адрес отправителя; домен должен быть подтверждён у провайдера)
  RESEND_API_KEY=re_...
  MAILERSEND_API_KEY=mlsn....
  SENDGRID_API_KEY=SG....
  MAILGUN_API_KEY=... MAILGUN_DOMAIN=mg.example.com
  POSTMARK_TOKEN=...
  UNISENDER_API_KEY=...
SMTP (EMAIL_PROVIDER=smtp, дефолт):
  EMAIL_SMTP_HOST / EMAIL_SMTP_PORT / EMAIL_SMTP_USER / EMAIL_SMTP_PASSWORD
  (если не заданы — берутся LISTMONK_SMTP_* из listmonk/.env)
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
WS = CF.parent

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def env_file(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def env(key: str, default: str = "") -> str:
    import os

    if os.environ.get(key):
        return os.environ[key]
    value = env_file(CF / ".env", key)
    if value:
        return value
    return default


def from_address() -> tuple[str, str]:
    raw = env("EMAIL_FROM", "valdislav.n@gmail.com")
    name = env("EMAIL_FROM_NAME", "Незабываемое путешествие · Travelata")
    return name, raw


def reply_to() -> str:
    """Reply-To (не требует верификации у провайдера). Пусто = как From."""
    return env("EMAIL_REPLY_TO", "")


def reply_to_name() -> str:
    return env("EMAIL_REPLY_TO_NAME", env("EMAIL_FROM_NAME", "Незабываемое путешествие · Travelata"))


def provider_name() -> str:
    return env("EMAIL_PROVIDER", "smtp").strip().lower()


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 30) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode() or "{}"
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"raw": body[:300]}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:300]
        raise RuntimeError(f"{error.code}: {detail}") from error


def send(to: str, subject: str, html: str, text: str = "") -> str:
    """Отправляет письмо через выбранного провайдера. Возвращает id/описание."""
    provider = provider_name()
    name, address = from_address()
    sender = formataddr((name, address))
    text = text or "HTML-письмо: откройте в клиенте с поддержкой HTML."

    if provider in ("smtp", "gmail"):
        return _send_smtp(sender, to, subject, html, text)
    if provider == "resend":
        key = env("RESEND_API_KEY")
        if not key:
            raise RuntimeError("RESEND_API_KEY не задан")
        out = _post_json("https://api.resend.com/emails",
                         {"from": sender, "to": [to], "subject": subject, "html": html, "text": text,
                          **({"reply_to": reply_to()} if reply_to() else {})},
                         {"Authorization": f"Bearer {key}"})
        return str(out.get("id", out))
    if provider == "mailersend":
        key = env("MAILERSEND_API_KEY")
        if not key:
            raise RuntimeError("MAILERSEND_API_KEY не задан")
        out = _post_json("https://api.mailersend.com/v1/email",
                         {"from": {"email": address, "name": name}, "to": [{"email": to}],
                          "subject": subject, "html": html, "text": text,
                          **({"reply_to": {"email": reply_to()}} if reply_to() else {})},
                         {"Authorization": f"Bearer {key}"})
        return str(out.get("id", out))
    if provider == "sendgrid":
        key = env("SENDGRID_API_KEY")
        if not key:
            raise RuntimeError("SENDGRID_API_KEY не задан")
        out = _post_json("https://api.sendgrid.com/v3/mail/send",
                         {"personalizations": [{"to": [{"email": to}]}],
                          "from": {"email": address, "name": name},
                          "reply_to": {"email": reply_to() or address},
                          "subject": subject,
                          "content": [{"type": "text/plain", "value": text},
                                      {"type": "text/html", "value": html}]},
                         {"Authorization": f"Bearer {key}"})
        return str(out.get("raw", "202 accepted"))
    if provider == "mailgun":
        key, domain = env("MAILGUN_API_KEY"), env("MAILGUN_DOMAIN")
        if not key or not domain:
            raise RuntimeError("нужны MAILGUN_API_KEY и MAILGUN_DOMAIN")
        import base64
        auth = base64.b64encode(f"api:{key}".encode()).decode()
        out = _post_json(f"https://api.mailgun.net/v3/{domain}/messages",
                         {"from": sender, "to": to, "subject": subject, "html": html, "text": text,
                          **({"h:Reply-To": reply_to()} if reply_to() else {})},
                         {"Authorization": f"Basic {auth}"})
        return str(out.get("id", out))
    if provider == "postmark":
        token = env("POSTMARK_TOKEN")
        if not token:
            raise RuntimeError("POSTMARK_TOKEN не задан")
        out = _post_json("https://api.postmarkapp.com/email",
                         {"From": sender, "To": to, "Subject": subject,
                          "ReplyTo": reply_to() or address,
                          "HtmlBody": html, "TextBody": text, "MessageStream": "broadcast"},
                         {"X-Postmark-Server-Token": token})
        return str(out.get("MessageID", out))
    if provider == "unisender":
        key = env("UNISENDER_API_KEY")
        if not key:
            raise RuntimeError("UNISENDER_API_KEY не задан")
        out = _post_json("https://go1.unisender.ru/ru/transactional/api/v1/email/send.json",
                         {"message": {"recipients": [{"email": to}],
                                      "body": {"html": html},
                                      "subject": subject,
                                      "from_email": address, "from_name": name,
                                      **({"reply_to": reply_to()} if reply_to() else {})}},
                         {"X-API-KEY": key})
        return str(out.get("job_id", out))
    raise RuntimeError(f"неизвестный EMAIL_PROVIDER={provider}")


def _send_smtp(sender: str, to: str, subject: str, html: str, text: str) -> str:
    if provider_name() == "gmail":
        host = env("EMAIL_SMTP_HOST", "smtp.gmail.com")
        port = int(env("EMAIL_SMTP_PORT", "587"))
        user = env("GMAIL_USER", env_file(CF / ".env", "EMAIL_FROM") or "")
        password = env("GMAIL_APP_PASSWORD", env("EMAIL_SMTP_PASSWORD", "")).replace(" ", "")
    else:
        host = env("EMAIL_SMTP_HOST", env_file(WS / "listmonk" / ".env", "LISTMONK_SMTP_HOST") or "smtp-relay.brevo.com")
        port = int(env("EMAIL_SMTP_PORT", env_file(WS / "listmonk" / ".env", "LISTMONK_SMTP_PORT") or "587"))
        user = env("EMAIL_SMTP_USER", env_file(WS / "listmonk" / ".env", "LISTMONK_SMTP_USER") or "")
        password = env("EMAIL_SMTP_PASSWORD", env_file(WS / "listmonk" / ".env", "LISTMONK_SMTP_PASSWORD") or "")
    if not user or not password:
        raise RuntimeError("нет SMTP-креденшелов (EMAIL_SMTP_* или LISTMONK_SMTP_*)")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    if reply_to():
        message["Reply-To"] = formataddr((reply_to_name(), reply_to()))
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(user, password)
        server.send_message(message)
    return f"smtp:{host}:{to}"


def report() -> str:
    """Что настроено — для --check."""
    provider = provider_name()
    _, address = from_address()
    keys = {
        "resend": "RESEND_API_KEY", "mailersend": "MAILERSEND_API_KEY",
        "sendgrid": "SENDGRID_API_KEY", "mailgun": "MAILGUN_API_KEY",
        "postmark": "POSTMARK_TOKEN", "unisender": "UNISENDER_API_KEY",
    }
    lines = [f"провайдер: {provider}", f"отправитель: {address}",
             f"reply-to: {reply_to() or '(как From)'}"]
    if provider in ("smtp", "gmail"):
        if provider == "gmail":
            lines.append(f"SMTP: {env('EMAIL_SMTP_HOST', 'smtp.gmail.com')}:{env('EMAIL_SMTP_PORT', '587')} (STARTTLS)")
            lines.append(f"GMAIL_USER: {env('GMAIL_USER') or '—'}")
            lines.append(f"GMAIL_APP_PASSWORD: {'задан' if env('GMAIL_APP_PASSWORD') else 'НЕ задан (создай в Google → Security → App passwords)'}")
        else:
            lines.append(f"SMTP: {env('EMAIL_SMTP_HOST', 'smtp-relay.brevo.com')}:{env('EMAIL_SMTP_PORT', '587')}")
            lines.append(f"есть SMTP-пароль: {'да' if env('EMAIL_SMTP_PASSWORD') or env_file(WS / 'listmonk' / '.env', 'LISTMONK_SMTP_PASSWORD') else 'нет'}")
    else:
        key_name = keys.get(provider, "")
        lines.append(f"{key_name}: {'задан' if env(key_name) else 'НЕ задан'}")
    return "\n".join(lines)
