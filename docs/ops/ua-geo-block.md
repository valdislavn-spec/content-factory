# Гео-блок UA: все воркеры аккаунта

Дата: 2026-11-26. Запрос: запретить всё из Украины (UA) на всех сервисах.

## Итог: 14 из 14 воркеров

Во всех воркерах на входе стоит проверка `request.cf.country === "UA"` →
**403 Forbidden** до любой логики, логов и записи в БД.

| Worker | UA-блок | Проверка после деплоя |
|---|---|---|
| links-tracker | ✅ | `/r/tg-es-crypto` → 302 на @TechnologiesNews01 |
| cf-subscribe | ✅ | GET / → 200 |
| cf-unsubscribe | ✅ | 400 на пустой токен (норма) |
| discord-oauth | ✅ | GET / → 200 |
| github-cron | ✅ | GET / → 200, repo/слоты на месте |
| price-alerts | ✅ | `/health` → 200, `last_trigger` тикает |
| kalshi-mcp-proxy | ✅ | `/health` → 200 |
| telegram-proxy | ✅ | проксирует api.telegram.org (Telegram-страница) |
| brevo-bridge | ✅ | workers.dev отключён, вызывается изнутри (404 — норма) |
| tcp-tunnel | ✅ | 403 без ключа туннеля (норма) |
| stars-pay | ✅ | GET / → 200 «cf-stars online» |
| growth-bot | ✅ | GET / → 200 «ok»; 2 модуля (logic.js + worker.js) сохранены |
| tg-cron | ✅ | health-JSON тот же, cron `*/15 * * * *` и D1/KV bindings целы |
| do-redis-growth | ✅ | 401 без токена (норма); DO-binding `STORAGE` сохранён |

## Как сделано

- Одиночные модули — обёртка `export default { fetch() { if (UA) 403; return orig.fetch() } }`.
- Мульти-модульные (`growth-bot`: logic.js + worker.js; `tg-cron`: tg-cron.js) —
  правился только main-модуль, остальные части и биндинги перезалиты как были.
- `do-redis-growth` — именованный default (`src_default`) обёрнут, класс
  `StorageDurableObject` экспортируется как раньше.
- Секреты не трогались (они живут отдельно от скрипта); проверено, что
  D1/KV/DO/plain_text-биндинги на месте.
- `tg-cron`: cron-триггер `*/15 * * * *` сохранился, health отдаёт тот же JSON.

## Проверка

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://links-tracker.valdislav-n.workers.dev/r/tg-es-crypto
```

С текущей сети (не UA) всё отвечает как раньше — блок не задел нормальный трафик.
403 можно увидеть только с украинского IP/VPN.
