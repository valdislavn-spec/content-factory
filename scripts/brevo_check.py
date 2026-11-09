#!/usr/bin/env python3
"""Check Brevo API access from the current runner: account, senders, lists.

Used by .github/workflows/brevo-check.yml after setting BREVO_API_KEY.
Prints no secrets. Exit 0 only if /v3/account returns 200.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.brevo.com/v3"


def call(path: str):
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if not key:
        raise SystemExit("BREVO_API_KEY не задан")
    req = urllib.request.Request(
        API + path,
        headers={"api-key": key, "Accept": "application/json", "User-Agent": "content-factory-brevo-check"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def main() -> int:
    st, account = call("/account")
    print("GET /account:", st)
    if st != 200:
        print(" ", str(account)[:400])
        if "unrecognised IP" in str(account) or "IP address" in str(account):
            print("Причина: Brevo блокирует IP раннера. Нужно отключить IP blocking для API в Brevo.")
        return 1
    if isinstance(account, dict):
        print("  email:", account.get("email"), "| company:", account.get("companyName"))
        print("  plan:", account.get("plan"))
    st, senders = call("/senders")
    print("GET /senders:", st)
    if st == 200 and isinstance(senders, dict):
        print("  senders:", [(s.get("id"), s.get("email"), s.get("active")) for s in senders.get("senders", [])])
    st, lists = call("/contacts/lists?limit=20")
    print("GET /contacts/lists:", st)
    if st == 200 and isinstance(lists, dict):
        print("  lists:", [(l.get("id"), l.get("name"), l.get("totalSubscribers")) for l in lists.get("lists", [])])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
