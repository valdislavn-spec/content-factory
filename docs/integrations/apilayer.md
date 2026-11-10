# APILayer: курсы валют и рейсы (10.11.2026)

## Аккаунт

- Платформа: https://app.apilayer.com (аккаунт уже существовал с 25.10.2026,
  email `valdislav.n@gmail.com`).
- Один API-ключ на все API: `APILAYER_KEY` (хранится в `.env` и GitHub Secrets).
- Подписки (Free, 01.12.2026 → дальше помесячно, $0):
  | API | План | Лимит | Endpoint |
  |---|---|---|---|
  | **Exchange Rate** | Free | 100 запросов/мес | `GET https://api.apilayer.net/exchangerate/v1/latest` |
  | **Aviationstack** | Free | 100 запросов/мес | `GET https://api.apilayer.net/aviationstack/v1/flights` |

Бесплатный Exchange Rate отдаёт базу **EUR** (смена base — платная), поэтому
USD конвертируем через курс `rates.USD` (USD за 1 EUR).

## Доступ (важно)

- Cloudflare на `api.apilayer.net` режет часть IP: локальный Mac и Cloudflare
  Worker получают **403**.
- **GitHub Actions-раннеры проходят** (проверено: FX и flights вернули 200).
- Локально: `APILAYER_SOCKS_PROXY=socks5h://127.0.0.1:1080` — клиент ходит
  через `curl` и Xray-прокси.

```bash
# локальная проверка
python scripts/apilayer_check.py
# в CI/на раннере — без APILAYER_SOCKS_PROXY
APILAYER_KEY=... python scripts/apilayer_check.py
```

## Где используется

- `content_factory/integrations/apilayer.py` — клиент (`latest_rates`,
  `usd_to_eur`, `flights`).
- `scripts/fediverse_mix.py` — в travel-постах цена показывается в USD и EUR
  (`from $44 (≈ €39)`), на карточке тоже.
- `scripts/flights_digest.py` — на страницах дешёвых билетов локальная валюта:
  для Алматы `≈ KZT`, для Минска `≈ BYN` (основная цена в ₽); курсы кэшируются
  на день в `data/flights/fx.json` (1 запрос на прогон, ~30/мес).
- `scripts/apilayer_check.py` — быстрый healthcheck.

Токен/ключ меняется в дашборде (API Key → Copy Key); после ротации обновить
`.env` и GitHub Secret `APILAYER_KEY`.
