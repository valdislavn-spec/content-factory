"""Optional LLM cluster verifier: parsing and safe fallback."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from content_factory.models import Article
from content_factory.nlp.cluster_verifier import (
    ClusterVerifier,
    _parse_verdict,
    make_cluster_verifier,
)

NOW_ARTICLE = Article(
    id="a1", title="OpenAI представила GPT-5", url="https://example.com/a",
    source_id="a", source_name="A", published_at=datetime.now(timezone.utc),
    summary="", weighted_source_score=1.0, meta={},
)


class FakeClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.available = True
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.answer


class ParseVerdictTest(unittest.TestCase):
    def test_json_true_false(self) -> None:
        self.assertIs(_parse_verdict('{"same_event": true, "confidence": 0.9}'), True)
        self.assertIs(_parse_verdict('```json\n{"same_event": false}\n```'), False)

    def test_plain_words_and_garbage(self) -> None:
        self.assertIs(_parse_verdict("да, это одно событие"), True)
        self.assertIs(_parse_verdict("нет, это разные события"), False)
        self.assertIsNone(_parse_verdict("не знаю"))


class ClusterVerifierTest(unittest.TestCase):
    def test_cached_and_budgeted(self) -> None:
        client = FakeClient('{"same_event": true}')
        verifier = ClusterVerifier(client, max_calls=1)
        self.assertIs(verifier.same_event(NOW_ARTICLE, NOW_ARTICLE), True)
        self.assertIs(verifier.same_event(NOW_ARTICLE, NOW_ARTICLE), True)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(len(client.prompts), 1)

    def test_off_by_default(self) -> None:
        settings = SimpleNamespace(pipeline={}, llm={"providers": {}})
        self.assertIsNone(make_cluster_verifier(settings))

    def test_model_and_host_overrides(self) -> None:
        settings = SimpleNamespace(
            pipeline={},
            llm={"providers": {"ollama": {"base_url": "http://ollama:11434"}}},
        )
        with patch.dict(
            os.environ,
            {"CLUSTER_VERIFIER": "ollama", "CLUSTER_VERIFIER_MODEL": "qwen3:1.7b"},
            clear=False,
        ):
            verifier = make_cluster_verifier(settings)
        self.assertIsNotNone(verifier)
        self.assertEqual(verifier.client.model, "qwen3:1.7b")
        self.assertEqual(verifier.client.base_url, "http://ollama:11434")


if __name__ == "__main__":
    unittest.main()
