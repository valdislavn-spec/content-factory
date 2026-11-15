# Кросспостинг: что подключено и как проверить

## Схема

1. Пост генерируется один раз в Telegram HTML.
2. Публикуется в Telegram — это основное направление каждого канала.
3. Затем вызываются публикаторы из `publisher_ids` канала.
4. Если у соцсети нет кредов, `optional`-публикатор пропускается и не
   останавливает пайплайн. Но **включённое направление без кредов — ошибка
   конфигурации**: её ловит `social-check --strict` в GitHub Actions.
5. Для отдельного аккаунта на канал используется суффикс с id:
   `BLUESKY_HANDLE_CRYPTO_NEWS`, `DISCORD_WEBHOOK_URL_SPORT_NEWS`,
   `MASTODON_TOKEN_CRYPTO_ES` и т.п.

## Текущая матрица (15.11.2026)

| Канал | Telegram | Mastodon | Discord | Bluesky | Akkoma |
|---|---:|:---:|:---:|:---:|:---:|
| `sport-news` | ✅ | ✅ | ✅ | — | — |
| `ai-news` | ✅ | ✅ | ✅ | — | — |
| `crypto-news` | ✅ | — | ✅ | ✅ | ✅ |
| `tech-ai-es` | ✅ | ✅ | — | — | — |
| `crypto-es` | ✅ | ✅ | — | — | — |
| `futbol-es` | ✅ | ✅ | — | — | — |

Итого: **6 каналов, 16 включённых направлений**. Discord оставлен только у
трёх английских каналов, Bluesky/Akkoma — только у крипто-канала, чтобы один
аккаунт не получал поток всех тем и не уходил в антиспам.

`Tumblr`-креды есть, но публикация включена только в отдельном дайджест-
сценарии (сейчас приостановлен). `X`, `VK`, `Facebook`, `LinkedIn`, `Medium`,
`Reddit`, `Instagram`, `Threads` не включены: нет полного набора токенов.
`Pinterest` проверяется отдельно и пока работает в sandbox.

## Проверка перед запуском

```bash
# только реально включённые направления; ⟶ код 1, если чего-то не хватает
python -m content_factory social-check --strict

# машинный отчёт для CI/мониторинга
python -m content_factory social-check --json

# весь каталог доступных соцсетей, включая выключенные
python -m content_factory social-check --all

# сетевая проверка Telegram (getChat + права бота)
python scripts/telegram_check.py

# сетевая проверка Discord-webhook (отправит и удалит тестовое сообщение)
python scripts/discord_probe.py --sample
```

`social-check` не делает сетевых запросов: он проверяет наличие кредов и
`chat_id`, поэтому безопасен для каждого запуска CI. В workflow
`content-factory-cloud-en-es` он стоит до тика и завершает job при пропущенном
секрете — например, если у канала включён Akkoma, а `AKKOMA_TOKEN` не проброшен
в `env`.

## Как добавить сеть

1. Добавить секреты в GitHub → Settings → Secrets and variables → Actions.
2. Пробросить их в `env:` workflow `.github/workflows/content-factory.yml`.
3. Добавить имя публикатора в `publisher_ids` нужного канала.
4. Выполнить `python -m content_factory social-check --strict`.
5. Сделать `python -m content_factory run --channel <id> --dry-run`, затем
   дождаться живого слота.

Для каждого канала можно задать отдельные креды суффиксом id. Без суффикса
используется общий аккаунт.

## Важно

- Mastodon: лимиты инстанса, не спамить; сейчас `MASTODON_NO_LINKS=1`.
- Discord: только свои серверы, webhook = 30 сообщений/мин.
- Bluesky: App Password, не основной пароль.
- Akkoma/Fediverse: один аккаунт = одна тематика; не включать на все каналы.
- X/Reddit: OAuth-токены истекают, нужен refresh.
- Публикации и ошибки пишутся в `data/logs/factory.log` и таблицу `publishes`.
