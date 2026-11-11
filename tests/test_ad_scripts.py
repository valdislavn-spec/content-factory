"""CLI-скрипты продажи рекламы: dry-run без сети и без публикаций."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from content_factory.config import DEFAULT_SETTINGS, Settings
from scripts import ad_bot, ad_orders, publish_ads


class AdScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        raw = copy.deepcopy(DEFAULT_SETTINGS)
        raw["app"].update(
            {
                "dry_run": True,
                "data_dir": str(self.root / "data"),
                "db_path": str(self.root / "data" / "factory.sqlite3"),
                "outbox_dir": str(self.root / "data" / "outbox"),
                "reports_dir": str(self.root / "data" / "reports"),
                "logs_dir": str(self.root / "data" / "logs"),
            }
        )
        self.settings = Settings(
            root=self.root,
            raw=raw,
            settings_path=self.root / "config" / "settings.yaml",
            channels_path=self.root / "config" / "channels.yaml",
        )

    def test_orders_stats_and_empty_list(self) -> None:
        with mock.patch("scripts.ad_orders.Settings.load", return_value=self.settings):
            self.assertEqual(ad_orders.main(["stats"]), 0)
            self.assertEqual(ad_orders.main(["list"]), 0)

    def test_publish_dry_run_without_orders(self) -> None:
        with mock.patch("scripts.publish_ads.Settings.load", return_value=self.settings), mock.patch(
            "scripts.publish_ads.load_network_channels", return_value=[]
        ):
            self.assertEqual(publish_ads.main(["--dry-run"]), 0)

    def test_ad_bot_dry_run(self) -> None:
        with mock.patch("scripts.ad_bot.Settings.load", return_value=self.settings), mock.patch.dict(
            os.environ, {"TELEGRAM_BOT_TOKEN": ""}, clear=False
        ):
            self.assertEqual(ad_bot.main(["--dry-run", "--config", str(Path(__file__).resolve().parents[1] / "config" / "monetization.yaml")]), 0)


if __name__ == "__main__":
    unittest.main()
