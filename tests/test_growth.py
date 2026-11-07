"""Тесты аналитики роста: парсер t.me/s, снимки, дельты, формат отчётов."""
from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from content_factory.analytics.growth import (
    append_snapshot,
    build_snapshot,
    format_markdown,
    format_telegram,
    history_path,
    load_previous_snapshot,
    load_username_cache,
    save_username_cache,
    usernames_path,
)
from content_factory.analytics.preview import (
    PreviewError,
    fetch_preview,
    normalize_username,
    parse_count,
    parse_preview,
)
from content_factory.config import DEFAULT_SETTINGS, Settings
from content_factory.models import ChannelConfig

FIXTURE = Path(__file__).parent / "fixtures" / "tme_preview.html"
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")

    def read(self, *args, **kwargs) -> bytes:
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


def make_settings(root: Path) -> Settings:
    import copy

    raw = copy.deepcopy(DEFAULT_SETTINGS)
    raw["app"].update(
        {
            "data_dir": str(root / "data"),
            "db_path": str(root / "data" / "factory.sqlite3"),
            "outbox_dir": str(root / "data" / "outbox"),
            "reports_dir": str(root / "data" / "reports"),
            "logs_dir": str(root / "data" / "logs"),
        }
    )
    return Settings(
        root=root,
        raw=raw,
        settings_path=root / "config" / "settings.yaml",
        channels_path=root / "config" / "channels.en.yaml",
    )


def make_channel(channel_id: str = "crypto-news", **overrides) -> ChannelConfig:
    values = {
        "id": channel_id,
        "title": "Crypto & Blockchain",
        "telegram_chat_id": "-1003891468537",
        "language": "en",
    }
    values.update(overrides)
    return ChannelConfig(**values)


class PreviewParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = FIXTURE.read_text(encoding="utf-8")

    def test_channel_info(self) -> None:
        channel = parse_preview(self.html, username="HOOPY0007")
        self.assertEqual(channel.title, "Crypto & Blockchain")
        self.assertEqual(channel.username, "HOOPY0007")
        self.assertEqual(channel.subscribers, 3670)
        self.assertIn("US crypto news", channel.description)

    def test_posts_with_views_and_reactions(self) -> None:
        channel = parse_preview(self.html)
        self.assertEqual([post.message_id for post in channel.posts], [5981, 5982, 5983])
        first = channel.posts[0]
        self.assertEqual(first.views, 202)
        self.assertEqual(first.reactions, 100)
        self.assertEqual(first.reactions_detail, {"🔥": 100})
        self.assertEqual(first.published_at, "2026-11-04T17:16:58+00:00")
        self.assertEqual(first.post_url, "https://t.me/HOOPY0007/5981")
        self.assertIn("Crypto Midweek", first.snippet)
        self.assertFalse(first.is_sponsored)
        self.assertTrue(channel.posts[2].is_sponsored)

    def test_limit_keeps_last_posts(self) -> None:
        channel = parse_preview(self.html, limit=2)
        self.assertEqual([post.message_id for post in channel.posts], [5982, 5983])

    def test_engagement_rate(self) -> None:
        channel = parse_preview(self.html)
        value = channel.engagement_rate()
        self.assertIsNotNone(value)
        self.assertAlmostEqual(value, 301 / 619, places=4)

    def test_service_message_without_data_post_is_skipped(self) -> None:
        stripped = self.html.replace('data-post="HOOPY0007/5982"', "")
        channel = parse_preview(stripped)
        self.assertEqual([post.message_id for post in channel.posts], [5981, 5983])

    def test_service_messages_are_skipped(self) -> None:
        service = (
            '<html><body><div class="tgme_widget_message_wrap js-widget_message_wrap">'
            '<div class="tgme_widget_message_service" data-post="HOOPY0007/5998">'
            '<div class="tgme_widget_message_service_text">Channel photo updated</div>'
            "</div></div></body></html>"
        )
        self.assertEqual(parse_preview(service).posts, [])
        # закреплённый пост-уведомление («… pinned «…»») тоже не пост
        pinned = (
            '<html><body><div class="tgme_widget_message_wrap js-widget_message_wrap">'
            '<div class="tgme_widget_message" data-post="HOOPY0007/5999">'
            '<div class="tgme_widget_message_text">Crypto & Blockchain pinned «intro»</div>'
            "</div></div></body></html>"
        )
        self.assertEqual(parse_preview(pinned).posts, [])

    def test_parse_count(self) -> None:
        cases = {
            "3.67K": 3670,
            "202": 202,
            "1,2M": 1200000,
            "0": 0,
            "1.5k": 1500,
            "12 ": 12,
            "мусор": None,
            "": None,
            None: None,
        }
        for raw, expected in cases.items():
            self.assertEqual(parse_count(raw), expected, raw)

    def test_normalize_username(self) -> None:
        for raw in ("@HOOPY0007", "https://t.me/HOOPY0007", "t.me/HOOPY0007", "HOOPY0007"):
            self.assertEqual(normalize_username(raw), "HOOPY0007")

    def test_garbage_html_does_not_crash(self) -> None:
        channel = parse_preview("<html><body>нет разметки</body></html>", username="x")
        self.assertIsNone(channel.subscribers)
        self.assertEqual(channel.posts, [])


