"""Тесты испаноязычной генерации постов: story / analysis / digest.

Проверяем, что для канала с ``language: es``:

* весь текст поста — испанский (без кириллицы), в том числе шаблонный
  fallback без LLM и fallback после мусорного/русского ответа модели;
* испанские подписи всех трёх тональностей (expert/science/friendly),
  испанская дата ``6 nov 2026`` и заглушка «Noticia»;
* ссылки на источники и Telegram HTML сохраняются;
* испанский LLM принимается, русский/мусорный — отбрасывается, а промпты и
  системный промпт — на испанском;
* диакритика в хэштегах не теряется, а кириллический CTA скрывается;
* русское поведение по умолчанию (channel.language == "ru") не изменилось.

Тесты герметичные: без сети, без реальной LLM, без config/*.
"""
from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser

from content_factory.models import Analysis, Article, ChannelConfig, StoryCluster
from content_factory.nlp.generator import generate_digest, generate_post
from content_factory.nlp.lang import is_spanish, language_code, resolve_language

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
DATE_ES_RE = re.compile(
    r"\d{1,2} (?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic) \d{4}"
)
DATE_RU_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")
DATE_EN_RE = re.compile(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4}")
ENTITY_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)")
ALLOWED_TAGS = {"b", "i", "a", "code"}
PUBLISHED = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)


class _HTMLCollector(HTMLParser):
    """Собирает теги/ссылки и проверяет, что HTML в стиле Telegram корректен."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.errors = []
        self.tags = []
        self.hrefs = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self.tags.append(tag)
        if tag not in ALLOWED_TAGS:
            self.errors.append("запрещённый тег: {}".format(tag))
            return
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href"))
        self.stack.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if not self.stack:
            self.errors.append("лишний закрывающий тег: </{}>".format(tag))
            return
        if self.stack[-1] != tag:
            self.errors.append(
                "неверный порядок тегов: ожидался </{}>, получен </{}>".format(
                    self.stack[-1], tag
                )
            )
            return
        self.stack.pop()

    def handle_data(self, data):
        self.text_parts.append(data)


class FakeSettings:
    """Минимальный заменитель Settings: генератору нужен только .get()."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, dotted, default=None):
        if dotted in self.values:
            return self.values[dotted]
        return {
            "pipeline.min_post_chars": 200,
            "pipeline.banned_words": [],
            "pipeline.cta": "",
        }.get(dotted, default)


def _article(article_id, title, url, source_id, source_name, text, minutes=0):
    return Article(
        id=article_id,
        title=title,
        url=url,
        source_id=source_id,
        source_name=source_name,
        published_at=PUBLISHED,
        text=text,
        language="es",
    )


def _make_cluster(cluster_id, title, domain, texts, score=0.8):
    source_names = ("El País", "El Mundo", "Agencia EFE")
    articles = []
    for index, text in enumerate(texts):
        articles.append(
            _article(
                "{}-a{}".format(cluster_id, index),
                title if index == 0 else "{}: última hora".format(title),
                "https://{}/articulo/{}".format(domain, index),
                "{}-s{}".format(cluster_id, index),
                source_names[index % len(source_names)],
                text,
            )
        )
    return StoryCluster(id=cluster_id, title=title, articles=articles, score=score)


ES_TECH_TEXTS = (
    "El Gobierno de España aprobó este martes un nuevo paquete de medidas económicas. "
    "Según el Ejecutivo, el objetivo es reducir la inflación y proteger el empleo. "
    "La medida afecta a los ciudadanos y a las empresas del país.",
    "El Gobierno anunció un plan de ayudas para las empresas. La inflación se redujo "
    "hasta el 2,8% el mes pasado, informó el Ministerio de Economía. Los expertos "
    "consideran que la medida es clave para la recuperación.",
    "España aprueba nuevas medidas económicas. El Ejecutivo destaca que la inflación "
    "bajó al 2,8% y que el empleo creció un 1,5%. Según los analistas, el plan "
    "también beneficia a las pequeñas empresas.",
)
ES_FIN_TEXTS = (
    "El Banco Central Europeo mantuvo los tipos de interés en el 4,5%. El regulador "
    "señaló que la inflación se moderó hasta el 2,8% y dejó abierta la puerta a "
    "futuras bajadas. Los analistas esperaban una decisión sin cambios.",
    "El BCE dejó los tipos en el 4,5%, informa Reuters. En un comunicado el "
    "regulador apuntó a una inflación del 2,8%. La próxima reunión está prevista "
    "para diciembre. Los mercados reaccionaron con calma.",
    "El BCE no cambió los tipos de interés, escribe Bloomberg. La inflación bajó "
    "al 2,8%, según el regulador. La decisión coincidió con las previsiones de los "
    "analistas. Una bajada es posible a finales de año.",
)
ES_SCI_TEXTS = (
    "Los científicos descubrieron cómo el sueño limpia el cerebro. La actividad del "
    "sistema glinfático aumentó un 60% en comparación con la vigilia. El estudio se "
    "publicó en una revista revisada por pares. Un equipo internacional confirmó que "
    "el sueño ayuda a eliminar los desechos metabólicos.",
    "Los investigadores mostraron cómo el sueño limpia el cerebro, informa Nature. "
    "Durante el sueño profundo la velocidad de limpieza aumentó un 55%. Según los "
    "autores, esto explica la relación entre la falta de sueño y el riesgo "
    "neurodegenerativo.",
    "Un nuevo estudio explica la limpieza del cerebro durante el sueño, escribe "
    "Science. La actividad del sistema aumentó un 60%. Los resultados se publicaron "
    "en una revista revisada por pares. Los científicos planean continuar el trabajo.",
)


