"""Render data/cmd_config.json inside the AstrBot container from env secrets.

Fail-fast only on the Telegram token. LLM providers whose API key is not set are
removed, so a deployment with one working provider still starts instead of
crashing on an unrelated missing key.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("ASTRBOT_ROOT", "/AstrBot")).resolve()
TEMPLATE = Path(os.environ.get("ASTRBOT_TEMPLATE", "/opt/cf/cmd_config.template.json"))
DATA = ROOT / "data"

PROVIDERS = {
    "groq": "__GROQ_API_KEY__",
    "openrouter": "__OPENROUTER_API_KEY__",
    "deepseek": "__DEEPSEEK_API_KEY__",
}
PLACEHOLDERS = {
    "__TELEGRAM_BOT_TOKEN__": "TELEGRAM_BOT_TOKEN",
    "__GROQ_API_KEY__": "GROQ_API_KEY",
    "__OPENROUTER_API_KEY__": "OPENROUTER_API_KEY",
    "__DEEPSEEK_API_KEY__": "DEEPSEEK_API_KEY",
    "__CLOUDFLARE_ACCOUNT_ID__": "CLOUDFLARE_ACCOUNT_ID",
    "__CLOUDFLARE_API_TOKEN__": "CLOUDFLARE_API_TOKEN",
}


def _json_escape(value: str) -> str:
    """Escape a value for insertion inside a JSON string literal."""
    return json.dumps(value, ensure_ascii=False)[1:-1]


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cmd_config-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main() -> int:
    for directory in (DATA, DATA / "config", DATA / "plugins", DATA / "temp"):
        directory.mkdir(parents=True, exist_ok=True)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("missing secret: TELEGRAM_BOT_TOKEN")

    secrets = {
        key: os.environ.get(key, "").strip()
        for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    values = {"TELEGRAM_BOT_TOKEN": token, **secrets}
    for placeholder, env_key in PLACEHOLDERS.items():
        text = text.replace(placeholder, _json_escape(values.get(env_key, "")))

    config = json.loads(text)
    available = {
        source.get("id")
        for source in config.get("provider_sources", [])
        if source.get("key") and any(str(item).strip() for item in source["key"])
    }
    config["provider_sources"] = [
        source for source in config.get("provider_sources", []) if source.get("id") in available
    ]
    cf_ready = bool(secrets.get("CLOUDFLARE_ACCOUNT_ID")) and bool(secrets.get("CLOUDFLARE_API_TOKEN"))
    config["provider"] = [
        provider
        for provider in config.get("provider", [])
        if provider.get("provider_source_id") in available
        or (provider.get("provider_type") == "embedding" and cf_ready)
    ]
    if not config["provider_sources"]:
        raise SystemExit("missing secret: нужен хотя бы один из GROQ_API_KEY / OPENROUTER_API_KEY / DEEPSEEK_API_KEY")

    settings = config.setdefault("provider_settings", {})
    if settings.get("default_provider_id") not in {
        provider.get("id") for provider in config["provider"]
    }:
        settings["default_provider_id"] = config["provider"][0]["id"]

    _write_atomic(DATA / "cmd_config.json", json.dumps(config, ensure_ascii=False, indent=4))
    print("cmd_config.json written:", DATA / "cmd_config.json")
    print("providers:", ", ".join(source["id"] for source in config["provider_sources"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
