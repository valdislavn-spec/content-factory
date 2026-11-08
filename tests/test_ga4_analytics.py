"""Тесты GA4-аналитики (без сети: сетевые вызовы замоканы)."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from content_factory.analytics import ga4

_ENV = ("GA4_SA_JSON", "GA4_SA_FILE", "GA4_PROPERTY_ID", "GA4_MEASUREMENT_ID")

# минимальный «сервисный аккаунт» без валидного ключа — только для проверки парсинга
_SA = {
    "type": "service_account",
    "client_email": "sa@example.iam.gserviceaccount.com",
    "private_key_id": "key-1",
    "private_key": "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n",
}


class Ga4TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = {key: os.environ.pop(key, None) for key in _ENV}
        self.addCleanup(self._restore)
        ga4._TOKEN_CACHE.update({"token": "", "expires_at": 0.0, "key": ""})

    def _restore(self) -> None:
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_not_configured(self):
        summary = ga4.landing_summary(days=7)
        self.assertFalse(summary["configured"])
        self.assertEqual(ga4.format_markdown_section(summary), "")
        self.assertEqual(ga4.format_telegram_line(summary), "")

    def test_service_account_from_json_env(self):
        os.environ["GA4_SA_JSON"] = json.dumps(_SA)
        os.environ["GA4_PROPERTY_ID"] = "123"
        self.assertTrue(ga4.configured())
        info = ga4.service_account_info()
        self.assertEqual(info["client_email"], _SA["client_email"])
        self.assertEqual(ga4.property_id(), "123")

    def test_service_account_from_file(self):
        path = Path(self._tmp.name) / "sa.json"
        path.write_text(json.dumps(_SA), encoding="utf-8")
        os.environ["GA4_SA_FILE"] = str(path)
        os.environ["GA4_PROPERTY_ID"] = "123"
        self.assertTrue(ga4.configured())

    def test_b64url_no_padding(self):
        encoded = ga4._b64url(b'{"a":1}')
        self.assertNotIn("=", encoded)
        self.assertEqual(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)), b'{"a":1}')

    def test_run_report_posts_expected_body(self):
        os.environ["GA4_SA_JSON"] = json.dumps(_SA)
        os.environ["GA4_PROPERTY_ID"] = "555"
        captured = {}

        def fake_post(endpoint, body, timeout=25.0):
            captured["endpoint"] = endpoint
            captured["body"] = body
            return {
                "dimensionHeaders": [{"name": "pagePath"}],
                "metricHeaders": [{"name": "screenPageViews"}],
                "rows": [
                    {
                        "dimensionValues": [{"value": "/"}],
                        "metricValues": [{"value": "7"}],
                    }
                ],
            }

        with mock.patch.object(ga4, "_data_post", side_effect=fake_post), mock.patch.object(
            ga4, "access_token", return_value="tok"
        ):
            rows = ga4.run_report(days=3, dimensions=["pagePath"], metrics=["screenPageViews"])
        self.assertEqual(captured["endpoint"], "runReport")
        self.assertEqual(captured["body"]["dateRanges"][0]["startDate"], "3daysAgo")
        self.assertEqual(rows[0]["pagePath"], "/")
        self.assertEqual(rows[0]["screenPageViews"], "7")

    def test_landing_summary_and_formatting(self):
        os.environ["GA4_SA_JSON"] = json.dumps(_SA)
        os.environ["GA4_PROPERTY_ID"] = "555"
        os.environ["GA4_MEASUREMENT_ID"] = "G-TEST123"

        def fake_run_report(days=7, dimensions=None, metrics=None, limit=10):
            if dimensions and "sessionSource" in dimensions:
                return [{"sessionSource": "google", "sessionMedium": "organic", "sessions": "3", "activeUsers": "2"}]
            if dimensions and "pagePath" in dimensions:
                return [{"pagePath": "/", "screenPageViews": "5", "activeUsers": "2"}]
            return [{"activeUsers": "2", "screenPageViews": "5", "sessions": "3"}]

        with mock.patch.object(ga4, "run_report", side_effect=fake_run_report), mock.patch.object(
            ga4, "realtime_active_users", return_value=1
        ):
            summary = ga4.landing_summary(days=7)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["active_users"], 2)
        md = ga4.format_markdown_section(summary)
        self.assertIn("GA4 — лендинг", md)
        self.assertIn("google / organic", md)
        self.assertIn("G-TEST123", md)
        self.assertIn("Сейчас на сайте", md)
        self.assertIn("GA4 лендинг", ga4.format_telegram_line(summary))

    def test_landing_summary_handles_api_error(self):
        os.environ["GA4_SA_JSON"] = json.dumps(_SA)
        os.environ["GA4_PROPERTY_ID"] = "555"
        with mock.patch.object(ga4, "run_report", side_effect=RuntimeError("boom")):
            summary = ga4.landing_summary()
        self.assertTrue(summary["configured"])
        self.assertFalse(summary["ok"])
        self.assertIn("boom", summary["error"])
        self.assertIn("GA4 недоступен", ga4.format_markdown_section(summary))


if __name__ == "__main__":
    unittest.main()
