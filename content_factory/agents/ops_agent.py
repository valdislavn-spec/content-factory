"""Многофункциональный операционный агент контент-завода.

Лёгкий agent-loop без внешних фреймворков: LLM выбирает инструмент из
компактного реестра, получает короткое наблюдение и в конце отдаёт сводку.
Бюджет токенов ограничен: максимум ``max_steps`` вызовов, ``max_tokens`` 480
на ответ, наблюдения обрезаются. Если LLM недоступна — детерминированная
сводка без единого токена.

Запуск:
    python -m content_factory.agents.ops_agent            # сводка в stdout
    python -m content_factory.agents.ops_agent --send     # ещё и в Telegram
    python -m content_factory.agents.ops_agent --task "проверь промо и метрики"
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..config import Settings
from ..nlp.llm import LLMClient, _build_llm
from .tools import TOOLS, call_tool, tools_prompt

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASK = (
    "Ежедневный обход: собери метрики роста каналов, проверь здоровье пайплайна, "
    "статус промо и расход LLM. Дай короткую сводку и 3 приоритетных действия на сегодня."
)
SYSTEM = (
    "Ты — операционный агент контент-завода Telegram-каналов. "
    "Отвечай ТОЛЬКО валидным JSON без markdown: "
    '{{"action":"<инструмент>","args":{{}}}} либо '
    '{{"action":"finish","args":{{"text":"..."}}}}. '
    "Сначала собери данные инструментами (не больше {max_steps}), затем finish. "
    "Не выдумывай цифры — только из наблюдений. Финальный текст ≤900 символов, "
    "по-русски: ключевые числа, что срочно, 3 приоритетных действия.\n\n"
    "Инструменты:\n{tools}"
)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def build_client(settings: Settings, model: str = "gemini") -> LLMClient:
    """Gemini (бесплатный AI Studio) → Pollinations (без ключа) → что дали."""
    client = _build_llm(model or "gemini", settings)
    if client.available:
        return client
    fallback = _build_llm("pollinations", settings)
    return fallback if fallback.available else client


def run_agent(
    client: LLMClient,
    task: str,
    *,
    max_steps: int = 6,
    max_tokens: int = 480,
    tool_runner: Callable[[str, Dict[str, Any]], Any] = call_tool,
) -> str:
    """Цикл «мысль → инструмент → наблюдение», возвращает финальный текст."""
    observations: List[str] = []
    steps = 0
    system = SYSTEM.format(max_steps=max_steps, tools=tools_prompt())
    for _ in range(max_steps + 1):
        prompt = "Задача: {}\n\nНаблюдения:\n{}".format(
            task, "\n".join(observations) if observations else "(пока нет)"
        )
        raw = client.generate(prompt, system=system, max_tokens=max_tokens, temperature=0.2)
        data = _extract_json(raw)
        if data is None:
            observations.append("ОШИБКА: ответ не JSON. Верни ровно один JSON-объект.")
            continue
        action = str(data.get("action") or "").strip()
        args = data.get("args") if isinstance(data.get("args"), dict) else {}
        if action == "finish":
            text = str(args.get("text") or "").strip()
            if text:
                return text
            observations.append("ОШИБКА: пустой finish.text")
            continue
        if action not in TOOLS:
            observations.append("ОШИБКА: неизвестный инструмент {!r}".format(action))
            continue
        result = tool_runner(action, args)
        observations.append(
            "{} -> {}".format(action, json.dumps(result, ensure_ascii=False)[:900])
        )
        steps += 1
        if steps >= max_steps:
            break
    return heuristic_summary(tool_runner)


def heuristic_summary(
    tool_runner: Callable[[str, Dict[str, Any]], Any] = call_tool,
) -> str:
    """Детерминированная сводка без LLM (токенов не тратит)."""
    lines = ["📊 Оперативная сводка (без LLM)"]
    channels = tool_runner("channels", {})
    if isinstance(channels, list):
        lines.append("Каналов: {}".format(len(channels)))
    health = tool_runner("health", {})
    if isinstance(health, list) and health:
        bad = [run for run in health if str(run.get("status")) not in ("success", "completed")]
        lines.append("Последние запуски Actions: {}, проблемных: {}".format(len(health), len(bad)))
        if bad:
            lines.append("Проблемы: " + ", ".join(str(item.get("name")) for item in bad[:3]))
    budget = tool_runner("budget", {})
    if isinstance(budget, dict) and budget.get("tokens"):
        tokens = budget["tokens"]
        lines.append(
            "Токены: {}/{}".format(tokens.get("total"), tokens.get("limit") or "—")
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
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=480)
    parser.add_argument("--model", default="gemini")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    task = (args.task or "").strip() or DEFAULT_TASK
    client = build_client(settings, args.model)
    if client.available:
        text = run_agent(client, task, max_steps=args.max_steps, max_tokens=args.max_tokens)
    else:
        text = heuristic_summary()
    print(text)
    if args.send:
        return _send_telegram(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
