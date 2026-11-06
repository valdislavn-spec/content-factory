"""Тесты картинок из RSS: enclosure, media:content, img в описании."""

from __future__ import annotations

import unittest
from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources.rss import RSSAdapter

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Test feed</title>
    <item>
      <title>First</title>
      <link>https://example.com/1</link>
      <description>Text one</description>
      <enclosure url="https://cdn.example.com/a.jpg" type="image/jpeg"/>
    </item>
    <item>
      <title>Second</title>
      <link>https://example.com/2</link>
      <description>Text two</description>
      <media:content url="https://cdn.example.com/b.png" type="image/png"/>
    </item>
    <item>
      <title>Third</title>
      <link>https://example.com/3</link>
      <description><![CDATA[<p>Text with <img src="/c.webp"> image</p>]]></description>
    </item>
    <item>
      <title>Fourth</title>
      <link>https://example.com/4</link>
      <description>No image here</description>
    </item>
  </channel>
</rss>
"""


class RSSImageTests(unittest.TestCase):
    def _fetch(self):
        settings = Settings.load(load_env=False)
        source = SourceConfig(
            id="feed", type="rss", url="https://example.com/feed.xml", name="Feed"
        )
        with mock.patch(
            "content_factory.sources.rss.http_get_text", return_value=FEED
        ):
            return {article.url: article for article in RSSAdapter().fetch(source, settings)}

    def test_enclosure_image(self):
        articles = self._fetch()
        self.assertEqual(
            articles["https://example.com/1"].meta["image"],
            "https://cdn.example.com/a.jpg",
        )

    def test_media_content_image(self):
        articles = self._fetch()
        self.assertEqual(
            articles["https://example.com/2"].meta["image"],
            "https://cdn.example.com/b.png",
        )

    def test_img_inside_description_resolved_against_feed(self):
        articles = self._fetch()
        self.assertEqual(
            articles["https://example.com/3"].meta["image"],
            "https://example.com/c.webp",
        )

    def test_no_image_no_meta_key(self):
        articles = self._fetch()
        self.assertNotIn("image", articles["https://example.com/4"].meta)


if __name__ == "__main__":
    unittest.main()
