"""Тесты интеграции Postman API и валидность ассетов коллекции (без сети)."""

from __future__ import annotations

import io
import json
import os
import re
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from content_factory.integrations import postman

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "postman"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args) -> bool:  # noqa: D401 - контекстный менеджер
        return False


def _with_key() -> mock._patch:
    return mock.patch.dict(os.environ, {"POSTMAN_API_KEY": "test-key"})


class PostmanClientTests(unittest.TestCase):
    def test_status_aggregates_account(self):
        def fake_urlopen(request, timeout=None):
            url = request.full_url
            if url.endswith("/me"):
                return _FakeResponse({"user": {"username": "valdislav-n", "email": "a@b.c", "fullName": "V. N."}})
            if url.endswith("/workspaces"):
                return _FakeResponse({"workspaces": [{"id": "ws-1", "name": "V. N.'s Workspace", "type": "team"}]})
            if "/collections" in url:
                return _FakeResponse({"collections": [{"name": "My Collection", "uid": "c-1"}]})
            if "/environments" in url:
                return _FakeResponse({"environments": [{"name": "content-factory (secrets)", "uid": "e-1"}]})
            return _FakeResponse({})

        with _with_key(), mock.patch(
            "content_factory.integrations.postman.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            data = postman.status()
        self.assertEqual(data["username"], "valdislav-n")
        self.assertEqual(data["workspaces"], 1)
        self.assertEqual(data["workspace_id"], "ws-1")
        self.assertEqual(data["collections"], 1)
        self.assertEqual(data["environments"], 1)
        self.assertEqual(data["collection_names"], ["My Collection"])

    def test_missing_key_raises_friendly_error(self):
        with mock.patch.dict(os.environ, {"POSTMAN_API_KEY": ""}, clear=False):
            with self.assertRaises(postman.PostmanError) as ctx:
                postman.me()
        self.assertIn("POSTMAN_API_KEY", str(ctx.exception))

    def test_http_error_wrapped(self):
        error = urllib.error.HTTPError(
            "https://api.getpostman.com/me", 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}')
        )
        with _with_key(), mock.patch(
            "content_factory.integrations.postman.urllib.request.urlopen", side_effect=error
        ):
            with self.assertRaises(postman.PostmanError) as ctx:
                postman.me()
        self.assertIn("HTTP 401", str(ctx.exception))

    def test_install_assets_creates_collection_and_environment(self):
        calls = {}

        def fake_create_collection(collection, workspace_id=None, api_key=None):
            calls["collection"] = (collection.get("info", {}).get("name"), workspace_id)
            return {"uid": "new-collection", "name": collection["info"]["name"]}

        def fake_create_environment(environment, workspace_id=None, api_key=None):
            calls["environment"] = (environment.get("name"), workspace_id)
            return {"uid": "new-env", "name": environment["name"]}

        with _with_key(), mock.patch.object(postman, "create_collection", fake_create_collection), mock.patch.object(
            postman, "create_environment", fake_create_environment
        ):
            result = postman.install_assets(ROOT, workspace_id="ws-1")
        self.assertEqual(result["collection_uid"], "new-collection")
        self.assertEqual(result["environment_uid"], "new-env")
        self.assertEqual(calls["collection"][1], "ws-1")
        self.assertIn("content-factory", calls["collection"][0])


class PostmanAssetsTests(unittest.TestCase):
    def _collection(self) -> dict:
        return json.loads((ASSETS / postman.COLLECTION_FILE).read_text(encoding="utf-8"))

    def _environment(self) -> dict:
        return json.loads((ASSETS / postman.ENVIRONMENT_FILE).read_text(encoding="utf-8"))

    def test_collection_schema_and_folders(self):
        collection = self._collection()
        self.assertTrue(collection["info"]["schema"].endswith("v2.1.0/collection.json"))
        names = [folder["name"] for folder in collection["item"]]
        self.assertIn("Telegram Bot API", names)
        self.assertIn("Postman API", names)
        telegram_requests = next(f for f in collection["item"] if f["name"] == "Telegram Bot API")["item"]
        self.assertTrue(any("getChatMemberCount" in r["name"] for r in telegram_requests))
        # у ключевых запросов есть тесты-ассерты
        for request in telegram_requests:
            if "getMe" in request["name"]:
                self.assertTrue(request.get("event"))

    def test_all_variables_are_defined(self):
        collection = self._collection()
        environment = self._environment()
        available = {item["key"] for item in environment["values"]} | {
            item["key"] for item in collection.get("variable", [])
        }
        text = json.dumps(collection, ensure_ascii=False)
        used = set(re.findall(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", text))
        self.assertEqual(used - available, set(), f"необъявленные переменные: {used - available}")

    def test_no_secrets_inside_assets(self):
        for path in (ASSETS / postman.COLLECTION_FILE, ASSETS / postman.ENVIRONMENT_FILE):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("PMAK-", text)
            self.assertIsNone(re.search(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b", text), f"похоже на токен бота в {path.name}")
            self.assertNotIn("Bearer eyJ", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
