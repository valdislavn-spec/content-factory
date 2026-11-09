#!/usr/bin/env python3
"""Собрать еженедельный email-дайджест и (опционально) отправить через Brevo.

    # безопасный прогон: HTML/text/JSON в exports/email-digest, ничего не шлём
    ./.venv/bin/python scripts/email_digest.py --language all

    # реальная отправка (нужны BREVO_API_KEY, BREVO_LIST_ID_EN/ES, EMAIL_FROM)
    ./.venv/bin/python scripts/email_digest.py --language en --send

Данные: SQLite завода (telegram_posts / posts), fallback — публичное t.me/s.
Без ``--send`` письма только сохраняются в файлы.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.integrations.email_digest import (  # noqa: E402
    collect_items,
    render,
    send_brevo_campaign,
)
from content_factory.models import utcnow  # noqa: E402
from content_factory.storage import Storage  # noqa: E402

LANGUAGES = {"en": "en", "es": "es"}
LIST_ENV = {"en": "BREVO_LIST_ID_EN", "es": "BREVO_LIST_ID_ES"}


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Еженедельный email-дайджест каналов")
    parser.add_argument("--language", choices=["en", "es", "all"], default="all")
    parser.add_argument("--days", type=float, default=7.0, help="Окно постов, дней")
    parser.add_argument("--per-channel", type=int, default=2, help="Сколько постов на канал")
    parser.add_argument("--limit", type=int, default=6, help="Сколько новостей в письме")
    parser.add_argument("--out", default="exports/email-digest", help="Каталог для HTML/text")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Отправить кампанию через Brevo (по умолчанию только сохранить файлы)",
    )
    parser.add_argument("--db", default="", help="Путь к SQLite (по умолчанию data/factory.sqlite3)")
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Не ходить в t.me/s, если в БД нет постов (для офлайн-проверок)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    db_path = Path(args.db) if args.db else settings.db_path
    if not db_path.is_absolute():
        db_path = settings.root / db_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = settings.root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    languages = [args.language] if args.language in LANGUAGES else list(LANGUAGES)
    storage = Storage(db_path)
    result: dict = {"generated": [], "sent": [], "errors": []}
    try:
        for language in languages:
            try:
                items = collect_items(
                    settings,
                    storage,
                    language,
                    days=args.days,
                    per_channel=args.per_channel,
                    max_items=args.limit,
                    allow_preview=not args.no_preview,
                )
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(f"{language}: collect: {exc}")
                continue
            digest = render(items, settings, language, now=utcnow())
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            html_path = out_dir / f"{language}-{stamp}.html"
            text_path = out_dir / f"{language}-{stamp}.txt"
            json_path = out_dir / f"{language}-{stamp}.json"
            html_path.write_text(digest.html, encoding="utf-8")
            text_path.write_text(digest.text, encoding="utf-8")
            json_path.write_text(
                json.dumps(
                    {
                        "language": language,
                        "subject": digest.subject,
                        "period": [digest.period_start, digest.period_end],
                        "items": [item.__dict__ for item in digest.items],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            result["generated"].append(
                {"language": language, "items": len(digest.items), "html": str(html_path)}
            )
            print(
                f"[{language}] новостей {len(digest.items)}; тема: {digest.subject}; "
                f"файл: {html_path}"
            )
            if not args.send:
                continue
            api_key = os.getenv("BREVO_API_KEY", "").strip()
            list_id_raw = os.getenv(LIST_ENV[language], "").strip()
            sender_email = os.getenv("EMAIL_FROM", "").strip()
            sender_name = os.getenv("EMAIL_FROM_NAME", "Content Factory").strip()
            missing = [
                name
                for name, value in (
                    ("BREVO_API_KEY", api_key),
                    (LIST_ENV[language], list_id_raw),
                    ("EMAIL_FROM", sender_email),
                )
                if not value
            ]
            if missing:
                result["errors"].append(f"{language}: не заданы {', '.join(missing)}")
                continue
            try:
                sent = send_brevo_campaign(
                    digest,
                    api_key=api_key,
                    sender_email=sender_email,
                    sender_name=sender_name,
                    list_id=int(list_id_raw),
                )
                result["sent"].append({"language": language, **sent})
                print(f"[{language}] кампания Brevo #{sent.get('id')} отправлена")
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(f"{language}: send: {exc}")
                print(f"[{language}] ошибка отправки: {exc}", file=sys.stderr)
    finally:
        storage.close()

    summary = out_dir / "summary.json"
    summary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Итог: {summary}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
