"""Post the Telegram channel promo to X through Buffer API."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / "growth-funnel" / ".tweeted-telegram-channels"
DEBUG = ROOT / "growth-funnel" / "buffer-post-debug.json"
CHANNEL_ID = "6951b346457dae6a34bd5e32"
IMAGE_URL = "https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/growth-funnel/twitter-telegram-channels.png"
TEXT = """Telegram channels worth your time — no fluff:

✈️ Travel: https://t.me/GOODTRAVEL007
🤖 AI: https://t.me/AINEWS0007
📈 Crypto: https://t.me/HOOPY0007
🏆 US Sports: https://t.me/SPORTNews0007

Save this post. #Telegram"""

QUERY = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id text dueAt status externalLink } }
    ... on MutationError { message }
  }
}
"""


def curl_json(payload: dict) -> tuple[int, int, dict, str]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        path = fh.name
    try:
        proc = subprocess.run([
            "curl", "-sS", "--max-time", "45",
            "-X", "POST", "https://api.buffer.com",
            "-H", "Authorization: Bearer " + os.environ.get("BUFFER_API_KEY", ""),
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json",
            "--data-binary", f"@{path}",
            "-w", "\n%{http_code}",
        ], capture_output=True, text=True)
    finally:
        Path(path).unlink(missing_ok=True)
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


def main() -> int:
    debug: dict = {"channel_id": CHANNEL_ID, "image_url": IMAGE_URL, "text": TEXT}
    try:
        if MARKER.exists():
            print("marker exists, already posted:", MARKER.read_text().strip())
            return 0
        if not os.environ.get("BUFFER_API_KEY", "").strip():
            debug["error"] = "BUFFER_API_KEY is not set"
            return 1
        payload = {
            "query": QUERY,
            "variables": {
                "input": {
                    "channelId": CHANNEL_ID,
                    "text": TEXT,
                    "schedulingType": "automatic",
                    "mode": "shareNow",
                    "needsApproval": False,
                    "assets": [{"image": {"url": IMAGE_URL}}],
                    "source": "api",
                }
            },
        }
        rc, status, data, body = curl_json(payload)
        debug.update({"rc": rc, "http": status, "body": body[:3000], "response": data})
        print(f"buffer: rc={rc} http={status} body={body[:500]}")
        errors = data.get("errors") or []
        result = ((data.get("data") or {}).get("createPost") or {}) if isinstance(data, dict) else {}
        post = result.get("post") or {}
        if errors or not post.get("id"):
            debug["error"] = "Buffer createPost failed"
            return 1
        marker = {
            "posted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider": "buffer",
            "channel_id": CHANNEL_ID,
            "post_id": post.get("id"),
            "status": post.get("status"),
            "external_link": post.get("externalLink"),
            "text": TEXT,
            "image_url": IMAGE_URL,
        }
        MARKER.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n")
        debug["marker"] = marker
        print("BUFFER_POST_ID=" + str(post.get("id")))
        print("BUFFER_STATUS=" + str(post.get("status")))
        print("BUFFER_LINK=" + str(post.get("externalLink") or ""))
        return 0
    except Exception as exc:  # noqa: BLE001
        debug["exception"] = f"{type(exc).__name__}: {exc}"
        print("exception:", debug["exception"])
        return 1
    finally:
        DEBUG.write_text(json.dumps(debug, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