def _tech_cluster():
    return _make_cluster(
        "cluster-tech-es",
        "El Gobierno de España aprueba nuevas medidas económicas",
        "es.example",
        ES_TECH_TEXTS,
    )


def _fin_cluster():
    return _make_cluster(
        "cluster-fin-es",
        "El BCE mantiene los tipos de interés en el 4,5%",
        "fin-es.example",
        ES_FIN_TEXTS,
    )


def _sci_cluster():
    return _make_cluster(
        "cluster-sci-es",
        "Los científicos descubren cómo el sueño limpia el cerebro",
        "sci-es.example",
        ES_SCI_TEXTS,
    )


def _tech_analysis():
    return Analysis(
        summary=(
            "El Gobierno de España aprobó un nuevo paquete de medidas económicas. "
            "La inflación se redujo hasta el 2,8% el mes pasado. Los expertos "
            "consideran que la medida es clave para la recuperación."
        ),
        bullets=[
            "El paquete incluye ayudas directas a las pequeñas empresas.",
            "El Ministerio de Economía prevé un crecimiento del 1,5% este año.",
            "La oposición criticó la falta de detalles del plan.",
        ],
        key_terms=["España", "inflación", "economía", "empleo"],
        numbers=["2,8%", "1,5%"],
        perspectives=[
            {
                "source_name": "El País",
                "quote": "El Gobierno de España aprobó un nuevo paquete de medidas económicas.",
                "angle": "Enfoque en la economía",
            },
            {
                "source_name": "El Mundo",
                "quote": "La inflación se redujo hasta el 2,8% el mes pasado.",
                "angle": "Los precios importan",
            },
        ],
        source_count=3,
        source_names=["El País", "El Mundo", "Agencia EFE"],
    )


def _fin_analysis():
    return Analysis(
        summary=(
            "El Banco Central Europeo mantuvo los tipos de interés en el 4,5%. "
            "La inflación se moderó hasta el 2,8%, según el regulador. Los analistas "
            "esperaban una decisión sin cambios."
        ),
        bullets=[
            "El BCE mantuvo los tipos en el 4,5% en la reunión del consejo.",
            "La inflación se moderó hasta el 2,8%, según el regulador.",
            "La próxima reunión está prevista para diciembre.",
        ],
        key_terms=["BCE", "tipos", "inflación"],
        numbers=["4,5%", "2,8%"],
        source_count=3,
        source_names=["El País", "El Mundo", "Agencia EFE"],
    )


def _sci_analysis():
    return Analysis(
        summary=(
            "Los científicos descubrieron cómo el sueño limpia el cerebro. La actividad "
            "del sistema glinfático aumentó un 60% en comparación con la vigilia. El "
            "estudio se publicó en una revista revisada por pares."
        ),
        bullets=[
            "La actividad del sistema glinfático aumentó un 60% durante el sueño.",
            "El estudio se publicó en una revista revisada por pares.",
            "Los científicos planean continuar el trabajo.",
        ],
        key_terms=["sueño", "cerebro", "estudio"],
        numbers=["60%"],
        source_count=3,
        source_names=["El País", "El Mundo", "Agencia EFE"],
    )


