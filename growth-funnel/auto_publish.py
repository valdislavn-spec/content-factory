"""Daily publisher for the GOODTRAVEL007 funnel.

- Telegram: publishes due posts via Bot API.
- Pinterest: publishes due pins via official API (image_base64).
- Queue state is stored in growth-funnel/queue.json.

Default is dry-run. Use --execute to publish.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "growth-funnel" / "queue.json"

sys.path.insert(0, str(ROOT / "affiliate-fanout"))
try:
    from affiliate_fanout.env import parse_env_file
except Exception:  # pragma: no cover
    parse_env_file = None


def merged_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if parse_env_file:
        for path in (ROOT / "content-factory/.env", ROOT / "affiliate-fanout/.env"):
            try:
                values.update(parse_env_file(str(path)))
            except Exception:
                pass
    values.update({k: v for k, v in os.environ.items() if isinstance(v, str)})
    return values


def load_queue(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("queue.json должен быть массивом")
    return data


def save_queue(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def curl_json(args: list[str], stdin_text: str | None = None) -> tuple[dict[str, Any], int, str]:
    cmd = ["curl", "-sS", "--max-time", "45"] + args
    proc = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True)
    if proc.returncode != 0:
        return {}, 0, (proc.stderr or "curl failed").strip()
    raw = proc.stdout or ""
    status = 0
    if "\n" in raw:
        maybe_status = raw.rsplit("\n", 1)[-1].strip()
        if maybe_status.isdigit():
            status = int(maybe_status)
            raw = raw.rsplit("\n", 1)[0]
    try:
        return json.loads(raw) if raw else {}, status, ""
    except ValueError:
        return {}, status, raw[:300]


def post_telegram(item: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN не задан"}
    base = (env.get("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")
    chat = str(item.get("chat_id") or env.get("TELEGRAM_CHANNEL_ID") or "@GOODTRAVEL007")
    text = str(item.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "пустой text"}

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as fh:
        fh.write(text)
        text_path = fh.name
    try:
        data, _, err = curl_json([
            "-X", "POST",
            f"{base}/bot{token}/sendMessage",
            "--data-urlencode", f"chat_id={chat}",
            "--data-urlencode", f"text@{text_path}",
            "--data-urlencode", "disable_web_page_preview=false",
        ])
    finally:
        Path(text_path).unlink(missing_ok=True)
    if err:
        return {"ok": False, "error": err}
    if not data.get("ok"):
        return {"ok": False, "error": str(data.get("description") or data)[:300]}
    result = data.get("result") or {}
    chat_info = result.get("chat") or {}
    username = chat_info.get("username")
    mid = result.get("message_id")
    url = f"https://t.me/{username}/{mid}" if username and mid else (f"https://t.me/{username}" if username else "")
    return {"ok": True, "message_id": mid, "url": url}


def post_pinterest(item: dict[str, Any], env: dict[str, str], allow_sandbox: bool = False) -> dict[str, Any]:
    token = (env.get("PINTEREST_ACCESS_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "skipped": True, "error": "PINTEREST_ACCESS_TOKEN не задан"}
    link = str(item.get("link") or "").strip()
    if not link:
        return {"ok": False, "error": "пустой link"}
    board_env = str(item.get("board_id_env") or "PINTEREST_BOARD_ID")
    board_id = (env.get(board_env) or env.get("PINTEREST_BOARD_ID") or "").strip()
    if not board_id:
        return {"ok": False, "error": f"не задан board_id ({board_env})"}

    image_value = str(item.get("image") or "").strip()
    image_path = Path(image_value)
    if not image_path.is_absolute():
        image_path = ROOT / image_path
    if not image_path.exists():
        return {"ok": False, "error": f"картинка не найдена: {image_path}"}
    suffix = image_path.suffix.lower()
    content_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix)
    if not content_type:
        return {"ok": False, "error": f"неизвестный тип картинки: {suffix}"}
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")

    base = (env.get("PINTEREST_API_BASE") or "https://api.pinterest.com").rstrip("/")
    if base.endswith("/v5"):
        base = base[:-3]
    if "sandbox" in base.lower() and not allow_sandbox:
        return {"ok": False, "skipped": True, "error": "Pinterest API в sandbox; production-токен ещё не настроен"}
    payload = {
        "board_id": board_id,
        "title": str(item.get("title") or "")[:100],
        "description": str(item.get("description") or "")[:500],
        "link": link,
        "media_source": {
            "source_type": "image_base64",
            "content_type": content_type,
            "data": encoded,
        },
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        payload_path = fh.name
    try:
        data, status, err = curl_json([
            "-X", "POST",
            f"{base}/v5/pins",
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/json",
            "--data-binary", f"@{payload_path}",
            "-w", "\n%{http_code}",
        ])
    finally:
        Path(payload_path).unlink(missing_ok=True)
    if err:
        return {"ok": False, "error": err}
    if status >= 400 or not data.get("id"):
        return {"ok": False, "error": str(data)[:300]}
    pin_id = data.get("id")
    return {"ok": True, "pin_id": pin_id, "url": f"https://www.pinterest.com/pin/{pin_id}/"}


def select_items(queue: list[dict[str, Any]], platforms: set[str], due_date: str, limit_per_platform: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for platform in sorted(platforms):
        candidates = [x for x in queue if x.get("platform") == platform and x.get("status") == "queued" and str(x.get("due") or "") <= due_date]
        candidates.sort(key=lambda x: (str(x.get("due") or ""), str(x.get("id") or "")))
        if limit_per_platform > 0:
            candidates = candidates[:limit_per_platform]
        selected.extend(candidates)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="GOODTRAVEL007 daily publisher")
    parser.add_argument("--queue", default=str(QUEUE))
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD; по умолчанию сегодня")
    parser.add_argument("--platforms", default="telegram,pinterest")
    parser.add_argument("--limit-per-platform", type=int, default=1, help="0 = все due-элементы")
    parser.add_argument("--execute", action="store_true", help="реально публиковать")
    parser.add_argument("--allow-sandbox", action="store_true", help="разрешить тестовую публикацию в Pinterest sandbox")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    env = merged_env()
    queue_path = Path(args.queue)
    queue = load_queue(queue_path)
    platforms = {x.strip() for x in args.platforms.split(",") if x.strip()}
    selected = select_items(queue, platforms, args.date, args.limit_per_platform)

    results: list[dict[str, Any]] = []
    for item in selected:
        platform = item.get("platform")
        if not args.execute:
            results.append({"id": item.get("id"), "platform": platform, "ok": True, "dry_run": True, "due": item.get("due")})
            continue
        item["last_attempt_at"] = now_iso()
        try:
            if platform == "telegram":
                outcome = post_telegram(item, env)
            elif platform == "pinterest":
                outcome = post_pinterest(item, env, allow_sandbox=args.allow_sandbox)
            else:
                outcome = {"ok": False, "error": f"неизвестная платформа: {platform}"}
        except Exception as exc:  # noqa: BLE001
            outcome = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        result = {"id": item.get("id"), "platform": platform, "due": item.get("due"), **outcome}
        if outcome.get("ok"):
            item["status"] = "published"
            item["published_at"] = args.date
            if outcome.get("message_id"):
                item["message_id"] = outcome["message_id"]
            if outcome.get("url"):
                item["published_url"] = outcome["url"]
            item.pop("last_error", None)
        else:
            item["last_error"] = str(outcome.get("error") or "unknown")[:300]
        results.append(result)

    if args.execute:
        save_queue(queue_path, queue)

    payload = {"mode": "execute" if args.execute else "dry-run", "date": args.date, "count": len(results), "results": results}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Режим: {payload['mode']}  дата: {args.date}  задач: {len(results)}")
        for r in results:
            if r.get("dry_run"):
                print(f"[dry-run] {r['platform']}: {r['id']} (due {r.get('due')})")
            elif r.get("ok"):
                print(f"[ok] {r['platform']}: {r['id']} -> {r.get('url') or r.get('pin_url') or ''}")
            elif r.get("skipped"):
                print(f"[skip] {r['platform']}: {r['id']} — {r.get('error')}")
            else:
                print(f"[error] {r['platform']}: {r['id']} — {r.get('error')}")
    return 0 if all(r.get("ok") or r.get("dry_run") or r.get("skipped") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
