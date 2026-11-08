# Twelve Data — рыночные данные для постов

Официальная библиотека: <https://github.com/twelvedata/twelvedata-python>.
В заводе подключена тонкая обёртка над REST API без новых зависимостей:
[`content_factory/integrations/twelvedata.py`](../../content_factory/integrations/twelvedata.py)
(при желании можно перейти на официальный `TDClient` — он умеет WebSocket,
индикаторы и fundamentals).

## Зачем

- рыночный блок в постах крипто-канала (`Markets: ₿ BTC $75 625.00 (−5.99%) · …`);
- котировки для финансовых/спортивных сюжетов (USD, индексы, акции, форекс);
- «свежие цифры» к дайджестам вместо ручного ввода.

## Ключ (бесплатно)

1. Зарегистрироваться: <https://twelvedata.com/pricing> (Free plan).
2. Скопировать API key → в `.env`:

   ```bash
   TWELVEDATA_API_KEY=...
   ```

3. Бесплатный план: **800 кредитов/день, 8 запросов/минуту** — для завода с
   5-6 постами в сутки хватает с запасом (1 quote = 1 кредит).

## Использование

```bash
cd content-factory

# снапшот рынка строкой для поста
../tools/markitdown-venv/bin/python scripts/market_data.py --snapshot

# конкретные символы / JSON
../tools/markitdown-venv/bin/python scripts/market_data.py --symbols BTC/USD,ETH/USD,SOL/USD
../tools/markitdown-venv/bin/python scripts/market_data.py --symbols AAPL --format json

# свечи (1h, 24 шт.)
../tools/markitdown-venv/bin/python scripts/market_data.py --symbols BTC/USD --series 1h --output 24
```

Из кода:

```python
from content_factory.integrations.twelvedata import TwelveDataClient, format_snapshot, build_market_note

client = TwelveDataClient()          # ключ из TWELVEDATA_API_KEY
quotes = client.quotes(["BTC/USD", "ETH/USD"])
print(format_snapshot(quotes))       # готовая строка для поста
note = build_market_note()           # "Markets: …" для крипто-канала
```

## Ограничения

- Free plan: 800 кредитов/день, 8 запросов/мин; превышение → HTTP 429
  (`TwelveDataError`, CLI вернёт код 1).
- Символы крипты — `BTC/USD`, форекс — `EUR/USD`, акции — `AAPL` (+ `exchange=NASDAQ`
  при неоднозначности).
- Ключ не коммитится: только `.env` (chmod 600, в gitignore).

## Что можно добавить дальше

- вставить `build_market_note()` в генерацию постов крипто-канала
  (строка в конце поста, 1 запрос/пост = 1 кредит);
- для спортивных каналов — курсы валют/индексы в аналитических постах;
- WebSocket-стрим для real-time алертов (через официальную библиотеку).
