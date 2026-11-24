"""Партнёрские блоки в автопостах: 1 блок на N постов канала.

Ссылки берутся из `config/affiliates.yaml` (реестр программ + привязка к каналам),
готовый блок рисует `content_factory.affiliates.render_block`. Счётчик постов
хранится в `data/affiliate/autopost_state.json`, чтобы блок не выпадал на каждом
посте и программа ротировалась.

Встраивается в `publishers/telegram.py` — значит работает для всех автопостов,
которые идут через общий пайплайн. Отключается переменной окружения
`AFFILIATE_AUTOPOST=0`.

CLI (предпросмотр без сети):

    python3 -m content_factory.affiliate_inject --channel ai-news --index 5
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .affiliates import AffiliateError, AffiliateRotator, load_registry, render_block

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "affiliates.yaml"
STATE_PATH = ROOT / "data" / "affiliate" / "autopost_state.json"
ENV_FLAG = "AFFILIATE_AUTOPOST"

MARKERS = ("🤝 Партнёры", "🤝 Partners")


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "1").strip().lower() not in {"0", "false", "no", "off"}


def _load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"channels": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"channels": {}}
    if not isinstance(data, dict) or not isinstance(data.get("channels"), dict):
        return {"channels": {}}
    return data


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_index(channel_id: str, state_path: Path = STATE_PATH) -> int:
    """Атомарно увеличить счётчик постов канала и вернуть номер текущего поста."""
    state = _load_state(state_path)
    counter = int((state["channels"].get(channel_id) or {}).get("posts", 0)) + 1
    state["channels"].setdefault(channel_id, {})["posts"] = counter
    _save_state(state_path, state)
    return counter


def peek_index(channel_id: str, state_path: Path = STATE_PATH) -> int:
    state = _load_state(state_path)
    return int((state["channels"].get(channel_id) or {}).get("posts", 0))


def build_block(
    channel_id: str,
    *,
    registry_path: Path = REGISTRY_PATH,
    language: Optional[str] = None,
    program_id: Optional[str] = None,
) -> Dict[str, str]:
    registry = load_registry(registry_path)
    return render_block(registry, channel_id, program_id, language=language)


def maybe_inject(
    text: str,
    channel_id: str,
    *,
    registry_path: Path = REGISTRY_PATH,
    state_path: Path = STATE_PATH,
    language: Optional[str] = None,
    force: bool = False,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Дописать партнёрский блок к посту, если по правилу 1:N пора.

    Возвращает (новый текст, метаданные блока). При любой проблеме с реестром
    пост уходит без изменений — публикация не должна падать из-за affiliate.
    """
    if not text or not enabled():
        return text, None
    if any(marker in text for marker in MARKERS):
        return text, None
    try:
        registry = load_registry(registry_path)
        rotator = AffiliateRotator(registry, channel_id)
    except AffiliateError as exc:
        logger.debug("affiliate: пропускаю канал %s (%s)", channel_id, exc)
        return text, None

    index = next_index(channel_id, state_path)
    program = rotator.for_post(index) if not force else (registry.ready_programs(channel_id) or [None])[0]
    if program is None:
        return text, None
    try:
        block = render_block(registry, channel_id, program.id, language=language)
    except AffiliateError as exc:
        logger.warning("affiliate: блок не собран для %s: %s", channel_id, exc)
        return text, None

    combined = f"{text.rstrip()}\n\n{block['html']}"
    meta = {
        "channel": channel_id,
        "index": index,
        "every": rotator.every,
        "program": block["program"],
        "url": block["url"],
        "disclosure": block["disclosure"],
    }
    return combined, meta


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Предпросмотр партнёрского блока для автопоста")
    parser.add_argument("--channel", required=True, help="id канала из config/affiliates.yaml")
    parser.add_argument("--index", type=int, default=5, help="номер поста (1-based)")
    parser.add_argument("--program", default="", help="конкретная программа (по умолчанию — ротация)")
    parser.add_argument("--language", default="", help="en|es")
    args = parser.parse_args(argv)

    registry = load_registry(REGISTRY_PATH)
    rotator = AffiliateRotator(registry, args.channel)
    if args.program:
        block = render_block(registry, args.channel, args.program, language=args.language or None)
    else:
        program = rotator.for_post(args.index)
        if program is None:
            print(f"  пост #{args.index} в {args.channel} — без блока (правило 1:{rotator.every})")
            return 0
        block = render_block(registry, args.channel, program.id, language=args.language or None)
    print(f"  канал {args.channel} · пост #{args.index} · программа {block['program']}")
    print(f"  url: {block['url']}")
    print("  ---")
    print(block["html"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
