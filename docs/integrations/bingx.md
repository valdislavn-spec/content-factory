# BingX: что есть на GitHub + бесплатные рыночные данные

Смотрел 08.11.2026. Два вывода: (1) у BingX живая официальная экосистема на
GitHub, (2) публичный API работает **без ключа** — отличный бесплатный источник
котировок для постов (в отличие от Twelve Data, где нужен ключ).

## Официальное (org BingX-API)

| Репозиторий | Что это | Полезность для нас |
|---|---|---|
| [BingX-API/BingX-swap-api-doc](https://github.com/BingX-API/BingX-swap-api-doc) | официальная документация Swap API | справочник по эндпоинтам |
| [BingX-API/docs](https://github.com/BingX-API/docs) | полная дока (HTML) | сверка параметров |
| [BingX-API/api-ai-skills](https://github.com/BingX-API/api-ai-skills) | **29 AI-скиллов** для Claude Code/Cursor/Codex: market-данные, спот, фьючерсы, copy trading, аккаунт | можно поставить read-only market-скиллы; trade-скиллы — только с ключом, на прод не ставить |

## SDK/клиенты (community)

| Язык | Репозиторий | Заметки |
|---|---|---|
| Python | [Ming119/bingX-connector-python](https://github.com/Ming119/bingX-connector-python) | простой коннектор, 34★ |
| Python | [niewiemczego/python-bingx](https://github.com/niewiemczego/python-bingx) | HTTP+WebSocket, 18★ |
| Python | [amirinsight/py-bingx](https://github.com/amirinsight/py-bingx) | перпетуалы, автоматизация |
| Go | [tigusigalpa/bingx-go](https://github.com/tigusigalpa/bingx-go) | полный SDK, 43★ |
| C#/.NET | [JKorf/BingX.Net](https://github.com/JKorf/BingX.Net) | typed models, 22★ |
| PHP | [tigusigalpa/bingx-php](https://github.com/tigusigalpa/bingx-php) | Laravel-интеграция |
| TypeScript | [singlesly/bingx-api](https://github.com/singlesly/bingx-api) | TS-клиент |

## Боты и контент

| Репозиторий | Что | Брать ли |
|---|---|---|
| [Drakkar-Software/OctoBot-Market-Making](https://github.com/Drakkar-Software/OctoBot-Market-Making) | маркет-мейкинг для MEXC/Bitmart/BingX и 15+ бирж | только если своя ликвидность/стратегия |
| [subaquatic-pierre/raderbot](https://github.com/subaquatic-pierre/raderbot) | Rust HFT-бот под BingX WebSocket | для экспериментов, не для контента |
| [NINJA0423/tradingview-bingx-bot](https://github.com/NINJA0423/tradingview-bingx-bot) | вебхук TradingView → ордера BingX | если торгуем по сигналам |
| [lowweihong/crypto_exchange_news_crawler](https://github.com/lowweihong/crypto_exchange_news_crawler) | краулер анонсов бирж, **включая BingX** | 🔥 источник новостей для крипто-канала |
| volume-боты (напр. 9jacoderYT/bingx-professional-trading-volume-bot) | накрутка объёма | ❌ нарушение ToS/риск бана — не трогаем |

## Наша интеграция: котировки без ключа

`content_factory/integrations/bingx.py` — публичный API, без ключей и подписи:

```bash
# снапшот для поста (теперь работает без TWELVEDATA_API_KEY)
python scripts/market_data.py --snapshot

# JSON/свечи
python scripts/market_data.py --symbols BTC/USD,ETH/USD --source bingx --format json
python scripts/market_data.py --symbols BTC/USD --source bingx --series 1h --output 24
```

Эндпоинты (проверены): `open-api.bingx.com/openApi/swap/v2/quote/ticker`,
`.../quote/klines`, `/openApi/spot/v1/ticker/24hr`. Пары USDT-маржинальные
(`BTC-USDT`); модуль сам конвертирует `BTC/USD → BTC-USDT`. Форматтер общий с
Twelve Data (`format_snapshot`), поэтому строка для поста выглядит одинаково:

```
Markets: ₿ BTC 76 050.40 (+0.27%) · Ξ ETH 2 240.96 (+0.02%) · ◎ SOL 89.65 (−0.12%)
```

Тесты: `tests/test_bingx.py` (7 тестов, без сети). CLI `--source auto` выбирает
BingX для крипты, Twelve Data — для форекса/акций/если есть ключ.

## Партнёрка — напоминание

BingX Affiliate (до 50% rev-share, ежедневные выплаты) **не работает для
пользователей США/Канады/UK/Singapore/Netherlands/Hong Kong** (Restricted
Jurisdictions) → для US-аудитории EN-канала не подходит, только ES/ЛатАм.
Детали: [`bingx-analysis.md`](../monetization/bingx-analysis.md).

## Что можно сделать дальше

1. Подключить `crypto_exchange_news_crawler` как источник анонсов BingX
   (листинги/делистинги = хорошие новости для крипто-канала).
2. Официальные AI-skills поставить только read-only (market/spot/coinm), trade —
   с отдельным ключом и на тестовом аккаунте.
3. Рыночный блок в посты: 1 запрос/пост к BingX, ключ не нужен; Twelve Data
   оставить для форекса/акций и индикаторов.