def _es_channel(**overrides):
    params = {
        "id": "noticias-es",
        "title": "Noticias España",
        "language": "es",
        "tone": "expert",
        "formats": ["digest", "story", "analysis"],
        "hashtags": ["#Economía"],
        "cta": "Lee nuestro canal para más noticias.",
        "emoji": True,
        "timezone_offset": 1,
        "max_post_chars": 3200,
        "topics": ["economia"],
        "description": "Noticias en español.",
    }
    params.update(overrides)
    return ChannelConfig(**params)


def _ru_channel(**overrides):
    params = {
        "id": "tech-ai",
        "title": "Технологии и ИИ",
        "tone": "expert",
        "formats": ["story"],
        "hashtags": ["#ИИ"],
        "cta": "",
        "emoji": True,
        "timezone_offset": 3,
        "max_post_chars": 3500,
        "topics": ["технологии"],
    }
    params.update(overrides)
    return ChannelConfig(**params)


RU_CLUSTER_TITLE = "Центральный банк оставил ключевую ставку на уровне 18%"
RU_TEXTS = (
    "Банк России сохранил ключевую ставку на уровне 18%. Регулятор отметил замедление "
    "инфляции до 8,5%. Аналитики ожидали сохранения ставки.",
    "ЦБ сохранил ключевую ставку 18%, сообщает РБК. Инфляция замедлилась до 8,5%, "
    "отмечает регулятор. Решение совпало с ожиданиями аналитиков.",
)


def _ru_cluster():
    return _make_cluster("cluster-ru", RU_CLUSTER_TITLE, "ru.example", RU_TEXTS)


def _ru_analysis():
    return Analysis(
        summary=(
            "Банк России сохранил ключевую ставку. Регулятор отметил замедление "
            "инфляции до 8,5%. Решение совпало с ожиданиями аналитиков."
        ),
        bullets=[
            "Банк России сохранил ключевую ставку на уровне 18%.",
            "Регулятор отметил замедление инфляции до 8,5%.",
            "Следующее заседание запланировано на декабрь.",
        ],
        numbers=["18%", "8,5%"],
        key_terms=["ставка", "инфляция"],
        source_count=2,
    )


class FakeLLM:
    """Фейковый LLM-клиент с интерфейсом LLMClient."""

    name = "fake"
    available = True

    def __init__(self, reply=""):
        self.reply = reply
        self.prompts = []
        self.systems = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        return self.reply


class SpanishPromptLLM:
    """Отвечает валидными испанскими текстами на промпты генератора."""

    name = "fake-es"
    available = True

    def __init__(self):
        self.prompts = []
        self.systems = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        lowered = prompt.lower()
        if "titular" in lowered:
            return "El Gobierno de España aprueba un plan de ayudas"
        if "por qué esta noticia importa" in lowered:
            return "La medida busca reducir la inflación y proteger el empleo en el país."
        if "conclusión neutral" in lowered:
            return "El plan reduce la inflación y protege el empleo según el Gobierno."
        return ""


class DigestSpanishLLM:
    """Отвечает испанскими строками на промпт дайджеста (3 новости)."""

    name = "fake-digest-es"
    available = True

    def __init__(self):
        self.prompts = []
        self.systems = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        if "lista de noticias para un resumen" in prompt.lower():
            return "\n".join(
                (
                    "El Gobierno de España aprueba un plan de ayudas para las empresas",
                    "El BCE mantiene los tipos de interés en el 4,5%",
                    "Los científicos explican cómo el sueño limpia el cerebro",
                )
            )
        return ""


class SpanishGeneratorTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = FakeSettings()
        cls.channel = _es_channel()
        cls.cluster = _tech_cluster()
        cls.analysis = _tech_analysis()

    # -- общие проверки ------------------------------------------------------
    def assert_no_cyrillic(self, post):
        self.assertIsNone(
            CYRILLIC_RE.search(post.text),
            "в es-посте найдена кириллица: {}".format(post.text),
        )
        self.assertIsNone(
            CYRILLIC_RE.search(post.plain_text),
            "в plain-тексте es-поста найдена кириллица: {}".format(post.plain_text),
        )

    def assert_valid_post(self, post, channel, clusters, allow_cyrillic=False):
        """HTML в стиле Telegram, ссылки только из кластеров, лимит соблюдён."""
        self.assertTrue(post.text.strip())
        self.assertLessEqual(len(post.text), channel.max_post_chars)
        collector = _HTMLCollector()
        collector.feed(post.text)
        collector.close()
        self.assertEqual(collector.errors, [])
        self.assertEqual(collector.stack, [])
        for tag in collector.tags:
            self.assertIn(tag, ALLOWED_TAGS)
        without_tags = re.sub(r"<[^>]+>", "", post.text)
        self.assertNotIn("<", without_tags)
        self.assertNotIn(">", without_tags)
        self.assertIsNone(ENTITY_RE.search(without_tags))
        expected_urls = {
            article.url
            for cluster in clusters
            for article in (cluster.articles or [])
        }
        for href in collector.hrefs:
            # Пост может содержать ссылку на добровольную поддержку канала.
            if "donationalerts.com" in href:
                continue
            self.assertIn(href, expected_urls)
        self.assertTrue(post.sources)
        for source in post.sources:
            self.assertEqual(set(source), {"title", "url", "source"})
            self.assertIn(source["url"], expected_urls)
            if not allow_cyrillic:
                self.assertFalse(CYRILLIC_RE.search(source["title"]))
                self.assertFalse(CYRILLIC_RE.search(source["source"]))
        self.assertIn("http", post.text)
        return collector


