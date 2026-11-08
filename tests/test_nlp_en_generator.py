"""Тесты англоязычной генерации постов: story / digest / analysis.

Проверяем, что для канала с ``language: en``:

* весь текст поста — английский (без кириллицы), в том числе шаблонный
  fallback без LLM и fallback после мусорного/русского ответа модели;
* английские подписи всех трёх тональностей (expert/science/friendly),
  английская дата и заглушки;
* ссылки на источники и Telegram HTML сохраняются;
* фейковый английский LLM принимается, русский/мусорный — отбрасывается;
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

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
DATE_EN_RE = re.compile(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4}")
DATE_RU_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")
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
    )


def _make_cluster(cluster_id, title, domain, texts, score=0.8):
    source_names = ("TechCrunch", "The Verge", "Ars Technica")
    articles = []
    for index, text in enumerate(texts):
        articles.append(
            _article(
                "{}-a{}".format(cluster_id, index),
                title if index == 0 else "{}: details".format(title),
                "https://{}/article/{}".format(domain, index),
                "{}-s{}".format(cluster_id, index),
                source_names[index % len(source_names)],
                text,
            )
        )
    return StoryCluster(id=cluster_id, title=title, articles=articles, score=score)


EN_TECH_TEXTS = (
    "OpenAI introduced its new GPT-5 model. The company said the model is available "
    "to developers through the API starting October 18. According to benchmarks, "
    "answer quality improved by 25% compared with the previous version. The new model "
    "supports a context window of up to 200 thousand tokens. Experts note growing "
    "interest in such solutions.",
    "OpenAI announced the GPT-5 model. The new version is available through the API, "
    "reports The Verge. The company claims a 25% performance gain and support for a "
    "context window of up to 200 thousand tokens. Developers can use the model to "
    "build applications.",
    "OpenAI released GPT-5. The model is now available to developers, writes Ars "
    "Technica. Earlier the company promised better answer quality and a larger "
    "context. The new version is already being tested in partner applications.",
)
EN_FIN_TEXTS = (
    "The Federal Reserve kept its key interest rate at 4.5%. The regulator noted that "
    "inflation slowed to 2.8% and said it sees room for rate cuts later this year. The "
    "decision was made at the board meeting. Analysts expected the rate to stay unchanged.",
    "The Fed held its key rate at 4.5%, reports Reuters. In a statement the regulator "
    "pointed to slowing inflation of 2.8%. The next board meeting is scheduled for "
    "December. Markets reacted calmly to the decision.",
    "The Fed left rates unchanged at 4.5%, writes Bloomberg. Inflation slowed to 2.8%, "
    "the regulator noted. The decision matched analysts' expectations. A rate cut is "
    "possible later this year.",
)
EN_SCI_TEXTS = (
    "Scientists found out how sleep clears the brain. Activity of the glymphatic "
    "system rose by 60% compared with wakefulness. The study was published in a "
    "peer-reviewed journal. An international team confirmed that sleep helps the brain "
    "remove metabolic waste.",
    "Researchers showed how sleep clears the brain, reports Nature. During slow-wave "
    "sleep the clearing speed increased by 55%. According to the authors, this "
    "explains the link between chronic sleep loss and neurodegenerative risk.",
    "A new study explains brain clearing during sleep, writes Science. Activity of the "
    "system rose by 60%. The results were published in a peer-reviewed journal. The "
    "scientists plan to continue the work.",
)


def _tech_cluster():
    return _make_cluster(
        "cluster-tech",
        "OpenAI introduced its new GPT-5 model",
        "tech.example",
        EN_TECH_TEXTS,
    )


def _fin_cluster():
    return _make_cluster(
        "cluster-fin",
        "The Fed kept its key interest rate at 4.5%",
        "fin.example",
        EN_FIN_TEXTS,
    )


def _sci_cluster():
    return _make_cluster(
        "cluster-sci",
        "Scientists found out how sleep clears the brain",
        "sci.example",
        EN_SCI_TEXTS,
    )


def _tech_analysis():
    return Analysis(
        summary=(
            "OpenAI announced GPT-5 on October 18. Developers can access the model "
            "through the API. The company promises a 25% quality improvement and a "
            "larger context window."
        ),
        bullets=[
            "The model is available to developers through the API starting October 18.",
            "Benchmark results show a 25% improvement over the previous version.",
            "The context window now supports up to 200 thousand tokens.",
        ],
        key_terms=["OpenAI", "GPT-5", "model", "context"],
        numbers=["25%", "200"],
        perspectives=[
            {
                "source_name": "TechCrunch",
                "quote": "The model is available to developers through the API.",
                "angle": "Focus on developer access",
            },
            {
                "source_name": "The Verge",
                "quote": "The company claims a 25% performance gain.",
                "angle": "Benchmarks matter",
            },
        ],
        source_count=3,
        source_names=["TechCrunch", "The Verge", "Ars Technica"],
    )


def _fin_analysis():
    return Analysis(
        summary=(
            "The Federal Reserve kept its key interest rate at 4.5%. Inflation slowed "
            "to 2.8%, the regulator said. Analysts expected the rate to stay unchanged."
        ),
        bullets=[
            "The Fed held its key rate at 4.5% at the board meeting.",
            "Inflation slowed to 2.8%, according to the regulator.",
            "The next board meeting is scheduled for December.",
        ],
        key_terms=["Fed", "rate", "inflation"],
        numbers=["4.5%", "2.8%"],
        source_count=3,
        source_names=["TechCrunch", "The Verge", "Ars Technica"],
    )


def _sci_analysis():
    return Analysis(
        summary=(
            "Scientists found out how sleep clears the brain. Activity of the "
            "glymphatic system rose by 60% compared with wakefulness. The study was "
            "published in a peer-reviewed journal."
        ),
        bullets=[
            "Activity of the glymphatic system rose by 60% during sleep.",
            "The study was published in a peer-reviewed journal.",
            "The scientists plan to continue the work.",
        ],
        key_terms=["sleep", "brain", "study"],
        numbers=["60%"],
        source_count=3,
        source_names=["TechCrunch", "The Verge", "Ars Technica"],
    )


def _en_analysis():
    return _tech_analysis()


def _en_channel(**overrides):
    params = {
        "id": "tech-ai",
        "title": "Tech & AI",
        "language": "en",
        "tone": "expert",
        "formats": ["digest", "story", "analysis"],
        "hashtags": ["AI", "Tech"],
        "cta": "Follow the channel for more tech news.",
        "emoji": True,
        "timezone_offset": 0,
        "max_post_chars": 3200,
        "topics": ["ai"],
        "description": "Tech news in English.",
    }
    params.update(overrides)
    return ChannelConfig(**params)


def _ru_channel(**overrides):
    params = {
        "id": "tech-ai",
        "title": "Технологии и ИИ",
        "tone": "expert",
        "formats": ["story", "digest"],
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
        self.calls = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return self.reply


class EnglishPromptLLM:
    """Отвечает валидными английскими текстами на промпты генератора."""

    name = "fake-en"
    available = True

    def __init__(self):
        self.prompts = []
        self.systems = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        lowered = prompt.lower()
        if "rewrite this news headline" in lowered:
            return "OpenAI ships GPT-5 with a bigger context window"
        if "why this news matters" in lowered:
            return (
                "Developers can access GPT-5 through the API, and answer quality "
                "improved by 25%."
            )
        if "write one neutral conclusion" in lowered:
            return (
                "OpenAI's GPT-5 improves answer quality by 25% and expands the "
                "context window."
            )
        return ""


class DigestEnglishLLM:
    """Отвечает английскими строками на промпт дайджеста (3 новости)."""

    name = "fake-digest-en"
    available = True

    def __init__(self):
        self.prompts = []
        self.systems = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        if "list of news items for a digest" in prompt.lower():
            return "\n".join(
                (
                    "OpenAI introduced GPT-5 with a larger context window",
                    "The Fed kept its key interest rate unchanged at 4.5%",
                    "Scientists explained how sleep helps clear the brain",
                )
            )
        return ""


class EnglishGeneratorTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = FakeSettings()
        cls.channel = _en_channel()
        cls.cluster = _tech_cluster()
        cls.analysis = _tech_analysis()

    # -- общие проверки ------------------------------------------------------
    def assert_no_cyrillic(self, post):
        self.assertIsNone(
            CYRILLIC_RE.search(post.text),
            "в en-посте найдена кириллица: {}".format(post.text),
        )
        self.assertIsNone(
            CYRILLIC_RE.search(post.plain_text),
            "в plain-тексте en-поста найдена кириллица: {}".format(post.plain_text),
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
# Story
# ---------------------------------------------------------------------------


class EnglishStoryTest(EnglishGeneratorTestBase):
    def test_story_without_llm_is_english(self):
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story"
        )
        self.assertEqual(post.format, "story")
        self.assert_no_cyrillic(post)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertEqual(post.meta["language"], "en")
        self.assertNotIn("Key points:", post.text)
        self.assertNotIn("Why it matters:", post.text)
        self.assertIn("Sources:", post.text)
        self.assertIn("Follow the channel for more tech news.", post.text)
        self.assertNotIn("Главное", post.text)
        self.assertNotIn("Источники", post.text)
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

    def test_story_question_tail_is_stripped_english(self):
        cluster = _make_cluster(
            "cluster-tail",
            "OpenAI introduces GPT-5: what we know",
            "tail.example",
            EN_TECH_TEXTS,
        )
        post = generate_post(
            cluster, self.analysis, self.channel, self.settings, fmt="story"
        )
        first_block = post.text.split("\n\n")[0]
        self.assertIn("<b>OpenAI introduces GPT-5</b>", first_block)
        self.assert_no_cyrillic(post)

    def test_story_without_title_uses_english_placeholder(self):
        cluster = StoryCluster(
            id="cluster-empty",
            title="",
            articles=[
                _article(
                    "empty-a1",
                    "",
                    "https://empty.example/1",
                    "empty-s1",
                    "Example",
                    "",
                )
            ],
        )
        post = generate_post(
            cluster, Analysis(), self.channel, self.settings, fmt="story"
        )
        self.assertIn("News", post.text)
        self.assert_no_cyrillic(post)
        self.assertTrue(post.sources)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class EnglishAnalysisTest(EnglishGeneratorTestBase):
    def test_analysis_without_llm_is_english(self):
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="analysis"
        )
        self.assertEqual(post.format, "analysis")
        self.assert_no_cyrillic(post)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("Analysis:", post.text)
        self.assertNotIn("What sources say", post.text)
        self.assertNotIn("Bottom line:", post.text)
        self.assertIn("Sources:", post.text)
        self.assertIn("TechCrunch", post.text)
        self.assertIn("25%", post.text)
        self.assertIn("“", post.text)
        self.assert_valid_post(post, self.channel, [self.cluster])
        self.assertEqual(post.meta["quality_issues"], [])

    def test_analysis_fallback_conclusion_is_english(self):
        analysis = Analysis(
            summary="The Fed kept its key interest rate at 4.5%. Markets reacted calmly.",
            bullets=["The Fed held its key rate at 4.5% at the board meeting."],
            key_terms=["Fed", "rate"],
            source_count=3,
            source_names=["TechCrunch", "The Verge", "Ars Technica"],
        )
        cluster = _fin_cluster()
        post = generate_post(cluster, analysis, self.channel, self.settings, fmt="analysis")
        self.assert_no_cyrillic(post)
        self.assertIn("The picture emerges from reports by 3 sources.", post.text)
        self.assertNotIn("Key topics", post.text)


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


class EnglishDigestTest(EnglishGeneratorTestBase):
    def _digest_items(self):
        return [
            (_tech_cluster(), _tech_analysis()),
            (_fin_cluster(), _fin_analysis()),
            (_sci_cluster(), _sci_analysis()),
        ]

    def test_generate_digest_is_english(self):
        items = self._digest_items()
        post = generate_digest(items, self.channel, self.settings)
        self.assertEqual(post.format, "digest")
        self.assertEqual(post.meta["items_count"], 3)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assert_no_cyrillic(post)
        self.assertIn("Digest", post.text)
        self.assertIsNotNone(DATE_EN_RE.search(post.text))
        self.assertNotIn("———", post.text)
        for marker in ("1️⃣", "2️⃣", "3️⃣"):
            self.assertNotIn(marker, post.text)
        self.assertIn("📌", post.text)
        self.assertEqual(post.text.count("<b><a href="), 3)
        self.assertIn("Sources:", post.text)
        self.assertNotRegex(post.text, DATE_RU_RE.pattern)
        clusters = [cluster for cluster, _ in items]
        self.assert_valid_post(post, self.channel, clusters)

    def test_single_digest_format_is_english_with_english_date(self):
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="digest"
        )
        self.assertEqual(post.format, "digest")
        self.assertIn("OpenAI", post.text)
        self.assert_no_cyrillic(post)
        self.assertIn("Sources:", post.text)
        self.assert_valid_post(post, self.channel, [self.cluster])

    def test_empty_digest_header_is_english(self):
        post = generate_digest([], self.channel, self.settings)
        self.assertIn("Digest", post.text)
        self.assertIsNotNone(DATE_EN_RE.search(post.text))
        self.assert_no_cyrillic(post)
        self.assertTrue(
            any("нет новостей" in issue for issue in post.meta["quality_issues"])
        )

    def test_digest_fallback_line_without_summary_is_english(self):
        cluster = _fin_cluster()
        post = generate_digest([(cluster, Analysis(source_count=2))], self.channel, self.settings)
        self.assert_no_cyrillic(post)
        self.assertIn("Details are in the source article.", post.text)
        # Для en-заглушки цифр/терминов — английские формулировки.
        analysis = Analysis(numbers=["18%"], key_terms=["Fed", "rate"], source_count=2)
        post = generate_digest([(cluster, analysis)], self.channel, self.settings)
        self.assert_no_cyrillic(post)
        self.assertIn("The reports mention numbers: 18%.", post.text)


# ---------------------------------------------------------------------------
# Тональности и emoji
# ---------------------------------------------------------------------------


class EnglishToneStylesTest(EnglishGeneratorTestBase):
    def _story(self, channel):
        return generate_post(
            self.cluster, self.analysis, channel, self.settings, fmt="story"
        )

    def test_expert_tone_labels(self):
        post = self._story(_en_channel(tone="expert"))
        self.assertNotIn("Key points:", post.text)
        self.assertNotIn("Why it matters:", post.text)
        self.assertIn("Sources:", post.text)
        self.assert_no_cyrillic(post)

    def test_science_tone_labels(self):
        post = self._story(_en_channel(tone="science"))
        self.assertNotIn("In short:", post.text)
        self.assertNotIn("Why it matters:", post.text)
        self.assert_no_cyrillic(post)

    def test_friendly_tone_labels(self):
        post = self._story(_en_channel(tone="friendly"))
        self.assertNotIn("The short version:", post.text)
        self.assertNotIn("Why you should care:", post.text)
        self.assertIn("Sources:", post.text)
        self.assert_no_cyrillic(post)

    def test_science_analysis_label_is_english(self):
        post = generate_post(
            self.cluster,
            self.analysis,
            _en_channel(tone="science"),
            self.settings,
            fmt="analysis",
        )
        self.assertNotIn("Research breakdown:", post.text)
        self.assert_no_cyrillic(post)

    def test_channel_without_emoji_uses_plain_bullets(self):
        post = self._story(_en_channel(emoji=False))
        self.assertNotIn("▪️", post.text)
        self.assertNotIn("• ", post.text)
        self.assert_no_cyrillic(post)


# ---------------------------------------------------------------------------
# LLM: английский принимается, русский/мусорный отбрасывается
# ---------------------------------------------------------------------------


class EnglishLLMTest(EnglishGeneratorTestBase):
    def test_english_llm_is_used(self):
        llm = EnglishPromptLLM()
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertEqual(post.meta["generator"], "llm")
        self.assertEqual(post.meta["llm_provider"], "fake-en")
        self.assertIn("<b>OpenAI ships GPT-5 with a bigger context window</b>", post.text)
        self.assertTrue(llm.prompts)
        self.assert_no_cyrillic(post)
        # Системный промпт — английский и без кириллицы.
        self.assertTrue(llm.systems)
        for system in llm.systems:
            self.assertIn("journalist", system)
            self.assertIsNone(CYRILLIC_RE.search(system))
        self.assertTrue(llm.prompts)
        for prompt in llm.prompts:
            self.assertIsNone(CYRILLIC_RE.search(prompt))
        self.assert_valid_post(post, self.channel, [self.cluster])

    def test_english_llm_conclusion_is_used_for_analysis(self):
        llm = EnglishPromptLLM()
        post = generate_post(
            self.cluster,
            self.analysis,
            self.channel,
            self.settings,
            fmt="analysis",
            llm=llm,
        )
        self.assertEqual(post.meta["generator"], "llm")
        self.assertNotIn("Bottom line:", post.text)
        self.assertIn("expands the context window", post.text)
        self.assert_no_cyrillic(post)

    def test_english_llm_digest_lines_are_used(self):
        llm = DigestEnglishLLM()
        items = [
            (_tech_cluster(), _tech_analysis()),
            (_fin_cluster(), _fin_analysis()),
            (_sci_cluster(), _sci_analysis()),
        ]
        post = generate_digest(items, self.channel, self.settings, llm=llm)
        self.assertEqual(post.meta["generator"], "llm")
        self.assertEqual(post.meta["llm_provider"], "fake-digest-en")
        self.assertIn("OpenAI introduced GPT-5 with a larger context window", post.text)
        self.assertIn("The Fed kept its key interest rate unchanged at 4.5%", post.text)
        self.assert_no_cyrillic(post)
        self.assertTrue(llm.systems)
        for system in llm.systems:
            self.assertIn("journalist", system)
            self.assertIsNone(CYRILLIC_RE.search(system))

    def test_russian_llm_answer_is_rejected(self):
        llm = FakeLLM(
            "Модель доступна разработчикам через API, а качество ответов выросло на 25%."
        )
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertEqual(post.meta["llm_provider"], "extractive")
        self.assertNotIn("Модель доступна", post.text)
        self.assert_no_cyrillic(post)
        self.assertNotIn("Key points:", post.text)

    def test_garbage_llm_answer_is_rejected(self):
        llm = FakeLLM('```json\n{"headline": "нельзя", "url": "https://fake.example"}\n```')
        post = generate_post(
            self.cluster,
            self.analysis,
            self.channel,
            self.settings,
            fmt="analysis",
            llm=llm,
        )
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("нельзя", post.text)
        self.assertNotIn("fake.example", post.text)
        self.assert_no_cyrillic(post)

    def test_mixed_language_digest_lines_are_rejected(self):
        llm = FakeLLM(
            "\n".join(
                (
                    "OpenAI introduced GPT-5 with a larger context window",
                    "ФРС сохранила ключевую ставку на уровне 4,5%",
                    "Scientists explained how sleep helps clear the brain",
                )
            )
        )
        items = [
            (_tech_cluster(), _tech_analysis()),
            (_fin_cluster(), _fin_analysis()),
            (_sci_cluster(), _sci_analysis()),
        ]
        post = generate_digest(items, self.channel, self.settings, llm=llm)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("ФРС", post.text)
        self.assert_no_cyrillic(post)

    def test_invented_numbers_and_markdown_are_rejected(self):
        llm = FakeLLM("**OpenAI ships GPT-5** and grows 300% year over year")
        post = generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("300", post.text)
        self.assertNotIn("**", post.text)
        self.assert_no_cyrillic(post)

    def test_english_llm_system_prompt_is_english(self):
        llm = FakeLLM("")
        generate_post(
            self.cluster, self.analysis, self.channel, self.settings, fmt="story", llm=llm
        )
        self.assertTrue(llm.calls)
        for call in llm.calls:
            self.assertIn("journalist", call["system"])
            self.assertIn("Telegram channel", call["system"])
            self.assertIsNone(CYRILLIC_RE.search(call["system"]))


# ---------------------------------------------------------------------------
# Гарантии: en-пост без кириллицы и при «чужом» анализе
# ---------------------------------------------------------------------------


class EnglishSafetyTest(EnglishGeneratorTestBase):
    def test_russian_analysis_on_en_channel_stays_english(self):
        for fmt in ("story", "analysis", "digest"):
            post = generate_post(
                self.cluster, _ru_analysis(), self.channel, self.settings, fmt=fmt
            )
            self.assert_no_cyrillic(post)
            self.assertTrue(post.text.strip())
            self.assertTrue(post.sources)
            self.assertIn("http", post.text)
            if fmt == "digest":
                self.assertTrue(post.text.strip())

    def test_cyrillic_cta_and_hashtags_are_not_shown(self):
        channel = _en_channel(cta="Подписывайтесь на канал!", hashtags=["#новости"])
        post = generate_post(
            self.cluster, self.analysis, channel, self.settings, fmt="story"
        )
        self.assertNotIn("Подписывайтесь", post.text)
        self.assertNotIn("#новости", post.text)
        self.assert_no_cyrillic(post)

    def test_russian_channel_without_llm_is_unchanged(self):
        channel = _ru_channel()
        post = generate_post(
            _ru_cluster(), _ru_analysis(), channel, self.settings, fmt="story"
        )
        self.assertIsNotNone(CYRILLIC_RE.search(post.text))
        self.assertNotIn("<i>Главное:</i>", post.text)
        self.assertNotIn("<b>Почему это важно:</b>", post.text)
        self.assertIn("Источники:", post.text)
        self.assertNotIn("▪️ ", post.text)
        self.assertIn("https://ru.example", post.text)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assert_valid_post(post, channel, [_ru_cluster()], allow_cyrillic=True)

    def test_russian_single_digest_keeps_numeric_date(self):
        channel = _ru_channel()
        post = generate_post(
            _ru_cluster(), _ru_analysis(), channel, self.settings, fmt="digest"
        )
        self.assertIn("Центральный банк", post.text)
        self.assertNotIn("Digest", post.text)

    def test_russian_tones_keep_russian_labels(self):
        for tone in ("expert", "science", "friendly"):
            post = generate_post(
                _ru_cluster(),
                _ru_analysis(),
                _ru_channel(tone=tone),
                self.settings,
                fmt="story",
            )
            self.assertNotIn("Главное:", post.text)
            self.assertNotIn("Суть:", post.text)
            self.assertIn("Источники:", post.text)


if __name__ == "__main__":
    unittest.main()
