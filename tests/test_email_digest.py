"""Тесты email-дайджеста: сбор, рендер, payload Brevo."""
import tempfile
import unittest
from pathlib import Path

from content_factory.config import Settings, load_network_channels
from content_factory.integrations.email_digest import (
    build_brevo_payload,
    collect_items,
    render,
)
from content_factory.models import GeneratedPost
from content_factory.storage import Storage


UNIQUE_TITLES = {
    "crypto-news": ["Bitcoin ETF inflows hit a new record", "SEC approves new crypto custody rules"],
    "ai-news": ["OpenAI releases a new reasoning model", "NVIDIA unveils faster AI chips"],
    "sport-news": ["NFL Week 10 injury report", "NBA trade deadline rumors"],
    "tech-ai-es": ["Nueva IA en español para empresas", "Startup española recauda ronda"],
    "crypto-es": ["Bitcoin supera un nuevo máximo", "Ethereum se prepara para una actualización"],
    "futbol-es": ["LaLiga: resultados de la jornada", "Mercado de fichajes en Argentina"],
}


class EmailDigestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.load()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "factory.sqlite3")
        self.channels = load_network_channels(self.settings)

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _save_posts(self, language: str, per_channel: int = 2):
        for channel in [c for c in self.channels if c.language == language]:
            for index in range(per_channel):
                post = GeneratedPost(
                    id=f"{channel.id}-{index}",
                    channel_id=channel.id,
                    cluster_id=f"cluster-{channel.id}-{index}",
                    format="story",
                    text=(
                        f"<b>{channel.title}: {UNIQUE_TITLES[channel.id][index]}</b>\n\n"
                        f"Details about {UNIQUE_TITLES[channel.id][index]} with facts, numbers and context for readers. "
                        "More in the linked source."
                    ),
                    hashtags=["#Test"],
                    sources=[{"title": "Source", "url": f"https://example.com/{channel.id}/{index}", "source": "Example"}],
                )
                self.storage.save_post(post, status="published")

    def test_collect_items_for_english(self):
        self._save_posts("en")
        items = collect_items(self.settings, self.storage, "en", days=7, allow_preview=False)
        self.assertEqual(len(items), 6)
        self.assertEqual({item.channel_id for item in items}, {"crypto-news", "ai-news", "sport-news"})
        self.assertTrue(all(item.url.startswith("https://t.me/") for item in items))

    def test_render_contains_channels_and_links(self):
        self._save_posts("es")
        items = collect_items(self.settings, self.storage, "es", days=7, allow_preview=False)
        digest = render(items, self.settings, "es")
        self.assertIn("Resumen semanal", digest.text)
        self.assertIn("t.me/", digest.html)
        self.assertIn("unsubscribe", digest.html)
        self.assertIn("historias de la semana", digest.subject)

    def test_brevo_payload(self):
        self._save_posts("en", per_channel=1)
        items = collect_items(self.settings, self.storage, "en", days=7, allow_preview=False)
        digest = render(items, self.settings, "en")
        payload = build_brevo_payload(
            digest,
            sender_email="digest@example.com",
            sender_name="Content Factory",
            list_id=42,
        )
        self.assertEqual(payload["recipients"]["listIds"], [42])
        self.assertEqual(payload["sender"]["email"], "digest@example.com")
        self.assertIn("subject", payload)
        self.assertIn("htmlContent", payload)

    def test_duplicate_titles_are_removed(self):
        channel = next(c for c in self.channels if c.language == "en")
        for index in range(3):
            post = GeneratedPost(
                id=f"dup-{index}",
                channel_id=channel.id,
                cluster_id="dup",
                format="story",
                text="<b>Same headline about OpenAI GPT-5 release</b>\n\nSame body text with enough characters to pass.",
                sources=[{"url": f"https://example.com/dup-{index}", "title": "x", "source": "x"}],
            )
            self.storage.save_post(post, status="published")
        items = collect_items(self.settings, self.storage, "en", days=7, allow_preview=False)
        titles = [item.title for item in items]
        self.assertEqual(len(titles), len(set(titles)))


if __name__ == "__main__":
    unittest.main()
