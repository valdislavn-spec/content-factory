"""Тесты детерминированной рубрики качества постов и опционального гейта.

Покрытие:

* API ``content_factory.nlp.quality``: ``QualityReport``/``QualityIssue``,
  ``score_post`` для ``GeneratedPost`` и строки;
* коды всех измерений рубрики (длина, HTML, ссылки, хэштеги, CTA, повторы,
  капс, читабельность, факты, кликбейт RU/EN/ES, markdown, эмодзи, хук);
* монотонность балла и границы 0..100;
* «хороший»/«плохой» фикстуры: >= 80 и < 50;
* гейт в ``pipeline.quality_issues``: по умолчанию выключен, при включении
  добавляет блокеры, ``warn``-режим и конфиг-словарь;
* интеграция гейта в ``pipeline.generate_posts`` (пост отклоняется);
* детерминированные улучшения генератора: лид без эха заголовка, конкретные
  цифры в тексте, добор хэштегов, правила качества в LLM-промптах RU/EN/ES.
"""

from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from content_factory import pipeline as pipeline_module
from content_factory.config import Settings, load_channels
from content_factory.models import (
    Analysis,
    Article,
    ChannelConfig,
    GeneratedPost,
    StoryCluster,
)
from content_factory.nlp.analyzer import analyze_cluster
from content_factory.nlp.generator import (
    _llm_headline,
    _system_prompt,
    generate_post,
)
from content_factory.utils import strip_html
from content_factory.nlp.quality import (
    BLOCKER,
    MAJOR,
    MINOR,
    QualityIssue,
    QualityReport,
    score_post,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)

TECH_TEXTS = (
    "OpenAI представила новую модель GPT-5. Компания сообщила, что модель доступна "
    "разработчикам через API уже с 18 октября. По данным бенчмарков, качество ответов "
    "выросло на 25% по сравнению с предыдущей версией. Новая модель поддерживает "
    "контекст до 200 тысяч токенов. Эксперты отмечают рост интереса к решениям.",
    "Компания OpenAI анонсировала модель GPT-5. Новая версия доступна через API, "
    "сообщает CNews. В компании заявили о росте производительности на 25% и поддержке "
    "контекста до 200 тысяч токенов. Разработчики смогут использовать модель.",
    "OpenAI выпустила GPT-5. Модель стала доступна разработчикам, пишет 3DNews. Ранее "
    "компания обещала улучшить качество ответов и увеличить контекст.",
)

EN_TECH_TEXTS = (
    "OpenAI introduced its new GPT-5 model. The company said the model is available "
    "to developers through the API starting October 18. The new model supports a "
    "context window of up to 200 thousand tokens. Developers can use the model to "
    "build applications.",
    "OpenAI unveiled GPT-5 on Tuesday. The API is available to developers today. "
    "Benchmarks show a 25% quality improvement over the previous version.",
    "OpenAI released GPT-5. The company says the model is available in the API.",
)

ES_TECH_TEXTS = (
    "El Gobierno de España aprueba nuevas medidas económicas. El Ejecutivo aprobó un "
    "nuevo paquete de medidas para reducir la inflación y proteger el empleo. La "
    "inflación se redujo hasta el 2,8% el mes pasado, según el Ministerio de Economía.",
    "El Gobierno español anuncia un plan de ayudas para las empresas. Las medidas "
    "buscan reducir la inflación, que bajó al 2,8%.",
    "España aprueba nuevas medidas económicas. El Ejecutivo destaca la bajada de la "
    "inflación al 2,8%.",
)

SOURCES = [
    {"title": "Habr", "url": "https://tech.example/1", "source": "Habr"},
    {"title": "CNews", "url": "https://tech.example/2", "source": "CNews"},
]

GOOD_LINK = '<a href="https://tech.example/1">Habr</a>'

GOOD_BODY = (
    "OpenAI выпустила новую модель GPT-5.\n\n"
    "Компания сообщила, что качество ответов выросло на 25% по сравнению с "
    "прошлой версией, а контекст вырос до 200 тысяч токенов.\n\n"
    "Разработчики уже могут подключить модель через API с 18 октября.\n\n"
    "Источники: " + GOOD_LINK + "\n\n"
    "Больше разборов — в нашем канале.\n\n"
    "#технологии #ИИ"
)


