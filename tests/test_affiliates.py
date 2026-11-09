"""Тесты affiliate-реестра: загрузка, UTM, блоки, ротация, учёт показов (без сети)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from content_factory.affiliates import (
    AffiliateError,
    AffiliateRotator,
    build_utm,
    load_registry,
    log_block,
    render_block,
    tracked_link,
    validate_registry,
)
from content_factory.storage import Storage

CONFIG = """
disclosure:
  en: "Advertising / affiliate link."
  es: "Publicidad / enlace de afiliado."
  age_18: "18+"
rules:
  affiliate_every: 3
programs:
  mylead:
    title: "MyLead"
    status: ready
    url: "https://mylead.global/r/abc"
    commission: "5%"
  collab:
    title: "Collaborator"
    status: ready
    url: "https://collaborator.pro/signup?code=xyz"
  bitget:
    title: "Bitget"
    status: awaiting_login
    url: ""
  onexbet:
    title: "1xBet"
    status: ready
    url: "https://1xbet.example/ref/1"
    age_restricted: true
channels:
  ai-news:
    language: en
    utm_source: tg_ai_en
    programs: [mylead, collab, bitget]
  sport-news:
    language: en
    utm_source: tg_sport_en
    age_restricted: true
    programs: [mylead, onexbet]
  tech-ai-es:
    language: es
    utm_source: tg_ai_es
    programs: [collab]
