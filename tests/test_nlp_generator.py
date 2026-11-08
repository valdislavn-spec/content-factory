"""Тесты генератора постов: три формата, Telegram HTML, лимиты, fallback LLM."""
import re
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser

from content_factory.config import Settings, load_channels
from content_factory.models import Analysis, Article, ChannelConfig, StoryCluster
from content_factory.nlp.analyzer import analyze_cluster
from content_factory.nlp.generator import generate_digest, generate_post

ALLOWED_TAGS = {"b", "i", "a", "code"}
PUBLISHED = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")
ENTITY_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)")


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


def _make_cluster(cluster_id, title, domain, texts, score=0.8):
    source_names = ("Habr", "CNews", "3DNews")
    articles = []
    for index, text in enumerate(texts):
        articles.append(
            _article(
                "{}-a{}".format(cluster_id, index),
                title if index == 0 else "{}: детали".format(title),
                "https://{}/article/{}".format(domain, index),
                "{}-s{}".format(cluster_id, index),
                source_names[index % len(source_names)],
                text,
                minutes=index * 20,
            )
        )
    return StoryCluster(id=cluster_id, title=title, articles=articles, score=score)


TECH_TEXTS = (
    "OpenAI представила новую модель GPT-5. Компания сообщила, что модель доступна "
    "разработчикам через API уже с 18 октября. По данным бенчмарков, качество ответов "
    "выросло на 25% по сравнению с предыдущей версией. Новая модель поддерживает "
    "контекст до 200 тысяч токенов. Эксперты отмечают рост интереса к подобным решениям.",
    "Компания OpenAI анонсировала модель GPT-5. Новая версия доступна через API, "
    "сообщает CNews. В компании заявили о росте производительности на 25% и поддержке "
    "контекста до 200 тысяч токенов. Разработчики смогут использовать модель для "
    "создания приложений.",
    "OpenAI выпустила GPT-5. Модель стала доступна разработчикам, пишет 3DNews. Ранее "
    "компания обещала улучшить качество ответов и увеличить контекст. Новая версия уже "
    "тестируется в приложениях партнёров.",
)
FIN_TEXTS = (
    "Центральный банк оставил ключевую ставку на уровне 18%. Регулятор отметил "
    "замедление инфляции до 8,5% и указал, что видит пространство для снижения ставки "
    "во втором полугодии. Решение принято на заседании совета директоров. Аналитики "
    "ожидали сохранения ставки.",
    "Банк России сохранил ключевую ставку на уровне 18%, сообщает РБК. В пресс-релизе "
    "регулятор указал на замедление инфляции до 8,5%. Следующее заседание совета "
    "директоров запланировано на декабрь. Рынок отреагировал спокойно.",
    "ЦБ сохранил ставку 18%, пишут Ведомости. Инфляция замедлилась до 8,5%, отмечает "
    "регулятор. Решение совпало с ожиданиями аналитиков. Снижение ставки возможно "
    "во втором полугодии.",
)
SCIENCE_TEXTS = (
    "Учёные выяснили, как сон очищает мозг. Активность глимфатической системы "
    "возрастала на 60% по сравнению с бодрствованием. Исследование опубликовано "
    "в рецензируемом журнале. Международная группа учёных подтвердила, что сон "
    "помогает мозгу избавляться от продуктов обмена.",
    "Исследователи показали, как сон очищает мозг, сообщает Naked Science. Во время "
    "медленноволнового сна скорость очистки увеличивалась на 55%. По словам авторов, "
    "это объясняет связь хронического недосыпа с риском нейродегенеративных "
    "заболеваний.",
    "Новое исследование объясняет очистку мозга во сне, пишет N+1. Активность системы "
    "возрастала на 60%. Результаты опубликованы в рецензируемом журнале. Учёные "
    "планируют продолжить работу.",
)


class FakeLLM:
    name = "fake"
    available = True

    def __init__(self, reply=""):
        self.reply = reply
        self.prompts = []

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        self.prompts.append(prompt)
        return self.reply


