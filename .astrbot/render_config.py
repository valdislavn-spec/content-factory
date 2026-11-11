"""Готовит data/cmd_config.json в $ASTRBOT_ROOT из шаблона и секретов."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(os.environ["ASTRBOT_ROOT"]).resolve()
TEMPLATE = Path(".astrbot/cmd_config.template.json").resolve()
DATA = ROOT / "data"

DATA.mkdir(parents=True, exist_ok=True)
(DATA / "config").mkdir(parents=True, exist_ok=True)

text = TEMPLATE.read_text(encoding="utf-8")
replacements = {
    "__TELEGRAM_BOT_TOKEN__": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "__GROQ_API_KEY__": os.environ.get("GROQ_API_KEY", ""),
    "__OPENROUTER_API_KEY__": os.environ.get("OPENROUTER_API_KEY", ""),
    "__DEEPSEEK_API_KEY__": os.environ.get("DEEPSEEK_API_KEY", ""),
}
for key, value in replacements.items():
    if not value:
        raise SystemExit(f"missing secret: {key}")
    text = text.replace(key, value)
config = json.loads(text)
(DATA / "cmd_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=4), encoding="utf-8")
print("cmd_config.json written:", tempfile_path := DATA / "cmd_config.json")
