#!/usr/bin/env python3
"""Брендированный дайджест → черновик рассылки в Kit (ConvertKit).

Kit отправляет сам (свои подписчики и статистика), а мы готовим контент письма.

  .venv/bin/python scripts/kit_broadcast.py --dry-run   # собрать HTML и показать размер
  .venv/bin/python scripts/kit_broadcast.py --create    # создать черновик в Kit

После создания: Kit → Broadcasts → открыть черновик → проверить и отправить.
Требуется подтверждённый send address в Kit (Settings → Email), иначе API вернёт 422,
но черновик всё равно создастся.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF / "scripts"))
from brand_email import build  # noqa: E402
from kit_client import Kit, KitError  # noqa: E402

SUBJECT_RU = "Куда поехать в декабре: 12 стран, от 18 473 ₽ за двоих"
SUBJECT_EN = "Where to go in December: 12 countries from 18 473 ₽ per couple"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=["ru", "en"], default="ru")
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cleanup", action="store_true", help="удалить пустые черновики New Broadcast")
    args = parser.parse_args()

    kit = Kit()

    if args.cleanup:
        removed = 0
        try:
            for broadcast in kit.broadcasts():
                if (broadcast.get("subject") or "") in ("", "New Broadcast"):
                    kit.delete_broadcast(broadcast["id"])
                    removed += 1
        except KitError as error:
            print(f"cleanup: {error}")
        print(f"удалено пустых черновиков: {removed}")
        return 0

    html = build(args.lang, "reader@example.com")
    subject = SUBJECT_RU if args.lang == "ru" else SUBJECT_EN
    print(f"письмо: {len(html)//1024} KB, тема: {subject}")

    if not args.create or args.dry_run:
        out = CF / ".local" / "email" / f"kit-{args.lang}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"dry-run: HTML сохранён {out}")
        print("создать черновик: --create")
        return 0

    before = {b.get("id") for b in kit.broadcasts()}
    error_text = ""
    try:
        kit.create_broadcast(subject, html, description="travel digest")
    except KitError as error:
        error_text = str(error)
    after = kit.broadcasts()
    new = [b for b in after if b.get("id") not in before]
    if not new:
        print(f"черновик не создался: {error_text[:300]}")
        return 1
    draft = new[0]
    print(f"черновик создан: id={draft.get('id')} ({draft.get('created_at')})")
    if error_text:
        print(f"предупреждение Kit: {error_text[:200]}")
    print("открыть: https://app.kit.com/broadcasts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
