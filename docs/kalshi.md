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

## Приватные данные (опционально)

1. Kalshi → Account & security → API Keys → Create Key (Ed25519).
2. Сохранить private key PEM и Key ID.
3. В GitHub Secrets: `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY` (PEM).
4. В коде: `KalshiClient(key_id=..., private_key_pem=...)`; для подписи нужен
   пакет `cryptography` (`pip install cryptography`).

## Монетизация

У Kalshi есть партнёрские/affiliate-программы — если получите реферальную
ссылку, впишите её в `affiliate_url` канала: скрипт добавит её в подпись с
пометкой `Ad ·` (требование FTC для США). Если ссылки нет — остаётся обычная
ссылка на `kalshi.com/markets`.

## Ограничения

- Дайджест берёт **open**-рынки, сортирует по объёму; фильтры — по ключевым
  словам в вопросе и префиксу тикера.
- Данные публичные, но лимиты запросов у Kalshi есть — дозируйте (2 поста/день).
- Не инвестиционная рекомендация: подпись включается в каждый пост.
- MCP-коннектор Kalshi (официальный) можно подключить к ассистенту отдельно —
  он требует OAuth через браузер, для завода не нужен.
