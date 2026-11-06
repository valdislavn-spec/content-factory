"""EN-анализ кластера и экстрактивный fallback (unittest, без сети).

Проверяют английский режим обязательного офлайн-анализа: английские промпты
и шаблоны, валидацию ответов LLM по целевому языку, отсутствие кириллицы в
EN-анализе, английские ключевые термины без русской морфологии и передачу
языка канала из конвейера. Русское поведение по умолчанию не должно меняться.
"""
from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from content_factory import pipeline
from content_factory.models import Analysis, Article, ChannelConfig, GeneratedPost, StoryCluster
from content_factory.nlp.analyzer import analyze_cluster
from content_factory.nlp.extractive import split_sentences, summarize_texts
from content_factory.nlp.keywords import extract_key_terms
from content_factory.utils import STOPWORDS_EN, STOPWORDS_RU, tokenize

PUBLISHED = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
EN_SETTINGS_VALUES = {"app.language": "en", "pipeline.max_text_chars": 15000}
RU_SETTINGS_VALUES = {"app.language": "ru", "pipeline.max_text_chars": 15000}
PIPELINE_SETTINGS_VALUES = {
    "app.language": "en",
    "pipeline.max_text_chars": 15000,
    "pipeline.min_cluster_chars": 200,
    "pipeline.min_post_chars": 220,
    "pipeline.banned_words": [],
    "pipeline.post_duplicate_window_hours": 72,
}


def _has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text or ""))


def _fake_settings(language: str = "en"):
    """Настройки без чтения живого settings.yaml (тесты не зависят от конфига)."""
    values = dict(EN_SETTINGS_VALUES if language == "en" else RU_SETTINGS_VALUES)
    return SimpleNamespace(
        app={"language": language},
        pipeline={"max_text_chars": 15000},
        llm={"provider": "extractive"},
        raw={"llm": {"provider": "extractive"}},
        get=lambda dotted, default=None: values.get(dotted, default),
    )


def _pipeline_settings(language: str = "en"):
    values = dict(PIPELINE_SETTINGS_VALUES)
    values["app.language"] = language
    return SimpleNamespace(
        app={"language": language},
        pipeline={
            "max_text_chars": 15000,
            "min_cluster_chars": 200,
            "min_post_chars": 220,
            "banned_words": [],
            "post_duplicate_window_hours": 72,
        },
        llm={"provider": "extractive"},
        raw={"llm": {"provider": "extractive"}},
        get=lambda dotted, default=None: values.get(dotted, default),
    )


def _article(article_id, title, text, source_id, source_name, language="en"):
    return Article(
        id=article_id,
        title=title,
        url=f"https://example.com/{article_id}",
        source_id=source_id,
        source_name=source_name,
        published_at=PUBLISHED,
        text=text,
        language=language,
    )


EN_ARTICLE_TEXTS = (
    "OpenAI unveiled its new GPT-5 model on Thursday. The company said the model "
    "is available to developers through its API. Benchmark scores improved by 25% "
    "compared with the previous version. The new model supports a context window "
    "of up to 200,000 tokens.",
    "OpenAI announced the GPT-5 model this week. The new version is available "
    "through the API, reports The Verge. Benchmark results show a 25% improvement "
    "over the previous model. Developers can use it to build applications.",
    "OpenAI released GPT-5. The model is now available to developers, writes Ars "
    "Technica. The company promised better benchmark scores and a larger context "
    "window. The new version is already being tested by partners.",
)

EN_ARTICLE_TITLES = (
    "OpenAI unveils GPT-5 model",
    "GPT-5: what we know",
    "GPT-5 is here",
)

EN_SOURCE_NAMES = (
    ("techcrunch", "TechCrunch"),
    ("theverge", "The Verge"),
    ("arstechnica", "Ars Technica"),
)


def _en_cluster() -> StoryCluster:
    articles = [
        _article(f"en-{index}", EN_ARTICLE_TITLES[index], EN_ARTICLE_TEXTS[index], *EN_SOURCE_NAMES[index])
        for index in range(len(EN_ARTICLE_TEXTS))
    ]
    return StoryCluster(
        id="cluster-en",
        title="OpenAI unveils GPT-5 model",
        articles=articles,
        score=0.8,
        channel_id="tech-ai",
    )


