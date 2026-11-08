#!/usr/bin/env python3
"""Сгенерировать ссылки на добровольную поддержку с UTM по каналам.

Показывает, какие ссылки уйдут в посты (utm_content = id канала), и сохраняет
их в data/support_links.json для оператора/аналитики.

    python scripts/support_links.py
    python scripts/support_links.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_network_channels  # noqa: E402
from content_factory.support import load_support_config, support_link  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="UTM-ссылки добровольной поддержки")
    parser.add_argument("--json", action="store_true", help="печать JSON")
    parser.add_argument("--no-save", action="store_true", help="не писать data/support_links.json")
    args = parser.parse_args(argv)

    settings = Settings.load()
    config = load_support_config(settings)
    channels = load_network_channels(settings)
    links = {
        channel.id: support_link(channel, settings, config=config)
        for channel in channels
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "enabled": bool(config.get("enabled")),
        "url_configured": bool(str(config.get("url") or "").strip()),
        "links": links,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not payload["url_configured"]:
            print("Добровольная поддержка включена, но url не задан.")
            print("Вставь donate-ссылку в config/support.yaml (или SUPPORT_URL).")
            return 0
        print("Ссылки на добровольную поддержку (UTM по каналам):")
        for channel_id, link in links.items():
            print("  {:16s} {}".format(channel_id, link or "—"))
    if not args.no_save:
        path = Path(settings.data_dir) / "support_links.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.json:
            print("Сохранено: {}".format(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
