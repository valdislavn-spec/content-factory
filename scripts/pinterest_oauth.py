#!/usr/bin/env python3
"""Pinterest OAuth2 helper: authorization code flow on localhost.

Requires the app's Client ID + Client secret and the redirect URI
``http://localhost:8085/callback`` registered in the app's Configure page.

Usage:
    python scripts/pinterest_oauth.py --client-id 1636122 --client-secret <secret>
    # opens a browser, waits for the redirect, exchanges the code for a token,
    # prints the access token (masked) and writes .pinterest-token.json.

Token exchange: POST https://api.pinterest.com/v5/oauth/token
    grant_type=authorization_code, code, redirect_uri
    Authorization: Basic base64(client_id:client_secret)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AUTH_URL = "https://www.pinterest.com/oauth/"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
REDIRECT = "http://localhost:8085/callback"
DEFAULT_SCOPES = "boards:read,pins:read,pins:write"


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    body = urllib.parse.urlencode(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
    ).encode()
    basic = base64.b64encode(("%s:%s" % (client_id, client_secret)).encode()).decode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": "Basic " + basic,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True, help="Pinterest App ID (e.g. 1636122)")
    parser.add_argument("--client-secret", required=True, help="Pinterest App secret")
    parser.add_argument("--scopes", default=DEFAULT_SCOPES)
    parser.add_argument("--redirect", default=REDIRECT)
    parser.add_argument("--out", default=".pinterest-token.json")
    args = parser.parse_args(argv)

    auth_url = (
        AUTH_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "client_id": args.client_id,
                "redirect_uri": args.redirect,
                "response_type": "code",
                "scope": args.scopes,
            }
        )
    )
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = (query.get("code") or [""])[0]
            captured["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                ("<h2>Pinterest OAuth</h2><p>%s</p>" % ("Code received, you can close this tab." if code else "No code received.")).encode()
            )

    print("1) Откройте и подтвердите доступ в браузере:")
    print(auth_url)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
    server = HTTPServer(("127.0.0.1", 8085), Handler)
    print("2) Жду redirect на %s ..." % args.redirect)
    server.handle_request()
    server.server_close()
    code = captured.get("code")
    if not code:
        print("FAIL: код авторизации не получен")
        return 1
    try:
        token = exchange_code(args.client_id, args.client_secret, code, args.redirect)
    except urllib.error.HTTPError as error:
        print("FAIL token exchange: HTTP", error.code, error.read()[:300])
        return 1
    access = token.get("access_token", "")
    print("OK: access_token len", len(access), "| refresh_token:", bool(token.get("refresh_token")))
    Path(args.out).write_text(json.dumps(token, indent=2), encoding="utf-8")
    print("saved:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