class FetchPreviewTests(unittest.TestCase):
    def test_success(self) -> None:
        html = FIXTURE.read_bytes()
        with mock.patch(
            "content_factory.analytics.preview.urllib.request.urlopen",
            return_value=FakeResponse(html),
        ) as mocked:
            channel = fetch_preview("@HOOPY0007", timeout=5)
        self.assertEqual(channel.subscribers, 3670)
        self.assertEqual(len(channel.posts), 3)
        request = mocked.call_args[0][0]
        self.assertEqual(request.full_url, "https://t.me/s/HOOPY0007")
        self.assertIn("Mozilla", request.get_header("User-agent"))

    def test_network_error_raises_preview_error(self) -> None:
        with mock.patch(
            "content_factory.analytics.preview.urllib.request.urlopen",
            side_effect=urllib.error.URLError("нет сети"),
        ):
            with self.assertRaises(PreviewError):
                fetch_preview("HOOPY0007")

    def test_http_error_raises_preview_error(self) -> None:
        error = urllib.error.HTTPError(
            "https://t.me/s/x", 404, "Not Found", {}, io.BytesIO(b"")
        )
        with mock.patch(
            "content_factory.analytics.preview.urllib.request.urlopen", side_effect=error
        ):
            with self.assertRaises(PreviewError):
                fetch_preview("missing_channel")

    def test_empty_username_raises(self) -> None:
        with self.assertRaises(PreviewError):
            fetch_preview("  ")


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_build_with_preview_and_api_subscribers(self) -> None:
        channel = make_channel()
        preview = parse_preview(self.html, username="HOOPY0007")
        snapshot = build_snapshot(
            [channel],
            {channel.id: preview},
            now=NOW,
            subscribers={channel.id: 3666},
        )
        row = snapshot["channels"][0]
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["subscribers"], 3666)  # точное значение из Bot API
        self.assertEqual(row["posts_shown"], 3)
        self.assertEqual(row["avg_views"], 206)
        self.assertEqual(row["max_views"], 211)
        self.assertAlmostEqual(row["engagement_rate"], 0.4863, places=3)
        self.assertEqual(row["top_post"]["url"], "https://t.me/HOOPY0007/5983")
        self.assertEqual(snapshot["totals"]["subscribers"], 3666)
        self.assertEqual(snapshot["totals"]["posts_24h"], 0)  # посты старше окна

    def test_delta_against_previous_snapshot(self) -> None:
        channel = make_channel()
        preview = parse_preview(self.html, username="HOOPY0007")
        previous = {
            "generated_at": "2026-11-06T09:00:00+00:00",
            "channels": [{"id": channel.id, "subscribers": 3000}],
        }
        snapshot = build_snapshot(
            [channel], {channel.id: preview}, previous=previous, subscribers={channel.id: 3666}
        )
        row = snapshot["channels"][0]
        self.assertEqual(row["subscribers_delta"], 666)
        self.assertEqual(snapshot["totals"]["subscribers_delta"], 666)

    def test_missing_preview_but_api_subscribers(self) -> None:
        channel = make_channel()
        snapshot = build_snapshot(
            [channel], {}, errors={channel.id: "t.me недоступен"}, subscribers={channel.id: 3}
        )
        row = snapshot["channels"][0]
        self.assertEqual(row["status"], "subscribers_only")
        self.assertEqual(row["subscribers"], 3)
        snapshot["usernames"] = {channel.id: "HOOPY0007"}
        text = format_telegram(snapshot)
        self.assertIn("только подписчики", text)
        self.assertIn("@HOOPY0007", text)

    def test_no_data_at_all(self) -> None:
        channel = make_channel()
        snapshot = build_snapshot([channel], {}, errors={channel.id: "нет сети"})
        self.assertEqual(snapshot["channels"][0]["status"], "no_data")
        self.assertIn("нет данных", format_telegram(snapshot))
        self.assertIn("нет превью", format_markdown(snapshot))

    def test_zero_reactions_and_no_views(self) -> None:
        channel = make_channel()
        html = re.sub(r'tgme_widget_message_views">[^<]+</span>', "", self.html)
        preview = parse_preview(html, username="HOOPY0007")
        snapshot = build_snapshot([channel], {channel.id: preview})
        self.assertIsNone(snapshot["channels"][0]["avg_views"])

    def test_telegram_format_under_limit(self) -> None:
        channels = [make_channel() for _ in range(6)]
        preview = parse_preview(self.html, username="HOOPY0007")
        snapshot = build_snapshot(
            channels, {channel.id: preview for channel in channels}, now=NOW
        )
        text = format_telegram(snapshot)
        self.assertLessEqual(len(text), 3900)
        self.assertIn("Рост каналов", text)
        self.assertIn("@HOOPY0007", text)

    def test_markdown_contains_table(self) -> None:
        channel = make_channel()
        preview = parse_preview(self.html, username="HOOPY0007")
        markdown = format_markdown(build_snapshot([channel], {channel.id: preview}))
        self.assertIn("| Канал | @ | Подписчики |", markdown)
        self.assertIn("Лучшие посты", markdown)


class HistoryAndCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.settings = make_settings(self.root)

    def test_snapshot_history_roundtrip(self) -> None:
        path = history_path(self.settings)
        self.assertFalse(path.exists())
        self.assertIsNone(load_previous_snapshot(path))

        append_snapshot(path, {"generated_at": "2026-11-06T09:00:00+00:00", "channels": []})
        append_snapshot(path, {"generated_at": "2026-11-07T09:00:00+00:00", "channels": []})
        previous = load_previous_snapshot(path)
        self.assertEqual(previous["generated_at"], "2026-11-07T09:00:00+00:00")

    def test_history_survives_broken_lines(self) -> None:
        path = history_path(self.settings)
        path.parent.mkdir(parents=True)
        path.write_text('не json\n{"generated_at": "x"}\n', encoding="utf-8")
        self.assertEqual(load_previous_snapshot(path)["generated_at"], "x")

    def test_username_cache_roundtrip(self) -> None:
        path = usernames_path(self.settings)
        save_username_cache(path, {"-1001": "AINEWS0007"})
        self.assertEqual(load_username_cache(path), {"-1001": "AINEWS0007"})
        save_username_cache(path, {"-1001": "AINEWS0007", "-1002": "HOOPY0007"})
        self.assertEqual(len(load_username_cache(path)), 2)

    def test_paths_live_under_data_dir(self) -> None:
        self.assertEqual(
            history_path(self.settings),
            self.settings.data_dir / "analytics" / "growth" / "history.jsonl",
        )
        self.assertEqual(usernames_path(self.settings).name, "usernames.json")


if __name__ == "__main__":
    unittest.main()
