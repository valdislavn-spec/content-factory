"""Загрузка и валидация конфигурации завода (JSON)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class ConfigError(RuntimeError):
    """Ошибка конфигурации с понятным сообщением."""


@dataclass
class RouteConfig:
    """Маршрут роли: цепочка провайдер/модель и параметры генерации."""

    role: str
    chain: List[Dict[str, str]] = field(default_factory=list)
    temperature: float = 0.3
    max_tokens: int = 800
    json: bool = False


@dataclass
class ServerConfig:
    """Описание MCP-сервера (stdio)."""

    name: str
    builtin: bool = False
    command: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0


@dataclass
class FactoryConfig:
    """Полная конфигурация запуска."""

    providers: Dict[str, Dict[str, Any]]
    routes: Dict[str, RouteConfig]
    feeds: List[str]
    pipeline: Dict[str, Any]
    servers: Dict[str, ServerConfig]
    budget_tokens: int = 0
    path: Optional[Path] = None

    def pipeline_value(self, key: str, default: Any = None) -> Any:
        return self.pipeline.get(key, default)


def _require_mapping(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError("{} должен быть объектом JSON".format(label))
    return value


def load_config(path: Path) -> FactoryConfig:
    """Прочитать config.json и проверить обязательные поля."""
    path = Path(path)
    if not path.exists():
        raise ConfigError("конфиг не найден: {}".format(path))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ConfigError("конфиг {} — невалидный JSON: {}".format(path, exc)) from exc
    raw = _require_mapping(raw, "корень конфига")

    providers = _require_mapping(raw.get("providers"), "providers")
    if not providers:
        raise ConfigError("providers пуст: нужен хотя бы один провайдер")

    routes_raw = _require_mapping(raw.get("routes"), "routes")
    routes: Dict[str, RouteConfig] = {}
    for role, route_data in routes_raw.items():
        route_data = _require_mapping(route_data, "routes.{}".format(role))
        chain = route_data.get("chain")
        if not isinstance(chain, list) or not chain:
            raise ConfigError("routes.{}: chain должен быть непустым списком".format(role))
        prepared_chain: List[Dict[str, str]] = []
        for index, item in enumerate(chain):
            item = _require_mapping(item, "routes.{}.chain[{}]".format(role, index))
            provider_name = str(item.get("provider", ""))
            model_name = str(item.get("model", ""))
            if not provider_name or not model_name:
                raise ConfigError(
                    "routes.{}.chain[{}]: нужны provider и model".format(role, index)
                )
            if provider_name not in providers:
                raise ConfigError(
                    "routes.{}.chain[{}]: провайдер {!r} не объявлен в providers".format(
                        role, index, provider_name
                    )
                )
            prepared_chain.append({"provider": provider_name, "model": model_name})
        routes[role] = RouteConfig(
            role=role,
            chain=prepared_chain,
            temperature=float(route_data.get("temperature", 0.3)),
            max_tokens=int(route_data.get("max_tokens", 800)),
            json=bool(route_data.get("json", False)),
        )

    feeds = raw.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        raise ConfigError("feeds должен быть непустым списком URL или sample://")
    feeds = [str(feed) for feed in feeds]

    pipeline = raw.get("pipeline") or {}
    pipeline = _require_mapping(pipeline, "pipeline")
    pipeline.setdefault("channel", "tech-ai")
    pipeline.setdefault("max_articles", 8)
    pipeline.setdefault("min_articles", 2)
    pipeline.setdefault("allow_publish", False)
    pipeline.setdefault("hashtags", [])

    servers_raw = raw.get("mcp", {}).get("servers") if isinstance(raw.get("mcp"), dict) else None
    servers: Dict[str, ServerConfig] = {}
    if servers_raw is None:
        servers["content_tools"] = ServerConfig(name="content_tools", builtin=True)
    else:
        servers_raw = _require_mapping(servers_raw, "mcp.servers")
        for name, server_data in servers_raw.items():
            server_data = _require_mapping(server_data, "mcp.servers.{}".format(name))
            command = server_data.get("command") or []
            if not isinstance(command, list):
                raise ConfigError("mcp.servers.{}: command должен быть списком".format(name))
            servers[name] = ServerConfig(
                name=name,
                builtin=bool(server_data.get("builtin", False)),
                command=[str(part) for part in command],
                cwd=server_data.get("cwd"),
                env={str(k): str(v) for k, v in (server_data.get("env") or {}).items()},
                timeout=float(server_data.get("timeout", 30)),
            )
    if not servers:
        servers["content_tools"] = ServerConfig(name="content_tools", builtin=True)

    budget_raw = raw.get("budget") or {}
    budget = int(budget_raw.get("max_tokens", raw.get("budget_tokens", 0)) or 0)

    return FactoryConfig(
        providers=providers,
        routes=routes,
        feeds=feeds,
        pipeline=pipeline,
        servers=servers,
        budget_tokens=budget,
        path=path.resolve(),
    )
