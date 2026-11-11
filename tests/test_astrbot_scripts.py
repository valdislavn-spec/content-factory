"""AstrBot deployment helpers: config rendering and safe state-sync paths."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / ".astrbot" / "render_config_image.py"
STATE = ROOT / ".astrbot" / "state_sync.py"
TEMPLATE = ROOT / ".astrbot" / "cmd_config.template.json"


def _run(script: Path, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    full = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, str(script)], cwd=str(cwd), env=full,
        capture_output=True, text=True, timeout=30,
    )


class RenderConfigTest(unittest.TestCase):
    def test_renders_available_providers_and_escapes_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                "ASTRBOT_ROOT": str(root),
                "ASTRBOT_TEMPLATE": str(TEMPLATE),
                "TELEGRAM_BOT_TOKEN": '12:"quoted"\\token',
                "GROQ_API_KEY": "gsk-test",
                "OPENROUTER_API_KEY": "",
                "DEEPSEEK_API_KEY": "ds-test",
            }
            result = _run(RENDER, env, root)
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads((root / "data" / "cmd_config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["platform"][0]["telegram_token"], '12:"quoted"\\token')
            ids = {source["id"] for source in config["provider_sources"]}
            self.assertEqual(ids, {"groq", "deepseek"})
            self.assertIn(config["provider_settings"]["default_provider_id"], {"groq-oss", "deepseek-flash"})
            self.assertEqual((root / "data" / "cmd_config.json").stat().st_mode & 0o777, 0o600)

    def test_requires_telegram_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _run(
                RENDER,
                {"ASTRBOT_ROOT": str(root), "ASTRBOT_TEMPLATE": str(TEMPLATE), "TELEGRAM_BOT_TOKEN": ""},
                root,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TELEGRAM_BOT_TOKEN", result.stderr)


class StateSyncTest(unittest.TestCase):
    def test_no_token_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run(
                STATE,
                {"ASTRBOT_ROOT": tmp, "HF_TOKEN": "", "HUGGINGFACE_API_KEY": ""},
                Path(tmp),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no HF token", result.stdout)


if __name__ == "__main__":
    unittest.main()
