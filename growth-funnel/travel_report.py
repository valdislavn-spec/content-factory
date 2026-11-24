"""Daily travel funnel report: clicks -> bot starts -> verified users -> affiliate clicks."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "growth-funnel" / "reports"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / "growth-funnel" / ".env"):
        if path.exists() is False:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line == "" or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if isinstance(v, str)})
    return values


def read_secret(path: Path) -> str:
    if path.exists() is False:
        return ""
    return path.read_text(encoding="utf-8").strip()


def get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 40) -> dict[str, Any]:
    merged = {"user-agent": "Mozilla/5.0 (compatible; TravelFunnelReport/1.0)", "accept": "application/json"}
    merged.update(headers or {})
    request = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any], timeout: int = 40) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "user-agent": "Mozilla/5.0 (compatible; TravelFunnelReport/1.0)"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def tracker_stats(env: dict[str, str]) -> dict[str, Any]:
    base = (env.get("LINK_TRACKER_BASE") or "https://links-tracker.valdislav-n.workers.dev").rstrip("/")
    token = env.get("LINK_TRACKER_ADMIN_TOKEN") or env.get("LINK_TRACKER_STATS_TOKEN") or ""
    if token == "":
        return {"ok": False, "error": "LINK_TRACKER_STATS_TOKEN is empty", "links": []}
    try:
        return get_json(base + "/admin/funnel?token=" + urllib.parse.quote(token))
    except Exception as first_exc:
        try:
            return get_json(base + "/stats?token=" + urllib.parse.quote(token))
        except Exception as exc:
            return {"ok": False, "error": type(first_exc).__name__ + ": " + str(first_exc) + " / " + type(exc).__name__ + ": " + str(exc), "links": []}


def growth_stats(env: dict[str, str]) -> dict[str, Any]:
    base = (env.get("GROWTH_WORKER_URL") or "https://growth-bot.valdislav-n.workers.dev").rstrip("/")
    token = env.get("GROWTH_STATS_TOKEN") or read_secret(ROOT / "growth-funnel" / ".secrets" / "growthbot-stats-token") or read_secret(ROOT.parent / "growth-funnel" / ".secrets" / "growthbot-stats-token")
    if token == "":
        return {"ok": False, "error": "growth stats token is empty"}
    try:
        return get_json(base + "/admin/stats?token=" + urllib.parse.quote(token))
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}


def telegram_members(env: dict[str, str]) -> dict[str, Any]:
    token = env.get("TELEGRAM_BOT_TOKEN") or ""
    base = (env.get("TELEGRAM_API_BASE") or "https://telegram-proxy.valdislav-n.workers.dev").rstrip("/")
    chat = env.get("TELEGRAM_CHANNEL_ID") or "@GOODTRAVEL007"
    if token == "":
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is empty"}
    try:
        query = urllib.parse.urlencode({"chat_id": chat})
        return get_json(base + "/bot" + token + "/getChatMemberCount?" + query)
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}



def queue_stats(env: dict[str, str]) -> dict[str, Any]:
    base = (env.get("LINK_TRACKER_BASE") or "https://links-tracker.valdislav-n.workers.dev").rstrip("/")
    token = env.get("LINK_TRACKER_ADMIN_TOKEN") or env.get("LINK_TRACKER_STATS_TOKEN") or ""
    if token == "":
        return {"ok": False, "error": "LINK_TRACKER_ADMIN_TOKEN is empty", "total": 0}
    try:
        data = get_json(base + "/admin/queue?status=queued", headers={"x-token": token})
        items = data.get("items") or []
        by_platform: dict[str, int] = {}
        for item in items:
            platform = str(item.get("platform") or "other")
            by_platform[platform] = by_platform.get(platform, 0) + 1
        next_due = min([str(item.get("due")) for item in items if item.get("due")], default=None)
        return {"ok": True, "total": len(items), "by_platform": by_platform, "next_due": next_due}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc), "total": 0}


def build_report(env: dict[str, str], report_date: str) -> dict[str, Any]:
    tracker = tracker_stats(env)
    growth = growth_stats(env)
    telegram = telegram_members(env)
    queue = queue_stats(env)
    links = tracker.get("links", []) if isinstance(tracker.get("links"), list) else []
    launch_clicks = 0
    affiliate_clicks = 0
    top_links = []
    for link in links:
        code = str(link.get("code") or "")
        total = int(link.get("total") or 0)
        if code.startswith("launch-"):
            launch_clicks += total
        if code.startswith("offer-") or code.startswith("kit-"):
            affiliate_clicks += total
        if total > 0:
            top_links.append({"code": code, "total": total, "channel": link.get("channel", ""), "last_click": link.get("last_click")})
    top_links.sort(key=lambda item: item["total"], reverse=True)
    users = int(growth.get("users") or 0)
    verified = int(growth.get("verified") or 0)
    sources = growth.get("sources") or {}
    start_rate = round((users / launch_clicks) * 100, 1) if launch_clicks > 0 else 0.0
    verified_rate = round((verified / users) * 100, 1) if users > 0 else 0.0
    return {
        "date": report_date,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tracker_ok": bool(tracker.get("ok")),
        "growth_ok": bool(growth.get("ok")),
        "telegram_ok": bool(telegram.get("ok")),
        "funnel": {
            "launch_clicks": launch_clicks,
            "bot_users": users,
            "verified_users": verified,
            "affiliate_clicks": affiliate_clicks,
            "start_rate_pct": start_rate,
            "verified_rate_pct": verified_rate,
        },
        "sources": sources,
        "telegram_members": telegram.get("result") if telegram.get("ok") else None,
        "queue": queue,
        "top_links": top_links[:12],
        "errors": [x.get("error") for x in (tracker, growth, telegram, queue) if x.get("ok") is not True and x.get("error")],
    }


def format_markdown(report: dict[str, Any]) -> str:
    funnel = report["funnel"]
    sources = report.get("sources") or {}
    source_line = ", ".join([str(k) + "=" + str(v) for k, v in sorted(sources.items(), key=lambda item: int(item[1]), reverse=True)[:6]]) or "none"
    lines = [
        "📊 Travel funnel — " + report["date"],
        "",
        "Clicks (launch): " + str(funnel["launch_clicks"]),
        "Bot users: " + str(funnel["bot_users"]),
        "Verified: " + str(funnel["verified_users"]) + " (" + str(funnel["verified_rate_pct"]) + "%)",
        "Start rate: " + str(funnel["start_rate_pct"]) + "%",
        "Affiliate clicks: " + str(funnel["affiliate_clicks"]),
        "Telegram members: " + str(report.get("telegram_members") if report.get("telegram_members") is not None else "n/a"),
        "Queue: " + str((report.get("queue") or {}).get("total", 0)) + " queued, next " + str((report.get("queue") or {}).get("next_due") or "n/a"),
        "Sources: " + source_line,
    ]
    if report.get("top_links"):
        lines.append("")
        lines.append("Top links:")
        for link in report["top_links"][:8]:
            lines.append("- " + str(link["code"]) + ": " + str(link["total"]))
    if report.get("errors"):
        lines.append("")
        lines.append("Errors: " + "; ".join([str(x) for x in report["errors"]]))
    return "\n".join(lines)


def send_report(env: dict[str, str], text: str) -> dict[str, Any]:
    token = env.get("TELEGRAM_BOT_TOKEN") or ""
    base = (env.get("TELEGRAM_API_BASE") or "https://telegram-proxy.valdislav-n.workers.dev").rstrip("/")
    chat = env.get("TELEGRAM_ALERT_CHAT_ID") or env.get("GROWTH_ADMIN_ID") or "8337412751"
    if token == "":
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is empty"}
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    request = urllib.request.Request(base + "/bot" + token + "/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily travel funnel report")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--send", action="store_true", help="send the report to the Telegram admin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    env = load_env()
    report = build_report(env, args.date)
    markdown = format_markdown(report)
    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / (args.date + ".json")
    md_path = REPORTS / (args.date + ".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown + "\n", encoding="utf-8")
    if args.send:
        try:
            sent = send_report(env, markdown)
            report["telegram_send"] = {"ok": sent.get("ok"), "description": sent.get("description")}
        except Exception as exc:
            report["telegram_send"] = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