# ---------------------------------------------------------------------------
# Языковые коды и resolve_language
# ---------------------------------------------------------------------------


class SpanishLanguageCodeTest(unittest.TestCase):
    def test_supported_languages_include_spanish(self):
        from content_factory.nlp.lang import SUPPORTED_LANGUAGES

        self.assertIn("es", SUPPORTED_LANGUAGES)

    def test_language_code_normalizes_spanish_variants(self):
        for value in ("es", "es-ES", "es_419", "es-MX", "ES", "español"):
            self.assertEqual(language_code(value), "es", value)

    def test_language_code_keeps_ru_and_en(self):
        self.assertEqual(language_code("en-US"), "en")
        self.assertEqual(language_code("ru-RU"), "ru")
        self.assertEqual(language_code(""), "ru")
        self.assertEqual(language_code("de"), "ru")

    def test_is_spanish(self):
        self.assertTrue(is_spanish("es-419"))
        self.assertTrue(is_spanish("ES"))
        self.assertFalse(is_spanish("en"))
        self.assertFalse(is_spanish("ru"))
        self.assertFalse(is_spanish(None))

    def test_resolve_language_explicit(self):
        self.assertEqual(resolve_language(explicit="es-MX"), "es")
        self.assertEqual(resolve_language(explicit="es"), "es")

    def test_resolve_language_from_settings(self):
        settings = FakeSettings({"app.language": "es-419"})
        self.assertEqual(resolve_language(settings=settings), "es")

    def test_resolve_language_explicit_wins_over_articles(self):
        article = Article(
            id="a", title="T", url="https://e.example/1", source_id="s",
            source_name="S", published_at=PUBLISHED, text="texto", language="en",
        )
        self.assertEqual(resolve_language(explicit="es", articles=[article]), "es")


class SpanishDateTest(unittest.TestCase):
    def test_spanish_months_are_abbreviated(self):
        from content_factory.nlp.generator import _ES_MONTHS, _format_date

        expected = (
            "ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic",
        )
        self.assertEqual(_ES_MONTHS, expected)
        channel = _es_channel(timezone_offset=0)
        for month, label in enumerate(expected, start=1):
            dt = datetime(2026, month, 6, 9, 0, tzinfo=timezone.utc)
            self.assertEqual(
                _format_date(channel, "es", dt), "6 {} 2026".format(label), month
            )


class SpanishLanguageChecksTest(unittest.TestCase):
    def test_fits_language_rejects_cyrillic(self):
        from content_factory.nlp.generator import _fits_language

        self.assertTrue(_fits_language("La inflación bajó al 2,8%", "es"))
        self.assertFalse(_fits_language("Инфляция снизилась", "es"))

    def test_headline_and_sentence_language_checks(self):
        from content_factory.nlp.generator import (
            _headline_fits_language,
            _sentence_fits_language,
        )

        self.assertTrue(_headline_fits_language("La inflación baja al 2,8%", "es"))
        self.assertFalse(_headline_fits_language("Инфляция снизилась", "es"))
        self.assertFalse(_headline_fits_language("12345", "es"))
        self.assertTrue(
            _sentence_fits_language(
                "El Gobierno aprobó el plan y la inflación bajó.", "es"
            )
        )
        self.assertFalse(
            _sentence_fits_language("Правительство одобрило план.", "es")
        )


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------


