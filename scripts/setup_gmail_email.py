#!/usr/bin/env python3
"""Настройка отправки через Gmail SMTP (App Password) в один шаг.

Что делает:
  1. просит Gmail-адрес и 16-символьный App Password (ввод скрыт);
  2. проверяет SMTP-логин на smtp.gmail.com:587;
  3. отправляет тестовое брендированное письмо на этот же адрес;
  4. при успехе прописывает в content-factory/.env: EMAIL_PROVIDER=gmail, GMAIL_USER,
     GMAIL_APP_PASSWORD, EMAIL_FROM (старый .env сохраняется в .env.bak-<timestamp>).

Как получить App Password (1 минута):
  Google Account → Security → 2-Step Verification (включить) → App passwords →
  создать пароль для «Mail» → скопировать 16 символов.

Запуск:
  content-factory/.venv/bin/python content-factory/scripts/setup_gmail_email.py
  (или с аргументами: --email you@gmail.com --app-password "abcd efgh ijkl mnop" --no-send)
"""
from __future__ import annotations

import argparse
import getpass
import re
import shutil
import smtplib
import ssl
import sys
from datetime import datetime
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
ENV = CF / ".env"
sys.path.insert(0, str(CF / "scripts"))


def normalize(password: str) -> str:
    return re.sub(r"\s+", "", password or "")


def check_login(user: str, password: str) -> None:
    """Логин в Gmail. Gmail иногда рвёт соединение вместо 535 — пробуем AUTH PLAIN явно."""
    last: Exception | None = None
    for attempt in range(2):
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            if attempt == 0:
                server.login(user, password)
            else:
                code, resp = server.docmd("AUTH", "PLAIN " + base64_plain(user, password))
                if code != 235:
                    raise smtplib.SMTPAuthenticationError(code, resp)
            server.quit()
            return
        except smtplib.SMTPAuthenticationError:
            raise
        except Exception as error:  # noqa: BLE001
            last = error
    raise last if last else RuntimeError("не удалось войти")


def base64_plain(user: str, password: str) -> str:
    import base64 as _b64
    return _b64.b64encode(chr(0).join(["", user, password]).encode()).decode()


def send_test(user: str, password: str) -> None:
    import email_providers as providers
    import os
    os.environ["EMAIL_PROVIDER"] = "gmail"
    os.environ["GMAIL_USER"] = user
    os.environ["GMAIL_APP_PASSWORD"] = password
    os.environ["EMAIL_FROM"] = user
    from brand_email import build
    providers.send(user, "Тест: брендированный дайджест Travelata", build("ru", user),
                   "HTML-письмо: откройте в клиенте с поддержкой HTML.")


def write_env(user: str, password: str) -> Path:
    backup = CF / f".env.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(ENV, backup)
    lines = ENV.read_text(encoding="utf-8").splitlines()
    wanted = {
        "EMAIL_PROVIDER": "gmail",
        "GMAIL_USER": user,
        "GMAIL_APP_PASSWORD": password,
        "EMAIL_FROM": user,
    }
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in wanted:
            out.append(f"{key}={wanted[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in wanted.items():
        if key not in seen:
            out.append(f"{key}={value}")
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="")
    parser.add_argument("--app-password", default="")
    parser.add_argument("--no-send", action="store_true", help="не отправлять тестовое письмо")
    args = parser.parse_args()

    user = args.email or input("Gmail-адрес: ").strip()
    if "@" not in user:
        print("нужен полноценный email")
        return 2
    password = normalize(args.app_password or getpass.getpass("App Password (16 символов, ввод скрыт): "))
    if len(password) != 16:
        print(f"App Password должен быть 16 символов, получено {len(password)}. "
              f"Google Account → Security → App passwords → Mail.")
        return 2

    print(f"проверяю SMTP-логин {user} на smtp.gmail.com:587 …")
    try:
        check_login(user, password)
    except smtplib.SMTPAuthenticationError as error:
        print(f"логин не прошёл: {error}. Проверь: 2FA включена, пароль именно App Password "
              f"(16 символов), а не обычный пароль аккаунта.")
        return 3
    except Exception as error:  # noqa: BLE001
        print(f"SMTP-ошибка: {type(error).__name__}: {error}")
        print("Если в тексте нет 535 — Gmail закрыл соединение; попробуй запустить скрипт ещё раз "
              "или проверь, что пароль именно App Password (не обычный).")
        return 3
    print("SMTP-логин OK")

    if not args.no_send:
        try:
            send_test(user, password)
            print(f"тестовое письмо отправлено на {user} — проверь входящие (и «Спам»)")
        except Exception as error:  # noqa: BLE001
            print(f"письмо не ушло: {type(error).__name__}: {error}")
            return 4

    backup = write_env(user, password)
    print(f".env обновлён (бэкап: {backup.name})")
    print("дальше: .venv/bin/python scripts/send_digest.py --check")
    print("       .venv/bin/python scripts/send_digest.py --to you@example.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
