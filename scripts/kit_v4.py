#!/usr/bin/env python3
"""Клиент Kit API v4 (https://api.kit.com/v4) — заголовок X-Kit-Api-Key.

Ключ: KIT_V4_API_KEY в content-factory/.env (Settings → Developer → API Keys).

  .venv/bin/python scripts/kit_v4.py --check
  .venv/bin/python scripts/kit_v4.py --upsert valdislav.n@gmail.com --fields '{"язык":"ru"}'
  .venv/bin/python scripts/kit_v4.py --webhook-create --url https://links-tracker.valdislav-n.workers.dev/kit/webhook
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
BASE = "https://api.kit.com/v4"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def env(key: str) -> str:
    import os

    if os.environ.get(key):
        return os.environ[key]
    path = CF / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class KitV4:
    def __init__(self) -> None:
        self.key = env("KIT_V4_API_KEY")
        if not self.key:
            raise RuntimeError("KIT_V4_API_KEY не задан в .env")

    def _request(self, method: str, path: str, payload: dict | None = None,
                 params: dict | None = None) -> dict:
        query = urllib.parse.urlencode(params or {})
        url = f"{BASE}{path}" + (f"?{query}" if query else "")
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("X-Kit-Api-Key", self.key)
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", UA)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode()[:400]
            raise RuntimeError(f"HTTP {error.code}: {detail}") from error

    def get(self, path: str, **params) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: dict) -> dict:
        return self._request("POST", path, payload=payload)

    def put(self, path: str, payload: dict) -> dict:
        return self._request("PUT", path, payload=payload)

    def delete(self, path: str) -> dict:
        return self._request("DELETE", path)

    # --- высокоуровневые операции ---
    def account(self) -> dict:
        return self.get("/account")

    def subscribers(self, **params) -> list:
        return self.get("/subscribers", **params).get("subscribers", [])

    def upsert_subscriber(self, email: str, fields: dict | None = None,
                          first_name: str = "", state: str = "active") -> dict:
        payload = {"email_address": email, "state": state}
        if first_name:
            payload["first_name"] = first_name
        if fields:
            payload["fields"] = fields
        return self.post("/subscribers", payload)

    def tags(self) -> list:
        return self.get("/tags").get("tags", [])

    def forms(self) -> list:
        return self.get("/forms").get("forms", [])

    def broadcast(self, broadcast_id: int | str) -> dict:
        return self.get(f"/broadcasts/{broadcast_id}").get("broadcast", {})

    def create_broadcast(self, subject: str, content: str, description: str,
                         send_at: str | None = None, public: bool = False,
                         preview_text: str = "", subscriber_filter: list | None = None,
                         email_template_id: int | None = None) -> dict:
        payload = {"subject": subject, "content": content, "description": description,
                   "public": public, "preview_text": preview_text,
                   "published_at": send_at, "send_at": send_at}
        if subscriber_filter:
            payload["subscriber_filter"] = subscriber_filter
        if email_template_id:
            payload["email_template_id"] = email_template_id
        return self.post("/broadcasts", payload)

    def webhook_endpoints(self) -> list:
        return self.get("/webhook_endpoints").get("webhook_endpoints", [])

    def create_webhook_endpoint(self, url: str, events: list[str], name: str = "",
                                description: str = "") -> dict:
        return self.post("/webhook_endpoints", {"url": url, "events": events,
                                                "name": name or "D1 sync",
                                                "description": description})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--upsert", default="")
    parser.add_argument("--fields", default="{}")
    parser.add_argument("--webhook-create", action="store_true")
    parser.add_argument("--url", default="https://links-tracker.valdislav-n.workers.dev/kit/webhook")
    args = parser.parse_args()

    kit = KitV4()
    if args.check or not (args.upsert or args.webhook_create):
        account = kit.account()
        print("account:", json.dumps(account.get("account", {}), ensure_ascii=False)[:200])
        print("subscribers:", len(kit.subscribers()))
        print("tags:", [(t["id"], t["name"]) for t in kit.tags()])
        print("forms:", [(f["id"], f["name"], f["type"]) for f in kit.forms()])
        print("webhook_endpoints:", [(w["id"], w["url"], w.get("status")) for w in kit.webhook_endpoints()])
        return 0

    if args.upsert:
        print(kit.upsert_subscriber(args.upsert, json.loads(args.fields)))
        return 0

    if args.webhook_create:
        events = ["subscriber.created", "subscriber.activated", "subscriber.unsubscribed",
                  "subscriber.subscribed_to_form", "subscriber.bounced", "subscriber.complained",
                  "subscriber.tag_added", "broadcast.sent"]
        out = kit.create_webhook_endpoint(args.url, events)
        endpoint = out.get("webhook_endpoint", {})
        secret = out.get("secret") or endpoint.get("secret") or ""
        print("webhook id:", endpoint.get("id"), "| url:", endpoint.get("url"))
        print("secret:", secret[:8] + "…" if secret else "НЕ ВЕРНУЛСЯ")
        if secret:
            cf_env = CF / ".env"
            text = cf_env.read_text(encoding="utf-8")
            if "KIT_WEBHOOK_SECRET=" in text:
                import re
                text = re.sub(r"(?m)^KIT_WEBHOOK_SECRET=.*$", f"KIT_WEBHOOK_SECRET={secret}", text)
            else:
                text += f"\nKIT_WEBHOOK_SECRET={secret}\n"
            cf_env.write_text(text, encoding="utf-8")
            print("секрет сохранён в .env (KIT_WEBHOOK_SECRET)")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