class SpanishStoryTest(SpanishGeneratorTestBase):
    def test_story_without_llm_is_spanish(self):
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story"
        )
        self.assertEqual(post.format, "story")
        self.assert_no_cyrillic(post)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertEqual(post.meta["language"], "es")
        self.assertNotIn("Claves:", post.text)
        self.assertNotIn("Por qué importa:", post.text)
        self.assertIn("Fuentes:", post.text)
        self.assertIn("Lee nuestro canal para más noticias.", post.text)
        self.assertNotIn("Главное", post.text)
        self.assertNotIn("Источники", post.text)
        self.assertNotIn("Почему это важно", post.text)
        self.assert_valid_post(post, self.channel, [self.cluster])

    def test_story_keeps_telegram_html_and_source_links(self):
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story"
        )
        collector = self.assert_valid_post(post, self.channel, [self.cluster])
        self.assertTrue(collector.hrefs)
        source_hrefs = [h for h in collector.hrefs if "donationalerts.com" not in h]
        self.assertEqual(len(source_hrefs), len(post.sources))
        self.assertIn("<b>", post.text)
        self.assertNotIn("▪️ ", post.text)
        self.assertEqual(post.meta["quality_issues"], [])

    def test_story_question_tail_is_stripped_spanish(self):
        for title in (
            "La inflación: lo que sabemos",
            "El plan económico: última hora",
            "La reforma: todo lo que necesitas saber",
            "La crisis: así te lo contamos",
            "La economía: claves",
        ):
            cluster = _make_cluster(
                "cluster-tail-es", title, "tail-es.example", ES_TECH_TEXTS
            )
            post = generate_post(
                cluster, self.analysis, self.channel, self.settings, fmt="story"
            )
            first_block = post.text.split("\n\n")[0]
            expected = title.split(":")[0]
            self.assertIn("<b>{}</b>".format(expected), first_block, title)
            self.assert_no_cyrillic(post)

    def test_story_without_title_uses_spanish_placeholder(self):
        cluster = StoryCluster(
            id="cluster-empty-es",
            title="",
            articles=[
                _article(
                    "empty-es-a1",
                    "",
                    "https://empty-es.example/1",
                    "empty-es-s1",
                    "Example",
                    "",
                )
            ],
        )
        post = generate_post(
            cluster, Analysis(), self.channel, self.settings, fmt="story"
        )
        self.assertIn("Noticia", post.text)
        self.assertNotIn("Новость", post.text)
        self.assert_no_cyrillic(post)
        self.assertTrue(post.sources)

    def test_russian_source_row_is_sanitized(self):
        cluster = StoryCluster(
            id="cluster-mixed",
            title="El Gobierno aprueba el plan económico",
            articles=[
                _article(
                    "mix-es",
                    "El Gobierno aprueba el plan económico",
                    "https://es.example/mix",
                    "s-es",
                    "El País",
                    ES_TECH_TEXTS[0],
                ),
                _article(
                    "mix-ru",
                    "Правительство Испании одобрило план",
                    "https://ru.example/mix",
                    "s-ru",
                    "РИА Новости",
                    "Правительство Испании одобрило новый план.",
                ),
            ],
        )
        post = generate_post(
            cluster, self.analysis, self.channel, self.settings, fmt="story"
        )
        self.assert_no_cyrillic(post)
        self.assert_valid_post(post, self.channel, [cluster])

    def test_cyrillic_cta_is_not_shown_in_spanish_post(self):
        channel = _es_channel(cta="Подписывайтесь на канал!")
        post = generate_post(
            self.cluster, self.analysis, channel, self.settings, fmt="story"
        )
        self.assertNotIn("Подписывайтесь", post.text)
        self.assert_no_cyrillic(post)

    def test_cyrillic_hashtags_are_not_shown_in_spanish_post(self):
        channel = _es_channel(hashtags=["#ИИ", "#Новости"])
        post = generate_post(
            self.cluster, self.analysis, channel, self.settings, fmt="story"
        )
        self.assertNotIn("#ИИ", post.text)
        self.assertNotIn("Новости", post.text)
        self.assert_no_cyrillic(post)
        self.assertTrue(post.hashtags)
        self.assertTrue(all(not CYRILLIC_RE.search(tag) for tag in post.hashtags))

    def test_spanish_hashtags_keep_diacritics(self):
        channel = _es_channel(hashtags=["#Economía", "#España"])
        post = generate_post(
            self.cluster, self.analysis, channel, self.settings, fmt="story"
        )
        self.assertIn("#Economía", post.text)
        self.assertIn("#España", post.text)
        self.assertIn("#Economía", post.hashtags)
        self.assertIn("#España", post.hashtags)

    def test_generated_hashtags_keep_diacritics(self):
        channel = _es_channel(hashtags=[])
        analysis = Analysis(key_terms=["economía", "inflación", "España"])
        cluster = _tech_cluster()
        post = generate_post(cluster, analysis, channel, self.settings, fmt="story")
        self.assertIn("#economía", post.hashtags)
        self.assertIn("#inflación", post.hashtags)
        self.assertIn("#economía", post.text)
        self.assert_no_cyrillic(post)