def _en_small_cluster(source_count: int = 2) -> StoryCluster:
    """Короткий EN-кластер: резюме получает шаблонные вставки (coverage)."""
    articles = [
        _article("small-1", "OpenAI releases GPT-5 model",
                 "OpenAI released the GPT-5 model on Thursday.", "techcrunch", "TechCrunch"),
        _article("small-2", "GPT-5 model is available",
                 "The GPT-5 model is available to developers.", "theverge", "The Verge"),
    ][:source_count]
    return StoryCluster(
        id="cluster-en-small",
        title="OpenAI released the GPT-5 model",
        articles=articles,
        channel_id="tech-ai",
    )


def _ru_small_cluster() -> StoryCluster:
    articles = [
        Article(
            id="ru-1", title="OpenAI выпустила GPT-5", url="https://habr.com/ru/1",
            source_id="habr", source_name="Habr", published_at=PUBLISHED,
            text="OpenAI выпустила модель GPT-5 в четверг.", language="ru",
        ),
        Article(
            id="ru-2", title="Модель GPT-5 доступна разработчикам", url="https://cnews.ru/2",
            source_id="cnews", source_name="CNews", published_at=PUBLISHED,
            text="Модель GPT-5 стала доступна разработчикам.", language="ru",
        ),
    ]
    return StoryCluster(
        id="cluster-ru-small",
        title="OpenAI выпустила GPT-5",
        articles=articles,
        channel_id="tech-ai",
    )


class FakeLLM:
    """Мок LLM-клиента с интерфейсом LLMClient: отдаёт заданные ответы."""

    name = "fake"
    available = True

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []
        self.systems = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        self.systems.append(system)
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


EN_VALID_SUMMARY = (
    "OpenAI has unveiled the GPT-5 model. Benchmark scores improved by 25% "
    "compared with the previous version. The model is available to developers "
    "through the API."
)
EN_VALID_BULLETS = (
    "GPT-5 is available to developers through the API.\n"
    "Scores improved by 25% over the previous version.\n"
    "The model supports a context window of 200,000 tokens."
)
RU_LLM_SUMMARY = (
    "Компания OpenAI представила модель GPT-5. Качество ответов выросло на 25%. "
    "Модель доступна разработчикам через API."
)


class EnglishAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = _fake_settings("en")
        cls.cluster = _en_cluster()
        cls.analysis = analyze_cluster(cls.cluster, cls.settings, language="en")

    def test_no_cyrillic_in_any_analysis_field(self):
        analysis = self.analysis
        texts = [analysis.summary, " ".join(analysis.bullets), " ".join(analysis.key_terms),
                 " ".join(analysis.entities)]
        for perspective in analysis.perspectives:
            texts.extend([perspective.get("quote", ""), perspective.get("angle", "")])
        for text in texts:
            self.assertFalse(_has_cyrillic(text), f"кириллица в EN-анализе: {text!r}")

    def test_summary_is_three_to_six_sentences(self):
        self.assertTrue(self.analysis.summary)
        sentences = split_sentences(self.analysis.summary)
        self.assertGreaterEqual(len(sentences), 3)
        self.assertLessEqual(len(sentences), 6)
        self.assertTrue(self.analysis.summary.rstrip().endswith((".", "!", "?", "…")))

    def test_bullets_are_three_to_five_and_unique(self):
        self.assertGreaterEqual(len(self.analysis.bullets), 3)
        self.assertLessEqual(len(self.analysis.bullets), 5)
        self.assertEqual(len(set(self.analysis.bullets)), len(self.analysis.bullets))
        for bullet in self.analysis.bullets:
            self.assertFalse(_has_cyrillic(bullet))

    def test_key_terms_are_english_without_stopwords(self):
        terms = self.analysis.key_terms
        self.assertGreaterEqual(len(terms), 3)
        for term in terms:
            self.assertFalse(_has_cyrillic(term))
            self.assertNotIn(term.lower(), STOPWORDS_EN)
        lowered = {term.lower() for term in terms}
        self.assertTrue(
            lowered & {"openai", "gpt-5", "model", "benchmark", "developers"},
            f"нет содержательных EN-терминов: {terms}",
        )

    def test_entities_are_english_proper_names(self):
        self.assertIn("OpenAI", self.analysis.entities)
        self.assertNotIn("The", self.analysis.entities)
        self.assertNotIn("Thursday", self.analysis.entities)

    def test_numbers_and_sources(self):
        self.assertIn("25%", self.analysis.numbers)
        self.assertEqual(self.analysis.source_count, 3)
        self.assertEqual(len(self.analysis.perspectives), 3)
        sources = {perspective["source_name"] for perspective in self.analysis.perspectives}
        self.assertEqual(sources, {"TechCrunch", "The Verge", "Ars Technica"})

    def test_confidence_in_range(self):
        self.assertGreaterEqual(self.analysis.confidence, 0.1)
        self.assertLessEqual(self.analysis.confidence, 1.0)

    def test_language_from_settings_resolved_to_english(self):
        # Без явного language: язык берётся из статей кластера (language="en").
        analysis = analyze_cluster(self.cluster, self.settings)
        self.assertTrue(analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))
        self.assertFalse(_has_cyrillic(" ".join(analysis.bullets)))

    def test_explicit_language_wins_over_settings(self):
        analysis = analyze_cluster(self.cluster, _fake_settings("ru"), language="en")
        self.assertFalse(_has_cyrillic(analysis.summary))
        self.assertFalse(_has_cyrillic(" ".join(analysis.bullets)))

    def test_language_codes_are_normalized(self):
        for value in ("en", "EN", "en-US", "english"):
            analysis = analyze_cluster(self.cluster, self.settings, language=value)
            self.assertFalse(
                _has_cyrillic(analysis.summary), f"язык {value!r} не распознан как английский"
            )

    def test_article_language_enables_english_analysis(self):
        # Настройки проекта могут быть русскими, но статьи кластера английские:
        # resolve_language выбирает язык статей, анализ остаётся английским.
        analysis = analyze_cluster(self.cluster, _fake_settings("ru"))
        self.assertFalse(_has_cyrillic(analysis.summary))
        self.assertIn("OpenAI", analysis.summary)

    def test_empty_en_cluster_does_not_crash(self):
        empty = StoryCluster(id="cluster-empty-en", title="Empty cluster", articles=[])
        analysis = analyze_cluster(empty, self.settings, language="en")
        self.assertIsInstance(analysis, Analysis)
        self.assertEqual(analysis.source_count, 0)
        self.assertEqual(analysis.perspectives, [])
        self.assertGreaterEqual(analysis.confidence, 0.0)


class EnglishLLMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = _fake_settings("en")
        cls.cluster = _en_cluster()

    def test_valid_english_llm_summary_and_bullets_are_used(self):
        llm = FakeLLM([EN_VALID_SUMMARY, EN_VALID_BULLETS])
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="en")
        self.assertIn("OpenAI has unveiled the GPT-5 model.", analysis.summary)
        self.assertIn("GPT-5 is available to developers through the API.", analysis.bullets)
        self.assertFalse(_has_cyrillic(" ".join(analysis.bullets)))

    def test_prompts_are_english(self):
        llm = FakeLLM([EN_VALID_SUMMARY, EN_VALID_BULLETS])
        analyze_cluster(self.cluster, self.settings, llm=llm, language="en")
        self.assertGreaterEqual(len(llm.prompts), 2)
        self.assertIn("in English", llm.prompts[0])
        self.assertIn("in English", llm.prompts[1])
        for system in llm.systems:
            self.assertTrue(system)
            self.assertFalse(_has_cyrillic(system))
        self.assertIn("English", llm.systems[0])

    def test_russian_llm_answer_is_rejected_for_english_channel(self):
        llm = FakeLLM([RU_LLM_SUMMARY, ""])
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="en")
        self.assertFalse(_has_cyrillic(analysis.summary))
        self.assertFalse(_has_cyrillic(" ".join(analysis.bullets)))
        # Использован экстрактивный fallback из английских источников.
        self.assertIn("OpenAI", analysis.summary)
        self.assertGreaterEqual(len(analysis.bullets), 3)

    def test_markdown_garbage_is_rejected(self):
        llm = FakeLLM(['```json\n{"summary": "OpenAI model summary from the model."}\n```', ""])
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="en")
        self.assertNotIn("```", analysis.summary)
        self.assertNotIn("json", analysis.summary.lower())
        self.assertFalse(_has_cyrillic(analysis.summary))

    def test_hallucinated_number_is_rejected(self):
        llm = FakeLLM(
            [
                "OpenAI has unveiled the GPT-5 model. Benchmark scores improved by "
                "150% compared with the previous version. The model is available "
                "through the API.",
                "",
            ]
        )
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="en")
        self.assertNotIn("150", analysis.summary)

    def test_invalid_bullets_fall_back_while_summary_is_kept(self):
        llm = FakeLLM([EN_VALID_SUMMARY, "One short line only."])
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="en")
        self.assertIn("OpenAI has unveiled the GPT-5 model.", analysis.summary)
        self.assertGreaterEqual(len(analysis.bullets), 3)
        self.assertLessEqual(len(analysis.bullets), 5)
        self.assertFalse(_has_cyrillic(" ".join(analysis.bullets)))

    def test_unavailable_llm_is_not_called(self):
        llm = UnavailableLLM()
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="en")
        self.assertEqual(llm.calls, 0)
        self.assertTrue(analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))


