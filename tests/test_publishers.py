"""Тесты публикаторов: dry-run, Telegram, ВКонтакте, реестр и нарезка HTML.

Сеть не используется: urllib.request.urlopen подменяется фейковыми ответами,
dry-run проверяется по реальным файлам во временном каталоге.
"""
from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from content_factory.config import DEFAULT_SETTINGS, Settings
from content_factory.models import ChannelConfig, GeneratedPost, SourceConfig
from content_factory.publishers import (
    DryRunPublisher,
    FacebookPublisher,
    InstagramPublisher,
    LinkedInPublisher,
    MediumPublisher,
    PinterestPublisher,
    TelegramPublisher,
    ThreadsPublisher,
    VKPublisher,
    XPublisher,
    available_publishers,
    get_publisher,
    publisher_classes,
)
from content_factory.publishers.base import TELEGRAM_MESSAGE_LIMIT, split_html_message
from content_factory.utils import normalize_space, strip_html

_ENV_KEYS = (
    "CONTENT_FACTORY_DRY_RUN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID_TECH_AI",
    "VK_ACCESS_TOKEN",
    "VK_GROUP_ID",
    "TG_API_ID",
    "TG_API_HASH",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_SECRET",
    "FACEBOOK_PAGE_ID",
    "FACEBOOK_PAGE_TOKEN",
    "LINKEDIN_ACCESS_TOKEN",
    "LINKEDIN_AUTHOR_URN",
    "MEDIUM_TOKEN",
    "THREADS_USER_ID",
    "THREADS_ACCESS_TOKEN",
    "INSTAGRAM_USER_ID",
    "INSTAGRAM_ACCESS_TOKEN",
    "INSTAGRAM_IMAGE_URL",
    "PINTEREST_ACCESS_TOKEN",
    "PINTEREST_BOARD_ID",
    "PINTEREST_IMAGE_URL",
)


class FakeResponse:
    """Минимальная замена http.client.HTTPResponse для urlopen."""

    def __init__(self, payload, status: int = 200) -> None:
        if isinstance(payload, bytes):
            self.payload = payload
        else:
            self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self, *args, **kwargs) -> bytes:  # noqa: D102 - сигнатура stdlib
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


def http_error(url: str, code: int, description: str) -> urllib.error.HTTPError:
    body = json.dumps({"ok": False, "description": description}).encode("utf-8")
    return urllib.error.HTTPError(url, code, description, {}, io.BytesIO(body))