# ---------------------------------------------------------------------------
# Analysis / digest
# ---------------------------------------------------------------------------


class SpanishAnalysisTest(SpanishGeneratorTestBase):
    def test_analysis_without_llm_is_spanish(self):
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="analysis"
        )
        self.assertEqual(post.format, "analysis")
        self.assert_no_cyrillic(post)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("Análisis:", post.text)
        self.assertNotIn("Qué dicen las fuentes", post.text)
        self.assertNotIn("Conclusión:", post.text)
        self.assertNotIn("Cifras", post.text)
        self.assertIn("Fuentes:", post.text)
        self.assertIn("El País", post.text)
        self.assertIn("2,8%", post.text)
        self.assertIn("«", post.text)
        self.assert_valid_post(post, self.channel, [self.cluster])
        self.assertEqual(post.meta["quality_issues"], [])

    def test_analysis_fallback_conclusion_is_spanish(self):
        analysis = Analysis(
            summary="La inflación bajó al 2,8% en España.",
            bullets=["El Gobierno aprobó el plan económico."],
            key_terms=["inflación", "España"],
            source_count=3,
            source_names=["El País", "El Mundo", "Agencia EFE"],
        )
        post = generate_post(
            self.cluster, analysis, self.channel, self.settings, fmt="analysis"
        )
        self.assert_no_cyrillic(post)
        self.assertIn("El panorama surge de los mensajes de 3 fuentes.", post.text)
        self.assertNotIn("Temas clave", post.text)
        self.assertNotIn("Картина", post.text)

    def test_template_why_is_spanish(self):
        analysis = Analysis(
            summary=(
                "El plan incluye ayudas directas a las pequeñas empresas. "
                "La medida entrará en vigor el próximo mes de enero."
            ),
            bullets=[
                "El plan fue aprobado por el Gobierno este martes.",
                "La oposición criticó la falta de detalles.",
            ],
            key_terms=["plan", "inflación"],
            source_count=2,
            source_names=["El País", "El Mundo"],
        )
        post = generate_post(
            self.cluster, analysis, self.channel, self.settings, fmt="story"
        )
        self.assert_no_cyrillic(post)
        self.assertNotIn("Por qué importa:", post.text)
        self.assertNotIn("Почему", post.text)

    def test_cyrillic_summary_fragments_are_filtered(self):
        analysis = Analysis(
            summary=(
                "El Gobierno aprobó el plan económico. "
                "Правительство Испании одобрило план. "
                "La inflación bajó al 2,8%."
            ),
            bullets=["El plan fue aprobado por el Gobierno."],
            key_terms=["plan", "inflación"],
            source_count=2,
            source_names=["El País", "El Mundo"],
        )
        post = generate_post(
            self.cluster, analysis, self.channel, self.settings, fmt="analysis"
        )
        self.assert_no_cyrillic(post)


