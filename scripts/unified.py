#!/usr/bin/env python3
"""Единый пульт контент-завода: тренды → автопостинг → SEO → рост аудитории.

Команды:

    python scripts/unified.py doctor          # проверка готовности всей системы
    python scripts/unified.py status          # краткая сводка + ближайшие слоты
    python scripts/unified.py trends          # собрать тренды по каналам
    python scripts/unified.py tick            # один тик автопостинга (dry-run по умолчанию)
    python scripts/unified.py tick --publish  # реальная публикация по расписанию
    python scripts/unified.py daily           # trends + tick + growth-report
    python scripts/unified.py brain           # превью LangGraph-мозга из mcp-content-factory

Структура задаётся config/unified.yaml; фактические настройки каналов,
распидения, LLM и публикаторов — в config/settings.yaml и
config/channels*.yaml. Скрипт ничего не переписывает: он только связывает
этапы и проверяет, что всё на месте.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from content_factory.config import Settings, load_network_channels  # noqa: E402
from content_factory.utils import env, load_dotenv  # noqa: E402

UNIFIED_PATH = ROOT / "config" / "unified.yaml"
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
STATUS_ICON = {PASS: "✅", WARN: "⚠️", FAIL: "❌"}


# ---------------------------------------------------------------------------
# Конфиг и вспомогательные функции
# ---------------------------------------------------------------------------


def load_unified(path: Optional[Path] = None) -> Dict[str, Any]:
    """Прочитать config/unified.yaml с понятной ошибкой."""
    file_path = Path(path or UNIFIED_PATH)
    if not file_path.is_file():
        raise FileNotFoundError("нет файла {}".format(file_path))
    data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("{} должен быть объектом YAML".format(file_path))
    return data


def load_all_channels(settings: Settings) -> List[Any]:
    """Все каналы сети (EN + ES), без дублей по id."""
    return load_network_channels(settings)


def next_slots(
    channels: Sequence[Any],
    now: Optional[datetime] = None,
    limit: int = 5,
) -> List[Tuple[datetime, str, str]]:
    """Ближайшие слоты публикаций: (UTC-время, channel_id, HH:MM локального)."""
    current = now or datetime.now(timezone.utc)
    entries: List[Tuple[datetime, str, str]] = []
    for channel in channels:
        offset = int(getattr(channel, "timezone_offset", 3) or 0)
        local_now = current + timedelta(hours=offset)
        for slot in getattr(channel, "schedule", []) or []:
            try:
                hour, minute = [int(part) for part in str(slot).split(":", 1)]
            except (TypeError, ValueError):
                continue
            candidate = local_now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if candidate <= local_now:
                candidate += timedelta(days=1)
            entries.append((candidate - timedelta(hours=offset), channel.id, str(slot)))
    entries.sort(key=lambda item: item[0])
    return entries[: max(1, int(limit))]


TREND_CATEGORY_HINTS = {
    "crypto": ("bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "defi",
               "тейкер", "эфир", "биткоин", "крипт", "solana", "тон", "toncoin"),
    "ai": ("ai", "ии", "openai", "gpt", "llm", "нейросет", "антропик", "anthropic",
           "nvidia", "чип", "machine learning", "model"),
    "sport": ("nfl", "nba", "mlb", "nhl", "футбол", "footbol", "soccer", "real madrid",
              "barcelona", "laliga", "nba", "nfl", "espn", "sport", "спорт", "лига",
              "чемпионат", "гол", "match", "game"),
}


def _contains_hint(text: str, hint: str) -> bool:
    """Подсказка целиком, чтобы «ai» не совпадало с «chairman»."""
    text = str(text or "").lower()
    value = str(hint or "").lower().strip()
    if not value:
        return False
    if len(value) <= 3:
        return re.search(
            r"(?<![0-9a-zа-яё]){}(?![0-9a-zа-яё])".format(re.escape(value)), text
        ) is not None
    return value in text


def match_channels(trend: str, channels: Sequence[Any]) -> List[str]:
    """Определить, каким каналам подходит тренд (по темам канала и подсказкам)."""
    text = str(trend or "").lower()
    matched: List[str] = []
    for channel in channels:
        channel_id = str(getattr(channel, "id", ""))
        if not channel_id or not getattr(channel, "enabled", True):
            continue
        language = str(getattr(channel, "language", "en"))
        score = 0
        for topic in getattr(channel, "topics", []) or []:
            topic_text = str(topic or "").lower().strip()
            if len(topic_text) < 3:
                continue
            if topic_text in text:
                score += 1
        for category, hints in TREND_CATEGORY_HINTS.items():
            if any(_contains_hint(text, hint) for hint in hints):
                if category == "crypto" and ("crypto" in channel_id):
                    score += 2
                elif category == "ai" and ("ai" in channel_id):
                    score += 2
                elif category == "sport" and ("sport" in channel_id or "futbol" in channel_id):
                    score += 2
        if "es" in channel_id and language != "es":
            continue
        if "es" not in channel_id and language == "es":
            continue
        if score > 0:
            matched.append(channel_id)
    return matched


# ---------------------------------------------------------------------------
# doctor: проверка готовности
# ---------------------------------------------------------------------------


def _check(status: str, label: str, detail: str = "") -> Tuple[str, str, str]:
    return (status, label, detail)


def build_doctor_sections(
    settings: Settings,
    channels: Sequence[Any],
    unified: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Собрать секции проверок (без сети) — используется doctor и тестами."""
    sections: List[Dict[str, Any]] = []

    # 1. Конфиг и каналы
    checks = []
    checks.append(_check(PASS, "config/settings.yaml + channels*.yaml загружены"))
    checks.append(
        _check(PASS, "каналов сети: {}".format(len(channels)),
               ", ".join(ch.id for ch in channels))
    )
    total_posts = sum(int(getattr(ch, "posts_per_day", 0) or 0) for ch in channels)
    expected = int((unified.get("pipeline") or {}).get("expected_posts_per_day") or 0)
    checks.append(
        _check(
            PASS if not expected or total_posts == expected else WARN,
            "постов/сутки по расписанию: {}".format(total_posts),
            "ожидалось {}".format(expected) if expected else "",
        )
    )
    # слоты vs posts_per_day
    bad_slots = [
        ch.id
        for ch in channels
        if len(getattr(ch, "schedule", []) or []) != int(getattr(ch, "posts_per_day", 0) or 0)
    ]
    checks.append(
        _check(
            PASS if not bad_slots else WARN,
            "слоты = posts_per_day у всех каналов",
            "расхождение: {}".format(", ".join(bad_slots)) if bad_slots else "",
        )
    )
    sections.append({"title": "1. Каналы и расписание", "checks": checks})

    # 2. LLM: цепочки, лимиты, ключи
    checks = []
    llm = settings.llm or {}
    stage_routes = llm.get("stage_routes") or {}
    checks.append(
        _check(
            PASS if stage_routes else WARN,
            "этапы LLM: {}".format(", ".join(sorted(stage_routes)) or "нет stage_routes"),
        )
    )
    limits = llm.get("provider_limits") or {}
    checks.append(
        _check(
            PASS if limits else WARN,
            "суточные лимиты провайдеров: {}".format(len(limits)),
            ", ".join("{}={}".format(k, v) for k, v in list(limits.items())[:6]),
        )
    )
    providers = llm.get("providers") or {}
    missing_keys = []
    for name, config in providers.items():
        key_env = str((config or {}).get("api_key_env") or "")
        if key_env and not env(key_env, ""):
            missing_keys.append(name)
    checks.append(
        _check(
            PASS if not missing_keys else WARN,
            "ключи провайдеров",
            "нет ключа: {}".format(", ".join(missing_keys)) if missing_keys else "все заданы",
        )
    )
    checks.append(
        _check(PASS, "страховка daily_token_limit",
               str(llm.get("daily_token_limit") or 0))
    )
    sections.append({"title": "2. LLM и автопереключение", "checks": checks})

    # 3. Тренды и SEO
    checks = []
    trends = unified.get("trends") or {}
    checks.append(
        _check(
            PASS if trends.get("enabled", True) else WARN,
            "сбор трендов: {}".format(", ".join(trends.get("sources") or []) or "выкл."),
        )
    )
    seo = unified.get("seo") or {}
    hashtag_channels = [
        ch.id for ch in channels if getattr(ch, "hashtags", None)
    ]
    checks.append(
        _check(
            PASS if len(hashtag_channels) == len(channels) else WARN,
            "SEO-хештеги у каналов: {}/{}".format(len(hashtag_channels), len(channels)),
        )
    )
    landing = ROOT / str(seo.get("landing") or "docs/index.html")
    checks.append(
        _check(
            PASS if landing.is_file() else WARN,
            "лендинг-хаб для SEO/био: {}".format(landing.relative_to(ROOT)),
        )
    )
    checks.append(
        _check(
            PASS if env("INDEXNOW_KEY", "") else WARN,
            "IndexNow (бесплатная индексация лендинга)",
            "INDEXNOW_KEY не задан",
        )
    )
    sections.append({"title": "3. Тренды и SEO", "checks": checks})

    # 4. Рост аудитории
    checks = []
    growth = unified.get("growth") or {}
    cross_path = ROOT / str(growth.get("cross_promo") or "config/cross_promo.yaml")
    cross_enabled = 0
    try:
        cross_data = yaml.safe_load(cross_path.read_text(encoding="utf-8")) or {}
        cross_enabled = sum(
            1 for entry in (cross_data.get("entries") or []) if entry.get("enabled")
        )
        checks.append(
            _check(PASS, "кросс-промо: {} активных связок".format(cross_enabled))
        )
    except (OSError, ValueError) as exc:
        checks.append(_check(WARN, "кросс-промо", str(exc)))
    pinned = ROOT / "config" / "pinned" / "ids.yaml"
    checks.append(
        _check(
            PASS if pinned.is_file() else WARN,
            "закрепы со ссылками на сеть",
            "config/pinned/ids.yaml",
        )
    )
    links_doc = ROOT / str(growth.get("pinned_links") or "docs/promo/link-placement.md")
    checks.append(
        _check(
            PASS if links_doc.is_file() else WARN,
            "реестр площадок для ссылок",
            str(links_doc.relative_to(ROOT)) if links_doc.is_file() else "нет файла",
        )
    )
    checks.append(
        _check(
            PASS if growth.get("link_hub") else WARN,
            "ссылка-хаб для био",
            str(growth.get("link_hub") or ""),
        )
    )
    checks.append(
        _check(
            PASS if env("TELEGRAM_GROWTH_BOT_USERNAME", "") else WARN,
            "growth-бот (deep links / inline)",
            "TELEGRAM_GROWTH_BOT_USERNAME не задан",
        )
    )
    sections.append({"title": "4. Привлечение аудитории", "checks": checks})

    # 5. «Мозг» mcp-content-factory (LangGraph/LangChain/трейсинг)
    checks = []
    brain = unified.get("brain") or {}
    brain_dir = (ROOT / str(brain.get("path") or "../mcp-content-factory")).resolve()
    checks.append(
        _check(
            PASS if brain_dir.is_dir() else WARN,
            "mcp-content-factory",
            str(brain_dir),
        )
    )
    if brain_dir.is_dir():
        python_path = brain_dir / str(brain.get("python") or ".venv/bin/python")
        checks.append(
            _check(
                PASS if python_path.is_file() else WARN,
                "venv мозга",
                str(python_path.relative_to(brain_dir)) if python_path.is_file() else "нет venv",
            )
        )
        if python_path.is_file():
            try:
                result = subprocess.run(
                    [
                        str(python_path),
                        "-c",
                        "import mcp_factory, langgraph, langchain_core; "
                        "print('ok')",
                    ],
                    cwd=str(brain_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                ok = result.returncode == 0
                checks.append(
                    _check(
                        PASS if ok else WARN,
                        "LangGraph/LangChain в мозге",
                        "ok" if ok else result.stderr.strip()[:120],
                    )
                )
            except (OSError, subprocess.SubprocessError) as exc:
                checks.append(_check(WARN, "проверка мозга", str(exc)))
        env_file = brain_dir / ".env"
        has_trace = bool(env("LANGSMITH_API_KEY", "")) or env_file.is_file()
        checks.append(
            _check(
                PASS if has_trace else WARN,
                "LangSmith-трейсинг",
                "ключ есть" if has_trace else "нет LANGSMITH_API_KEY",
            )
        )
    checks.append(
        _check(
            PASS if (brain.get("engine") == "langgraph") else WARN,
            "движок мозга: {}".format(brain.get("engine")),
            "grounding={}, rounds={}".format(
                brain.get("grounding"), brain.get("revision_rounds")
            ),
        )
    )
    sections.append({"title": "5. Мозг: LangGraph + RAG + трейсинг", "checks": checks})

    # 6. Публикация
    checks = []
    checks.append(
        _check(
            PASS if settings.dry_run else WARN,
            "режим публикации: {}".format("dry-run" if settings.dry_run else "LIVE"),
            "dry-run безопасен для проверок",
        )
    )
    checks.append(
        _check(
            PASS if env("TELEGRAM_BOT_TOKEN", "") else WARN,
            "Telegram Bot API",
            "токен задан" if env("TELEGRAM_BOT_TOKEN", "") else "нет TELEGRAM_BOT_TOKEN",
        )
    )
    with_ids = [
        ch.id for ch in channels if getattr(ch, "telegram_chat_id", "")
    ]
    checks.append(
        _check(
            PASS if with_ids else WARN,
            "chat_id каналов: {}/{}".format(len(with_ids), len(channels)),
            "ES-каналы берут id из TELEGRAM_CHAT_ID_*",
        )
    )
    sections.append({"title": "6. Публикация", "checks": checks})
    return sections


def doctor_exit_code(sections: Sequence[Dict[str, Any]]) -> int:
    for section in sections:
        for status, _label, _detail in section.get("checks", []):
            if status == FAIL:
                return 1
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    load_dotenv()
    unified = load_unified(Path(args.config) if args.config else None)
    settings = Settings.load()
    channels = load_all_channels(settings)
    sections = build_doctor_sections(settings, channels, unified)
    for section in sections:
        print("\n{}".format(section["title"]))
        for status, label, detail in section["checks"]:
            icon = STATUS_ICON.get(status, "•")
            line = "  {} {}".format(icon, label)
            if detail:
                line += " — {}".format(detail)
            print(line)
    code = doctor_exit_code(sections)
    print(
        "\nИтог: {}".format(
            "готово к автопостингу" if code == 0 else "есть FAIL — исправьте"
        )
    )
    return code


# ---------------------------------------------------------------------------
# status: сводка и ближайшие слоты
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    load_dotenv()
    unified = load_unified(Path(args.config) if args.config else None)
    settings = Settings.load()
    channels = load_all_channels(settings)
    total = sum(int(getattr(ch, "posts_per_day", 0) or 0) for ch in channels)
    print("Каналов: {} | постов/сутки по расписанию: {}".format(len(channels), total))
    print("Режим: {}".format("dry-run" if settings.dry_run else "LIVE"))
    preview = int((unified.get("pipeline") or {}).get("next_slots_preview") or 5)
    print("\nБлижайшие слоты (UTC):")
    for when, channel_id, slot in next_slots(channels, limit=preview):
        print("  {}  {:20s} (локально {})".format(
            when.strftime("%Y-%m-%d %H:%M"), channel_id, slot
        ))
    return 0


# ---------------------------------------------------------------------------
# trends: сбор трендов по каналам
# ---------------------------------------------------------------------------


def save_trends(payload: Dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def cmd_trends(args: argparse.Namespace) -> int:
    load_dotenv()
    unified = load_unified(Path(args.config) if args.config else None)
    settings = Settings.load()
    channels = load_all_channels(settings)
    if args.channel and args.channel != "all":
        channels = [ch for ch in channels if ch.id == args.channel]
        if not channels:
            print("Нет такого канала: {}".format(args.channel), file=sys.stderr)
            return 1
    from content_factory.trends import collect_trends

    limit = int(args.limit or (unified.get("trends") or {}).get("per_channel_limit") or 3)
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": limit,
        "channels": {},
    }
    print("Сбор трендов (limit={}):".format(limit))
    for channel in channels:
        values = collect_trends(channel, settings, clusters=None, limit=limit)
        payload["channels"][channel.id] = values
        print("\n{} ({})".format(channel.id, channel.title))
        if not values:
            print("  — тренды недоступны (сеть/источники), будет локальная частота")
        for value in values:
            targets = match_channels(value, channels)
            extra = " → {}".format(", ".join(targets)) if targets else ""
            print("  • {}{}".format(value, extra))
    save_path = ROOT / str(
        (unified.get("trends") or {}).get("save_path") or "data/trends/latest.json"
    )
    if not args.no_save:
        path = save_trends(payload, save_path)
        print("\nСохранено: {}".format(path))
    return 0


# ---------------------------------------------------------------------------
# tick: один тик автопостинга по расписанию
# ---------------------------------------------------------------------------


def cmd_tick(args: argparse.Namespace) -> int:
    command = [sys.executable, "-m", "content_factory", "daemon", "--once"]
    env_vars = os.environ.copy()
    env_vars["CONTENT_FACTORY_DRY_RUN"] = "false" if args.publish else "true"
    print(
        "Тик автопостинга ({}): {}".format(
            "LIVE" if args.publish else "dry-run", " ".join(command)
        )
    )
    result = subprocess.run(command, cwd=str(ROOT), env=env_vars)
    return int(result.returncode)


# ---------------------------------------------------------------------------
# daily: тренды + тик + отчёт роста
# ---------------------------------------------------------------------------


def cmd_daily(args: argparse.Namespace) -> int:
    load_dotenv()
    unified = load_unified(Path(args.config) if args.config else None)
    code = 0
    if (unified.get("trends") or {}).get("enabled", True) and not args.skip_trends:
        print("\n== Тренды ==")
        code = cmd_trends(argparse.Namespace(
            config=args.config, channel="all", limit=None, no_save=False
        )) or code
    print("\n== Автопостинг по расписанию ==")
    code = cmd_tick(argparse.Namespace(publish=args.publish)) or code
    report_script = ROOT / "scripts" / "growth_report.py"
    if not args.skip_report and report_script.is_file():
        print("\n== Отчёт роста ==")
        command = [sys.executable, str(report_script), "--quiet"]
        if args.send_report:
            command.append("--send")
        result = subprocess.run(command, cwd=str(ROOT))
        if result.returncode != 0:
            print("Отчёт роста завершился с кодом {}".format(result.returncode))
    return code


# ---------------------------------------------------------------------------
# brain: превью LangGraph-мозга из mcp-content-factory
# ---------------------------------------------------------------------------


def cmd_brain(args: argparse.Namespace) -> int:
    unified = load_unified(Path(args.config) if args.config else None)
    brain = unified.get("brain") or {}
    brain_dir = (ROOT / str(brain.get("path") or "../mcp-content-factory")).resolve()
    python_path = brain_dir / str(brain.get("python") or ".venv/bin/python")
    if not python_path.is_file():
        print(
            "Мозг не настроен: нет {}. Установите окружение mcp-content-factory.".format(
                python_path
            ),
            file=sys.stderr,
        )
        return 1
    out_dir = ROOT / str(brain.get("preview_out") or "data/brain-preview")
    command = [
        str(python_path),
        "-m",
        "mcp_factory",
        "demo",
        "--engine",
        str(brain.get("engine") or "langgraph"),
        "--revision-rounds",
        str(int(brain.get("revision_rounds") or 1)),
        "--out",
        str(out_dir),
    ]
    if brain.get("grounding"):
        command.append("--grounding")
    print("Мозг: {}".format(" ".join(command)))
    result = subprocess.run(command, cwd=str(brain_dir))
    if result.returncode == 0:
        print("Готово. Черновики и run-логи: {}".format(out_dir))
    return int(result.returncode)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unified.py",
        description=(
            "Единый пульт: тренды → автопостинг по расписанию → SEO → рост аудитории. "
            "Структура — config/unified.yaml."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="проверить готовность всей системы")
    p_doctor.add_argument("--config", help="путь к unified.yaml")
    p_doctor.set_defaults(func=cmd_doctor)

    p_status = sub.add_parser("status", help="сводка и ближайшие слоты")
    p_status.add_argument("--config", help="путь к unified.yaml")
    p_status.set_defaults(func=cmd_status)

    p_trends = sub.add_parser("trends", help="собрать тренды по каналам")
    p_trends.add_argument("--config", help="путь к unified.yaml")
    p_trends.add_argument("--channel", default="all", help="id канала или all")
    p_trends.add_argument("--limit", type=int, default=None, help="трендов на канал")
    p_trends.add_argument("--no-save", action="store_true", help="не сохранять JSON")
    p_trends.set_defaults(func=cmd_trends)

    p_tick = sub.add_parser("tick", help="один тик автопостинга по расписанию")
    p_tick.add_argument(
        "--publish", action="store_true", help="реальная публикация (по умолчанию dry-run)"
    )
    p_tick.set_defaults(func=cmd_tick)

    p_daily = sub.add_parser("daily", help="тренды + тик + отчёт роста")
    p_daily.add_argument("--config", help="путь к unified.yaml")
    p_daily.add_argument("--publish", action="store_true", help="реальная публикация")
    p_daily.add_argument("--skip-trends", action="store_true")
    p_daily.add_argument("--skip-report", action="store_true")
    p_daily.add_argument("--send-report", action="store_true", help="отправить сводку в Telegram")
    p_daily.set_defaults(func=cmd_daily)

    p_brain = sub.add_parser("brain", help="превью LangGraph-мозга (mcp-content-factory)")
    p_brain.add_argument("--config", help="путь к unified.yaml")
    p_brain.set_defaults(func=cmd_brain)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - понятная ошибка оператору
        print("Ошибка: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
