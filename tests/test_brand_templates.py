"""Тесты брендовых шаблонов (чистая логика; рендер требует PIL)."""
import unittest
from unittest import mock

from content_factory.brand import templates


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = templates.load_config()

    def test_networks_registry(self):
        self.assertGreaterEqual(len(self.config["networks"]), 12)
        keys = {network["key"] for network in self.config["networks"]}
        for expected in ("telegram_post", "instagram_story", "x_post", "pinterest_pin",
                         "mastodon_post", "bluesky_post", "youtube_thumb", "og_image"):
            self.assertIn(expected, keys)

    def test_sizes_and_layouts(self):
        for network in self.config["networks"]:
            width, height = network["size"]
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
            self.assertIn(network["layout"], templates.VALID_LAYOUTS)

    def test_topics_have_required_fields(self):
        for key, topic in self.config["topics"].items():
            for field in ("label", "accent", "headline", "subtitle", "cta"):
                self.assertTrue(topic.get(field), f"{key}: нет {field}")

    def test_ready_partners_only(self):
        partners = templates.ready_partners(self.config)
        self.assertTrue(partners)
        keys = {partner["key"] for partner in partners}
        self.assertIn("mylead", keys)
        self.assertIn("collaborator", keys)
        for partner in partners:
            self.assertTrue(partner["url"].startswith("http"))
        # pending/awaiting не должны попадать
        self.assertNotIn("bitget", keys)
        self.assertNotIn("writesonic", keys)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.config = templates.load_config()

    def test_plan_defaults(self):
        spec = templates.plan(self.config, "x_post", "ai", "mylead")
        self.assertEqual(spec["network"], "x_post")
        self.assertEqual(spec["size"], (1200, 675))
        self.assertEqual(spec["layout"], "wide")
        self.assertIn("AI", spec["headline"])
        self.assertEqual(spec["partner"]["key"], "mylead")
        self.assertIn("Advertising", spec["disclosure"])

    def test_plan_custom_text(self):
        spec = templates.plan(self.config, "pinterest_pin", "crypto", "collaborator",
                              headline="Custom headline", subtitle="Custom subtitle",
                              cta="Go now")
        self.assertEqual(spec["headline"], "Custom headline")
        self.assertEqual(spec["subtitle"], "Custom subtitle")
        self.assertEqual(spec["cta"], "Go now")

    def test_unknown_network_topic_partner(self):
        with self.assertRaises(ValueError):
            templates.plan(self.config, "nope")
        with self.assertRaises(ValueError):
            templates.plan(self.config, "x_post", "nope")
        with self.assertRaises(ValueError):
            templates.plan(self.config, "x_post", "ai", "bitget")  # не ready

    def test_plan_without_partner_when_no_ready(self):
        config = dict(self.config)
        with mock.patch.object(templates, "ready_partners", return_value=[]):
            spec = templates.plan(config, "x_post", "ai", "")
        self.assertIsNone(spec["partner"])


if __name__ == "__main__":
    unittest.main()
