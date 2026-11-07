#!/usr/bin/env python3
"""Ежедневный heartbeat: состояние последних запусков + сообщение в Telegram."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

API = "https://api.github.com/repos/valdislavn-spec/content-factory"


def gh_runs(token: str):
    req = __import__("urllib.request", fromlist=["Request"]).Request(
        API + "/actions/runs?per_page=30",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "content-factory-heartbeat",
        },
    )
    with __import__("urllib.request", fromlist=["urlopen"]).urlopen(req, timeout=25) as resp:
        return json.load(resp).get("workflow_runs", [])




def subscribers_line() -> str:
    """Подписчики по каналам (Bot API getChatMemberCount)."""
    import os
    import urllib.parse
    import urllib.request

    try:
        import yaml
    except Exception:
        return "Подписчики: нет pyyaml"
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return "Подписчики: нет токена"
    parts = []
    for lang in ("en", "es"):
        path = f"config/channels.{lang}.yaml"
        try:
            data = yaml.safe_load(open(path, encoding="utf-8")) or {}
        except Exception:
            continue
        for channel in data.get("channels") or []:
            chat_id = str(channel.get("telegram_chat_id") or "").strip()
            if not chat_id:
                continue
            try:
                url = f"https://api.telegram.org/bot{token}/getChatMemberCount?chat_id={urllib.parse.quote(chat_id)}"
                with urllib.request.urlopen(url, timeout=20) as resp:
                    data2 = json.load(resp)
                count = data2.get("result")
                label = str(channel.get("title") or channel.get("id"))
                parts.append(f"{label}: {count}")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"{channel.get('id')}: err {type(exc).__name__}")
    return "Подписчики: " + (" · ".join(parts) if parts else "нет данных")


def main() -> int:
    token = os.environ.get("ALERT_GITHUB_TOKEN", "").strip()
    now = datetime.now(timezone.utc)
    lines = [f"✅ content-factory жив · {now.strftime('%d.%m %H:%M')} UTC"]
    if token:
        try:
            runs = gh_runs(token)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"GitHub API: ошибка {type(exc).__name__}")
            runs = []
        cf = [r for r in runs if r.get("name") == "content-factory-cloud-en-es"]
        day = [r for r in cf if r.get("created_at") and datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) > now - timedelta(hours=24)]
        ok = sum(1 for r in day if r.get("conclusion") == "success")
        bad = [r for r in day if r.get("conclusion") == "failure"]
        lines.append(f"За сутки: запусков {len(day)}, успешно {ok}, ошибок {len(bad)}")
        if cf:
            last = cf[0]
            lines.append(f"Последний: {last.get('created_at','?')[:16]} · {last.get('conclusion') or last.get('status')}")
        for r in bad[:3]:
            lines.append(f"❌ {r.get('created_at','?')[:16]} · {r.get('html_url','')}")
    else:
        lines.append("ALERT_GITHUB_TOKEN не задан — статус без деталей")
    lines.append(subscribers_line())
    text = "\n".join(lines)
    print(text)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_telegram.py")
    return subprocess.call([sys.executable, script, text])


if __name__ == "__main__":
    sys.exit(main())
