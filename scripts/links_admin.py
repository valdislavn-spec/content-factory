#!/usr/bin/env python3
"""Управление трекером коротких ссылок (Cloudflare Worker + KV).

Примеры:
    python scripts/links_admin.py list
    python scripts/links_admin.py stats --json
    python scripts/links_admin.py create --code bingx-crypto-news \
        --target https://bingxdao.com/invite/WYYEGK/ --channel crypto-news --network bingx
    python scripts/links_admin.py seed          # создать/обновить базовый набор
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.integrations.link_tracker import LinkTrackerClient, LinkTrackerError  # noqa: E402
from content_factory.utils import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

SEED = [
    {
        "code": "bingx-crypto-news",
        "target": "https://bingxdao.com/invite/WYYEGK/",
        "channel": "crypto-news",
        "network": "bingx",
        "label": "BingX referral (EN)",
    },
    {
        "code": "bingx-crypto-es",
        "target": "https://bingxdao.com/invite/WYYEGK/",
        "channel": "crypto-es",
        "network": "bingx",
        "label": "BingX referral (ES)",
    },
    {
        "code": "bingx-default",
        "target": "https://bingxdao.com/invite/WYYEGK/",
        "channel": "",
        "network": "bingx",
        "label": "BingX referral (alerts)",
    },
    {
        "code": "mylead-crypto-news",
        "target": "https://mylead.global/r/dJ67Qo",
        "channel": "crypto-news",
        "network": "mylead",
        "label": "MyLead referral",
    },
    {
        "code": "collab-crypto-news",
        "target": "https://collaborator.pro/ru/signup?code=m9Vidx",
        "channel": "crypto-news",
        "network": "collaborator",
        "label": "collaborator.pro signup",
    },
]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tracked short links admin")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    stats = sub.add_parser("stats")
    stats.add_argument("--code", default="")
    stats.add_argument("--json", action="store_true")
    create = sub.add_parser("create")
    create.add_argument("--code", required=True)
    create.add_argument("--target", required=True)
    create.add_argument("--channel", default="")
    create.add_argument("--network", default="")
    create.add_argument("--label", default="")
    sub.add_parser("seed")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    client = LinkTrackerClient()
    try:
        if args.command == "list":
            for link in client.list_links():
                print("{code:28} {channel:14} {network:14} {target}".format(**{**link, "target": link.get("target", "")[:80]}))
            return 0
        if args.command == "stats":
            data = client.stats(getattr(args, "code", ""))
            if getattr(args, "json", False):
                print(json.dumps(data, ensure_ascii=False, indent=1))
                return 0
            for link in data.get("links") or []:
                print(
                    "{code:28} total={total:<5} channel={channel:<14} last={last}".format(
                        code=link.get("code", ""),
                        total=link.get("total", 0),
                        channel=link.get("channel", ""),
                        last=(link.get("last_click") or "—")[:19],
                    )
                )
            return 0
        if args.command == "create":
            record = client.create_link(
                args.code,
                args.target,
                channel=args.channel,
                network=args.network,
                label=args.label,
            )
            print("ok:", json.dumps(record, ensure_ascii=False))
            return 0
        if args.command == "seed":
            for item in SEED:
                record = client.create_link(**item)
                print("seed ok:", record.get("code"), "->", record.get("target"))
            return 0
    except LinkTrackerError as exc:
        print("error:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
