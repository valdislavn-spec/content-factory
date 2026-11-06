"""Планировщик публикаций по расписанию каналов (в их часовых поясах).

Состояние (последняя проверка и уже отработанные слоты) хранится в
data/schedule_state.json и пишется атомарно, поэтому повторный запуск
демона не публикует один и тот же слот дважды.

Защита от спама при первом запуске/долгом простое (catch-up): в этом режиме
для каждого канала выдаётся не более ОДНОГО — самого позднего наступившего
слота за последние 24 часа. Иначе демон, впервые запущенный вечером, выдал
бы сразу все слоты дня (6 каналов × 3 слота = до 18 публикаций подряд).

Планировщик не ходит в сеть и не публикует сам: он лишь говорит, какие
слоты наступили, а публикацию выполняет callback демона.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .config import Settings
from .models import ChannelConfig, utcnow
from .utils import (
    format_iso,
    parse_datetime,
    parse_hhmm,
    read_json,
    write_json,
)

logger = logging.getLogger(__name__)

STATE_VERSION = 1
# Окно первого запуска/catch-up: слоты старше суток не поднимаем вообще,
# а из наступивших берём только самый поздний на каждый канал.
FIRST_RUN_WINDOW = timedelta(hours=24)
# Сколько хранить информацию об отработанных слотах.
DONE_RETENTION = timedelta(days=14)
# Глубина поиска следующего слота.
NEXT_SLOT_HORIZON = timedelta(days=8)


@dataclass
class ScheduleItem:
    """Наступивший слот публикации канала."""

    channel_id: str
    slot: str  # "HH:MM" в часовом поясе канала
    scheduled_at: datetime  # timezone-aware UTC

    def __post_init__(self) -> None:
        if self.scheduled_at.tzinfo is None:
            self.scheduled_at = self.scheduled_at.replace(tzinfo=timezone.utc)
        else:
            self.scheduled_at = self.scheduled_at.astimezone(timezone.utc)

    def to_dict(self) -> Dict[str, str]:
        return {
            "channel_id": self.channel_id,
            "slot": self.slot,
            "scheduled_at": format_iso(self.scheduled_at),
        }


def _as_utc(value: Optional[datetime]) -> datetime:
    if value is None:
        return utcnow()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Scheduler:
    """Считает наступившие слоты и запоминает их в schedule_state.json."""

    def __init__(self, settings: Settings, state_path: Optional[Any] = None) -> None:
        self.settings = settings
        self.state_path = (
            Path(state_path) if state_path else Path(settings.data_dir) / "schedule_state.json"
        )

    # ------------------------------------------------------------------
    # состояние
    # ------------------------------------------------------------------
    @property
    def last_check(self) -> Optional[datetime]:
        state = self._load_state()
        value = state.get("last_check")
        return parse_datetime(value) if value else None

    def _load_state(self) -> Dict[str, Any]:
        """Читает состояние с диска; битый/отсутствующий файл — пустое состояние."""
        raw = read_json(self.state_path, None)
        state: Dict[str, Any] = {"version": STATE_VERSION, "last_check": "", "done": {}}
        if not isinstance(raw, dict):
            return state
        last_check = parse_datetime(raw.get("last_check"))
        if last_check is not None:
            state["last_check"] = format_iso(last_check)
        done_raw = raw.get("done")
        if not isinstance(done_raw, dict):
            return state
        retention_start = utcnow() - DONE_RETENTION
        for channel_id, values in done_raw.items():
            if not isinstance(values, (list, tuple)):
                continue
            cleaned: List[str] = []
            for value in values:
                parsed = parse_datetime(value)
                if parsed is None or parsed < retention_start:
                    continue
                cleaned.append(format_iso(parsed))
            if cleaned:
                state["done"][str(channel_id)] = sorted(set(cleaned))
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        state["version"] = STATE_VERSION
        write_json(self.state_path, state)

    # ------------------------------------------------------------------
    # вычисление слотов
    # ------------------------------------------------------------------
    @staticmethod
    def _slots_between(
        channel: ChannelConfig, start_utc: datetime, end_utc: datetime
    ) -> List[ScheduleItem]:
        """Слоты канала в интервале (start_utc, end_utc] с учётом его пояса."""
        if start_utc > end_utc:
            return []
        local_tz = channel.local_tz
        start_local = start_utc.astimezone(local_tz)
        end_local = end_utc.astimezone(local_tz)
        items: Dict[tuple, ScheduleItem] = {}
        day: date = start_local.date()
        last_day: date = end_local.date()
        while day <= last_day:
            for raw_slot in channel.schedule:
                try:
                    hour, minute = parse_hhmm(raw_slot)
                except ValueError:
                    logger.warning(
                        "Канал %s: некорректное время в расписании %r — пропущено",
                        channel.id,
                        raw_slot,
                    )
                    continue
                slot_local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=local_tz)
                slot_utc = slot_local.astimezone(timezone.utc)
                if not (start_utc < slot_utc <= end_utc):
                    continue
                slot = "{:02d}:{:02d}".format(hour, minute)
                key = (channel.id, slot, format_iso(slot_utc))
                items[key] = ScheduleItem(channel.id, slot, slot_utc)
            day = day + timedelta(days=1)
        return sorted(items.values(), key=lambda item: (item.scheduled_at, item.slot))

    def due(
        self, channels: Sequence[ChannelConfig], now: Optional[datetime] = None
    ) -> List[ScheduleItem]:
        """Возвращает наступившие слоты и сдвигает отметку последней проверки.

        Обычная работа демона: окно (last_check, now], поэтому один и тот же
        слот не выдаётся повторно. Режим catch-up включается, когда состояния
        нет, последняя проверка старше 24 часов или «часы перевели назад» —
        тогда для каждого канала выдаётся не более ОДНОГО, самого позднего
        наступившего слота. Если этот слот уже отработан, более старые не
        поднимаем: бэклог не публикуем и не спамим.
        """
        now_utc = _as_utc(now)
        state = self._load_state()
        last_check = parse_datetime(state.get("last_check"))
        catch_up = (
            last_check is None
            or last_check > now_utc
            or (now_utc - last_check) > FIRST_RUN_WINDOW
        )
        if catch_up:
            window_start = now_utc - FIRST_RUN_WINDOW
            logger.info(
                "Планировщик: catch-up (первый запуск или простой > %s ч) — "
                "по одному последнему слоту на канал",
                int(FIRST_RUN_WINDOW.total_seconds() // 3600),
            )
        else:
            window_start = last_check

        done = state.get("done", {})
        items: List[ScheduleItem] = []
        seen: set = set()
        for channel in channels:
            if not channel.enabled:
                continue
            done_slots = set(done.get(channel.id, []))
            channel_slots = self._slots_between(channel, window_start, now_utc)
            if catch_up:
                if not channel_slots:
                    continue
                latest = channel_slots[-1]
                # самый поздний слот уже отработан — старый бэклог не поднимаем
                if format_iso(latest.scheduled_at) in done_slots:
                    continue
                candidates = [latest]
            else:
                candidates = channel_slots
            for item in candidates:
                slot_iso = format_iso(item.scheduled_at)
                if slot_iso in done_slots:
                    continue
                key = (item.channel_id, item.slot, slot_iso)
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)

        items.sort(key=lambda item: (item.scheduled_at, item.channel_id, item.slot))
        state["last_check"] = format_iso(now_utc)
        self._save_state(state)
        if items:
            logger.info(
                "Планировщик: наступило слотов — %s (до %s)",
                len(items),
                format_iso(now_utc),
            )
        return items

    def mark_done(self, item: ScheduleItem) -> None:
        """Фиксирует слот как отработанный (идемпотентно)."""
        state = self._load_state()
        slot_iso = format_iso(item.scheduled_at)
        entries = set(state["done"].get(item.channel_id, []))
        entries.add(slot_iso)
        state["done"][item.channel_id] = sorted(entries)
        self._save_state(state)
        logger.debug(
            "Планировщик: слот %s канала %s отмечен выполненным",
            item.slot,
            item.channel_id,
        )

    def next_slot(
        self, channel: ChannelConfig, now: Optional[datetime] = None
    ) -> Optional[datetime]:
        """Ближайший будущий слот канала (UTC) или None, если его нет."""
        now_utc = _as_utc(now)
        items = self._slots_between(channel, now_utc, now_utc + NEXT_SLOT_HORIZON)
        return items[0].scheduled_at if items else None


def daemon_loop(
    settings: Settings,
    channels_provider: Callable[[], List[ChannelConfig]],
    callback: Callable[[ScheduleItem], None],
    once: bool = False,
    interval: Optional[int] = None,
    sleep: Optional[Callable[[float], None]] = None,
) -> None:
    """Автономный цикл: проверять расписание и вызывать callback для слотов.

    :param channels_provider: функция, возвращающая актуальный список каналов;
    :param callback: обработчик слота (публикация поста);
    :param once: один проход и выход — для cron/тестов;
    :param interval: пауза в секундах; None — settings.app.daemon_interval_sec;
    :param sleep: подмена time.sleep для тестов.
    """
    scheduler = Scheduler(settings)
    sleeper = sleep or time.sleep
    pause = int(interval) if interval is not None else int(
        settings.app.get("daemon_interval_sec", 60)
    )
    pause = max(5, pause)
    logger.info(
        "Демон запущен: интервал %s с, состояние %s, dry_run=%s",
        pause,
        scheduler.state_path,
        settings.dry_run,
    )
    try:
        while True:
            try:
                channels = channels_provider()
            except Exception as exc:  # noqa: BLE001 - демон не должен падать
                logger.exception("Не удалось получить список каналов: %s", exc)
                channels = []
            items = scheduler.due(channels)
            for item in items:
                try:
                    callback(item)
                except Exception as exc:  # noqa: BLE001 - один слот не роняет демона
                    logger.exception(
                        "Ошибка обработки слота %s канала %s: %s",
                        item.slot,
                        item.channel_id,
                        exc,
                    )
                    continue
                scheduler.mark_done(item)
            if once:
                logger.info("Демон: одиночный проход завершён, слотов обработано %s", len(items))
                return
            sleeper(pause)
    except KeyboardInterrupt:
        logger.info("Демон остановлен по Ctrl+C")
