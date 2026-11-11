"""Telegram-бот с оплатой через PayPal Checkout.

Схема:
1. Пользователь нажимает «Купить» в боте.
2. Бот создаёт PayPal Order и отправляет ссылку на оплату.
3. PayPal возвращает пользователя на /paypal/return.
4. Бот захватывает платёж (capture) и выдаёт доступ.
5. Дублирующий webhook /paypal/webhook страхует от потери return-запроса.

Это учебный пример: замените in-memory хранилище на SQLite/Postgres,
а проверку webhook — на продакшн-секрет.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from typing import Any

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paypal-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_BASE = os.getenv("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
PRICE = os.getenv("PRICE", "9.99")
CURRENCY = os.getenv("CURRENCY", "USD")
PRODUCT_NAME = os.getenv("PRODUCT_NAME", "Доступ к боту")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

RETURN_URL = f"{PUBLIC_BASE_URL}/paypal/return"
CANCEL_URL = f"{PUBLIC_BASE_URL}/paypal/cancel"

router = Router()
bot: Bot | None = None
http: httpx.AsyncClient | None = None

# Демо-хранилище. В проде: таблица orders(order_id, user_id, status, capture_id).
_orders: dict[str, dict[str, Any]] = {}
_token: tuple[str, float] | None = None


def paypal_client() -> httpx.AsyncClient:
    global http
    if http is None:
        http = httpx.AsyncClient(base_url=PAYPAL_BASE, timeout=30.0)
    return http


async def paypal_token() -> str:
    """OAuth2 client_credentials, кэш до истечения."""
    global _token
    if _token and _token[1] > time.time() + 60:
        return _token[0]
    client = paypal_client()
    response = await client.post(
        "/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    data = response.json()
    _token = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
    return _token[0]


async def paypal_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {await paypal_token()}",
        "Content-Type": "application/json",
    }


async def create_order(user_id: int) -> dict[str, Any]:
    """Создаёт PayPal Order и запоминает, кому он принадлежит."""
    client = paypal_client()
    reference = f"tg-{user_id}-{secrets.token_hex(4)}"
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference,
                "custom_id": str(user_id),
                "description": PRODUCT_NAME,
                "amount": {"currency_code": CURRENCY, "value": PRICE},
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "return_url": RETURN_URL,
                    "cancel_url": CANCEL_URL,
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                }
            }
        },
    }
    response = await client.post(
        "/v2/checkout/orders",
        json=payload,
        headers={**await paypal_headers(), "PayPal-Request-Id": reference},
    )
    response.raise_for_status()
    order = response.json()
    _orders[order["id"]] = {
        "user_id": user_id,
        "reference": reference,
        "status": "created",
        "capture_id": None,
    }
    return order


def approve_url(order: dict[str, Any]) -> str:
    for link in order.get("links", []):
        if link.get("rel") in {"payer-action", "approve"}:
            return link["href"]
    raise RuntimeError("PayPal не вернул ссылку на оплату")


async def capture_order(order_id: str) -> dict[str, Any] | None:
    """CAPTURE заказа. Идемпотентно по локальному статусу."""
    info = _orders.get(order_id)
    if info and info.get("status") == "paid":
        return None
    client = paypal_client()
    response = await client.post(
        f"/v2/checkout/orders/{order_id}/capture",
        headers=await paypal_headers(),
    )
    if response.status_code >= 400:
        log.error("capture %s failed: %s %s", order_id, response.status_code, response.text[:500])
        return None
    data = response.json()
    if data.get("status") == "COMPLETED":
        await mark_paid(order_id, data)
    return data


async def mark_paid(order_id: str, capture: dict[str, Any]) -> None:
    """Выдаёт доступ один раз. Здесь — сообщение; в проде — запись в БД."""
    info = _orders.get(order_id)
    if not info or info.get("status") == "paid":
        return
    info["status"] = "paid"
    capture_id = None
    try:
        capture_id = capture["purchase_units"][0]["payments"]["captures"][0]["id"]
    except (KeyError, IndexError, TypeError):
        pass
    info["capture_id"] = capture_id
    log.info("paid order=%s user=%s capture=%s", order_id, info["user_id"], capture_id)
    if bot:
        try:
            await bot.send_message(
                info["user_id"],
                f"✅ Оплата получена. Доступ к «{PRODUCT_NAME}» открыт.\n"
                f"Заказ: {order_id}",
            )
        except Exception:
            log.exception("не удалось отправить сообщение пользователю")


async def verify_webhook(request: web.Request, raw: bytes) -> bool:
    """Проверка подписи webhook. Без PAYPAL_WEBHOOK_ID пропускается (только для локального теста)."""
    if not PAYPAL_WEBHOOK_ID:
        log.warning("PAYPAL_WEBHOOK_ID не задан — подпись webhook не проверяется")
        return True
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return False
    payload = {
        "auth_algo": request.headers.get("paypal-auth-algo", ""),
        "cert_url": request.headers.get("paypal-cert-url", ""),
        "transmission_id": request.headers.get("paypal-transmission-id", ""),
        "transmission_sig": request.headers.get("paypal-transmission-sig", ""),
        "transmission_time": request.headers.get("paypal-transmission-time", ""),
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    client = paypal_client()
    response = await client.post(
        "/v1/notifications/verify-webhook-signature",
        json=payload,
        headers=await paypal_headers(),
    )
    if response.status_code >= 400:
        return False
    return response.json().get("verification_status") == "SUCCESS"


async def paypal_return(request: web.Request) -> web.Response:
    order_id = request.query.get("token", "")
    if not order_id:
        return web.Response(status=400, text="Нет token заказа")
    try:
        await capture_order(order_id)
    except Exception:
        log.exception("return capture failed")
    return web.Response(text="Оплата обрабатывается. Вернись в Telegram.")


async def paypal_cancel(_: web.Request) -> web.Response:
    return web.Response(text="Оплата отменена. Вернись в Telegram.")


async def paypal_webhook(request: web.Request) -> web.Response:
    raw = await request.read()
    if not await verify_webhook(request, raw):
        return web.Response(status=400, text="bad signature")
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return web.Response(status=400, text="bad json")
    event_type = event.get("event_type", "")
    resource = event.get("resource", {}) or {}
    if event_type == "CHECKOUT.ORDER.APPROVED":
        await capture_order(resource.get("id", ""))
    elif event_type == "PAYMENT.CAPTURE.COMPLETED":
        order_id = (
            resource.get("supplementary_data", {})
            .get("related_ids", {})
            .get("order_id", "")
        )
        if order_id:
            await mark_paid(order_id, {"purchase_units": []})
    return web.Response(text="ok")


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        f"Привет! Здесь можно купить «{PRODUCT_NAME}» за {PRICE} {CURRENCY}.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Купить", callback_data="buy")]]
        ),
    )


@router.callback_query(F.data == "buy")
async def buy(callback: CallbackQuery) -> None:
    await callback.answer("Создаю заказ…")
    try:
        order = await create_order(callback.from_user.id)
        url = approve_url(order)
    except Exception:
        log.exception("create order failed")
        if callback.message:
            await callback.message.answer("Не удалось создать заказ. Попробуй позже.")
        return
    if callback.message:
        await callback.message.answer(
            f"Заказ на {PRICE} {CURRENCY} создан. Нажми «Оплатить PayPal»:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Оплатить PayPal", url=url)]]
            ),
        )


async def start_web() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/paypal/return", paypal_return)
    app.router.add_get("/paypal/cancel", paypal_cancel)
    app.router.add_post("/paypal/webhook", paypal_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
    await site.start()
    log.info("HTTP server on :%s", WEB_PORT)
    return runner


async def main() -> None:
    global bot
    missing = [
        name
        for name, value in {
            "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
            "PAYPAL_CLIENT_ID": PAYPAL_CLIENT_ID,
            "PAYPAL_CLIENT_SECRET": PAYPAL_CLIENT_SECRET,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("Заполни .env: " + ", ".join(missing))
    bot = Bot(TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    runner = await start_web()
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        if http:
            await http.aclose()


if __name__ == "__main__":
    asyncio.run(main())
