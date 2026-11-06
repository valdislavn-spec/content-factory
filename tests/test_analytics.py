"""Тесты аналитики: сбор метрик, отчёты HTML/Markdown, пустая и заполненная база."""
from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from content_factory.analytics.collector import (
    collect_all,
    collect_channel_metrics,
    fetch_subscribers,
)
from content_factory.analytics.report import (
    build_report,
    render_html,
    render_markdown,
    save_report,
)
from content_factory.config import DEFAULT_SETTINGS, Settings
from content_factory.models import (
    Article,
    ChannelConfig,
    GeneratedPost,
    MetricSnapshot,
    PublishResult,
    RunResult,
    utcnow,
)
from content_factory.storage import Storage

_ENV_KEYS = (
    "CONTENT_FACTORY_DRY_RUN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID_TECH_AI",
    "TG_API_ID",
    "TG_API_HASH",
)


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = (
            payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        )

    def read(self, *args, **kwargs) -> bytes:  # noqa: D102 - сигнатура stdlib
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


class _HtmlChecker(HTMLParser):
    """Проверяет, что в отчёте нет внешних/скриптовых ресурсов и теги читаются."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forbidden = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "link", "iframe", "object", "embed"):
            self.forbidden.append(tag)


class AnalyticsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._saved_env = {key: os.environ.pop(key, None) for key in _ENV_KEYS}
        self.addCleanup(self._restore_env)
        self.settings = self.make_settings()
        self.storage = Storage(self.settings.db_path)
        self.addCleanup(self.storage.close)

    def _restore_env(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_settings(self, dry_run: bool = True, **app_overrides) -> Settings:
        raw = copy.deepcopy(DEFAULT_SETTINGS)
        raw["app"].update(
            {
                "dry_run": dry_run,
                "data_dir": str(self.root / "data"),
                "db_path": str(self.root / "data" / "factory.sqlite3"),
                "outbox_dir": str(self.root / "data" / "outbox"),
                "reports_dir": str(self.root / "data" / "reports"),
                "logs_dir": str(self.root / "data" / "logs"),
            }
        )
        raw["app"].update(app_overrides)
        return Settings(
            root=self.root,
            raw=raw,
            settings_path=self.root / "config" / "settings.yaml",
            channels_path=self.root / "config" / "channels.yaml",
        )

    def make_channel(self, channel_id: str = "tech-ai", **overrides) -> ChannelConfig:
        values = {
            "id": channel_id,
            "title": "Технологии и ИИ",
            "description": "Главное из мира технологий",
            "topics": ["технологии"],
            "telegram_chat_id": "@test_channel",
        }
        values.update(overrides)
        return ChannelConfig(**values)

    # ---- наполнение базы ----
    def seed_articles(self, channel_id: str, count: int = 2) -> None:
        names = ["Пример", "Второй источник"]
        articles = [
            Article(
                id="article-{}".format(index),
                title="Новость {}".format(index),
                url="https://example.com/news/{}".format(index),
                source_id="source-{}".format(index % 2),
                source_name=names[index % 2],
                published_at=utcnow(),
                text="Учёные рассказали о новых технологиях и нейросетях.",
            )
            for index in range(count)
        ]
        self.storage.save_articles(channel_id, articles)

    def seed_posts(self, channel_id: str, count: int = 2) -> None:
        formats = ["story", "analysis"]
        for index in range(count):
            post = GeneratedPost(
                id="post-{}-{}".format(channel_id, index),
                channel_id=channel_id,
                cluster_id="cluster-{}".format(index),
                format=formats[index % len(formats)],
                text=(
                    "<b>Заголовок {}</b>\n\nТекст поста про технологии, "
                    "нейросети и исследования.".format(index)
                ),
                hashtags=["#технологии"],
                sources=[{"title": "Новость", "url": "https://example.com/news/1", "source": "Пример"}],
                created_at=utcnow(),
            )
            self.storage.save_post(post, status="generated" if index % 2 == 0 else "published")

    def seed_publications(self, channel_id: str, post_id: str) -> None:
        self.storage.save_publish(
            PublishResult(
                channel_id=channel_id,
                post_id=post_id,
                publisher="dryrun",
                ok=True,
                url=str(self.root / "data" / "outbox" / channel_id / "post.html"),
                dry_run=True,
            )
        )
        self.storage.save_publish(
            PublishResult(
                channel_id=channel_id,
                post_id=post_id,
                publisher="telegram",
                ok=False,
                error="Тестовая ошибка публикации",
                dry_run=False,
            )
        )

    def seed_metrics(self, channel_id: str, subscribers: int = 150) -> None:
        self.storage.save_metrics(
            MetricSnapshot(
                channel_id=channel_id,
                subscribers=subscribers,
                posts_total=2,
                posts_published=1,
                articles_total=2,
                clusters_total=1,
                avg_post_chars=100.0,
                top_sources=[{"source_name": "Пример", "count": 2}],
                top_terms=[{"term": "нейросети", "count": 3}],
                formats={"story": 1, "analysis": 1},
            )
        )

    def seed_run(self, channel_id: str, with_error: bool = True) -> None:
        run = RunResult(
            channel_id=channel_id,
            articles_fetched=2,
            articles_new=2,
            clusters=1,
            posts_generated=2,
            posts_published=1,
            dry_run=True,
        )
        if with_error:
            run.add_error("Тестовая ошибка запуска")
        self.storage.save_run(run.finish())

    def seed_all(self, channels) -> None:
        for channel in channels:
            self.seed_articles(channel.id)
            self.seed_posts(channel.id)
            self.seed_publications(channel.id, "post-{}-0".format(channel.id))
            self.seed_metrics(channel.id)
            self.seed_run(channel.id)


# ---------------------------------------------------------------------------
# пустая база
# ---------------------------------------------------------------------------
class EmptyReportTests(AnalyticsTestCase):
    def test_empty_build_report(self) -> None:
        channels = [self.make_channel(), self.make_channel("business-finance", title="Бизнес и финансы")]
        data = build_report(self.settings, self.storage, channels, days=7)

        self.assertEqual(data["days"], 7)
        self.assertTrue(data["dry_run"])
        self.assertFalse(data["has_data"])
        self.assertEqual(data["totals"]["channels"], 2)
        self.assertEqual(data["totals"]["articles"], 0)
        self.assertEqual(data["totals"]["posts"], 0)
        self.assertEqual(data["totals"]["publishes"]["total"], 0)
        self.assertIsNone(data["totals"]["subscribers"])
        self.assertEqual(len(data["per_channel"]), 2)
        self.assertIn("demo", data["hint"])
        self.assertEqual(data["llm"]["provider"], "extractive")
        self.assertIn(".", data["generated_at_local"])
        self.assertIn(":", data["generated_at_local"])

    def test_empty_html_is_self_contained(self) -> None:
        channels = [self.make_channel()]
        data = build_report(self.settings, self.storage, channels)
        html = render_html(data)

        self.assertGreater(len(html), 1000)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<style>", html)
        self.assertIn("</html>", html)
        self.assertIn("Технологии и ИИ", html)
        self.assertIn("Сводка", html)
        self.assertIn("DRY RUN", html)
        self.assertNotIn("http://", html.lower())
        self.assertNotIn("https://", html.lower())
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("cdn.", html.lower())
        self.assertEqual(html.count("<div"), html.count("</div>"))
        self.assertEqual(html.count("<table"), html.count("</table>"))
        self.assertEqual(html.count("<tr"), html.count("</tr>"))

        checker = _HtmlChecker()
        checker.feed(html)
        self.assertEqual(checker.forbidden, [])

    def test_empty_markdown(self) -> None:
        channels = [self.make_channel()]
        data = build_report(self.settings, self.storage, channels)
        markdown = render_markdown(data)
        self.assertIn("# Контент-завод: аналитика", markdown)
        self.assertIn("Технологии и ИИ", markdown)
        self.assertIn("## Сводка", markdown)
        self.assertIn("Публикаций пока нет", markdown)
        self.assertIn("Запусков пока не было", markdown)

    def test_save_report_creates_both_files(self) -> None:
        channels = [self.make_channel()]
        paths = save_report(self.settings, self.storage, channels, days=30)

        self.assertEqual(set(paths), {"html", "md"})
        html_path = Path(paths["html"])
        md_path = Path(paths["md"])
        self.assertTrue(html_path.is_absolute())
        self.assertTrue(md_path.is_absolute())
        self.assertTrue(html_path.is_file())
        self.assertTrue(md_path.is_file())
        self.assertEqual(html_path.name, "report.html")
        self.assertEqual(md_path.name, "report.md")
        self.assertIn("<!DOCTYPE html>", html_path.read_text(encoding="utf-8"))
        self.assertTrue(md_path.read_text(encoding="utf-8").strip())

    def test_report_without_channels(self) -> None:
        data = build_report(self.settings, self.storage, [], days=7)
        self.assertEqual(data["per_channel"], [])
        self.assertFalse(data["has_data"])
        self.assertIn("demo", data["hint"])
        self.assertIn("Каналы не настроены", render_html(data))


# ---------------------------------------------------------------------------
# заполненная база
# ---------------------------------------------------------------------------
class PopulatedReportTests(AnalyticsTestCase):
    def test_report_contains_real_numbers(self) -> None:
        channels = [self.make_channel()]
        self.seed_all(channels)
        data = build_report(self.settings, self.storage, channels, days=7)

        self.assertTrue(data["has_data"])
        totals = data["totals"]
        self.assertEqual(totals["articles"], 2)
        self.assertEqual(totals["posts"], 2)
        self.assertEqual(totals["publishes"]["total"], 2)
        self.assertEqual(totals["publishes"]["ok"], 1)
        self.assertEqual(totals["publishes"]["failed"], 1)
        self.assertEqual(totals["publishes"]["dry_run"], 1)
        self.assertEqual(totals["subscribers"], 150)

        channel_row = data["per_channel"][0]
        self.assertEqual(channel_row["subscribers"], 150)
        self.assertEqual(channel_row["articles"], 2)
        self.assertEqual(channel_row["posts"], 2)
        self.assertEqual(channel_row["publishes"]["ok"], 1)
        self.assertIsNotNone(channel_row["last_run"])

        self.assertIn("Сюжет", data["formats"])
        self.assertEqual(data["formats"]["Сюжет"], 1)
        self.assertEqual(data["formats"]["Анализ"], 1)
        terms = {item["term"]: item["count"] for item in data["top_terms"]}
        self.assertIn("нейросети", terms)
        self.assertEqual(terms["нейросети"], 3)
        self.assertTrue(data["sources"])
        self.assertTrue(data["errors"])
        messages = " ".join(item["message"] for item in data["errors"])
        self.assertIn("Тестовая ошибка запуска", messages)
        self.assertIn("Тестовая ошибка публикации", messages)
        self.assertTrue(data["publications"])
        self.assertEqual(len(data["runs"]), 1)

    def test_populated_html_and_markdown(self) -> None:
        channels = [self.make_channel()]
        self.seed_all(channels)
        paths = save_report(self.settings, self.storage, channels, days=7)
        html = Path(paths["html"]).read_text(encoding="utf-8")
        markdown = Path(paths["md"]).read_text(encoding="utf-8")

        self.assertIn("Технологии и ИИ", html)
        self.assertIn("150", html)
        self.assertIn("Сюжет", html)
        self.assertIn("нейросети", html)
        self.assertIn('class="bar-fill"', html)
        self.assertIn("Тестовая ошибка публикации", html)
        self.assertIn("dry-run", html)  # dry-run публикация помечена
        self.assertNotIn("<script", html.lower())
        self.assertEqual(html.count("<div"), html.count("</div>"))

        self.assertIn("| Технологии и ИИ (tech-ai) |", markdown)
        self.assertIn("## Источники", markdown)
        self.assertIn("## Последние публикации", markdown)
        self.assertIn("Тестовая ошибка запуска", markdown)

    def test_populated_report_with_other_channel_still_works(self) -> None:
        channels = [self.make_channel(), self.make_channel("travel", title="Путешествия")]
        self.seed_all(channels[:1])
        data = build_report(self.settings, self.storage, channels, days=7)
        self.assertEqual(len(data["per_channel"]), 2)
        empty_row = data["per_channel"][1]
        self.assertEqual(empty_row["id"], "travel")
        self.assertEqual(empty_row["posts"], 0)
        self.assertEqual(data["totals"]["posts"], 2)


# ---------------------------------------------------------------------------
# подписчики и сбор метрик
# ---------------------------------------------------------------------------
class FetchSubscribersTests(AnalyticsTestCase):
    def test_success(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            return FakeResponse({"ok": True, "result": 1234})

        with mock.patch(
            "content_factory.analytics.collector.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            value = fetch_subscribers("@test_channel", "123:token", 15)
        self.assertEqual(value, 1234)
        self.assertIn("getChatMemberCount", captured["url"])
        self.assertIn("chat_id=%40test_channel", captured["url"])

    def test_api_error_returns_none(self) -> None:
        with mock.patch(
            "content_factory.analytics.collector.urllib.request.urlopen",
            return_value=FakeResponse({"ok": False, "description": "Bad Request: chat not found"}),
        ):
            self.assertIsNone(fetch_subscribers("@test_channel", "123:token", 15))

    def test_http_error_returns_none(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.telegram.org/",
            403,
            "Forbidden",
            {},
            io.BytesIO(json.dumps({"ok": False, "description": "Forbidden"}).encode("utf-8")),
        )
        with mock.patch(
            "content_factory.analytics.collector.urllib.request.urlopen", side_effect=error
        ):
            self.assertIsNone(fetch_subscribers("@test_channel", "123:token", 15))

    def test_network_error_returns_none(self) -> None:
        with mock.patch(
            "content_factory.analytics.collector.urllib.request.urlopen",
            side_effect=urllib.error.URLError("нет сети"),
        ):
            self.assertIsNone(fetch_subscribers("@test_channel", "123:token", 15))

    def test_empty_input_returns_none_without_network(self) -> None:
        with mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")
        ):
            self.assertIsNone(fetch_subscribers("", "123:token", 15))
            self.assertIsNone(fetch_subscribers("@channel", "", 15))


class CollectorTests(AnalyticsTestCase):
    def test_dry_run_does_not_request_subscribers(self) -> None:
        channel = self.make_channel()
        self.seed_all([channel])
        with mock.patch(
            "content_factory.analytics.collector.fetch_subscribers",
            side_effect=AssertionError("в dry-run сеть не нужна"),
        ):
            snapshot = collect_channel_metrics(channel, self.settings, self.storage)

        self.assertIsNone(snapshot.subscribers)
        self.assertEqual(snapshot.posts_total, 2)
        self.assertEqual(snapshot.posts_published, 1)
        self.assertEqual(snapshot.articles_total, 2)
        self.assertEqual(snapshot.clusters_total, 2)
        self.assertTrue(snapshot.top_terms)
        self.assertEqual(snapshot.formats.get("story"), 1)
        latest = self.storage.latest_metrics(channel.id)
        self.assertIsNotNone(latest)
        self.assertTrue(latest["payload"]["dry_run"])

    def test_collects_subscribers_in_real_mode(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        self.seed_all([channel])
        with mock.patch(
            "content_factory.analytics.collector.fetch_subscribers", return_value=777
        ) as mocked, mock.patch(
            "content_factory.analytics.collector.collect_post_views", return_value={}
        ):
            snapshot = collect_channel_metrics(channel, settings, self.storage)
        self.assertEqual(snapshot.subscribers, 777)
        mocked.assert_called_once()
        latest = self.storage.latest_metrics(channel.id)
        self.assertEqual(latest["subscribers"], 777)

    def test_collect_all_skips_disabled_and_saves(self) -> None:
        enabled = self.make_channel()
        disabled = self.make_channel("travel", title="Путешествия", enabled=False)
        self.seed_all([enabled])
        snapshots = collect_all([enabled, disabled], self.settings, self.storage)
        self.assertEqual([item.channel_id for item in snapshots], [enabled.id])
        self.assertIsNotNone(self.storage.latest_metrics(enabled.id))
        self.assertIsNone(self.storage.latest_metrics(disabled.id))

    def test_collect_all_disabled_in_settings(self) -> None:
        self.settings.raw["analytics"]["enabled"] = False
        channel = self.make_channel()
        self.seed_all([channel])
        self.assertEqual(collect_all([channel], self.settings, self.storage), [])

    def test_collect_survives_broken_storage_methods(self) -> None:
        channel = self.make_channel()
        with mock.patch.object(
            self.storage, "channel_stats", side_effect=RuntimeError("база недоступна")
        ), mock.patch.object(
            self.storage, "get_posts", side_effect=RuntimeError("база недоступна")
        ):
            snapshot = collect_channel_metrics(channel, self.settings, self.storage)
        self.assertEqual(snapshot.posts_total, 0)
        self.assertEqual(snapshot.channel_id, channel.id)


if __name__ == "__main__":
    unittest.main()
