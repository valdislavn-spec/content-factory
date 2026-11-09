"""Тесты Canva Connect: PKCE, токены, экспорт (без сети)."""
import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import content_factory.integrations.canva as canva


class PkceTests(unittest.TestCase):
    def test_pair_is_valid_s256(self):
        verifier, challenge = canva.pkce_pair()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        self.assertEqual(challenge, expected)
        self.assertGreaterEqual(len(verifier), 43)

    def test_authorization_url(self):
        with mock.patch.dict(os.environ, {"CANVA_CLIENT_ID": "cid", "CANVA_CLIENT_SECRET": "sec",
                                          "CANVA_REDIRECT_URI": "http://127.0.0.1:8085/callback"}):
            url, verifier = canva.authorization_url(scopes="design:meta:read")
        self.assertIn("https://www.canva.com/api/oauth/authorize?", url)
        self.assertIn("client_id=cid", url)
        self.assertIn("code_challenge_method=s256", url)
        self.assertIn("response_type=code", url)
        self.assertTrue(verifier)

    def test_missing_credentials(self):
        with mock.patch.dict(os.environ, {"CANVA_CLIENT_ID": "", "CANVA_CLIENT_SECRET": ""}):
            with self.assertRaises(canva.CanvaError):
                canva.authorization_url()


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.token_path = Path(self.tmp.name) / "canva_token.json"
        self._orig = canva.TOKEN_PATH
        canva.TOKEN_PATH = self.token_path

    def tearDown(self):
        canva.TOKEN_PATH = self._orig
        self.tmp.cleanup()

    def test_exchange_code_saves_token(self):
        with mock.patch.dict(os.environ, {"CANVA_CLIENT_ID": "cid", "CANVA_CLIENT_SECRET": "sec"}), \
             mock.patch.object(canva, "_http", return_value={
                 "access_token": "at", "refresh_token": "rt", "expires_in": 3600}):
            canva.exchange_code("code", "verifier")
        stored = json.loads(self.token_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["access_token"], "at")
        self.assertGreater(stored["expires_at"], 0)

    def test_refresh_expired_token(self):
        self.token_path.write_text(json.dumps({
            "access_token": "old", "refresh_token": "rt", "expires_at": 0}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"CANVA_CLIENT_ID": "cid", "CANVA_CLIENT_SECRET": "sec"}), \
             mock.patch.object(canva, "_http", return_value={
                 "access_token": "new", "refresh_token": "rt2", "expires_in": 3600}):
            token = canva.ensure_token()
        self.assertEqual(token, "new")

    def test_missing_token_file(self):
        with self.assertRaises(canva.CanvaError):
            canva.ensure_token()


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.token_path = Path(self.tmp.name) / "token.json"
        self.token_path.write_text(json.dumps({"access_token": "at", "expires_at": 9e12}))
        self._orig = canva.TOKEN_PATH
        canva.TOKEN_PATH = self.token_path

    def tearDown(self):
        canva.TOKEN_PATH = self._orig
        self.tmp.cleanup()

    def test_export_polls_and_downloads(self):
        jobs = [
            {"id": "job1", "status": "in_progress"},
            {"id": "job1", "status": "success", "urls": ["https://cdn.example/img.png"]},
        ]
        calls = {"n": 0}

        def fake_api(method, path, payload=None):
            calls["n"] += 1
            if method == "POST":
                return {"job": {"id": "job1", "status": "in_progress"}}
            return {"job": jobs.pop(0) if jobs else {"id": "job1", "status": "success", "urls": []}}

        class FakeResponse:
            def read(self):
                return b"\x89PNG fake"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch.object(canva, "_api", side_effect=fake_api), \
             mock.patch.object(canva.urllib.request, "urlopen", return_value=FakeResponse()), \
             mock.patch.object(canva.time, "sleep"):
            result = canva.export_design("DA123", "png", out_dir=self.tmp.name)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["files"]), 1)
        self.assertTrue(Path(result["files"][0]).is_file())

    def test_profile_and_designs(self):
        def fake_api(method, path, payload=None):
            if path.startswith("/designs"):
                return {"items": [{"design": {"id": "D1", "title": "T"}}]}
            return {"display_name": "Vlad"}

        with mock.patch.object(canva, "_api", side_effect=fake_api):
            data = canva.list_designs(5)
            profile = canva.profile()
        self.assertEqual(data["items"][0]["design"]["title"], "T")
        self.assertEqual(profile["display_name"], "Vlad")


if __name__ == "__main__":
    unittest.main()
