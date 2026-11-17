# Growth Funnel publisher

Автопубликация очереди GOODTRAVEL007.

- `queue.json` — очередь и состояние.
- `auto_publish.py` — публикатор Telegram/Pinterest.
- `manual-pins/batch2/` — картинки для Pinterest API.

Workflow: `.github/workflows/growth-funnel.yml`, запуск ежедневно в 09:00 UTC
и вручную через `workflow_dispatch`.

Секреты:

- `TELEGRAM_BOT_TOKEN` — уже используется content-factory;
- `TELEGRAM_API_BASE` — variable;
- `PINTEREST_ACCESS_TOKEN` — production OAuth-токен;
- `PINTEREST_API_BASE` — `https://api.pinterest.com`;
- `PINTEREST_BOARD_ID_BUDGET_TRAVEL`, `PINTEREST_BOARD_ID_CITY_BREAKS`,
  `PINTEREST_BOARD_ID_TRAVEL_IDEAS`.

Пока Pinterest-токен не задан, Pinterest-элементы пропускаются, Telegram
продолжает публиковаться.

## GrowthBot storage

GrowthBot worker больше не использует Cloudflare KV. Состояние хранится в
Redis-совместимом воркере `do-redis-growth` на Durable Objects.

Подробности, проверка и передеплой: [`REDIS.md`](REDIS.md).
