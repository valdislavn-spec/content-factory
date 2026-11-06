"""Тесты экономии токенов в анализе и генерации (без сети).

Проверяем:
* объединённый запрос «резюме + тезисы» действительно один вызов;
* при нарушенном формате — безопасный откат на прежнюю схему из двух вызовов;
* компактный промпт заголовка короче и опирается на резюме, а не на 6000
  символов исходного текста.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from content_factory.config import Settings
from content_factory.models import Analysis, Article, StoryCluster
from content_factory.nlp.analyzer import analyze_cluster
from content_factory.nlp.generator import _llm_headline

SOURCE_TEXT = (
    "OpenAI представила модель GPT-5. Компания сообщила, что модель доступна "
    "разработчикам через API с 18 октября. По данным бенчмарков, качество ответов "
    "выросло на 25%. Новая модель поддерживает контекст до 200 тысяч токенов."
)


class FakeLLM:
    name = "fake"
    available = True
    max_tokens = 500
    temperature = 0.3

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None, **kwargs):
        self.prompts.append(prompt)
        if not self.replies:
            return ""
        return self.replies.pop(0)


def _settings(optimized: bool = True) -> Settings:
    settings = Settings.load(load_env=False)
    settings.raw.setdefault("llm", {})["optimize"] = {
        "combined_analysis": optimized,
        "compact_headline": optimized,
    }
    return settings


def _cluster(text: str = SOURCE_TEXT) -> StoryCluster:
    article = Article(
        id="a1",
        title="OpenAI представила новую модель GPT-5",
        url="https://habr.com/ru/news/1/",
        source_id="habr",
        source_name="Habr",
        published_at=datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc),
        text=text,
    )
    return StoryCluster(
        id="cluster-1",
        title="OpenAI представила новую модель GPT-5",
        articles=[article],
        score=0.8,
        channel_id="tech-ai",
    )


COMBINED_OK = (
    "РЕЗЮМЕ: OpenAI представила модель GPT-5. Модель доступна разработчикам через API. "
    "Качество ответов выросло на 25%.\n"
    "ТЕЗИСЫ:\n"
    "- Модель доступна через API.\n"
    "- Качество ответов выросло на 25%.\n"
    "- Контекст достигает 200 тысяч токенов."
)
SUMMARY_OK = (
    "OpenAI представила модель GPT-5. Модель доступна разработчикам через API. "
    "Качество ответов выросло на 25%."
)
BULLETS_OK = (
    "Модель доступна через API.\n"
    "Качество ответов выросло на 25%.\n"
    "Контекст достигает 200 тысяч токенов."
)


class CombinedAnalysisTests(unittest.TestCase):
    def test_combined_mode_uses_one_llm_call(self):
        llm = FakeLLM([COMBINED_OK])
        analysis = analyze_cluster(_cluster(), _settings(optimized=True), llm=llm)
        self.assertEqual(len(llm.prompts), 1)
        self.assertIn("OpenAI представила модель GPT-5.", analysis.summary)
        self.assertGreaterEqual(len(analysis.bullets), 3)
        self.assertLessEqual(len(analysis.bullets), 5)

    def test_broken_format_falls_back_to_two_calls(self):
        llm = FakeLLM(["Не могу помочь.", SUMMARY_OK, BULLETS_OK])
        analysis = analyze_cluster(_cluster(), _settings(optimized=True), llm=llm)
        self.assertEqual(len(llm.prompts), 3)
        self.assertIn("OpenAI представила модель GPT-5.", analysis.summary)
        self.assertGreaterEqual(len(analysis.bullets), 3)

    def test_opt_out_uses_legacy_two_calls(self):
        llm = FakeLLM([SUMMARY_OK, BULLETS_OK])
        analysis = analyze_cluster(_cluster(), _settings(optimized=False), llm=llm)
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("OpenAI представила модель GPT-5.", analysis.summary)


class CompactHeadlineTests(unittest.TestCase):
    def setUp(self):
        self.cluster = _cluster(text=SOURCE_TEXT + " " + ("Подробности новости. " * 400))
        self.analysis = Analysis(
            summary="OpenAI представила модель GPT-5, качество ответов выросло на 25%.",
            bullets=[
                "Модель доступна через API.",
                "Качество ответов выросло на 25%.",
                "Контекст достигает 200 тысяч токенов.",
            ],
        )
        self.headline_reply = "Новый заголовок о GPT-5 и его API для разработчиков"

    def test_compact_prompt_is_much_shorter_and_uses_summary(self):
        llm = FakeLLM([self.headline_reply])
        title = _llm_headline(
            self.cluster,
            self.analysis,
            self.cluster.combined_text or SOURCE_TEXT,
            llm,
            compact=True,
        )
        self.assertTrue(title)
        prompt = llm.prompts[0]
        self.assertIn("Резюме:", prompt)
        self.assertLess(len(prompt), 1500)

    def test_legacy_prompt_contains_source_text(self):
        llm = FakeLLM([self.headline_reply])
        _llm_headline(
            self.cluster,
            self.analysis,
            self.cluster.combined_text or SOURCE_TEXT,
            llm,
            compact=False,
        )
        self.assertGreater(len(llm.prompts[0]), 3000)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