def _settings(**pipeline_overrides) -> Settings:
    settings = Settings.load(load_env=False)
    overrides = dict(pipeline_overrides)
    settings.raw.setdefault("pipeline", {}).update(overrides)
    return settings


def _channel(
    language: str = "ru",
    channel_id: str = "tech-ai",
    **overrides,
) -> ChannelConfig:
    params = {
        "id": channel_id,
        "title": "Технологии и ИИ" if language == "ru" else "Tech & AI",
        "language": language,
        "tone": "expert",
        "formats": ["story"],
        "hashtags": ["#технологии", "#ИИ"] if language == "ru" else ["#AI", "#Tech"],
        "cta": "Больше разборов — в нашем канале."
        if language == "ru"
        else "Follow the channel for more tech news.",
        "emoji": True,
        "timezone_offset": 3,
        "max_post_chars": 3500,
        "topics": ["технологии"] if language == "ru" else ["ai"],
    }
    params.update(overrides)
    return ChannelConfig(**params)


def _article(article_id: str, title: str, text: str, url: str) -> Article:
    return Article(
        id=article_id,
        title=title,
        url=url,
        source_id="test",
        source_name="Test",
        published_at=PUBLISHED,
        text=text,
    )


def _cluster(
    title: str = "OpenAI представила новую модель GPT-5",
    texts=TECH_TEXTS,
    domain: str = "tech.example",
) -> StoryCluster:
    articles = [
        _article(
            "a{}".format(index),
            title if index == 0 else "{}: детали".format(title),
            text,
            "https://{}/article/{}".format(domain, index),
        )
        for index, text in enumerate(texts)
    ]
    return StoryCluster(id="cluster-quality", title=title, articles=articles, score=0.8)


def _post(
    text: str = GOOD_BODY,
    *,
    sources=None,
    hashtags=None,
    fmt: str = "story",
) -> GeneratedPost:
    return GeneratedPost(
        id="post-quality",
        channel_id="tech-ai",
        cluster_id="cluster-quality",
        format=fmt,
        text=text,
        hashtags=list(hashtags or []),
        sources=list(SOURCES if sources is None else sources),
    )


def _generated_post(
    language: str = "ru",
    fmt: str = "story",
):
    """Реальный пост детерминированного генератора + канал + настройки."""
    settings = _settings()
    channel = _channel(language=language)
    if language == "en":
        cluster = _cluster(
            "OpenAI introduces GPT-5: what we know", EN_TECH_TEXTS, "tech.example"
        )
    elif language == "es":
        cluster = _cluster(
            "El Gobierno de España aprueba nuevas medidas económicas",
            ES_TECH_TEXTS,
            "es.example",
        )
    else:
        cluster = _cluster()
    analysis = analyze_cluster(cluster, settings, language=language)
    post = generate_post(cluster, analysis, channel, settings, fmt=fmt)
    return post, channel, settings


def _codes(report: QualityReport):
    return set(report.codes())


def _blocks(post: GeneratedPost):
    return [
        strip_html(block).strip()
        for block in post.text.split("\n\n")
        if strip_html(block).strip()
    ]


def _broken_text_scores() -> str:
    """Текст, который проходит старые проверки конвейера, но слаб по рубрике."""
    return (
        "<b>СРОЧНО: ВСЁ РУХНУЛО</b>\n\n"
        "Ситуация на рынке изменилась. Ситуация на рынке изменилась. "
        "Инвесторы не понимают, что происходит. Инвесторы не понимают, что происходит. "
        "Вы не поверите, но это просто шок. "
        "Одни говорят, что это временно, другие — что это надолго. "
        "Никто не знает, чем всё закончится, но все внимательно следят за новостями. "
        "Новости появляются каждый час, а ясности всё нет. "
        "Рынок ждёт новых сигналов от регулятора. "
        "Регулятор пока молчит, и это тревожит участников. "
        "Эксперты советуют сохранять спокойствие. "
        "Наблюдаем за развитием ситуации.\n\n"
        "<a href=\"https://tech.example/1\">Habr</a>"
    )


