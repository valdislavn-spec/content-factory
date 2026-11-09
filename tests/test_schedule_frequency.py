"""Частота публикаций: 5 постов в сутки на канал, 30 по сети."""

from __future__ import annotations

import unittest

from content_factory.config import Settings, load_channels


class ScheduleFrequencyTest(unittest.TestCase):
    def test_five_posts_per_day_per_channel(self):
        settings = Settings.load(load_env=False)
        channels = []
        for path in ("config/channels.en.yaml", "config/channels.es.yaml"):
            channels.extend(load_channels(settings, path=path))
        self.assertEqual(len(channels), 6)
        for channel in channels:
            self.assertEqual(channel.posts_per_day, 5, channel.id)
            self.assertEqual(len(channel.schedule), 5, channel.id)
        self.assertEqual(sum(c.posts_per_day for c in channels), 30)

    def test_no_night_slots(self):
        settings = Settings.load(load_env=False)
        channels = []
        for path in ("config/channels.en.yaml", "config/channels.es.yaml"):
            channels.extend(load_channels(settings, path=path))
        for channel in channels:
            for slot in channel.schedule:
                hour = int(slot.split(":")[0])
                self.assertTrue(6 <= hour < 23, f"{channel.id}: ночной слот {slot}")


if __name__ == "__main__":
    unittest.main()
