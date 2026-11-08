#!/usr/bin/env python3
"""Diagnose X/Twitter credentials: bearer vs OAuth 1.0a, which split works."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from content_factory.publishers.x import oauth1_header  # noqa: E402

CONSUMER_KEY = os.environ.get("X_API_KEY", "").strip()
CONSUMER_SECRET = os.environ.get("X_API_SECRET", "").strip()
BLOB = os.environ.get("X_ACCOUNT_BLOB", "").strip()


def request(url: str, headers=None, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={"User-Agent": "content-factory-x-check", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")[:500]
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")[:500]
    except Exception as error:  # noqa: BLE001
        return None, "%s: %s" % (type(error).__name__, error)


def main() -> int:
    print("X_API_KEY len:", len(CONSUMER_KEY), "| X_API_SECRET len:", len(CONSUMER_SECRET), "| blob len:", len(BLOB))
    if not BLOB:
        print("no blob"); return 1
    marker = "%3D"
    index = BLOB.find(marker)
    first = BLOB[: index + len(marker)] if index >= 0 else BLOB
    second = BLOB[index + len(marker):] if index >= 0 else ""
    print("split: first len", len(first), "| second len", len(second))

    # 1) app-only bearer search
    for label, token in (("raw", BLOB), ("unquoted", urllib.parse.unquote(BLOB)), ("first-unquoted", urllib.parse.unquote(first))):
        status, body = request(
            "https://api.x.com/2/tweets/search/recent?query=bitcoin&max_results=10",
            {"Authorization": "Bearer " + token},
        )
        print("bearer[%s]: HTTP %s | %s" % (label, status, body[:200]))
        if status == 200:
            break

    # 2) user-context tests with candidate access token/secret pairs
    candidates = [
        ("unquoted-first/second", urllib.parse.unquote(first), second),
        ("raw-first/second", first, second),
        ("blob/empty", BLOB, ""),
        ("unquoted-blob/empty", urllib.parse.unquote(BLOB), ""),
    ]
    for label, access_token, access_secret in candidates:
        url = "https://api.x.com/2/users/me"
        header = oauth1_header("GET", url, CONSUMER_KEY, CONSUMER_SECRET, access_token, access_secret)
        status, body = request(url, {"Authorization": header})
        print("oauth1 users/me[%s]: HTTP %s | %s" % (label, status, body[:220]))
        if status == 200:
            try:
                data = json.loads(body)
                print("  USER:", (data.get("data") or {}).get("username"), "| id:", (data.get("data") or {}).get("id"))
            except ValueError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