class QualityApiTest(unittest.TestCase):
    def test_report_dataclasses_and_dicts(self):
        issue = QualityIssue(
            code="x", severity=MAJOR, message="проблема", penalty=5, dimension="test"
        )
        report = QualityReport(score=42, issues=[issue], metrics={"a": 1})
        self.assertTrue(report.has_blockers() is False)
        self.assertEqual(report.codes(), ["x"])
        self.assertEqual(report.messages(), ["проблема"])
        data = report.as_dict()
        self.assertEqual(data["score"], 42)
        self.assertEqual(data["issues"][0]["code"], "x")
        self.assertEqual(data["metrics"]["a"], 1)
        self.assertEqual(issue.as_dict()["severity"], MAJOR)
        self.assertIsInstance(report.score, int)

    def test_string_input_is_supported(self):
        report = score_post(
            "OpenAI выпустила GPT-5.\n\nМодель доступна разработчикам с 18 октября.",
            _channel(),
            _settings(),
        )
        self.assertIsInstance(report, QualityReport)
        self.assertGreaterEqual(report.score, 0)
        self.assertLessEqual(report.score, 100)
        # Строка не несёт post.sources: отсутствие источников не считается блокером.
        self.assertNotIn("no_sources", _codes(report))

    def test_empty_post_scores_zero_with_blocker(self):
        report = score_post(_post(text="", sources=[]), _channel(), _settings())
        self.assertEqual(report.score, 0)
        self.assertIn("empty_text", _codes(report))
        self.assertTrue(report.has_blockers())

    def test_score_is_deterministic_and_bounded(self):
        post, channel, settings = _generated_post()
        first = score_post(post, channel, settings)
        second = score_post(post, channel, settings)
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.codes(), second.codes())
        self.assertEqual(first.metrics, second.metrics)
        for post, ch in (
            (_post(), _channel()),
            (_post(text="x", sources=[]), _channel()),
        ):
            report = score_post(post, ch, settings)
            self.assertGreaterEqual(report.score, 0)
            self.assertLessEqual(report.score, 100)


class GoodAndBadFixturesTest(unittest.TestCase):
    def test_generated_good_posts_score_at_least_80(self):
        for language in ("ru", "en", "es"):
            with self.subTest(language=language):
                post, channel, settings = _generated_post(language)
                report = score_post(post, channel, settings)
                self.assertGreaterEqual(
                    report.score,
                    80,
                    "{}: {} {}".format(language, report.score, report.codes()),
                )
                self.assertFalse(report.has_blockers(), report.codes())

    def test_handcrafted_good_fixture_scores_at_least_80(self):
        report = score_post(_post(), _channel(), _settings())
        self.assertGreaterEqual(report.score, 80, report.codes())
        self.assertFalse(report.has_blockers(), report.codes())

    def test_bad_fixture_scores_below_50(self):
        bad = _post(
            text="СРОЧНО!!! ШОК!!! Вы не поверите: рынок рухнул. ПОДПИСЫВАЙТЕСЬ!!!",
            sources=[],
        )
        report = score_post(bad, _channel(), _settings())
        self.assertLess(report.score, 50)
        self.assertIn("too_short", _codes(report))
        self.assertIn("clickbait", _codes(report))
        self.assertIn("all_caps", _codes(report))
        self.assertIn("hashtags_missing", _codes(report))

    def test_score_monotonicity_on_degradation(self):
        settings = _settings()
        channel = _channel()
        base = score_post(_post(), channel, settings).score
        degraded = [
            _post(text=GOOD_BODY + "\n\nВы не поверите, это просто шок!"),
            _post(text=GOOD_BODY + "\n\nСРОЧНО ПОДПИСЫВАЙТЕСЬ И ДЕЛИТЕСЬ"),
            _post(text=GOOD_BODY + "\n\nТекст с **markdown** разметкой."),
            _post(sources=[]),
            _post(text=GOOD_BODY.replace("#технологии #ИИ", "")),
            _post(text=GOOD_BODY + "\n\n" + GOOD_BODY.split("\n\n")[1]),
        ]
        scores = [score_post(post, channel, settings).score for post in degraded]
        for score in scores:
            self.assertLessEqual(score, base)
        self.assertLess(scores[3], base)  # нет источников
        self.assertLess(scores[4], base)  # нет хэштегов
        self.assertLess(scores[0], base)  # кликбейт
        self.assertLess(scores[1], base)  # капс
        self.assertLess(scores[2], base)  # markdown


