"""Тесты health-модуля Telegram: @SpamBot, сессии, скор, flood-wait (без сети)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from content_factory.tg_health import (
    TgHealthError,
    extract_retry_after,
    looks_like_session_string,
    mask_ip,
    normalize_ref,
    parse_spambot_reply,
    score_account,
    sessions_report,
    summarize_auth,
)

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
EPOCH = int(NOW.timestamp())


class SpamBotTests(unittest.TestCase):
    def test_clean_en(self):
        result = parse_spambot_reply(
            "Good news, no limits are currently applied to your account. You're free as a bird!"
        )
        self.assertEqual(result["status"], "clean")

    def test_clean_ru(self):
        result = parse_spambot_reply("Хорошие новости: ограничений на ваш аккаунт нет.")
        self.assertEqual(result["status"], "clean")

    def test_limited_en(self):
        result = parse_spambot_reply(
            "I'm very sorry, but your account seems to have been limited for spam. "
            "You can't send messages to people who don't know you."
        )
        self.assertEqual(result["status"], "limited")
        self.assertIn("limited", result["details"].lower())

    def test_limited_ru(self):
        result = parse_spambot_reply("Ваш аккаунт ограничен за спам.")
        self.assertEqual(result["status"], "limited")

    def test_unknown(self):
        self.assertEqual(parse_spambot_reply("")["status"], "unknown")
        self.assertEqual(parse_spambot_reply("hello")["status"], "unknown")


class SessionsTests(unittest.TestCase):
    def test_mask_ip(self):
        self.assertEqual(mask_ip("1.2.3.4"), "1.2.*.*")
        self.assertEqual(mask_ip("2001:db8::1"), "2001:…")
        self.assertEqual(mask_ip("not-an-ip"), "—")
        self.assertEqual(mask_ip(""), "—")

    def test_summarize_current(self):
        item = summarize_auth(
            {
                "current": True,
                "date_active": EPOCH - 3600,
                "app_name": "Telegram Desktop",
                "device_model": "MacBook",
                "platform": "macOS",
                "country": "RU",
                "ip": "10.0.0.1",
            },
            now=NOW,
        )
        self.assertTrue(item["current"])
        self.assertEqual(item["app"], "Telegram Desktop")
        self.assertFalse(item["suspicious"])
        self.assertEqual(item["ip"], "10.0.*.*")

    def test_summarize_suspicious_without_device(self):
        item = summarize_auth({"current": False, "date_active": None}, now=NOW)
        self.assertFalse(item["current"])
        self.assertTrue(item["suspicious"])
        self.assertIsNone(item["days_ago"])

    def test_sessions_report(self):
        report = sessions_report(
            [
                {"current": True, "app_name": "Desktop", "date_active": EPOCH},
                {"current": False, "app_name": "Mobile", "date_active": EPOCH - 86400 * 10},
                {"current": False, "date_active": None},
            ],
            now=NOW,
        )
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["current"], 1)
        self.assertEqual(report["other"], 2)
        self.assertEqual(report["suspicious"], 1)


class ScoreTests(unittest.TestCase):
    def test_clean_account(self):
        score = score_account(
            spambot_status="clean",
            sessions={"total": 2, "current": 1, "other": 1, "suspicious": 0},
            twofa=True,
        )
        self.assertGreaterEqual(score["score"], 85)
        self.assertEqual(score["grade"], "A")

    def test_limited_penalty(self):
        score = score_account(spambot_status="limited", sessions=None, twofa=True)
        self.assertLessEqual(score["score"], 50)

    def test_no_2fa_and_suspicious(self):
        score = score_account(
            spambot_status="clean",
            sessions={"total": 5, "current": 1, "other": 4, "suspicious": 1},
            twofa=False,
        )
        self.assertLess(score["score"], 85)
        self.assertTrue(any("2FA" in reason for reason in score["reasons"]))
        self.assertTrue(any("сессии" in reason for reason in score["reasons"]))

    def test_unknown_spambot_penalty(self):
        score = score_account(spambot_status="unknown", twofa=True)
        self.assertLess(score["score"], 100)


class FloodWaitTests(unittest.TestCase):
    def test_retry_after_nested(self):
        self.assertEqual(
            extract_retry_after({"error_code": 429, "parameters": {"retry_after": 30}}), 30.0
        )

    def test_retry_after_top_level(self):
        self.assertEqual(extract_retry_after({"retry_after": 5}), 5.0)
        self.assertEqual(extract_retry_after({"seconds": "7"}), 7.0)

    def test_retry_after_absent(self):
        self.assertIsNone(extract_retry_after({}))
        self.assertIsNone(extract_retry_after(None))
        self.assertIsNone(extract_retry_after({"parameters": {"retry_after": "bad"}}))


class HelpersTests(unittest.TestCase):
    def test_session_string(self):
        self.assertTrue(looks_like_session_string("1" + "A" * 120))
        self.assertFalse(looks_like_session_string("content_factory"))
        self.assertFalse(looks_like_session_string("data/content_factory.session"))
        self.assertFalse(looks_like_session_string("short"))

    def test_normalize_ref(self):
        self.assertEqual(normalize_ref("@SpamBot"), "SpamBot")
        self.assertEqual(normalize_ref("https://t.me/SpamBot"), "SpamBot")
        self.assertEqual(normalize_ref("SpamBot"), "SpamBot")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
