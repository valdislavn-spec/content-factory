"""Price alerts for crypto channels: BingX prices → alert post on a trigger.

Rules live in ``config/price_alerts.yaml`` (see docs/monetization/price-alerts.md):

    rules:
      - symbol: BTC/USDT
        above: 78000          # cross above this level
        below: 74000          # cross below this level
        cooldown_minutes: 360
      - symbol: ETH/USDT
        move_percent: 2.5     # |move| in the last window
        move_window_minutes: 60
        cooldown_minutes: 120

The engine polls BingX public ticker (no API key), detects threshold crossings
and fast moves, and publishes a localized post to the selected channels with
per-rule cooldowns. State (last prices + last-fired timestamps) is kept on disk
so restarts don't spam duplicate alerts.

Design goals: best-effort (network errors never crash the loop), dry-run safe
(``settings.dry_run`` or ``--dry-run`` force the dryrun publisher), and
testable without network (price fetcher and publisher factory are injectable).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import Settings, load_channels
from .integrations.bingx import BingXClient
from .models import ChannelConfig, GeneratedPost, PublishResult, utcnow
from .publishers import get_publisher

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config/price_alerts.yaml"
DEFAULT_STATE_PATH = "data/price_alerts_state.json"

TEMPLATES: Dict[str, Dict[str, str]] = {
    "en": {
        "above": "🚀 {symbol} broke above ${level} — now ${price} ({change:+.2f}% / 24h).",
        "below": "🔻 {symbol} fell below ${level} — now ${price} ({change:+.2f}% / 24h).",
        "move": "⚡️ {symbol} moved {pct:+.2f}% in {window} min — now ${price}.",
        "footer": "Data: BingX · not financial advice.",
    },
    "es": {
        "above": "🚀 {symbol} superó los ${level} — ahora ${price} ({change:+.2f}% / 24h).",
        "below": "🔻 {symbol} cayó por debajo de ${level} — ahora ${price} ({change:+.2f}% / 24h).",
        "move": "⚡️ {symbol} se movió {pct:+.2f}% en {window} min — ahora ${price}.",
        "footer": "Datos: BingX · no es asesoramiento financiero.",
    },
    "ru": {
        "above": "🚀 {symbol} пробил уровень ${level} — сейчас ${price} ({change:+.2f}% за 24ч).",
        "below": "🔻 {symbol} упал ниже ${level} — сейчас ${price} ({change:+.2f}% за 24ч).",
        "move": "⚡️ {symbol} изменился на {pct:+.2f}% за {window} мин — сейчас ${price}.",
        "footer": "Данные: BingX · не инвестиционная рекомендация.",
    },
}

HASHTAGS = {"BTC": "#Bitcoin #BTC", "ETH": "#Ethereum #ETH", "SOL": "#Solana #SOL", "XRP": "#XRP"}


def _fmt_price(value: float) -> str:
    if value >= 1000:
        return "{:,.2f}".format(value).replace(",", ",")
    if value >= 1:
        return "{:,.2f}".format(value)
    return "{:,.4f}".format(value)


def _fmt_level(value: float) -> str:
    return "{:,.0f}".format(value)


@dataclass
class AlertRule:
    """Одно правило алерта."""

    symbol: str
    above: Optional[float] = None
    below: Optional[float] = None
    move_percent: Optional[float] = None
    move_window_minutes: int = 60
    cooldown_minutes: int = 360
    channels: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol or "").strip().upper().replace("-", "/")

    def keys(self) -> List[str]:
        """Идентификаторы сработавших условий (для cooldown)."""
        result: List[str] = []
        if self.above is not None:
            result.append("{}:above:{:g}".format(self.symbol, self.above))
        if self.below is not None:
            result.append("{}:below:{:g}".format(self.symbol, self.below))
        if self.move_percent is not None:
            result.append("{}:move:{:g}".format(self.symbol, self.move_percent))
        return result


def load_rules(config: Dict[str, Any]) -> List[AlertRule]:
    rules: List[AlertRule] = []
    for raw in config.get("rules") or []:
        if not isinstance(raw, dict) or not raw.get("symbol"):
            continue
        try:
            rule = AlertRule(
                symbol=str(raw.get("symbol")),
                above=float(raw["above"]) if raw.get("above") is not None else None,
                below=float(raw["below"]) if raw.get("below") is not None else None,
                move_percent=float(raw["move_percent"]) if raw.get("move_percent") is not None else None,
                move_window_minutes=int(raw.get("move_window_minutes") or 60),
                cooldown_minutes=int(raw.get("cooldown_minutes") or 360),
                channels=[str(c) for c in (raw.get("channels") or [])],
            )
        except (TypeError, ValueError):
            log.warning("Некорректное правило алерта: %r", raw)
            continue
        if rule.above is None and rule.below is None and rule.move_percent is None:
            continue
        rules.append(rule)
    return rules


def _iso_now(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def _parse_ts(value: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def check_rules(
    rules: Sequence[AlertRule],
    tickers: Dict[str, Dict[str, Any]],
    state: Dict[str, Any],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Возвращает сработавшие алерты; обновляет state (prices/last check)."""
    now = now or utcnow()
    prices_state: Dict[str, Any] = state.setdefault("prices", {})
    fired_state: Dict[str, Any] = state.setdefault("last_fired", {})
    alerts: List[Dict[str, Any]] = []
    for rule in rules:
        ticker = tickers.get(rule.symbol)
        if not ticker or ticker.get("price") is None:
            continue
        try:
            price = float(ticker["price"])
        except (TypeError, ValueError):
            continue
        previous = prices_state.get(rule.symbol)
        prev_price: Optional[float] = None
        prev_time: Optional[datetime] = None
        if isinstance(previous, dict):
            try:
                prev_price = float(previous.get("price"))
            except (TypeError, ValueError):
                prev_price = None
            prev_time = _parse_ts(previous.get("at"))
        elif previous is not None:
            try:
                prev_price = float(previous)
            except (TypeError, ValueError):
                prev_price = None

        fired_conditions: List[Tuple[str, Dict[str, Any]]] = []
        if prev_price is not None:
            if rule.above is not None and prev_price < rule.above <= price:
                fired_conditions.append(
                    (
                        "{}:above:{:g}".format(rule.symbol, rule.above),
                        {"type": "above", "level": rule.above},
                    )
                )
            if rule.below is not None and prev_price > rule.below >= price:
                fired_conditions.append(
                    (
                        "{}:below:{:g}".format(rule.symbol, rule.below),
                        {"type": "below", "level": rule.below},
                    )
                )
            if rule.move_percent is not None and prev_price:
                elapsed = (now - prev_time).total_seconds() if prev_time else None
                if elapsed is not None and 0 < elapsed <= rule.move_window_minutes * 60:
                    pct = (price - prev_price) / prev_price * 100.0
                    if abs(pct) >= rule.move_percent:
                        fired_conditions.append(
                            (
                                "{}:move:{:g}".format(rule.symbol, rule.move_percent),
                                {"type": "move", "pct": pct, "window": rule.move_window_minutes},
                            )
                        )

        for key, payload in fired_conditions:
            last = _parse_ts(fired_state.get(key))
            if last is not None and (now - last).total_seconds() < rule.cooldown_minutes * 60:
                continue
            fired_state[key] = _iso_now(now)
            alerts.append(
                {
                    "symbol": rule.symbol,
                    "price": price,
                    "percent_change": ticker.get("percent_change"),
                    "rule": rule,
                    **payload,
                }
            )
        prices_state[rule.symbol] = {"price": price, "at": _iso_now(now)}
    return alerts


