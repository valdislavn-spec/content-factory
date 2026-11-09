#!/usr/bin/env python3
"""Генерация брендовых шаблонов для всех соцсетей + партнёрские ссылки.

    PYBIN=".venv/bin/python"          # конфиг/план (без PIL)
    RENDER="<DSH python>"             # рендер (PIL + segno)
    PYTHONPATH=/tmp/segno $RENDER scripts/brand_templates.py --list
    PYTHONPATH=/tmp/segno $RENDER scripts/brand_templates.py --all

Сети/размеры/темы/партнёрки — config/brand_templates.yaml.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_factory.brand import templates  # noqa: E402


def cmd_list(config) -> int:
    print(f"{'network':<20} {'layout':<9} {'size':<12} label")
    for network in config["networks"]:
        w, h = network["size"]
        print(f"{network['key']:<20} {network['layout']:<9} {w}x{h:<8} {network.get('label')}")
    print("\nПартнёрки ready:")
    for partner in templates.ready_partners(config):
        print(f"- {partner['key']:<12} {partner['title']:<16} {partner['url']}")
    print("\nТемы:", ", ".join(sorted((config.get("topics") or {}).keys())))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="показать сети/партнёрок/темы")
    parser.add_argument("--all", action="store_true", help="все сети × все ready-партнёрки")
    parser.add_argument("--network", default="", help="ключ сети (см. --list)")
    parser.add_argument("--topic", default="", choices=["ai", "crypto", "sports"], help="тема")
    parser.add_argument("--partner", default="", help="ключ партнёрки (ready)")
    parser.add_argument("--headline", default="")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--cta", default="")
    parser.add_argument("--out", default="", help="каталог вывода (по умолчанию из конфига)")
    parser.add_argument("--json", action="store_true", help="JSON-отчёт")
    args = parser.parse_args()

    config = templates.load_config()
    if args.list or not (args.all or args.network):
        return cmd_list(config)

    try:
        from content_factory.brand import templates as render_mod
        _ = render_mod.render  # проверка импортируемости (PIL тянется лениво при вызове)
    except Exception:  # noqa: BLE001
        pass

    out_dir = Path(args.out) if args.out else ROOT / ((config.get("output") or {}).get("dir") or "assets/brand")
    partners = templates.ready_partners(config)
    if args.all:
        jobs = []
        for index, network in enumerate(config["networks"]):
            topic = args.topic or ["ai", "crypto", "sports"][index % 3]
            for partner in (partners or [{"key": ""}]):
                jobs.append((network["key"], topic, partner["key"]))
    else:
        jobs = [(args.network, args.topic or "ai", args.partner or (partners[0]["key"] if partners else ""))]

    generated, errors = [], []
    for network_key, topic_key, partner_key in jobs:
        try:
            spec = templates.plan(
                config, network_key, topic_key, partner_key,
                args.headline, args.subtitle, args.cta,
            )
            path = templates.render(spec, out_dir)
            generated.append(str(path))
        except Exception as exc:  # noqa: BLE001
            errors.append({"network": network_key, "error": str(exc)})
    payload = {"generated": generated, "errors": errors}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for path in generated:
            print("готово:", path)
        for error in errors:
            print("ошибка:", error["network"], error["error"])
    return 0 if generated else 1


if __name__ == "__main__":
    raise SystemExit(main())
