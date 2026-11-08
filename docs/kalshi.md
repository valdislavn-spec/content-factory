# Kalshi: прогнозные рынки в контент-заводе

Интеграция с [Kalshi API](https://docs.kalshi.com/welcome): дайджесты самых
ликвидных prediction-рынков публикуются в каналы сети как отдельные посты.

## Что уже подключено

- `content_factory/integrations/kalshi.py` — клиент Kalshi: публичные рынки
  (без ключа), подпись запросов Ed25519/RSA-PSS для приватных эндпоинтов.
- `scripts/kalshi_digest.py` — собирает рынки по фильтрам и публикует дайджест
  (dry-run по умолчанию).
- `config/kalshi.yaml` — какие каналы получают дайджест, ключевые слова,
  минимальный объём, формат.
- `.github/workflows/kalshi-digest.yml` — расписание 2 раза в день (12:15 и
  21:15 UTC) + ручной запуск с `dry_run`.

## API: что нужно знать

| Что | Значение |
|---|---|
| Публичный base URL | `https://external-api.kalshi.com/trade-api/v2` |
| Demo | `https://external-api.demo.kalshi.co/trade-api/v2` |
| Публичные данные | рынки, серии, события — **без ключа** |
| Приватные | портфель, ордера — нужен API key |
| Подпись | `timestamp + METHOD + path` (без query), Ed25519 или RSA-PSS/SHA-256 |
| Заголовки | `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP`, `KALSHI-ACCESS-SIGNATURE` |

Важно: официальная документация советует `external-api.kalshi.com` — несмотря
на поддомен «elections», там **все** рынки Kalshi. Блокировка `api.elections.kalshi.com`
из локальной сети — нормально; из GitHub Actions запросы проходят.

## Включение

1. Публичные данные работают сразу — ничего не нужно.
2. Проверить dry-run: Actions → **kalshi-digest** → Run workflow →
   `dry_run=true` → смотреть лог с готовыми постами.
3. Включить live: `dry_run=false` вручную или дождаться расписания.
4. При необходимости поменять каналы/ключевые слова в `config/kalshi.yaml`.

## MCP-коннектор (ассистент)

Kalshi отдаёт MCP по адресу `https://api.elections.kalshi.com/mcp`
(Streamable HTTP). С этой машины Kalshi блокируется CloudFront (403), поэтому
подключение идёт через Cloudflare Worker-релей
`https://kalshi-mcp-proxy.valdislav-n.workers.dev/mcp`
(исходник — `infra/kalshi-mcp-proxy/`).

В DSH профиле (`~/.dsh/profiles/desktop/cordis.patch.yml`) добавлен entry
`kalshi-mcp` с `serverName: kalshi`; инструменты видны как
`mcp__kalshi__search_markets`, `mcp__kalshi__get_event_odds` и т.д.
Публичные рыночные инструменты работают без аккаунта. OAuth (портфель и
price-alerts) клиент DSH не поддерживает — для этих данных используйте REST
клиент с API-ключом.

## Приватные данные (опционально)

1. Kalshi → Account & security → API Keys → Create Key (Ed25519).
2. Сохранить private key PEM и Key ID.
3. В GitHub Secrets: `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY` (PEM).
4. В коде: `KalshiClient(key_id=..., private_key_pem=...)`; для подписи нужен
   пакет `cryptography` (`pip install cryptography`).

## Монетизация: реферальная ссылка (раз в день)

Kalshi платит за приглашённых друзей (Referral Program). Ссылка выдаётся в
приложении Kalshi: **Explore → меню → Your rewards → Offers → «Refer a friend»
→ поделиться**. Условия: только US-аккаунты, бонусы зависят от оффера.

Как только ссылка есть — вписать в `config/kalshi.yaml`:

```yaml
affiliate:
  enabled: true
  url: "https://kalshi.com/r/ВАШ_КОД"
  disclosure: "Ad"
  once_per_day: true
  daily_hour_utc: 12   # строка попадает только в утренний дайджест (12:15 UTC)
```

Правила встраивания:
- строка добавляется **не более одного раза в день** — только в дайджест,
  который запускается в `daily_hour_utc` (по умолчанию 12:15 UTC);
- тексты EN/ES задаются в `text_en` / `text_es`, пометка `Ad` обязательна
  (требование FTC для США);
- пустой `url` = выключено, посты идут без ссылки;
- ссылка не попадает в каждый пост канала — только в ежедневный дайджест.

Если вместо реферальной ссылки нужен просто трекинг трафика, можно указать
UTM-ссылку на `kalshi.com/markets` и честно не называть её affiliate.

## Ограничения

- Дайджест берёт **open**-рынки, сортирует по объёму; фильтры — по ключевым
  словам в вопросе и префиксу тикера.
- Данные публичные, но лимиты запросов у Kalshi есть — дозируйте (2 поста/день).
- Не инвестиционная рекомендация: подпись включается в каждый пост.
- MCP-коннектор Kalshi (официальный) можно подключить к ассистенту отдельно —
  он требует OAuth через браузер, для завода не нужен.
