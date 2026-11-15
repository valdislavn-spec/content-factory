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
| `sport-news` | ✅ | ⛔ paused | ⚠️ | — | — |
| `ai-news` | ✅ | ⛔ paused | ⚠️ | — | — |
| `crypto-news` | ✅ | — | ⚠️ | ✅ | ⚠️ |
| `tech-ai-es` | ✅ | ⛔ paused | — | — | — |
| `crypto-es` | ✅ | ⛔ paused | — | — | — |
| `futbol-es` | ✅ | ⛔ paused | — | — | — |

Итого: **6 каналов, 11 включённых направлений**. Mastodon временно снят: аккаунт отдаёт `403 Your login is currently disabled` на каждом посте. Discord оставлен только у
трёх английских каналов, Bluesky/Akkoma — только у крипто-канала, чтобы один
аккаунт не получал поток всех тем и не уходил в антиспам.

Легенда: ✅ — сетевой тест пройден; ⚠️ — креды есть, но сетевой запрос
возвращает ошибку; ⛔ — внешний аккаунт/сервис отключён. На 15.11.2026
Mastodon отвечает `403 Your login is currently disabled`, Discord и Akkoma —
`403 Cloudflare 1010` (исправлен User-Agent, нужен повторный прогон).

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

## Discord: отдельный webhook на каждый канал

Один webhook привязан к одному каналу Discord. Если у `sport-news`,
`ai-news` и `crypto-news` один общий `DISCORD_WEBHOOK_URL`, все три темы
попадут в одну ленту. Для нормальной структуры сервера задайте отдельные
секреты:

```text
DISCORD_WEBHOOK_URL_SPORT_NEWS
DISCORD_WEBHOOK_URL_AI_NEWS
DISCORD_WEBHOOK_URL_CRYPTO_NEWS
```

Общий `DISCORD_WEBHOOK_URL` остаётся fallback'ом. Имена суффиксов — это
`channel.id` в верхнем регистре, дефисы заменены на `_`.

Проверка реального webhook (GET + тестовый пост + удаление) выполняется
workflow **`discord-check`** вручную или ежедневно:

```bash
python scripts/discord_probe.py --sample          # отправит и удалит
python scripts/discord_probe.py --sample --keep   # оставить для осмотра
```

Пост в Discord теперь:

- конвертирует Telegram HTML в Discord Markdown;
- убирает бесполезные в Discord хэштеги;
- добавляет CTA канала (`cta` или `meta.discord_cta`) и ссылку на Telegram;
- добавляет `allowed_mentions: {"parse": []}` — автопост не пингует `@everyone`;
- использует `?wait=true`, чтобы получить `message_id` и писать его в `publishes`;
- при наличии `meta.image_url` прикрепляет картинку через embed.

Проверка `social-check --strict` по-прежнему не ходит в сеть: она проверяет
только наличие/формат кредов. Сетевой статус — только у `discord-check`.

План роста и структура сервера: `docs/growth/discord-playbook.md`.