class PromptLLM:
    """Отвечает валидными текстами на разные промпты генератора."""

    name = "fake-llm"
    available = True

    def generate(self, prompt, system="", max_tokens=None, temperature=None):
        if "Перепиши заголовок" in prompt:
            return "OpenAI выпустила GPT-5: главное"
        if "почему эта новость важна" in prompt:
            return "Модель доступна разработчикам через API, а качество ответов выросло на 25%."
        return ""


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GeneratorTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.load(load_env=False)
        # Тесты генератора русские: явно читаем config/channels.yaml,
        # не полагаясь на app.channels_file из живых настроек.
        cls.channels = load_channels(
            cls.settings, path=PROJECT_ROOT / "config" / "channels.yaml"
        )
        cls.settings.raw.setdefault("app", {})["language"] = "ru"
        cls.tech_channel = next(c for c in cls.channels if c.id == "tech-ai")
        cls.cluster = _make_cluster("cluster-tech", "OpenAI представила новую модель GPT-5", "tech.example", TECH_TEXTS)
        cls.analysis = analyze_cluster(cls.cluster, cls.settings)

    def assert_valid_post(self, post, channel, cluster):
        collector = _HTMLCollector()
        collector.feed(post.text)
        collector.close()
        self.assertEqual(collector.errors, [])
        self.assertEqual(collector.stack, [])
        for tag in collector.tags:
            self.assertIn(tag, ALLOWED_TAGS)
        self.assertTrue(post.text.strip())
        self.assertLessEqual(len(post.text), channel.max_post_chars)
        self.assertTrue(post.plain_text.strip())
        # Вне тегов не должно остаться «сырых» угловых скобок и битых сущностей.
        without_tags = re.sub(r"<[^>]+>", "", post.text)
        self.assertNotIn("<", without_tags)
        self.assertNotIn(">", without_tags)
        self.assertIsNone(ENTITY_RE.search(without_tags))
        # Ссылки — только реальные URL из статей кластера.
        expected_urls = {article.url for article in cluster.articles}
        for href in collector.hrefs:
            # Пост может содержать ссылку на добровольную поддержку канала.
            if "donationalerts.com" in href:
                continue
            self.assertIn(href, expected_urls)
        self.assertTrue(post.sources)
        for source in post.sources:
            self.assertEqual(set(source), {"title", "url", "source"})
            self.assertIn(source["url"], expected_urls)
            self.assertTrue(source["title"])
        self.assertEqual(post.channel_id, channel.id)
        self.assertIn(post.format, {"story", "digest", "analysis"})
        self.assertIn(post.meta.get("generator"), {"llm", "extractive"})
        self.assertIn("quality_issues", post.meta)
        return collector


