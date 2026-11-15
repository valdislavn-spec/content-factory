#!/usr/bin/env python3
"""Проверка Discord-webhook: GET, тестовый POST и удаление сообщения.

    python scripts/discord_probe.py --all --sample
    python scripts/discord_probe.py --channel sport-news --sample
    python scripts/discord_probe.py --keep         # не удалять сообщение
    python scripts/discord_probe.py --json         # машинный отчёт

Проверяет все каналы с `discord` в publisher_ids. Для каждого канала сначала
берётся DISCORD_WEBHOOK_URL_<CHANNEL>, затем общий DISCORD_WEBHOOK_URL.
Токен webhook не печатается.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content_factory.config import Settings, load_network_channels  # noqa: E402
from content_factory.models import GeneratedPost  # noqa: E402
from content_factory.publishers.discord import (  # noqa: E402
    BOT_API, BOT_USER_AGENT, DiscordPublisher, _bot_token, _channel_id,
)
from content_factory.publishers.social import channel_suffix, env_for_channel  # noqa: E402

UA = "Mozilla/5.0 (compatible; ContentFactory/1.0)"


def call(url: str, method: str = "GET", payload: dict | None = None,
         headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Content-Type": "application/json", "User-Agent": UA}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url, data=data, method=method, headers=request_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body[:200]}


def _with_query(url: str, **params: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _webhook_id(url: str) -> str:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    return parts[-2] if len(parts) >= 2 else "?"


def _select_channels(settings: Settings, requested: list[str]) -> list:
    channels = [ch for ch in load_network_channels(settings) if "discord" in ch.publisher_ids]
    wanted = {part.strip() for item in requested for part in item.split(",") if part.strip()}
    if not wanted or "all" in wanted:
        return channels
    return [ch for ch in channels if ch.id in wanted]


def _probe_post(channel, sample: bool, message: str) -> GeneratedPost:
    from uuid import uuid4

    if sample:
        text = (
            "<b>Probe: канал жив и готов к автоматизации</b>\n\n"
            "Это тестовое сообщение из content-factory. Оно будет удалено "
            "автоматически.\n\n#Probe #Automation"
        )
    else:
        text = message
    return GeneratedPost(
        id="discord-probe-" + uuid4().hex[:10],
        channel_id=channel.id,
        cluster_id="discord-probe",
        format="story",
        text=text,
        meta={},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка Discord-webhook(ов)")
    parser.add_argument("--channel", action="append", default=[], help="id канала; можно несколько раз или через запятую")
    parser.add_argument("--all", action="store_true", help="все каналы с discord в publisher_ids")
    parser.add_argument("--keep", action="store_true", help="не удалять тестовое сообщение")
    parser.add_argument("--text", default="Content Factory: проверка webhook. Сообщение удалится автоматически.")
    parser.add_argument("--sample", action="store_true", help="отправить образец форматированного поста")
    parser.add_argument("--json", action="store_true", help="машинный JSON-отчёт")
    args = parser.parse_args()

    settings = Settings.load()
    channels = _select_channels(settings, args.channel or (["all"] if args.all else []))
    if not channels:
        print("Нет каналов с publisher_ids, содержащим discord", file=sys.stderr)
        return 2

    reports = []
    seen: dict[str, list[str]] = {}
    bot_token = _bot_token()
    for channel in channels:
        configured_id = _channel_id(channel)
        use_bot = bool(bot_token and configured_id)
        report = {
            "channel_id": channel.id,
            "source": "bot" if use_bot else "webhook",
            "ok": False,
            "detail": "",
        }
        reports.append(report)
        bot_headers = {
            "Authorization": f"Bot {bot_token}",
            "User-Agent": BOT_USER_AGENT,
        }
        if use_bot:
            report["discord_channel_id"] = configured_id
            status, info = call(f"{BOT_API}/channels/{configured_id}", headers=bot_headers)
            if status != 200:
                report["detail"] = f"GET bot channel: HTTP {status}"
                continue
            report["guild_id"] = str(info.get("guild_id") or "")
            report["channel_name"] = str(info.get("name") or "")
            url = ""
        else:
            url = env_for_channel(channel, "DISCORD_WEBHOOK_URL", "").strip()
            has_specific = bool((os.environ.get("DISCORD_WEBHOOK_URL_" + channel_suffix(channel), "") or "").strip())
            report["source"] = "channel" if has_specific else "global"
            if not url.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
                report["detail"] = "DISCORD_WEBHOOK_URL не задан/неверный"
                continue
            report["webhook_id"] = _webhook_id(url)
            seen.setdefault(report["webhook_id"], []).append(channel.id)
            status, info = call(url, "GET")
            if status != 200:
                report["detail"] = f"GET webhook: HTTP {status}"
                continue
            discord_channel_id = str(info.get("channel_id") or "")
            if not discord_channel_id:
                report["detail"] = "GET webhook: нет channel_id"
                continue
            report["discord_channel_id"] = discord_channel_id
            report["guild_id"] = str(info.get("guild_id") or "")
        if report.get("guild_id"):
            widget_status, widget = call(
                f"https://discord.com/api/v10/guilds/{report['guild_id']}/widget.json"
            )
            if widget_status == 200:
                report["guild_name"] = str(widget.get("name") or "")
                report["invite_url"] = str(widget.get("instant_invite") or "")

        publisher = DiscordPublisher(settings)
        result = publisher.publish(
            _probe_post(channel, args.sample, args.text), channel, settings
        )
        if not result.ok:
            report["detail"] = f"publish: {result.error}"
            continue
        message_id = str(result.external_id or "")
        dest = report.get("discord_channel_id") or "?"
        kind = "bot" if use_bot else f"webhook={report.get('webhook_id', '?')}"
        report.update({
            "ok": True,
            "detail": f"{kind}, channel={dest}, message={message_id or 'no-id'}",
            "message_id": message_id,
        })
        if not args.keep and message_id:
            if use_bot:
                status, _ = call(
                    f"{BOT_API}/channels/{dest}/messages/{message_id}",
                    "DELETE", headers=bot_headers,
                )
            else:
                status, _ = call(f"{url.rstrip('/')}/messages/{message_id}", "DELETE")
            if status not in (200, 204):
                report.update({"ok": False, "detail": f"POST ok, DELETE: HTTP {status}"})

    duplicates = {hook: ids for hook, ids in seen.items() if len(ids) > 1}
    for hook, ids in duplicates.items():
        print(f"⚠ Общий webhook {hook} используется каналами {', '.join(ids)}", file=sys.stderr)
    payload = {
        "ok": all(item["ok"] for item in reports),
        "checked": len(reports),
        "failed": sum(1 for item in reports if not item["ok"]),
        "webhooks": len(seen),
        "duplicates": duplicates,
        "results": reports,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in reports:
            print(f"{'✓' if item['ok'] else '✗'} {item['channel_id']}: {item['detail']}")
        print(f"Итого: {payload['checked'] - payload['failed']}/{payload['checked']} OK, webhook'ов: {payload['webhooks']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