def format_alert(alert: Dict[str, Any], language: str = "en") -> str:
    """Готовый текст поста для алерта (без хештегов)."""
    lang = str(language or "en").strip().lower()
    templates = TEMPLATES.get(lang) or TEMPLATES["en"]
    symbol = str(alert["symbol"]).replace("/USDT", "/USDT")
    base = symbol.split("/")[0]
    display = "{} ({})".format(base, symbol)
    change = alert.get("percent_change")
    try:
        change_value = float(change) if change is not None else 0.0
    except (TypeError, ValueError):
        change_value = 0.0
    if alert.get("type") == "move":
        text = templates["move"].format(
            symbol=display,
            pct=float(alert.get("pct") or 0.0),
            window=int(alert.get("window") or 60),
            price=_fmt_price(float(alert["price"])),
        )
    elif alert.get("type") == "below":
        text = templates["below"].format(
            symbol=display,
            level=_fmt_level(float(alert.get("level") or 0)),
            price=_fmt_price(float(alert["price"])),
            change=change_value,
        )
    else:
        text = templates["above"].format(
            symbol=display,
            level=_fmt_level(float(alert.get("level") or 0)),
            price=_fmt_price(float(alert["price"])),
            change=change_value,
        )
    footer = templates.get("footer", "")
    hashtags = HASHTAGS.get(base, "")
    parts = [text]
    if footer:
        parts.append(footer)
    if hashtags:
        parts.append(hashtags)
    return "\n\n".join(parts)


