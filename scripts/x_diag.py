"""Diagnose X OAuth credentials without posting anything."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from post_telegram_channels_tweet import API, candidate_pairs, curl, oauth_header  # noqa: E402


def main() -> int:
    out = {
        "x_api_key_len": len(__import__("os").environ.get("X_API_KEY", "")),
        "x_api_secret_len": len(__import__("os").environ.get("X_API_SECRET", "")),
        "x_account_blob_len": len(__import__("os").environ.get("X_ACCOUNT_BLOB", "")),
        "x_access_token_len": len(__import__("os").environ.get("X_ACCESS_TOKEN", "")),
        "x_access_secret_len": len(__import__("os").environ.get("X_ACCESS_SECRET", "")),
        "candidates": [],
    }
    for label, ck, cs, tok, sec in candidate_pairs():
        if not ck or not cs or not tok:
            out["candidates"].append({"label": label, "skipped": "missing key/secret/token"})
            continue
        url = f"{API}/2/users/me"
        try:
            header = oauth_header("GET", url, ck, cs, tok, sec)
            rc, status, data, body = curl(["-H", f"Authorization: {header}", "-w", "\n%{http_code}", url])
            user = (data.get("data") or {}) if isinstance(data, dict) else {}
            out["candidates"].append({
                "label": label,
                "rc": rc,
                "http": status,
                "username": user.get("username"),
                "user_id": user.get("id"),
                "body": body[:500],
            })
        except Exception as exc:  # noqa: BLE001
            out["candidates"].append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
    path = ROOT / "growth-funnel" / "x-debug.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
