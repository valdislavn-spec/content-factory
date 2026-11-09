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


def llm_usage_line() -> str:
    """Расход бесплатных LLM-провайдеров за текущие сутки (UTC)."""
    from pathlib import Path

    limits = {
        "cloudflare": 100,
        "cohere": 30,
        "ollama_cloud": 250,
        "deepseek_chat": 120,
        "openrouter": 50,
    }
    parts = []
    warnings = []
    for provider, limit in limits.items():
        path = Path("data") / f"llm_usage_{provider}.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        count = int(data.get("count") or 0)
        parts.append(f"{provider} {count}/{limit}")
        if limit and count >= limit * 0.9:
            warnings.append(provider)
    tokens_line = ""
    tokens_path = Path("data") / "llm_tokens.json"
    if tokens_path.is_file():
        try:
            tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
            calls = int(tokens.get("calls") or 0)
            prompt = int(tokens.get("prompt_tokens") or 0)
            completion = int(tokens.get("completion_tokens") or 0)
            tokens_line = f" · токены: {calls} вызовов, {prompt}+{completion}"
        except (OSError, ValueError):
            tokens_line = ""
    if not parts:
        return "LLM: нет данных (кэш состояния не восстановлен)"
    line = "LLM за сутки: " + " · ".join(parts) + tokens_line
    if warnings:
        line += " ⚠️ близко к лимиту: " + ", ".join(sorted(warnings))
    return line


def travelpayouts_line() -> str:
    """Баланс Travelpayouts + число подключённых программ."""
    try:
        import yaml
    except Exception:
        pass
    token = os.environ.get("TRAVELPAYOUTS_API_TOKEN", "").strip()
    if not token:
        return "Travelpayouts: нет токена"
    programs = 0
    try:
        import yaml

        data = yaml.safe_load(open("config/affiliate_links.yaml", encoding="utf-8")) or {}
        programs = len((data.get("programs") or {}))
    except Exception:  # noqa: BLE001
        programs = 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from content_factory.integrations.travelpayouts import TravelpayoutsClient

        client = TravelpayoutsClient(
            token=token,
            marker=os.environ.get("TRAVELPAYOUTS_MARKER", "").strip(),
            trs=os.environ.get("TRAVELPAYOUTS_TRS", "597672"),
        )
        balance = client.balance().get("usd", "0")
        payout = client.next_payout().get("usd", "0")
        return "Travelpayouts: $" + str(balance) + " · к выплате $" + str(payout) + " · программ " + str(programs)
    except Exception as error:  # noqa: BLE001
        return "Travelpayouts: ошибка " + type(error).__name__


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
    lines.append(llm_usage_line())
    lines.append(travelpayouts_line())
    text = "\n".join(lines)
    print(text)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_telegram.py")
    return subprocess.call([sys.executable, script, text])


if __name__ == "__main__":
    sys.exit(main())
