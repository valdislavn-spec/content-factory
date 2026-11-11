"""Монетизация каналов: продажа рекламных постов за Telegram Stars (XTR).

Схема (без платёжного провайдера и без сервера):
    1. рекламодатель открывает бота → выбирает канал и тариф;
    2. бот выставляет счёт в Stars (``sendInvoice``, currency=XTR);
    3. после оплаты (``successful_payment``) бот запрашивает текст поста;
    4. заявка уходит админу с кнопками «Одобрить/Отклонить»;
    5. одобренная заявка попадает в ``data/ads/queue/<order_id>.json`` —
       дальше её публикует контент-завод (или вручную).

Хранилище — своя таблица ``ad_orders`` в том же SQLite (``settings.db_path``).
Все сетевые вызовы — Bot API ``https://api.telegram.org`` (stdlib urllib).

Безопасность: платёж принимает только наш бот; публикация — только после ручного
одобрения админом (никакого автопостига чужого текста).
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import GeneratedPost, utcnow
from .utils import env

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
CURRENCY = "XTR"
STATUSES = (
    "pending_invoice",
    "awaiting_text",
    "moderation",
    "approved",
    "rejected",
    "published",
    "refunded",
)


class MonetizationError(RuntimeError):
    """Ошибка конфигурации/API монетизации."""


# ---------------------------------------------------------------------------
# Конфиг
# ---------------------------------------------------------------------------


@dataclass
class Tariff:
    code: str          # "1/24"
    price: int         # в Stars
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "price": self.price, "description": self.description}


@dataclass
class ChannelOffer:
    id: str
    title: str
    tariffs: List[Tariff] = field(default_factory=list)

    def tariff(self, code: str) -> Optional[Tariff]:
        for tariff in self.tariffs:
            if tariff.code == code:
                return tariff
        return None


def load_offers(path: Path) -> Tuple[Dict[str, Any], Dict[str, ChannelOffer]]:
    """Читает config/monetization.yaml → (raw_config, offers)."""
    import yaml

    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise MonetizationError(f"не удалось прочитать конфиг {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise MonetizationError(f"конфиг {path}: ожидался объект")
    channels = raw.get("channels")
    if not isinstance(channels, dict) or not channels:
        raise MonetizationError(f"конфиг {path}: нет секции channels")
    offers: Dict[str, ChannelOffer] = {}
    min_amount = int(raw.get("min_amount") or 1)
    for channel_id, data in channels.items():
        if not isinstance(data, dict):
            raise MonetizationError(f"канал {channel_id}: ожидался объект")
        title = str(data.get("title") or channel_id)
        tariffs_raw = data.get("tariffs")
        if not isinstance(tariffs_raw, dict) or not tariffs_raw:
            raise MonetizationError(f"канал {channel_id}: нет tariffs")
        tariffs: List[Tariff] = []
        for code, params in tariffs_raw.items():
            params = params if isinstance(params, dict) else {}
            try:
                price = int(params.get("price"))
            except (TypeError, ValueError) as exc:
                raise MonetizationError(f"{channel_id}/{code}: price должен быть числом") from exc
            if price < max(1, min_amount):
                raise MonetizationError(f"{channel_id}/{code}: price должен быть >= {max(1, min_amount)}")
            tariffs.append(
                Tariff(code=str(code), price=price, description=str(params.get("description") or ""))
            )
        offers[str(channel_id)] = ChannelOffer(id=str(channel_id), title=title, tariffs=tariffs)
    return raw, offers


def channel_offer(offers: Dict[str, ChannelOffer], channel_id: str) -> Optional[ChannelOffer]:
    return offers.get(str(channel_id))


# ---------------------------------------------------------------------------
# Заказы (SQLite)
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ad_orders (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    tariff        TEXT NOT NULL,
    amount        INTEGER NOT NULL,
    payload       TEXT NOT NULL,
    buyer_id      TEXT DEFAULT '',
    buyer_username TEXT DEFAULT '',
    ad_text       TEXT DEFAULT '',
    status        TEXT NOT NULL,
    invoice_url   TEXT DEFAULT '',
    paid_at       TEXT DEFAULT '',
    queue_file    TEXT DEFAULT '',
    payment_charge_id TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ad_orders_status ON ad_orders (status, created_at);
"""


