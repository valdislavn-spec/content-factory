"""Тесты оформления профиля Mastodon (без сети)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.mastodon_profile as prof


class ProfileTests(unittest.TestCase):
    def test_dry_run_contains_bio_and_fields(self):
        result = prof.apply_profile("https://mastodon.social", "token", dry_run=True)
        self.assertTrue(result["dry_run"])
        fields = result["fields"]
        self.assertEqual(fields["display_name"], "Content Factory")
        self.assertIn("t.me/AINEWS0007", fields["note"])
        self.assertEqual(fields["bot"], "true")
        self.assertEqual(fields["fields_attributes[0][name]"], "AI News")

    def test_apply_calls_patch_with_files(self):
        calls = []

        def fake_patch(base, token, fields, files=None):
            calls.append({"fields": dict(fields), "files": dict(files or {})})
            return {"url": "https://mastodon.social/@cf", "display_name": "Content Factory",
                    "note": "bio", "bot": True, "fields": []}

        with tempfile.TemporaryDirectory() as tmp:
            avatar = Path(tmp) / "avatar.png"; avatar.write_bytes(b"\x89PNG" + b"0" * 100)
            header = Path(tmp) / "header.png"; header.write_bytes(b"\x89PNG" + b"0" * 100)
            with mock.patch.object(prof, "_patch", side_effect=fake_patch):
                result = prof.apply_profile("https://mastodon.social", "tok", avatar, header)
        self.assertEqual(result["url"], "https://mastodon.social/@cf")
        self.assertEqual(len(calls), 3)  # fields + avatar + header
        self.assertEqual(calls[0]["fields"]["bot"], "true")
        self.assertIn("avatar", calls[1]["files"])
        self.assertIn("header", calls[2]["files"])

    def test_load_credentials_from_profile_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_file = Path(tmp) / "app.json"
            app_file.write_text('{"instance": "https://mastodon.social", "access_token": "tok"}', encoding="utf-8")
            original = prof.PROFILE_APP
            prof.PROFILE_APP = app_file
            try:
                base, token = prof.load_credentials()
            finally:
                prof.PROFILE_APP = original
        self.assertEqual(base, "https://mastodon.social")
        self.assertEqual(token, "tok")

    def test_multipart_contains_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.png"; path.write_bytes(b"PNG")
            body, content_type = prof._multipart({"bot": "true"}, {"avatar": path})
        self.assertIn(b'name="bot"', body)
        self.assertIn(b'filename="a.png"', body)
        self.assertIn("multipart/form-data; boundary=", content_type)


if __name__ == "__main__":
    unittest.main()
