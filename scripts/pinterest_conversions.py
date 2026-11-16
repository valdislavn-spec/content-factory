#!/usr/bin/env python3
"""Pinterest Conversions API v5 helper (server-side events).

Send lead/signup/checkout events to Pinterest so ads can optimise for real
conversions instead of clicks. Uses only the standard library.

Environment (content-factory/.env is loaded automatically):
  PINTEREST_CAPI_TOKEN     token with ads:write scope
  PINTEREST_AD_ACCOUNT_ID  Ads Manager ad account id
  PINTEREST_CAPI_API_BASE  default https://api.pinterest.com/v5

The token is intentionally separate from PINTEREST_ACCESS_TOKEN (pins):
Pinterest ads tokens and pinning tokens have different scopes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
DEFAULT_API_BASE = "https://api.pinterest.com/v5"
DEFAULT_TRACKER = "https://links-tracker.valdislav-n.workers.dev"
MAX_EVENT_AGE_SECONDS = 7 * 24 * 3600

EVENT_NAMES = {
    "add_to_cart", "checkout", "custom", "lead", "page_visit",
    "search", "signup", "view_category", "watch_video",
}
ACTION_SOURCES = {"web", "app_android", "app_ios", "offline"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
_PHONE_RE = re.compile(r"[^0-9+]")


def load_env(path: Path = ENV_FILE) -> None:
    """Load simple KEY=VALUE lines without overriding the real environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(chr(35)) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (key not in os.environ or os.environ.get(key) == ""):
            os.environ[key] = value


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("invalid email: " + repr(value))
    return email


