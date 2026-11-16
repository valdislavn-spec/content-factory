"""One-off X/Twitter post: advertise the Telegram channel network."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "growth-funnel" / "twitter-telegram-channels.png"
MARKER = ROOT / "growth-funnel" / ".tweeted-telegram-channels"
DEBUG = ROOT / "growth-funnel" / "x-post-debug.json"
DEBUG_DATA: dict = {}
API = "https://api.x.com"
TEXT = """Telegram channels worth your time — no fluff:

✈️ Travel: https://t.me/GOODTRAVEL007
🤖 AI: https://t.me/AINEWS0007
📈 Crypto: https://t.me/HOOPY0007
🏆 US Sports: https://t.me/SPORTNews0007

Save this post. #Telegram"""


def pct(value: str) -> str:
    return quote(str(value), safe="~")


def oauth_header(method: str, url: str, consumer_key: str, consumer_secret: str, token: str, token_secret: str) -> str:
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    parameter_string = "&".join(f"{pct(k)}={pct(v)}" for k, v in sorted(params.items()))
    base_string = "&".join([method.upper(), pct(url), pct(parameter_string)])
    signing_key = f"{pct(consumer_secret)}&{pct(token_secret)}"
    digest = hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    return "OAuth " + ", ".join(f'{pct(k)}="{pct(v)}"' for k, v in sorted(params.items()))


def curl(args: list[str]) -> tuple[int, int, dict, str]:
    proc = subprocess.run(["curl", "-sS", "--max-time", "45"] + args, capture_output=True, text=True)
    raw = proc.stdout or ""
    status = 0
    body = raw
    if "\n" in raw:
        last = raw.rsplit("\n", 1)[-1].strip()
        if last.isdigit():
            status = int(last)
            body = raw.rsplit("\n", 1)[0]
    try:
        data = json.loads(body) if body else {}
    except ValueError:
        data = {}
    return proc.returncode, status, data, body


def candidate_pairs() -> list[tuple[str, str, str]]:
    ck = os.environ.get("X_API_KEY", "").strip()
    cs = os.environ.get("X_API_SECRET", "").strip()
    blob = os.environ.get("X_ACCOUNT_BLOB", "").strip()
    out: list[tuple[str, str, str]] = []
    tok = os.environ.get("X_ACCESS_TOKEN", "").strip()
    sec = os.environ.get("X_ACCESS_SECRET", "").strip()
    if tok:
        out.append(("env-access-token", tok, sec))
    if blob:
        marker = "%3D"
        idx = blob.find(marker)
        first = blob[: idx + len(marker)] if idx >= 0 else blob
        second = blob[idx + len(marker) :] if idx >= 0 else ""
        out.extend([
            ("unquoted-first/second", unquote(first), second),
            ("raw-first/second", first, second),
            ("blob/empty", blob, ""),
            ("unquoted-blob/empty", unquote(blob), ""),
        ])
    return [(label, ck, cs, tok, sec) for label, tok, sec in out]


def find_creds() -> tuple[str, str, str, str, str] | None:
    seen = set()
    for label, ck, cs, tok, sec in candidate_pairs():
        if not ck or not cs or not tok or (label, tok, sec) in seen:
            continue
        seen.add((label, tok, sec))
        url = f"{API}/2/users/me"
        header = oauth_header("GET", url, ck, cs, tok, sec)
        rc, status, data, body = curl(["-H", f"Authorization: {header}", "-w", "\n%{http_code}", url])
        print(f"creds[{label}]: rc={rc} http={status} body={body[:160]}")
        if status == 200 and (data.get("data") or {}).get("id"):
            user = data["data"]
            print(f"authenticated as @{user.get('username')} id={user.get('id')}")
            return label, ck, cs, tok, sec
    return None


def upload_media(ck: str, cs: str, tok: str, sec: str) -> str | None:
    if not IMAGE.exists():
        print("image missing:", IMAGE)
        return None
    endpoints = [
        "https://upload.twitter.com/1.1/media/upload.json",
        "https://api.x.com/1.1/media/upload.json",
    ]
    for url in endpoints:
        header = oauth_header("POST", url, ck, cs, tok, sec)
        rc, status, data, body = curl([
            "-X", "POST", url,
            "-H", f"Authorization: {header}",
            "-F", f"media=@{IMAGE};type=image/png",
            "-w", "\n%{http_code}",
        ])
        print(f"media[{url}]: rc={rc} http={status} body={body[:180]}")
        mid = ""
        if status in (200, 201):
            mid = data.get("media_id_string") or (str(data.get("media_id")) if data.get("media_id") else "")
        DEBUG_DATA.setdefault("media", []).append({"url": url, "rc": rc, "http": status, "body": body[:800], "media_id": mid})
        if mid:
            return mid
    return None


def post_tweet(ck: str, cs: str, tok: str, sec: str, media_id: str | None) -> str | None:
    url = f"{API}/2/tweets"
    payload = {"text": TEXT}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        path = fh.name
    try:
        header = oauth_header("POST", url, ck, cs, tok, sec)
        rc, status, data, body = curl([
            "-X", "POST", url,
            "-H", f"Authorization: {header}",
            "-H", "Content-Type: application/json",
            "--data-binary", f"@{path}",
            "-w", "\n%{http_code}",
        ])
    finally:
        Path(path).unlink(missing_ok=True)
    print(f"tweet: rc={rc} http={status} body={body[:300]}")
    DEBUG_DATA["tweet"] = {"rc": rc, "http": status, "body": body[:2000], "payload": payload}
    if status in (200, 201) and (data.get("data") or {}).get("id"):
        tid = data["data"]["id"]
        return f"https://x.com/i/web/status/{tid}"
    return None


def main() -> int:
    try:
        if MARKER.exists():
            print("marker exists, already posted:", MARKER.read_text().strip())
            return 0
        creds = find_creds()
        if not creds:
            print("no working X OAuth user context found")
            return 1
        label, ck, cs, tok, sec = creds
        DEBUG_DATA["credential"] = label
        DEBUG_DATA["image"] = str(IMAGE)
        media_id = upload_media(ck, cs, tok, sec)
        if media_id:
            print("media_id:", media_id)
        else:
            print("media upload failed, posting text-only")
        tweet_url = post_tweet(ck, cs, tok, sec, media_id)
        if not tweet_url:
            return 1
        MARKER.write_text(json.dumps({
            "posted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tweet_url": tweet_url,
            "media_id": media_id,
            "credential": label,
        }, ensure_ascii=False, indent=2) + "\n")
        DEBUG_DATA["tweet_url"] = tweet_url
        print("TWEET_URL=" + tweet_url)
        return 0
    except Exception as exc:  # noqa: BLE001
        DEBUG_DATA["exception"] = f"{type(exc).__name__}: {exc}"
        print("exception:", DEBUG_DATA["exception"])
        return 1
    finally:
        DEBUG.write_text(json.dumps(DEBUG_DATA, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
