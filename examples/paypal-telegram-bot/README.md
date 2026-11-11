# Telegram-бот с PayPal Checkout

Пример на **aiogram 3** + **aiohttp** + **PayPal Orders API v2**.

## Важно

- **Telegram Payments не поддерживает PayPal** как провайдера. Поэтому оплата
  идёт через внешнюю ссылку PayPal Checkout, а бот получает подтверждение по
  `return_url` и/или webhook.
- PayPal в РФ не работает. Пример — для зарубежного аккаунта.
- Это учебный пример: in-memory заказы и выдача доступа в сообщении. В проде
  нужны БД, идемпотентность и проверка webhook.

## Установка

```bash
cd examples/paypal-telegram-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# заполни .env
```

## Публичный HTTPS

PayPal не примет `localhost` как `return_url`. Нужен публичный адрес:

```bash
# вариант 1: Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8080

# вариант 2: ngrok
ngrok http 8080
```

Полученный `https://...` впиши в `PUBLIC_BASE_URL`.

## Запуск

```bash
.venv/bin/python bot.py
```

## Настройка PayPal

1. [developer.paypal.com](https://developer.paypal.com/) → **Apps & Credentials**.
2. Создай **Sandbox** app, возьми `Client ID` и `Secret`.
3. Включи **Webhooks**:
   - URL: `https://<твой-домен>/paypal/webhook`
   - события: `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED`
   - скопируй **Webhook ID** в `.env` (`PAYPAL_WEBHOOK_ID`).
4. Для теста создай sandbox personal account и оплати им.

## Как проверить

1. `/start` → «Купить».
2. Бот пришлёт кнопку **Оплатить PayPal**.
3. Оплати sandbox-аккаунтом.
4. После return бот захватит платёж и пришлёт «Оплата получена».
5. Проверь, что повторный webhook не выдаёт доступ второй раз.

## Что менять для прода

- `_orders` → SQLite/Postgres, уникальный индекс по `order_id`.
- `mark_paid` → запись в БД + выдача доступа; проверять сумму/валюту.
- Webhook: всегда проверять подпись (`PAYPAL_WEBHOOK_ID`), не отключать.
- Добавить `PayPal-Request-Id` на capture (идемпотентность).
- Логировать `capture_id`, `custom_id`, `reference_id`.
- Не хранить секреты в коде; только `.env`/secrets manager.
- Для подписок использовать `Subscriptions API`, не разовый CAPTURE.

## Официальные библиотеки

- Python: [paypal/PayPal-Python-Server-SDK](https://github.com/paypal/PayPal-Python-Server-SDK)
- TypeScript: [paypal/PayPal-TypeScript-Server-SDK](https://github.com/paypal/PayPal-TypeScript-Server-SDK)
- JS/React: [paypal/paypal-js](https://github.com/paypal/paypal-js)

В этом примере используется прямой REST через `httpx`: так проще контролировать
capture, webhook и идемпотентность, чем через неполный codegen-SDK.