class StoryFormatTest(GeneratorTestBase):
    def test_story_is_valid_html_with_all_sections(self):
        post = generate_post(
            self.cluster, self.analysis, self.tech_channel, self.settings, fmt="story"
        )
        self.assertEqual(post.format, "story")
        self.assertEqual(post.meta["tone"], self.tech_channel.tone)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assert_valid_post(post, self.tech_channel, self.cluster)
        self.assertNotIn("Главное", post.text)
        self.assertNotIn("Почему это важно", post.text)
        self.assertIn("Источники", post.text)
        self.assertIn("Больше разборов", post.text)
        self.assertEqual(post.meta["quality_issues"], [])
        for tag in self.tech_channel.hashtags:
            self.assertIn(tag, post.text)
            self.assertIn(tag, post.hashtags)

    def test_user_text_is_escaped(self):
        analysis = analyze_cluster(self.cluster, self.settings)
        analysis.summary = 'Угроза <script>alert(1)</script> & "кавычки" и <b>теги</b>.'
        analysis.bullets = [
            'Угроза <script>alert(1)</script> & "кавычки"',
            "Второй факт про <b>теги</b> и 25%.",
            "Третий факт без спецсимволов.",
        ]
        post = generate_post(self.cluster, analysis, self.tech_channel, self.settings, fmt="story")
        self.assertIn("&lt;script&gt;", post.text)
        self.assertIn("&amp;", post.text)
        self.assertIn("&lt;b&gt;теги&lt;/b&gt;", post.text)
        self.assertNotIn("<script>", post.text)
        self.assert_valid_post(post, self.tech_channel, self.cluster)

    def test_headline_drops_generic_tail(self):
        cluster = _make_cluster(
            "cluster-tail",
            "OpenAI представила модель GPT-5: главное",
            "tail.example",
            TECH_TEXTS,
        )
        analysis = analyze_cluster(cluster, self.settings)
        post = generate_post(cluster, analysis, self.tech_channel, self.settings, fmt="story")
        first_block = post.text.split("\n\n")[0]
        self.assertIn("<b>OpenAI представила модель GPT-5</b>", first_block)
        # В источниках остаётся оригинальный заголовок статьи.
        self.assertIn(
            "OpenAI представила модель GPT-5: главное",
            [source["title"] for source in post.sources],
        )

    def test_headline_drops_what_is_known_tail(self):
        cluster = _make_cluster(
            "cluster-tail-2", "ЦБ сохранил ставку: что известно", "tail2.example", FIN_TEXTS
        )
        analysis = analyze_cluster(cluster, self.settings)
        post = generate_post(cluster, analysis, self.tech_channel, self.settings, fmt="story")
        self.assertIn("<b>ЦБ сохранил ставку</b>", post.text)

    def test_bullets_do_not_echo_headline(self):
        cluster = _make_cluster(
            "cluster-echo",
            "Центральный банк оставил ключевую ставку на уровне 18%",
            "echo.example",
            FIN_TEXTS,
        )
        analysis = analyze_cluster(cluster, self.settings)
        analysis.summary = "Банк России сохранил ключевую ставку. Инфляция замедлилась до 8,5%."
        analysis.bullets = [
            "Центральный банк оставил ключевую ставку на уровне 18%.",
            "Регулятор отметил замедление инфляции до 8,5%.",
            "Решение сохраняет ставку до конца года.",
        ]
        post = generate_post(cluster, analysis, self.tech_channel, self.settings, fmt="story")
        self.assertNotIn("▪️ ", post.text)
        self.assertNotIn("Почему это важно", post.text)
        self.assertIn("<b>", post.text)
        self.assertIn("ставк", post.text)


class AnalysisFormatTest(GeneratorTestBase):
    def test_analysis_format_sections(self):
        post = generate_post(
            self.cluster, self.analysis, self.tech_channel, self.settings, fmt="analysis"
        )
        self.assertEqual(post.format, "analysis")
        self.assert_valid_post(post, self.tech_channel, self.cluster)
        self.assertNotIn("Разбор:", post.text)
        self.assertNotIn("Что пишут источники", post.text)
        self.assertNotIn("Цифры", post.text)
        self.assertNotIn("Вывод", post.text)
        self.assertIn("Источники", post.text)
        self.assertIn("Habr", post.text)
        self.assertIn("25%", post.text)
        self.assertEqual(post.meta["quality_issues"], [])

    def test_analysis_uses_only_real_source_quotes(self):
        post = generate_post(
            self.cluster, self.analysis, self.tech_channel, self.settings, fmt="analysis"
        )
        source_texts = " ".join(
            (article.title + " " + article.text).lower() for article in self.cluster.articles
        )
        for perspective in self.analysis.perspectives:
            quote = perspective["quote"].lower().rstrip("…").strip()
            self.assertIn(quote, source_texts)
            self.assertIn(perspective["source_name"], post.text)