class RubricCodesTest(unittest.TestCase):
    def setUp(self):
        self.settings = _settings()
        self.channel = _channel()

    def _codes_for(self, post, channel=None, settings=None):
        return _codes(score_post(post, channel or self.channel, settings or self.settings))

    def test_length_codes(self):
        short = _post(text="Короткий текст без фактов.")
        self.assertIn("too_short", self._codes_for(short))
        long_text = "Слово. " * 1500
        self.assertIn("too_long", self._codes_for(_post(text=long_text)))

    def test_structure_and_hook_codes(self):
        no_structure = _post(
            text="Один блок текста без структуры и без абзацев. " * 8
        )
        self.assertIn("no_structure", self._codes_for(no_structure))
        long_hook = _post(
            text="<b>{}</b>\n\nВторой абзац с фактом за 2026 год и числом 25%.".format(
                "Очень длинный заголовок " * 8
            )
        )
        self.assertIn("weak_hook", self._codes_for(long_hook))
        echo = _post(
            text="<b>OpenAI выпустила GPT-5</b>\n\n"
            "OpenAI выпустила GPT-5.\n\n"
            "<a href=\"https://tech.example/1\">Habr</a>\n\n#технологии #ИИ"
        )
        self.assertIn("hook_echo", self._codes_for(echo))

    def test_bullet_list_counts_as_structure(self):
        bullets = (
            "<b>OpenAI выпустила GPT-5</b>\n"
            "▪️ Качество ответов выросло на 25% 18 октября.\n"
            "▪️ Контекст увеличен до 200 тысяч токенов.\n"
            "Источники: <a href=\"https://tech.example/1\">Habr</a>\n"
            "Больше разборов — в нашем канале.\n"
            "#технологии #ИИ"
        )
        report = score_post(_post(text=bullets), self.channel, self.settings)
        self.assertNotIn("no_structure", report.codes())
        self.assertGreaterEqual(report.metrics.get("bullets", 0), 2)

    def test_html_and_source_codes(self):
        broken = _post(text="<b>Незакрытый тег\n\n<a href=\"https://tech.example/1\">Habr</a>")
        self.assertIn("broken_html", self._codes_for(broken))
        unsupported = _post(text="<div>" + GOOD_BODY + "</div>")
        self.assertIn("unsupported_tags", self._codes_for(unsupported))
        plain_url = _post(
            text=GOOD_BODY.replace(GOOD_LINK, "https://tech.example/1")
        )
        self.assertIn("plain_url", self._codes_for(plain_url))
        no_links = _post(text=GOOD_BODY.replace(GOOD_LINK, "Habr"))
        self.assertIn("missing_source_links", self._codes_for(no_links))
        no_sources = _post(sources=[])
        self.assertIn("no_sources", self._codes_for(no_sources))

    def test_hashtag_codes(self):
        none = _post(text=GOOD_BODY.replace("\n\n#технологии #ИИ", ""))
        self.assertIn("hashtags_missing", self._codes_for(none))
        one = _post(text=GOOD_BODY.replace("#технологии #ИИ", "#технологии"))
        self.assertIn("hashtags_low", self._codes_for(one))
        many = _post(
            text=GOOD_BODY.replace(
                "#технологии #ИИ",
                " ".join("#тег{}".format(index) for index in range(10)),
            )
        )
        self.assertIn("hashtags_high", self._codes_for(many))

    def test_cta_code(self):
        no_cta = _post(
            text=GOOD_BODY.replace("Больше разборов — в нашем канале.", "Просто текст.")
        )
        self.assertIn("cta_missing", self._codes_for(no_cta))

    def test_duplicate_sentence_code(self):
        duplicate = _post(
            text=GOOD_BODY + "\n\nOpenAI выпустила новую модель GPT-5."
        )
        self.assertIn("duplicate_sentences", self._codes_for(duplicate))

    def test_caps_and_punctuation_codes(self):
        caps = _post(
            text=GOOD_BODY.replace(
                "Компания сообщила", "КОМПАНИЯ СООБЩИЛА ОГРОМНЫЙ РОСТ"
            )
        )
        codes = self._codes_for(caps)
        self.assertIn("all_caps", codes)
        shout = _post(text=GOOD_BODY + "\n\nЭто правда???")
        self.assertIn("punctuation_shout", self._codes_for(shout))

    def test_clickbait_codes_for_three_languages(self):
        cases = (
            ("ru", "Вы не поверите, но это просто шок!"),
            ("en", "You won't believe this shocking story!"),
            ("es", "No vas a creer esta noticia increíble."),
        )
        for language, phrase in cases:
            with self.subTest(language=language):
                channel = _channel(language=language)
                report = score_post(
                    _post(text=GOOD_BODY + "\n\n" + phrase), channel, self.settings
                )
                self.assertIn("clickbait", report.codes())

    def test_markdown_and_placeholder_codes(self):
        markdown = _post(text=GOOD_BODY + "\n\n**Жирный** маркdown.")
        self.assertIn("markdown_leak", self._codes_for(markdown))
        placeholder = _post(text=GOOD_BODY + "\n\nTODO: добавить текст {{title}}")
        self.assertIn("placeholder_text", self._codes_for(placeholder))

    def test_emoji_policy_code(self):
        no_emoji_channel = _channel(emoji=False)
        report = score_post(_post(text="🤖 " + GOOD_BODY), no_emoji_channel, self.settings)
        self.assertIn("emoji_policy", report.codes())

    def test_fact_density_and_weak_fact_style_codes(self):
        no_facts = _post(
            text="<b>Новость дня</b>\n\nСитуация меняется, и это важно для всех. "
            "Люди ждут новостей и следят за ситуацией.\n\n"
            + GOOD_LINK
            + "\n\nБольше разборов — в нашем канале.\n\n#технологии #ИИ"
        )
        self.assertIn("fact_density", self._codes_for(no_facts))
        weak_style = _post(
            text=GOOD_BODY.replace(
                "Компания сообщила, что качество ответов выросло на 25% по сравнению с "
                "прошлой версией, а контекст вырос до 200 тысяч токенов.",
                "Фигурирующие цифры: 25%.",
            )
        )
        self.assertIn("weak_fact_style", self._codes_for(weak_style))

    def test_readability_code(self):
        long_sentence = (
            "Компания сообщила что модель доступна разработчикам через API уже с "
            "восемнадцатого октября и при этом стоимость использования снизилась на "
            "тридцать процентов по сравнению с предыдущей версией модели и теперь "
            "доступна всем желающим без ограничений по странам и регионам мира "
            "включая самые отдалённые уголки планеты и это очень важно для всех."
        )
        text = (
            "<b>OpenAI выпустила GPT-5</b>\n\n"
            + long_sentence
            + "\n\n"
            + GOOD_LINK
            + "\n\nБольше разборов — в нашем канале.\n\n#технологии #ИИ"
        )
        self.assertIn("long_sentence", self._codes_for(_post(text=text)))