"""


class AffiliateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.config_path = self.root / "affiliates.yaml"
        self.config_path.write_text(CONFIG, encoding="utf-8")
        self.registry = load_registry(self.config_path)

    def write(self, text: str) -> Path:
        path = self.root / f"bad-{len(list(self.root.glob('bad-*')))}.yaml"
        path.write_text(text, encoding="utf-8")
        return path


class LoadTests(AffiliateTestCase):
    def test_loaded(self):
        self.assertEqual(len(self.registry.programs), 4)
        self.assertEqual(len(self.registry.channels), 3)
        self.assertEqual(self.registry.affiliate_every, 3)
        self.assertEqual([program.id for program in self.registry.ready_programs("ai-news")], ["mylead", "collab"])

    def test_ready_without_url_rejected(self):
        path = self.write(
            "programs:\n  p:\n    title: P\n    status: ready\n    url: ''\n"
            "channels:\n  c:\n    programs: [p]\n"
        )
        with self.assertRaises(AffiliateError):
            load_registry(path)

    def test_unknown_program_rejected(self):
        path = self.write(
            "programs:\n  p:\n    title: P\n    status: pending\n"
            "channels:\n  c:\n    programs: [nope]\n"
        )
        with self.assertRaises(AffiliateError):
            load_registry(path)

    def test_bad_url_rejected(self):
        path = self.write(
            "programs:\n  p:\n    title: P\n    status: ready\n    url: 'javascript:alert(1)'\n"
            "channels:\n  c:\n    programs: [p]\n"
        )
        with self.assertRaises(AffiliateError):
            load_registry(path)

    def test_unknown_channel(self):
        with self.assertRaises(AffiliateError):
            self.registry.channel("nope")


class ValidateTests(AffiliateTestCase):
    def test_warnings_for_pending_and_age(self):
        warnings = validate_registry(self.registry)
        self.assertTrue(any("bitget" in warning for warning in warnings))
        self.assertFalse(any("sport-news" in warning and "18+" in warning for warning in warnings))

    def test_missing_ready_warns(self):
        path = self.write(
            "programs:\n  p:\n    title: P\n    status: pending\n"
            "channels:\n  c:\n    utm_source: tg_c\n    programs: [p]\n"
        )
        registry = load_registry(path)
        warnings = validate_registry(registry)
        self.assertTrue(any("нет ни одной программы" in warning for warning in warnings))


class LinkTests(AffiliateTestCase):
    def test_build_utm_keeps_existing_query(self):
        link = build_utm("https://collaborator.pro/signup?code=xyz", "tg_ai_en")
        self.assertIn("code=xyz", link)
        self.assertIn("utm_source=tg_ai_en", link)
        self.assertIn("utm_medium=telegram", link)
        self.assertIn("utm_campaign=partners", link)

    def test_tracked_link_pending_raises(self):
        with self.assertRaises(AffiliateError):
            tracked_link(self.registry, "ai-news", "bitget")
        with self.assertRaises(AffiliateError):
            tracked_link(self.registry, "ai-news", "unknown")

    def test_invalid_url(self):
        with self.assertRaises(AffiliateError):
            build_utm("not-a-url", "tg_ai_en")


class BlockTests(AffiliateTestCase):
    def test_disclosure_en_and_es(self):
        self.assertEqual(self.registry.disclosure("ai-news"), "Advertising / affiliate link.")
        self.assertEqual(self.registry.disclosure("tech-ai-es"), "Publicidad / enlace de afiliado.")

    def test_age_restricted_disclosure(self):
        self.assertIn("18+", self.registry.disclosure("sport-news"))

    def test_render_block(self):
        block = render_block(self.registry, "ai-news")
        self.assertEqual(block["program"], "mylead")
        self.assertIn("mylead.global", block["url"])
        self.assertIn("Advertising / affiliate link.", block["html"])
        self.assertIn("<i>", block["html"])
        es = render_block(self.registry, "tech-ai-es")
        self.assertIn("Publicidad", es["html"])

    def test_render_block_specific_and_unknown(self):
        block = render_block(self.registry, "ai-news", program_id="collab")
        self.assertEqual(block["program"], "collab")
        with self.assertRaises(AffiliateError):
            render_block(self.registry, "ai-news", program_id="bitget")
        with self.assertRaises(AffiliateError):
            render_block(self.registry, "tech-ai-es", program_id="mylead")  # not assigned to channel

    def test_html_escape(self):
        path = self.write(
            "programs:\n  p:\n    title: '<script>alert(1)</script>'\n    status: ready\n"
            "    url: 'https://example.com/ref'\n"
            "channels:\n  c:\n    utm_source: tg_c\n    programs: [p]\n"
        )
        registry = load_registry(path)
        block = render_block(registry, "c")
        self.assertNotIn("<script>", block["html"])
        self.assertIn("&lt;script&gt;", block["html"])


class RotatorTests(AffiliateTestCase):
    def test_every_n_and_rotation(self):
        rotator = AffiliateRotator(self.registry, "ai-news")  # every=3, же ready: mylead, collab
        self.assertIsNone(rotator.for_post(1))
        self.assertEqual(rotator.for_post(3).id, "mylead")
        self.assertEqual(rotator.for_post(6).id, "collab")
        self.assertEqual(rotator.for_post(9).id, "mylead")

    def test_plan_length(self):
        plan = AffiliateRotator(self.registry, "ai-news").plan(10)
        self.assertEqual([item["post"] for item in plan], [3, 6, 9])

    def test_custom_every(self):
        self.assertIsNone(AffiliateRotator(self.registry, "ai-news", every=4).for_post(3))

    def test_channel_without_ready(self):
        path = self.write(
            "programs:\n  p:\n    title: P\n    status: pending\n"
            "channels:\n  c:\n    utm_source: tg_c\n    programs: [p]\n"
        )
        registry = load_registry(path)
        rotator = AffiliateRotator(registry, "c")
        self.assertIsNone(rotator.for_post(5))


class LogTests(AffiliateTestCase):
    def test_log_block_records_growth_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Storage(Path(tmp) / "test.sqlite3") as storage:
                log_block(storage, "ai-news", "mylead")
                summary = storage.growth_summary(days=1)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["by_event"]["affiliate_block"], 1)
        self.assertEqual(summary["by_channel"]["ai-news"], 1)
        self.assertEqual(summary["by_source"]["affiliate"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
