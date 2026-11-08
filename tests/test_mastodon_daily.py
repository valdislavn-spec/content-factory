"""Тесты ежедневного Mastodon-треда (без сети и LLM)."""
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

import scripts.mastodon_daily as daily


class FakeChannel:
    id = "ai-news"
    title = "AI News"
    telegram_chat_id = "@AINEWS0007"
    description = ""
    sources = []


def article(title, summary, days_ago=0):
    return SimpleNamespace(title=title, summary=summary, text=summary, published_at=None)


class DailyTests(unittest.TestCase):
    def setUp(self):
        os.environ["MASTODON_NO_LINKS"] = "1"

    def tearDown(self):
        os.environ.pop("MASTODON_NO_LINKS", None)

    def test_topic_rotation(self):
        day = date(2026, 11, 8)
        a = daily.topic_for(day, 0)
        b = daily.topic_for(day, 0)
        self.assertEqual(a, b)
        slots = {daily.topic_for(day, i)["channel_id"] for i in range(3)}
        self.assertEqual(slots, {"ai-news", "crypto-news", "sport-news"})

    def test_clean_part_strips_urls_and_truncates(self):
        text = "Hello https://t.me/AINEWS0007 world. " + "x" * 600
        cleaned = daily.clean_part(text)
        self.assertNotIn("https://", cleaned)
        self.assertLessEqual(len(cleaned), daily.MAX_PART)

    def test_clean_part_keeps_links_when_disabled(self):
        os.environ["MASTODON_NO_LINKS"] = "0"
        cleaned = daily.clean_part("Read https://t.me/AINEWS0007 now")
        self.assertIn("https://t.me/AINEWS0007", cleaned)

    def test_fallback_thread_is_long_form_with_channel_accent(self):
        parts = daily.build_fallback(
            FakeChannel(), daily.TOPICS[0],
            [article("OpenAI raises $11B", "OpenAI raised more money at a higher valuation."),
             article("Anthropic nears IPO", "Anthropic is preparing to go public."),
             article("Small models win", "Teams pick smaller models for cost and speed.")],
        )
        self.assertGreaterEqual(len(parts), 3)
        for part in parts:
            self.assertLessEqual(len(part), 500)
        last = parts[-1]
        self.assertIn("@AINEWS0007", last)
        self.assertIn("#AI", last)

    def test_prepare_thread_falls_back_when_llm_unavailable(self):
        llm = SimpleNamespace(available=False)
        with mock.patch.object(daily, "get_llm", return_value=llm):
            parts = daily.prepare_thread(FakeChannel(), daily.TOPICS[0], [], mock.Mock())
        self.assertGreaterEqual(len(parts), 2)

    def test_dry_run_does_not_post(self):
        with mock.patch.object(daily, "post_status") as posted:
            results = daily.publish_thread(["one", "two"], apply=False)
        posted.assert_not_called()
        self.assertTrue(all(item.get("dry_run") for item in results))

    def test_apply_publishes_thread_with_replies(self):
        calls = []

        def fake_post(text, reply_to=""):
            calls.append({"text": text, "reply_to": reply_to})
            return {"id": f"id-{len(calls)}", "url": f"https://mastodon.social/@cf/{len(calls)}"}

        with mock.patch.object(daily, "post_status", side_effect=fake_post):
            results = daily.publish_thread(["one", "two", "three"], apply=True)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["reply_to"], "")
        self.assertEqual(calls[1]["reply_to"], "id-1")
        self.assertEqual(calls[2]["reply_to"], "id-2")
        self.assertEqual(len(results), 3)

    def test_split_llm_text_by_separators(self):
        raw = "First part text.\n---\nSecond part text.\n---\nThird part text."
        parts = daily.split_llm_text(raw)
        self.assertEqual(len(parts), 3)

    def test_split_llm_text_paragraphs_packed(self):
        raw = "Para one sentence.\n\nPara two sentence.\n\nPara three sentence."
        parts = daily.split_llm_text(raw)
        self.assertGreaterEqual(len(parts), 2)
        for part in parts:
            self.assertLessEqual(len(part), daily.MAX_PART + 1)

    def test_split_llm_text_single_blob_packs_sentences(self):
        raw = " ".join(["This is a sentence about the topic."] * 40)
        parts = daily.split_llm_text(raw)
        self.assertGreaterEqual(len(parts), 3)
        for part in parts:
            self.assertLessEqual(len(part), daily.MAX_PART + 1)

    def test_state_skip_logic(self):
        with mock.patch.object(daily, "_state_get", return_value={"value": "2026-11-08:0"}):
            self.assertTrue(daily._already_done(date(2026, 11, 8), 0))
            self.assertFalse(daily._already_done(date(2026, 11, 9), 0))


if __name__ == "__main__":
    unittest.main()
