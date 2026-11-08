#!/usr/bin/env python3
"""Программа роста Mastodon: подписки, хэштеги, бусты.

    python scripts/mastodon_growth.py --all --dry-run
    python scripts/mastodon_growth.py --all

Настройки: config/mastodon_growth.yaml; токен: MASTODON_TOKEN/MASTODON_BASE_URL.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from content_factory.utils import load_dotenv  # noqa: E402

UA = {"User-Agent": "content-factory-growth/1.0", "Accept": "application/json"}


def api(method: str, path: str, token: str, base: str, payload: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    headers = dict(UA)
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", "replace")
    return json.loads(body) if body.strip() else {}


def load_state(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def age_hours(created_at: Optional[str]) -> float:
    if not created_at:
        return 1e9
    try:
        value = created_at.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0
    except ValueError:
        return 1e9


def is_interesting_account(account: Dict[str, Any], config: Dict[str, Any]) -> bool:
    cfg = config.get("follow") or {}
    if account.get("bot") or account.get("locked"):
        return False
    followers = int(account.get("followers_count") or 0)
    statuses = int(account.get("statuses_count") or 0)
    if followers < int(cfg.get("min_followers") or 0):
        return False
    if followers > int(cfg.get("max_followers") or 10**9):
        return False
    if statuses < int(cfg.get("min_statuses") or 0):
        return False
    note = str(account.get("note") or "")
    if cfg.get("require_bio", True) and len(note) < 10:
        return False
    return True


def account_language_ok(status: Dict[str, Any], config: Dict[str, Any]) -> bool:
    allowed = [str(x).lower() for x in ((config.get("follow") or {}).get("languages") or [])]
    if not allowed:
        return True
    language = str(status.get("language") or "").lower()
    return not language or language in allowed


def discover_accounts(base: str, token: str, config: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    max_age = float((config.get("follow") or {}).get("max_age_hours") or 72)
    seen: Dict[str, Dict[str, Any]] = {}
    for topic in config.get("topics") or []:
        try:
            statuses = api("GET", "/api/v1/timelines/tag/" + urllib.parse.quote(str(topic)), token, base, params={"limit": 30})
        except Exception as exc:  # noqa: BLE001
            print("tag {} error: {}".format(topic, exc))
            continue
        for status in statuses if isinstance(statuses, list) else []:
            if status.get("reblog") or status.get("sensitive"):
                continue
            if age_hours(status.get("created_at")) > max_age:
                continue
            account = status.get("account") or {}
            if not is_interesting_account(account, config) or not account_language_ok(status, config):
                continue
            account_id = str(account.get("id") or "")
            if account_id:
                seen.setdefault(account_id, account)
        time.sleep(1.0)
    return list(seen.values())[:limit]


def run_follow(base: str, token: str, state: Dict[str, Any], config: Dict[str, Any], dry_run: bool, limit: Optional[int] = None) -> int:
    cfg = config.get("follow") or {}
    daily_limit = int(limit or cfg.get("daily_limit") or 20)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counters = state.setdefault("counters", {})
    if counters.get("date") != today:
        counters = state["counters"] = {"date": today, "followed": 0, "boosted": 0}
    budget = max(0, daily_limit - int(counters.get("followed") or 0))
    if budget <= 0:
        print("follow: дневной лимит исчерпан")
        return 0
    followed_ids = set(state.get("followed") or [])
    accounts = discover_accounts(base, token, config, budget * 4)
    own = api("GET", "/api/v1/accounts/verify_credentials", token, base)
    own_id = str(own.get("id") or "")
    count = 0
    for account in accounts:
        if count >= budget:
            break
        account_id = str(account.get("id") or "")
        if not account_id or account_id == own_id or account_id in followed_ids:
            continue
        name = "@{}".format(account.get("acct") or account_id)
        try:
            relationship = api("GET", "/api/v1/accounts/relationships", token, base, params={"id[]": [account_id]})
            if relationship and relationship[0].get("following"):
                followed_ids.add(account_id)
                continue
        except Exception as exc:  # noqa: BLE001
            print("relationship {} error: {}".format(name, exc))
            continue
        if dry_run:
            print("[dry] follow", name, "| followers:", account.get("followers_count"))
        else:
            try:
                api("POST", "/api/v1/accounts/{}/follow".format(account_id), token, base)
                print("follow", name, "| followers:", account.get("followers_count"))
                time.sleep(3.0)
            except Exception as exc:  # noqa: BLE001
                print("follow {} error: {}".format(name, exc))
                continue
        followed_ids.add(account_id)
        counters["followed"] = int(counters.get("followed") or 0) + 1
        count += 1
        if not dry_run:
            save_state(Path(str(config.get("state_path") or "data/mastodon_growth_state.json")), state)
    state["followed"] = sorted(followed_ids)
    print("followed now: {}".format(count))
    return count


def run_boost(base: str, token: str, state: Dict[str, Any], config: Dict[str, Any], dry_run: bool) -> int:
    cfg = config.get("boost") or {}
    daily_limit = int(cfg.get("daily_limit") or 5)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counters = state.setdefault("counters", {})
    if counters.get("date") != today:
        counters = state["counters"] = {"date": today, "followed": 0, "boosted": 0}
    budget = max(0, daily_limit - int(counters.get("boosted") or 0))
    if budget <= 0:
        print("boost: дневной лимит исчерпан")
        return 0
    boosted = set(state.get("boosted") or [])
    candidates: List[Dict[str, Any]] = []
    max_age = float(cfg.get("max_age_hours") or 48)
    for topic in config.get("topics") or []:
        try:
            statuses = api("GET", "/api/v1/timelines/tag/" + urllib.parse.quote(str(topic)), token, base, params={"limit": 20})
        except Exception:  # noqa: BLE001
            continue
        for status in statuses if isinstance(statuses, list) else []:
            if status.get("reblog") or status.get("sensitive") or age_hours(status.get("created_at")) > max_age:
                continue
            if not account_language_ok(status, config):
                continue
            account = status.get("account") or {}
            if int(account.get("followers_count") or 0) > int(cfg.get("max_followers") or 10**9):
                continue
            if int(status.get("favourites_count") or 0) < int(cfg.get("min_favourites") or 0):
                continue
            candidates.append(status)
    count = 0
    for status in candidates:
        if count >= budget:
            break
        status_id = str(status.get("id") or "")
        if not status_id or status_id in boosted:
            continue
        account = status.get("account") or {}
        if account.get("id") and str(account.get("id")) == "":  # pragma: no cover
            continue
        if dry_run:
            print("[dry] boost", status.get("url"), "| favs:", status.get("favourites_count"))
        else:
            try:
                api("POST", "/api/v1/statuses/{}/reblog".format(status_id), token, base)
                print("boost", status.get("url"))
                time.sleep(4.0)
            except Exception as exc:  # noqa: BLE001
                print("boost error:", exc)
                continue
        boosted.add(status_id)
        counters["boosted"] = int(counters.get("boosted") or 0) + 1
        count += 1
        save_state(Path(str(config.get("state_path") or "data/mastodon_growth_state.json")), state)
    state["boosted"] = sorted(boosted)
    print("boosted now: {}".format(count))
    return count


def follow_tags(base: str, token: str, config: Dict[str, Any], dry_run: bool) -> int:
    count = 0
    for topic in config.get("topics") or []:
        tag = str(topic).strip("#")
        if dry_run:
            print("[dry] follow tag #" + tag)
            count += 1
            continue
        try:
            api("POST", "/api/v1/tags/{}/follow".format(urllib.parse.quote(tag)), token, base)
            print("follow tag #" + tag)
            count += 1
            time.sleep(2.0)
        except Exception as exc:  # noqa: BLE001
            print("tag #{} error: {}".format(tag, exc))
    return count


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mastodon growth program")
    parser.add_argument("--config", default="config/mastodon_growth.yaml")
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--boost", action="store_true")
    parser.add_argument("--tags", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    load_dotenv(ROOT / ".env")
    base = (os.environ.get("MASTODON_BASE_URL", "") or "").strip().rstrip("/")
    token = (os.environ.get("MASTODON_TOKEN", "") or "").strip()
    if not base or not token:
        print("MASTODON_BASE_URL/MASTODON_TOKEN не заданы")
        return 1
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if config.get("enabled") is False:
        print("growth disabled")
        return 0
    state_path = Path(str(config.get("state_path") or "data/mastodon_growth_state.json"))
    if not state_path.is_absolute():
        state_path = ROOT / state_path
    config["state_path"] = str(state_path)
    state = load_state(state_path)
    if args.all or args.follow:
        run_follow(base, token, state, config, args.dry_run, args.limit or None)
    if args.all or args.tags:
        follow_tags(base, token, config, args.dry_run)
    if args.all or args.boost:
        run_boost(base, token, state, config, args.dry_run)
    if not args.dry_run:
        save_state(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
