# Гео-блок UA: все публичные workers

Дата: 2026-11-25. Запрос: запретить всё из Украины (UA) на всех сервисах.

## Что сделано

На уровне кода воркеров: `request.cf.country === "UA"` → **403 Forbidden**
до любой логики и записи в БД. Задеплоено в Cloudflare (аккаунт `valdislav-n`).

| Worker | UA-блок | Проверка |
|---|---|---|
| links-tracker | ✅ | /r/tg-es-crypto → 302 на @TechnologiesNews01 |
| cf-subscribe | ✅ | GET / → 200 `{"ok":true,"service":"cf-subscribe"}` |
| cf-unsubscribe | ✅ | GET / → 400 «Invalid unsubscribe link» (ожидаемо без `?e=&s=`) |
| discord-oauth | ✅ | GET / → 200 |
| github-cron | ✅ | GET / → 200, repo/слоты на месте |
| price-alerts | ✅ | /health → 200, `last_trigger` тикает |
| kalshi-mcp-proxy | ✅ | /health → 200 |
| telegram-proxy | ✅ | GET / → страница Telegram (прокси работает) |
| brevo-bridge | ✅ | workers.dev отключён (вызывается изнутри), 404 — норма |
| tcp-tunnel | ✅ | GET / → 403 (нужен ключ туннеля — так и было) |
| stars-pay | ✅ | GET / → 200 «cf-stars online» |

Скрипты после деплоя: bindings и секреты сохранены (D1/KV/plain_text на месте,
secret_text остаются на воркере).

## Не тронуты (и почему)

| Worker | Причина |
|---|---|
| tg-cron | cron-воркер (по расписанию), минифицированный бандл; публичного трафика нет |
| growth-bot | только webhook от Telegram; блок по стране рискует отбросить апдейты |
| do-redis-growth | внутренний Durable Object-стор, доступен только по service binding |

Если нужно «совсем всё» — эти три тоже можно закрыть, но защиты от посетителей
это не даёт, а риск для пайплайна/бота ненулевой.

## Ручная проверка

```bash
# должно вернуть 403 только с украинского IP
curl -s -o /dev/null -w "%{http_code}\n" https://links-tracker.valdislav-n.workers.dev/r/tg-es-crypto
```

Для проверки из UA нужен украинский прокси/VPN — с текущей сети видно только
разрешённый ответ (302), что подтверждает, что блок не ломает остальной трафик.
