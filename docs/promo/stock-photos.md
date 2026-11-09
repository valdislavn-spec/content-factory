# Фото-API для пинов: статус (09.11.2026)

## Pexels — не подключить
Официальная страница Pexels Developer: **«New API key issuance is currently paused
and cannot be requested»** (проверено 09.11.2026). Ключ получить нельзя.

## Unsplash — блокирует регистрация
`unsplash.com/join` за Cloudflare **Turnstile**: форма зависает на «Verifying…»,
отправка невозможна из автоматизации. Если создать аккаунт/приложение вручную —
ключи (Access Key / Secret Key) выдаются мгновенно на https://unsplash.com/oauth/applications.

## Что подключено вместо: Wikimedia Commons API (бесплатно, без ключа)
`scripts/stock_photos.py` — поиск по Commons, фильтр свободных лицензий
(CC0/PD/CC BY/CC BY-SA), скачивание 1600px, сохранение кредитов в
`docs/assets/photos/credits.json`.

Скачано (реальные фото направлений):
`bali.jpg` (CC BY 4.0), `dubai.jpg` (CC BY-SA 4.0), `lisbon.jpg` (CC BY-SA 4.0),
`europe.jpg` (CC0), `esim.jpg` (CC BY-SA 3.0), `car.jpg` (Public domain),
`flight.jpg` (CC BY-SA 3.0).

## Новый дизайн пинов v4 (фото + оверлей)
`scripts/build_photo_pins.py` → `docs/assets/pins/photo/` (7 пинов):
реальное фото на весь кадр, тёмный градиент для контраста, заголовок ≤6 слов в верхней
трети (белый Playfair + stroke), keyword-пилюля, QR + CTA + «Ad», обязательная атрибуция
фото (автор/лицензия/Wikimedia Commons).

CSV для Pinterest: `docs/pinterest-import-qr.csv` (Media URL → `/assets/pins/photo/…`).

## Альтернативы
- Pixabay API (регистрация, Cloudflare возможен).
- Hugging Face (ключ уже в .env) — AI-фоны.
- Собственный HTML→PNG рендер через headless Chrome (без внешних сервисов).