class QualityGateTest(unittest.TestCase):
    def setUp(self):
        self.channel = _channel()
        self.weak_post = _post(text=_broken_text_scores())

    def test_gate_is_off_by_default_and_existing_checks_unchanged(self):
        settings = _settings()
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertEqual(issues, [])
        # Метрики при этом всегда записываются в meta.
        self.assertIn("quality_score", self.weak_post.meta)
        self.assertIn("quality_warnings", self.weak_post.meta)
        self.assertIn("quality_metrics", self.weak_post.meta)
        self.assertIsInstance(self.weak_post.meta["quality_score"], int)
        self.assertLess(self.weak_post.meta["quality_score"], 60)

    def test_existing_blockers_keep_their_behavior(self):
        base = _post(text="Слишком коротко.", sources=[])
        channel = _channel(language="es")
        off_settings = _settings()
        issues_off = pipeline_module.quality_issues(base, channel, off_settings)
        self.assertTrue(any("коротк" in issue for issue in issues_off), issues_off)
        on_settings = _settings(quality_gate=True)
        issues_on = pipeline_module.quality_issues(base, channel, on_settings)
        # Старые блокеры не изменились, новые (если есть) добавлены в конец.
        self.assertEqual(issues_on[: len(issues_off)], issues_off)

    def test_gate_blocks_low_score(self):
        settings = _settings(quality_gate=True)
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertTrue(issues, issues)
        self.assertTrue(
            any("quality score" in issue for issue in issues),
            issues,
        )

    def test_gate_blocks_rubric_blockers(self):
        # Пост проходит старые проверки, но HTML не сбалансирован -> blocker рубрики.
        post = _post(text=GOOD_BODY + "\n\n<i>курсив без закрытия")
        settings = _settings(
            quality_gate={"enabled": True, "block_blockers": True, "min_score": 0}
        )
        issues = pipeline_module.quality_issues(post, self.channel, settings)
        self.assertTrue(any("quality[broken_html]" in issue for issue in issues), issues)

    def test_gate_warn_mode_never_blocks(self):
        settings = _settings(quality_gate="warn")
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertEqual(issues, [])
        self.assertIn("quality_score", self.weak_post.meta)

    def test_gate_dict_custom_min_score(self):
        post = _post(
            text=GOOD_BODY + "\n\nДополнительный абзац про рынок и экспертов."
        )
        settings = _settings(quality_gate={"enabled": True, "min_score": 101})
        issues = pipeline_module.quality_issues(post, self.channel, settings)
        self.assertTrue(any("quality score" in issue for issue in issues), issues)

    def test_gate_min_score_zero_skips_score_check(self):
        settings = _settings(
            quality_gate={"enabled": True, "min_score": 0, "block_blockers": True}
        )
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertEqual(issues, [], issues)

    def test_gate_numeric_value_sets_min_score(self):
        settings = _settings(quality_gate=75)
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertTrue(any("quality score" in issue for issue in issues), issues)

    def test_gate_top_level_min_score_key(self):
        settings = _settings(quality_gate=True, quality_gate_min_score=90)
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertTrue(any("quality score" in issue for issue in issues), issues)
        settings = _settings(quality_gate={"enabled": True}, quality_gate_min_score=0)
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertEqual(issues, [], issues)

    def test_gate_does_not_duplicate_existing_short_message(self):
        post = _post(text="Слишком коротко.", sources=[])
        settings = _settings(
            quality_gate={"enabled": True, "block_blockers": True, "min_score": 0}
        )
        issues = pipeline_module.quality_issues(post, self.channel, settings)
        self.assertFalse(any("quality[too_short]" in issue for issue in issues), issues)

    def test_gate_disabled_explicitly(self):
        settings = _settings(quality_gate=False)
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertEqual(issues, [])
        settings = _settings(quality_gate="off")
        issues = pipeline_module.quality_issues(self.weak_post, self.channel, settings)
        self.assertEqual(issues, [])

    def test_good_post_passes_gate(self):
        post, channel, _ = _generated_post()
        settings = _settings(quality_gate=True)
        issues = pipeline_module.quality_issues(post, channel, settings)
        self.assertEqual(issues, [])
        self.assertGreaterEqual(post.meta["quality_score"], 80)

    def test_gate_in_generate_posts(self):
        cluster = _cluster()
        post = _post(text=_broken_text_scores())
        channel = _channel()

        class FakeStorage:
            def get_posts(self, *args, **kwargs):
                return []

            def recent_post_titles(self, *args, **kwargs):
                return []

        storage = FakeStorage()

        settings = _settings(post_mode="", min_post_chars=100)
        with mock.patch.object(
            pipeline_module, "generate_post", return_value=post
        ), mock.patch.object(pipeline_module, "analyze_cluster", return_value=Analysis()), \
                mock.patch.object(pipeline_module, "_attach_card"):
            posts, errors = pipeline_module.generate_posts(
                channel, [cluster], settings, storage, llm=None, max_posts=1
            )
        self.assertEqual(len(posts), 1)
        self.assertEqual(errors, [])

        settings = _settings(post_mode="", min_post_chars=100, quality_gate=True)
        with mock.patch.object(
            pipeline_module, "generate_post", return_value=post
        ), mock.patch.object(pipeline_module, "analyze_cluster", return_value=Analysis()), \
                mock.patch.object(pipeline_module, "_attach_card"):
            posts, errors = pipeline_module.generate_posts(
                channel, [cluster], settings, storage, llm=None, max_posts=1
            )
        self.assertEqual(posts, [])
        self.assertTrue(
            any("quality score" in error for error in errors), errors
        )


