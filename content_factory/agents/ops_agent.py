"""Многофункциональный операционный агент контент-завода.

Схема экономит токены и устойчива к бесплатным лимитам:
1. Детерминированно собирает данные семью инструментами (без LLM).
2. Один LLM-вызов пишет сводку и 3 приоритета по сжатым фактам.
3. Если LLM недоступна (429/503/пусто) — детерминированная сводка без токенов.

Запуск:
    python -m content_factory.agents.ops_agent
    python -m content_factory.agents.ops_agent --send
    python -m content_factory.agents.ops_agent --task "проверь промо"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from ..config import Settings
from ..nlp.llm import FallbackLLMClient, LLMClient, OpenAICompatibleLLM, _build_llm
from ..utils import env
from .tools import call_tool

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASK = (
    "Ежедневный обход: метрики роста, здоровье пайплайна, промо, расход LLM. "
    "Дай короткую сводку и 3 приоритетных действия на сегодня."
)
SYSTEM = (
    "Ты — операционный аналитик контент-завода Telegram-каналов. "
    "По сжатым данным ниже напиши сводку ≤900 символов и ровно 3 приоритетных "
    "действия на день. Только факты и числа из данных, без выдумок. По-русски."
)


def build_client(settings: Settings, model: str = "gemini") -> LLMClient:
    """Gemini-проект №1 → Gemini-проект №2 (своя квота) → Pollinations (без ключа)."""
    chain = [_build_llm(model or "gemini", settings)]
    if model in ("gemini", "") and (env("GEMINI_API_KEY_ALT", "") or "").strip():
        for alt_model in ("gemini-3.5-flash", "gemini-3.6-flash"):
            chain.append(
                OpenAICompatibleLLM(
                    {
                        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                        "api_key_env": "GEMINI_API_KEY_ALT",
                        "model": alt_model,
                        "timeout": 90,
                    }
                )
            )
    chain.append(_build_llm("pollinations", settings))
    usable = [client for client in chain if client.available]
    if not usable:
        return chain[0]
    if len(usable) == 1:
        return usable[0]
    return FallbackLLMClient(usable)


def collect_data(tool_runner: Callable[[str, Dict[str, Any]], Any] = call_tool) -> Dict[str, Any]:
    """Все инструменты один раз; у каждого инструмента своя защита от сбоев."""
    return {
        "channels": tool_runner("channels", {}),
        "growth": tool_runner("growth", {"limit": 10}),
        "health": tool_runner("health", {}),
        "budget": tool_runner("budget", {}),
        "promo": tool_runner("promo", {}),
    }


def compact_data(data: Dict[str, Any], limit: int = 1500) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    return text[:limit]


def analyze(
    client: LLMClient,
    task: str,
    data: Dict[str, Any],
    *,
    max_tokens: int = 700,
) -> str:
    """Один LLM-вызов: сводка по данным. Пустая строка = модель не справилась."""
    prompt = "Задача: {}\n\nСжатые данные (JSON):\n{}".format(task, compact_data(data))
    return client.generate(
        prompt, system=SYSTEM, max_tokens=max_tokens, temperature=0.2, keep_lines=True
    )


def heuristic_summary(
    data: Optional[Dict[str, Any]] = None,
    tool_runner: Callable[[str, Dict[str, Any]], Any] = call_tool,
) -> str:
    """Детерминированная сводка без LLM (токенов не тратит)."""
    if data is None:
        data = collect_data(tool_runner)
    lines = ["📊 Оперативная сводка (без LLM)"]
    channels = data.get("channels")
    if isinstance(channels, list):
        lines.append("Каналов: {}".format(len(channels)))
    health = data.get("health")
    if isinstance(health, list) and health:
        ok = ("success", "completed", "queued", "in_progress", "waiting", "requested", "")
        bad = [run for run in health if str(run.get("status", "")) not in ok]
        lines.append("Запуски Actions: {}, проблемных: {}".format(len(health), len(bad)))
        if bad:
            names = [str(item.get("name")) for item in bad[:3]]
            lines.append("Проблемы: " + ", ".join(names))
    growth = data.get("growth")
    if isinstance(growth, dict) and growth.get("summary"):
        tail = [line for line in str(growth["summary"]).splitlines() if line.strip()][-3:]
        lines.extend(tail)
    promo = data.get("promo")
    if isinstance(promo, dict) and promo.get("outreach_rows") is not None:
        lines.append(
            "ВП-трекер: {} строк, статусы {}".format(
                promo.get("outreach_rows"), promo.get("statuses") or {}
            )
        )
    lines.append("Приоритет: метрики → проблемные запуски → промо.")
    return "\n".join(lines)


def _send_telegram(text: str) -> int:
    script = ROOT / "scripts" / "notify_telegram.py"
    return subprocess.call([sys.executable, str(script), text])


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Операционный агент контент-завода")
    parser.add_argument("--task", default="", help="Свободная задача вместо ежедневной")
    parser.add_argument("--send", action="store_true", help="Отправить итог в Telegram")
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--model", default="gemini")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    task = (args.task or "").strip() or DEFAULT_TASK
    data = collect_data()
    text = ""
    client = build_client(settings, args.model)
    describe = getattr(client, "describe", None)
    if callable(describe):
        print("LLM: " + describe(), file=sys.stderr)
    if client.available:
        text = analyze(client, task, data, max_tokens=args.max_tokens).strip()
        if text:
            print("LLM provider: " + client.name, file=sys.stderr)
    if not text:
        print("LLM недоступна — детерминированная сводка", file=sys.stderr)
        text = heuristic_summary(data)
    print(text)
    if args.send:
        return _send_telegram(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
