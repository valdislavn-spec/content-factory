#!/usr/bin/env python3
"""Diagnose Pinterest credentials: list boards, verify board id, optionally post a test pin."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
import urllib.error

API = "https://api.pinterest.com/v5"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def call(url: str, token: str, payload=None, timeout: float = 20.0):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "content-factory-pinterest-check",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")[:400]
    except Exception as error:  # noqa: BLE001
        return None, "%s: %s" % (type(error).__name__, error)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", action="store_true", help="create a test pin")
    parser.add_argument("--title", default="Daily crypto news")
    parser.add_argument("--description", default="Bitcoin, Ethereum, markets and regulation — daily on Telegram.")
    parser.add_argument("--link", default="")
    args = parser.parse_args()

    token = env("PINTEREST_ACCESS_TOKEN")
    board = env("PINTEREST_BOARD_ID")
    image = env("PINTEREST_IMAGE_URL")
    print("PINTEREST_ACCESS_TOKEN len:", len(token), "| BOARD_ID:", board or "—", "| IMAGE_URL:", image or "—")
    if not token:
        print("FAIL: PINTEREST_ACCESS_TOKEN не задан — нужен OAuth2-токен со scope pins:write, boards:read")
        return 1

    status, data = call(API + "/boards?page_size=100", token)
    print("GET /boards: HTTP", status)
    boards = data.get("items") if isinstance(data, dict) else []
    for item in (boards or [])[:30]:
        print("  board:", item.get("id"), "|", item.get("name"))
    if board:
        status2, data2 = call(API + "/boards/" + board, token)
        print("GET /boards/{}: HTTP {}".format(board, status2), str(data2)[:160])

    if args.post:
        if not board or not image:
            print("FAIL: для постинга нужны PINTEREST_BOARD_ID и PINTEREST_IMAGE_URL")
            return 1
        payload = {
            "board_id": board,
            "title": args.title[:100],
            "description": args.description[:500],
            "media_source": {"source_type": "image_url", "url": image},
        }
        if args.link:
            payload["link"] = args.link
        status3, data3 = call(API + "/pins", token, payload)
        print("POST /pins: HTTP", status3, str(data3)[:300])
        if status3 not in (200, 201):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