class PriceAlertEngine:
    """Проверяет правила и публикует алерты в каналы."""

    def __init__(
        self,
        settings: Settings,
        config: Dict[str, Any],
        *,
        price_fetcher: Optional[Callable[[str], Dict[str, Any]]] = None,
        publisher_factory: Optional[Callable[[str, Settings], Any]] = None,
        channels: Optional[Sequence[ChannelConfig]] = None,
        state_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        self.settings = settings
        self.config = config or {}
        self.rules = load_rules(self.config)
        self.dry_run = bool(dry_run or settings.dry_run)
        self.price_fetcher = price_fetcher
        self.publisher_factory = publisher_factory or get_publisher
        root = Path(settings.root)
        self.channels = list(channels) if channels is not None else self._load_channels(root, settings)
        self.channels = [c for c in self.channels if c.id in self._allowed_channels()]
        state_value = state_path or self.config.get("state_path") or DEFAULT_STATE_PATH
        self.state_path = Path(state_value)
        if not self.state_path.is_absolute():
            self.state_path = root / self.state_path
        self.state = self._load_state()

    def _allowed_channels(self) -> set:
        ids = self.config.get("channels") or []
        return {str(c) for c in ids} if ids else set()

    def _load_channels(self, root: Path, settings: Settings) -> List[ChannelConfig]:
        files = self.config.get("channels_files") or []
        if isinstance(files, str):
            files = [files]
        loaded: List[ChannelConfig] = []
        seen: set = set()
        for relative in files or []:
            path = Path(str(relative))
            if not path.is_absolute():
                path = root / path
            try:
                for channel in load_channels(settings, path=path):
                    if channel.id not in seen:
                        seen.add(channel.id)
                        loaded.append(channel)
            except Exception as exc:  # noqa: BLE001 - конфиг канала не должен ронять алерты
                log.warning("Не удалось загрузить каналы из %s: %s", path, exc)
        return loaded

    def _load_state(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:  # noqa: BLE001
            log.warning("Не удалось сохранить состояние алертов: %s", exc)

    def _fetch_tickers(self) -> Dict[str, Dict[str, Any]]:
        symbols = sorted({rule.symbol for rule in self.rules})
        result: Dict[str, Dict[str, Any]] = {}
        if self.price_fetcher is not None:
            for symbol in symbols:
                try:
                    result[symbol] = self.price_fetcher(symbol)
                except Exception:  # noqa: BLE001
                    continue
            return result
        client = BingXClient()
        for symbol in symbols:
            try:
                result[symbol] = client.ticker(symbol)
            except Exception as exc:  # noqa: BLE001
                log.warning("Цена %s недоступна: %s", symbol, exc)
        return result

    def _publisher(self):
        name = "dryrun" if self.dry_run else "telegram"
        return self.publisher_factory(name, self.settings)

    def _target_channels(self, alert: Dict[str, Any]) -> List[ChannelConfig]:
        rule = alert.get("rule")
        allowed = set(getattr(rule, "channels", None) or [])
        channels = self.channels
        if allowed:
            channels = [c for c in channels if c.id in allowed]
        return channels

    def _maybe_affiliate(self, text: str, channel: ChannelConfig) -> str:
        """Добавляет реферальную строку в алерт 1 раз в N алертов канала."""
        affiliate = getattr(channel, "affiliate", None)
        if not isinstance(affiliate, dict) or not affiliate.get("enabled"):
            # fallback: общий блок affiliate в config/price_alerts.yaml
            affiliate = self.config.get("affiliate")
        if not isinstance(affiliate, dict) or not affiliate.get("enabled"):
            return text
        try:
            every_n = int(self.config.get("affiliate_every_n") or 3)
        except (TypeError, ValueError):
            every_n = 3
        counters = self.state.setdefault("affiliate_counters", {})
        try:
            count = int(counters.get(channel.id) or 0)
        except (TypeError, ValueError):
            count = 0
        counters[channel.id] = count + 1
        if every_n > 1 and count % every_n != 0:
            return text
        from .integrations.affiliate import build_affiliate_line
        from .integrations.marketline import insert_before_hashtags

        line = build_affiliate_line(affiliate, language=channel.language, channel_id=channel.id)
        return insert_before_hashtags(text, line) if line else text

    def run_once(self) -> List[PublishResult]:
        if not self.rules:
            return []
        tickers = self._fetch_tickers()
        alerts = check_rules(self.rules, tickers, self.state)
        if not alerts:
            self._save_state()
            return []
        results: List[PublishResult] = []
        for alert in alerts:
            for channel in self._target_channels(alert):
                text = self._maybe_affiliate(format_alert(alert, channel.language), channel)
                post = GeneratedPost(
                    id="alert-{}-{}".format(
                        str(alert["symbol"]).replace("/", "-").lower(),
                        int(time.time() * 1000),
                    ),
                    channel_id=channel.id,
                    cluster_id="price-alert",
                    format="alert",
                    text=text,
                )
                try:
                    results.append(self._publisher().publish(post, channel, self.settings))
                except Exception as exc:  # noqa: BLE001
                    log.exception("Не удалось опубликовать алерт: %s", exc)
        self._save_state()
        return results

    def run_forever(self, interval_seconds: float = 60.0) -> None:
        log.info("Price alerts: %d правил, интервал %.0f c", len(self.rules), interval_seconds)
        while True:
            try:
                results = self.run_once()
                for result in results:
                    log.info(
                        "Алерт %s: %s%s",
                        result.channel_id,
                        "ok" if result.ok else "fail",
                        "" if result.ok else ": {}".format(result.error),
                    )
            except Exception:  # noqa: BLE001 - цикл не должен падать
                log.exception("Ошибка цикла алертов")
            time.sleep(max(10.0, float(interval_seconds)))
