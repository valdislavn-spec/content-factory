"""Загрузка и валидация конфигурации проекта.

Конфигурация: config/settings.yaml (общие настройки) + config/channels.yaml
(6 каналов: темы, источники, расписание). Все секреты берутся из .env или
переменных окружения — в YAML они не хранятся.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import ChannelConfig, SourceConfig
from .utils import ConfigError, env, load_dotenv, parse_hhmm

try:  # PyYAML — единственная обязательная внешняя зависимость
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ConfigError(
        "Не установлен PyYAML. Выполните: python -m pip install -r requirements.txt"
    ) from exc


# Значения по умолчанию: пользователю достаточно поправить пару строк.
DEFAULT_SETTINGS: Dict[str, Any] = {
    "app": {
        "data_dir": "data",
        "db_path": "data/factory.sqlite3",
        "outbox_dir": "data/outbox",
        "reports_dir": "data/reports",
        "logs_dir": "data/logs",
        "log_level": "INFO",
        "timezone_offset": 3,
        "dry_run": True,
        "language": "ru",
        "channels_file": "config/channels.yaml",
        "user_agent": (
            "Mozilla/5.0 (compatible; ContentFactory/1.0; "
            "+https://t.me/) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"
        ),
        "request_timeout": 20,
        "request_retries": 2,
        "daemon_interval_sec": 60,
    },
    "pipeline": {
        "lookback_hours": 30,
        "max_articles_per_channel": 150,
        "cluster_similarity": 0.34,
        "min_cluster_sources": 1,
        "max_posts_per_run": 2,
        "post_generator": "internal",  # internal | dify_app
        "dify_post_app": "posts",      # ключ из integrations.dify_apps
        "min_relevance": 0.22,
        "min_cluster_chars": 200,
        "max_text_chars": 15000,
        "post_duplicate_window_hours": 72,
        "min_post_chars": 220,
        "banned_words": [
            "гарантированный доход",
            "100% заработок",
            "крипто-сигнал",
        ],
        "cta": "",
    },
    "llm": {
        # extractive | ollama | openai_compatible | gigachat | yandexgpt | dify
        "provider": "extractive",
        "timeout": 120,
        "max_tokens": 700,
        "temperature": 0.3,
        "daily_request_limit": 0,  # 0 = без лимита; >0 — запросов к LLM в сутки (UTC)
        "fallback": [],  # например ["openrouter", "sambanova", "openai", "dify"]
        "providers": {},  # именованные OpenAI-совместимые провайдеры
        "ollama": {
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen3.5:9b",
            "num_ctx": 8192,
        },
        "openai_compatible": {
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "qwen3.5:9b",
            "api_key_env": "OPENAI_COMPAT_API_KEY",
        },
        "gigachat": {
            "base_url": "https://gigachat.devices.sberbank.ru/api/v1",
            "oauth_url": "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            "model": "GigaChat",
            "credentials_env": "GIGACHAT_CREDENTIALS",
            "scope": "GIGACHAT_API_PERS",
        },
        "yandexgpt": {
            "base_url": "https://llm.api.cloud.yandex.net/foundationModels/v1",
            "model": "yandexgpt-lite/latest",
            "api_key_env": "YANDEXGPT_API_KEY",
            "folder_id_env": "YANDEX_FOLDER_ID",
        },
        "dify": {
            "base_url": "https://api.dify.ai/v1",
            "app_mode": "chat",
            "api_key_env": "DIFY_API_KEY",
            "user": "content-factory",
            "include_system": True,
            "inputs": {},
        },
    },
    "integrations": {
        "dify_apps": {
            "posts": {
                "api_key_env": "DIFY_POSTS_API_KEY",
                "timeout": 180,
                "daily_limit": 20,
                "output_key": "",
                "outputs": {
                    "text": "result",
                    "image_url": "image_url",
                    "source_url": "source_url",
                },
                "inputs": {"channel": "{channel}", "topic": "{topic}"},
            },
            "news": {"api_key_env": "DIFY_NEWS_API_KEY", "timeout": 180},
            "trends": {"api_key_env": "DIFY_TRENDS_API_KEY", "timeout": 120},
            "seo": {"api_key_env": "DIFY_SEO_API_KEY", "timeout": 120},
        },
    },
    "publishers": {
        "telegram": {
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
            "parse_mode": "HTML",
            "disable_preview": False,
        },
        "vk": {
            "access_token_env": "VK_ACCESS_TOKEN",
            "group_id_env": "VK_GROUP_ID",
            "api_version": "5.199",
        },
        "dryrun": {"enabled": True},
    },
    "analytics": {
        "enabled": True,
        "report_title": "Контент-завод: аналитика",
        "collect_subscribers": True,
        "retention_days": 180,
    },
}

CHANNEL_DEFAULTS: Dict[str, Any] = {
    "description": "",
    "topics": [],
    "exclude_keywords": [],
    "schedule": ["09:00", "18:00"],
    "timezone_offset": 3,
    "posts_per_day": 2,
    "tone": "expert",
    "max_post_chars": 3500,
    "min_relevance": 0.25,
    "formats": ["digest", "story", "analysis"],
    "content_mix": {"story": 30, "analysis": 40, "interactive": 30},
    "night_max_chars": 900,
    "night_window": "23:00-07:00",
    "hashtags": [],
    "cta": "",
    "telegram_chat_id": "",
    "publisher_ids": ["telegram"],
    "enabled": True,
    "emoji": True,
    "language": "ru",
    "sources": [],
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def project_root() -> Path:
    """Корень проекта: каталог, содержащий config/, content_factory/, data/."""
    env_root = os.environ.get("CONTENT_FACTORY_HOME")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """Обёртка над settings.yaml с путями и удобными геттерами."""

    root: Path
    raw: Dict[str, Any]
    settings_path: Path
    channels_path: Path

    @classmethod
    def load(
        cls,
        root: Optional[Any] = None,
        settings_path: Optional[Any] = None,
        load_env: bool = True,
    ) -> "Settings":
        root_path = Path(root).resolve() if root else project_root()
        if load_env:
            load_dotenv(root_path / ".env")
        settings_file = Path(settings_path) if settings_path else root_path / "config" / "settings.yaml"
        settings_file = settings_file if settings_file.is_absolute() else root_path / settings_file
        data = _load_yaml(settings_file)
        if not isinstance(data, dict):
            raise ConfigError(f"Файл настроек пуст или некорректен: {settings_file}")
        merged = _deep_merge(DEFAULT_SETTINGS, data)
        _validate_settings(merged)
        # Список каналов: env-переменная важнее settings.yaml (удобно для daemon/systemd).
        channels_value = env("CONTENT_FACTORY_CHANNELS", "") or str(
            merged.get("app", {}).get("channels_file") or ""
        )
        channels_file = root_path / "config" / "channels.yaml"
        if channels_value:
            candidate = Path(channels_value)
            channels_file = candidate if candidate.is_absolute() else root_path / candidate
        return cls(
            root=root_path,
            raw=merged,
            settings_path=settings_file,
            channels_path=channels_file,
        )

    # ---- доступ к секциям ----
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def app(self) -> Dict[str, Any]:
        return self.raw.get("app", {})

    @property
    def pipeline(self) -> Dict[str, Any]:
        return self.raw.get("pipeline", {})

    @property
    def llm(self) -> Dict[str, Any]:
        return self.raw.get("llm", {})

    @property
    def publishers(self) -> Dict[str, Any]:
        return self.raw.get("publishers", {})

    @property
    def analytics(self) -> Dict[str, Any]:
        return self.raw.get("analytics", {})

    # ---- пути ----
    def _path(self, key: str) -> Path:
        value = Path(str(self.app.get(key, "")))
        return value if value.is_absolute() else (self.root / value)

    @property
    def data_dir(self) -> Path:
        return self._path("data_dir")

    @property
    def db_path(self) -> Path:
        return self._path("db_path")

    @property
    def outbox_dir(self) -> Path:
        return self._path("outbox_dir")

    @property
    def reports_dir(self) -> Path:
        return self._path("reports_dir")

    @property
    def logs_dir(self) -> Path:
        return self._path("logs_dir")

    @property
    def dry_run(self) -> bool:
        # Переменная окружения позволяет быстро переключить режим на сервере.
        override = env("CONTENT_FACTORY_DRY_RUN")
        if override is not None:
            return override.strip().lower() in ("1", "true", "yes", "on", "да")
        return bool(self.app.get("dry_run", True))

    @property
    def timezone_offset(self) -> int:
        return int(self.app.get("timezone_offset", 3))

    @property
    def user_agent(self) -> str:
        return str(self.app.get("user_agent", ""))

    @property
    def request_timeout(self) -> float:
        return float(self.app.get("request_timeout", 20))

    @property
    def request_retries(self) -> int:
        return int(self.app.get("request_retries", 2))

    def channel_env_chat_id(self, channel_id: str) -> str:
        """TELEGRAM_CHAT_ID_<CHANNEL> — чтобы не хранить id каналов в git."""
        suffix = "".join(ch if ch.isalnum() else "_" for ch in channel_id).upper()
        return env(f"TELEGRAM_CHAT_ID_{suffix}", "") or ""

    def ensure_dirs(self) -> None:
        for directory in (self.data_dir, self.outbox_dir, self.reports_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Не найден файл конфигурации: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Ошибка YAML в {path}: {exc}") from exc


def _validate_settings(settings: Dict[str, Any]) -> None:
    llm_section = settings.get("llm", {}) or {}
    provider = llm_section.get("provider", "extractive")
    named_providers = set((llm_section.get("providers") or {}).keys())
    allowed = {
        "extractive", "ollama", "openai_compatible", "gigachat", "yandexgpt", "dify",
        "groq", "openrouter", "sambanova", "huggingface", "openai",
    } | named_providers
    if provider not in allowed:
        raise ConfigError(
            f"llm.provider={provider!r} неизвестен. Допустимо: {', '.join(sorted(allowed))}"
        )
    dify_mode = settings.get("llm", {}).get("dify", {}).get("app_mode", "chat")
    if dify_mode not in ("chat", "completion"):
        raise ConfigError(
            "llm.dify.app_mode должен быть 'chat' (Chatbot/Agent/Chatflow) "
            "или 'completion' (Text Generator)"
        )
    offset = settings.get("app", {}).get("timezone_offset", 3)
    if not isinstance(offset, int) or not (-12 <= offset <= 14):
        raise ConfigError("app.timezone_offset должен быть целым числом от -12 до 14")


def load_channels(
    settings: Optional[Settings] = None,
    path: Optional[Any] = None,
) -> List[ChannelConfig]:
    """Загружает config/channels.yaml и валидирует все 6 каналов."""
    settings = settings or Settings.load()
    channels_file = Path(path) if path else settings.channels_path
    if not channels_file.is_absolute():
        channels_file = settings.root / channels_file
    data = _load_yaml(channels_file)
    if isinstance(data, list):
        raw_channels = data
    elif isinstance(data, dict):
        raw_channels = data.get("channels", [])
    else:
        raw_channels = []
    if not isinstance(raw_channels, list) or not raw_channels:
        raise ConfigError(f"В {channels_file} не найден список channels")

    channels: List[ChannelConfig] = []
    errors: List[str] = []
    seen_ids = set()
    for index, raw in enumerate(raw_channels, start=1):
        try:
            channel = _parse_channel(raw, index, settings)
            if channel.id in seen_ids:
                raise ConfigError(f"повторяющийся id канала: {channel.id}")
            seen_ids.add(channel.id)
            channels.append(channel)
        except (ConfigError, TypeError, ValueError) as exc:
            errors.append(f"канал #{index}: {exc}")
    if errors:
        raise ConfigError("Ошибки в config/channels.yaml:\n- " + "\n- ".join(errors))
    return channels


def _parse_channel(raw: Any, index: int, settings: Settings) -> ChannelConfig:
    if not isinstance(raw, dict):
        raise ConfigError("ожидался объект с полями id/title/...")
    data = copy.deepcopy(CHANNEL_DEFAULTS)
    data.update(raw)
    channel_id = str(data.get("id") or "").strip()
    if not channel_id:
        raise ConfigError("не указан id канала (латиница, например tech-ai)")
    if not re_valid_id(channel_id):
        raise ConfigError(f"id канала {channel_id!r} должен содержать только латиницу, цифры, '-' и '_'")

    title = str(data.get("title") or "").strip()
    if not title:
        raise ConfigError("не указан title канала")

    topics = data.get("topics") or []
    if not isinstance(topics, list) or not [str(t).strip() for t in topics if str(t).strip()]:
        raise ConfigError("нужен непустой список topics (ключевые слова темы)")

    schedule = data.get("schedule") or []
    if not isinstance(schedule, list) or not schedule:
        raise ConfigError("нужен schedule — список времён публикации, например ['09:00', '18:00']")
    for slot in schedule:
        parse_hhmm(str(slot))

    formats = [str(f).lower() for f in (data.get("formats") or ["story"])]
    allowed_formats = {"digest", "story", "analysis", "interactive"}
    bad_formats = set(formats) - allowed_formats
    if bad_formats:
        raise ConfigError(f"неизвестные форматы постов: {', '.join(sorted(bad_formats))}")

    raw_sources = data.get("sources") or []
    if not isinstance(raw_sources, list):
        raise ConfigError("sources должен быть списком источников")
    sources: List[SourceConfig] = []
    for src_index, src in enumerate(raw_sources, start=1):
        if not isinstance(src, dict):
            raise ConfigError(f"источник #{src_index} должен быть объектом")
        src_id = str(src.get("id") or f"source-{src_index}").strip()
        src_type = str(src.get("type") or "rss").strip().lower()
        if src_type not in ("rss", "web", "telegram", "worldnews", "newsdata", "currents", "espn"):
            raise ConfigError(
                f"источник {src_id}: неизвестный type={src_type!r} "
                "(rss/web/telegram/worldnews/newsdata/currents/espn)"
            )
        url = str(src.get("url") or "").strip()
        if src_type != "telegram" and not url:
            raise ConfigError(f"источник {src_id}: нужен url")
        if src_type == "telegram" and not url:
            raise ConfigError(f"источник {src_id}: для telegram нужен url вида https://t.me/channel")
        options = src.get("options") or {}
        if not isinstance(options, dict):
            raise ConfigError(f"источник {src_id}: options должен быть объектом")
        sources.append(
            SourceConfig(
                id=src_id,
                type=src_type,
                url=url,
                name=str(src.get("name") or src_id),
                weight=float(src.get("weight", 1.0)),
                enabled=bool(src.get("enabled", True)),
                options=options,
            )
        )
    if not any(s.enabled for s in sources):
        raise ConfigError("нет ни одного включённого источника (enabled: true)")

    chat_id = str(data.get("telegram_chat_id") or "").strip()
    chat_id = settings.channel_env_chat_id(channel_id) or chat_id

    return ChannelConfig(
        id=channel_id,
        title=title,
        description=str(data.get("description") or ""),
        topics=[str(t).strip() for t in topics],
        exclude_keywords=[str(t).strip() for t in (data.get("exclude_keywords") or [])],
        sources=sources,
        schedule=[str(s) for s in schedule],
        timezone_offset=int(data.get("timezone_offset", settings.timezone_offset)),
        posts_per_day=int(data.get("posts_per_day", len(schedule))),
        tone=str(data.get("tone") or "expert"),
        max_post_chars=int(data.get("max_post_chars", 3500)),
        min_relevance=float(data.get("min_relevance", settings.pipeline.get("min_relevance", 0.25))),
        formats=formats,
        content_mix=data.get("content_mix") or {"story": 30, "analysis": 40, "interactive": 30},
        night_max_chars=int(data.get("night_max_chars", 900)),
        night_window=str(data.get("night_window") or "23:00-07:00"),
        hashtags=[str(t) for t in (data.get("hashtags") or [])],
        cta=str(data.get("cta") or ""),
        telegram_chat_id=chat_id,
        publisher_ids=[str(p) for p in (data.get("publisher_ids") or ["telegram"])],
        enabled=bool(data.get("enabled", True)),
        emoji=bool(data.get("emoji", True)),
        language=str(data.get("language") or "ru"),
        meta={"raw": raw},
    )


def re_valid_id(value: str) -> bool:
    return bool(value) and all(ch.isalnum() or ch in "-_" for ch in value)