@dataclass
class AdOrder:
    id: str
    channel_id: str
    tariff: str
    amount: int
    payload: str = ""
    buyer_id: str = ""
    buyer_username: str = ""
    ad_text: str = ""
    status: str = "pending_invoice"
    invoice_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    paid_at: str = ""
    queue_file: str = ""
    payment_charge_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "tariff": self.tariff,
            "amount": self.amount,
            "payload": self.payload,
            "buyer_id": self.buyer_id,
            "buyer_username": self.buyer_username,
            "ad_text": self.ad_text,
            "status": self.status,
            "invoice_url": self.invoice_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "paid_at": self.paid_at,
            "queue_file": self.queue_file,
            "payment_charge_id": self.payment_charge_id,
        }


def _now_iso() -> str:
    return utcnow().isoformat()


class AdOrderStore:
    """Хранилище заявок на рекламу в SQLite (отдельная таблица)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Добавляет новые колонки в уже существующую таблицу."""
        columns = {
            str(row[1]) for row in self.conn.execute("PRAGMA table_info(ad_orders)").fetchall()
        }
        if "payment_charge_id" not in columns:
            self.conn.execute("ALTER TABLE ad_orders ADD COLUMN payment_charge_id TEXT DEFAULT ''")

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # pragma: no cover
            pass

    def __enter__(self) -> "AdOrderStore":
        return self

    def __exit__(self, *args) -> bool:
        self.close()
        return False

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    def create(
        self,
        channel_id: str,
        tariff: str,
        amount: int,
        buyer_id: str = "",
        buyer_username: str = "",
        payload: str = "",
    ) -> AdOrder:
        order = AdOrder(
            id=self.new_id(),
            channel_id=str(channel_id),
            tariff=str(tariff),
            amount=int(amount),
            payload=str(payload or ""),
            buyer_id=str(buyer_id or ""),
            buyer_username=str(buyer_username or ""),
            status="pending_invoice",
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        if not order.payload:
            order.payload = make_payload(order.channel_id, order.tariff, order.id)
        self.conn.execute(
            """INSERT INTO ad_orders
            (id, created_at, updated_at, channel_id, tariff, amount, payload,
             buyer_id, buyer_username, ad_text, status, invoice_url, paid_at, queue_file,
             payment_charge_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.id,
                order.created_at,
                order.updated_at,
                order.channel_id,
                order.tariff,
                order.amount,
                order.payload,
                order.buyer_id,
                order.buyer_username,
                order.ad_text,
                order.status,
                order.invoice_url,
                order.paid_at,
                order.queue_file,
                order.payment_charge_id,
            ),
        )
        self.conn.commit()
        return order

    def get(self, order_id: str) -> Optional[AdOrder]:
        row = self.conn.execute("SELECT * FROM ad_orders WHERE id = ?", (str(order_id),)).fetchone()
        return self._row(row) if row else None

    def by_payload(self, payload: str) -> Optional[AdOrder]:
        row = self.conn.execute(
            "SELECT * FROM ad_orders WHERE payload = ? ORDER BY created_at DESC LIMIT 1",
            (str(payload),),
        ).fetchone()
        return self._row(row) if row else None

    def latest_for_buyer(self, buyer_id: str, status: str) -> Optional[AdOrder]:
        row = self.conn.execute(
            """SELECT * FROM ad_orders WHERE buyer_id = ? AND status = ?
               ORDER BY created_at DESC LIMIT 1""",
            (str(buyer_id), str(status)),
        ).fetchone()
        return self._row(row) if row else None

    def update(self, order_id: str, **fields: Any) -> Optional[AdOrder]:
        allowed = {field_name for field_name in AdOrder.__dataclass_fields__ if field_name != "id"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return self.get(order_id)
        values["updated_at"] = _now_iso()
        assignments = ", ".join(f"{key} = ?" for key in values)
        params = list(values.values()) + [str(order_id)]
        self.conn.execute(f"UPDATE ad_orders SET {assignments} WHERE id = ?", params)
        self.conn.commit()
        return self.get(order_id)

    def list(self, status: Optional[str] = None, limit: int = 50) -> List[AdOrder]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM ad_orders WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (str(status), int(limit)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM ad_orders ORDER BY created_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [self._row(row) for row in rows]

    def stats(self) -> Dict[str, Any]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count, COALESCE(SUM(amount),0) AS stars FROM ad_orders GROUP BY status"
        ).fetchall()
        by_status = {str(row["status"]): int(row["count"]) for row in rows}
        paid_stars = sum(
            int(row["stars"]) for row in rows if str(row["status"]) not in ("pending_invoice", "rejected")
        )
        return {"by_status": by_status, "paid_stars": paid_stars}

    @staticmethod
    def _row(row: sqlite3.Row) -> AdOrder:
        data = dict(row)
        return AdOrder(
            id=str(data.get("id") or ""),
            channel_id=str(data.get("channel_id") or ""),
            tariff=str(data.get("tariff") or ""),
            amount=int(data.get("amount") or 0),
            payload=str(data.get("payload") or ""),
            buyer_id=str(data.get("buyer_id") or ""),
            buyer_username=str(data.get("buyer_username") or ""),
            ad_text=str(data.get("ad_text") or ""),
            status=str(data.get("status") or ""),
            invoice_url=str(data.get("invoice_url") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            paid_at=str(data.get("paid_at") or ""),
            queue_file=str(data.get("queue_file") or ""),
            payment_charge_id=str(data.get("payment_charge_id") or ""),
        )


# ---------------------------------------------------------------------------
# Payload счёта
# ---------------------------------------------------------------------------


def make_payload(channel_id: str, tariff: str, order_id: str) -> str:
    """Payload счёта: ``ad:<channel>:<tariff>:<order>`` (<=128 байт)."""
    channel = re.sub(r"[^A-Za-z0-9_-]+", "-", str(channel_id))[:24]
    tariff_code = re.sub(r"[^A-Za-z0-9_-]+", "-", str(tariff))[:12]
    order = re.sub(r"[^A-Za-z0-9]+", "", str(order_id))[:16]
    payload = f"ad:{channel}:{tariff_code}:{order}"
    return payload[:128]


def parse_payload(payload: str) -> Optional[Dict[str, str]]:
    text = str(payload or "").strip()
    parts = text.split(":")
    if len(parts) != 4 or parts[0] != "ad" or not parts[1] or not parts[2]:
        return None
    return {"channel_id": parts[1], "tariff": parts[2], "order_id": parts[3]}


# ---------------------------------------------------------------------------
# Планирование ответов бота (чистые функции)
# ---------------------------------------------------------------------------


def _username(user: Dict[str, Any]) -> str:
    value = str(user.get("username") or "").strip()
    return f"@{value}" if value else ""


def _start_keyboard(offers: Dict[str, ChannelOffer]) -> Dict[str, Any]:
    rows = [
        [{"text": f"📣 {offer.title}", "callback_data": f"ch:{offer.id}"}]
        for offer in offers.values()
    ]
    return {"inline_keyboard": rows}


def _tariffs_keyboard(offer: ChannelOffer) -> Dict[str, Any]:
    rows = [
        [
            {
                "text": f"{tariff.code} — {tariff.price} ⭐",
                "callback_data": f"buy:{offer.id}:{re.sub(r'[^A-Za-z0-9_-]+', '-', tariff.code)}",
            }
        ]
        for tariff in offer.tariffs
    ]
    return {"inline_keyboard": rows + [[{"text": "⬅️ Назад", "callback_data": "back"}] ]}


def _invoice_payload(store: AdOrderStore, order: AdOrder, offers: Dict[str, ChannelOffer]) -> Dict[str, Any]:
    offer = offers.get(order.channel_id)
    title = f"Реклама в «{offer.title if offer else order.channel_id}»"
    tariff = offer.tariff(order.tariff) if offer else None
    description = (
        f"{tariff.description + '. ' if tariff and tariff.description else ''}"
        f"Тариф {order.tariff}. После оплаты пришлите текст поста — публикация после модерации."
    )
    return {
        "chat_id": int(order.buyer_id) if str(order.buyer_id).isdigit() else order.buyer_id,
        "title": title[:32],
        "description": description[:255],
        "payload": order.payload,
        "provider_token": "",  # для Stars провайдер не нужен
        "currency": CURRENCY,
        "prices": [{"label": f"Тариф {order.tariff}"[:32], "amount": int(order.amount)}],
    }


def plan_update_actions(
    update: Dict[str, Any],
    store: AdOrderStore,
    offers: Dict[str, ChannelOffer],
    admin_chat_id: str = "",
    queue_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Возвращает список вызовов Bot API, которые надо выполнить по update.

    Побочные эффекты (запись заказов) выполняются здесь же; сеть — снаружи.
    """
    actions: List[Dict[str, Any]] = []

    # --- сообщения ---
    message = update.get("message") or {}
    if message:
        text = str(message.get("text") or "")
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = chat.get("id")
        user_id = str(user.get("id") or "")
        if text.startswith("/start"):
            actions.append(
                {
                    "method": "sendMessage",
                    "payload": {
                        "chat_id": chat_id,
                        "text": (
                            "Здравствуйте! Это бот размещения рекламы в наших Telegram-каналах.\n"
                            "Выберите канал — покажу тарифы в ⭐ Telegram Stars."
                        ),
                        "reply_markup": _start_keyboard(offers),
                    },
                }
            )
            return actions
        if text.startswith("/buy"):
            actions.append(
                {
                    "method": "sendMessage",
                    "payload": {
                        "chat_id": chat_id,
                        "text": "Выберите канал:",
                        "reply_markup": _start_keyboard(offers),
                    },
                }
            )
            return actions
        if text.startswith("/help"):
            actions.append(
                {
                    "method": "sendMessage",
                    "payload": {
                        "chat_id": chat_id,
                        "text": (
                            "Как это работает: выберите канал и тариф → оплатите публикацию "
                            "в ⭐ Telegram Stars → пришлите текст поста. После модерации пост "
                            "выходит в канале. Вопросы — ответом на это сообщение."
                        ),
                    },
                }
            )
            return actions
        if text.startswith("/orders"):
            admin = _is_admin(user_id, admin_chat_id)
            if admin:
                items = store.list(limit=20)
                lines = [f"{order.id} | {order.channel_id} {order.tariff} | {order.status} | {order.ad_text[:40]}" for order in items]
                actions.append(
                    {
                        "method": "sendMessage",
                        "payload": {"chat_id": chat_id, "text": "\n".join(lines) or "Заказов нет"},
                    }
                )
                return actions
        # текст рекламы после оплаты
        if text and not text.startswith("/"):
            order = store.latest_for_buyer(user_id, "awaiting_text")
            if order is not None and len(text) > 3000:
                actions.append(
                    {
                        "method": "sendMessage",
                        "payload": {
                            "chat_id": chat_id,
                            "text": "Текст слишком длинный (максимум 3000 символов). Пришлите короче.",
                        },
                    }
                )
                return actions
            if order is not None:
                order = store.update(order.id, ad_text=text, status="moderation")
                actions.append(
                    {
                        "method": "sendMessage",
                        "payload": {
                            "chat_id": chat_id,
                            "text": "Спасибо! Текст отправлен на модерацию. Ответим здесь же.",
                        },
                    }
                )
                if admin_chat_id:
                    actions.append(
                        {
                            "method": "sendMessage",
                            "payload": {
                                "chat_id": _chat_id(admin_chat_id),
                                "text": (
                                    f"🆕 Заявка {order.id}\n"
                                    f"Канал: {order.channel_id} · тариф {order.tariff} · {order.amount} ⭐\n"
                                    f"Покупатель: {_username(user) or user_id}\n\n{text[:3000]}"
                                ),
                                "reply_markup": _moderation_keyboard(order.id),
                            },
                        }
                    )
                return actions

    # --- callback-кнопки ---
    callback = update.get("callback_query") or {}
    if callback:
        data = str(callback.get("data") or "")
        user = callback.get("from") or {}
        user_id = str(user.get("id") or "")
        chat_id = (callback.get("message") or {}).get("chat", {}).get("id") or user_id
        actions.append({"method": "answerCallbackQuery", "payload": {"callback_query_id": callback.get("id")}})
        if data == "back":
            actions.append(
                {
                    "method": "sendMessage",
                    "payload": {
                        "chat_id": chat_id,
                        "text": "Выберите канал:",
                        "reply_markup": _start_keyboard(offers),
                    },
                }
            )
            return actions
        if data.startswith("ch:"):
            offer = offers.get(data.split(":", 1)[1])
            if offer is None:
                actions.append({"method": "sendMessage", "payload": {"chat_id": chat_id, "text": "Канал не найден"}})
                return actions
            actions.append(
                {
                    "method": "sendMessage",
                    "payload": {
                        "chat_id": chat_id,
                        "text": f"«{offer.title}»: выберите тариф.",
                        "reply_markup": _tariffs_keyboard(offer),
                    },
                }
            )
            return actions
        if data.startswith("buy:"):
            parts = data.split(":")
            if len(parts) != 3:
                return actions
            offer = offers.get(parts[1])
            tariff = offer.tariff(parts[2].replace("-", "/")) if offer else None
            if offer is None or tariff is None:
                actions.append({"method": "sendMessage", "payload": {"chat_id": chat_id, "text": "Тариф не найден"}})
                return actions
            order = store.create(
                channel_id=offer.id,
                tariff=tariff.code,
                amount=tariff.price,
                buyer_id=user_id,
                buyer_username=_username(user),
            )
            actions.append({"method": "sendInvoice", "payload": _invoice_payload(store, order, offers)})
            return actions
        if data.startswith(("adok:", "adno:")):
            if not _is_admin(user_id, admin_chat_id):
                actions.append({"method": "sendMessage", "payload": {"chat_id": chat_id, "text": "Недостаточно прав"}})
                return actions
            verdict, order_id = data.split(":", 1)
            order = store.get(order_id)
            if order is None:
                actions.append({"method": "sendMessage", "payload": {"chat_id": chat_id, "text": "Заявка не найдена"}})
                return actions
            if verdict == "adok":
                queue_file = ""
                if queue_dir is not None:
                    queue_dir = Path(queue_dir)
                    queue_dir.mkdir(parents=True, exist_ok=True)
                    path = queue_dir / f"{order.id}.json"
                    path.write_text(
                        json.dumps(order.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    queue_file = str(path)
                order = store.update(order.id, status="approved", queue_file=queue_file)
                actions.append(
                    {
                        "method": "sendMessage",
                        "payload": {
                            "chat_id": _chat_id(order.buyer_id),
                            "text": f"✅ Заявка {order.id} одобрена. Пост выйдет в «{order.channel_id}» по тарифу {order.tariff}.",
                        },
                    }
                )
                actions.append(
                    {
                        "method": "sendMessage",
                        "payload": {
                            "chat_id": _chat_id(admin_chat_id),
                            "text": f"Заявка {order.id} одобрена, файл: {queue_file or '—'}",
                        },
                    }
                )
            else:
                order = store.update(order.id, status="rejected")
                actions.append(
                    {
                        "method": "sendMessage",
                        "payload": {
                            "chat_id": _chat_id(order.buyer_id),
                            "text": f"❌ Заявка {order.id} отклонена. Напишите в поддержку, если нужен возврат.",
                        },
                    }
                )
            return actions

    # --- платежи ---
    pre_checkout = update.get("pre_checkout_query") or {}
    if pre_checkout:
        parsed = parse_payload(str(pre_checkout.get("invoice_payload") or ""))
        store_order = store.by_payload(str(pre_checkout.get("invoice_payload") or ""))
        ok = parsed is not None and store_order is not None
        actions.append(
            {
                "method": "answerPreCheckoutQuery",
                "payload": {
                    "pre_checkout_query_id": pre_checkout.get("id"),
                    "ok": ok,
                    **({} if ok else {"error_message": "Заказ не найден"}),
                },
            }
        )
        return actions
    payment = update.get("message", {}).get("successful_payment") if isinstance(update.get("message"), dict) else None
    if payment:
        payload = str(payment.get("invoice_payload") or "")
        order = store.by_payload(payload)
        chat_id = (update.get("message") or {}).get("chat", {}).get("id")
        if order is None:
            return actions
        order = store.update(
            order.id,
            status="awaiting_text",
            paid_at=_now_iso(),
            payment_charge_id=str(payment.get("telegram_payment_charge_id") or ""),
        )
        actions.append(
            {
                "method": "sendMessage",
                "payload": {
                    "chat_id": chat_id,
                    "text": "Оплата получена ✅ Пришлите текст рекламного поста одним сообщением.",
                    "reply_markup": {"force_reply": True, "input_field_placeholder": "Текст поста"},
                },
            }
        )
        if admin_chat_id:
            actions.append(
                {
                    "method": "sendMessage",
                    "payload": {
                        "chat_id": _chat_id(admin_chat_id),
                        "text": f"💰 Оплата: {order.amount} ⭐ · заказ {order.id} · канал {order.channel_id}",
                    },
                }
            )
        return actions

    return actions


def _moderation_keyboard(order_id: str) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Одобрить", "callback_data": f"adok:{order_id}"},
                {"text": "❌ Отклонить", "callback_data": f"adno:{order_id}"},
            ]
        ]
    }


def ad_order_to_post(order: AdOrder, text: Optional[str] = None) -> GeneratedPost:
    """Одобренная заявка → GeneratedPost для публикатора Telegram."""
    body = str(text if text is not None else order.ad_text or "").strip()
    if not body:
        raise MonetizationError(f"заявка {order.id}: пустой текст поста")
    return GeneratedPost(
        id=f"ad-{order.id}",
        channel_id=order.channel_id,
        cluster_id="",
        format="story",
        text=body,
        hashtags=[],
        sources=[],
        meta={
            "ad_order_id": order.id,
            "ad_tariff": order.tariff,
            "ad_amount": order.amount,
            "ad_buyer": order.buyer_id,
        },
    )


def _chat_id(value: Any) -> Any:
    text = str(value or "")
    return int(text) if text.lstrip("-").isdigit() else text


def _is_admin(user_id: str, admin_chat_id: str) -> bool:
    if not admin_chat_id:
        return False
    return str(user_id) == str(admin_chat_id).lstrip("-") or str(user_id) == str(admin_chat_id)


def _bot_api(token: str, method: str, payload: Dict[str, Any], api_base: str = API_BASE) -> Dict[str, Any]:
    """Один вызов Bot API (stdlib urllib); ошибки → MonetizationError."""
    url = f"{api_base.rstrip('/')}/bot{token}/{method}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise MonetizationError(f"{method}: HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MonetizationError(f"{method}: сеть недоступна: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    if isinstance(data, dict) and not data.get("ok"):
        raise MonetizationError(f"{method}: {data.get('description') or 'ok=false'}")
    return data if isinstance(data, dict) else {}


def refund_star_payment(
    token: str,
    user_id: Any,
    payment_charge_id: str,
    api_base: str = API_BASE,
) -> Dict[str, Any]:
    """Возврат Stars за заявку (refundStarPayment).

    Нужен, если заявку отклонили после оплаты. ``payment_charge_id`` хранится
    в заявке (``telegram_payment_charge_id``).
    """
    if not payment_charge_id:
        raise MonetizationError("нет payment_charge_id: возврат невозможен")
    return _bot_api(
        token,
        "refundStarPayment",
        {"user_id": int(user_id) if str(user_id).isdigit() else user_id, "telegram_payment_charge_id": str(payment_charge_id)},
        api_base=api_base,
    )


# ---------------------------------------------------------------------------
# Long-polling бот
# ---------------------------------------------------------------------------


class AdSalesBot:
    """Бот приёма рекламных заказов (long-polling, stdlib urllib)."""

    def __init__(
        self,
        token: str,
        store: AdOrderStore,
        offers: Dict[str, ChannelOffer],
        admin_chat_id: str = "",
        queue_dir: Optional[Path] = None,
        *,
        api_base: str = API_BASE,
        timeout: float = 25.0,
    ) -> None:
        if not token:
            raise MonetizationError("не задан TELEGRAM_BOT_TOKEN")
        self.token = token
        self.store = store
        self.offers = offers
        self.admin_chat_id = str(admin_chat_id or "")
        self.queue_dir = queue_dir
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.offset = 0

    def _api(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.api_base}/bot{self.token}/{method}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise MonetizationError(f"{method}: HTTP {exc.code}: {detail}") from exc
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            return {}
        if isinstance(data, dict) and not data.get("ok"):
            raise MonetizationError(f"{method}: {data.get('description') or 'ok=false'}")
        return data if isinstance(data, dict) else {}

    def poll_once(self, timeout: int = 25) -> int:
        data = self._api(
            "getUpdates",
            {
                "offset": self.offset,
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query", "pre_checkout_query"],
            },
        )
        updates = data.get("result") or []
        processed = 0
        for update in updates:
            if isinstance(update, dict) and update.get("update_id"):
                self.offset = max(self.offset, int(update["update_id"]) + 1)
            try:
                actions = plan_update_actions(
                    update,
                    self.store,
                    self.offers,
                    admin_chat_id=self.admin_chat_id,
                    queue_dir=self.queue_dir,
                )
            except Exception as exc:  # update не должен ронять бота
                logger.warning("Ad-бот: ошибка обработки update: %s", exc)
                continue
            for action in actions:
                try:
                    self._api(action["method"], action["payload"])
                    processed += 1
                except MonetizationError as exc:
                    logger.warning("Ad-бот: %s не выполнен: %s", action["method"], exc)
        return processed