class SpanishDigestTest(SpanishGeneratorTestBase):
    def _digest_items(self):
        return [
            (_tech_cluster(), _tech_analysis()),
            (_fin_cluster(), _fin_analysis()),
            (_sci_cluster(), _sci_analysis()),
        ]

    def test_generate_digest_is_spanish(self):
        items = self._digest_items()
        post = generate_digest(items, self.channel, self.settings)
        self.assertEqual(post.format, "digest")
        self.assertEqual(post.meta["items_count"], 3)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assert_no_cyrillic(post)
        self.assertIn("Resumen", post.text)
        self.assertIsNotNone(DATE_ES_RE.search(post.text))
        self.assertNotRegex(post.text, DATE_RU_RE.pattern)
        self.assertNotRegex(post.text, DATE_EN_RE.pattern)
        self.assertNotIn("———", post.text)
        for marker in ("1️⃣", "2️⃣", "3️⃣"):
            self.assertNotIn(marker, post.text)
        self.assertIn("📌", post.text)
        self.assertIn("Fuentes:", post.text)
        clusters = [cluster for cluster, _ in items]
        self.assert_valid_post(post, self.channel, clusters)

    def test_single_digest_format_is_spanish_with_spanish_date(self):
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="digest"
        )
        self.assertEqual(post.format, "digest")
        # 18 окт 2026 09:00 UTC + offset 1 = 18 oct 2026.
        self.assertIn("<b>", post.text)
        self.assert_no_cyrillic(post)
        self.assertIn("Fuentes:", post.text)
        self.assert_valid_post(post, self.channel, [self.cluster])

    def test_empty_digest_header_is_spanish(self):
        post = generate_digest([], self.channel, self.settings)
        self.assertIn("Resumen", post.text)
        self.assertNotIn("Дайджест", post.text)
        self.assertIsNotNone(DATE_ES_RE.search(post.text))
        self.assert_no_cyrillic(post)

    def test_digest_fallback_line_without_summary_is_spanish(self):
        cluster = _fin_cluster()
        post = generate_digest(
            [(cluster, Analysis(source_count=2))], self.channel, self.settings
        )
        self.assert_no_cyrillic(post)
        self.assertIn("Los detalles están en el artículo de la fuente.", post.text)
        analysis = Analysis(numbers=["18%"], key_terms=["BCE", "tipos"], source_count=2)
        post = generate_digest(
            [(cluster, analysis)], self.channel, self.settings
        )
        self.assert_no_cyrillic(post)
        # La cifra se resalta en negrita: comprobamos el texto sin el tag.
        self.assertIn("Los informes mencionan estas cifras:", post.text)
        self.assertIn("18%", post.text)


# ---------------------------------------------------------------------------
# Тональности и emoji
# ---------------------------------------------------------------------------


class SpanishToneStylesTest(SpanishGeneratorTestBase):
    def _story(self, channel):
        return generate_post(
            self.cluster, self.analysis, channel, self.settings, fmt="story"
        )

    def test_expert_tone_labels(self):
        post = self._story(_es_channel(tone="expert"))
        self.assertNotIn("Claves:", post.text)
        self.assertNotIn("Lo principal:", post.text)
        self.assertNotIn("Por qué importa:", post.text)
        self.assertIn("Fuentes:", post.text)
        self.assert_no_cyrillic(post)

    def test_science_tone_labels(self):
        post = self._story(_es_channel(tone="science"))
        self.assertNotIn("Claves:", post.text)
        self.assertNotIn("Lo principal:", post.text)
        self.assertNotIn("Por qué importa:", post.text)
        self.assert_no_cyrillic(post)

    def test_friendly_tone_labels(self):
        post = self._story(_es_channel(tone="friendly"))
        self.assertNotIn("En breve:", post.text)
        self.assertNotIn("Por qué deberías saberlo:", post.text)
        self.assertIn("Fuentes:", post.text)
        self.assert_no_cyrillic(post)

    def test_science_analysis_label_is_spanish(self):
        post = generate_post(
            self.cluster,
            self.analysis,
            _es_channel(tone="science"),
            self.settings,
            fmt="analysis",
        )
        self.assertNotIn("Análisis del estudio:", post.text)
        self.assert_no_cyrillic(post)

    def test_tone_dictionaries_have_spanish_labels(self):
        from content_factory.nlp.generator import (
            _SHORT_SUMMARY_LABEL,
            _TONE_STYLES_BY_LANGUAGE,
            _WHY_MARKERS,
        )

        self.assertIn("es", _TONE_STYLES_BY_LANGUAGE)
        for tone in ("expert", "science", "friendly"):
            labels = _TONE_STYLES_BY_LANGUAGE["es"][tone]
            for key in (
                "lead", "bullet", "summary", "why", "analysis", "digest",
                "context", "perspectives", "numbers", "conclusion", "sources",
            ):
                self.assertIn(key, labels)
                self.assertFalse(CYRILLIC_RE.search(labels[key]), (tone, key))
        self.assertEqual(_SHORT_SUMMARY_LABEL["es"], "En breve")
        self.assertIn("importan", _WHY_MARKERS["es"])

    def test_channel_without_emoji_uses_plain_bullets(self):
        post = self._story(_es_channel(emoji=False))
        self.assertNotIn("▪️", post.text)
        self.assertNotIn("• ", post.text)
        self.assert_no_cyrillic(post)


# ---------------------------------------------------------------------------
# LLM: испанский принимается, русский/мусорный отбрасывается
# ---------------------------------------------------------------------------