class EnglishTemplatesTest(unittest.TestCase):
    def test_coverage_sentence_plural_english(self):
        analysis = analyze_cluster(
            _en_small_cluster(source_count=2), _fake_settings("en"), language="en"
        )
        self.assertIn("2 outlets reported this: TechCrunch, The Verge.", analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))

    def test_coverage_sentence_singular_english(self):
        analysis = analyze_cluster(
            _en_small_cluster(source_count=1), _fake_settings("en"), language="en"
        )
        self.assertIn("Reported by TechCrunch.", analysis.summary)
        self.assertNotIn("outlets reported this", analysis.summary)

    def test_russian_coverage_and_templates_unchanged(self):
        analysis = analyze_cluster(_ru_small_cluster(), _fake_settings("ru"))
        self.assertIn("Об этом сообщают 2 источника: Habr, CNews.", analysis.summary)
        self.assertNotIn("outlets reported this", analysis.summary)
        self.assertTrue(_has_cyrillic(analysis.summary))
        self.assertTrue(_has_cyrillic(" ".join(analysis.bullets)))


class ExtractiveEnglishTest(unittest.TestCase):
    def test_english_abbreviations_do_not_split_sentences(self):
        text = (
            "Companies, e.g. Apple and Google, reported growth. "
            "Shares rose after the news. Analysts expect more gains."
        )
        sentences = split_sentences(text)
        self.assertEqual(len(sentences), 3)
        self.assertTrue(sentences[0].endswith("growth."))
        self.assertIn("e.g.", sentences[0])

    def test_summarize_texts_returns_english_summary(self):
        summary = summarize_texts(list(EN_ARTICLE_TEXTS), max_sentences=3, language="en")
        self.assertTrue(summary)
        self.assertFalse(_has_cyrillic(summary))
        self.assertLessEqual(len(split_sentences(summary)), 3)
        self.assertTrue(summary.rstrip().endswith((".", "!", "?", "…")))

    def test_english_tokenize_removes_english_stopwords(self):
        tokens = tokenize(
            "The company said the new model is available to developers, and the API is open.",
            language="en",
        )
        self.assertIn("developers", tokens)
        for stopword in ("the", "and", "is", "to", "said"):
            self.assertNotIn(stopword, tokens)

    def test_default_tokenize_still_russian(self):
        self.assertEqual(
            tokenize("Российский рынок вырос на 5 процентов"),
            tokenize("Российский рынок вырос на 5 процентов", language="ru"),
        )


class KeyTermsEnglishTest(unittest.TestCase):
    def test_english_terms_auto_detected(self):
        terms = extract_key_terms(list(EN_ARTICLE_TEXTS), top_n=8)
        self.assertGreaterEqual(len(terms), 3)
        for term in terms:
            self.assertFalse(_has_cyrillic(term))
            self.assertNotIn(term.lower(), STOPWORDS_EN)
        lowered = {term.lower() for term in terms}
        self.assertTrue(lowered & {"openai", "gpt-5", "model", "benchmark", "developers"})

    def test_english_terms_explicit_language(self):
        auto = extract_key_terms(list(EN_ARTICLE_TEXTS), top_n=6)
        explicit = extract_key_terms(list(EN_ARTICLE_TEXTS), top_n=6, language="en")
        self.assertEqual(auto, explicit)

    def test_russian_terms_unchanged(self):
        texts = [
            "Российские учёные представили новую модель нейросети для анализа снимков.",
            "Нейросеть для диагностики заболеваний представили в России.",
        ]
        terms = extract_key_terms(texts, top_n=5)
        self.assertGreaterEqual(len(terms), 3)
        self.assertTrue(any("модел" in term.lower() or "нейросет" in term.lower() for term in terms))
        for term in terms:
            self.assertNotIn(term.lower().replace("ё", "е"), STOPWORDS_RU)


