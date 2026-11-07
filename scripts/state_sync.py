#!/usr/bin/env python3
"""Дублирует состояние слотов в GitHub variable (переживает потерю кэша).

Зачем: GitHub Actions cache может вытесниться/не сохраниться и тогда
планировщик снова публикует «последний слот» (дубли постов). Здесь состояние
(JSON обоих наборов каналов) хранится в переменной репозитория.

    python scripts/state_sync.py pull   # переменная -> data/schedule_state*.json
    python scripts/state_sync.py push   # файлы -> переменная (с обрезкой старых слотов)

Токен: ALERT_GITHUB_TOKEN (fine-grained PAT с доступом к Variables: write).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = os.environ.get("STATE_SYNC_REPO", "valdislavn-spec/content-factory")
VAR = os.environ.get("STATE_SYNC_VAR", "CF_SCHEDULE_STATE")
FILES = {
    "schedule_state": Path("data/schedule_state.json"),
    "schedule_state_es": Path("data/schedule_state_es.json"),
}
KEEP_DAYS = 3
MAX_BYTES = 45000


def token() -> str:
    return os.environ.get("ALERT_GITHUB_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()


def api(method: str, path: str, payload=None):
    import urllib.error
    import urllib.request

    url = f"https://api.github.com/repos/{REPO}{path}"
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": "Bearer " + token(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "content-factory-state-sync",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
        if not raw:
            return resp.status, {}
        return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:200]
    except Exception as exc:  # noqa: BLE001
        return "ERR", f"{type(exc).__name__}: {exc}"


def prune(state):
    """Оставляем только слоты за последние KEEP_DAYS дней — переменная маленькая."""
    if not isinstance(state, dict):
        return state
    done = state.get("done") or {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    pruned = {}
    for channel_id, values in done.items():
        keep = []
        for value in values or []:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed >= cutoff:
                keep.append(str(value))
        if keep:
            pruned[channel_id] = keep
    state["done"] = pruned
    return state


def load_files():
    payload = {}
    for key, path in FILES.items():
        if path.exists():
            try:
                payload[key] = prune(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
    return payload


def pull() -> int:
    status, data = api("GET", f"/actions/variables/{VAR}")
    if status != 200 or not isinstance(data, dict):
        print(f"state pull: переменная недоступна ({status}) — работаем на кэше")
        return 0
    raw = str(data.get("value") or "")
    try:
        payload = json.loads(raw)
    except ValueError:
        print("state pull: значение переменной не JSON — пропуск")
        return 0
    written = 0
    for key, path in FILES.items():
        state = payload.get(key)
        if isinstance(state, dict):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            written += 1
    print(f"state pull: записано файлов {written}")
    return 0


def push() -> int:
    payload = load_files()
    if not payload:
        print("state push: нет файлов состояния — пропуск")
        return 0
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode()) > MAX_BYTES:
        print("state push: состояние слишком большое — пропуск")
        return 0
    status, data = api("GET", f"/actions/variables/{VAR}")
    if status == 200:
        status, data = api("PATCH", f"/actions/variables/{VAR}", {"name": VAR, "value": raw})
    else:
        status, data = api("POST", "/actions/variables", {"name": VAR, "value": raw})
    if status in (201, 204):
        print(f"state push: ok ({len(raw.encode())} байт)")
        return 0
    print(f"state push: ошибка {status} {str(data)[:200]}")
    return 0  # не валим публикацию, если синк не удался


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "pull"
    if not token():
        print("state sync: нет ALERT_GITHUB_TOKEN/GITHUB_TOKEN — пропуск")
        sys.exit(0)
    sys.exit(pull() if command == "pull" else push())