def normalize_phone(value: str) -> str:
    digits = _PHONE_RE.sub("", value.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if not 7 <= len(digits) <= 15:
        raise ValueError("invalid phone: " + repr(value))
    return digits


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_user_data(*, email: str = "", phone: str = "", external_id: str = "", click_id: str = "") -> dict[str, Any]:
    """Return Pinterest user_data with SHA-256 hashes where required."""
    data: dict[str, list[str]] = {}
    if email:
        data["em"] = [sha256_hex(normalize_email(email))]
    if phone:
        data["ph"] = [sha256_hex(normalize_phone(phone))]
    if external_id:
        data["external_id"] = [sha256_hex(_clean(external_id))]
    if click_id:
        data["click_id"] = _clean(click_id)
    if not data:
        raise ValueError("at least one of email, phone, external_id or click_id is required")
    return data


def build_event(
    *, event_name: str = "lead", email: str = "", phone: str = "",
    external_id: str = "", click_id: str = "", event_id: str = "",
    event_time: int | None = None, source_url: str = "",
    value: str | float | None = None, currency: str = "USD",
    action_source: str = "web", opt_out: bool = False,
    client_ip: str = "", client_user_agent: str = "",
    extra_user_data: dict[str, Any] | None = None,
    extra_custom_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = _clean(event_name).lower()
    if name not in EVENT_NAMES:
        raise ValueError("unsupported event_name " + repr(event_name))
    if action_source not in ACTION_SOURCES:
        raise ValueError("unsupported action_source " + repr(action_source))

    user_data = build_user_data(email=email, phone=phone, external_id=external_id, click_id=click_id)
    if client_ip:
        user_data["client_ip_address"] = _clean(client_ip)
    if client_user_agent:
        user_data["client_user_agent"] = _clean(client_user_agent)[:500]
    for key, raw in (extra_user_data or {}).items():
        if raw in (None, "", [], {}):
            continue
        if isinstance(raw, list):
            user_data[key] = [_clean(v) for v in raw if _clean(v)]
        else:
            user_data[key] = [_clean(raw)]

    event: dict[str, Any] = {
        "event_name": name,
        "action_source": action_source,
        "event_time": int(event_time or time.time()),
        "event_id": _clean(event_id) or sha256_hex(
            name + "|" + email + "|" + external_id + "|" + click_id + "|" + str(int(time.time()))
        )[:32],
        "user_data": user_data,
    }
    if source_url:
        event["event_source_url"] = _clean(source_url)
    custom_data = dict(extra_custom_data or {})
    if value is not None:
        custom_data["value"] = "{:.2f}".format(float(value))
        custom_data["currency"] = _clean(currency).upper() or "USD"
    if custom_data:
        event["custom_data"] = custom_data
    if opt_out:
        event["opt_out"] = True
    return event


def api_base() -> str:
    return (os.environ.get("PINTEREST_CAPI_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def config() -> tuple[str, str]:
    token = (os.environ.get("PINTEREST_CAPI_TOKEN") or "").strip()
    ad_account = (os.environ.get("PINTEREST_AD_ACCOUNT_ID") or "").strip()
    return token, ad_account


def send_events(events: Iterable[dict[str, Any]], *, dry_run: bool = False, test: bool = False, timeout: int = 30) -> dict[str, Any]:
    data = list(events)
    payload = {"data": data}
    if not data:
        return {"ok": True, "dry_run": dry_run, "sent": 0, "note": "no events"}
    if dry_run:
        return {"ok": True, "dry_run": True, "sent": len(data), "payload": payload}

    token, ad_account = config()
    if not token:
        raise RuntimeError("PINTEREST_CAPI_TOKEN is not set (needs ads:write scope)")
    if not ad_account:
        raise RuntimeError("PINTEREST_AD_ACCOUNT_ID is not set")

    url = api_base() + "/ad_accounts/" + urllib.parse.quote(ad_account, safe="") + "/events"
    if test:
        url = url + "?test=true"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "content-factory-pinterest-capi/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body.strip().startswith("{") else {"raw": body[:1000]}
            failed = 0
            if isinstance(parsed, dict):
                try:
                    failed = int(parsed.get("num_events_failed") or 0)
                except (TypeError, ValueError):
                    failed = 1 if parsed.get("num_events_failed") else 0
            return {"ok": failed == 0, "status": resp.status, "sent": len(data), "failed": failed, "response": parsed}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:1000]}
        return {"ok": False, "status": exc.code, "sent": len(data), "error": parsed}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": 0, "sent": len(data), "error": str(exc.reason)}


def _fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "content-factory-pinterest-capi/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def events_from_d1(*, tracker: str = DEFAULT_TRACKER, admin_token: str = "", limit: int = 200) -> list[dict[str, Any]]:
    """Convert active D1 subscribers into Pinterest lead events."""
    if not admin_token:
        raise RuntimeError("LINK_TRACKER_ADMIN_TOKEN is required for --from-d1")
    url = tracker.rstrip("/") + "/admin/subscribers?token=" + urllib.parse.quote(admin_token)
    payload = _fetch_json(url)
    rows = payload.get("subscribers") or []
    events: list[dict[str, Any]] = []
    for row in rows[-limit:]:
        email = _clean(row.get("email"))
        if not email:
            continue
        created = _clean(row.get("created_at"))
        try:
            event_time = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp())
        except Exception:
            event_time = int(time.time())
        source = _clean(row.get("source"))
        if event_time < int(time.time()) - MAX_EVENT_AGE_SECONDS:
            continue
        events.append(build_event(
            event_name="lead",
            email=email,
            external_id="email:" + email,
            event_id=sha256_hex("lead|" + email)[:32],
            event_time=event_time,
            source_url="https://valdislavn-spec.github.io/content-factory/?utm_source=pinterest&utm_medium=email&utm_campaign=" + source,
            extra_custom_data={"source": source, "lang": _clean(row.get("lang"))},
        ))
    return events


def _load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("sent_event_ids") or [])
    except Exception:
        return set()


def _save_state(path: Path, event_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sent_event_ids": sorted(event_ids)}, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(description="Pinterest Conversions API v5 helper")
    parser.add_argument("--check", action="store_true", help="validate configuration without network calls")
    parser.add_argument("--verify", action="store_true", help="GET ad account to verify token/scopes")
    parser.add_argument("--event", default="lead", choices=sorted(EVENT_NAMES))
    parser.add_argument("--email", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--external-id", default="")
    parser.add_argument("--click-id", default="", help="Pinterest epik click id")
    parser.add_argument("--event-id", default="")
    parser.add_argument("--event-time", type=int, default=0)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--client-ip", default="")
    parser.add_argument("--client-user-agent", default="")
    parser.add_argument("--value", default="")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--from-json", metavar="FILE", help="send events from JSON file")
    parser.add_argument("--from-d1", action="store_true", help="send D1 subscribers as lead events")
    parser.add_argument("--tracker", default=DEFAULT_TRACKER)
    parser.add_argument("--state", default=".local/pinterest-capi-state.json")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--send", action="store_true", help="actually call Pinterest (default is dry-run)")
    parser.add_argument("--test", action="store_true", help="send in Pinterest test mode (not counted in reporting)")
    parser.add_argument("--dry-run", action="store_true", help="explicitly only print the payload")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    token, ad_account = config()
    if args.check or args.verify:
        info = {
            "token_set": bool(token),
            "token_suffix": token[-6:] if token else "",
            "ad_account_id": ad_account,
            "api_base": api_base(),
            "ready": bool(token and ad_account),
        }
        if args.verify and token and ad_account:
            account_url = api_base() + "/ad_accounts/" + urllib.parse.quote(ad_account, safe="")
            req = urllib.request.Request(account_url, headers={"Authorization": "Bearer " + token})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    info["verify_status"] = resp.status
                    info["verify_ok"] = True
            except urllib.error.HTTPError as exc:
                info["verify_status"] = exc.code
                info["verify_ok"] = False
                info["verify_error"] = exc.read().decode("utf-8", errors="replace")[:500]
            except urllib.error.URLError as exc:
                info["verify_ok"] = False
                info["verify_error"] = str(exc.reason)
            # Safe write probe: an empty data array is rejected by validation and
            # does not create a conversion. A validation 400 proves ads:write.
            probe_req = urllib.request.Request(
                account_url + "/events",
                data=b'{"data":[]}',
                method="POST",
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(probe_req, timeout=30) as resp:
                    info["write_probe_status"] = resp.status
                    info["write_access"] = True
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                info["write_probe_status"] = exc.code
                info["write_probe_response"] = body[:500]
                info["write_access"] = exc.code == 400
            except urllib.error.URLError as exc:
                info["write_access"] = False
                info["write_probe_error"] = str(exc.reason)
            info["ready"] = bool(token and ad_account and (info.get("verify_ok") or info.get("write_access")))
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0 if (info["ready"] or args.check) else 1

    events: list[dict[str, Any]] = []
    state_path = Path(args.state)
    if args.from_json:
        raw = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        events = raw.get("data") if isinstance(raw, dict) else raw
        if not isinstance(events, list):
            raise SystemExit("JSON must be a list or an object with a data list")
    elif args.from_d1:
        events = events_from_d1(
            tracker=args.tracker,
            admin_token=os.environ.get("LINK_TRACKER_ADMIN_TOKEN", "").strip(),
            limit=args.limit,
        )
        seen = _load_state(state_path)
        events = [e for e in events if e.get("event_id") not in seen]
    else:
        events = [build_event(
            event_name=args.event,
            email=args.email,
            phone=args.phone,
            external_id=args.external_id,
            click_id=args.click_id,
            event_id=args.event_id,
            event_time=args.event_time or None,
            source_url=args.source_url,
            client_ip=args.client_ip,
            client_user_agent=args.client_user_agent,
            value=args.value or None,
            currency=args.currency,
        )]

    result = send_events(events, dry_run=(not args.send) or args.dry_run, test=args.test)
    if args.send and result.get("ok") and args.from_d1:
        seen = _load_state(state_path)
        seen.update(str(e.get("event_id")) for e in events)
        _save_state(state_path, seen)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result.get("dry_run"):
        print("[dry-run] " + str(result.get("sent", 0)) + " event(s)")
        print(json.dumps(result.get("payload"), ensure_ascii=False, indent=2))
    elif result.get("ok"):
        print("sent: " + str(result.get("sent", 0)) + " status: " + str(result.get("status")))
        print(json.dumps(result.get("response"), ensure_ascii=False, indent=2))
    else:
        print("failed: status=" + str(result.get("status")) + " error=" + str(result.get("error")), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
