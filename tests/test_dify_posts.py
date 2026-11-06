"""Тесты генератора готовых постов из Dify workflow (без сети)."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from content_factory.integrations.dify_posts import (
    DifyPostGenerator,
    build_post_generator,
)
from content_factory.integrations.dify_workflow import DifyWorkflowError
from content_factory.models import Article, ChannelConfig, StoryCluster
from content_factory.nlp.budget import DailyBudget

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
GOOD_TEXT = (
    "OpenAI unveiled a new reasoning model with a two-million-token context. "
    "The company says it is available in the API today and costs 30 percent less "
    "than the previous version. Developers can use it for long-document analysis, "
    "coding assistants and multi-step agent workflows. The release also includes "
    "updated safety evaluations, according to the company. #AI"
)


def _article(source_id="techcrunch", title="OpenAI launches new model", url="https://example.com/a"):
    return Article(
        id="a1",
        title=title,
        url=url,
        source_id=source_id,
        source_name="TechCrunch",
        published_at=NOW - timedelta(hours=1),
        text="OpenAI launched a new reasoning model with a larger context window.",
        language="en",
    )


def _cluster():
    return StoryCluster(
        id="cluster-1",
        title="OpenAI launches new reasoning model",
        articles=[_article()],
        key_terms=["OpenAI", "model"],
        relevance=0.9,
    )


def _channel(**overrides):
    values = {
        "id": "tech-ai",
        "title": "Tech & AI",
        "topics": ["ai"],
        "language": "en",
        "hashtags": ["#AI"],
        "max_post_chars": 3200,
        "telegram_chat_id": "@tech_channel",
    }
    values.update(overrides)
    return ChannelConfig(**values)


def _settings(**pipeline):
    payload = {"min_cluster_chars": 100, "post_duplicate_window_hours": 72}
    payload.update(pipeline)
    return SimpleNamespace(
        pipeline=payload,
        raw={"pipeline": payload},
        data_dir=Path(tempfile.gettempdir()) / "cf-dify-posts-tests",
    )


DEFAULT_IMAGE = "https://example.com/image.jpg"
DEFAULT_SOURCE = "https://example.com/article"


class FakeWorkflowClient:
    def __init__(
        self,
        text: str = GOOD_TEXT,
        error: Exception | None = None,
        outputs: dict | None = None,
    ) -> None:
        self.text = text
        self.error = error
        self.explicit_outputs = outputs
        self.calls = []

    def run(self, inputs, user="content-factory") -> dict:
        self.calls.append({"inputs": dict(inputs), "user": user})
        if self.error is not None:
            raise self.error
        if self.explicit_outputs is not None:
            outputs = dict(self.explicit_outputs)
        else:
            outputs = {
                "result": self.text,
                "image_url": DEFAULT_IMAGE,
                "source_url": DEFAULT_SOURCE,
            }
        return {"data": {"status": "succeeded", "outputs": outputs}}

    def outputs(self, data: dict) -> dict:
        return (data.get("data") or {}).get("outputs") or {}


class DifyPostGeneratorTests(unittest.TestCase):
    def _generate(self, client, config=None, budget=None):
        generator = DifyPostGenerator(
            client, config or {}, budget=budget, purpose="posts", settings=_settings()
        )
        with mock.patch(
            "content_factory.integrations.dify_posts.shorten_url",
            return_value="https://tiny.test/abc",
        ):
            return generator.generate(_channel(), _cluster(), now=NOW)

    def test_builds_ready_post(self):
        client = FakeWorkflowClient()
        post = self._generate(client)
        self.assertIsNotNone(post)
        self.assertEqual(post.channel_id, "tech-ai")
        self.assertEqual(post.meta["generator"], "dify_app")
        self.assertEqual(post.meta["app"], "posts")
        self.assertEqual(post.meta["image_url"], DEFAULT_IMAGE)
        self.assertEqual(post.meta["source_url"], DEFAULT_SOURCE)
        self.assertIn("OpenAI", post.plain_text)
        # Короткая ссылка на источник и emoji-оформление добавлены заводом.
        self.assertIn("https://tiny.test/abc", post.plain_text)
        self.assertGreaterEqual(len(re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", post.text)), 3)
        self.assertEqual(len(post.sources), 1)
        self.assertEqual(post.sources[0]["url"], "https://example.com/a")
        self.assertEqual(client.calls[0]["inputs"]["channel"], "@tech_channel")
        self.assertIn("OpenAI launches new reasoning model", client.calls[0]["inputs"]["topic"])

    def test_plain_text_is_escaped_for_telegram_html(self):
        client = FakeWorkflowClient(text="AI <script>alert(1)</script> " + GOOD_TEXT)
        post = self._generate(client)
        self.assertIn("&lt;script&gt;", post.text)
        self.assertNotIn("<script>", post.text)

    def test_rejects_cyrillic_in_english_channel(self):
        client = FakeWorkflowClient(text="Готовый пост про ИИ. " + GOOD_TEXT)
        self.assertIsNone(self._generate(client))

    def test_rejects_too_short_post(self):
        client = FakeWorkflowClient(text="Too short.")
        self.assertIsNone(self._generate(client))

    def test_empty_outputs_falls_back(self):
        client = FakeWorkflowClient(outputs={})
        self.assertIsNone(self._generate(client))

    def test_workflow_error_falls_back(self):
        client = FakeWorkflowClient(error=DifyWorkflowError("нет Output-узла"))
        self.assertIsNone(self._generate(client))

    def test_daily_budget_exhaustion_skips_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = DailyBudget(Path(tmp) / "usage.json", 1)
            client = FakeWorkflowClient()
            self.assertIsNotNone(self._generate(client, budget=budget))
            self.assertIsNone(self._generate(client, budget=budget))
        self.assertEqual(len(client.calls), 1)

    def test_channel_input_falls_back_to_title(self):
        client = FakeWorkflowClient()
        self._generate(client, config={"inputs": {"channel": "{channel}", "topic": "{topic}"}})
        self.assertEqual(client.calls[0]["inputs"]["channel"], "@tech_channel")

    def test_custom_outputs_mapping_and_inputs(self):
        client = FakeWorkflowClient(
            outputs={
                "post": GOOD_TEXT,
                "img": "https://example.com/pic.png",
                "src": "https://example.com/source",
            }
        )
        config = {
            "inputs": {"channel": "{channel}", "topic": "{topic}", "tone": "expert"},
            "outputs": {"text": "post", "image_url": "img", "source_url": "src"},
        }
        post = self._generate(client, config=config)
        self.assertIsNotNone(post)
        self.assertEqual(post.meta["image_url"], "https://example.com/pic.png")
        self.assertEqual(client.calls[0]["inputs"]["tone"], "expert")


class BuildPostGeneratorTests(unittest.TestCase):
    def _settings(self, pipeline, integrations=None):
        raw = {"pipeline": pipeline}
        if integrations is not None:
            raw["integrations"] = {"dify_apps": integrations}
        return SimpleNamespace(raw=raw, data_dir=Path(tempfile.gettempdir()) / "cf-dify-posts-tests")

    def test_disabled_returns_none(self):
        self.assertIsNone(build_post_generator(self._settings({"post_generator": "internal"})))

    def test_missing_key_returns_none(self):
        with mock.patch.dict(os.environ, {"DIFY_POSTS_API_KEY": ""}, clear=False):
            generator = build_post_generator(
                self._settings({"post_generator": "dify_app", "dify_post_app": "posts"})
            )
        self.assertIsNone(generator)

    def test_enabled_with_key_builds_generator(self):
        integrations = {
            "posts": {"api_key_env": "DIFY_POSTS_API_KEY", "timeout": 30, "daily_limit": 5}
        }
        with mock.patch.dict(os.environ, {"DIFY_POSTS_API_KEY": "app-test"}, clear=False):
            generator = build_post_generator(
                self._settings(
                    {"post_generator": "dify_app", "dify_post_app": "posts"},
                    integrations=integrations,
                )
            )
        self.assertIsNotNone(generator)
        self.assertEqual(generator.purpose, "posts")
        self.assertEqual(generator.budget.limit, 5)


class PipelineUsesDifyGeneratorTests(unittest.TestCase):
    def test_generate_posts_uses_dify_app_without_internal_generation(self):
        from content_factory import pipeline as pipeline_module

        class FakeStorage:
            def get_posts(self, channel_id, days=1, limit=200):
                return []

            def recent_post_titles(self, channel_id, hours=72):
                return []

        class FakeGenerator:
            def __init__(self):
                self.calls = 0

            def generate(self, channel, cluster):
                self.calls += 1
                return pipeline_module.GeneratedPost(
                    id="dify-post-1",
                    channel_id=channel.id,
                    cluster_id=cluster.id,
                    format="story",
                    text="Ready English post from Dify app.",
                    meta={"generator": "dify_app"},
                )

        fake = FakeGenerator()
        settings = _settings(min_cluster_chars=10)
        cluster = _cluster()
        with mock.patch.object(pipeline_module, "build_post_generator", return_value=fake):
            posts, errors = pipeline_module.generate_posts(
                _channel(), [cluster], settings, FakeStorage(), llm=None, max_posts=1
            )
        self.assertEqual(errors, [])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].meta["generator"], "dify_app")
        self.assertEqual(fake.calls, 1)


if __name__ == "__main__":
    unittest.main()