class GeneratorQualityTest(unittest.TestCase):
    """Детерминированные правила качества генератора (RU/EN/ES)."""

    def test_lead_does_not_echo_headline_ru(self):
        post, _, _ = _generated_post("ru")
        blocks = _blocks(post)
        title = blocks[0]
        lead = blocks[1]
        self.assertIn("OpenAI представила новую модель GPT-5", title)
        self.assertNotEqual(lead, title)
        self.assertFalse(lead.startswith("OpenAI представила новую модель GPT-5."))
        self.assertGreaterEqual(len(post.plain_text), 220)

    def test_numbers_are_added_as_facts_not_labels_ru(self):
        post, _, _ = _generated_post("ru")
        self.assertIn("25%", post.plain_text)
        self.assertNotIn("Фигурирующие цифры", post.plain_text)

    def test_numbers_are_added_as_facts_not_labels_en(self):
        post, _, _ = _generated_post("en")
        self.assertIn("25%", post.plain_text)
        self.assertNotIn("The figures involved", post.plain_text)

    def test_hashtags_are_topped_up_to_two(self):
        channel = _channel(hashtags=["#ИИ"])
        cluster = _cluster()
        settings = _settings()
        analysis = analyze_cluster(cluster, settings)
        post = generate_post(cluster, analysis, channel, settings, fmt="story")
        self.assertGreaterEqual(len(post.hashtags), 2, post.hashtags)

    def test_prompts_request_hook_numbers_and_quality_rules(self):
        cases = {
            "ru": Analysis(
                summary="OpenAI представила модель GPT-5, качество ответов выросло на 25%.",
                bullets=["Модель доступна через API.", "Качество выросло на 25%."],
                numbers=["25%"],
            ),
            "en": Analysis(
                summary="OpenAI introduced GPT-5 with a 25% quality improvement.",
                bullets=["The model is available through the API."],
                numbers=["25%"],
            ),
            "es": Analysis(
                summary="OpenAI presentó GPT-5 con una mejora del 25% en calidad.",
                bullets=["El modelo está disponible en la API."],
                numbers=["25%"],
            ),
        }
        clusters = {
            "ru": _cluster(),
            "en": _cluster("OpenAI introduces GPT-5", EN_TECH_TEXTS, "tech.example"),
            "es": _cluster("OpenAI presenta GPT-5", ES_TECH_TEXTS, "es.example"),
        }
        for language in ("ru", "en", "es"):
            with self.subTest(language=language):
                llm = mock.Mock()
                llm.name = "fake"
                llm.available = True
                llm.generate.return_value = ""
                cluster = clusters[language]
                _llm_headline(
                    cluster,
                    cases[language],
                    cluster.combined_text or "",
                    llm,
                    language,
                )
                prompt = llm.generate.call_args[0][0]
                self.assertIn("90", prompt)
                if language == "en":
                    self.assertIsNone(re.search(r"[А-Яа-яЁё]", prompt))
                    self.assertIn("rewrite this news headline", prompt.lower())
                if language == "es":
                    self.assertIsNone(re.search(r"[А-Яа-яЁё]", prompt))
                    self.assertIn("titular", prompt.lower())

    def test_system_prompts_carry_quality_rules(self):
        ru = _system_prompt("ru")
        en = _system_prompt("en")
        es = _system_prompt("es")
        self.assertIn("90", ru)
        self.assertIn("кликбейт", ru)
        self.assertIn("journalist", en)
        self.assertIn("Telegram channel", en)
        self.assertIn("90", en)
        self.assertIn("periodista", es)
        self.assertIn("español".lower(), es.lower())
        self.assertIn("90", es)


if __name__ == "__main__":
    unittest.main()
