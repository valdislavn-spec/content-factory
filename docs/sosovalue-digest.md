# SoSoValue digest → Telegram (6 тем)

Ежедневные аналитические посты в каналы контент-фабрики на данных SoSoValue:
потоки ETF, секторальные индексы, макро/ликвидность, сентимент, деривативы,
TVL экосистем. Скрипт: `scripts/sosovalue_digest.py`, конфиг:
`config/sosovalue.yaml`, модуль: `content_factory/sosovalue.py`, workflow:
`.github/workflows/sosovalue-digest.yml`.

## Режим по умолчанию: один сводный пост

Пайплайн публикует **один пост в день** в 07:00 UTC на канал: шесть строк —
flows, sectors, macro, sentiment, derivatives, TVL — около 700 знаков, влезает
в лимит 1200 символов канала. Включается опциями источника `summary: true` и
`hour_utc: 7`; `summary: false` возвращает пофайловый режим (одна тема в час).
Отдельный `scripts/sosovalue_digest.py` по-прежнему умеет публиковать темы
по отдельности — это ручной/резервный путь.

## Что публикуется

| Тема | Ключ | Что внутри |
|---|---|---|
| Институциональные потоки | `flows` | BTC/ETH ETF: чистый приток за 7 дней и за день, AUM, серия дней оттока/притока |
| Секторальные индексы | `sectors` | Топ-3 из 13 индексов SSI по 7-дневной доходности (7д / 24ч / 1м) |
| Макро и ликвидность | `macro` | SOFR, TGCR, ON-RRP, ближайший FOMC (диапазон + вероятность), календарь |
| Сентимент | `sentiment` | Crypto Fear & Greed + 3 самых горячих сектора за 24ч (доминация) |
| Деривативы | `derivatives` | Funding Binance/OKX/Bybit, средний за 7 дней, открытый интерес и его 7д-динамика, long/short |
| Экосистемы | `ecosystems` | TVL Ethereum/Solana/Base/Sui/Aptos и рост за 7 дней, лидер роста |

Каждая тема уходит в `crypto-news` (EN) и `crypto-es` (ES): рендеры
мультиязычные, тексты собираются детерминированно, без LLM.

## Расписание

`config/sosovalue.yaml` задаёт час UTC для каждой темы (7, 9, 11, 14, 16, 18).
Cron workflow запускается каждый час в :10 и публикует только темы, у которых
`hour_utc` совпал с текущим часом. Повторный запуск в тот же день ничего не
дублирует: состояние в `data/sosovalue_state.json` (ключ `дата → канал:тема`).

## Запуск

```bash
export SOSO_API_KEY=...
python scripts/sosovalue_digest.py --all --dry-run        # превью всех тем
python scripts/sosovalue_digest.py --theme flows --dry-run
python scripts/sosovalue_digest.py --theme flows --live   # отправка
```

Секреты GitHub: `SOSO_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID_CRYPTO_NEWS`, `TELEGRAM_CHAT_ID_CRYPTO_ES`
(chat_id также читается из `config/channels.*.yaml`).

## Источники данных и ограничения

* SoSoValue v1, заголовок `x-soso-api-key`. Ключ: консоль
  https://sosovalue.com/ru/developer/console/keys.
* **Соцданных нет в API.** Социальный объём/сентимент по секторам платформа
  показывает в интерфейсе, но в публичном API таких эндпоинтов нет; в посте
  `sentiment` остаются Fear & Greed и сектора по 24ч-изменению и доминации.
* **Ликвидаций нет в API.** В каталоге `/analyses` 30 графиков, ликвидаций
  среди них нет — в посте `derivatives` строка об этом честно пишется.
* **TVL по сетям.** График `/analyses/tvl_of_different_type_of_chain` отдаёт
  только all/ethereum/layer_2/others и **не обновлялся с 2024-11-14**, поэтому
  TVL по сетям берётся из DefiLlama (`api.llama.fi`), источник указан в данных
  как `tvl_source: defillama`. Отключить: `TVL_SOURCE=off`.
* Квоты: Free — 100 запросов/мин и 10 000/мес. Один прогон всех тем — около
  19 запросов SoSoValue + 6 DefiLlama; при 6 прогонах в день это ~3.5 тыс.
  запросов/мес, то есть в лимит укладывается.

## Проверка

```bash
.venv/bin/python -m pytest tests/test_sosovalue_digest.py -q
```

Тесты без сети: рендеры всех шести тем на EN/ES, формат сумм, сортировка TVL,
неизвестная тема, выбор темы по часу.

## Если падает TLS на macOS

Системный Python 3.9 (LibreSSL) не проверяет цепочку Cloudflare:

```bash
export SOSO_CA_BUNDLE=/etc/ssl/cert.pem
```

На Ubuntu/GitHub Actions и в Dify (Python 3.12) это не нужно.

## Встраивание в основной пайплайн (режим по умолчанию)

Темы подключены как обычный источник type: sosovalue в
config/channels.en.yaml (crypto-news) и config/channels.es.yaml (crypto-es):

    - id: soso-daily
      type: sosovalue
      name: SoSoValue daily
      weight: 1.25
      options:
        language: en          # es для испанского канала
        symbols: [BTC, ETH]
        country_code: US
        themes: auto          # или список: [flows, sectors]
        trust: true
        cache_ttl: 1800

Адаптер content_factory/sources/sosovalue.py на каждом прогоне отдаёт только
темы, чей UTC-час наступил (7/9/11/14/16/18), и кладёт в статью
meta["prewritten_html"] — готовый детерминированный блок с цифрами.
pipeline.generate_posts такие статьи публикует как есть (format digest),
не прогоняя через анализ и LLM: цифры и подписи не переписываются, хвост
канала (market line, хэштеги) добавляется как обычно.

Почему так: обычный путь сжимает статью до 200-символьного summary и терял
ETH/AUM/детали; prewritten-путь сохраняет все строки блока. LLM остаётся
только для новостных сюжетов — там он ограничен валидатором цифр.

Проверено на живом прогоне: 6 статей → 6 постов (prewritten=6) для
crypto-news, EN. Повторный запуск в тот же час не дублирует: URL содержит
?theme=...&d=YYYY-MM-DD, а состояние публикаций ведёт storage фабрики.

Отдельный scripts/sosovalue_digest.py остаётся для ручного прогона,
превью и как запасной путь без основного планировщика.
