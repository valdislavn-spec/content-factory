"""LangSmith-трейсинг LangGraph-движка (опция A).

LangSmith — облачный трейсер LangChain/LangGraph: видно каждый узел графа,
промпты, ответы, токены, ошибки и тайминги. Трейсинг опционален и выключен по
умолчанию: включается явно (CLI ``--tracing`` или ``LANGSMITH_TRACING=true``)
и требует API-ключ. Без ключа движок работает как раньше.

Переменные окружения (совместимы со старыми именами LangChain):
``LANGSMITH_API_KEY`` / ``LANGCHAIN_API_KEY``, ``LANGSMITH_PROJECT`` /
``LANGCHAIN_PROJECT``, ``LANGSMITH_ENDPOINT`` / ``LANGCHAIN_ENDPOINT``
(для self-hosted LangSmith).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

TRACING_FLAGS = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
API_KEY_ENVS = ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")
PROJECT_ENVS = ("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT")
ENDPOINT_ENVS = ("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT")
DEFAULT_PROJECT = "mcp-content-factory"


def load_env_file(path: Any) -> int:
    """Прочитать простой ``.env`` (KEY=VALUE) и добавить в os.environ.

    Не перезаписывает уже заданные переменные. Нужен, чтобы ключ LangSmith
    можно было хранить в ``mcp-content-factory/.env`` (файл в ``.gitignore``)
    и не экспортировать вручную. Возвращает число добавленных переменных.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return 0
    added = 0
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or key in os.environ:
            continue
        os.environ[key] = value
        added += 1
    return added


def _first_env(names) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _disable_tracing_env() -> None:
    """Явно выключить трейсинг в окружении (важно при --no-tracing и .env)."""
    for name in TRACING_FLAGS:
        os.environ[name] = "false"


def tracing_requested() -> bool:
    """Включён ли трейсинг флагом окружения (без учёта ключа)."""
    for name in TRACING_FLAGS:
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


def configure_tracing(
    enabled: Optional[bool] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Настроить env для LangSmith и вернуть статус.

    ``enabled=None`` — решает окружение (``LANGSMITH_TRACING``), ``False`` —
    принудительно выключить, ``True`` — включить (нужен ключ). Никогда не
    бросает исключений: трейсинг не должен ломать прогон.
    """
    key = _first_env(API_KEY_ENVS)
    if not key:
        _disable_tracing_env()
        return {
            "enabled": False,
            "reason": "LANGSMITH_API_KEY не задан",
            "hint": "export LANGSMITH_API_KEY=lsv2_... и запустите с --tracing",
        }
    if enabled is None:
        enabled = tracing_requested()
    if not enabled:
        _disable_tracing_env()
        return {
            "enabled": False,
            "reason": "трейсинг выключен (--tracing или LANGSMITH_TRACING=true)",
        }
    used_project = project or _first_env(PROJECT_ENVS) or DEFAULT_PROJECT
    endpoint = _first_env(ENDPOINT_ENVS)

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ.setdefault("LANGCHAIN_API_KEY", key)
    os.environ["LANGSMITH_PROJECT"] = used_project
    os.environ.setdefault("LANGCHAIN_PROJECT", used_project)
    if endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", endpoint)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", endpoint)
    return {"enabled": True, "project": used_project, "endpoint": endpoint or None}
