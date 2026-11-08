#!/usr/bin/env python3
"""Публикация стартовых постов в Mastodon из config/mastodon_queue.yaml.

    python scripts/mastodon_publish.py            # dry-run (по умолчанию)
    python scripts/mastodon_publish.py --apply    # реальная публикация

Креды: MASTODON_BASE_URL / MASTODON_TOKEN (или per-channel
MASTODON_BASE_URL_<CHANNEL_ID> / MASTODON_TOKEN_<CHANNEL_ID>).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_channels  # noqa: E402
from content_factory.publishers.social import env_for_channel  # noqa: E402

MAX_TEXT = 500
QUEUE_FILE = ROOT / "config" / "mastodon_queue.yaml"


def load_queue(path: Path = QUEUE_FILE) -> List[Dict[str, Any]]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    posts = data.get("posts") or []
    result: List[Dict[str, Any]] = []
    for item in posts:
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError("пустой текст поста в очереди")
        if len(text) > MAX_TEXT:
            raise ValueError(
                f"пост длиннее {MAX_TEXT} символов ({len(text)}): {text[:60]!r}…"
            )
        result.append(
            {
                "channel": str(item.get("channel") or "").strip(),
                "language": str(item.get("language") or "en"),
                "visibility": str(item.get("visibility") or "public"),
                "text": text,
            }
        )
    return result


def channels_map(settings: Settings) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for path in ("config/channels.en.yaml", "config/channels.es.yaml"):
        try:
            for channel in load_channels(settings, path=str(ROOT / path)):
                mapping[channel.id] = channel
        except Exception:  # noqa: BLE001 - отсутствующий набор не критичен
            continue
    return mapping


def post_status(base: str, token: str, text: str, visibility: str, language: str,
                timeout: int = 30) -> Dict[str, Any]:
    body = urllib.parse.urlencode(
        {"status": text, "visibility": visibility, "language": language}
    ).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + "/api/v1/statuses",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "factory-mastodon-poster/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"Mastodon HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Mastodon недоступен: {exc}") from exc


def run(apply: bool, only_channel: str = "", delay: float = 0.0) -> int:
    settings = Settings.load()
    channels = channels_map(settings)
    queue = load_queue()
    if only_channel:
        queue = [item for item in queue if item["channel"] == only_channel]
    if not queue:
        print("Очередь пуста.")
        return 0
    sent, skipped, failed = 0, 0, 0
    for index, item in enumerate(queue, start=1):
        channel = channels.get(item["channel"])
        title = f"[{index}/{len(queue)}] {item['channel']} ({len(item['text'])} симв.)"
        if channel is None:
            print(f"{title}: пропуск — канал не найден")
            skipped += 1
            continue
        base = env_for_channel(channel, "MASTODON_BASE_URL")
        token = env_for_channel(channel, "MASTODON_TOKEN")
        if not apply:
            print(f"{title}: dry-run — {item['text'].splitlines()[0][:70]}")
            continue
        if not base or not token:
            print(f"{title}: пропуск — нет MASTODON_BASE_URL/MASTODON_TOKEN для {channel.id}")
            skipped += 1
            continue
        try:
            data = post_status(base, token, item["text"], item["visibility"], item["language"])
        except RuntimeError as exc:
            print(f"{title}: ошибка — {exc}")
            failed += 1
            continue
        print(f"{title}: опубликовано {data.get('url') or data.get('uri') or data.get('id')}")
        sent += 1
        if delay:
            time.sleep(delay)
    if apply:
        print(f"\nИтого: опубликовано {sent}, пропущено {skipped}, ошибок {failed}")
        return 0 if failed == 0 else 1
    print(f"\nDry-run: {len(queue)} постов готово к публикации (запустите с --apply).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="публиковать (без флага — dry-run)")
    parser.add_argument("--channel", default="", help="только один канал, например ai-news")
    parser.add_argument("--delay", type=float, default=0.0, help="пауза между постами, сек")
    args = parser.parse_args()
    try:
        return run(args.apply, args.channel, args.delay)
    except ValueError as exc:
        print(f"Ошибка очереди: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
