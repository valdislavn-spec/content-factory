"""Тесты email-дайджеста (без сети/SMTP)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.email_digest as digest


POSTS = [
    {"channel_id": "ai-news", "format": "story", "created_at": "2026-11-09T08:00:00+00:00",
     "status": "published", "text": "<b>OpenAI ships GPT-5</b> — bigger context window."},
    {"channel_id": "crypto-news", "format": "analysis", "created_at": "2026-11-08T12:00:00+00:00",
     "status": "published", "text": "Bitcoin ETFs saw record inflows this week."},
]


class DigestBuildTests(unittest.TestCase):
    def test_subject_and_body(self):
        result = digest.build_digest(POSTS, days=7)
        self.assertIn("Content Factory Digest", result["subject"])
        self.assertIn("Content Factory", result["html"])
        self.assertIn("OpenAI ships GPT-5", result["text"])
        self.assertIn("Bitcoin ETFs", result["html"])
        self.assertIn("ai-news", result["html"])

    def test_message_headers(self):
        data = digest.build_digest(POSTS, days=3)
        message = digest.make_message(data, "from@example.com", ["a@example.com", "b@example.com"])
        self.assertEqual(message["From"], "from@example.com")
        self.assertEqual(message["To"], "a@example.com, b@example.com")
        self.assertIn("Content Factory Digest", message["Subject"])
        self.assertTrue(message.is_multipart())

    def test_save_eml_dry_run(self):
        data = digest.build_digest(POSTS)
        message = digest.make_message(data, "from@example.com", ["a@example.com"])
        with tempfile.TemporaryDirectory() as tmp:
            original = digest.OUT_DIR
            digest.OUT_DIR = Path(tmp)
            try:
                path = digest.save_eml(message)
                self.assertTrue(path.is_file())
                self.assertIn(b"Content Factory Digest", path.read_bytes())
            finally:
                digest.OUT_DIR = original


class SendTests(unittest.TestCase):
    def test_missing_smtp_returns_error(self):
        with mock.patch.dict(os.environ, {"EMAIL_SMTP_HOST": "", "EMAIL_SMTP_USER": "",
                                          "EMAIL_SMTP_PASSWORD": ""}):
            ok = True
            try:
                digest.send_message(digest.make_message(digest.build_digest(POSTS),
                                                        "f@e.com", ["t@e.com"]),
                                    "", 587, "", "")
            except Exception:
                ok = False
            self.assertFalse(ok)

    def test_send_message_uses_smtp(self):
        data = digest.build_digest(POSTS)
        message = digest.make_message(data, "from@example.com", ["to@example.com"])
        server = mock.MagicMock()
        with mock.patch.object(digest.smtplib, "SMTP", return_value=server) as smtp:
            server.__enter__.return_value = server
            digest.send_message(message, "smtp.example.com", 587, "user", "pass")
        smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("user", "pass")
        server.send_message.assert_called_once()


class EmptyPostsTests(unittest.TestCase):
    def test_build_digest_without_posts(self):
        result = digest.build_digest([], days=7)
        self.assertIn("Дайджест за 7 дн.", result["html"])
        self.assertIn("Отписаться", result["text"])


if __name__ == "__main__":
    unittest.main()
