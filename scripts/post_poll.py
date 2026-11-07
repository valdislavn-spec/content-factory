#!/usr/bin/env python3
"""Опрос в Telegram-канале: честная вовлечённость вместо покупных реакций.

Публикует анонимный опрос (sendPoll) и умеет снимать результаты (stopPoll).
Bot API ходит через TELEGRAM_API_BASE (прокси), как остальные скрипты завода.

Примеры:
    python scripts/post_poll.py --channel crypto-news \
        --question "What matters most for BTC next week?" \
        --options "ETF flows,Halving,Regulation,Macro"

    # узнать результаты и остановить опрос (по message_id из ответа)
    python scripts/post_poll.py --channel crypto-news --check 6004
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_network_channels
from content_factory.utils import env


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Опрос в Telegram-канале через Bot API")
    parser.add_argument("--channel", required=True, help="id канала из config (например crypto-news)")
    parser.add_argument("--question", default="", help="вопрос опроса (до 300 символов)")
    parser.add_argument(
        "--options",
        default="",
        help="варианты ответа через запятую (2–10), например: ETF,Halving,Regulation",
    )
    parser.add_argument("--check", type=int, default=0, help="message_id опроса: снять результаты (stopPoll)")
    parser.add_argument("--dry-run", action="store_true", help="только показать, не отправлять")
    return parser.parse_args(argv)


def bot_call(method: str, **params: Any) -> Any:
    base = (env("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    token = env("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан")
    url = base + "/bot" + token + "/" + method
    data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(
        url, data=data, headers={"User-Agent": "ContentFactory/1.0"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit("Bot API HTTP %s: %s" % (exc.code, exc.read()[:300]))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SystemExit("Bot API недоступен: %s" % exc)
    if not isinstance(payload, dict) or not payload.get("ok"):
        description = (payload or {}).get("description", "unknown")
        raise SystemExit("Bot API ошибка: %s" % description)
    return payload.get("result")


def resolve_channel(settings: Settings, channel_id: str) -> str:
    for channel in load_network_channels(settings):
        if channel.id == channel_id:
            chat_id = str(channel.telegram_chat_id or "").strip()
            if not chat_id:
                raise SystemExit("у канала %s нет telegram_chat_id" % channel_id)
            return chat_id
    raise SystemExit("канал %s не найден в конфигах" % channel_id)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    settings = Settings.load(load_env=True)
    chat_id = resolve_channel(settings, args.channel)

    if args.check:
        result = bot_call("stopPoll", chat_id=chat_id, message_id=args.check)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    question = args.question.strip()
    options: List[str] = [part.strip() for part in args.options.split(",") if part.strip()]
    if not question or len(question) > 300:
        print("нужен --question до 300 символов", file=sys.stderr)
        return 2
    if not (2 <= len(options) <= 10):
        print("нужно 2–10 вариантов --options", file=sys.stderr)
        return 2
    if args.dry_run:
        print("dry-run: channel=%s chat_id=%s question=%r options=%r" % (args.channel, chat_id, question, options))
        return 0

    result: Dict[str, Any] = bot_call(
        "sendPoll",
        chat_id=chat_id,
        question=question,
        options=json.dumps(options),
        is_anonymous="true",
        allows_multiple_answers="false",
    )
    print(json.dumps(result, ensure_ascii=False, indent=1))
    message_id = (result or {}).get("message_id")
    if message_id:
        print("message_id=%s — результаты: --check %s" % (message_id, message_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