def _en_long_cluster(cluster_id: str = "cluster-pipeline") -> StoryCluster:
    article = _article(
        "pipeline-1",
        "OpenAI unveils GPT-5 model",
        EN_ARTICLE_TEXTS[0],
        "techcrunch",
        "TechCrunch",
    )
    return StoryCluster(id=cluster_id, title="OpenAI unveils GPT-5 model", articles=[article])


def _fake_storage():
    return SimpleNamespace(
        get_posts=lambda *args, **kwargs: [],
        recent_post_titles=lambda *args, **kwargs: [],
    )


def _news_post() -> GeneratedPost:
    return GeneratedPost(
        id="post-pipeline",
        channel_id="tech-ai",
        cluster_id="cluster-pipeline",
        format="story",
        text="<b>OpenAI unveils GPT-5 model</b>",
        sources=[{"title": "TechCrunch", "url": "https://example.com/1", "source": "TechCrunch"}],
    )


class PipelineLanguageTest(unittest.TestCase):
    def test_generate_posts_passes_channel_language(self):
        channel = ChannelConfig(id="tech-ai", title="Tech & AI", formats=["story"], language="en")
        post = _news_post()
        with mock.patch.object(pipeline, "analyze_cluster", return_value=Analysis()) as analyze_mock, \
                mock.patch.object(pipeline, "generate_post", return_value=post):
            pipeline.generate_posts(
                channel, [_en_long_cluster()], _pipeline_settings(), _fake_storage(), llm=None, max_posts=1
            )
        analyze_mock.assert_called_once()
        self.assertEqual(analyze_mock.call_args.kwargs.get("language"), "en")

    def test_digest_passes_channel_language(self):
        channel = ChannelConfig(id="tech-ai", title="Tech & AI", formats=["digest"], language="en")
        clusters = [_en_long_cluster("cluster-a"), _en_long_cluster("cluster-b")]
        digest = _news_post()
        digest.format = "digest"
        with mock.patch.object(pipeline, "analyze_cluster", return_value=Analysis()) as analyze_mock, \
                mock.patch.object(pipeline, "generate_digest", return_value=digest):
            pipeline.generate_posts(
                channel, clusters, _pipeline_settings(), _fake_storage(), llm=None, max_posts=1
            )
        self.assertEqual(analyze_mock.call_count, 2)
        for call in analyze_mock.call_args_list:
            self.assertEqual(call.kwargs.get("language"), "en")

    def test_preview_channel_passes_channel_language(self):
        channel = ChannelConfig(id="tech-ai", title="Tech & AI", formats=["story"], language="en")
        cluster = _en_long_cluster()
        with mock.patch.object(
            pipeline, "collect_channel_articles", return_value=([cluster.articles[0]], [])
        ), mock.patch.object(pipeline, "build_clusters", return_value=[cluster]), \
                mock.patch.object(pipeline, "analyze_cluster", return_value=Analysis()) as analyze_mock, \
                mock.patch.object(pipeline, "generate_post", return_value=_news_post()):
            pipeline.preview_channel(channel, _pipeline_settings(), _fake_storage(), limit=1)
        analyze_mock.assert_called_once()
        self.assertEqual(analyze_mock.call_args.kwargs.get("language"), "en")

    def test_pipeline_passes_russian_language_for_ru_channel(self):
        channel = ChannelConfig(id="tech-ai", title="Технологии и ИИ", formats=["story"], language="ru")
        with mock.patch.object(pipeline, "analyze_cluster", return_value=Analysis()) as analyze_mock, \
                mock.patch.object(pipeline, "generate_post", return_value=_news_post()):
            pipeline.generate_posts(
                channel, [_en_long_cluster()], _pipeline_settings("ru"), _fake_storage(), llm=None, max_posts=1
            )
        analyze_mock.assert_called_once()
        self.assertEqual(analyze_mock.call_args.kwargs.get("language"), "ru")


if __name__ == "__main__":
    unittest.main()