class DigestFormatTest(GeneratorTestBase):
    def _digest(self):
        clusters = [
            self.cluster,
            _make_cluster(
                "cluster-fin", "Центральный банк оставил ключевую ставку на уровне 18%", "fin.example", FIN_TEXTS
            ),
            _make_cluster(
                "cluster-sci", "Учёные выяснили, как сон очищает мозг", "sci.example", SCIENCE_TEXTS
            ),
        ]
        items = [(cluster, analyze_cluster(cluster, self.settings)) for cluster in clusters]
        return clusters, generate_digest(items, self.tech_channel, self.settings)

    def test_digest_contains_three_to_five_news(self):
        clusters, post = self._digest()
        self.assertEqual(post.format, "digest")
        self.assertTrue(post.cluster_id.startswith("digest-"))
        self.assertEqual(post.meta["items_count"], 3)
        self.assert_valid_post(
            post,
            self.tech_channel,
            StoryCluster(
                id="digest",
                title="Дайджест",
                articles=[article for cluster in clusters for article in cluster.articles],
            ),
        )
        self.assertIn("Дайджест", post.text)
        self.assertIsNotNone(DATE_RE.search(post.text))
        self.assertNotIn("———", post.text)
        # После даты и перед каждым пунктом есть перевод строки.
        self.assertNotIn("———", post.text)
        for marker in ("1️⃣", "2️⃣", "3️⃣"):
            self.assertNotIn(marker, post.text)
        for marker in ("📌", "📈", "📊"):
            self.assertIn(marker, post.text)
        # Ссылка на источник выделена жирным и оформлена как <a href>.
        self.assertEqual(post.text.count("<b><a href="), 3)
        plain = post.plain_text
        for cluster in clusters:
            self.assertIn(cluster.title[:20], plain)
        self.assertEqual(len(post.sources), 9)
        self.assertEqual(post.meta["quality_issues"], [])

    def test_digest_without_llm_is_extractive(self):
        _clusters, post = self._digest()
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("```", post.text)

    def test_digest_llm_garbage_falls_back(self):
        llm = FakeLLM("```json\n{\"result\": \"мусор от модели\"}\n```")
        clusters = [
            self.cluster,
            _make_cluster("cluster-fin", "ЦБ сохранил ставку", "fin2.example", FIN_TEXTS),
            _make_cluster("cluster-sci", "Учёные выяснили, как сон очищает мозг", "sci2.example", SCIENCE_TEXTS),
        ]
        items = [(cluster, analyze_cluster(cluster, self.settings)) for cluster in clusters]
        post = generate_digest(items, self.tech_channel, self.settings, llm=llm)
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("```", post.text)
        self.assertNotIn("мусор от модели", post.text)

    def test_empty_digest_is_flagged(self):
        post = generate_digest([], self.tech_channel, self.settings)
        self.assertEqual(post.format, "digest")
        self.assertTrue(post.text)
        self.assertTrue(any("нет новостей" in issue for issue in post.meta["quality_issues"]))
        self.assertEqual(post.sources, [])


class FormatSelectionAndToneTest(GeneratorTestBase):
    def test_default_format_uses_channel_formats(self):
        post = generate_post(self.cluster, self.analysis, self.tech_channel, self.settings)
        self.assertEqual(post.format, self.tech_channel.formats[0])

    def test_friendly_tone_labels(self):
        channel = next(c for c in self.channels if c.id == "travel")
        post = generate_post(self.cluster, self.analysis, channel, self.settings, fmt="story")
        self.assertEqual(post.meta["tone"], "friendly")
        self.assertNotIn("Коротко о главном", post.text)
        self.assertIn(channel.cta, post.text)

    def test_science_tone_labels(self):
        channel = next(c for c in self.channels if c.id == "science-health")
        post = generate_post(self.cluster, self.analysis, channel, self.settings, fmt="story")
        self.assertNotIn("Суть:", post.text)
        # У научного канала emoji отключены: только обычные маркеры.
        self.assertNotIn("🔹", post.text)
        self.assertNotIn("• ", post.text)

    def test_channel_without_emoji_has_no_emoji_markers(self):
        channel = next(c for c in self.channels if c.id == "business-finance")
        self.assertFalse(channel.emoji)
        post = generate_post(self.cluster, self.analysis, channel, self.settings, fmt="story")
        self.assertNotIn("📊", post.text)
        self.assertNotIn("▪️", post.text)
        self.assertNotIn("• ", post.text)

    def test_hashtags_derived_from_key_terms_if_channel_has_none(self):
        channel = ChannelConfig(
            id="no-tags",
            title="Без тегов",
            topics=["технологии"],
            formats=["story"],
            max_post_chars=3500,
            hashtags=[],
        )
        analysis = analyze_cluster(self.cluster, self.settings)
        analysis.key_terms = ["нейросеть", "OpenAI", "модель"]
        post = generate_post(self.cluster, analysis, channel, self.settings, fmt="story")
        self.assertTrue(post.hashtags)
        for tag in post.hashtags:
            self.assertTrue(tag.startswith("#"))
            self.assertIn(tag, post.text)


