"""Тесты OSS Radar: отбор релизов, рендер, кэш, GitHub/libraries.io клиенты (без сети)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from content_factory.oss_radar import (
    GitHubClient,
    LibrariesIOClient,
    OSSRadarError,
    RateLimitError,
    Release,
    ResponseCache,
    _clean_body,
    channel_config,
    github_items_to_releases,
    libraries_io_releases,
    load_config,
    parse_iso,
    render_digest,
    select_recent,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def make_release(repo="ollama/ollama", tag="v1.0.0", hours_ago=1.0, prerelease=False, source="github"):
    return Release(
        repo=repo,
        tag=tag,
        url=f"https://github.com/{repo}/releases/tag/{tag}",
        published_at=NOW - timedelta(hours=hours_ago),
        body="Full Changelog: https://github.com/x/y/compare/a...b\n\nПоддержка новых моделей.",
        prerelease=prerelease,
        source=source,
    )


class ParseAndSelectTests(unittest.TestCase):
    def test_parse_iso_formats(self):
        self.assertEqual(parse_iso("2026-11-08T08:11:09Z"), datetime(2026, 11, 8, 8, 11, 9, tzinfo=timezone.utc))
        self.assertEqual(
            parse_iso("2026-10-09 12:56:54 UTC"), datetime(2026, 10, 9, 12, 56, 54, tzinfo=timezone.utc)
        )
        self.assertEqual(parse_iso("2026-10-09"), datetime(2026, 10, 9, tzinfo=timezone.utc))
        self.assertIsNone(parse_iso(""))
        self.assertIsNone(parse_iso("не дата"))

    def test_select_recent_filters_window_and_prereleases(self):
        releases = [
            make_release(tag="new", hours_ago=1),
            make_release(tag="old", hours_ago=48),
            make_release(tag="pre", hours_ago=2, prerelease=True),
            make_release(repo="other/repo", tag="dup", hours_ago=3),
            make_release(repo="other/repo", tag="dup", hours_ago=3),
        ]
        selected = select_recent(releases, hours=24, max_items=10, now=NOW)
        self.assertEqual([release.tag for release in selected], ["new", "dup"])
        with_pre = select_recent(
            releases, hours=24, max_items=10, include_prereleases=True, now=NOW, per_repo=0
        )
        self.assertEqual(len(with_pre), 3)
        limited = select_recent(releases, hours=24, max_items=1, now=NOW, per_repo=0)
        self.assertEqual(len(limited), 1)

    def test_per_repo_diversifies_digest(self):
        releases = [
            make_release(repo="crewAIInc/crewAI", tag="1.15.37", hours_ago=1),
            make_release(repo="crewAIInc/crewAI", tag="1.15.36", hours_ago=2),
            make_release(repo="ollama/ollama", tag="v0.40.15", hours_ago=3),
        ]
        selected = select_recent(releases, hours=24, now=NOW, per_repo=1)
        self.assertEqual([release.tag for release in selected], ["1.15.37", "v0.40.15"])
        unlimited = select_recent(releases, hours=24, now=NOW, per_repo=0)
        self.assertEqual(len(unlimited), 3)

    def test_clean_body(self):
        self.assertEqual(
            _clean_body("<b>Release</b> <a href='x'>link</a>"),
            "Release link",
        )
        self.assertIn("Поддержка", _clean_body(make_release().body))
        self.assertFalse(_clean_body("Full Changelog: a...b").startswith("Full Changelog"))
        self.assertLessEqual(len(_clean_body("слово " * 200)), 141)


class RenderTests(unittest.TestCase):
    def test_render_en(self):
        digest = render_digest([make_release()], channel_id="ai-news", hours=24, language="en")
        self.assertEqual(digest["items"], 1)
        self.assertIn("Open-source releases", digest["html"])
        self.assertIn('href="https://github.com/ollama/ollama/releases/tag/v1.0.0"', digest["html"])
        self.assertIn("<code>v1.0.0</code>", digest["html"])
        self.assertIn("#opensource", digest["plain"])
        self.assertIn("https://github.com/ollama/ollama/releases/tag/v1.0.0", digest["plain"])

    def test_render_marks_prerelease(self):
        digest = render_digest(
            [make_release(tag="b12202", prerelease=True)], channel_id="ai-news", hours=24, language="en"
        )
        self.assertIn("(pre-release)", digest["plain"])
        self.assertIn("(pre-release)", digest["html"])

    def test_render_es_and_empty(self):
        es = render_digest([make_release()], channel_id="tech-ai-es", hours=24, language="es")
        self.assertIn("Lanzamientos open source", es["html"])
        self.assertIn("#IA", es["html"])
        empty = render_digest([], channel_id="ai-news", hours=24, language="en")
        self.assertEqual(empty["items"], 0)
        self.assertIn("no new releases", empty["html"])


class CacheTests(unittest.TestCase):
    def test_ttl_and_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = ResponseCache(Path(tmp), ttl=1)
            cache.set("key", [{"a": 1}])
            self.assertEqual(cache.get("key"), [{"a": 1}])
            self.assertIsNone(cache.get("key", allow_stale=False) if False else None)
            self.assertEqual(cache.get("key", allow_stale=True), [{"a": 1}])


class GitHubClientTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cache_dir = Path(self._tmp.name) / "cache"

    def test_releases_cache_one_request(self):
        payload = [{"tag_name": "v1", "published_at": "2026-11-08T08:00:00Z", "html_url": "https://github.com/a/b/releases/v1"}]
        with mock.patch(
            "content_factory.oss_radar._http_json",
            return_value=(payload, {"x-ratelimit-remaining": "42"}, 200),
        ) as mocked:
            client = GitHubClient(cache_dir=self.cache_dir)
            first = client.releases("a/b")
            second = client.releases("a/b")
        self.assertEqual(first, payload)
        self.assertEqual(second, payload)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(client.remaining, 42)

    def test_rate_limit_uses_stale_cache(self):
        payload = [{"tag_name": "v1", "published_at": "2026-11-08T08:00:00Z"}]
        with mock.patch(
            "content_factory.oss_radar._http_json",
            return_value=(payload, {}, 200),
        ):
            GitHubClient(cache_dir=self.cache_dir).releases("a/b")
        with mock.patch(
            "content_factory.oss_radar._http_json",
            side_effect=RateLimitError("HTTP 403"),
        ):
            client = GitHubClient(cache_dir=self.cache_dir)
            releases = client.releases("a/b")
        self.assertEqual(releases, payload)

    def test_not_found_returns_empty(self):
        with mock.patch(
            "content_factory.oss_radar._http_json",
            side_effect=OSSRadarError("HTTP 404: Not Found"),
        ):
            self.assertEqual(GitHubClient().releases("none/none"), [])

    def test_items_mapping(self):
        releases = github_items_to_releases(
            "ollama/ollama",
            [
                {"tag_name": "v1", "published_at": "2026-11-08T08:00:00Z", "body": "notes", "prerelease": True},
                {"tag_name": "bad"},
            ],
        )
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "v1")
        self.assertTrue(releases[0].prerelease)
        self.assertEqual(releases[0].source, "github")


class LibrariesIOTests(unittest.TestCase):
    def test_requires_key(self):
        with mock.patch.dict("os.environ", {"LIBRARIES_IO_API_KEY": ""}):
            client = LibrariesIOClient()
            with self.assertRaises(OSSRadarError):
                client.search("llm")

    def test_search_cached_and_key_in_url(self):
        payload = [
            {
                "platform": "PyPI",
                "name": "langchain",
                "latest_release_number": "1.2.3",
                "latest_release_published_at": "2026-11-08 10:00:00 UTC",
                "package_manager_url": "https://pypi.org/project/langchain/",
                "description": "LLM framework",
                "licenses": "MIT",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "content_factory.oss_radar._http_json", return_value=(payload, {}, 200)
        ) as mocked:
            client = LibrariesIOClient(api_key="secret-key", cache_dir=Path(tmp))
            first = client.search("llm", platforms=["PyPI"])
            second = client.search("llm", platforms=["PyPI"])
        self.assertEqual(first, payload)
        self.assertEqual(second, payload)
        self.assertEqual(mocked.call_count, 1)
        self.assertIn("api_key=secret-key", mocked.call_args.args[0])

    def test_mapping_and_license_filter(self):
        items = [
            {
                "platform": "PyPI",
                "name": "a",
                "latest_release_number": "1.0",
                "latest_release_published_at": "2026-11-08 10:00:00 UTC",
                "package_manager_url": "https://pypi.org/project/a/",
                "licenses": "MIT",
            },
            {
                "platform": "npm",
                "name": "b",
                "latest_release_number": "2.0",
                "latest_release_published_at": "2026-11-08 10:00:00 UTC",
                "licenses": "GPL-3.0",
            },
            {"platform": "npm", "name": "c"},
        ]
        releases = libraries_io_releases(items, allowed_licenses=["MIT", "Apache-2.0"])
        self.assertEqual([release.repo for release in releases], ["PyPI:a"])
        self.assertEqual(releases[0].source, "libraries_io")
        all_releases = libraries_io_releases(items)
        self.assertEqual(len(all_releases), 2)


class ConfigTests(unittest.TestCase):
    def test_load_and_channel_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "radar.yaml"
            path.write_text(
                "channels:\n  ai-news:\n    language: en\n    repos: [ollama/ollama]\n",
                encoding="utf-8",
            )
            config = load_config(path)
            channel = channel_config(config, "ai-news")
        self.assertEqual(channel["language"], "en")
        self.assertEqual(channel["repos"], ["ollama/ollama"])
        self.assertEqual(channel["platforms"], ["PyPI", "npm"])
        self.assertEqual(channel["max_items"], 10)

    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text("channels: []\n", encoding="utf-8")
            with self.assertRaises(OSSRadarError):
                load_config(path)
        with self.assertRaises(OSSRadarError):
            channel_config({"channels": {}}, "missing")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