class PublisherTestCase(unittest.TestCase):
    """Общая обвязка: временный корень, чистые переменные окружения, фикстуры."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._saved_env = {key: os.environ.pop(key, None) for key in _ENV_KEYS}
        self.addCleanup(self._restore_env)

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

    def make_channel(self, **overrides) -> ChannelConfig:
        values = {
            "id": "tech-ai",
            "title": "Технологии и ИИ",
            "topics": ["технологии"],
            "telegram_chat_id": "@test_channel",
            "publisher_ids": ["telegram"],
            "sources": [
                SourceConfig(
                    id="source-1",
                    type="rss",
                    url="https://example.com/rss",
                    name="Пример",
                )
            ],
        }
        values.update(overrides)
        return ChannelConfig(**values)

    def make_post(self, text: str = "<b>Заголовок</b>\n\nТекст поста.", **overrides) -> GeneratedPost:
        values = {
            "id": "post-1",
            "channel_id": "tech-ai",
            "cluster_id": "cluster-1",
            "format": "story",
            "text": text,
            "hashtags": ["#тест"],
            "sources": [
                {"title": "Новость", "url": "https://example.com/news", "source": "Пример"}
            ],
            "meta": {"generator": "extractive", "tone": "expert"},
        }
        values.update(overrides)
        return GeneratedPost(**values)


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------
class DryRunPublisherTests(PublisherTestCase):
    def test_creates_txt_and_html_in_outbox(self) -> None:
        settings = self.make_settings(dry_run=True)
        channel = self.make_channel()
        post = self.make_post()
        result = DryRunPublisher(settings).publish(post, channel, settings)

        self.assertTrue(result.ok)
        self.assertTrue(result.dry_run)
        self.assertEqual(result.publisher, "dryrun")
        self.assertEqual(result.channel_id, channel.id)
        self.assertEqual(result.post_id, post.id)

        html_path = Path(result.url)
        txt_path = Path(result.external_id)
        self.assertTrue(html_path.is_file(), html_path)
        self.assertTrue(txt_path.is_file(), txt_path)
        self.assertEqual(html_path.suffix, ".html")
        self.assertEqual(txt_path.suffix, ".txt")
        self.assertEqual(html_path.parent.name, channel.id)
        self.assertTrue(str(html_path).startswith(str(settings.outbox_dir)))
        self.assertIn(post.id, html_path.name)

        txt = txt_path.read_text(encoding="utf-8")
        self.assertIn("DRY RUN", txt)
        self.assertIn("Заголовок", txt)
        self.assertIn("Технологии и ИИ", txt)

        html = html_path.read_text(encoding="utf-8")
        self.assertIn("DRY RUN", html)
        self.assertIn("НЕ ОПУБЛИКОВАНО", html)
        self.assertIn("<style>", html)
        self.assertIn("Технологии и ИИ", html)
        self.assertIn("https://example.com/news", html)
        self.assertNotIn("cdn.", html)
        self.assertNotIn("fonts.googleapis.com", html)

    def test_english_channel_preview_has_no_cyrillic(self) -> None:
        """Dry-run предпросмотр en-канала тоже полностью английский."""
        settings = self.make_settings(dry_run=True)
        channel = self.make_channel(title="Tech & AI", language="en")
        post = self.make_post(
            text="<b>AI is changing everything</b>\n\nEnglish post body.",
            hashtags=["#AI"],
            sources=[
                {
                    "title": "AI news",
                    "url": "https://example.com/ai",
                    "source": "Example",
                }
            ],
        )
        result = DryRunPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok)
        txt = Path(result.external_id).read_text(encoding="utf-8")
        html = Path(result.url).read_text(encoding="utf-8")
        self.assertNotRegex(txt, r"[А-Яа-яЁё]")
        self.assertNotRegex(html, r"[А-Яа-яЁё]")
        self.assertIn("DRY RUN", txt)
        self.assertIn("Channel:", txt)
        self.assertIn("Sources:", txt)
        self.assertIn("Hashtags:", txt)
        self.assertIn("https://example.com/ai", html)
        self.assertIn('lang="en"', html)

    def test_escapes_external_text_and_title(self) -> None:
        settings = self.make_settings(dry_run=True)
        channel = self.make_channel(title="Канал <script>alert(1)</script>")
        post = self.make_post(text="<b>Безопасно</b>")
        result = DryRunPublisher(settings).publish(post, channel, settings)
        html = Path(result.url).read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_does_not_touch_network(self) -> None:
        settings = self.make_settings(dry_run=True)
        channel = self.make_channel()
        post = self.make_post()
        with mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")
        ):
            result = DryRunPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok)
        self.assertEqual(DryRunPublisher(settings).check()[0], True)


# ---------------------------------------------------------------------------
# реестр
# ---------------------------------------------------------------------------
class PublisherRegistryTests(PublisherTestCase):
    def test_available_publishers(self) -> None:
        required = {"dryrun", "facebook", "instagram", "linkedin", "medium",
                    "pinterest", "reddit", "telegram", "threads", "tumblr", "vk", "x"}
        self.assertTrue(required.issubset(set(available_publishers())))
        self.assertIn("telegram", publisher_classes())
        self.assertIn("vk", publisher_classes())
        self.assertIn("x", publisher_classes())
        self.assertIn("facebook", publisher_classes())
        self.assertIn("linkedin", publisher_classes())
        self.assertIn("medium", publisher_classes())
        self.assertIn("tumblr", publisher_classes())
        self.assertIn("reddit", publisher_classes())
        self.assertIn("dryrun", publisher_classes())

    def test_dry_run_always_returns_dry_run(self) -> None:
        settings = self.make_settings(dry_run=True)
        for name in ("telegram", "vk", "dryrun", "unknown-publisher"):
            self.assertIsInstance(get_publisher(name, settings), DryRunPublisher, name)

    def test_real_publishers_without_dry_run(self) -> None:
        settings = self.make_settings(dry_run=False)
        self.assertIsInstance(get_publisher("telegram", settings), TelegramPublisher)
        self.assertIsInstance(get_publisher("vk", settings), VKPublisher)
        self.assertIsInstance(get_publisher("dryrun", settings), DryRunPublisher)
        self.assertIsInstance(get_publisher("tg", settings), TelegramPublisher)
        self.assertIsInstance(get_publisher("dry-run", settings), DryRunPublisher)

    def test_unknown_publisher_raises(self) -> None:
        settings = self.make_settings(dry_run=False)
        with self.assertRaises(ValueError):
            get_publisher("myspace", settings)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
class TelegramPublisherTests(PublisherTestCase):
    def _capture(self, responses):
        """Возвращает (список запросов, side_effect для urlopen)."""
        requests = []
        iterator = iter(responses)

        def fake_urlopen(request, timeout=None):
            body = request.data.decode("utf-8") if getattr(request, "data", None) else ""
            requests.append(
                {
                    "url": request.full_url,
                    "payload": dict(urllib.parse.parse_qsl(body)),
                    "timeout": timeout,
                }
            )
            try:
                return next(iterator)
            except StopIteration:
                return FakeResponse({"ok": True, "result": {"message_id": len(requests)}})

        return requests, fake_urlopen

    def test_send_message_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post(text="<b>Привет</b>\n\nТекст.")
        requests, fake_urlopen = self._capture(
            [FakeResponse({"ok": True, "result": {"message_id": 42}})]
        )
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test-token"}), mock.patch(
            "content_factory.publishers.telegram.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)

        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.dry_run)
        self.assertEqual(result.publisher, "telegram")
        self.assertEqual(result.external_id, "42")
        self.assertEqual(result.url, "https://t.me/test_channel/42")
        self.assertEqual(len(requests), 1)
        self.assertIn("/sendMessage", requests[0]["url"])
        self.assertIn("123:test-token", requests[0]["url"])
        payload = requests[0]["payload"]
        self.assertEqual(payload["chat_id"], "@test_channel")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("<b>Привет</b>", payload["text"])
        self.assertIn("disable_web_page_preview", payload)

    def test_ad_photo_file_id_is_sent_as_photo(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post(text="Рекламный текст")
        post.meta["photo_file_id"] = "AgACAgIAAxkBAAI"
        requests, fake_urlopen = self._capture(
            [FakeResponse({"ok": True, "result": {"message_id": 55}})]
        )
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test-token"}), mock.patch(
            "content_factory.publishers.telegram.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(requests), 1)
        self.assertIn("/sendPhoto", requests[0]["url"])
        self.assertEqual(requests[0]["payload"]["photo"], "AgACAgIAAxkBAAI")
        self.assertEqual(requests[0]["payload"]["caption"], "Рекламный текст")

    def test_api_error_is_returned_not_raised(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test-token"}), mock.patch(
            "content_factory.publishers.telegram.urllib.request.urlopen",
            return_value=FakeResponse({"ok": False, "description": "Bad Request: chat not found"}),
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("chat not found", result.error)
        self.assertFalse(result.dry_run)

    def test_http_error_is_returned_not_raised(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        error = http_error(
            "https://api.telegram.org/bot123/sendMessage", 403, "Forbidden: bot is not a member"
        )
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test-token"}), mock.patch(
            "content_factory.publishers.telegram.urllib.request.urlopen", side_effect=error
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("bot is not a member", result.error)

    def test_long_post_is_split_without_breaking_html(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        body = "Это длинный пост. " * 450  # около 8000 символов
        post = self.make_post(text="<b>Важное</b>\n\n" + body + "\n\n<i>Конец</i>")
        ids = [101, 102, 103, 104]
        responses = [FakeResponse({"ok": True, "result": {"message_id": value}}) for value in ids]
        requests, fake_urlopen = self._capture(responses)
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test-token"}), mock.patch(
            "content_factory.publishers.telegram.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)

        self.assertTrue(result.ok, result.error)
        self.assertGreaterEqual(len(requests), 2)
        for request in requests:
            text = request["payload"]["text"]
            self.assertLessEqual(len(text), TELEGRAM_MESSAGE_LIMIT)
            self.assertEqual(text.count("<b>"), text.count("</b>"))
            self.assertEqual(text.count("<i>"), text.count("</i>"))
        # текст не потерялся (сравнение по словам)
        joined = normalize_space(" ".join(strip_html(r["payload"]["text"]) for r in requests))
        expected = normalize_space(strip_html(post.text))
        self.assertEqual(joined, expected)
        self.assertEqual(result.external_id, str(ids[len(requests) - 1]))

    def test_missing_token_returns_error_and_check_fails(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        with mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)
            ok, message = TelegramPublisher(settings).check()
        self.assertFalse(result.ok)
        self.assertIn("TELEGRAM_BOT_TOKEN", result.error)
        self.assertFalse(ok)
        self.assertIn("TELEGRAM_BOT_TOKEN", message)

    def test_check_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:test-token"}), mock.patch(
            "content_factory.publishers.telegram.urllib.request.urlopen",
            return_value=FakeResponse({"ok": True, "result": {"username": "my_bot"}}),
        ):
            ok, message = TelegramPublisher(settings).check()
        self.assertTrue(ok)
        self.assertIn("@my_bot", message)

    def test_chat_id_from_environment(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel(telegram_chat_id="")
        post = self.make_post()
        requests, fake_urlopen = self._capture(
            [FakeResponse({"ok": True, "result": {"message_id": 7}})]
        )
        env = {
            "TELEGRAM_BOT_TOKEN": "123:test-token",
            "TELEGRAM_CHAT_ID_TECH_AI": "-1001234567890",
        }
        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.telegram.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(requests[0]["payload"]["chat_id"], "-1001234567890")
        # числовой id не даёт публичной ссылки t.me
        self.assertEqual(result.url, "")

    def test_dry_run_delegates_even_for_real_publisher(self) -> None:
        settings = self.make_settings(dry_run=True)
        channel = self.make_channel()
        post = self.make_post()
        with mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")
        ):
            result = TelegramPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok)
        self.assertTrue(result.dry_run)
        self.assertTrue(Path(result.url).is_file())


# ---------------------------------------------------------------------------
# ВКонтакте
# ---------------------------------------------------------------------------
class VKPublisherTests(PublisherTestCase):
    def test_wall_post_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel(publisher_ids=["vk"])
        post = self.make_post(text="<b>ВК</b>\n\nТекст для стены.")
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["payload"] = dict(
                urllib.parse.parse_qsl(request.data.decode("utf-8"))
            )
            return FakeResponse({"response": {"post_id": 77}})

        env = {"VK_ACCESS_TOKEN": "vk-token", "VK_GROUP_ID": "12345"}
        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.vk.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = VKPublisher(settings).publish(post, channel, settings)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.publisher, "vk")
        self.assertEqual(result.url, "https://vk.com/wall-12345_77")
        self.assertEqual(captured["url"], "https://api.vk.com/method/wall.post")
        payload = captured["payload"]
        self.assertEqual(payload["owner_id"], "-12345")
        self.assertEqual(payload["v"], "5.199")
        self.assertEqual(payload["from_group"], "1")
        self.assertEqual(payload["message"], "ВК Текст для стены.")
        self.assertNotIn("<b>", payload["message"])

    def test_api_error_is_returned(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        response = FakeResponse(
            {"error": {"error_code": 100, "error_msg": "Invalid access_token"}}
        )
        env = {"VK_ACCESS_TOKEN": "bad", "VK_GROUP_ID": "1"}
        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.vk.urllib.request.urlopen", return_value=response
        ):
            result = VKPublisher(settings).publish(post, channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("Invalid access_token", result.error)

    def test_missing_config(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        with mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")
        ):
            result = VKPublisher(settings).publish(post, channel, settings)
            ok, message = VKPublisher(settings).check()
        self.assertFalse(result.ok)
        self.assertIn("VK_ACCESS_TOKEN", result.error)
        self.assertFalse(ok)
        self.assertIn("VK_ACCESS_TOKEN", message)

    def test_dry_run_delegates(self) -> None:
        settings = self.make_settings(dry_run=True)
        channel = self.make_channel()
        post = self.make_post()
        with mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")
        ):
            result = VKPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok)
        self.assertTrue(result.dry_run)

    def test_unexpected_exception_is_contained(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        env = {"VK_ACCESS_TOKEN": "token", "VK_GROUP_ID": "1"}
        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.vk.urllib.request.urlopen",
            side_effect=RuntimeError("boom"),
        ):
            result = VKPublisher(settings).publish(post, channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("Непредвиденная ошибка", result.error)


# ---------------------------------------------------------------------------
# нарезка HTML
# ---------------------------------------------------------------------------
class XPublisherTests(PublisherTestCase):
    def _run(self, response, env):
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post(text="<b>X</b>\n\nТекст для X.")
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization") or ""
            captured["body"] = request.data.decode("utf-8") if request.data else ""
            return response

        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.social.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = XPublisher(settings).publish(post, channel, settings)
        return result, captured

    def test_tweet_success(self) -> None:
        env = {
            "X_API_KEY": "ck", "X_API_SECRET": "cs",
            "X_ACCESS_TOKEN": "at", "X_ACCESS_SECRET": "as",
        }
        result, captured = self._run(FakeResponse({"data": {"id": "12345"}}), env)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.publisher, "x")
        self.assertEqual(result.url, "https://x.com/i/web/status/12345")
        self.assertEqual(captured["url"], "https://api.x.com/2/tweets")
        self.assertIn("Текст для X.", captured["body"])
        self.assertNotIn("<b>", captured["body"])
        self.assertTrue(captured["auth"].startswith("OAuth "))
        self.assertIn("oauth_signature=", captured["auth"])

    def test_missing_creds(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        with mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")
        ):
            result = XPublisher(settings).publish(post, channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("не настроен", result.error)

    def test_api_error(self) -> None:
        env = {
            "X_API_KEY": "ck", "X_API_SECRET": "cs",
            "X_ACCESS_TOKEN": "at", "X_ACCESS_SECRET": "as",
        }
        result, _ = self._run(FakeResponse({"detail": "Unauthorized"}), env)
        self.assertFalse(result.ok)
        self.assertIn("Unauthorized", result.error)


class FacebookPublisherTests(PublisherTestCase):
    def test_page_post_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["payload"] = dict(urllib.parse.parse_qsl(request.data.decode("utf-8")))
            return FakeResponse({"id": "111_222"})

        with mock.patch.dict(os.environ, {"FACEBOOK_PAGE_ID": "111", "FACEBOOK_PAGE_TOKEN": "tok"}), mock.patch(
            "content_factory.publishers.social.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = FacebookPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(captured["url"], "https://graph.facebook.com/v21.0/111/feed")
        self.assertEqual(captured["payload"]["access_token"], "tok")
        self.assertIn("111_222", result.url)


class LinkedInPublisherTests(PublisherTestCase):
    def test_post_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["auth"] = request.get_header("Authorization") or ""
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({})

        env = {"LINKEDIN_ACCESS_TOKEN": "tok", "LINKEDIN_AUTHOR_URN": "urn:li:organization:1"}
        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.social.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = LinkedInPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(captured["auth"], "Bearer tok")
        self.assertEqual(captured["body"]["author"], "urn:li:organization:1")
        self.assertEqual(captured["body"]["lifecycleState"], "PUBLISHED")


class MediumPublisherTests(PublisherTestCase):
    def test_post_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post(text="<b>Заголовок</b>\n\nТекст статьи для Medium.")
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            if request.full_url.endswith("/me"):
                return FakeResponse({"data": {"id": "u1"}})
            return FakeResponse(
                {"data": {"id": "p1", "url": "https://medium.com/p/1"}}
            )

        with mock.patch.dict(os.environ, {"MEDIUM_TOKEN": "tok"}), mock.patch(
            "content_factory.publishers.social.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = MediumPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.url, "https://medium.com/p/1")
        self.assertEqual(len(calls), 2)


class ThreadsPublisherTests(PublisherTestCase):
    def test_post_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        post = self.make_post()
        payloads = []

        def fake_urlopen(request, timeout=None):
            payloads.append(dict(urllib.parse.parse_qsl(request.data.decode("utf-8"))))
            return FakeResponse({"id": "container-1"} if len(payloads) == 1 else {"id": "post-1"})

        env = {"THREADS_USER_ID": "123", "THREADS_ACCESS_TOKEN": "tok"}
        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.social.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = ThreadsPublisher(settings).publish(post, channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(payloads[0]["media_type"], "TEXT")
        self.assertEqual(payloads[1]["creation_id"], "container-1")

    def test_missing_creds(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("сеть не ожидалась")):
            result = ThreadsPublisher(settings).publish(self.make_post(), channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("не настроен", result.error)


class InstagramPublisherTests(PublisherTestCase):
    def test_missing_image_url(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        env = {"INSTAGRAM_USER_ID": "123", "INSTAGRAM_ACCESS_TOKEN": "tok"}
        with mock.patch.dict(os.environ, env):
            result = InstagramPublisher(settings).publish(self.make_post(), channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("картинки", result.error)

    def test_post_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        env = {"INSTAGRAM_USER_ID": "123", "INSTAGRAM_ACCESS_TOKEN": "tok",
               "INSTAGRAM_IMAGE_URL": "https://example.com/card.png"}
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            return FakeResponse({"id": "media-1"})

        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.social.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = InstagramPublisher(settings).publish(self.make_post(), channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(calls), 2)


class PinterestPublisherTests(PublisherTestCase):
    def test_post_success(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        env = {"PINTEREST_ACCESS_TOKEN": "tok", "PINTEREST_BOARD_ID": "42",
               "PINTEREST_IMAGE_URL": "https://example.com/card.png"}
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"id": "pin-1"})

        with mock.patch.dict(os.environ, env), mock.patch(
            "content_factory.publishers.social.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = PinterestPublisher(settings).publish(self.make_post(), channel, settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(captured["body"]["board_id"], "42")
        self.assertEqual(captured["body"]["media_source"]["source_type"], "image_url")
        self.assertIn("pin-1", result.url)

    def test_missing_image(self) -> None:
        settings = self.make_settings(dry_run=False)
        channel = self.make_channel()
        env = {"PINTEREST_ACCESS_TOKEN": "tok", "PINTEREST_BOARD_ID": "42"}
        with mock.patch.dict(os.environ, env):
            result = PinterestPublisher(settings).publish(self.make_post(), channel, settings)
        self.assertFalse(result.ok)
        self.assertIn("картинки", result.error)


class SplitHtmlMessageTests(unittest.TestCase):
    def test_short_text_unchanged(self) -> None:
        text = "<b>Короткий</b> пост"
        self.assertEqual(split_html_message(text), [text])

    def test_empty_text(self) -> None:
        self.assertEqual(split_html_message(""), [])

    def test_plain_long_text(self) -> None:
        text = "слово " * 1500
        parts = split_html_message(text)
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertLessEqual(len(part), TELEGRAM_MESSAGE_LIMIT)
        self.assertEqual(
            normalize_space(" ".join(parts)),
            normalize_space(text),
        )

    def test_tags_are_not_broken(self) -> None:
        text = "<b>" + ("важно " * 1200) + "</b>"
        parts = split_html_message("<b>" + text + "</b>")
        for part in parts:
            self.assertLessEqual(len(part), TELEGRAM_MESSAGE_LIMIT)
            self.assertEqual(part.count("<b>"), part.count("</b>"))
            self.assertTrue(part.startswith("<b>"))
            self.assertTrue(part.endswith("</b>"))

    def test_nested_tags_and_entities(self) -> None:
        text = (
            "<b><i>Заголовок</i></b>\n\n"
            + ("&laquo;цитата&raquo; и ещё немного текста. " * 250)
            + "\n\n<a href=\"https://example.com/long\">ссылка</a>"
        )
        parts = split_html_message(text)
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertLessEqual(len(part), TELEGRAM_MESSAGE_LIMIT)
            self.assertEqual(part.count("<b>"), part.count("</b>"))
            self.assertEqual(part.count("<i>"), part.count("</i>"))
        joined = "".join(parts)
        self.assertIn("&laquo;", joined)
        self.assertIn("https://example.com/long", joined)
        self.assertEqual(joined.count("&laquo;"), text.count("&laquo;"))

    def test_never_ends_with_half_opened_tag(self) -> None:
        text = "<a href=\"https://example.com\">" + ("ссылка " * 1000) + "</a>"
        parts = split_html_message(text)
        for part in parts:
            self.assertFalse(part.rstrip().endswith("<a"), part[-40:])
            self.assertEqual(part.count("<a href="), part.count("</a>"))


if __name__ == "__main__":
    unittest.main()
