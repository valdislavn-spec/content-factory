#!/usr/bin/env python3
"""Admin helper for the self-hosted link tracker (links-tracker worker, D1).

Env: LINK_TRACKER_BASE, LINK_TRACKER_ADMIN_TOKEN.

    python3 scripts/link_tracker_admin.py --list
    python3 scripts/link_tracker_admin.py --upsert code --target https://... [--label text] [--channel ch]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def base() -> str:
    value = (os.environ.get("LINK_TRACKER_BASE") or "").rstrip("/")
    if not value:
        raise SystemExit("LINK_TRACKER_BASE is not set")
    return value


def admin_token() -> str:
    value = (os.environ.get("LINK_TRACKER_ADMIN_TOKEN") or "").strip()
    if not value:
        raise SystemExit("LINK_TRACKER_ADMIN_TOKEN is not set")
    return value


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base() + path,
        data=data,
        method=method,
        headers={
            "x-token": admin_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Cloudflare WAF (error 1010) blocks non-browser UAs
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:300]}
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode("utf-8", errors="replace")[:300]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--upsert", metavar="CODE")
    parser.add_argument("--target")
    parser.add_argument("--label", default="")
    parser.add_argument("--channel", default="")
    parser.add_argument("--plan", metavar="JSON",
                        help="bulk upsert: JSON array of {code,target,label,channel}")
    args = parser.parse_args(argv)
    if args.list:
        status, payload = call("GET", "/admin/links")
        if status != 200:
            print(f"list failed: {status} {payload}", file=sys.stderr)
            return 1
        links = payload.get("links") or []
        print(f"links: {len(links)}")
        for link in links:
            flag = "on " if link.get("active", 1) else "off"
            print(f"  [{flag}] {link['code']:<24} {link.get('channel') or '-':<14} {link.get('target','')[:110]}")
        return 0
    if args.plan:
        items = json.loads(args.plan)
        ok = True
        for item in items:
            status, payload = call("POST", "/admin/links", {
                "code": item["code"], "target": item["target"],
                "label": item.get("label", ""), "channel": item.get("channel", ""),
            })
            print(f"{item['code']}: {status} {payload}")
            ok = ok and status in (200, 201)
        return 0 if ok else 1
    if not args.upsert or not args.target:
        parser.error("use --list, --upsert CODE --target URL or --plan JSON")
    status, payload = call("POST", "/admin/links", {
        "code": args.upsert,
        "target": args.target,
        "label": args.label,
        "channel": args.channel,
    })
    print(f"upsert {args.upsert}: {status} {payload}")
    return 0 if status in (200, 201) else 1


if __name__ == "__main__":
    raise SystemExit(main())
