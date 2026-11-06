"""Тесты анализа кластера, тональности и LLM-контракта (unittest, без сети)."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from content_factory.config import Settings
from content_factory.models import Analysis, Article, StoryCluster
from content_factory.nlp.analyzer import analyze_cluster
from content_factory.nlp.llm import LLMClient, clean_llm_output, get_llm
from content_factory.nlp.sentiment import detect_sentiment

PUBLISHED = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)


def _make_settings():
    # load_env=False — тесты не зависят от локального .env.
    return Settings.load(load_env=False)


def _article(article_id, title, url, source_id, source_name, text, minutes=0):
    return Article(
        id=article_id,
        title=title,
        url=url,
        source_id=source_id,
        source_name=source_name,
        published_at=PUBLISHED + timedelta(minutes=minutes),
        text=text,
    )


def _multi_source_cluster():
    articles = [
        _article(
            "a1",
            "OpenAI представила новую модель GPT-5",
            "https://habr.com/ru/news/1/",
            "habr",
            "Habr",
            "OpenAI представила новую модель GPT-5. Компания сообщила, что модель "
            "доступна разработчикам через API уже с 18 октября. По данным бенчмарков, "
            "качество ответов выросло на 25% по сравнению с предыдущей версией. "
            "Новая модель поддерживает контекст до 200 тысяч токенов. "
            "Эксперты отмечают рост интереса к подобным решениям.",
            minutes=0,
        ),
        _article(
            "a2",
            "Представлена GPT-5: что известно",
            "https://www.cnews.ru/news/2",
            "cnews",
            "CNews",
            "Компания OpenAI анонсировала модель GPT-5. Новая версия доступна через API, "
            "сообщает CNews. В компании заявили о росте производительности на 25% и "
            "поддержке контекста в 200 тысяч токенов. Разработчики смогут использовать "
            "модель для создания приложений.",
            minutes=30,
        ),
        _article(
            "a3",
            "GPT-5: главное о новинке",
            "https://3dnews.ru/3",
            "3dnews",
            "3DNews",
            "OpenAI выпустила GPT-5. Модель стала доступна разработчикам, пишет 3DNews. "
            "Ранее компания обещала улучшить качество ответов и увеличить контекст. "
            "Новая версия уже тестируется в приложениях партнёров.",
            minutes=60,
        ),
    ]
    return StoryCluster(
        id="cluster-1",
        title="OpenAI представила новую модель GPT-5",
        articles=articles,
        score=0.82,
        channel_id="tech-ai",
    )


class FakeLLM:
    """Мок LLM: возвращает заранее заданные ответы, считает вызовы."""

    name = "fake"
    available = True

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        if not self.replies:
            return ""
        return self.replies.pop(0)


class UnavailableLLM:
    name = "unavailable"
    available = False

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.calls += 1
        raise AssertionError("недоступная LLM не должна вызываться")


class BrokenLLM(LLMClient):
    """Клиент, который всегда падает: базовый класс обязан вернуть ""."""

    def __init__(self):
        super().__init__(name="broken", available=True, config={"timeout": 1})

    def _generate(self, prompt, system, max_tokens, temperature):
        raise RuntimeError("сеть недоступна")


class AnalyzeClusterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = _make_settings()
        cls.cluster = _multi_source_cluster()
        cls.analysis = analyze_cluster(cls.cluster, cls.settings)

    def test_summary_is_three_to_six_sentences(self):
        self.assertTrue(self.analysis.summary)
        sentences = self.analysis.summary.split(". ")
        self.assertGreaterEqual(len(sentences), 3)
        self.assertLessEqual(len(sentences), 6)
        self.assertTrue(self.analysis.summary.rstrip().endswith((".", "!", "?", "…")))

    def test_bullets_are_three_to_five(self):
        self.assertGreaterEqual(len(self.analysis.bullets), 3)
        self.assertLessEqual(len(self.analysis.bullets), 5)
        self.assertEqual(len(set(self.analysis.bullets)), len(self.analysis.bullets))
        for bullet in self.analysis.bullets:
            self.assertTrue(bullet.strip())

    def test_key_terms_filled(self):
        self.assertGreaterEqual(len(self.analysis.key_terms), 3)
        self.assertTrue(any("модел" in term.lower() for term in self.analysis.key_terms))

    def test_numbers_extracted_from_sources(self):
        self.assertIn("25%", self.analysis.numbers)

    def test_sentiment_and_entities(self):
        self.assertIn(self.analysis.sentiment, ("positive", "neutral", "negative"))
        self.assertGreaterEqual(self.analysis.sentiment_score, -1.0)
        self.assertLessEqual(self.analysis.sentiment_score, 1.0)
        self.assertIn("OpenAI", self.analysis.entities)
        self.assertIn("GPT-5", self.analysis.entities)

    def test_perspectives_cover_every_source(self):
        self.assertEqual(self.analysis.source_count, 3)
        self.assertEqual(len(self.analysis.source_names), 3)
        self.assertEqual(len(self.analysis.perspectives), 3)
        sources = {perspective["source_name"] for perspective in self.analysis.perspectives}
        self.assertEqual(sources, {"Habr", "CNews", "3DNews"})
        source_texts = {
            article.source_name: (article.text + " " + article.title).lower()
            for article in self.cluster.articles
        }
        for perspective in self.analysis.perspectives:
            self.assertEqual(set(perspective), {"source_name", "quote", "angle"})
            self.assertTrue(perspective["quote"])
            self.assertTrue(perspective["angle"])
            quote = perspective["quote"].lower().rstrip("…").strip()
            self.assertIn(quote, source_texts[perspective["source_name"]])

    def test_confidence_in_range(self):
        self.assertGreaterEqual(self.analysis.confidence, 0.1)
        self.assertLessEqual(self.analysis.confidence, 1.0)

    def test_multi_source_confidence_higher_than_single_source(self):
        single = StoryCluster(
            id="cluster-single",
            title="OpenAI представила новую модель GPT-5",
            articles=[self.cluster.articles[0]],
        )
        single_analysis = analyze_cluster(single, self.settings)
        self.assertEqual(single_analysis.source_count, 1)
        self.assertLess(single_analysis.confidence, self.analysis.confidence)
        self.assertEqual(len(single_analysis.perspectives), 1)

    def test_empty_cluster_does_not_crash(self):
        empty = StoryCluster(id="cluster-empty", title="Пустой кластер", articles=[])
        analysis = analyze_cluster(empty, self.settings)
        self.assertIsInstance(analysis, Analysis)
        self.assertEqual(analysis.source_count, 0)
        self.assertEqual(analysis.perspectives, [])
        self.assertGreaterEqual(analysis.confidence, 0.0)


class LLMFallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = _make_settings()
        cls.cluster = _multi_source_cluster()

    def test_garbage_llm_output_falls_back_to_extractive(self):
        garbage = FakeLLM(
            [
                '```json\n{"summary": "Это выдуманный ответ модели, который не должен попасть в анализ."}\n```',
                "Не могу помочь.",
            ]
        )
        analysis = analyze_cluster(self.cluster, self.settings, llm=garbage)
        self.assertNotIn("```", analysis.summary)
        self.assertNotIn("выдуманный", analysis.summary)
        self.assertIn("OpenAI", analysis.summary)
        self.assertGreaterEqual(len(analysis.bullets), 3)
        self.assertLessEqual(len(analysis.bullets), 5)

    def test_valid_llm_output_is_used(self):
        llm = FakeLLM(
            [
                "Компания OpenAI представила модель GPT-5. По данным компании, качество "
                "ответов выросло на 25%. Модель доступна разработчикам через API.",
                "Модель доступна разработчикам через API.\n"
                "Качество ответов выросло на 25%.\n"
                "Новая версия поддерживает контекст до 200 тысяч токенов.",
            ]
        )
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm)
        self.assertIn("Компания OpenAI представила модель GPT-5.", analysis.summary)
        self.assertIn("Модель доступна разработчикам через API.", analysis.bullets)

    def test_llm_hallucinated_number_is_rejected(self):
        llm = FakeLLM(
            [
                "Компания OpenAI представила модель GPT-5. Качество ответов выросло "
                "на 150 процентов, сообщают источники. Модель доступна через API.",
                "",
            ]
        )
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm)
        self.assertNotIn("150", analysis.summary)

    def test_unavailable_llm_is_not_called(self):
        llm = UnavailableLLM()
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm)
        self.assertEqual(llm.calls, 0)
        self.assertTrue(analysis.summary)
        self.assertGreaterEqual(len(analysis.bullets), 3)

    def test_broken_client_returns_empty_string(self):
        client = BrokenLLM()
        self.assertEqual(client.generate("привет"), "")
        self.assertFalse(client.available)


class SentimentTest(unittest.TestCase):
    def test_positive_text(self):
        label, score = detect_sentiment(
            "Компания показала рекордный рост прибыли и успех на рынке."
        )
        self.assertEqual(label, "positive")
        self.assertGreater(score, 0.0)

    def test_negative_text(self):
        label, score = detect_sentiment(
            "Авария привела к убыткам: сбой усилил угрозу кризиса и скандал."
        )
        self.assertEqual(label, "negative")
        self.assertLess(score, 0.0)

    def test_neutral_text(self):
        label, score = detect_sentiment("В Москве прошла встреча представителей компаний.")
        self.assertEqual(label, "neutral")
        self.assertEqual(score, 0.0)

    def test_empty_text_is_neutral(self):
        self.assertEqual(detect_sentiment(""), ("neutral", 0.0))

    def test_negation_reduces_positive_score(self):
        positive_score = detect_sentiment("Прибыль выросла, успех и рекорд.")[1]
        negated_score = detect_sentiment("Прибыль не выросла, успеха нет.")[1]
        self.assertGreater(positive_score, negated_score)


class LLMFactoryTest(unittest.TestCase):
    def test_extractive_provider_is_default_and_safe(self):
        # Явно проверяем дефолт get_llm, не завися от llm.provider в settings.yaml.
        settings = SimpleNamespace(llm={})
        llm = get_llm(settings)
        self.assertEqual(llm.name, "extractive")
        self.assertFalse(llm.available)
        self.assertEqual(llm.generate("любой промпт", system="система"), "")

    def test_unknown_provider_falls_back_to_extractive(self):
        llm = get_llm(SimpleNamespace(llm={"provider": "unknown-provider"}))
        self.assertEqual(llm.name, "extractive")
        self.assertFalse(llm.available)

    def test_gigachat_without_credentials_is_unavailable(self):
        with mock.patch.dict(os.environ, {"GIGACHAT_CREDENTIALS": ""}):
            llm = get_llm(SimpleNamespace(llm={"provider": "gigachat", "timeout": 1}))
        self.assertEqual(llm.name, "gigachat")
        self.assertFalse(llm.available)
        self.assertEqual(llm.generate("текст"), "")

    def test_yandexgpt_without_credentials_is_unavailable(self):
        with mock.patch.dict(
            os.environ, {"YANDEXGPT_API_KEY": "", "YANDEX_FOLDER_ID": ""}
        ):
            llm = get_llm(SimpleNamespace(llm={"provider": "yandexgpt"}))
        self.assertEqual(llm.name, "yandexgpt")
        self.assertFalse(llm.available)

    def test_clean_llm_output_removes_markdown_and_prefixes(self):
        self.assertEqual(clean_llm_output("```\nРезюме: текст ответа\n```"), "текст ответа")
        self.assertEqual(clean_llm_output("Ответ: готово"), "готово")
        self.assertEqual(clean_llm_output(""), "")
        self.assertEqual(clean_llm_output("  - пункт списка  "), "пункт списка")


if __name__ == "__main__":
    unittest.main()
