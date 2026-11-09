#!/usr/bin/env python3
"""Canva Connect: авторизация и экспорт дизайнов.

    # 1) service app (client credentials)
    python scripts/canva_connect.py service
    # 2) public/private app (OAuth PKCE): получить ссылку, открыть в браузере
    python scripts/canva_connect.py login
    #    затем прислать код:
    python scripts/canva_connect.py login --code "<code>" --verifier "<verifier>"
    # 3) проверка и работа
    python scripts/canva_connect.py check
    python scripts/canva_connect.py designs --limit 10
    python scripts/canva_connect.py export --design-id DAxxxx --format png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import content_factory.integrations.canva as canva  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("service", help="получить токен service app (client credentials)")
    p_login = sub.add_parser("login", help="OAuth PKCE вход")
    p_login.add_argument("--code", default="")
    p_login.add_argument("--verifier", default="")
    p_login.add_argument("--scopes", default="")
    sub.add_parser("check", help="проверить токен (users/me/profile)")
    p_designs = sub.add_parser("designs", help="список дизайнов")
    p_designs.add_argument("--limit", type=int, default=20)
    p_export = sub.add_parser("export", help="экспорт дизайна в png/jpg")
    p_export.add_argument("--design-id", required=True)
    p_export.add_argument("--format", default="png", choices=["png", "jpg", "pdf"])
    p_export.add_argument("--out-dir", default="")
    args = parser.parse_args()
    try:
        if args.command == "service":
            data = canva.client_credentials_token()
            print(json.dumps({"ok": True, "token_type": data.get("token_type"),
                              "expires_in": data.get("expires_in")}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "login":
            if args.code:
                if not args.verifier:
                    print("Нужен --verifier (был напечатан при login).")
                    return 2
                data = canva.exchange_code(args.code, args.verifier)
                print(json.dumps({"ok": True, "expires_in": data.get("expires_in")},
                                 ensure_ascii=False, indent=2))
                return 0
            url, verifier = canva.authorization_url(scopes=args.scopes)
            print("Открой ссылку под нужным Canva-аккаунтом и авторизуй приложение:\n")
            print(url)
            print("\ncode_verifier (сохрани):", verifier)
            print("Затем: python scripts/canva_connect.py login --code <code> --verifier <verifier>")
            return 0
        if args.command == "check":
            data = canva.profile()
            print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
            return 0
        if args.command == "designs":
            data = canva.list_designs(args.limit)
            items = data.get("items") or []
            print(f"дизайнов: {len(items)}")
            for item in items[:20]:
                design = item.get("design") or item
                print(f"- {design.get('id')} | {design.get('title')} | {design.get('url')}")
            return 0
        if args.command == "export":
            result = canva.export_design(args.design_id, args.format, args.out_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except canva.CanvaError as exc:
        print(f"Ошибка Canva: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
