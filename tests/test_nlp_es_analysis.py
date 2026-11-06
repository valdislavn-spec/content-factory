"""Тесты испаноязычного анализа кластера и экстрактивного fallback.

Проверяют испанский режим обязательного офлайн-анализа: испанские промпты и
шаблоны, валидацию ответов LLM по целевому языку, отсутствие кириллицы в
ES-анализе, испанские ключевые термины без английских/русских стоп-слов,
извлечение терминов из испанского текста и передачу языка канала из
конвейера. Русское и английское поведение по умолчанию не должно меняться.
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
from content_factory.nlp.generator import generate_post
from content_factory.nlp.keywords import extract_key_terms
from content_factory.nlp.lang import resolve_language
from content_factory.nlp.sentiment import detect_sentiment
from content_factory.utils import (
    STOPWORDS_EN,
    STOPWORDS_ES,
    STOPWORDS_RU,
    detect_text_language,
    tokenize,
)

PUBLISHED = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
EN_SETTINGS_VALUES = {"app.language": "en", "pipeline.max_text_chars": 15000}
RU_SETTINGS_VALUES = {"app.language": "ru", "pipeline.max_text_chars": 15000}
ES_SETTINGS_VALUES = {"app.language": "es", "pipeline.max_text_chars": 15000}
PIPELINE_SETTINGS_VALUES = {
    "app.language": "es",
    "pipeline.max_text_chars": 15000,
    "pipeline.min_cluster_chars": 200,
    "pipeline.min_post_chars": 220,
    "pipeline.banned_words": [],
    "pipeline.post_duplicate_window_hours": 72,
}


def _has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text or ""))


def _fake_settings(language: str = "es"):
    values = {
        "en": EN_SETTINGS_VALUES,
        "ru": RU_SETTINGS_VALUES,
        "es": ES_SETTINGS_VALUES,
    }[language]
    return SimpleNamespace(
        app={"language": language},
        pipeline={"max_text_chars": 15000},
        llm={"provider": "extractive"},
        raw={"llm": {"provider": "extractive"}},
        get=lambda dotted, default=None: values.get(dotted, default),
    )


def _pipeline_settings(language: str = "es"):
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


def _article(article_id, title, text, source_id, source_name, language="es"):
    return Article(
        id=article_id,
        title=title,
        url=f"https://es.example.com/{article_id}",
        source_id=source_id,
        source_name=source_name,
        published_at=PUBLISHED,
        text=text,
        language=language,
    )


ES_ARTICLE_TEXTS = (
    "El Gobierno de España aprobó este martes un nuevo paquete de medidas "
    "económicas. Según el Ejecutivo, el objetivo es reducir la inflación y "
    "proteger el empleo. La medida afecta a los ciudadanos y a las empresas del "
    "país.",
    "El Gobierno anunció un plan de ayudas para las empresas. La inflación se "
    "redujo hasta el 2,8% el mes pasado, informó el Ministerio de Economía. Los "
    "expertos consideran que la medida es clave para la recuperación.",
    "España aprueba nuevas medidas económicas. El Ejecutivo destaca que la "
    "inflación bajó al 2,8% y que el empleo creció un 1,5%. Según los analistas, "
    "el plan también beneficia a las pequeñas empresas.",
)

ES_ARTICLE_TITLES = (
    "España aprueba nuevas medidas económicas",
    "El Gobierno anuncia ayudas para las empresas",
    "La inflación baja al 2,8% en España",
)

ES_SOURCE_NAMES = (
    ("elpais", "El País"),
    ("elmundo", "El Mundo"),
    ("efe", "Agencia EFE"),
)


def _es_cluster() -> StoryCluster:
    articles = [
        _article(
            f"es-{index}",
            ES_ARTICLE_TITLES[index],
            ES_ARTICLE_TEXTS[index],
            *ES_SOURCE_NAMES[index],
        )
        for index in range(len(ES_ARTICLE_TEXTS))
    ]
    return StoryCluster(
        id="cluster-es",
        title="España aprueba nuevas medidas económicas",
        articles=articles,
        score=0.8,
        channel_id="noticias-es",
    )


def _es_small_cluster(source_count: int = 2) -> StoryCluster:
    """Короткий ES-кластер: резюме получает шаблонные вставки (coverage)."""
    articles = [
        _article(
            "small-es-1",
            "El Gobierno aprueba el plan económico",
            "El Gobierno aprobó el plan económico el martes.",
            "elpais",
            "El País",
        ),
        _article(
            "small-es-2",
            "El plan económico entra en vigor",
            "El plan económico entrará en vigor en enero.",
            "elmundo",
            "El Mundo",
        ),
    ][:source_count]
    return StoryCluster(
        id="cluster-es-small",
        title="El Gobierno aprueba el plan económico",
        articles=articles,
        channel_id="noticias-es",
    )


def _ru_small_cluster() -> StoryCluster:
    articles = [
        Article(
            id="ru-1", title="ЦБ сохранил ставку", url="https://rbc.ru/1",
            source_id="rbc", source_name="РБК", published_at=PUBLISHED,
            text="Банк России сохранил ключевую ставку на уровне 18%.", language="ru",
        ),
        Article(
            id="ru-2", title="Ставка осталась прежней", url="https://cnews.ru/2",
            source_id="cnews", source_name="CNews", published_at=PUBLISHED,
            text="Регулятор сохранил ставку 18%, инфляция замедлилась.", language="ru",
        ),
    ]
    return StoryCluster(
        id="cluster-ru-small",
        title="ЦБ сохранил ключевую ставку",
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
        self.calls = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None, **kwargs):
        self.prompts.append(prompt)
        self.systems.append(system)
        self.calls.append(prompt)
        if not self.replies:
            return ""
        return self.replies.pop(0)


class ScriptedAnalyzerLLM:
    """Отвечает валидными испанскими текстами на промпты анализатора."""

    name = "fake-es-analyzer"
    available = True

    def __init__(self):
        self.prompts = []
        self.systems = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None, **kwargs):
        self.prompts.append(prompt)
        self.systems.append(system)
        lowered = prompt.lower()
        if "escribe un resumen neutral" in lowered:
            return ES_VALID_SUMMARY
        if "redacta tres o cuatro puntos" in lowered:
            return ES_VALID_BULLETS
        if "haz dos cosas" in lowered:
            return ES_COMBINED_REPLY
        return ""


class UnavailableLLM:
    name = "unavailable"
    available = False

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, system="", max_tokens=None, temperature=None, **kwargs):
        self.calls += 1
        raise AssertionError("недоступная LLM не должна вызываться")


ES_VALID_SUMMARY = (
    "El Gobierno de España aprobó un plan de ayudas para las empresas. "
    "La inflación se redujo hasta el 2,8% el mes pasado según el Ministerio de "
    "Economía. Los expertos consideran que la medida es clave para la recuperación."
)
ES_VALID_BULLETS = (
    "El plan incluye ayudas directas para las pequeñas empresas.\n"
    "La inflación bajó al 2,8% el mes pasado.\n"
    "Los expertos ven la medida clave para la recuperación."
)
ES_COMBINED_REPLY = (
    "RESUMEN: " + ES_VALID_SUMMARY + "\n"
    "PUNTOS:\n"
    "- El plan incluye ayudas directas para las pequeñas empresas.\n"
    "- La inflación bajó al 2,8% el mes pasado.\n"
    "- Los expertos ven la medida clave para la recuperación."
)
RU_LLM_SUMMARY = (
    "Правительство Испании одобрило план помощи компаниям. Инфляция снизилась "
    "до 2,8% в прошлом месяце, сообщило Министерство экономики."
)


class SpanishAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = _fake_settings("es")
        cls.cluster = _es_cluster()
        cls.analysis = analyze_cluster(cls.cluster, cls.settings, language="es")

    def test_no_cyrillic_in_any_analysis_field(self):
        analysis = self.analysis
        texts = [
            analysis.summary,
            " ".join(analysis.bullets),
            " ".join(analysis.key_terms),
            " ".join(analysis.entities),
        ]
        for perspective in analysis.perspectives:
            texts.extend([perspective.get("quote", ""), perspective.get("angle", "")])
        for text in texts:
            self.assertFalse(_has_cyrillic(text), f"кириллица в ES-анализе: {text!r}")

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

    def test_key_terms_are_spanish_without_stopwords(self):
        terms = self.analysis.key_terms
        self.assertGreaterEqual(len(terms), 3)
        lowered = {term.lower() for term in terms}
        for term in terms:
            self.assertFalse(_has_cyrillic(term))
            self.assertNotIn(term.lower(), STOPWORDS_ES)
            self.assertNotIn(term.lower(), STOPWORDS_EN)
            self.assertNotIn(term.lower(), STOPWORDS_RU)
        self.assertTrue(
            lowered & {"inflación", "gobierno", "españa", "medidas", "empleo", "empresas"},
            f"нет испанских терминов: {terms}",
        )

    def test_coverage_sentence_is_spanish(self):
        analysis = analyze_cluster(_es_small_cluster(2), self.settings, language="es")
        self.assertIn("De esto informan 2 fuentes: El País, El Mundo.", analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))

    def test_coverage_sentence_singular_is_spanish(self):
        analysis = analyze_cluster(_es_small_cluster(1), self.settings, language="es")
        self.assertIn("De esto informa El País.", analysis.summary)
        self.assertNotIn("fuentes:", analysis.summary)

    def test_entities_are_latin_proper_names(self):
        for entity in self.analysis.entities:
            self.assertFalse(_has_cyrillic(entity), entity)
        self.assertIn("España", self.analysis.entities)

    def test_numbers_and_sources(self):
        self.assertTrue(self.analysis.numbers)
        self.assertIn("2,8%", self.analysis.numbers)
        self.assertEqual(self.analysis.source_count, 3)
        self.assertEqual(
            self.analysis.source_names, ["El País", "El Mundo", "Agencia EFE"]
        )

    def test_confidence_in_range(self):
        self.assertGreaterEqual(self.analysis.confidence, 0.0)
        self.assertLessEqual(self.analysis.confidence, 1.0)

    def test_russian_coverage_and_templates_unchanged(self):
        analysis = analyze_cluster(_ru_small_cluster(), _fake_settings("ru"))
        self.assertTrue(_has_cyrillic(analysis.summary))
        self.assertTrue(_has_cyrillic(" ".join(analysis.bullets)))
        self.assertNotIn("De esto informan", analysis.summary)
        self.assertNotIn("Temas clave", analysis.summary)

    def test_language_from_settings_resolved_to_spanish(self):
        self.assertEqual(resolve_language(settings=_fake_settings("es")), "es")

    def test_explicit_language_wins_over_article_language(self):
        # Источники помечают статьи app.language (en/ru), но канал es важнее.
        articles = [
            _article(
                "lang-1",
                "España aprueba nuevas medidas económicas",
                ES_ARTICLE_TEXTS[0],
                "elpais",
                "El País",
                language="en",
            )
        ]
        self.assertEqual(resolve_language(articles=articles), "en")
        self.assertEqual(resolve_language(explicit="es", articles=articles), "es")
        cluster = StoryCluster(
            id="cluster-lang", title="España aprueba nuevas medidas económicas",
            articles=articles,
        )
        analysis = analyze_cluster(
            cluster, _fake_settings("ru"), language="es"
        )
        self.assertFalse(_has_cyrillic(analysis.summary))
        self.assertIn("España", analysis.summary)

    def test_empty_cluster_does_not_crash(self):
        analysis = analyze_cluster(StoryCluster(id="empty", title=""), _fake_settings("es"), language="es")
        self.assertIsInstance(analysis, Analysis)


class SpanishLLMAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = _fake_settings("es")
        cls.cluster = _es_cluster()

    def test_valid_spanish_llm_summary_and_bullets_are_used(self):
        llm = ScriptedAnalyzerLLM()
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="es")
        self.assertIn("El Gobierno de España aprobó un plan de ayudas", analysis.summary)
        self.assertIn("La inflación se redujo hasta el 2,8%", analysis.summary)
        self.assertTrue(analysis.bullets)
        for bullet in analysis.bullets:
            self.assertFalse(_has_cyrillic(bullet))
        self.assertFalse(_has_cyrillic(analysis.summary))

    def test_prompts_and_system_are_spanish(self):
        llm = ScriptedAnalyzerLLM()
        analyze_cluster(self.cluster, self.settings, llm=llm, language="es")
        self.assertTrue(llm.prompts)
        for prompt in llm.prompts:
            self.assertIsNone(_CYRILLIC_RE.search(prompt), prompt)
            self.assertIn("Noticia:", prompt)
        self.assertTrue(llm.systems)
        for system in llm.systems:
            self.assertIn("español", system)
            self.assertIsNone(_CYRILLIC_RE.search(system))

    def test_russian_llm_answer_is_rejected_for_spanish_channel(self):
        llm = FakeLLM([RU_LLM_SUMMARY, RU_LLM_SUMMARY])
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="es")
        self.assertNotIn("Правительство", analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))
        self.assertFalse(_has_cyrillic(" ".join(analysis.bullets)))
        # Откат на экстрактивный анализатор.
        self.assertTrue(analysis.summary)

    def test_markdown_garbage_is_rejected(self):
        llm = FakeLLM(['```json\n{"summary": "нельзя", "url": "https://fake.example"}\n```'])
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="es")
        self.assertNotIn("нельзя", analysis.summary)
        self.assertNotIn("fake.example", analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))

    def test_hallucinated_number_is_rejected(self):
        llm = FakeLLM(
            [
                "El Gobierno de España aprobó un plan de 999 millones de euros. "
                "La inflación bajó al 2,8% el mes pasado.",
                ES_VALID_BULLETS,
            ]
        )
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="es")
        self.assertNotIn("999", analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))

    def test_combined_mode_parses_spanish_markers(self):
        settings = SimpleNamespace(
            app={"language": "es"},
            pipeline={"max_text_chars": 15000},
            llm={"provider": "extractive"},
            raw={"llm": {"provider": "extractive"}},
            get=lambda dotted, default=None: {
                "app.language": "es",
                "pipeline.max_text_chars": 15000,
                "llm.optimize.combined_analysis": True,
            }.get(dotted, default),
        )
        llm = ScriptedAnalyzerLLM()
        analysis = analyze_cluster(self.cluster, settings, llm=llm, language="es")
        self.assertIn("El Gobierno de España aprobó un plan de ayudas", analysis.summary)
        self.assertGreaterEqual(len(analysis.bullets), 3)
        for bullet in analysis.bullets:
            self.assertFalse(_has_cyrillic(bullet))

    def test_unavailable_llm_is_not_called(self):
        llm = UnavailableLLM()
        analysis = analyze_cluster(self.cluster, self.settings, llm=llm, language="es")
        self.assertEqual(llm.calls, 0)
        self.assertTrue(analysis.summary)
        self.assertFalse(_has_cyrillic(analysis.summary))


class SpanishKeyTermsTest(unittest.TestCase):
    TEXTS = list(ES_ARTICLE_TEXTS)

    def test_spanish_terms_auto_detected(self):
        terms = extract_key_terms(self.TEXTS, top_n=8)
        self.assertGreaterEqual(len(terms), 3)
        for term in terms:
            self.assertFalse(_has_cyrillic(term))
            self.assertNotIn(term.lower(), STOPWORDS_ES)
        lowered = {term.lower() for term in terms}
        self.assertTrue(
            lowered & {"inflación", "gobierno", "españa", "medidas", "empleo"},
            f"нет испанских терминов: {terms}",
        )

    def test_spanish_terms_explicit_language(self):
        auto = extract_key_terms(self.TEXTS, top_n=6)
        explicit = extract_key_terms(self.TEXTS, top_n=6, language="es")
        self.assertEqual(auto, explicit)

    def test_spanish_terms_without_english_stopwords(self):
        terms = extract_key_terms(self.TEXTS, top_n=8, language="es")
        english_news = {"the", "and", "said", "from", "that", "with", "this", "news"}
        for term in terms:
            self.assertNotIn(term.lower(), english_news, term)

    def test_accented_words_are_not_truncated(self):
        terms = extract_key_terms(
            ["La inflación y la economía española crecieron.", "La inflación se moderó."],
            top_n=5,
            language="es",
        )
        lowered = [term.lower() for term in terms]
        self.assertIn("inflación", lowered)
        self.assertNotIn("inflaci", lowered)

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


class DetectAndTokenizeSpanishTest(unittest.TestCase):
    def test_spanish_text_detected(self):
        self.assertEqual(detect_text_language(ES_ARTICLE_TEXTS), "es")

    def test_english_text_still_detected(self):
        english = (
            "OpenAI introduced its new GPT-5 model. The company said the model is "
            "available to developers through the API."
        )
        self.assertEqual(detect_text_language([english]), "en")

    def test_russian_text_still_detected(self):
        self.assertEqual(
            detect_text_language(["Банк России сохранил ключевую ставку на уровне 18%."]),
            "ru",
        )

    def test_spanish_tokenize_removes_stopwords_keeps_terms(self):
        tokens = tokenize(
            "El Gobierno de España aprobó un plan para las empresas y la inflación.",
            language="es",
        )
        self.assertIn("gobierno", tokens)
        self.assertIn("españa", tokens)
        self.assertIn("inflación", tokens)
        for stopword in ("el", "de", "para", "las", "y", "la"):
            self.assertNotIn(stopword, tokens)

    def test_default_tokenize_still_russian(self):
        self.assertEqual(
            tokenize("Российский рынок вырос на 5 процентов"),
            tokenize("Российский рынок вырос на 5 процентов", language="ru"),
        )


class ExtractiveSpanishTest(unittest.TestCase):
    def test_spanish_abbreviations_do_not_split_sentences(self):
        text = (
            "El Sr. García llegó a EE. UU. el lunes. Después habló con la prensa. "
            "El Dr. Pérez confirmó la noticia."
        )
        sentences = split_sentences(text)
        self.assertEqual(len(sentences), 3)
        self.assertIn("EE. UU.", sentences[0])
        self.assertIn("Sr. García", sentences[0])

    def test_question_and_exclamation_marks_are_handled(self):
        text = "¿Qué pasó con el plan? El Gobierno no lo confirmó. ¡Atención! La prensa espera."
        sentences = split_sentences(text)
        self.assertEqual(len(sentences), 4)
        self.assertTrue(sentences[0].startswith("¿"))
        self.assertTrue(sentences[2].startswith("¡"))

    def test_short_spanish_question_is_kept(self):
        sentences = split_sentences("El plan está listo. ¿Qué pasó?")
        self.assertIn("¿Qué pasó?", sentences)

    def test_summarize_texts_returns_spanish_summary(self):
        summary = summarize_texts(list(ES_ARTICLE_TEXTS), max_sentences=3, language="es")
        self.assertTrue(summary)
        self.assertFalse(_has_cyrillic(summary))
        self.assertLessEqual(len(split_sentences(summary)), 3)
        self.assertTrue(summary.rstrip().endswith((".", "!", "?", "…")))


class SpanishSentimentTest(unittest.TestCase):
    def test_positive_spanish_text(self):
        label, score = detect_sentiment(
            "El crecimiento económico fue un éxito y la empresa logró un récord "
            "de beneficios."
        )
        self.assertEqual(label, "positive")
        self.assertGreater(score, 0)

    def test_negative_spanish_text(self):
        label, score = detect_sentiment(
            "La caída de las ventas provocó pérdidas y una crisis para la empresa."
        )
        self.assertEqual(label, "negative")
        self.assertLess(score, 0)

    def test_spanish_negation_flips_polarity(self):
        label, score = detect_sentiment("El empleo no creció y las ventas nunca aumentaron.")
        self.assertEqual(label, "negative")
        self.assertLess(score, 0)

    def test_spanish_intensifier_increases_score(self):
        plain = detect_sentiment("El resultado fue positivo.")[1]
        strong = detect_sentiment("El resultado fue muy positivo.")[1]
        self.assertGreater(strong, plain)

    def test_russian_and_english_sentiment_unchanged(self):
        self.assertEqual(detect_sentiment("Компания показала рекордный рост и прибыль.")[0], "positive")
        self.assertEqual(detect_sentiment("Авария и кризис привели к потерям.")[0], "negative")
        self.assertEqual(
            detect_sentiment("The company reported record profit and growth.")[0],
            "positive",
        )
        self.assertEqual(
            detect_sentiment("The crisis and losses hit the company.")[0],
            "negative",
        )


def _es_long_cluster(cluster_id: str = "cluster-pipeline-es") -> StoryCluster:
    article = _article(
        "pipeline-es-1",
        "España aprueba nuevas medidas económicas",
        ES_ARTICLE_TEXTS[0],
        "elpais",
        "El País",
    )
    return StoryCluster(
        id=cluster_id,
        title="España aprueba nuevas medidas económicas",
        articles=[article],
    )


def _fake_storage():
    return SimpleNamespace(
        get_posts=lambda *args, **kwargs: [],
        recent_post_titles=lambda *args, **kwargs: [],
    )


def _news_post() -> GeneratedPost:
    return GeneratedPost(
        id="post-pipeline-es",
        channel_id="noticias-es",
        cluster_id="cluster-pipeline-es",
        format="story",
        text="<b>España aprueba nuevas medidas económicas</b>",
        sources=[
            {
                "title": "El País",
                "url": "https://example.com/1",
                "source": "El País",
            }
        ],
    )


class PipelineSpanishLanguageTest(unittest.TestCase):
    def test_generate_posts_passes_channel_language_es(self):
        channel = ChannelConfig(
            id="noticias-es", title="Noticias España", formats=["story"], language="es"
        )
        post = _news_post()
        with mock.patch.object(pipeline, "analyze_cluster", return_value=Analysis()) as analyze_mock, \
                mock.patch.object(pipeline, "generate_post", return_value=post):
            pipeline.generate_posts(
                channel,
                [_es_long_cluster()],
                _pipeline_settings("es"),
                _fake_storage(),
                llm=None,
                max_posts=1,
            )
        analyze_mock.assert_called_once()
        self.assertEqual(analyze_mock.call_args.kwargs.get("language"), "es")

    def test_digest_passes_channel_language_es(self):
        channel = ChannelConfig(
            id="noticias-es", title="Noticias España", formats=["digest"], language="es"
        )
        clusters = [_es_long_cluster("cluster-a"), _es_long_cluster("cluster-b")]
        digest = _news_post()
        digest.format = "digest"
        with mock.patch.object(pipeline, "analyze_cluster", return_value=Analysis()) as analyze_mock, \
                mock.patch.object(pipeline, "generate_digest", return_value=digest):
            pipeline.generate_posts(
                channel,
                clusters,
                _pipeline_settings("es"),
                _fake_storage(),
                llm=None,
                max_posts=1,
            )
        self.assertEqual(analyze_mock.call_count, 2)
        for call in analyze_mock.call_args_list:
            self.assertEqual(call.kwargs.get("language"), "es")


class SpanishScenarioTest(unittest.TestCase):
    """Сценарная проверка: канал es + пара испанских статей -> испанский пост."""

    def test_channel_es_generates_spanish_post_end_to_end(self):
        channel = ChannelConfig(
            id="noticias-es",
            title="Noticias España",
            language="es",
            tone="expert",
            formats=["story"],
            hashtags=["#Economía"],
            cta="Lee nuestro canal para más noticias.",
            emoji=True,
            timezone_offset=1,
            max_post_chars=3200,
            topics=["economia"],
        )
        cluster = _es_cluster()
        settings = _fake_settings("es")
        analysis = analyze_cluster(cluster, settings, language=channel.language)
        post = generate_post(cluster, analysis, channel, settings, fmt="story")

        self.assertEqual(post.meta["language"], "es")
        self.assertFalse(_has_cyrillic(post.text))
        self.assertFalse(_has_cyrillic(post.plain_text))
        self.assertIn("Claves:", post.text)
        self.assertIn("Fuentes:", post.text)
        self.assertIn("#Economía", post.text)
        self.assertIn("Lee nuestro canal para más noticias.", post.text)
        self.assertNotIn("Главное", post.text)
        self.assertNotIn("Источники", post.text)
        self.assertTrue(post.sources)
        self.assertEqual(post.meta["quality_issues"], [])

        # Резюме анализа — тоже испанское и без кириллицы.
        self.assertFalse(_has_cyrillic(analysis.summary))
        self.assertFalse(_has_cyrillic(" ".join(analysis.bullets)))


if __name__ == "__main__":
    unittest.main()