class SpanishLLMTest(SpanishGeneratorTestBase):
    def test_spanish_llm_is_used(self):
        llm = SpanishPromptLLM()
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertEqual(post.meta["generator"], "llm")
        self.assertEqual(post.meta["llm_provider"], "fake-es")
        self.assertIn("<b>El Gobierno de España aprueba un plan de ayudas</b>", post.text)
        self.assertTrue(llm.prompts)
        self.assert_no_cyrillic(post)
        for system in llm.systems:
            self.assertIn("español", system.lower())
            self.assertIsNone(CYRILLIC_RE.search(system))
        for prompt in llm.prompts:
            self.assertIsNone(CYRILLIC_RE.search(prompt))
        self.assert_valid_post(post, self.channel, [self.cluster])

    def test_spanish_llm_conclusion_is_used_for_analysis(self):
        llm = SpanishPromptLLM()
        post = generate_post(
            self.cluster,
            self.analysis,
            self.channel,
            self.settings,
            fmt="analysis",
            llm=llm,
        )
        self.assertEqual(post.meta["generator"], "llm")
        self.assertNotIn("Conclusión:", post.text)
        self.assertIn("El plan reduce la inflación y protege el empleo", post.text)
        self.assert_no_cyrillic(post)

    def test_spanish_llm_system_prompt_is_spanish(self):
        llm = SpanishPromptLLM()
        generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertTrue(llm.systems)
        for system in llm.systems:
            self.assertIn("periodista", system)
            self.assertIn("español", system.lower())
            self.assertIsNone(CYRILLIC_RE.search(system))

    def test_spanish_llm_digest_lines_are_used(self):
        llm = DigestSpanishLLM()
        items = [
            (_tech_cluster(), _tech_analysis()),
            (_fin_cluster(), _fin_analysis()),
            (_sci_cluster(), _sci_analysis()),
        ]
        post = generate_digest(items, self.channel, self.settings, llm=llm)
        self.assertEqual(post.meta["generator"], "llm")
        self.assertEqual(post.meta["llm_provider"], "fake-digest-es")
        self.assertIn("El Gobierno de España aprueba un plan de ayudas para las empresas", post.text)
        self.assertIn("El BCE mantiene los tipos de interés en el 4,5%", post.text)
        self.assert_no_cyrillic(post)
        self.assertTrue(llm.systems)
        for system in llm.systems:
            self.assertIn("español", system.lower())
            self.assertIsNone(CYRILLIC_RE.search(system))

    def test_russian_llm_answer_is_rejected(self):
        llm = FakeLLM(
            "Правительство Испании одобрило новый пакет экономических мер."
        )
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertEqual(post.meta["llm_provider"], "extractive")
        self.assertNotIn("Правительство", post.text)
        self.assert_no_cyrillic(post)
        self.assertNotIn("Claves:", post.text)

    def test_garbage_llm_answer_is_rejected(self):
        llm = FakeLLM('```json\n{"titular": "нельзя", "url": "https://fake.example"}\n```')
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="analysis", llm=llm
        )
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("нельзя", post.text)
        self.assertNotIn("fake.example", post.text)
        self.assert_no_cyrillic(post)

    def test_invented_numbers_and_markdown_are_rejected(self):
        llm = FakeLLM(
            "El Gobierno aprueba un plan con 999 millones de euros para las empresas "
            "según el nuevo **decreto**."
        )
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertNotIn("999", post.text)
        self.assert_no_cyrillic(post)


# ---------------------------------------------------------------------------
# Русское поведение по умолчанию не изменилось
# ---------------------------------------------------------------------------


class RussianBehaviourUnchangedTest(unittest.TestCase):
    def test_russian_channel_without_llm_is_unchanged(self):
        settings = FakeSettings()
        cluster = _ru_cluster()
        post = generate_post(
            cluster, _ru_analysis(), _ru_channel(), settings, fmt="story"
        )
        self.assertTrue(CYRILLIC_RE.search(post.text))
        self.assertNotIn("Главное:", post.text)
        self.assertNotIn("Claves:", post.text)
        self.assertNotIn("Fuentes:", post.text)

    def test_russian_single_digest_keeps_numeric_date(self):
        settings = FakeSettings()
        post = generate_post(
            _ru_cluster(), _ru_analysis(), _ru_channel(), settings, fmt="digest"
        )
        self.assertIn("Центральный банк", post.text)
        self.assertNotIn("Digest", post.text)
        pass


if __name__ == "__main__":
    unittest.main()
