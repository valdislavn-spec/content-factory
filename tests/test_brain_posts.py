"""Тесты моста «мозга»: content-factory → mcp-content-factory (без сети)."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from content_factory.integrations.brain_posts import (
    BrainPostGenerator,
    build_brain_generator,
)
from content_factory.integrations.dify_posts import build_post_generator

MARKDOWN = """# Spot Bitcoin ETFs Hit Record Inflows

US spot Bitcoin ETFs attracted a record $1.2 billion in weekly inflows, led by BlackRock.

---

**Источники:**

1. [Spot Bitcoin ETFs see record weekly inflows](<https://example.com/btc>) — Test
"""


def make_channel(channel_id: str = "crypto-news", language: str = "en"):
    return SimpleNamespace(
        id=channel_id,
        title=channel_id,
        language=language,
        hashtags=["Crypto", "#Bitcoin"],
        cta="Подписывайтесь на сеть",
        max_post_chars=2000,
    )


def make_cluster():
    article = SimpleNamespace(
        title="Spot Bitcoin ETFs see record weekly inflows",
        url="https://example.com/btc",
        summary="Record $1.2B weekly inflows.",
        text="",
        source_id="bloomberg",
        source_name="Bloomberg",
        published_at="2026-11-07T10:00:00+00:00",
    )
    return SimpleNamespace(id="cluster-42", title=article.title, articles=[article])


def make_settings(root: Path, enabled: bool = True):
    brain_dir = root / "mcp-brain"
    brain_dir.mkdir(parents=True, exist_ok=True)
    python_path = brain_dir / "python"
    python_path.write_text("#!/bin/sh\n", encoding="utf-8")
    config_path = brain_dir / "brain.json"
    config_path.write_text("{}", encoding="utf-8")
    raw = {
        "pipeline": {"post_generator": "brain"},
        "brain": {
            "enabled": enabled,
            "channels": ["crypto-news"],
            "path": "mcp-brain",
            "python": "mcp-brain/python",
            "config": "mcp-brain/brain.json",
            "engine": "langgraph",
            "grounding": True,
            "revision_rounds": 1,
            "timeout": 30,
        },
        "llm": {"provider": "ollama_cloud"},
    }
    return SimpleNamespace(root=root, raw=raw, data_dir=root / "data")


class BrainGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.settings = make_settings(self.root)
        self.generator = build_brain_generator(self.settings)

    def tearDown(self):
        self.tmp.cleanup()

    def test_builder_returns_generator(self):
        self.assertIsInstance(self.generator, BrainPostGenerator)
        self.assertTrue(self.generator.available())

    def test_builder_routed_from_dify_posts(self):
        routed = build_post_generator(self.settings)
        self.assertIsInstance(routed, BrainPostGenerator)

    def test_generate_builds_telegram_post(self):
        completed = subprocess.CompletedProcess(
            args=["brain"], returncode=0,
            stdout=json.dumps(
                {
                    "title": "Spot Bitcoin ETFs Hit Record Inflows",
                    "markdown": MARKDOWN,
                    "draft_path": "/tmp/draft.md",
                    "run_log": "/tmp/run.json",
                    "engine": "langgraph",
                    "language": "en",
                }
            ),
            stderr="",
        )
        with mock.patch(
            "content_factory.integrations.brain_posts.subprocess.run",
            return_value=completed,
        ) as run:
            post = self.generator.generate(make_channel(), make_cluster())
        self.assertIsNotNone(post)
        self.assertEqual(post.channel_id, "crypto-news")
        self.assertIn("<b>Spot Bitcoin ETFs Hit Record Inflows</b>", post.text)
        self.assertNotIn("# Spot Bitcoin ETFs Hit Record Inflows", post.text)
        self.assertIn("#Crypto", post.text)
        self.assertIn("#Bitcoin", post.text)
        self.assertIn("Подписывайтесь на сеть", post.text)
        self.assertNotIn("**Источники:**", post.text)
        self.assertEqual(post.meta["generator"], "brain")
        self.assertEqual(post.sources[0]["url"], "https://example.com/btc")
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["channel"], "crypto-news")
        self.assertEqual(payload["language"], "en")
        self.assertEqual(payload["articles"][0]["source"], "Bloomberg")

    def test_other_channel_falls_back(self):
        with mock.patch(
            "content_factory.integrations.brain_posts.subprocess.run"
        ) as run:
            post = self.generator.generate(make_channel("sport-news"), make_cluster())
        self.assertIsNone(post)
        run.assert_not_called()

    def test_subprocess_failure_falls_back(self):
        completed = subprocess.CompletedProcess(
            args=["brain"], returncode=1, stdout="", stderr="boom"
        )
        with mock.patch(
            "content_factory.integrations.brain_posts.subprocess.run",
            return_value=completed,
        ):
            post = self.generator.generate(make_channel(), make_cluster())
        self.assertIsNone(post)

    def test_invalid_json_falls_back(self):
        completed = subprocess.CompletedProcess(
            args=["brain"], returncode=0, stdout="not-json", stderr=""
        )
        with mock.patch(
            "content_factory.integrations.brain_posts.subprocess.run",
            return_value=completed,
        ):
            post = self.generator.generate(make_channel(), make_cluster())
        self.assertIsNone(post)

    def test_missing_bridge_returns_none(self):
        broken = make_settings(self.root)
        broken.raw["brain"]["path"] = "missing-dir"
        self.assertIsNone(build_brain_generator(broken))

    def test_extractive_mode_disables_bridge(self):
        self.settings.raw["llm"] = {"provider": "extractive"}
        self.assertIsNone(build_brain_generator(self.settings))

    def test_env_kill_switch(self):
        with mock.patch.dict("os.environ", {"CONTENT_FACTORY_BRAIN": "off"}):
            self.assertIsNone(build_brain_generator(self.settings))


if __name__ == "__main__":
    unittest.main()