class LimitsAndSafetyTest(GeneratorTestBase):
    def test_every_format_fits_strict_limit(self):
        channel = ChannelConfig(
            id="short",
            title="Короткий канал",
            topics=["технологии"],
            formats=["story", "analysis", "digest"],
            max_post_chars=420,
            hashtags=["#тест"],
            cta="Подписывайтесь на канал, чтобы ничего не пропустить!",
            emoji=True,
        )
        for fmt in ("story", "analysis", "digest"):
            post = generate_post(self.cluster, self.analysis, channel, self.settings, fmt=fmt)
            self.assertLessEqual(len(post.text), 420, "формат {} длиннее лимита".format(fmt))
            collector = _HTMLCollector()
            collector.feed(post.text)
            collector.close()
            self.assertEqual(collector.errors, [])
            self.assertEqual(collector.stack, [])
            self.assertTrue(post.plain_text.strip())
            self.assertTrue(post.sources)

    def test_banned_words_are_reported_in_meta(self):
        analysis = analyze_cluster(self.cluster, self.settings)
        analysis.summary = "Инвесторам обещают гарантированный доход. Рынок растёт."
        analysis.bullets = [
            "Инвесторам обещают гарантированный доход.",
            "Второй тезис про рынок и рост.",
            "Третий тезис про ключевую ставку.",
        ]
        post = generate_post(self.cluster, analysis, self.tech_channel, self.settings, fmt="story")
        self.assertTrue(
            any("запрещённое слово" in issue for issue in post.meta["quality_issues"]),
            post.meta["quality_issues"],
        )

    def test_short_post_gets_quality_issue(self):
        cluster = StoryCluster(
            id="cluster-short",
            title="Короткая новость",
            articles=[
                _article(
                    "short-a1",
                    "Короткая новость",
                    "https://short.example/1",
                    "short-s1",
                    "Short",
                    "",
                )
            ],
        )
        analysis = analyze_cluster(cluster, self.settings)
        post = generate_post(cluster, analysis, self.tech_channel, self.settings, fmt="story")
        self.assertTrue(
            any("короче минимума" in issue for issue in post.meta["quality_issues"]),
            post.meta["quality_issues"],
        )
        # Даже короткий пост остаётся валидным HTML с источниками.
        collector = _HTMLCollector()
        collector.feed(post.text)
        collector.close()
        self.assertEqual(collector.errors, [])
        self.assertTrue(post.sources)

    def test_meta_contains_required_fields(self):
        post = generate_post(
            self.cluster, self.analysis, self.tech_channel, self.settings, fmt="story"
        )
        self.assertEqual(post.meta["format"], "story")
        self.assertEqual(post.meta["tone"], self.tech_channel.tone)
        self.assertEqual(post.meta["char_count"], len(post.text))
        self.assertEqual(post.id, post.id.strip())
        self.assertTrue(post.id)
        self.assertEqual(post.score, self.cluster.score)


class LLMGenerationTest(GeneratorTestBase):
    def test_garbage_llm_falls_back_to_templates(self):
        llm = FakeLLM("```json\n{\"headline\": \"нельзя\"}\n```")
        post = generate_post(
            self.cluster, self.analysis, self.tech_channel, self.settings, fmt="story", llm=llm
        )
        self.assertEqual(post.meta["generator"], "extractive")
        self.assertNotIn("```", post.text)
        self.assertNotIn("нельзя", post.text)
        self.assert_valid_post(post, self.tech_channel, self.cluster)

    def test_valid_llm_text_is_used(self):
        post = generate_post(
            self.cluster,
            self.analysis,
            self.tech_channel,
            self.settings,
            fmt="story",
            llm=PromptLLM(),
        )
        self.assertEqual(post.meta["generator"], "llm")
        # LLM-заголовок очищен от служебного хвоста «: главное».
        self.assertIn("<b>OpenAI выпустила GPT-5</b>", post.text)
        self.assertIn("OpenAI", post.text)
        self.assert_valid_post(post, self.tech_channel, self.cluster)

    def test_llm_links_and_numbers_are_validated(self):
        llm = FakeLLM(
            "OpenAI выпустила GPT-5 и выросла на 300%. Подробности: https://fake.example/x"
        )
        post = generate_post(
            self.cluster, self.analysis, self.tech_channel, self.settings, fmt="story", llm=llm
        )
        self.assertNotIn("300%", post.text)
        self.assertNotIn("fake.example", post.text)
        self.assertEqual(post.meta["generator"], "extractive")


if __name__ == "__main__":
    unittest.main()
