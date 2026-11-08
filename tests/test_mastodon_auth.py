"""Тесты OAuth-помощника Mastodon (без сети)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.mastodon_auth as auth


class AuthTests(unittest.TestCase):
    def test_register_saves_app_and_builds_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_file = Path(tmp) / "app.json"
            original = auth.APP_FILE
            auth.APP_FILE = app_file
            try:
                with mock.patch.object(auth, "_post", return_value={
                    "client_id": "cid", "client_secret": "cs",
                    "redirect_uri": auth.REDIRECT_URI,
                }):
                    app = auth.register_app("https://mastodon.social", "content-factory",
                                            auth.DEFAULT_SCOPES, "https://t.me/AINEWS0007")
                saved = json.loads(app_file.read_text(encoding="utf-8"))
            finally:
                auth.APP_FILE = original
        self.assertEqual(saved["client_id"], "cid")
        url = auth.authorization_url(app)
        self.assertIn("https://mastodon.social/oauth/authorize?", url)
        self.assertIn("client_id=cid", url)
        self.assertIn("response_type=code", url)
        self.assertIn("scope=read%3Aaccounts+write%3Astatuses", url)

    def test_missing_fields_rejected(self):
        with mock.patch.object(auth, "_post", return_value={"client_id": "cid"}):
            with self.assertRaises(auth.MastodonAuthError):
                auth.register_app()

    def test_exchange_code(self):
        captured = {}

        def fake_post(url, payload, timeout=30):
            captured.update(url=url, payload=payload)
            return {"access_token": "tok-1"}

        app = {"instance": "https://mastodon.social", "client_id": "cid",
               "client_secret": "cs", "redirect_uri": auth.REDIRECT_URI,
               "scopes": auth.DEFAULT_SCOPES}
        with mock.patch.object(auth, "_post", side_effect=fake_post):
            data = auth.exchange_code(app, "code-123")
        self.assertEqual(data["access_token"], "tok-1")
        self.assertEqual(captured["payload"]["grant_type"], "authorization_code")
        self.assertEqual(captured["payload"]["code"], "code-123")
        self.assertEqual(captured["url"], "https://mastodon.social/oauth/token")

    def test_write_env_replaces_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("FOO=1\nMASTODON_BASE_URL=old\nBAR=2\n", encoding="utf-8")
            auth.write_env("https://mastodon.social", "tok", env)
            text = env.read_text(encoding="utf-8")
        self.assertIn("MASTODON_BASE_URL=https://mastodon.social", text)
        self.assertIn("MASTODON_TOKEN=tok", text)
        self.assertIn("FOO=1", text)
        self.assertNotIn("old", text)

    def test_verify_credentials(self):
        captured = {}

        def fake_get(url, token, timeout=30):
            captured.update(url=url, token=token)
            return {"username": "cf", "acct": "cf", "followers_count": 3, "statuses_count": 7}

        with mock.patch.object(auth, "_get", side_effect=fake_get):
            account = auth.verify_credentials("https://mastodon.social/", "tok")
        self.assertEqual(account["username"], "cf")
        self.assertEqual(captured["url"], "https://mastodon.social/api/v1/accounts/verify_credentials")


if __name__ == "__main__":
    unittest.main()
