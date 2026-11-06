"""Тесты планировщика: слоты по МСК и другим поясам, состояние, демон."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from content_factory.config import DEFAULT_SETTINGS, Settings
from content_factory.models import MSK, ChannelConfig, utcnow
from content_factory.scheduler import (
    FIRST_RUN_WINDOW,
    ScheduleItem,
    Scheduler,
    daemon_loop,
)
from content_factory.utils import format_iso, write_json

_ENV_KEYS = ("CONTENT_FACTORY_DRY_RUN",)


def msk(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=MSK)


class SchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._saved_env = {key: os.environ.pop(key, None) for key in _ENV_KEYS}
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_settings(self, **app_overrides) -> Settings:
        raw = copy.deepcopy(DEFAULT_SETTINGS)
        raw["app"].update(
            {
                "dry_run": True,
                "data_dir": str(self.root / "data"),
                "db_path": str(self.root / "data" / "factory.sqlite3"),
                "outbox_dir": str(self.root / "data" / "outbox"),
                "reports_dir": str(self.root / "data" / "reports"),
                "logs_dir": str(self.root / "data" / "logs"),
                "daemon_interval_sec": 60,
            }
        )
        raw["app"].update(app_overrides)
        return Settings(
            root=self.root,
            raw=raw,
            settings_path=self.root / "config" / "settings.yaml",
            channels_path=self.root / "config" / "channels.yaml",
        )

    def make_channel(self, **overrides) -> ChannelConfig:
        values = {
            "id": "tech-ai",
            "title": "Технологии и ИИ",
            "topics": ["технологии"],
            "schedule": ["09:00", "18:00"],
            "timezone_offset": 3,
        }
        values.update(overrides)
        return ChannelConfig(**values)


class SchedulerSlotsTests(SchedulerTestCase):
    def test_first_run_catch_up_returns_single_latest_slot(self) -> None:
        """Первый запуск: не спамим — на канал только самый поздний слот."""
        settings = self.make_settings()
        channel = self.make_channel(schedule=["09:00", "13:00", "19:00"])
        scheduler = Scheduler(settings)
        now = msk(2026, 10, 18, 22, 5)

        items = scheduler.due([channel], now=now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].slot, "19:00")
        self.assertEqual(items[0].scheduled_at.astimezone(MSK).hour, 19)
        self.assertEqual(items[0].scheduled_at.astimezone(MSK).day, 18)
        self.assertEqual(
            items[0].scheduled_at,
            datetime(2026, 10, 18, 19, 0, tzinfo=MSK).astimezone(timezone.utc),
        )
        self.assertTrue(scheduler.state_path.is_file())
        state = json.loads(scheduler.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["last_check"], format_iso(now))
        self.assertGreaterEqual(scheduler.state_path.stat().st_size, 10)

    def test_first_run_catch_up_morning_returns_previous_slot(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=["09:00", "13:00", "19:00"])
        scheduler = Scheduler(settings)
        items = scheduler.due([channel], now=msk(2026, 10, 18, 9, 30))
        self.assertEqual([item.slot for item in items], ["09:00"])

    def test_first_run_many_channels_one_slot_each(self) -> None:
        settings = self.make_settings()
        channels = [
            self.make_channel(
                id="channel-{}".format(index),
                title="Канал {}".format(index),
                schedule=["09:00", "13:00", "19:00"],
            )
            for index in range(6)
        ]
        scheduler = Scheduler(settings)
        items = scheduler.due(channels, now=msk(2026, 10, 18, 22, 5))
        self.assertEqual(len(items), 6)
        self.assertEqual({item.slot for item in items}, {"19:00"})
        self.assertEqual(
            sorted(item.channel_id for item in items),
            ["channel-{}".format(index) for index in range(6)],
        )

    def test_first_run_does_not_spam_old_slots(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=["09:00"])
        scheduler = Scheduler(settings)
        now = msk(2026, 10, 18, 12, 0)
        items = scheduler.due([channel], now=now)
        self.assertEqual(len(items), 1)  # только сегодняшние 09:00
        self.assertEqual(items[0].scheduled_at.astimezone(MSK).day, 18)
        self.assertGreaterEqual(items[0].scheduled_at, now - FIRST_RUN_WINDOW)

    def test_stale_state_uses_catch_up(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=["09:00", "13:00", "19:00"])
        scheduler = Scheduler(settings)
        now = msk(2026, 10, 18, 22, 5)
        # состояние трёхдневной давности — как после долгого простоя
        write_json(
            scheduler.state_path,
            {
                "version": 1,
                "last_check": format_iso(now - timedelta(days=3)),
                "done": {},
            },
        )
        items = scheduler.due([channel], now=now)
        self.assertEqual([item.slot for item in items], ["19:00"])

    def test_first_run_does_not_spam_old_slots(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=["09:00"])
        scheduler = Scheduler(settings)
        now = msk(2026, 10, 18, 12, 0)
        items = scheduler.due([channel], now=now)
        self.assertEqual(len(items), 1)  # только сегодняшние 09:00
        self.assertEqual(items[0].scheduled_at.astimezone(MSK).day, 18)
        self.assertGreaterEqual(items[0].scheduled_at, now - FIRST_RUN_WINDOW)

    def test_repeated_due_does_not_duplicate(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        scheduler = Scheduler(settings)
        now = msk(2026, 10, 18, 12, 0)
        first = scheduler.due([channel], now=now)
        self.assertEqual([item.slot for item in first], ["09:00"])
        second = scheduler.due([channel], now=now + timedelta(minutes=5))
        self.assertEqual(second, [])
        third = scheduler.due([channel], now=now + timedelta(minutes=10))
        self.assertEqual(third, [])

    def test_new_slot_after_last_check(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        scheduler = Scheduler(settings)
        scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))

        evening = scheduler.due([channel], now=msk(2026, 10, 18, 19, 0))
        self.assertEqual([item.slot for item in evening], ["18:00"])

        next_morning = scheduler.due([channel], now=msk(2026, 10, 19, 9, 1))
        self.assertEqual([item.slot for item in next_morning], ["09:00"])
        self.assertEqual(next_morning[0].scheduled_at.astimezone(MSK).day, 19)

    def test_different_timezones(self) -> None:
        settings = self.make_settings()
        channel_msk = self.make_channel(id="channel-msk", schedule=["09:00"], timezone_offset=3)
        channel_utc = self.make_channel(id="channel-utc", schedule=["09:00"], timezone_offset=0)
        scheduler = Scheduler(settings)
        now = msk(2026, 10, 18, 15, 0)  # 12:00 UTC
        items = scheduler.due([channel_msk, channel_utc], now=now)
        by_channel = {item.channel_id: item for item in items}
        self.assertEqual(len(items), 2)
        self.assertEqual(by_channel["channel-msk"].scheduled_at.astimezone(MSK).hour, 9)
        self.assertEqual(by_channel["channel-msk"].scheduled_at.astimezone(MSK).minute, 0)
        # для канала с UTC-поясом 09:00 — это 12:00 МСК
        self.assertEqual(by_channel["channel-utc"].scheduled_at.astimezone(MSK).hour, 12)
        self.assertEqual(
            by_channel["channel-utc"].scheduled_at.hour,
            9,
        )

    def test_disabled_channel_skipped(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(enabled=False)
        scheduler = Scheduler(settings)
        self.assertEqual(scheduler.due([channel], now=msk(2026, 10, 18, 12, 0)), [])

    def test_invalid_slot_in_schedule_ignored(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=["25:99", "09:00"])
        scheduler = Scheduler(settings)
        items = scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))
        self.assertEqual([item.slot for item in items], ["09:00"])

    def test_next_slot(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        scheduler = Scheduler(settings)
        next_evening = scheduler.next_slot(channel, now=msk(2026, 10, 18, 10, 0))
        self.assertEqual(next_evening.astimezone(MSK).hour, 18)
        self.assertEqual(next_evening.astimezone(MSK).day, 18)

        next_morning = scheduler.next_slot(channel, now=msk(2026, 10, 18, 20, 0))
        self.assertEqual(next_morning.astimezone(MSK).hour, 9)
        self.assertEqual(next_morning.astimezone(MSK).day, 19)

    def test_next_slot_none_for_empty_schedule(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=[])
        self.assertIsNone(Scheduler(settings).next_slot(channel, now=msk(2026, 10, 18, 12, 0)))


class SchedulerStateTests(SchedulerTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Фикстуры ниже датированы 2026-10-18, а _load_state отбрасывает done
        # старше DONE_RETENTION (14 дней). Фиксируем «текущее» время, иначе
        # тесты начинают падать просто оттого, что на календаре другая дата.
        frozen = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        patcher = mock.patch("content_factory.scheduler.utcnow", return_value=frozen)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_state_survives_restart(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        Scheduler(settings).due([channel], now=msk(2026, 10, 18, 12, 0))

        restarted = Scheduler(settings)
        self.assertEqual(restarted.due([channel], now=msk(2026, 10, 18, 12, 10)), [])
        later = restarted.due([channel], now=msk(2026, 10, 18, 19, 0))
        self.assertEqual([item.slot for item in later], ["18:00"])

    def test_mark_done_records_slot_and_is_idempotent(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        scheduler = Scheduler(settings)
        item = scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))[0]
        scheduler.mark_done(item)
        scheduler.mark_done(item)
        state = json.loads(scheduler.state_path.read_text(encoding="utf-8"))
        self.assertIn(format_iso(item.scheduled_at), state["done"][channel.id])
        self.assertEqual(len(state["done"][channel.id]), 1)

    def test_done_slot_not_returned_again(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        scheduler = Scheduler(settings)
        scheduler.mark_done(
            ScheduleItem(channel.id, "09:00", msk(2026, 10, 18, 9, 0).astimezone(MSK))
        )
        # сбрасываем last_check в состояние «сутки назад» с сохранённым done
        write_json(
            scheduler.state_path,
            {
                "version": 1,
                "last_check": format_iso(msk(2026, 10, 18, 0, 0)),
                "done": state_done(scheduler.state_path),
            },
        )
        items = scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))
        self.assertEqual(items, [])  # 09:00 уже выполнен, 18:00 ещё не наступил

    def test_catch_up_after_mark_done_does_not_repeat(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=["09:00", "13:00", "19:00"])
        scheduler = Scheduler(settings)
        now = msk(2026, 10, 18, 22, 5)

        first = scheduler.due([channel], now=now)
        self.assertEqual([item.slot for item in first], ["19:00"])
        scheduler.mark_done(first[0])

        # снова «первый запуск» (простой): поздний слот уже отработан,
        # старый бэклог (13:00/09:00) поднимать нельзя
        state = json.loads(scheduler.state_path.read_text(encoding="utf-8"))
        state["last_check"] = format_iso(now - timedelta(days=2))
        write_json(scheduler.state_path, state)

        repeat = scheduler.due([channel], now=now + timedelta(minutes=10))
        self.assertEqual(repeat, [])
        again = scheduler.due([channel], now=now + timedelta(minutes=20))
        self.assertEqual(again, [])

    def test_broken_state_file_is_recovered(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        scheduler = Scheduler(settings)
        scheduler.state_path.parent.mkdir(parents=True, exist_ok=True)
        scheduler.state_path.write_text("это не json {{", encoding="utf-8")
        items = scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))
        self.assertEqual([item.slot for item in items], ["09:00"])
        state = json.loads(scheduler.state_path.read_text(encoding="utf-8"))
        self.assertIn("last_check", state)

    def test_custom_state_path(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        custom = self.root / "custom" / "state.json"
        scheduler = Scheduler(settings, state_path=custom)
        self.assertEqual(scheduler.state_path, custom)
        scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))
        self.assertTrue(custom.is_file())

    def test_clock_skew_does_not_duplicate_done_slots(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel()
        scheduler = Scheduler(settings)
        item = scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))[0]
        scheduler.mark_done(item)
        # «часы перевели назад»: last_check в будущем, слот не должен вернуться
        state = json.loads(scheduler.state_path.read_text(encoding="utf-8"))
        state["last_check"] = format_iso(msk(2026, 10, 18, 13, 0))
        write_json(scheduler.state_path, state)
        items = scheduler.due([channel], now=msk(2026, 10, 18, 12, 0))
        keys = {(item.channel_id, item.slot, format_iso(item.scheduled_at)) for item in items}
        self.assertNotIn(
            (item.channel_id, item.slot, format_iso(item.scheduled_at)),
            keys,
        )


def state_done(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("done", {})
    except (OSError, ValueError):
        return {}


class DaemonLoopTests(SchedulerTestCase):
    def _due_channel(self) -> ChannelConfig:
        """Канал со слотом час назад по МСК — гарантированно наступил."""
        now_msk = utcnow().astimezone(MSK)
        slot = (now_msk - timedelta(hours=1)).strftime("%H:%M")
        return self.make_channel(schedule=[slot])

    def test_once_processes_due_slot_and_marks_done(self) -> None:
        settings = self.make_settings(data_dir=str(self.root / "data"))
        channel = self._due_channel()
        calls = []

        daemon_loop(
            settings,
            channels_provider=lambda: [channel],
            callback=lambda item: calls.append(item),
            once=True,
            sleep=lambda seconds: None,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].channel_id, channel.id)
        self.assertIsInstance(calls[0].slot, str)

        state = json.loads((settings.data_dir / "schedule_state.json").read_text(encoding="utf-8"))
        self.assertIn(format_iso(calls[0].scheduled_at), state["done"][channel.id])

        # повторный проход не должен публиковать тот же слот
        second_calls = []
        daemon_loop(
            settings,
            channels_provider=lambda: [channel],
            callback=lambda item: second_calls.append(item),
            once=True,
            sleep=lambda seconds: None,
        )
        self.assertEqual(second_calls, [])

    def test_interval_from_settings(self) -> None:
        settings = self.make_settings(daemon_interval_sec=77)
        channel = self.make_channel(schedule=[])
        recorded = []

        def fake_sleep(seconds):
            recorded.append(seconds)
            raise KeyboardInterrupt

        daemon_loop(
            settings,
            channels_provider=lambda: [channel],
            callback=lambda item: None,
            once=False,
            sleep=fake_sleep,
        )
        self.assertEqual(recorded, [77])

    def test_explicit_interval_overrides_settings(self) -> None:
        settings = self.make_settings(daemon_interval_sec=77)
        channel = self.make_channel(schedule=[])
        recorded = []

        def fake_sleep(seconds):
            recorded.append(seconds)
            raise KeyboardInterrupt

        daemon_loop(
            settings,
            channels_provider=lambda: [channel],
            callback=lambda item: None,
            once=False,
            interval=125,
            sleep=fake_sleep,
        )
        self.assertEqual(recorded, [125])

    def test_keyboard_interrupt_stops_loop_cleanly(self) -> None:
        settings = self.make_settings()
        channel = self.make_channel(schedule=[])

        def fake_sleep(seconds):
            raise KeyboardInterrupt

        daemon_loop(
            settings,
            channels_provider=lambda: [channel],
            callback=lambda item: None,
            once=False,
            sleep=fake_sleep,
        )  # не должно выбросить исключение

    def test_callback_error_does_not_crash_daemon(self) -> None:
        settings = self.make_settings()
        channel = self._due_channel()
        calls = []

        def bad_callback(item):
            calls.append(item)
            raise RuntimeError("сломался обработчик")

        daemon_loop(
            settings,
            channels_provider=lambda: [channel],
            callback=bad_callback,
            once=True,
            sleep=lambda seconds: None,
        )
        self.assertEqual(len(calls), 1)
        state = json.loads((settings.data_dir / "schedule_state.json").read_text(encoding="utf-8"))
        self.assertNotIn(channel.id, state.get("done", {}))

    def test_channels_provider_error_does_not_crash_daemon(self) -> None:
        settings = self.make_settings()

        def bad_provider():
            raise RuntimeError("конфигурация недоступна")

        daemon_loop(
            settings,
            channels_provider=bad_provider,
            callback=lambda item: None,
            once=True,
            sleep=lambda seconds: None,
        )


if __name__ == "__main__":
    unittest.main()
